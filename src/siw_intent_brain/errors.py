"""
SIW Intent Brain - Exception types and error codes.

All errors derive from SIWError base class.
Error codes are constants for stable API contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# =============================================================================
# Exception Classes
# =============================================================================

class SIWError(Exception):
    """Base error for SIW Intent Brain."""
    pass


class ConfigError(SIWError):
    """Configuration is missing or invalid."""
    pass


class UpstreamError(SIWError):
    """Upstream LLM provider error (HTTP, timeout, empty content)."""
    pass


class ParseError(SIWError):
    """Could not parse/interpret model output as JSON."""
    pass


class ContractError(SIWError):
    """Output violates lead-card contract/schema."""
    pass


# =============================================================================
# Error Codes (must match README + meta.error_code)
# =============================================================================

E_CONFIG_MISSING_KEY = "E_CONFIG_MISSING_KEY"
E_UPSTREAM_HTTP = "E_UPSTREAM_HTTP"
E_UPSTREAM_TIMEOUT = "E_UPSTREAM_TIMEOUT"
E_UPSTREAM_EMPTY_CONTENT = "E_UPSTREAM_EMPTY_CONTENT"
E_PARSE_JSON = "E_PARSE_JSON"
E_CONTRACT_INVALID = "E_CONTRACT_INVALID"


# =============================================================================
# Error Info (structured error metadata)
# =============================================================================

@dataclass(frozen=True)
class ErrorInfo:
    """
    Structured error information for logging and meta output.
    
    Attributes:
        code: Error code constant (E_*)
        detail: Human-readable error detail (truncated, no sensitive data)
        retryable: Whether the operation can be retried
        http_status: HTTP status code if applicable
    """
    code: str
    detail: str
    retryable: bool = False
    http_status: Optional[int] = None
    
    def to_meta_fields(self) -> dict:
        """
        Return fields suitable for LeadCard meta.
        
        Returns dict with:
          - error_code: str
          - error_detail: str (truncated to 280 chars)
        """
        detail = self.detail
        if len(detail) > 280:
            detail = detail[:277] + "..."
        return {
            "error_code": self.code,
            "error_detail": detail,
        }

