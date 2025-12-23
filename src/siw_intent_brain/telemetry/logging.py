"""
Structured logging for SIW Intent Brain.

Outputs JSON lines to STDERR (never stdout).
NEVER logs API key or full input text.

By default, logging is DISABLED. Enable with enable_logging().
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Optional

# Logger type alias
Logger = logging.Logger

# Global flag to control logging (default: disabled)
_logging_enabled: bool = False


def enable_logging(enabled: bool = True) -> None:
    """
    Enable or disable logging globally.
    
    When disabled, log_event() is a no-op.
    Default is disabled to keep stdout clean.
    """
    global _logging_enabled
    _logging_enabled = enabled


def is_logging_enabled() -> bool:
    """Check if logging is currently enabled."""
    return _logging_enabled


def get_logger(name: str = "siw_intent_brain", level: str = "INFO") -> Logger:
    """
    Get or create a structured logger.
    
    Uses idempotent setup to avoid duplicate handlers.
    Outputs JSON lines to STDERR (not stdout).
    
    Args:
        name: Logger name.
        level: Log level (DEBUG, INFO, WARNING, ERROR).
    
    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # JSON formatter - output to STDERR, not stdout
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    
    # Don't propagate to root logger
    logger.propagate = False
    
    return logger


class JsonFormatter(logging.Formatter):
    """
    JSON line formatter for structured logging.
    
    Each log record becomes a single JSON line.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON line."""
        payload: Dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
        }
        
        # Add extra fields if present
        if hasattr(record, "event_data") and record.event_data:
            payload.update(record.event_data)
        
        return json.dumps(payload, ensure_ascii=False)


def log_event(
    logger: Logger,
    event: str,
    fields: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log a structured event.
    
    Does NOTHING if logging is disabled (default).
    
    NEVER logs:
      - API key
      - Full input text
      - Sensitive user data
    
    Args:
        logger: Logger instance.
        event: Event name (e.g., "score_start", "score_end", "fail_closed").
        fields: Optional dict of additional fields.
    """
    # No-op if logging is disabled
    if not _logging_enabled:
        return
    
    safe_fields = _sanitize_fields(fields or {})
    safe_fields["event"] = event
    
    # Create log record with extra data
    logger.info(
        event,
        extra={"event_data": safe_fields},
    )


def _sanitize_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize fields to remove sensitive data.
    
    Removes or truncates:
      - api_key
      - text (full input text)
      - content (LLM response content, truncate to 100 chars)
    """
    result: Dict[str, Any] = {}
    
    # Sensitive keys to exclude
    exclude_keys = {"api_key", "key", "token", "password", "secret"}
    
    # Keys to truncate
    truncate_keys = {"text", "content", "body", "message"}
    
    for key, value in fields.items():
        key_lower = key.lower()
        
        # Skip sensitive keys
        if key_lower in exclude_keys:
            continue
        
        # Truncate large text fields
        if key_lower in truncate_keys and isinstance(value, str):
            if len(value) > 100:
                result[key] = value[:100] + "...[truncated]"
            else:
                result[key] = value
            continue
        
        # Include other fields as-is
        result[key] = value
    
    return result
