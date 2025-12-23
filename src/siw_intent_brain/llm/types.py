"""
LLM request/response type definitions.

These dataclasses define the interface between prompt builder and LLM client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ChatMessage:
    """A single message in a chat conversation."""
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ChatRequest:
    """
    Request to send to LLM provider.
    
    Attributes:
        model: Model identifier (e.g., "openai/gpt-4o-mini")
        messages: List of chat messages
        temperature: Sampling temperature (default 0.2 for consistency)
        max_tokens: Maximum tokens in response
        response_format: Optional format hint (e.g., {"type": "json_object"})
    """
    model: str
    messages: tuple[ChatMessage, ...]  # Use tuple for immutability
    temperature: float = 0.2
    max_tokens: int = 600
    response_format: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in self.messages
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.response_format is not None:
            result["response_format"] = self.response_format
        return result


@dataclass(frozen=True)
class ChatResponse:
    """
    Response from LLM provider.
    
    Attributes:
        content: The text content of the response
        raw: Raw response dict from provider
        latency_ms: Total request latency in milliseconds
        retries: Number of retries performed
        status_code: HTTP status code
    """
    content: str
    raw: Dict[str, Any]
    latency_ms: int
    retries: int
    status_code: int

