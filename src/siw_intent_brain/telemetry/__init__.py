"""
Telemetry module - Logging and metrics.

Provides structured logging and in-memory metrics.
Logging is DISABLED by default - enable with enable_logging().
"""

from .logging import (
    Logger,
    enable_logging,
    get_logger,
    is_logging_enabled,
    log_event,
)
from .metrics import Metrics

__all__ = [
    "Logger",
    "enable_logging",
    "get_logger",
    "is_logging_enabled",
    "log_event",
    "Metrics",
]
