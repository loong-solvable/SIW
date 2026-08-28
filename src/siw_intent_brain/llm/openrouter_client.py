"""
OpenRouter HTTP Client with retry and backoff.

Implements the LLM client interface for OpenRouter API.
Never logs API key or full input text.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests

from ..config import BrainConfig
from ..errors import (
    UpstreamError,
    E_UPSTREAM_HTTP,
    E_UPSTREAM_TIMEOUT,
    E_UPSTREAM_EMPTY_CONTENT,
)
from .types import ChatRequest, ChatResponse


# HTTP status codes that are retryable
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class OpenRouterClient:
    """
    OpenRouter chat completions client.
    
    Features:
      - Retry with exponential backoff
      - Timeout handling
      - Error classification with proper error codes
    
    Never logs API key or sensitive content.
    """

    def __init__(self, cfg: BrainConfig) -> None:
        """
        Initialize client with configuration.
        
        Args:
            cfg: BrainConfig with API key, base URL, timeout, retries, backoff.
        """
        self.cfg = cfg

    def complete(self, req: ChatRequest) -> ChatResponse:
        """
        Send chat completion request to OpenRouter.
        
        Args:
            req: ChatRequest with model, messages, temperature, max_tokens.
        
        Returns:
            ChatResponse with content, raw response, latency, retries, status code.
        
        Raises:
            UpstreamError: On HTTP errors, timeout, or empty content.
        """
        headers = self._build_headers()
        payload = req.to_dict()
        
        start_time = time.time()
        retries = 0
        last_exception: Optional[Exception] = None
        last_status_code = 0
        
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                response = self._make_request(headers, payload)
                last_status_code = response.status_code
                
                # Check for HTTP errors
                if response.status_code >= 400:
                    error_msg = self._safe_error_message(response)
                    
                    # Retry if status is retryable and we have attempts left
                    if response.status_code in RETRYABLE_STATUS_CODES and attempt < self.cfg.max_retries:
                        retries += 1
                        self._wait_backoff(attempt)
                        continue
                    
                    raise UpstreamError(
                        f"{E_UPSTREAM_HTTP}: HTTP {response.status_code} - {error_msg}"
                    )
                
                # Parse response
                raw = response.json()
                content = self._extract_content(raw)
                
                # Check for empty content
                if not content or not content.strip():
                    raise UpstreamError(f"{E_UPSTREAM_EMPTY_CONTENT}: Empty response content")
                
                latency_ms = int((time.time() - start_time) * 1000)
                usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}

                def non_negative_int(value: Any) -> int:
                    return int(value) if isinstance(value, (int, float)) and value >= 0 else 0

                input_tokens = non_negative_int(usage.get("prompt_tokens"))
                output_tokens = non_negative_int(usage.get("completion_tokens"))
                total_tokens = non_negative_int(usage.get("total_tokens"))
                if total_tokens == 0:
                    total_tokens = input_tokens + output_tokens

                cost = usage.get("cost")
                reported_cost_usd_micros = (
                    round(float(cost) * 1_000_000)
                    if isinstance(cost, (int, float)) and cost >= 0
                    else None
                )
                
                return ChatResponse(
                    content=content,
                    raw=raw,
                    latency_ms=latency_ms,
                    retries=retries,
                    status_code=response.status_code,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    reported_cost_usd_micros=reported_cost_usd_micros,
                )
            
            except requests.Timeout as e:
                last_exception = e
                last_status_code = 0
                
                if attempt < self.cfg.max_retries:
                    retries += 1
                    self._wait_backoff(attempt)
                    continue
                
                raise UpstreamError(
                    f"{E_UPSTREAM_TIMEOUT}: Request timed out after {self.cfg.timeout_s}s"
                ) from e
            
            except requests.RequestException as e:
                last_exception = e
                
                if attempt < self.cfg.max_retries:
                    retries += 1
                    self._wait_backoff(attempt)
                    continue
                
                raise UpstreamError(
                    f"{E_UPSTREAM_HTTP}: Request failed - {type(e).__name__}"
                ) from e
            
            except UpstreamError:
                # Re-raise UpstreamError as-is (already has proper error code)
                raise
            
            except Exception as e:
                last_exception = e
                
                if attempt < self.cfg.max_retries:
                    retries += 1
                    self._wait_backoff(attempt)
                    continue
                
                raise UpstreamError(
                    f"{E_UPSTREAM_HTTP}: Unexpected error - {type(e).__name__}"
                ) from e
        
        # Should not reach here, but safety fallback
        raise UpstreamError(
            f"{E_UPSTREAM_HTTP}: Failed after {self.cfg.max_retries} retries"
        )

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers (never logs API key)."""
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }
        
        if self.cfg.http_referer:
            headers["HTTP-Referer"] = self.cfg.http_referer
        
        if self.cfg.x_title:
            headers["X-Title"] = self.cfg.x_title
        
        return headers

    def _make_request(
        self, headers: Dict[str, str], payload: Dict[str, Any]
    ) -> requests.Response:
        """
        Make HTTP POST request.
        
        Separated for easier testing/mocking.
        """
        return requests.post(
            self.cfg.base_url,
            headers=headers,
            json=payload,
            timeout=self.cfg.timeout_s,
        )

    def _extract_content(self, raw: Dict[str, Any]) -> str:
        """
        Extract message content from OpenRouter response.
        
        Expected structure:
            {"choices": [{"message": {"content": "..."}}]}
        """
        try:
            choices = raw.get("choices", [])
            if not choices:
                return ""
            first_choice = choices[0]
            message = first_choice.get("message", {})
            return str(message.get("content", "") or "")
        except (IndexError, KeyError, TypeError):
            return ""

    def _wait_backoff(self, attempt: int) -> None:
        """
        Wait with exponential backoff.
        
        Formula: backoff_s * (2 ** (attempt - 1))
        Example with backoff_s=1.2:
          attempt 1 -> 1.2s
          attempt 2 -> 2.4s
          attempt 3 -> 4.8s
        """
        wait_time = self.cfg.backoff_s * (2 ** (attempt - 1))
        time.sleep(wait_time)

    def _safe_error_message(self, response: requests.Response) -> str:
        """
        Extract safe error message from response (no sensitive data).
        
        Truncates to 200 chars to avoid log bloat.
        """
        try:
            text = response.text[:200] if response.text else "No response body"
            return text
        except Exception:
            return "Could not read response body"
