"""
Tests for contracts.py - Lead Card contract definitions and validation.
"""

import json
from pathlib import Path

import pytest

from siw_intent_brain.contracts import (
    LEAD_TIERS,
    NEXT_STEPS,
    PARSER_MODES,
    SCHEMA_VERSION,
    build_lead_card,
    default_extracted_signals,
    default_scores,
    validate_lead_card,
)


# =============================================================================
# Test Default Builders
# =============================================================================

class TestDefaultScores:
    def test_returns_dict(self):
        scores = default_scores()
        assert isinstance(scores, dict)
    
    def test_all_fields_present(self):
        scores = default_scores()
        assert "urgency" in scores
        assert "pain_point_intensity" in scores
        assert "commercial_relevance" in scores
        assert "solution_seeking" in scores
    
    def test_all_fields_zero(self):
        scores = default_scores()
        for key, val in scores.items():
            assert val == 0.0, f"{key} should be 0.0"


class TestDefaultExtractedSignals:
    def test_returns_dict(self):
        signals = default_extracted_signals()
        assert isinstance(signals, dict)
    
    def test_all_fields_present(self):
        signals = default_extracted_signals()
        assert "problem_summary" in signals
        assert "constraints" in signals
        assert "budget_hints" in signals
        assert "tooling_stack" in signals
        assert "keywords" in signals
    
    def test_all_fields_empty(self):
        signals = default_extracted_signals()
        assert signals["problem_summary"] == ""
        assert signals["constraints"] == []
        assert signals["budget_hints"] == []
        assert signals["tooling_stack"] == []
        assert signals["keywords"] == []


class TestBuildLeadCard:
    def test_basic_construction(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.5,
            lead_tier="C",
            recommended_next_step="monitor",
            rationale="Test rationale.",
            extracted_signals=default_extracted_signals(),
            safety_notes=["Be polite."],
            meta={"model": "test-model", "parser_mode": "strict"},
        )
        assert card["ok"] is True
        assert card["confidence"] == 0.5
        assert card["lead_tier"] == "C"
        assert card["recommended_next_step"] == "monitor"
    
    def test_meta_defaults_applied(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta=None,
        )
        meta = card["meta"]
        assert meta["provider"] == "openai_compatible"
        assert meta["schema_version"] == "lead_card.v1"
        assert meta["latency_ms"] == 0
        assert meta["retries"] == 0
        assert meta["parser_mode"] == "strict"
        assert meta["model"] == ""  # Default empty
    
    def test_meta_override_not_clobbered(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.8,
            lead_tier="A",
            recommended_next_step="offer_resource",
            rationale="Good lead.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "gpt-4o", "latency_ms": 500, "retries": 2},
        )
        meta = card["meta"]
        assert meta["model"] == "gpt-4o"
        assert meta["latency_ms"] == 500
        assert meta["retries"] == 2
        # Defaults still applied for missing
        assert meta["provider"] == "openai_compatible"
        assert meta["schema_version"] == "lead_card.v1"


# =============================================================================
# Test Validation - Valid Cases
# =============================================================================

class TestValidateLeadCardValid:
    def test_default_card_is_valid(self):
        """A card built with defaults should pass validation."""
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Default card.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "test-model", "parser_mode": "strict"},
        )
        errors = validate_lead_card(card)
        assert errors == [], f"Expected no errors, got: {errors}"
    
    def test_full_valid_card(self):
        """A fully populated valid card should pass."""
        card = {
            "ok": True,
            "scores": {
                "urgency": 0.8,
                "pain_point_intensity": 0.6,
                "commercial_relevance": 0.7,
                "solution_seeking": 0.9,
            },
            "confidence": 0.85,
            "lead_tier": "S",
            "recommended_next_step": "offer_resource",
            "rationale": "High-intent lead with budget signals.",
            "extracted_signals": {
                "problem_summary": "User needs tool replacement",
                "constraints": ["budget under $50/mo"],
                "budget_hints": ["$50/mo", "cheap"],
                "tooling_stack": ["Python", "AWS"],
                "keywords": ["automation", "monitoring"],
            },
            "safety_notes": ["Be helpful", "Avoid spam"],
            "meta": {
                "model": "openai/gpt-4o-mini",
                "provider": "openrouter",
                "latency_ms": 450,
                "retries": 0,
                "parser_mode": "strict",
                "schema_version": "lead_card.v1",
            },
        }
        errors = validate_lead_card(card)
        assert errors == [], f"Expected no errors, got: {errors}"
    
    def test_fail_closed_card_valid(self):
        """A fail-closed card (ok=false) with error fields should pass."""
        card = build_lead_card(
            ok=False,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Fail-closed: upstream error.",
            extracted_signals=default_extracted_signals(),
            safety_notes=["Fail-closed: conservative output."],
            meta={
                "model": "openai/gpt-4o-mini",
                "parser_mode": "fail_closed",
                "error_code": "E_UPSTREAM_HTTP",
                "error_detail": "HTTP 500",
            },
        )
        errors = validate_lead_card(card)
        assert errors == [], f"Expected no errors, got: {errors}"
    
    def test_all_tiers_valid(self):
        """All lead_tier enum values should be valid."""
        for tier in LEAD_TIERS:
            card = build_lead_card(
                ok=True,
                scores=default_scores(),
                confidence=0.5,
                lead_tier=tier,  # type: ignore
                recommended_next_step="monitor",
                rationale="Tier test.",
                extracted_signals=default_extracted_signals(),
                safety_notes=[],
                meta={"model": "m", "parser_mode": "strict"},
            )
            errors = validate_lead_card(card)
            assert errors == [], f"Tier {tier} should be valid, got: {errors}"
    
    def test_all_next_steps_valid(self):
        """All recommended_next_step enum values should be valid."""
        for step in NEXT_STEPS:
            card = build_lead_card(
                ok=True,
                scores=default_scores(),
                confidence=0.5,
                lead_tier="C",
                recommended_next_step=step,  # type: ignore
                rationale="Step test.",
                extracted_signals=default_extracted_signals(),
                safety_notes=[],
                meta={"model": "m", "parser_mode": "strict"},
            )
            errors = validate_lead_card(card)
            assert errors == [], f"Step {step} should be valid, got: {errors}"
    
    def test_all_parser_modes_valid(self):
        """All parser_mode enum values should be valid."""
        for mode in PARSER_MODES:
            card = build_lead_card(
                ok=True,
                scores=default_scores(),
                confidence=0.5,
                lead_tier="C",
                recommended_next_step="monitor",
                rationale="Mode test.",
                extracted_signals=default_extracted_signals(),
                safety_notes=[],
                meta={"model": "m", "parser_mode": mode},  # type: ignore
            )
            errors = validate_lead_card(card)
            assert errors == [], f"Mode {mode} should be valid, got: {errors}"


# =============================================================================
# Test Validation - Invalid Cases
# =============================================================================

class TestValidateLeadCardInvalid:
    def test_not_a_dict(self):
        errors = validate_lead_card("not a dict")  # type: ignore
        assert len(errors) == 1
        assert "Root must be an object" in errors[0]
    
    def test_missing_required_keys(self):
        errors = validate_lead_card({})
        assert len(errors) == 9  # All 9 required keys missing
        assert any("Missing required key" in e for e in errors)
    
    def test_ok_wrong_type(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["ok"] = "yes"  # type: ignore
        errors = validate_lead_card(card)
        assert any("'ok' must be a boolean" in e for e in errors)
    
    def test_scores_wrong_type(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["scores"] = "not an object"  # type: ignore
        errors = validate_lead_card(card)
        assert any("'scores' must be an object" in e for e in errors)
    
    def test_scores_out_of_range_high(self):
        card = build_lead_card(
            ok=True,
            scores={"urgency": 1.5, "pain_point_intensity": 0.5, "commercial_relevance": 0.5, "solution_seeking": 0.5},  # type: ignore
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        errors = validate_lead_card(card)
        assert any("scores.urgency must be in [0, 1]" in e for e in errors)
    
    def test_scores_out_of_range_low(self):
        card = build_lead_card(
            ok=True,
            scores={"urgency": -0.1, "pain_point_intensity": 0.5, "commercial_relevance": 0.5, "solution_seeking": 0.5},  # type: ignore
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        errors = validate_lead_card(card)
        assert any("scores.urgency must be in [0, 1]" in e for e in errors)
    
    def test_confidence_out_of_range(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["confidence"] = 2.0
        errors = validate_lead_card(card)
        assert any("'confidence' must be in [0, 1]" in e for e in errors)
    
    def test_invalid_lead_tier(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["lead_tier"] = "Z"  # Invalid
        errors = validate_lead_card(card)
        assert any("'lead_tier' must be one of" in e for e in errors)
    
    def test_invalid_next_step(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["recommended_next_step"] = "unknown"  # Invalid
        errors = validate_lead_card(card)
        assert any("'recommended_next_step' must be one of" in e for e in errors)
    
    def test_rationale_too_long(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="x" * 401,  # Exceeds 400
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        errors = validate_lead_card(card)
        assert any("'rationale' exceeds maxLength 400" in e for e in errors)
    
    def test_extracted_signals_wrong_type(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["extracted_signals"] = "wrong"  # type: ignore
        errors = validate_lead_card(card)
        assert any("'extracted_signals' must be an object" in e for e in errors)
    
    def test_extracted_signals_list_exceeds_max(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals={
                "problem_summary": "",
                "constraints": ["x"] * 51,  # Exceeds 50
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        errors = validate_lead_card(card)
        assert any("extracted_signals.constraints exceeds maxItems 50" in e for e in errors)
    
    def test_safety_notes_exceeds_max(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=["x"] * 51,  # Exceeds 50
            meta={"model": "m", "parser_mode": "strict"},
        )
        errors = validate_lead_card(card)
        assert any("'safety_notes' exceeds maxItems 50" in e for e in errors)
    
    def test_meta_missing_required(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        del card["meta"]["provider"]  # type: ignore
        errors = validate_lead_card(card)
        assert any("meta.provider is missing" in e for e in errors)
    
    def test_meta_wrong_provider(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["meta"]["provider"] = "other"
        errors = validate_lead_card(card)
        assert any("meta.provider must be a supported provider" in e for e in errors)

    def test_meta_accepts_provider_neutral_value(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={
                "model": "m",
                "provider": "openai_compatible",
                "parser_mode": "strict",
            },
        )

        assert validate_lead_card(card) == []

    def test_json_schema_accepts_current_and_legacy_provider_names(self):
        schema_path = Path(__file__).parents[1] / "schemas" / "lead_card.v1.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        provider_schema = schema["properties"]["meta"]["properties"]["provider"]

        assert provider_schema["enum"] == [
            "openai_compatible",
            "cc_switch",
            "openrouter",
        ]
    
    def test_meta_wrong_schema_version(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["meta"]["schema_version"] = "v2"
        errors = validate_lead_card(card)
        assert any("meta.schema_version must be 'lead_card.v1'" in e for e in errors)
    
    def test_meta_invalid_parser_mode(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["meta"]["parser_mode"] = "invalid"
        errors = validate_lead_card(card)
        assert any("meta.parser_mode must be one of" in e for e in errors)
    
    def test_meta_latency_negative(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict", "latency_ms": -10},
        )
        errors = validate_lead_card(card)
        assert any("meta.latency_ms must be >= 0" in e for e in errors)


# =============================================================================
# Test additionalProperties: false enforcement
# =============================================================================

class TestValidateAdditionalProperties:
    """Test that unexpected keys are rejected (additionalProperties: false)."""
    
    def test_unexpected_top_level_key(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.5,
            lead_tier="C",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["extra_field"] = "unexpected"  # type: ignore
        errors = validate_lead_card(card)
        assert any("Unexpected top-level keys" in e for e in errors)
        assert any("extra_field" in e for e in errors)
    
    def test_unexpected_scores_key(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.5,
            lead_tier="C",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["scores"]["bonus_score"] = 0.5  # type: ignore
        errors = validate_lead_card(card)
        assert any("Unexpected keys in scores" in e for e in errors)
        assert any("bonus_score" in e for e in errors)
    
    def test_unexpected_meta_key(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.5,
            lead_tier="C",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["meta"]["usage"] = {"tokens": 100}  # type: ignore
        errors = validate_lead_card(card)
        assert any("Unexpected keys in meta" in e for e in errors)
        assert any("usage" in e for e in errors)
    
    def test_unexpected_signals_key(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.5,
            lead_tier="C",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["extracted_signals"]["custom_tags"] = ["tag1"]  # type: ignore
        errors = validate_lead_card(card)
        assert any("Unexpected keys in extracted_signals" in e for e in errors)
        assert any("custom_tags" in e for e in errors)
    
    def test_multiple_unexpected_keys_sorted(self):
        """Unexpected keys should be reported in sorted order for stable output."""
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.5,
            lead_tier="C",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["zebra"] = 1  # type: ignore
        card["alpha"] = 2  # type: ignore
        errors = validate_lead_card(card)
        # Find the error about unexpected keys
        unexpected_err = [e for e in errors if "Unexpected top-level keys" in e][0]
        # Should be sorted: ['alpha', 'zebra']
        assert "['alpha', 'zebra']" in unexpected_err


# =============================================================================
# Test sorted enum output in error messages
# =============================================================================

class TestSortedEnumErrors:
    """Test that enum errors output sorted lists for stable messages."""
    
    def test_lead_tier_error_sorted(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.5,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["lead_tier"] = "X"
        errors = validate_lead_card(card)
        tier_err = [e for e in errors if "'lead_tier'" in e][0]
        # Should be sorted: ['A', 'B', 'C', 'D', 'S']
        assert "['A', 'B', 'C', 'D', 'S']" in tier_err
    
    def test_next_step_error_sorted(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.5,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["recommended_next_step"] = "bad"
        errors = validate_lead_card(card)
        step_err = [e for e in errors if "'recommended_next_step'" in e][0]
        # Should be sorted: ['ask_question', 'draft_reply', 'ignore', 'monitor', 'offer_resource']
        assert "['ask_question', 'draft_reply', 'ignore', 'monitor', 'offer_resource']" in step_err
    
    def test_parser_mode_error_sorted(self):
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.5,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "m", "parser_mode": "strict"},
        )
        card["meta"]["parser_mode"] = "bad"
        errors = validate_lead_card(card)
        mode_err = [e for e in errors if "parser_mode" in e][0]
        # Should be sorted: ['extracted', 'fail_closed', 'strict']
        assert "['extracted', 'fail_closed', 'strict']" in mode_err


# =============================================================================
# Test Constants
# =============================================================================

class TestConstants:
    def test_schema_version(self):
        assert SCHEMA_VERSION == "lead_card.v1"
    
    def test_lead_tiers_complete(self):
        assert LEAD_TIERS == {"S", "A", "B", "C", "D"}
    
    def test_next_steps_complete(self):
        assert NEXT_STEPS == {"ignore", "monitor", "draft_reply", "ask_question", "offer_resource"}
    
    def test_parser_modes_complete(self):
        assert PARSER_MODES == {"strict", "extracted", "fail_closed"}


# =============================================================================
# Test CLI Validate Command
# =============================================================================

import json
import tempfile
import os

from siw_intent_brain.cli import main as cli_main


class TestCLIValidate:
    def test_validate_valid_file(self):
        """CLI validate should return 0 for valid lead card."""
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.5,
            lead_tier="C",
            recommended_next_step="monitor",
            rationale="Test.",
            extracted_signals=default_extracted_signals(),
            safety_notes=[],
            meta={"model": "test", "parser_mode": "strict"},
        )
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(card, f)
            temp_path = f.name
        
        try:
            result = cli_main(["validate", "--json-file", temp_path])
            assert result == 0
        finally:
            os.unlink(temp_path)
    
    def test_validate_invalid_file(self):
        """CLI validate should return 2 for invalid lead card."""
        invalid_card = {"ok": "not a bool"}  # Invalid
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(invalid_card, f)
            temp_path = f.name
        
        try:
            result = cli_main(["validate", "--json-file", temp_path])
            assert result == 2
        finally:
            os.unlink(temp_path)
    
    def test_validate_missing_file(self):
        """CLI validate should return 1 for missing file."""
        result = cli_main(["validate", "--json-file", "/nonexistent/path/file.json"])
        assert result == 1
    
    def test_validate_invalid_json(self):
        """CLI validate should return 1 for malformed JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("not valid json {{{")
            temp_path = f.name
        
        try:
            result = cli_main(["validate", "--json-file", temp_path])
            assert result == 1
        finally:
            os.unlink(temp_path)
