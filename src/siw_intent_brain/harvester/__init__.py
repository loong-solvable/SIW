"""
Harvester module - Data collection from external sources.

Currently supports:
  - Reddit (via public .json endpoints)

Per project rules (§13):
  - Uses only public, unauthenticated APIs
  - Handles 429/503 with exponential backoff
  - Fail-closed: returns empty results on failure
"""

from .reddit_client import RedditHarvester, HarvestResult

__all__ = [
    "RedditHarvester",
    "HarvestResult",
]

