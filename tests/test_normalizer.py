"""
Tests for parsing/normalizer.py - LLM output normalization.
"""

import pytest

from siw_intent_brain.parsing.normalizer import (
    clamp_score,
    clamp_confidence,
    clean_string,
    clean_string_list,
    normalize_scores,
    normalize_extracted_signals,
    validate_lead_tier,
    validate_next_step,
    validate_parser_mode,
    normalize_llm_output,
    NormalizationFlags,
)
from siw_intent_brain.contracts import default_scores, default_extracted_signals


# =============================================================================
# Test clamp_score / clamp_confidence
# =============================================================================

class TestClampScore:
    """Tests for score clamping to [0, 1]."""
    
    def test_normal_value(self):
        """Normal float in range passes through."""
        assert clamp_score(0.5) == 0.5
        assert clamp_score(0.0) == 0.0
        assert clamp_score(1.0) == 1.0
    
    def test_clamp_high(self):
        """Values > 1 clamp to 1."""
        assert clamp_score(1.5) == 1.0
        assert clamp_score(100) == 1.0
        assert clamp_score(999.99) == 1.0
    
    def test_clamp_low(self):
        """Values < 0 clamp to 0."""
        assert clamp_score(-0.1) == 0.0
        assert clamp_score(-100) == 0.0
    
    def test_none_returns_zero(self):
        """None returns 0."""
        assert clamp_score(None) == 0.0
    
    def test_string_numeric(self):
        """Numeric strings convert and clamp."""
        assert clamp_score("0.7") == 0.7
        assert clamp_score("1.5") == 1.0
        assert clamp_score("-0.5") == 0.0
    
    def test_string_non_numeric(self):
        """Non-numeric strings return 0."""
        assert clamp_score("high") == 0.0
        assert clamp_score("") == 0.0
        assert clamp_score("abc") == 0.0
    
    def test_integer(self):
        """Integers convert and clamp."""
        assert clamp_score(0) == 0.0
        assert clamp_score(1) == 1.0
        assert clamp_score(5) == 1.0
    
    def test_infinity(self):
        """Infinity values clamp to bounds."""
        assert clamp_score(float("inf")) == 1.0
        assert clamp_score(float("-inf")) == 0.0
    
    def test_nan(self):
        """NaN returns 0."""
        assert clamp_score(float("nan")) == 0.0
    
    def test_boolean(self):
        """Booleans convert (True=1, False=0)."""
        assert clamp_score(True) == 1.0
        assert clamp_score(False) == 0.0


class TestClampConfidence:
    """Tests for confidence clamping (alias for clamp_score)."""
    
    def test_same_as_clamp_score(self):
        """clamp_confidence behaves same as clamp_score."""
        assert clamp_confidence(0.5) == 0.5
        assert clamp_confidence(1.5) == 1.0
        assert clamp_confidence(-0.5) == 0.0
        assert clamp_confidence(None) == 0.0


# =============================================================================
# Test clean_string
# =============================================================================

class TestCleanString:
    """Tests for string cleaning."""
    
    def test_normal_string(self):
        """Normal string passes through."""
        assert clean_string("hello", 100) == "hello"
    
    def test_strips_whitespace(self):
        """Whitespace is stripped."""
        assert clean_string("  hello  ", 100) == "hello"
        assert clean_string("\n\thello\n\t", 100) == "hello"
    
    def test_truncates_long(self):
        """Long strings are truncated."""
        assert clean_string("a" * 100, 10) == "a" * 10
    
    def test_none_returns_empty(self):
        """None returns empty string."""
        assert clean_string(None, 100) == ""
    
    def test_non_string_converts(self):
        """Non-strings are converted."""
        assert clean_string(123, 100) == "123"
        assert clean_string(3.14, 100) == "3.14"
        assert clean_string(True, 100) == "True"
    
    def test_exact_length(self):
        """String at exact max length not truncated."""
        assert clean_string("12345", 5) == "12345"


# =============================================================================
# Test clean_string_list
# =============================================================================

class TestCleanStringList:
    """Tests for list cleaning."""
    
    def test_normal_list(self):
        """Normal list passes through."""
        assert clean_string_list(["a", "b", "c"], 10) == ["a", "b", "c"]
    
    def test_filters_empty(self):
        """Empty strings are filtered."""
        assert clean_string_list(["a", "", "b", "  ", "c"], 10) == ["a", "b", "c"]
    
    def test_filters_none(self):
        """None items are filtered."""
        assert clean_string_list(["a", None, "b"], 10) == ["a", "b"]
    
    def test_truncates_to_max_items(self):
        """List truncates to max_items."""
        assert clean_string_list(["a", "b", "c", "d", "e"], 3) == ["a", "b", "c"]
    
    def test_not_a_list(self):
        """Non-list returns empty list."""
        assert clean_string_list("not a list", 10) == []
        assert clean_string_list(None, 10) == []
        assert clean_string_list(123, 10) == []
        assert clean_string_list({"a": 1}, 10) == []
    
    def test_converts_items(self):
        """Non-string items are converted."""
        assert clean_string_list([1, 2, 3], 10) == ["1", "2", "3"]
    
    def test_strips_items(self):
        """Items are stripped."""
        assert clean_string_list(["  a  ", "\nb\n"], 10) == ["a", "b"]
    
    def test_truncates_individual_items(self):
        """Individual items truncated to max_item_length."""
        long_item = "x" * 1000
        result = clean_string_list([long_item], 10, max_item_length=50)
        assert len(result[0]) == 50


# =============================================================================
# Test normalize_scores
# =============================================================================

class TestNormalizeScores:
    """Tests for scores normalization."""
    
    def test_valid_scores(self):
        """Valid scores pass through."""
        raw = {
            "urgency": 0.5,
            "pain_point_intensity": 0.7,
            "commercial_relevance": 0.3,
            "solution_seeking": 0.9,
        }
        scores = normalize_scores(raw)
        assert scores["urgency"] == 0.5
        assert scores["pain_point_intensity"] == 0.7
        assert scores["commercial_relevance"] == 0.3
        assert scores["solution_seeking"] == 0.9
    
    def test_clamps_out_of_range(self):
        """Out-of-range scores are clamped."""
        raw = {
            "urgency": 1.5,
            "pain_point_intensity": -0.5,
            "commercial_relevance": 2.0,
            "solution_seeking": -1.0,
        }
        scores = normalize_scores(raw)
        assert scores["urgency"] == 1.0
        assert scores["pain_point_intensity"] == 0.0
        assert scores["commercial_relevance"] == 1.0
        assert scores["solution_seeking"] == 0.0
    
    def test_missing_fields(self):
        """Missing fields default to 0."""
        raw = {"urgency": 0.5}
        scores = normalize_scores(raw)
        assert scores["urgency"] == 0.5
        assert scores["pain_point_intensity"] == 0.0
        assert scores["commercial_relevance"] == 0.0
        assert scores["solution_seeking"] == 0.0
    
    def test_not_a_dict(self):
        """Non-dict returns default scores."""
        assert normalize_scores("not a dict") == default_scores()
        assert normalize_scores(None) == default_scores()
        assert normalize_scores([1, 2, 3]) == default_scores()
    
    def test_string_values(self):
        """String values are converted and clamped."""
        raw = {"urgency": "0.8", "pain_point_intensity": "invalid"}
        scores = normalize_scores(raw)
        assert scores["urgency"] == 0.8
        assert scores["pain_point_intensity"] == 0.0


# =============================================================================
# Test normalize_extracted_signals
# =============================================================================

class TestNormalizeExtractedSignals:
    """Tests for extracted_signals normalization."""
    
    def test_valid_signals(self):
        """Valid signals pass through."""
        raw = {
            "problem_summary": "User needs help",
            "constraints": ["budget"],
            "budget_hints": ["$50/mo"],
            "tooling_stack": ["Python"],
            "keywords": ["automation"],
        }
        signals = normalize_extracted_signals(raw)
        assert signals["problem_summary"] == "User needs help"
        assert signals["constraints"] == ["budget"]
    
    def test_not_a_dict(self):
        """Non-dict returns default signals."""
        assert normalize_extracted_signals(None) == default_extracted_signals()
        assert normalize_extracted_signals("wrong") == default_extracted_signals()
    
    def test_truncates_summary(self):
        """Long summary is truncated."""
        raw = {"problem_summary": "x" * 300}
        signals = normalize_extracted_signals(raw, max_summary_length=100)
        assert len(signals["problem_summary"]) == 100
    
    def test_truncates_lists(self):
        """Lists are truncated to max_items."""
        raw = {"constraints": ["a"] * 100}
        signals = normalize_extracted_signals(raw, max_list_items=10)
        assert len(signals["constraints"]) == 10
    
    def test_cleans_lists(self):
        """Lists are cleaned (empties filtered)."""
        raw = {"keywords": ["a", "", "b", None, "  ", "c"]}
        signals = normalize_extracted_signals(raw)
        assert signals["keywords"] == ["a", "b", "c"]


# =============================================================================
# Test Enum Validation
# =============================================================================

class TestValidateLeadTier:
    """Tests for lead_tier validation."""
    
    def test_valid_tiers(self):
        """Valid tiers return normalized and valid."""
        for tier in ["S", "A", "B", "C", "D"]:
            value, valid = validate_lead_tier(tier)
            assert value == tier
            assert valid is True
    
    def test_lowercase_normalized(self):
        """Lowercase is uppercased."""
        value, valid = validate_lead_tier("a")
        assert value == "A"
        assert valid is True
    
    def test_invalid_tier(self):
        """Invalid tier returns empty and invalid."""
        value, valid = validate_lead_tier("X")
        assert value == ""
        assert valid is False
    
    def test_none(self):
        """None returns empty and invalid."""
        value, valid = validate_lead_tier(None)
        assert value == ""
        assert valid is False


class TestValidateNextStep:
    """Tests for recommended_next_step validation."""
    
    def test_valid_steps(self):
        """Valid steps return normalized and valid."""
        for step in ["ignore", "monitor", "draft_reply", "ask_question", "offer_resource"]:
            value, valid = validate_next_step(step)
            assert value == step
            assert valid is True
    
    def test_uppercase_normalized(self):
        """Uppercase is lowercased."""
        value, valid = validate_next_step("MONITOR")
        assert value == "monitor"
        assert valid is True
    
    def test_invalid_step(self):
        """Invalid step returns empty and invalid."""
        value, valid = validate_next_step("unknown")
        assert value == ""
        assert valid is False


class TestValidateParserMode:
    """Tests for parser_mode validation."""
    
    def test_valid_modes(self):
        """Valid modes return normalized and valid."""
        for mode in ["strict", "extracted", "fail_closed"]:
            value, valid = validate_parser_mode(mode)
            assert value == mode
            assert valid is True
    
    def test_invalid_mode(self):
        """Invalid mode returns empty and invalid."""
        value, valid = validate_parser_mode("unknown")
        assert value == ""
        assert valid is False


# =============================================================================
# Test normalize_llm_output
# =============================================================================

class TestNormalizeLlmOutput:
    """Tests for full LLM output normalization."""
    
    def test_valid_output(self):
        """Valid output normalizes correctly."""
        raw = {
            "scores": {
                "urgency": 0.8,
                "pain_point_intensity": 0.6,
                "commercial_relevance": 0.7,
                "solution_seeking": 0.9,
            },
            "confidence": 0.85,
            "lead_tier": "A",
            "recommended_next_step": "offer_resource",
            "rationale": "High intent lead.",
            "extracted_signals": {
                "problem_summary": "Needs tool",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": ["tool"],
            },
            "safety_notes": ["Be helpful"],
        }
        normalized, flags = normalize_llm_output(raw)
        
        assert normalized["scores"]["urgency"] == 0.8
        assert normalized["confidence"] == 0.85
        assert normalized["lead_tier"] == "A"
        assert normalized["recommended_next_step"] == "offer_resource"
        assert normalized["rationale"] == "High intent lead."
        assert flags.tier_valid is True
        assert flags.next_step_valid is True
    
    def test_clamps_scores(self):
        """Scores are clamped."""
        raw = {
            "scores": {"urgency": 1.5, "pain_point_intensity": -0.5},
            "confidence": 2.0,
        }
        normalized, flags = normalize_llm_output(raw)
        
        assert normalized["scores"]["urgency"] == 1.0
        assert normalized["scores"]["pain_point_intensity"] == 0.0
        assert normalized["confidence"] == 1.0
    
    def test_invalid_tier_flagged(self):
        """Invalid lead_tier sets flag."""
        raw = {"lead_tier": "X"}
        normalized, flags = normalize_llm_output(raw)
        
        assert normalized["lead_tier"] == ""
        assert flags.tier_valid is False
    
    def test_invalid_next_step_flagged(self):
        """Invalid next_step sets flag."""
        raw = {"recommended_next_step": "unknown"}
        normalized, flags = normalize_llm_output(raw)
        
        assert normalized["recommended_next_step"] == ""
        assert flags.next_step_valid is False
    
    def test_empty_rationale_default(self):
        """Empty rationale gets default message."""
        raw = {"rationale": ""}
        normalized, flags = normalize_llm_output(raw)
        assert normalized["rationale"] == "No rationale provided."
    
    def test_truncates_rationale(self):
        """Long rationale is truncated."""
        raw = {"rationale": "x" * 500}
        normalized, flags = normalize_llm_output(raw, max_rationale_chars=100)
        assert len(normalized["rationale"]) == 100
    
    def test_missing_fields_handled(self):
        """Missing fields get defaults."""
        raw = {}
        normalized, flags = normalize_llm_output(raw)
        
        assert normalized["scores"] == default_scores()
        assert normalized["confidence"] == 0.0
        assert normalized["lead_tier"] == ""
        assert normalized["recommended_next_step"] == ""
        assert normalized["rationale"] == "No rationale provided."
        assert normalized["extracted_signals"] == default_extracted_signals()
        assert normalized["safety_notes"] == []
        
        assert flags.scores_defaulted is True
        assert flags.signals_defaulted is True
        assert flags.tier_valid is False
        assert flags.next_step_valid is False

