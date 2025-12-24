"""
Shared fakes for offline tests (importable module).

NOTE:
- Do NOT import from conftest.py in tests. Put reusable fakes here instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# =============================================================================
# Harvest Result Mock
# =============================================================================

@dataclass
class FakeHarvestResult:
    """Mock HarvestResult for testing."""
    items: List[Dict[str, Any]]
    skipped_count: int = 0
    error_message: Optional[str] = None


# =============================================================================
# FakeHarvester Variants
# =============================================================================

class FakeHarvester:
    """
    Fake harvester that returns predefined data.
    
    Per project rules (§13): Tests must use FakeHarvester with pre-recorded mock responses.
    """
    
    def __init__(self, posts: Optional[List[Dict[str, Any]]] = None):
        self._posts = posts if posts is not None else self._default_posts()
    
    def _default_posts(self) -> List[Dict[str, Any]]:
        return [
            {
                "text": "Looking for a cheaper alternative to ToolX. Currently paying $59/mo.",
                "context": {
                    "subreddit": "SaaS",
                    "author": "test_user",
                    "permalink": "/r/SaaS/comments/abc123",
                    "title": "Cheaper ToolX alternative?",
                },
                "_meta": {
                    "created_utc": 1703500000,
                    "score": 42,
                    "num_comments": 15,
                    "id": "abc123",
                },
            },
            {
                "text": "Just discovered Rust and loving it!",
                "context": {
                    "subreddit": "rust",
                    "author": "rust_fan",
                    "permalink": "/r/rust/comments/def456",
                    "title": "Loving Rust",
                },
                "_meta": {
                    "created_utc": 1703400000,
                    "score": 100,
                    "num_comments": 30,
                    "id": "def456",
                },
            },
        ]
    
    def fetch_posts(
        self,
        subreddit: str,
        query: Optional[str] = None,
        limit: int = 10,
        sort: str = "new",
    ) -> FakeHarvestResult:
        """Return mock posts as HarvestResult."""
        items = self._posts[:limit]
        return FakeHarvestResult(items=items, skipped_count=0)


class FakeHarvesterEmpty(FakeHarvester):
    """FakeHarvester that returns empty results (simulates fail-closed)."""
    
    def fetch_posts(self, *args, **kwargs) -> FakeHarvestResult:
        return FakeHarvestResult(
            items=[],
            error_message="Simulated network error",
        )


class FakeHarvesterWithSkips(FakeHarvester):
    """FakeHarvester that simulates skipped empty posts."""
    
    def fetch_posts(self, *args, **kwargs) -> FakeHarvestResult:
        return FakeHarvestResult(
            items=self._default_posts()[:2],
            skipped_count=3,  # 模拟跳过了 3 个空帖子
        )

