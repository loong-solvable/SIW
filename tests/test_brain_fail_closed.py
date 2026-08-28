"""
Fail-closed tests for IntentBrain.

All tests use FakeClient/BadClient - NO real network requests.
Tests verify correct fail-closed behavior on errors.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from siw_intent_brain import (
    BrainConfig,
    IntentBrain,
    validate_lead_card,
    E_PARSE_JSON,
    E_UPSTREAM_HTTP,
    E_UPSTREAM_TIMEOUT,
    E_UPSTREAM_EMPTY_CONTENT,
)
from siw_intent_brain.errors import UpstreamError
from siw_intent_brain.llm.types import ChatRequest, ChatResponse


# =============================================================================
# Bad Clients - Various Failure Modes
# =============================================================================

class UpstreamErrorClient:
    """Client that raises UpstreamError."""
    
    def __init__(self, error_code: str = E_UPSTREAM_HTTP, message: str = "Server error"):
        self.error_code = error_code
        self.message = message
    
    def complete(self, req: ChatRequest) -> ChatResponse:
        raise UpstreamError(f"{self.error_code}: {self.message}")


class TimeoutErrorClient:
    """Client that simulates timeout."""
    
    def complete(self, req: ChatRequest) -> ChatResponse:
        raise UpstreamError(f"{E_UPSTREAM_TIMEOUT}: Connection timed out")


class EmptyContentClient:
    """Client that returns empty content."""
    
    def complete(self, req: ChatRequest) -> ChatResponse:
        raise UpstreamError(f"{E_UPSTREAM_EMPTY_CONTENT}: Empty response")


class BadJsonClient:
    """Client that returns invalid JSON."""
    
    def __init__(self, content: str = "not valid json {"):
        self.content = content
    
    def complete(self, req: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content=self.content,
            raw={},
            latency_ms=50,
            retries=0,
            status_code=200,
        )


class UnexpectedExceptionClient:
    """Client that raises unexpected exception."""
    
    def complete(self, req: ChatRequest) -> ChatResponse:
        raise RuntimeError("Something unexpected happened")


class ValidJsonClient:
    """Client that returns configurable valid JSON."""
    
    def __init__(self, obj: dict):
        self.obj = obj
    
    def complete(self, req: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content=json.dumps(self.obj),
            raw={},
            latency_ms=50,
            retries=0,
            status_code=200,
        )


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
# Test: Upstream Errors -> Fail-Closed
# =============================================================================

class TestUpstreamErrors:
    """Tests for upstream error handling."""

    def test_upstream_error_full_contract(self, config: BrainConfig) -> None:
        """UpstreamError returns complete fail-closed card with all required fields."""
        client = UpstreamErrorClient(E_UPSTREAM_HTTP, "Server error 500")
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        # Core fail-closed behavior
        assert card["ok"] is False
        assert card["lead_tier"] == "D"
        assert card["recommended_next_step"] == "monitor"
        
        # Meta fields must be present and correct
        meta = card["meta"]
        assert "error_code" in meta
        assert meta["error_code"] == E_UPSTREAM_HTTP
        assert meta["schema_version"] == "lead_card.v1"
        assert meta["provider"] == "openai_compatible"
        assert meta["model"] == config.model
        assert isinstance(meta["latency_ms"], int)
        assert meta["latency_ms"] >= 0
        
        # Must pass validation
        errors = validate_lead_card(card)
        assert errors == [], f"Validation failed: {errors}"

    def test_upstream_error_returns_ok_false(self, config: BrainConfig) -> None:
        """UpstreamError returns ok=false."""
        client = UpstreamErrorClient()
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["ok"] is False

    def test_upstream_error_tier_d(self, config: BrainConfig) -> None:
        """UpstreamError returns tier D."""
        client = UpstreamErrorClient()
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["lead_tier"] == "D"

    def test_upstream_error_monitor(self, config: BrainConfig) -> None:
        """UpstreamError returns next_step=monitor."""
        client = UpstreamErrorClient()
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["recommended_next_step"] == "monitor"

    def test_upstream_error_has_error_code(self, config: BrainConfig) -> None:
        """UpstreamError includes error_code in meta."""
        client = UpstreamErrorClient(E_UPSTREAM_HTTP)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert "error_code" in card["meta"]
        assert card["meta"]["error_code"] == E_UPSTREAM_HTTP

    def test_upstream_error_validates(self, config: BrainConfig) -> None:
        """UpstreamError fail-closed still validates."""
        client = UpstreamErrorClient()
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        errors = validate_lead_card(card)
        assert errors == [], f"Validation failed: {errors}"

    def test_timeout_error_full_contract(self, config: BrainConfig) -> None:
        """Timeout error has correct error code and full contract compliance."""
        client = TimeoutErrorClient()
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        # Core assertions
        assert card["ok"] is False
        assert card["lead_tier"] == "D"
        assert card["recommended_next_step"] == "monitor"
        assert card["meta"]["error_code"] == E_UPSTREAM_TIMEOUT
        assert card["meta"]["schema_version"] == "lead_card.v1"
        assert card["meta"]["provider"] == "openai_compatible"
        
        # Must pass validation
        errors = validate_lead_card(card)
        assert errors == [], f"Validation failed: {errors}"

    def test_empty_content_full_contract(self, config: BrainConfig) -> None:
        """Empty content error has correct error code and full contract compliance."""
        client = EmptyContentClient()
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        # Core assertions
        assert card["ok"] is False
        assert card["lead_tier"] == "D"
        assert card["recommended_next_step"] == "monitor"
        assert card["meta"]["error_code"] == E_UPSTREAM_EMPTY_CONTENT
        assert card["meta"]["schema_version"] == "lead_card.v1"
        assert card["meta"]["provider"] == "openai_compatible"
        
        # Must pass validation
        errors = validate_lead_card(card)
        assert errors == [], f"Validation failed: {errors}"


# =============================================================================
# Test: Bad JSON -> Fail-Closed
# =============================================================================

class TestBadJson:
    """Tests for invalid JSON handling."""

    def test_bad_json_full_contract(self, config: BrainConfig) -> None:
        """Invalid JSON returns complete fail-closed card with all required fields."""
        client = BadJsonClient("not valid json at all {{{")
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        # Core fail-closed behavior
        assert card["ok"] is False
        assert card["lead_tier"] == "D"
        assert card["recommended_next_step"] == "monitor"
        
        # Meta fields must be present and correct
        meta = card["meta"]
        assert meta["error_code"] == E_PARSE_JSON
        assert meta["parser_mode"] == "fail_closed"
        assert meta["schema_version"] == "lead_card.v1"
        assert meta["provider"] == "openai_compatible"
        
        # Must pass validation
        errors = validate_lead_card(card)
        assert errors == [], f"Validation failed: {errors}"

    def test_bad_json_returns_ok_false(self, config: BrainConfig) -> None:
        """Invalid JSON returns ok=false."""
        client = BadJsonClient("not json at all")
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["ok"] is False

    def test_bad_json_tier_d(self, config: BrainConfig) -> None:
        """Invalid JSON returns tier D."""
        client = BadJsonClient("{ broken json")
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["lead_tier"] == "D"

    def test_bad_json_next_step_monitor(self, config: BrainConfig) -> None:
        """Invalid JSON returns next_step=monitor."""
        client = BadJsonClient("{ broken json")
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["recommended_next_step"] == "monitor"

    def test_bad_json_parser_mode_fail_closed(self, config: BrainConfig) -> None:
        """Invalid JSON has parser_mode=fail_closed."""
        client = BadJsonClient("not json")
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["meta"]["parser_mode"] == "fail_closed"

    def test_bad_json_error_code(self, config: BrainConfig) -> None:
        """Invalid JSON has E_PARSE_JSON error code."""
        client = BadJsonClient("not json")
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["meta"]["error_code"] == E_PARSE_JSON

    def test_bad_json_validates(self, config: BrainConfig) -> None:
        """Invalid JSON fail-closed still validates."""
        client = BadJsonClient("not json")
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        errors = validate_lead_card(card)
        assert errors == []
    
    def test_broken_json_brace_validates(self, config: BrainConfig) -> None:
        """Broken JSON with brace returns fail-closed and validates."""
        client = BadJsonClient('{"key": broken')
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["ok"] is False
        assert card["lead_tier"] == "D"
        assert card["recommended_next_step"] == "monitor"
        assert card["meta"]["error_code"] == E_PARSE_JSON
        assert card["meta"]["parser_mode"] == "fail_closed"
        
        errors = validate_lead_card(card)
        assert errors == []


# =============================================================================
# Test: Missing/Invalid Fields -> Heuristic Fallback
# =============================================================================

class TestHeuristicFallback:
    """Tests for heuristic fallback with invalid LLM fields."""

    def test_missing_tier_uses_heuristic(self, config: BrainConfig) -> None:
        """Missing lead_tier triggers heuristic calculation."""
        obj = {
            "scores": {
                "urgency": 1.0,
                "pain_point_intensity": 1.0,
                "commercial_relevance": 1.0,
                "solution_seeking": 1.0,
            },
            "confidence": 1.0,
            # lead_tier missing!
            "recommended_next_step": "offer_resource",
            "rationale": "Test",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        }
        client = ValidJsonClient(obj)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["ok"] is True
        # With all 1.0 scores and conf=1.0, heuristic should return S
        assert card["lead_tier"] == "S"

    def test_invalid_tier_uses_heuristic(self, config: BrainConfig) -> None:
        """Invalid lead_tier (e.g., 'X') triggers heuristic."""
        obj = {
            "scores": {
                "urgency": 0.0,
                "pain_point_intensity": 0.0,
                "commercial_relevance": 0.0,
                "solution_seeking": 0.0,
            },
            "confidence": 0.5,
            "lead_tier": "X",  # Invalid!
            "recommended_next_step": "monitor",
            "rationale": "Test",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        }
        client = ValidJsonClient(obj)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["ok"] is True
        # With all 0.0 scores, heuristic should return D
        assert card["lead_tier"] == "D"

    def test_missing_next_step_uses_heuristic(self, config: BrainConfig) -> None:
        """Missing recommended_next_step triggers heuristic."""
        obj = {
            "scores": {
                "urgency": 0.5,
                "pain_point_intensity": 0.5,
                "commercial_relevance": 0.7,
                "solution_seeking": 0.6,
            },
            "confidence": 0.8,
            "lead_tier": "B",
            # recommended_next_step missing!
            "rationale": "Test",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        }
        client = ValidJsonClient(obj)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["ok"] is True
        # Should compute next_step from heuristic
        assert card["recommended_next_step"] in {
            "ignore", "monitor", "draft_reply", "ask_question", "offer_resource"
        }

    def test_invalid_next_step_uses_heuristic(self, config: BrainConfig) -> None:
        """Invalid next_step triggers heuristic."""
        obj = {
            "scores": {
                "urgency": 0.1,
                "pain_point_intensity": 0.1,
                "commercial_relevance": 0.1,
                "solution_seeking": 0.1,
            },
            "confidence": 0.9,
            "lead_tier": "D",
            "recommended_next_step": "invalid_step",  # Invalid!
            "rationale": "Test",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        }
        client = ValidJsonClient(obj)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["ok"] is True
        # With low composite (0.1), should be ignore
        assert card["recommended_next_step"] == "ignore"

    def test_heuristic_fallback_still_validates(self, config: BrainConfig) -> None:
        """Cards with heuristic fallback still validate."""
        obj = {
            "scores": {
                "urgency": 0.5,
                "pain_point_intensity": 0.5,
                "commercial_relevance": 0.5,
                "solution_seeking": 0.5,
            },
            "confidence": 0.8,
            "lead_tier": "INVALID",
            "recommended_next_step": "INVALID",
            "rationale": "Test",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        }
        client = ValidJsonClient(obj)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["ok"] is True
        errors = validate_lead_card(card)
        assert errors == []


# =============================================================================
# Test: Low Confidence -> Soft Fail-Closed
# =============================================================================

class TestLowConfidence:
    """Tests for soft fail-closed when confidence < min_confidence."""

    def test_low_confidence_full_contract(self, config: BrainConfig) -> None:
        """Low confidence triggers soft fail-closed with all required behavior."""
        obj = {
            "scores": {
                "urgency": 1.0,
                "pain_point_intensity": 1.0,
                "commercial_relevance": 1.0,
                "solution_seeking": 1.0,
            },
            "confidence": 0.2,  # Below min_confidence (0.35)
            "lead_tier": "S",
            "recommended_next_step": "offer_resource",
            "rationale": "High scores but low confidence",
            "extracted_signals": {
                "problem_summary": "test",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        }
        client = ValidJsonClient(obj)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        # Soft fail-closed: ok=true but conservative output
        assert card["ok"] is True
        assert card["lead_tier"] == "D"
        assert card["recommended_next_step"] == "monitor"
        
        # Must have low confidence safety note
        assert any("confidence" in note.lower() for note in card["safety_notes"])
        
        # Must pass validation
        errors = validate_lead_card(card)
        assert errors == [], f"Validation failed: {errors}"

    def test_low_confidence_tier_d(self, config: BrainConfig) -> None:
        """Low confidence forces tier D."""
        obj = {
            "scores": {
                "urgency": 1.0,
                "pain_point_intensity": 1.0,
                "commercial_relevance": 1.0,
                "solution_seeking": 1.0,
            },
            "confidence": 0.2,  # Below min_confidence (0.35)
            "lead_tier": "S",
            "recommended_next_step": "offer_resource",
            "rationale": "High scores but low confidence",
            "extracted_signals": {
                "problem_summary": "test",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        }
        client = ValidJsonClient(obj)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert card["ok"] is True  # Still ok=true (soft fail-closed)
        assert card["lead_tier"] == "D"  # Forced to D

    def test_low_confidence_forces_monitor(self, config: BrainConfig) -> None:
        """Low confidence forces next_step to monitor when original is not ignore/monitor."""
        obj = {
            "scores": {
                "urgency": 1.0,
                "pain_point_intensity": 1.0,
                "commercial_relevance": 1.0,
                "solution_seeking": 1.0,
            },
            "confidence": 0.1,  # Very low
            "lead_tier": "S",
            "recommended_next_step": "draft_reply",  # Should be changed to monitor
            "rationale": "Test",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        }
        client = ValidJsonClient(obj)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        # draft_reply is not allowed with low confidence, should be forced to monitor
        assert card["recommended_next_step"] == "monitor"
        
        # Must pass validation
        errors = validate_lead_card(card)
        assert errors == []

    def test_low_confidence_safety_note(self, config: BrainConfig) -> None:
        """Low confidence adds safety note with 'confidence' keyword."""
        obj = {
            "scores": {
                "urgency": 0.5,
                "pain_point_intensity": 0.5,
                "commercial_relevance": 0.5,
                "solution_seeking": 0.5,
            },
            "confidence": 0.2,
            "lead_tier": "B",
            "recommended_next_step": "draft_reply",
            "rationale": "Test",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        }
        client = ValidJsonClient(obj)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        # Should have low confidence warning
        assert any("confidence" in note.lower() for note in card["safety_notes"])
        # Check for specific message
        assert any("low confidence" in note.lower() for note in card["safety_notes"])
        
        # Must pass validation
        errors = validate_lead_card(card)
        assert errors == []

    def test_low_confidence_allows_ignore(self, config: BrainConfig) -> None:
        """Low confidence keeps next_step=ignore if already ignore."""
        obj = {
            "scores": {
                "urgency": 0.1,
                "pain_point_intensity": 0.1,
                "commercial_relevance": 0.1,
                "solution_seeking": 0.1,
            },
            "confidence": 0.1,
            "lead_tier": "D",
            "recommended_next_step": "ignore",  # Already acceptable
            "rationale": "Test",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        }
        client = ValidJsonClient(obj)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        # ignore is acceptable for low confidence (allowed to stay)
        assert card["recommended_next_step"] in ("ignore", "monitor")
        
        # Must pass validation
        errors = validate_lead_card(card)
        assert errors == []

    def test_low_confidence_validates(self, config: BrainConfig) -> None:
        """Low confidence soft fail-closed still validates."""
        obj = {
            "scores": {
                "urgency": 1.0,
                "pain_point_intensity": 1.0,
                "commercial_relevance": 1.0,
                "solution_seeking": 1.0,
            },
            "confidence": 0.1,
            "lead_tier": "S",
            "recommended_next_step": "offer_resource",
            "rationale": "Test",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        }
        client = ValidJsonClient(obj)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        errors = validate_lead_card(card)
        assert errors == []
    
    def test_low_confidence_with_ask_question_forces_monitor(self, config: BrainConfig) -> None:
        """Low confidence forces ask_question to monitor."""
        obj = {
            "scores": {
                "urgency": 0.8,
                "pain_point_intensity": 0.8,
                "commercial_relevance": 0.5,
                "solution_seeking": 0.7,
            },
            "confidence": 0.1,
            "lead_tier": "A",
            "recommended_next_step": "ask_question",  # Not allowed with low conf
            "rationale": "Test",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
        }
        client = ValidJsonClient(obj)
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        # ask_question should be forced to monitor
        assert card["recommended_next_step"] == "monitor"
        assert card["lead_tier"] == "D"
        assert any("confidence" in note.lower() for note in card["safety_notes"])
        
        errors = validate_lead_card(card)
        assert errors == []


# =============================================================================
# Test: Unexpected Exceptions -> Never Throw
# =============================================================================

class TestUnexpectedExceptions:
    """Tests that brain never throws uncaught exceptions."""

    def test_unexpected_exception_returns_card(self, config: BrainConfig) -> None:
        """Unexpected exception returns fail-closed card, not exception."""
        client = UnexpectedExceptionClient()
        brain = IntentBrain(config, client=client)
        
        # Should NOT raise
        card = brain.score("Test text")
        
        assert card["ok"] is False
        assert card["lead_tier"] == "D"
        assert card["recommended_next_step"] == "monitor"

    def test_unexpected_exception_validates(self, config: BrainConfig) -> None:
        """Unexpected exception fail-closed still validates."""
        client = UnexpectedExceptionClient()
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        errors = validate_lead_card(card)
        assert errors == []


# =============================================================================
# Test: Safety Notes Content
# =============================================================================

class TestSafetyNotes:
    """Tests for safety notes in fail-closed scenarios."""

    def test_fail_closed_has_safety_note(self, config: BrainConfig) -> None:
        """Fail-closed includes conservative output note."""
        client = UpstreamErrorClient()
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert len(card["safety_notes"]) > 0
        assert any("fail" in note.lower() or "conservative" in note.lower() 
                   for note in card["safety_notes"])

    def test_rationale_mentions_fail_closed(self, config: BrainConfig) -> None:
        """Fail-closed rationale mentions the failure."""
        client = BadJsonClient("not json")
        brain = IntentBrain(config, client=client)
        
        card = brain.score("Test text")
        
        assert "fail" in card["rationale"].lower() or "error" in card["rationale"].lower()
