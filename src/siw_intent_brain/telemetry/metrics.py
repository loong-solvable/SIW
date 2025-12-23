"""
In-memory metrics for SIW Intent Brain.

Simple counters for:
  - Total requests
  - Fail-closed count
  - Retry count
  - Latency tracking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Metrics:
    """
    In-memory metrics counters.
    
    Thread-safety is NOT guaranteed - use only in single-threaded contexts
    or add locks for multi-threaded use.
    """
    
    # Request counts
    total_requests: int = 0
    total_ok: int = 0
    total_fail_closed: int = 0
    
    # Retry tracking
    upstream_retries_total: int = 0
    
    # Latency tracking (in milliseconds)
    total_latency_ms: int = 0
    
    # Parser mode counts
    parser_mode_counts: Dict[str, int] = field(default_factory=lambda: {
        "strict": 0,
        "extracted": 0,
        "fail_closed": 0,
    })

    def record(
        self,
        latency_ms: int,
        retries: int,
        fail_closed: bool,
        parser_mode: str = "strict",
    ) -> None:
        """
        Record metrics for a single request.
        
        Args:
            latency_ms: Request latency in milliseconds.
            retries: Number of upstream retries.
            fail_closed: Whether request resulted in fail-closed.
            parser_mode: Parser mode used (strict/extracted/fail_closed).
        """
        self.total_requests += 1
        self.total_latency_ms += max(0, int(latency_ms))
        self.upstream_retries_total += max(0, int(retries))
        
        if fail_closed:
            self.total_fail_closed += 1
        else:
            self.total_ok += 1
        
        # Track parser mode
        if parser_mode in self.parser_mode_counts:
            self.parser_mode_counts[parser_mode] += 1

    def avg_latency_ms(self) -> float:
        """
        Calculate average latency in milliseconds.
        
        Returns:
            Average latency, or 0.0 if no requests recorded.
        """
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    def fail_closed_rate(self) -> float:
        """
        Calculate fail-closed rate as percentage.
        
        Returns:
            Fail-closed rate (0.0 to 1.0), or 0.0 if no requests.
        """
        if self.total_requests == 0:
            return 0.0
        return self.total_fail_closed / self.total_requests

    def summary(self) -> Dict[str, float]:
        """
        Get metrics summary dict.
        
        Returns:
            Dict with key metrics.
        """
        return {
            "total_requests": self.total_requests,
            "total_ok": self.total_ok,
            "total_fail_closed": self.total_fail_closed,
            "upstream_retries_total": self.upstream_retries_total,
            "avg_latency_ms": self.avg_latency_ms(),
            "fail_closed_rate": self.fail_closed_rate(),
        }

