"""
SIW Intent Brain - Main entry point.

IntentBrain.score() orchestrates the full pipeline:
  prompt -> OpenRouterClient -> extract_json -> normalize -> heuristics -> validate

CRITICAL: Never throws uncaught exceptions. Always returns valid LeadCard.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, TYPE_CHECKING

from .config import BrainConfig, load_config
from .contracts import (
    SCHEMA_VERSION,
    LeadCard,
    LeadTier,
    RecommendedNextStep,
    build_lead_card,
    default_extracted_signals,
    default_scores,
    validate_lead_card,
)
from .errors import (
    ErrorInfo,
    ParseError,
    UpstreamError,
    E_CONTRACT_INVALID,
    E_PARSE_JSON,
    E_UPSTREAM_EMPTY_CONTENT,
    E_UPSTREAM_HTTP,
    E_UPSTREAM_TIMEOUT,
)
from .heuristics.next_step import compute_next_step
from .heuristics.tiering import compute_lead_tier
from .llm.openrouter_client import OpenRouterClient
from .llm.types import ChatResponse
from .parsing.json_extractor import extract_json
from .parsing.normalizer import normalize_llm_output
from .prompt.builder import build_chat_request

if TYPE_CHECKING:
    from .telemetry.logging import Logger
    from .telemetry.metrics import Metrics


class IntentBrain:
    """
    Main scoring API for SIW Intent Brain.
    
    Usage:
        brain = IntentBrain.from_env()
        card = brain.score("Looking for a cheaper alternative...", {"subreddit": "marketing"})
    
    Features:
        - Full pipeline orchestration
        - Fail-closed on any error
        - Heuristic fallback for missing/invalid LLM fields
        - Soft fail-closed when confidence < min_confidence
        - All outputs pass validate_lead_card()
    
    Never throws uncaught exceptions to caller.
    Never logs API key or full input text.
    """

    def __init__(
        self,
        cfg: BrainConfig,
        client: Optional[OpenRouterClient] = None,
    ) -> None:
        """
        Initialize IntentBrain.
        
        Args:
            cfg: Brain configuration (API key, model, thresholds).
            client: Optional LLM client (for testing with FakeClient).
        """
        self.cfg = cfg
        self.client = client or OpenRouterClient(cfg)
        
        # Lazy-loaded telemetry (avoid import errors)
        self._logger: Optional[Any] = None
        self._metrics: Optional[Any] = None

    @classmethod
    def from_env(cls, config_path: Optional[str] = None) -> "IntentBrain":
        """
        Create IntentBrain from environment variables and optional config file.
        
        Args:
            config_path: Optional path to YAML config file.
        
        Returns:
            Configured IntentBrain instance.
        
        Raises:
            ConfigError: If OPENROUTER_API_KEY is missing.
        """
        cfg = load_config(config_path)
        return cls(cfg)

    def score(self, text: str, context: Optional[Dict[str, Any]] = None) -> LeadCard:
        """
        Score text for commercial intent signals.
        
        This is the main entry point. It orchestrates:
          1. Build chat request
          2. Call LLM provider
          3. Parse JSON response
          4. Normalize output
          5. Apply heuristic fallbacks
          6. Apply soft fail-closed if low confidence
          7. Validate contract
        
        Args:
            text: Text to analyze (post body, comment, etc.)
            context: Optional context dict (subreddit, title, author, permalink)
        
        Returns:
            LeadCard dict that ALWAYS passes validate_lead_card().
            - ok=true on success
            - ok=false on any failure (fail-closed)
        
        Never raises exceptions to caller.
        """
        t0 = time.time()
        ctx = context or {}
        
        # Initialize tracking variables
        parser_mode = "fail_closed"
        retries = 0
        latency_ms = 0
        
        try:
            # === Step 0: Empty input short-circuit ===
            if not text or not str(text).strip():
                return self._build_low_signal_card(
                    reason="Empty text input.",
                    t0=t0,
                    parser_mode="fail_closed",
                )
            
            self._log_event("score_start", {"model": self.cfg.model})
            
            # === Step 1: Build chat request ===
            try:
                req = build_chat_request(self.cfg, text=text, context=ctx)
            except Exception as e:
                return self._build_fail_closed_card(
                    error_info=ErrorInfo(
                        code=E_CONTRACT_INVALID,
                        detail=f"Prompt build failed: {type(e).__name__}: {str(e)[:100]}",
                    ),
                    t0=t0,
                    parser_mode="fail_closed",
                    retries=0,
                )
            
            # === Step 2: Call LLM provider ===
            try:
                resp: ChatResponse = self.client.complete(req)
                retries = resp.retries
            except UpstreamError as e:
                error_code = self._classify_upstream_error(str(e))
                return self._build_fail_closed_card(
                    error_info=ErrorInfo(
                        code=error_code,
                        detail=str(e)[:200],
                        retryable=True,
                    ),
                    t0=t0,
                    parser_mode="fail_closed",
                    retries=retries,
                )
            except Exception as e:
                return self._build_fail_closed_card(
                    error_info=ErrorInfo(
                        code=E_UPSTREAM_HTTP,
                        detail=f"Unexpected upstream error: {type(e).__name__}",
                    ),
                    t0=t0,
                    parser_mode="fail_closed",
                    retries=retries,
                )
            
            # === Step 3: Parse JSON ===
            try:
                obj, parser_mode = extract_json(resp.content)
            except ParseError as e:
                return self._build_fail_closed_card(
                    error_info=ErrorInfo(
                        code=E_PARSE_JSON,
                        detail=str(e)[:200],
                    ),
                    t0=t0,
                    parser_mode="fail_closed",
                    retries=resp.retries,
                )
            
            # === Step 4: Normalize ===
            normalized, flags = normalize_llm_output(
                raw=obj,
                max_rationale_chars=self.cfg.max_rationale_chars,
                max_list_items=self.cfg.max_list_items,
            )
            
            scores = normalized["scores"]
            confidence = normalized["confidence"]
            
            # === Step 5: Heuristic fallbacks ===
            lead_tier: LeadTier
            if not flags.tier_valid or not normalized["lead_tier"]:
                lead_tier = compute_lead_tier(
                    urgency=scores["urgency"],
                    pain=scores["pain_point_intensity"],
                    commercial=scores["commercial_relevance"],
                    seeking=scores["solution_seeking"],
                    confidence=confidence,
                )
            else:
                lead_tier = normalized["lead_tier"]  # type: ignore
            
            next_step: RecommendedNextStep
            if not flags.next_step_valid or not normalized["recommended_next_step"]:
                next_step = compute_next_step(
                    pain=scores["pain_point_intensity"],
                    commercial=scores["commercial_relevance"],
                    seeking=scores["solution_seeking"],
                    confidence=confidence,
                )
            else:
                next_step = normalized["recommended_next_step"]  # type: ignore
            
            # === Step 6: Soft fail-closed + D-tier consistency ===
            safety_notes = list(normalized["safety_notes"])
            
            if confidence < self.cfg.min_confidence:
                # Low confidence: force D-tier and monitor
                lead_tier = "D"
                if next_step not in ("ignore", "monitor"):
                    next_step = "monitor"
                safety_notes.append("Low confidence: conservative fallback applied.")
            elif lead_tier == "D":
                # D-tier consistency: very low composite should be ignore
                # (re-check heuristic even if LLM gave a valid next_step)
                composite = (
                    scores["commercial_relevance"]
                    + scores["solution_seeking"]
                    + scores["pain_point_intensity"]
                ) / 3.0
                if composite < 0.18 and next_step not in ("ignore",):
                    next_step = "ignore"
            
            # === Step 7: Build LeadCard ===
            latency_ms = int((time.time() - t0) * 1000)
            
            card = build_lead_card(
                ok=True,
                scores=scores,
                confidence=confidence,
                lead_tier=lead_tier,
                recommended_next_step=next_step,
                rationale=normalized["rationale"],
                extracted_signals=normalized["extracted_signals"],
                safety_notes=safety_notes,
                meta={
                    "model": self.cfg.model,
                    "provider": "openrouter",
                    "latency_ms": latency_ms,
                    "retries": resp.retries,
                    "parser_mode": parser_mode,
                    "schema_version": SCHEMA_VERSION,
                },
            )
            
            # === Step 8: Validate contract ===
            validation_errors = validate_lead_card(card)
            
            if validation_errors:
                return self._build_fail_closed_card(
                    error_info=ErrorInfo(
                        code=E_CONTRACT_INVALID,
                        detail=f"Validation failed: {'; '.join(validation_errors[:3])}",
                    ),
                    t0=t0,
                    parser_mode="fail_closed",
                    retries=resp.retries,
                    validation_error=True,
                )
            
            # === Success ===
            self._record_metrics(latency_ms=latency_ms, retries=resp.retries, fail_closed=False)
            self._log_event("score_end", {
                "ok": True,
                "latency_ms": latency_ms,
                "retries": resp.retries,
                "parser_mode": parser_mode,
                "lead_tier": lead_tier,
            })
            
            return card
        
        except Exception as e:
            # Catch-all: NEVER throw to caller
            return self._build_fail_closed_card(
                error_info=ErrorInfo(
                    code=E_CONTRACT_INVALID,
                    detail=f"Unexpected error in score(): {type(e).__name__}",
                ),
                t0=t0,
                parser_mode="fail_closed",
                retries=retries,
            )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _build_low_signal_card(
        self,
        reason: str,
        t0: float,
        parser_mode: str,
    ) -> LeadCard:
        """
        Build ok=true card with minimal signal (tier D, monitor).
        
        Used for empty/whitespace-only input.
        """
        latency_ms = int((time.time() - t0) * 1000)
        
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale=reason[:self.cfg.max_rationale_chars],
            extracted_signals=default_extracted_signals(),
            safety_notes=["Low signal input."],
            meta={
                "model": self.cfg.model,
                "provider": "openrouter",
                "latency_ms": latency_ms,
                "retries": 0,
                "parser_mode": parser_mode,
                "schema_version": SCHEMA_VERSION,
            },
        )
        
        self._record_metrics(latency_ms=latency_ms, retries=0, fail_closed=False)
        return card

    def _build_fail_closed_card(
        self,
        error_info: ErrorInfo,
        t0: float,
        parser_mode: str,
        retries: int = 0,
        validation_error: bool = False,
    ) -> LeadCard:
        """
        Build ok=false fail-closed card.
        
        Always returns valid LeadCard with:
          - ok=false
          - tier=D
          - next_step=monitor
          - error details in meta
        """
        latency_ms = int((time.time() - t0) * 1000)
        
        # Build meta with error fields
        meta_fields = error_info.to_meta_fields()
        meta = {
            "model": self.cfg.model,
            "provider": "openrouter",
            "latency_ms": latency_ms,
            "retries": retries,
            "parser_mode": parser_mode,
            "schema_version": SCHEMA_VERSION,
            "error_code": meta_fields["error_code"],
            "error_detail": meta_fields["error_detail"],
        }
        
        if validation_error:
            meta["validation_error"] = True
        
        card = build_lead_card(
            ok=False,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale=f"Fail-closed: {meta_fields['error_detail'][:350]}",
            extracted_signals=default_extracted_signals(),
            safety_notes=["Fail-closed: conservative output."],
            meta=meta,
        )
        
        self._record_metrics(latency_ms=latency_ms, retries=retries, fail_closed=True)
        self._log_event("fail_closed", {
            "ok": False,
            "error_code": error_info.code,
            "latency_ms": latency_ms,
            "retries": retries,
        })
        
        return card

    def _classify_upstream_error(self, error_str: str) -> str:
        """Classify upstream error string to error code."""
        if E_UPSTREAM_TIMEOUT in error_str:
            return E_UPSTREAM_TIMEOUT
        if E_UPSTREAM_EMPTY_CONTENT in error_str:
            return E_UPSTREAM_EMPTY_CONTENT
        return E_UPSTREAM_HTTP

    def _log_event(self, event: str, fields: Optional[Dict[str, Any]] = None) -> None:
        """Log structured event (lazy-load logger)."""
        try:
            if self._logger is None:
                from .telemetry.logging import get_logger
                self._logger = get_logger()
            
            from .telemetry.logging import log_event
            log_event(self._logger, event, fields)
        except Exception:
            # Never fail on logging
            pass

    def _record_metrics(
        self,
        latency_ms: int,
        retries: int,
        fail_closed: bool,
    ) -> None:
        """Record metrics (lazy-load metrics)."""
        try:
            if self._metrics is None:
                from .telemetry.metrics import Metrics
                self._metrics = Metrics()
            
            self._metrics.record(
                latency_ms=latency_ms,
                retries=retries,
                fail_closed=fail_closed,
            )
        except Exception:
            # Never fail on metrics
            pass

