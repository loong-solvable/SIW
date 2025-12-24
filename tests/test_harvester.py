"""
Tests for harvester module.

All tests are OFFLINE - use FakeHarvester with mock data.
Per project rules (§8): Tests must run offline with FakeHarvester.
"""

from __future__ import annotations

import json

from siw_intent_brain import validate_lead_card
from siw_intent_brain.config import BrainConfig
from siw_intent_brain.brain import IntentBrain
from siw_intent_brain.llm.types import ChatRequest, ChatResponse

from tests._fixtures import FakeHarvester, FakeHarvesterEmpty, FakeHarvesterWithSkips


# =============================================================================
# FakeClient for Brain Testing
# =============================================================================

class FakeClient:
    """Fake LLM client for offline testing."""
    
    def complete(self, req: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content=json.dumps({
                "scores": {
                    "urgency": 0.7,
                    "pain_point_intensity": 0.8,
                    "commercial_relevance": 0.9,
                    "solution_seeking": 0.95,
                },
                "confidence": 0.9,
                "lead_tier": "S",
                "recommended_next_step": "offer_resource",
                "rationale": "High intent.",
                "extracted_signals": {
                    "problem_summary": "User seeking alternative",
                    "constraints": ["budget"],
                    "budget_hints": ["$59/mo"],
                    "tooling_stack": ["ToolX"],
                    "keywords": ["alternative", "cheaper"],
                },
                "safety_notes": [],
            }),
            raw={},
            latency_ms=50,
            retries=0,
            status_code=200,
        )


# =============================================================================
# Tests
# =============================================================================

class TestFakeHarvester:
    """Tests for FakeHarvester mock."""

    def test_returns_posts(self) -> None:
        harvester = FakeHarvester()
        result = harvester.fetch_posts("test")
        
        assert len(result.items) == 2
        assert result.items[0]["text"]
        assert result.items[0]["context"]["subreddit"]
        assert result.error_message is None

    def test_respects_limit(self) -> None:
        harvester = FakeHarvester()
        result = harvester.fetch_posts("test", limit=1)
        
        assert len(result.items) == 1


class TestFakeHarvesterEmpty:
    """Tests for fail-closed behavior (empty results)."""

    def test_returns_empty_on_error(self) -> None:
        harvester = FakeHarvesterEmpty()
        result = harvester.fetch_posts("test")
        
        assert result.items == []
        assert result.error_message is not None


class TestFakeHarvesterWithSkips:
    """Tests for skipped posts handling."""

    def test_reports_skipped_count(self) -> None:
        harvester = FakeHarvesterWithSkips()
        result = harvester.fetch_posts("test")
        
        assert len(result.items) == 2
        assert result.skipped_count == 3


class TestHarvestIntegration:
    """Integration tests using FakeHarvester + FakeClient."""

    def test_harvest_and_score_offline(self) -> None:
        """Full pipeline: harvest → score → validate."""
        # Setup
        harvester = FakeHarvester()
        cfg = BrainConfig(api_key="test-key")
        brain = IntentBrain(cfg, client=FakeClient())
        
        # Harvest
        result = harvester.fetch_posts("SaaS", limit=2)
        
        # Score each post
        for item in result.items:
            card = brain.score(text=item["text"], context=item["context"])
            
            # Validate
            errors = validate_lead_card(card)
            assert errors == [], f"Validation failed: {errors}"
            assert card["meta"]["model"] == "openai/gpt-4o-mini"

    def test_empty_harvest_no_crash(self) -> None:
        """Empty harvest result should not crash (fail-closed)."""
        harvester = FakeHarvesterEmpty()
        result = harvester.fetch_posts("test")
        
        assert result.items == []
        # No crash, just empty results

