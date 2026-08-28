"""
Offline tests for IntentBrain.

All tests use FakeClient - NO real network requests.
Tests verify correct behavior with valid LLM responses.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from siw_intent_brain import (
    BrainConfig,
    IntentBrain,
    validate_lead_card,
)
from siw_intent_brain.llm.types import ChatRequest, ChatResponse


# =============================================================================
# FakeClient - Returns Valid Responses
# =============================================================================

class FakeClient:
    """Fake LLM client that returns configurable responses."""
    
    def __init__(self, content: str, retries: int = 0, status_code: int = 200):
        self.content = content
        self.retries = retries
        self.status_code = status_code
        self.call_count = 0
        self.last_request: ChatRequest | None = None
    
    def complete(self, req: ChatRequest) -> ChatResponse:
        self.call_count += 1
        self.last_request = req
        return ChatResponse(
            content=self.content,
            raw={"choices": [{"message": {"content": self.content}}]},
            latency_ms=42,
            retries=self.retries,
            status_code=self.status_code,
        )


def make_valid_llm_response(
    urgency: float = 0.8,
    pain: float = 0.9,
    commercial: float = 0.7,
    seeking: float = 0.95,
    confidence: float = 0.9,
    lead_tier: str = "S",
    next_step: str = "offer_resource",
) -> str:
    """Generate a valid LLM response JSON."""
    obj = {
        "scores": {
            "urgency": urgency,
            "pain_point_intensity": pain,
            "commercial_relevance": commercial,
            "solution_seeking": seeking,
        },
        "confidence": confidence,
        "lead_tier": lead_tier,
        "recommended_next_step": next_step,
        "rationale": "High commercial intent detected. User is actively seeking alternatives.",
        "extracted_signals": {
            "problem_summary": "User needs a cheaper monitoring solution",
            "constraints": ["budget", "self-hosted"],
            "budget_hints": ["$59/mo too expensive"],
            "tooling_stack": ["ToolX"],
            "keywords": ["alternative", "cheaper", "monitor"],
        },
        "safety_notes": ["Be polite and helpful."],
    }
    return json.dumps(obj)


@pytest.fixture
def config() -> BrainConfig:
    """Basic config for testing."""
    return BrainConfig(
        api_key="test-key-12345",
        model="openai/gpt-4o-mini",
        min_confidence=0.35,
        max_rationale_chars=400,
        max_list_items=50,
    )


# =============================================================================
# Test: Successful Scoring (Strict JSON)
# =============================================================================

class TestSuccessfulScoring:
    """Tests for successful scoring with valid LLM responses."""

    def test_score_returns_ok_true(self, config: BrainConfig) -> None:
        """Successful scoring returns ok=true."""
        client = FakeClient(make_valid_llm_response())
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Looking for a cheaper alternative to ToolX")
        
        assert card["ok"] is True

    def test_score_validates_output(self, config: BrainConfig) -> None:
        """All outputs pass validate_lead_card()."""
        client = FakeClient(make_valid_llm_response())
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text", {"subreddit": "marketing"})
        
        errors = validate_lead_card(card)
        assert errors == [], f"Validation failed: {errors}"

    def test_score_parser_mode_strict(self, config: BrainConfig) -> None:
        """Clean JSON returns parser_mode=strict."""
        client = FakeClient(make_valid_llm_response())
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["meta"]["parser_mode"] == "strict"

    def test_score_preserves_scores(self, config: BrainConfig) -> None:
        """Scores from LLM are preserved."""
        client = FakeClient(make_valid_llm_response(
            urgency=0.5,
            pain=0.6,
            commercial=0.7,
            seeking=0.8,
        ))
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["scores"]["urgency"] == 0.5
        assert card["scores"]["pain_point_intensity"] == 0.6
        assert card["scores"]["commercial_relevance"] == 0.7
        assert card["scores"]["solution_seeking"] == 0.8

    def test_score_preserves_tier(self, config: BrainConfig) -> None:
        """Lead tier from LLM is preserved when valid."""
        client = FakeClient(make_valid_llm_response(lead_tier="A"))
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["lead_tier"] == "A"

    def test_score_preserves_next_step(self, config: BrainConfig) -> None:
        """Next step from LLM is preserved when valid."""
        client = FakeClient(make_valid_llm_response(next_step="ask_question"))
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["recommended_next_step"] == "ask_question"

    def test_score_meta_fields(self, config: BrainConfig) -> None:
        """Meta contains required fields."""
        client = FakeClient(make_valid_llm_response())
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        meta = card["meta"]
        assert meta["model"] == config.model
        assert meta["provider"] == config.provider
        assert meta["schema_version"] == "lead_card.v1"
        assert isinstance(meta["latency_ms"], int)
        assert meta["latency_ms"] >= 0
        assert isinstance(meta["retries"], int)
        assert meta["total_tokens"] == 0
        assert meta["reported_cost_usd_micros"] is None

    def test_score_extracted_signals(self, config: BrainConfig) -> None:
        """Extracted signals are included."""
        client = FakeClient(make_valid_llm_response())
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        signals = card["extracted_signals"]
        assert "problem_summary" in signals
        assert isinstance(signals["constraints"], list)
        assert isinstance(signals["budget_hints"], list)
        assert isinstance(signals["tooling_stack"], list)
        assert isinstance(signals["keywords"], list)


# =============================================================================
# Test: Extracted JSON (parser_mode=extracted)
# =============================================================================

class TestExtractedJson:
    """Tests for JSON extraction from messy LLM output."""

    def test_parser_mode_extracted_with_prefix(self, config: BrainConfig) -> None:
        """JSON with text prefix returns parser_mode=extracted."""
        response = "Here's my analysis:\n" + make_valid_llm_response()
        client = FakeClient(response)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["ok"] is True
        assert card["meta"]["parser_mode"] == "extracted"

    def test_parser_mode_extracted_with_suffix(self, config: BrainConfig) -> None:
        """JSON with text suffix returns parser_mode=extracted."""
        response = make_valid_llm_response() + "\n\nHope this helps!"
        client = FakeClient(response)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["ok"] is True
        assert card["meta"]["parser_mode"] == "extracted"

    def test_parser_mode_extracted_with_both(self, config: BrainConfig) -> None:
        """JSON with text on both sides returns parser_mode=extracted."""
        response = "Analysis:\n" + make_valid_llm_response() + "\nEnd."
        client = FakeClient(response)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["ok"] is True
        assert card["meta"]["parser_mode"] == "extracted"
        errors = validate_lead_card(card)
        assert errors == []


# =============================================================================
# Test: Empty Input Handling
# =============================================================================

class TestEmptyInput:
    """Tests for empty/whitespace input handling."""

    def test_empty_text_returns_low_signal(self, config: BrainConfig) -> None:
        """Empty text returns ok=true with tier D."""
        client = FakeClient(make_valid_llm_response())
        brain = IntentBrain(config, client=client)
        
        card = brain.score("")
        
        assert card["ok"] is True
        assert card["lead_tier"] == "D"
        assert card["recommended_next_step"] == "monitor"
        # Client should NOT be called
        assert client.call_count == 0

    def test_whitespace_text_returns_low_signal(self, config: BrainConfig) -> None:
        """Whitespace-only text returns ok=true with tier D."""
        client = FakeClient(make_valid_llm_response())
        brain = IntentBrain(config, client=client)
        
        card = brain.score("   \n\t   ")
        
        assert card["ok"] is True
        assert card["lead_tier"] == "D"
        assert client.call_count == 0

    def test_empty_input_validates(self, config: BrainConfig) -> None:
        """Empty input still returns valid LeadCard."""
        client = FakeClient(make_valid_llm_response())
        brain = IntentBrain(config, client=client)
        
        card = brain.score("")
        
        errors = validate_lead_card(card)
        assert errors == []


# =============================================================================
# Test: Retries Tracking
# =============================================================================

class TestRetriesTracking:
    """Tests for retry count tracking in meta."""

    def test_retries_zero(self, config: BrainConfig) -> None:
        """Successful first attempt has retries=0."""
        client = FakeClient(make_valid_llm_response(), retries=0)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["meta"]["retries"] == 0

    def test_retries_tracked(self, config: BrainConfig) -> None:
        """Retries from client are tracked in meta."""
        client = FakeClient(make_valid_llm_response(), retries=2)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["meta"]["retries"] == 2


# =============================================================================
# Test: Context Handling
# =============================================================================

class TestContextHandling:
    """Tests for context parameter handling."""

    def test_context_passed_to_prompt(self, config: BrainConfig) -> None:
        """Context is passed to prompt builder."""
        client = FakeClient(make_valid_llm_response())
        brain = IntentBrain(config, client=client)
        
        card = brain.score(
            "Test text",
            context={"subreddit": "marketing", "title": "Help wanted"}
        )
        
        assert card["ok"] is True
        # Verify context was in the request
        assert client.last_request is not None
        user_content = client.last_request.messages[1].content
        assert "marketing" in user_content

    def test_none_context_handled(self, config: BrainConfig) -> None:
        """None context is handled gracefully."""
        client = FakeClient(make_valid_llm_response())
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text", context=None)
        
        assert card["ok"] is True
        errors = validate_lead_card(card)
        assert errors == []


# =============================================================================
# Test: from_env Factory
# =============================================================================

class TestFromEnv:
    """Tests for from_env factory method."""

    def test_from_env_with_env_var(self, monkeypatch) -> None:
        """from_env loads config from environment."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-from-env")
        
        brain = IntentBrain.from_env()
        
        assert brain.cfg.api_key == "test-key-from-env"

    def test_from_env_missing_key_raises(self, monkeypatch) -> None:
        """from_env raises ConfigError if API key missing."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        
        from siw_intent_brain.errors import ConfigError
        with pytest.raises(ConfigError):
            IntentBrain.from_env()


# =============================================================================
# Test: D-tier Low Composite Forces Ignore
# =============================================================================

class TestDTierLowCompositeIgnore:
    """Tests for D-tier consistency: low composite should force ignore."""

    def test_dtier_low_composite_forces_ignore(self) -> None:
        """
        D-tier with scores P=C=S=0, conf=0.8, LLM next_step=monitor
        should be corrected to ignore (composite < 0.18).
        """
        # LLM returns D-tier with monitor, but composite is 0
        response = json.dumps({
            "scores": {
                "urgency": 0.1,
                "pain_point_intensity": 0.0,
                "commercial_relevance": 0.0,
                "solution_seeking": 0.0,
            },
            "confidence": 0.8,  # High confidence, so not soft fail-closed
            "lead_tier": "D",
            "recommended_next_step": "monitor",  # LLM says monitor
            "rationale": "No commercial signal.",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        })
        
        cfg = BrainConfig(api_key="test-key")
        client = FakeClient(content=response)
        brain = IntentBrain(cfg, client=client)
        
        card = brain.score("Just saying hi", {})
        
        # Composite = (0 + 0 + 0) / 3 = 0 < 0.18
        # Should be corrected to ignore
        assert card["lead_tier"] == "D"
        assert card["recommended_next_step"] == "ignore"
        
        # Still valid
        errors = validate_lead_card(card)
        assert errors == []

    def test_dtier_above_threshold_keeps_monitor(self) -> None:
        """
        D-tier with composite >= 0.18 should NOT be corrected.
        """
        # LLM returns D-tier with monitor, composite = 0.2
        response = json.dumps({
            "scores": {
                "urgency": 0.2,
                "pain_point_intensity": 0.2,
                "commercial_relevance": 0.2,
                "solution_seeking": 0.2,
            },
            "confidence": 0.8,
            "lead_tier": "D",
            "recommended_next_step": "monitor",
            "rationale": "Low signal.",
            "extracted_signals": {
                "problem_summary": "Minimal content",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        })
        
        cfg = BrainConfig(api_key="test-key")
        client = FakeClient(content=response)
        brain = IntentBrain(cfg, client=client)
        
        card = brain.score("Some text", {})
        
        # Composite = (0.2 + 0.2 + 0.2) / 3 = 0.2 >= 0.18
        # Should NOT be corrected
        assert card["lead_tier"] == "D"
        assert card["recommended_next_step"] == "monitor"
        
        errors = validate_lead_card(card)
        assert errors == []

    def test_low_confidence_takes_priority_over_dtier_correction(self) -> None:
        """
        Low confidence should keep monitor even if D-tier low composite.
        """
        # LLM returns D-tier with offer_resource (invalid combo), low confidence
        response = json.dumps({
            "scores": {
                "urgency": 0.0,
                "pain_point_intensity": 0.0,
                "commercial_relevance": 0.0,
                "solution_seeking": 0.0,
            },
            "confidence": 0.2,  # Below min_confidence
            "lead_tier": "D",
            "recommended_next_step": "offer_resource",
            "rationale": "Test.",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        })
        
        cfg = BrainConfig(api_key="test-key", min_confidence=0.35)
        client = FakeClient(content=response)
        brain = IntentBrain(cfg, client=client)
        
        card = brain.score("Test", {})
        
        # Low confidence forces monitor (not ignore)
        assert card["lead_tier"] == "D"
        assert card["recommended_next_step"] == "monitor"
        assert "Low confidence" in str(card["safety_notes"])
        
        errors = validate_lead_card(card)
        assert errors == []
