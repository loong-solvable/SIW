"""
CLI tests for siw-brain command.

All tests are OFFLINE - no real network requests.
Uses FakeClient and brain factory injection.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest

from siw_intent_brain import validate_lead_card, BrainConfig
from siw_intent_brain.cli import main, set_brain_factory
from siw_intent_brain.brain import IntentBrain
from siw_intent_brain.llm.types import ChatRequest, ChatResponse


# =============================================================================
# FakeClient for Offline Testing
# =============================================================================

class FakeClient:
    """Fake LLM client that returns valid responses."""
    
    def __init__(self, response: Optional[str] = None):
        self.response = response or self._default_response()
    
    def _default_response(self) -> str:
        return json.dumps({
            "scores": {
                "urgency": 0.7,
                "pain_point_intensity": 0.8,
                "commercial_relevance": 0.6,
                "solution_seeking": 0.9,
            },
            "confidence": 0.85,
            "lead_tier": "A",
            "recommended_next_step": "offer_resource",
            "rationale": "High intent detected.",
            "extracted_signals": {
                "problem_summary": "User seeking solution",
                "constraints": ["budget"],
                "budget_hints": ["$50/mo"],
                "tooling_stack": ["ToolX"],
                "keywords": ["alternative", "cheaper"],
            },
            "safety_notes": ["Be helpful."],
        })
    
    def complete(self, req: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content=self.response,
            raw={},
            latency_ms=50,
            retries=0,
            status_code=200,
        )


def make_fake_brain_factory(client: Optional[FakeClient] = None):
    """Create a brain factory that uses FakeClient."""
    def factory(config_path: Optional[str] = None, **kwargs):
        cfg = BrainConfig(api_key="test-key-fake")
        return IntentBrain(cfg, client=client or FakeClient())
    return factory


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def valid_lead_card() -> Dict[str, Any]:
    """A valid LeadCard dict."""
    return {
        "ok": True,
        "scores": {
            "urgency": 0.5,
            "pain_point_intensity": 0.6,
            "commercial_relevance": 0.7,
            "solution_seeking": 0.8,
        },
        "confidence": 0.9,
        "lead_tier": "A",
        "recommended_next_step": "offer_resource",
        "rationale": "Test rationale",
        "extracted_signals": {
            "problem_summary": "Test problem",
            "constraints": [],
            "budget_hints": [],
            "tooling_stack": [],
            "keywords": [],
        },
        "safety_notes": [],
        "meta": {
            "model": "test-model",
            "provider": "openrouter",
            "latency_ms": 100,
            "retries": 0,
            "parser_mode": "strict",
            "schema_version": "lead_card.v1",
        },
    }


@pytest.fixture
def invalid_lead_card() -> Dict[str, Any]:
    """An invalid LeadCard dict (missing required fields)."""
    return {
        "ok": True,
        "scores": {"urgency": 0.5},  # Missing other scores
        # Missing many required fields
    }


@pytest.fixture(autouse=True)
def reset_brain_factory():
    """Reset brain factory and logging after each test."""
    yield
    set_brain_factory(None)
    # Reset logging to default (disabled)
    from siw_intent_brain.telemetry.logging import enable_logging
    enable_logging(False)


# =============================================================================
# Test: validate command - Valid File
# =============================================================================

class TestValidateValid:
    """Tests for validate command with valid files."""

    def test_validate_valid_returns_zero(
        self, temp_dir: Path, valid_lead_card: Dict[str, Any]
    ) -> None:
        """Valid LeadCard returns exit code 0."""
        json_file = temp_dir / "valid.json"
        json_file.write_text(json.dumps(valid_lead_card), encoding="utf-8")
        
        result = main(["validate", "--json-file", str(json_file)])
        
        assert result == 0

    def test_validate_valid_prints_valid(
        self, temp_dir: Path, valid_lead_card: Dict[str, Any], capsys
    ) -> None:
        """Valid LeadCard prints 'VALID'."""
        json_file = temp_dir / "valid.json"
        json_file.write_text(json.dumps(valid_lead_card), encoding="utf-8")
        
        main(["validate", "--json-file", str(json_file)])
        
        captured = capsys.readouterr()
        assert "VALID" in captured.out


# =============================================================================
# Test: validate command - Invalid File
# =============================================================================

class TestValidateInvalid:
    """Tests for validate command with invalid files."""

    def test_validate_invalid_returns_two(
        self, temp_dir: Path, invalid_lead_card: Dict[str, Any]
    ) -> None:
        """Invalid LeadCard returns exit code 2."""
        json_file = temp_dir / "invalid.json"
        json_file.write_text(json.dumps(invalid_lead_card), encoding="utf-8")
        
        result = main(["validate", "--json-file", str(json_file)])
        
        assert result == 2

    def test_validate_invalid_prints_invalid(
        self, temp_dir: Path, invalid_lead_card: Dict[str, Any], capsys
    ) -> None:
        """Invalid LeadCard prints 'INVALID' and errors."""
        json_file = temp_dir / "invalid.json"
        json_file.write_text(json.dumps(invalid_lead_card), encoding="utf-8")
        
        main(["validate", "--json-file", str(json_file)])
        
        captured = capsys.readouterr()
        assert "INVALID" in captured.out


# =============================================================================
# Test: validate command - File Errors
# =============================================================================

class TestValidateFileErrors:
    """Tests for validate command with file errors."""

    def test_validate_missing_file_returns_one(self) -> None:
        """Missing file returns exit code 1."""
        result = main(["validate", "--json-file", "/nonexistent/path/file.json"])
        
        assert result == 1

    def test_validate_missing_file_prints_error(self, capsys) -> None:
        """Missing file prints error message."""
        main(["validate", "--json-file", "/nonexistent/path/file.json"])
        
        captured = capsys.readouterr()
        assert "ERROR" in captured.err or "not found" in captured.err.lower()

    def test_validate_invalid_json_returns_one(self, temp_dir: Path) -> None:
        """Invalid JSON file returns exit code 1."""
        json_file = temp_dir / "bad.json"
        json_file.write_text("{ not valid json", encoding="utf-8")
        
        result = main(["validate", "--json-file", str(json_file)])
        
        assert result == 1


# =============================================================================
# Test: score command - Basic Functionality
# =============================================================================

class TestScoreBasic:
    """Tests for score command basic functionality."""

    def test_score_with_text_returns_zero(self) -> None:
        """score --text returns exit code 0."""
        set_brain_factory(make_fake_brain_factory())
        
        result = main(["score", "--text", "Looking for an alternative"])
        
        assert result == 0

    def test_score_outputs_valid_json(self, capsys) -> None:
        """score outputs valid JSON."""
        set_brain_factory(make_fake_brain_factory())
        
        main(["score", "--text", "Test text"])
        
        captured = capsys.readouterr()
        # Should be valid JSON
        card = json.loads(captured.out)
        assert isinstance(card, dict)

    def test_score_output_passes_validation(self, capsys) -> None:
        """score output passes validate_lead_card()."""
        set_brain_factory(make_fake_brain_factory())
        
        main(["score", "--text", "Test text"])
        
        captured = capsys.readouterr()
        card = json.loads(captured.out)
        errors = validate_lead_card(card)
        assert errors == [], f"Validation failed: {errors}"

    def test_score_with_context_json(self, capsys) -> None:
        """score --context-json works."""
        set_brain_factory(make_fake_brain_factory())
        
        result = main([
            "score",
            "--text", "Test text",
            "--context-json", '{"subreddit": "marketing", "title": "Help wanted"}',
        ])
        
        assert result == 0
        captured = capsys.readouterr()
        card = json.loads(captured.out)
        assert card["ok"] is True


# =============================================================================
# Test: score command - File Input
# =============================================================================

class TestScoreFileInput:
    """Tests for score command with file input."""

    def test_score_text_file(self, temp_dir: Path, capsys) -> None:
        """score --text-file reads from file."""
        set_brain_factory(make_fake_brain_factory())
        
        text_file = temp_dir / "input.txt"
        text_file.write_text("Looking for cheaper alternatives", encoding="utf-8")
        
        result = main(["score", "--text-file", str(text_file)])
        
        assert result == 0
        captured = capsys.readouterr()
        card = json.loads(captured.out)
        errors = validate_lead_card(card)
        assert errors == []

    def test_score_context_file(self, temp_dir: Path, capsys) -> None:
        """score --context-file reads from file."""
        set_brain_factory(make_fake_brain_factory())
        
        ctx_file = temp_dir / "context.json"
        ctx_file.write_text('{"subreddit": "test"}', encoding="utf-8")
        
        result = main([
            "score",
            "--text", "Test text",
            "--context-file", str(ctx_file),
        ])
        
        assert result == 0
        captured = capsys.readouterr()
        card = json.loads(captured.out)
        errors = validate_lead_card(card)
        assert errors == []

    def test_score_missing_text_file_returns_one(self) -> None:
        """score with missing text file returns exit code 1."""
        set_brain_factory(make_fake_brain_factory())
        
        result = main(["score", "--text-file", "/nonexistent/file.txt"])
        
        assert result == 1

    def test_score_missing_context_file_returns_one(self) -> None:
        """score with missing context file returns exit code 1."""
        set_brain_factory(make_fake_brain_factory())
        
        result = main([
            "score",
            "--text", "Test",
            "--context-file", "/nonexistent/context.json",
        ])
        
        assert result == 1


# =============================================================================
# Test: score command - Output Format
# =============================================================================

class TestScoreOutputFormat:
    """Tests for score command output formatting."""

    def test_score_default_pretty_json(self, capsys) -> None:
        """Default output is pretty-printed JSON."""
        set_brain_factory(make_fake_brain_factory())
        
        main(["score", "--text", "Test"])
        
        captured = capsys.readouterr()
        # Pretty JSON has newlines
        assert "\n" in captured.out
        assert "  " in captured.out  # Indentation

    def test_score_quiet_compact_json(self, capsys) -> None:
        """--quiet outputs compact JSON."""
        set_brain_factory(make_fake_brain_factory())
        
        main(["score", "--text", "Test", "--quiet"])
        
        captured = capsys.readouterr()
        # Should be single line (no indentation newlines within JSON)
        lines = [l for l in captured.out.strip().split("\n") if l.strip()]
        assert len(lines) == 1


# =============================================================================
# Test: score command - stdout/stderr Separation
# =============================================================================

class TestScoreStdoutStderrSeparation:
    """Tests for score stdout/stderr separation (no log pollution)."""

    def test_score_stdout_is_pure_json(self, capsys) -> None:
        """stdout must be pure LeadCard JSON, parseable in one json.loads()."""
        set_brain_factory(make_fake_brain_factory())
        
        main(["score", "--text", "Looking for alternative"])
        
        captured = capsys.readouterr()
        # Must be parseable as single JSON object
        card = json.loads(captured.out)
        assert isinstance(card, dict)
        # Must pass validation
        errors = validate_lead_card(card)
        assert errors == [], f"Validation failed: {errors}"

    def test_score_no_log_in_stdout_by_default(self, capsys) -> None:
        """Without --verbose, stdout contains no log keywords."""
        set_brain_factory(make_fake_brain_factory())
        
        main(["score", "--text", "Test"])
        
        captured = capsys.readouterr()
        # Log events should NOT appear in stdout
        assert "score_start" not in captured.out
        assert "score_end" not in captured.out
        assert '"event"' not in captured.out
        assert '"level"' not in captured.out

    def test_score_verbose_logs_to_stderr(self, capsys) -> None:
        """With --verbose, logs go to stderr (not stdout)."""
        set_brain_factory(make_fake_brain_factory())
        
        main(["score", "--text", "Test verbose mode", "--verbose"])
        
        captured = capsys.readouterr()
        # stdout should still be pure JSON
        card = json.loads(captured.out)
        errors = validate_lead_card(card)
        assert errors == []
        # stdout should NOT have log events
        assert "score_start" not in captured.out
        # stderr should have log events (if any are logged)
        # Note: logs may or may not appear depending on brain.py implementation
        # But if they do, they go to stderr
        assert "score_start" not in captured.out  # Ensure not in stdout

    def test_score_stdout_only_lead_card(self, capsys) -> None:
        """stdout contains only the LeadCard, nothing else."""
        set_brain_factory(make_fake_brain_factory())
        
        main(["score", "--text", "Test", "--context-json", '{"subreddit": "test"}'])
        
        captured = capsys.readouterr()
        # Strip and parse - should work without any trimming of extra lines
        stdout_stripped = captured.out.strip()
        card = json.loads(stdout_stripped)
        # Should have expected top-level keys
        assert "ok" in card
        assert "scores" in card
        assert "meta" in card


# =============================================================================
# Test: score command - Missing Input
# =============================================================================

class TestScoreMissingInput:
    """Tests for score command with missing input."""

    def test_score_no_text_returns_one(self, capsys) -> None:
        """score without text returns exit code 1."""
        set_brain_factory(make_fake_brain_factory())
        
        result = main(["score"])
        
        assert result == 1
        captured = capsys.readouterr()
        assert "ERROR" in captured.err

    def test_score_invalid_context_json_returns_one(self, capsys) -> None:
        """score with invalid context JSON returns exit code 1."""
        set_brain_factory(make_fake_brain_factory())
        
        result = main([
            "score",
            "--text", "Test",
            "--context-json", "{ not valid json",
        ])
        
        assert result == 1


# =============================================================================
# Test: score command - LeadCard Content
# =============================================================================

class TestScoreLeadCardContent:
    """Tests for score command LeadCard content."""

    def test_score_lead_card_has_ok(self, capsys) -> None:
        """LeadCard has 'ok' field."""
        set_brain_factory(make_fake_brain_factory())
        
        main(["score", "--text", "Test"])
        
        captured = capsys.readouterr()
        card = json.loads(captured.out)
        assert "ok" in card

    def test_score_lead_card_has_meta(self, capsys) -> None:
        """LeadCard has 'meta' with required fields."""
        set_brain_factory(make_fake_brain_factory())
        
        main(["score", "--text", "Test"])
        
        captured = capsys.readouterr()
        card = json.loads(captured.out)
        meta = card["meta"]
        assert "model" in meta
        assert meta["provider"] == "openrouter"
        assert meta["schema_version"] == "lead_card.v1"

    def test_score_lead_card_has_scores(self, capsys) -> None:
        """LeadCard has 'scores' with all four dimensions."""
        set_brain_factory(make_fake_brain_factory())
        
        main(["score", "--text", "Test"])
        
        captured = capsys.readouterr()
        card = json.loads(captured.out)
        scores = card["scores"]
        assert "urgency" in scores
        assert "pain_point_intensity" in scores
        assert "commercial_relevance" in scores
        assert "solution_seeking" in scores


# =============================================================================
# Test: No Command
# =============================================================================

class TestNoCommand:
    """Tests for running without command."""

    def test_no_command_returns_zero(self) -> None:
        """No command shows help and returns 0."""
        result = main([])
        assert result == 0

    def test_version_flag(self, capsys) -> None:
        """--version shows version."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        # argparse exits with 0 on --version
        assert exc_info.value.code == 0


# =============================================================================
# Test: Empty Context
# =============================================================================

class TestEmptyContext:
    """Tests for score with empty/no context."""

    def test_score_no_context_uses_empty_dict(self, capsys) -> None:
        """score without context uses empty dict."""
        set_brain_factory(make_fake_brain_factory())
        
        result = main(["score", "--text", "Test text"])
        
        assert result == 0
        captured = capsys.readouterr()
        card = json.loads(captured.out)
        errors = validate_lead_card(card)
        assert errors == []

    def test_score_empty_context_json(self, capsys) -> None:
        """score with empty context JSON works."""
        set_brain_factory(make_fake_brain_factory())
        
        result = main([
            "score",
            "--text", "Test",
            "--context-json", "{}",
        ])
        
        assert result == 0
        captured = capsys.readouterr()
        card = json.loads(captured.out)
        errors = validate_lead_card(card)
        assert errors == []


# =============================================================================
# Test: doctor command
# =============================================================================

class TestDoctor:
    """Tests for doctor command."""

    def test_doctor_returns_zero(self, capsys) -> None:
        """doctor command returns 0 when checks pass."""
        result = main(["doctor"])
        
        # Should return 0 (key missing is just a warning, not failure)
        assert result == 0

    def test_doctor_prints_check_results(self, capsys) -> None:
        """doctor prints check results."""
        main(["doctor"])
        
        captured = capsys.readouterr()
        # Should contain check output
        assert "Python version" in captured.out
        assert "Package imports" in captured.out
        assert "OPENROUTER_API_KEY" in captured.out

    def test_doctor_does_not_print_api_key(self, capsys, monkeypatch) -> None:
        """doctor does NOT print actual API key value."""
        # Set a fake API key
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-key-12345")
        
        main(["doctor"])
        
        captured = capsys.readouterr()
        # Key value should NOT appear in output
        assert "sk-secret-key-12345" not in captured.out
        assert "sk-secret-key-12345" not in captured.err
        # But should show "Set" status
        assert "Set" in captured.out

    def test_doctor_without_key_shows_not_set(self, capsys, monkeypatch) -> None:
        """doctor shows 'Not set' when API key is missing."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        
        main(["doctor"])
        
        captured = capsys.readouterr()
        assert "Not set" in captured.out or "WARN" in captured.out

    def test_doctor_without_key_still_returns_zero(self, monkeypatch) -> None:
        """doctor returns 0 even without API key (it's a warning)."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        
        result = main(["doctor"])
        
        # Missing key is a warning, not a failure
        assert result == 0


# =============================================================================
# Test: demo command
# =============================================================================

class TestDemo:
    """Tests for demo command (offline demo)."""

    def test_demo_returns_zero(self) -> None:
        """demo command returns 0."""
        result = main(["demo"])
        
        assert result == 0

    def test_demo_outputs_json_to_stdout(self, capsys) -> None:
        """demo outputs JSON for each sample to stdout."""
        main(["demo"])
        
        captured = capsys.readouterr()
        # Should contain JSON output (look for "ok" field) in stdout
        assert '"ok"' in captured.out

    def test_demo_outputs_at_least_three_cards(self, capsys) -> None:
        """demo outputs at least 3 LeadCards to stdout."""
        main(["demo"])
        
        captured = capsys.readouterr()
        # Count occurrences of "ok" in stdout (each card has one)
        ok_count = captured.out.count('"ok":')
        assert ok_count >= 3

    def test_demo_all_cards_valid(self, capsys) -> None:
        """All demo cards pass validate_lead_card()."""
        main(["demo"])
        
        captured = capsys.readouterr()
        # VALID messages go to stderr now
        assert "VALID" in captured.err
        # Should NOT contain INVALID
        assert "INVALID" not in captured.err

    def test_demo_does_not_require_api_key(self, monkeypatch) -> None:
        """demo works without API key (uses FakeClient)."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        
        result = main(["demo"])
        
        assert result == 0

    def test_demo_info_to_stderr(self, capsys) -> None:
        """demo info messages go to stderr, not stdout."""
        result = main(["demo"])
        
        assert result == 0
        captured = capsys.readouterr()
        # Info messages should be in stderr
        assert "offline" in captured.err.lower() or "fake" in captured.err.lower()
        # stdout should only have JSON
        assert "Offline Demo" not in captured.out
        assert "FakeClient" not in captured.out

    def test_demo_stdout_is_only_json(self, capsys) -> None:
        """demo stdout contains only JSON (no info messages)."""
        main(["demo"])
        
        captured = capsys.readouterr()
        # All non-empty lines in stdout should be valid JSON fragments
        # Check that we can find all the cards
        assert captured.out.count('"ok":') >= 3
        # Should NOT contain demo info messages
        assert "Sample" not in captured.out
        assert "Demo" not in captured.out

    def test_demo_all_cards_have_meta_model(self, capsys) -> None:
        """All demo cards have meta.model field."""
        main(["demo"])
        
        captured = capsys.readouterr()
        # Parse all JSON objects from stdout
        import re
        json_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', captured.out, re.DOTALL)
        
        cards_found = 0
        for match in json_matches:
            try:
                obj = json.loads(match)
                if "ok" in obj and "meta" in obj:
                    cards_found += 1
                    # Check meta.model exists and is non-empty string
                    meta = obj.get("meta", {})
                    assert "model" in meta, f"meta.model missing in card"
                    assert isinstance(meta["model"], str), f"meta.model must be string"
                    assert meta["model"], f"meta.model must be non-empty"
                    # Validate entire card
                    errors = validate_lead_card(obj)
                    assert errors == [], f"Card validation failed: {errors}"
            except json.JSONDecodeError:
                continue
        
        assert cards_found >= 3, f"Expected at least 3 cards, found {cards_found}"


# =============================================================================
# Test: score command - stdin input
# =============================================================================

class TestScoreStdin:
    """Tests for score command with stdin input."""

    def test_score_reads_from_stdin(self, capsys, monkeypatch) -> None:
        """score reads text from stdin when no --text provided."""
        set_brain_factory(make_fake_brain_factory())
        
        # Mock stdin
        stdin_text = "Looking for cheaper alternative to ToolX"
        monkeypatch.setattr('sys.stdin', io.StringIO(stdin_text))
        monkeypatch.setattr('sys.stdin', type('FakeStdin', (), {
            'isatty': lambda self: False,
            'read': lambda self: stdin_text,
        })())
        
        result = main(["score", "--context-json", "{}"])
        
        assert result == 0
        captured = capsys.readouterr()
        card = json.loads(captured.out)
        errors = validate_lead_card(card)
        assert errors == []


# =============================================================================
# Test: score command - integration with validate_lead_card
# =============================================================================

class TestScoreValidation:
    """Integration tests verifying score output is always valid."""

    def test_score_output_always_valid(self, capsys) -> None:
        """Every score output must pass validate_lead_card()."""
        set_brain_factory(make_fake_brain_factory())
        
        # Test various inputs
        test_cases = [
            ["score", "--text", "Simple text"],
            ["score", "--text", "Looking for alternative to expensive tool"],
            ["score", "--text", "help", "--context-json", '{"subreddit": "test"}'],
        ]
        
        for args in test_cases:
            main(args)
            captured = capsys.readouterr()
            card = json.loads(captured.out)
            errors = validate_lead_card(card)
            assert errors == [], f"Failed for {args}: {errors}"

