"""
Tests for the report module.

Tests:
  - reader: JSONL parsing, encoding handling, validation
  - curator: sorting, selection, statistics
  - render_pdf: PDF generation

All tests are offline (no network required).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import pytest


# =============================================================================
# Fixtures
# =============================================================================

def _make_valid_lead_card(
    *,
    ok: bool = True,
    tier: str = "B",
    confidence: float = 0.8,
    next_step: str = "ask_question",
    urgency: float = 0.3,
    pain_point_intensity: float = 0.5,
    commercial_relevance: float = 0.6,
    solution_seeking: float = 0.7,
    problem_summary: str = "Test problem",
    rationale: str = "Test rationale",
    keywords: list = None,
    budget_hints: list = None,
) -> Dict[str, Any]:
    """Create a valid LeadCard dict."""
    return {
        "ok": ok,
        "scores": {
            "urgency": urgency,
            "pain_point_intensity": pain_point_intensity,
            "commercial_relevance": commercial_relevance,
            "solution_seeking": solution_seeking,
        },
        "confidence": confidence,
        "lead_tier": tier,
        "recommended_next_step": next_step,
        "rationale": rationale,
        "extracted_signals": {
            "problem_summary": problem_summary,
            "constraints": [],
            "budget_hints": budget_hints or [],
            "tooling_stack": [],
            "keywords": keywords or ["test", "keyword"],
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


# =============================================================================
# Reader Tests
# =============================================================================

class TestReader:
    """Tests for reader.py."""
    
    def test_read_valid_jsonl(self, tmp_path: Path):
        """Test reading a valid JSONL file."""
        from siw_intent_brain.report.reader import read_candidates_jsonl
        
        # Create test file
        cards = [
            _make_valid_lead_card(tier="S", confidence=0.95),
            _make_valid_lead_card(tier="A", confidence=0.85),
            _make_valid_lead_card(tier="B", confidence=0.75),
        ]
        
        jsonl_path = tmp_path / "test.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for card in cards:
                f.write(json.dumps(card) + "\n")
        
        # Read
        records, invalid_lines = read_candidates_jsonl(jsonl_path)
        
        assert len(records) == 3
        assert len(invalid_lines) == 0
        assert records[0]["lead_tier"] == "S"
    
    def test_read_utf16_file(self, tmp_path: Path):
        """Test reading UTF-16 encoded file (Windows PowerShell default)."""
        from siw_intent_brain.report.reader import read_candidates_jsonl
        
        cards = [_make_valid_lead_card()]
        
        jsonl_path = tmp_path / "test_utf16.jsonl"
        content = "\n".join(json.dumps(c) for c in cards)
        jsonl_path.write_text(content, encoding="utf-16")
        
        records, invalid_lines = read_candidates_jsonl(jsonl_path)
        
        assert len(records) == 1
        assert len(invalid_lines) == 0
    
    def test_read_with_invalid_lines(self, tmp_path: Path):
        """Test that invalid JSON lines are collected, not raised."""
        from siw_intent_brain.report.reader import read_candidates_jsonl
        
        jsonl_path = tmp_path / "mixed.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            # Valid line
            f.write(json.dumps(_make_valid_lead_card()) + "\n")
            # Invalid JSON
            f.write("this is not json\n")
            # Empty line (should be skipped)
            f.write("\n")
            # Another valid line
            f.write(json.dumps(_make_valid_lead_card()) + "\n")
        
        records, invalid_lines = read_candidates_jsonl(jsonl_path)
        
        assert len(records) == 2
        assert len(invalid_lines) == 1
        assert invalid_lines[0]["line_number"] == 2
        assert "JSON parse error" in invalid_lines[0]["reason"]
    
    def test_read_harvest_wrapper_format(self, tmp_path: Path):
        """Test reading harvest output format with 'card' wrapper."""
        from siw_intent_brain.report.reader import read_candidates_jsonl
        
        card = _make_valid_lead_card()
        wrapper = {
            "card": card,
            "source_meta": {"subreddit": "SaaS", "author": "test"},
        }
        
        jsonl_path = tmp_path / "harvest.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(wrapper) + "\n")
        
        records, invalid_lines = read_candidates_jsonl(jsonl_path)
        
        assert len(records) == 1
        assert len(invalid_lines) == 0
        assert records[0]["lead_tier"] == "B"
    
    def test_read_invalid_schema(self, tmp_path: Path):
        """Test that schema-invalid records are collected as invalid."""
        from siw_intent_brain.report.reader import read_candidates_jsonl
        
        # Missing required field
        invalid_card = {"ok": True}  # Missing scores, etc.
        
        jsonl_path = tmp_path / "invalid_schema.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(invalid_card) + "\n")
        
        records, invalid_lines = read_candidates_jsonl(jsonl_path)
        
        assert len(records) == 0
        assert len(invalid_lines) == 1
        assert "schema invalid" in invalid_lines[0]["reason"]
    
    def test_read_harvest_format_with_source_info(self, tmp_path: Path):
        """Test that harvest output with source_meta and source_context is properly extracted."""
        from siw_intent_brain.report.reader import read_candidates_jsonl
        
        card = _make_valid_lead_card(tier="S", confidence=0.95)
        # Full harvest output format (as produced by CLI harvest command)
        wrapper = {
            "card": card,
            "source_meta": {
                "created_utc": 1703980800,
                "score": 42,
                "num_comments": 15,
                "id": "abc123",
                "url": "https://reddit.com/r/SaaS/comments/abc123/",
            },
            "source_context": {
                "subreddit": "SaaS",
                "author": "business_user",
                "permalink": "/r/SaaS/comments/abc123/looking_for_crm/",
                "title": "Looking for CRM alternative",
            },
        }
        
        jsonl_path = tmp_path / "harvest_full.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(wrapper) + "\n")
        
        records, invalid_lines = read_candidates_jsonl(jsonl_path)
        
        assert len(records) == 1
        assert len(invalid_lines) == 0
        
        # Check that _source field is attached with all metadata
        source = records[0].get("_source", {})
        assert source.get("author") == "business_user"
        assert source.get("subreddit") == "SaaS"
        assert source.get("permalink") == "/r/SaaS/comments/abc123/looking_for_crm/"
        assert source.get("title") == "Looking for CRM alternative"
        assert source.get("score") == 42
        assert source.get("num_comments") == 15
        assert source.get("created_utc") == 1703980800


# =============================================================================
# Curator Tests
# =============================================================================

class TestCurator:
    """Tests for curator.py."""
    
    def test_select_top_basic(self):
        """Test basic top selection."""
        from siw_intent_brain.report.curator import select_top
        
        cards = [
            _make_valid_lead_card(tier="B", confidence=0.7),
            _make_valid_lead_card(tier="S", confidence=0.9),
            _make_valid_lead_card(tier="A", confidence=0.8),
        ]
        
        top = select_top(cards, 2)
        
        assert len(top) == 2
        assert top[0]["lead_tier"] == "S"
        assert top[1]["lead_tier"] == "A"
    
    def test_select_top_filters_ok_false(self):
        """Test that ok=False records are excluded by default."""
        from siw_intent_brain.report.curator import select_top
        
        cards = [
            _make_valid_lead_card(ok=False, tier="S", confidence=0.99),
            _make_valid_lead_card(ok=True, tier="B", confidence=0.7),
        ]
        
        top = select_top(cards, 10)
        
        assert len(top) == 1
        assert top[0]["lead_tier"] == "B"
    
    def test_select_top_zero(self):
        """Test top_n <= 0 returns empty list."""
        from siw_intent_brain.report.curator import select_top
        
        cards = [_make_valid_lead_card()]
        
        assert select_top(cards, 0) == []
        assert select_top(cards, -1) == []
    
    def test_compute_stats_basic(self):
        """Test basic stats computation."""
        from siw_intent_brain.report.curator import compute_stats
        
        cards = [
            _make_valid_lead_card(
                tier="S", confidence=0.9,
                urgency=0.8, pain_point_intensity=0.7,
                commercial_relevance=0.9, solution_seeking=0.85,
                keywords=["keyword1", "keyword2"],
                budget_hints=["$100"],
            ),
            _make_valid_lead_card(
                tier="A", confidence=0.8,
                urgency=0.6, pain_point_intensity=0.5,
                commercial_relevance=0.7, solution_seeking=0.75,
                keywords=["keyword1", "keyword3"],
                budget_hints=["$200"],
            ),
        ]
        
        stats = compute_stats(cards)
        
        assert stats["total"] == 2
        assert stats["valid"] == 2
        assert stats["invalid"] == 0
        assert stats["tier_counts"]["S"] == 1
        assert stats["tier_counts"]["A"] == 1
        assert stats["means"]["confidence"] == 0.85
        # keyword1 appears twice
        assert ("keyword1", 2) in stats["top_keywords"]
    
    def test_compute_stats_with_invalid_lines(self):
        """Test stats with invalid lines counted."""
        from siw_intent_brain.report.curator import compute_stats
        
        cards = [_make_valid_lead_card()]
        invalid = [
            {"line_number": 1, "reason": "error", "raw": "..."},
            {"line_number": 2, "reason": "error", "raw": "..."},
        ]
        
        stats = compute_stats(cards, invalid)
        
        assert stats["total"] == 3
        assert stats["valid"] == 1
        assert stats["invalid"] == 2
    
    def test_compute_stats_empty(self):
        """Test stats with no valid records."""
        from siw_intent_brain.report.curator import compute_stats
        
        stats = compute_stats([])
        
        assert stats["total"] == 0
        assert stats["means"]["confidence"] == 0.0


# =============================================================================
# Render PDF Tests
# =============================================================================

class TestRenderPDF:
    """Tests for render_pdf.py."""
    
    def test_render_basic_pdf(self, tmp_path: Path):
        """Test basic PDF generation."""
        from siw_intent_brain.report.curator import compute_stats, select_top
        from siw_intent_brain.report.render_pdf import render_report
        
        cards = [
            _make_valid_lead_card(tier="S", confidence=0.95),
            _make_valid_lead_card(tier="A", confidence=0.85),
        ]
        
        stats = compute_stats(cards)
        top = select_top(cards, 10)
        
        out_path = tmp_path / "report.pdf"
        render_report(
            records=top,
            stats=stats,
            invalid_lines=[],
            out_path=str(out_path),
            input_filename="test.jsonl",
        )
        
        assert out_path.exists()
        assert out_path.stat().st_size > 0
    
    def test_render_with_invalid_lines(self, tmp_path: Path):
        """Test PDF generation includes invalid lines appendix."""
        from siw_intent_brain.report.curator import compute_stats, select_top
        from siw_intent_brain.report.render_pdf import render_report
        
        cards = [_make_valid_lead_card()]
        invalid = [
            {"line_number": 5, "reason": "JSON parse error", "raw": "bad json"},
        ]
        
        stats = compute_stats(cards, invalid)
        top = select_top(cards, 10)
        
        out_path = tmp_path / "report_with_invalid.pdf"
        render_report(
            records=top,
            stats=stats,
            invalid_lines=invalid,
            out_path=str(out_path),
        )
        
        assert out_path.exists()
        assert out_path.stat().st_size > 0
    
    def test_render_empty_records(self, tmp_path: Path):
        """Test PDF generation with no records."""
        from siw_intent_brain.report.curator import compute_stats
        from siw_intent_brain.report.render_pdf import render_report
        
        stats = compute_stats([])
        
        out_path = tmp_path / "empty_report.pdf"
        render_report(
            records=[],
            stats=stats,
            invalid_lines=[],
            out_path=str(out_path),
        )
        
        assert out_path.exists()
        assert out_path.stat().st_size > 0


# =============================================================================
# Integration Tests
# =============================================================================

class TestReportIntegration:
    """Integration tests for the full report pipeline."""
    
    def test_full_pipeline(self, tmp_path: Path):
        """Test full pipeline: read -> select -> stats -> render."""
        from siw_intent_brain.report import (
            read_candidates_jsonl,
            select_top,
            compute_stats,
            render_report,
        )
        
        # Create test JSONL
        cards = [
            _make_valid_lead_card(tier="S", confidence=0.95),
            _make_valid_lead_card(tier="A", confidence=0.85),
            _make_valid_lead_card(tier="B", confidence=0.75),
            _make_valid_lead_card(tier="C", confidence=0.65),
            _make_valid_lead_card(tier="D", confidence=0.55),
        ]
        
        jsonl_path = tmp_path / "candidates.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for card in cards:
                f.write(json.dumps(card) + "\n")
        
        # Run pipeline
        records, invalid_lines = read_candidates_jsonl(jsonl_path)
        assert len(records) == 5
        
        top = select_top(records, 3)
        assert len(top) == 3
        assert top[0]["lead_tier"] == "S"
        
        stats = compute_stats(records, invalid_lines)
        assert stats["valid"] == 5
        
        out_path = tmp_path / "final_report.pdf"
        render_report(
            records=top,
            stats=stats,
            invalid_lines=invalid_lines,
            out_path=str(out_path),
            input_filename="candidates.jsonl",
        )
        
        assert out_path.exists()
        assert out_path.stat().st_size > 1000  # Should be a reasonable size


# =============================================================================
# Stdin Encoding Tests
# =============================================================================

class TestStdinEncoding:
    """Tests for stdin encoding handling."""
    
    def test_decode_utf16_le_with_bom(self):
        """Test decoding UTF-16-LE with BOM (PowerShell default)."""
        from siw_intent_brain.report.reader import _decode_stdin_bytes
        
        text = '{"ok": true}\n'
        # UTF-16-LE with BOM
        raw_bytes = text.encode('utf-16')
        
        result, used_fallback = _decode_stdin_bytes(raw_bytes)
        assert '{"ok": true}' in result
        assert used_fallback is False
    
    def test_decode_utf16_le_no_bom(self):
        """Test decoding UTF-16-LE without BOM (alternate PowerShell)."""
        from siw_intent_brain.report.reader import _decode_stdin_bytes
        
        text = '{"ok": true}\n'
        # UTF-16-LE without BOM (has NUL bytes)
        raw_bytes = text.encode('utf-16-le')
        
        result, used_fallback = _decode_stdin_bytes(raw_bytes)
        assert '{"ok": true}' in result
        assert used_fallback is False
    
    def test_decode_utf8(self):
        """Test decoding standard UTF-8."""
        from siw_intent_brain.report.reader import _decode_stdin_bytes
        
        text = '{"ok": true}\n'
        raw_bytes = text.encode('utf-8')
        
        result, used_fallback = _decode_stdin_bytes(raw_bytes)
        assert '{"ok": true}' in result
        assert used_fallback is False
    
    def test_decode_utf8_with_bom(self):
        """Test decoding UTF-8 with BOM."""
        from siw_intent_brain.report.reader import _decode_stdin_bytes
        
        text = '{"ok": true}\n'
        raw_bytes = b'\xef\xbb\xbf' + text.encode('utf-8')
        
        result, used_fallback = _decode_stdin_bytes(raw_bytes)
        assert '{"ok": true}' in result
        assert used_fallback is False
    
    def test_decode_fallback_latin1(self):
        """Test that unrecognized encoding falls back to latin-1."""
        from siw_intent_brain.report.reader import _decode_stdin_bytes
        
        # Create bytes that are valid latin-1 but not valid UTF-8
        # Latin-1 specific chars (128-255 range, no NUL bytes to avoid UTF-16 detection)
        raw_bytes = b'\xe0\xe1\xe2\xe3\xe4'  # àáâãä in latin-1
        
        result, used_fallback = _decode_stdin_bytes(raw_bytes)
        assert used_fallback is True
        assert len(result) == 5  # Should decode all bytes


# =============================================================================
# Sanitize Text Tests
# =============================================================================

class TestSanitizeText:
    """Tests for text sanitization."""
    
    def test_control_char_removal(self):
        """Test that control characters are removed."""
        from siw_intent_brain.report.render_pdf import _sanitize_text
        
        # Text with control characters
        text = "hello\x00world\x1ftest"
        result = _sanitize_text(text)
        
        assert "\x00" not in result
        assert "\x1f" not in result
        assert "hello" in result
        assert "world" in result
        assert "test" in result
    
    def test_xml_escaping(self):
        """Test that XML special chars are escaped."""
        from siw_intent_brain.report.render_pdf import _sanitize_text
        
        text = "<tag> & value"
        result = _sanitize_text(text)
        
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result
    
    def test_preserves_newlines(self):
        """Test that newlines and tabs are preserved."""
        from siw_intent_brain.report.render_pdf import _sanitize_text
        
        text = "line1\nline2\ttab"
        result = _sanitize_text(text)
        
        assert "\n" in result
        assert "\t" in result


# =============================================================================
# CLI Integration Tests
# =============================================================================

class TestReportCLI:
    """CLI integration tests for report command."""
    
    def test_report_cli_from_file(self, tmp_path: Path):
        """Test CLI report command with file input."""
        from siw_intent_brain.cli import main
        
        # Create test JSONL
        cards = [
            _make_valid_lead_card(tier="S", confidence=0.95),
            _make_valid_lead_card(tier="A", confidence=0.85),
        ]
        
        jsonl_path = tmp_path / "input.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for card in cards:
                f.write(json.dumps(card) + "\n")
        
        out_path = tmp_path / "report.pdf"
        
        # Run CLI
        exit_code = main([
            "report",
            "--in", str(jsonl_path),
            "--out", str(out_path),
            "--top", "10",
        ])
        
        assert exit_code == 0
        assert out_path.exists()
        assert out_path.stat().st_size > 0
    
    def test_report_cli_missing_output(self, tmp_path: Path):
        """Test CLI report command fails without --out."""
        from siw_intent_brain.cli import main
        import sys
        
        jsonl_path = tmp_path / "input.jsonl"
        jsonl_path.write_text('{"ok": true}', encoding="utf-8")
        
        # Capture stderr and expect non-zero exit or argparse error
        # argparse will exit with code 2 for missing required args
        try:
            exit_code = main(["report", "--in", str(jsonl_path)])
            # If we get here, it should be an error code
            assert exit_code != 0
        except SystemExit as e:
            # argparse raises SystemExit(2) for missing required args
            assert e.code == 2
    
    def test_report_cli_verbose_mode(self, tmp_path: Path, capsys):
        """Test CLI report command verbose output."""
        from siw_intent_brain.cli import main
        
        # Create test JSONL
        card = _make_valid_lead_card()
        jsonl_path = tmp_path / "input.jsonl"
        jsonl_path.write_text(json.dumps(card), encoding="utf-8")
        
        out_path = tmp_path / "report.pdf"
        
        # Run CLI with verbose
        exit_code = main([
            "report",
            "--in", str(jsonl_path),
            "--out", str(out_path),
            "--verbose",
        ])
        
        assert exit_code == 0
        
        # Check stderr has verbose output
        captured = capsys.readouterr()
        assert "valid records" in captured.err.lower() or "report written" in captured.err.lower()
    
    def test_report_cli_quiet_mode(self, tmp_path: Path, capsys):
        """Test CLI report command quiet (non-verbose) output."""
        from siw_intent_brain.cli import main
        
        # Create test JSONL
        card = _make_valid_lead_card()
        jsonl_path = tmp_path / "input.jsonl"
        jsonl_path.write_text(json.dumps(card), encoding="utf-8")
        
        out_path = tmp_path / "report.pdf"
        
        # Run CLI without verbose
        exit_code = main([
            "report",
            "--in", str(jsonl_path),
            "--out", str(out_path),
        ])
        
        assert exit_code == 0
        
        # Check stderr is quiet (no summary/path messages)
        captured = capsys.readouterr()
        # Should not have the verbose messages
        assert "valid records" not in captured.err.lower()
        assert "report written" not in captured.err.lower()
    
    def test_report_cli_stdin_dash(self, tmp_path: Path, monkeypatch):
        """Test CLI report command with --in - (stdin) via UTF-8."""
        import io
        from siw_intent_brain.cli import main
        
        # Create test JSONL content
        card = _make_valid_lead_card()
        jsonl_content = json.dumps(card) + "\n"
        
        # Mock stdin with UTF-8 bytes
        stdin_bytes = jsonl_content.encode('utf-8')
        mock_stdin = io.BytesIO(stdin_bytes)
        
        # Create a mock stdin that has buffer attribute
        class MockStdin:
            def __init__(self, data: bytes):
                self.buffer = io.BytesIO(data)
            def isatty(self):
                return False
            def read(self):
                return self.buffer.read().decode('utf-8')
        
        monkeypatch.setattr('sys.stdin', MockStdin(stdin_bytes))
        
        out_path = tmp_path / "report_stdin.pdf"
        
        # Run CLI with --in -
        exit_code = main([
            "report",
            "--in", "-",
            "--out", str(out_path),
        ])
        
        assert exit_code == 0
        assert out_path.exists()
        assert out_path.stat().st_size > 0
    
    def test_report_cli_stdin_utf16(self, tmp_path: Path, monkeypatch):
        """Test CLI report command with stdin UTF-16 (PowerShell pipe simulation)."""
        import io
        from siw_intent_brain.cli import main
        
        # Create test JSONL content
        card = _make_valid_lead_card()
        jsonl_content = json.dumps(card) + "\n"
        
        # Encode as UTF-16 (PowerShell default pipe encoding)
        stdin_bytes = jsonl_content.encode('utf-16')
        
        # Create a mock stdin that has buffer attribute
        class MockStdin:
            def __init__(self, data: bytes):
                self.buffer = io.BytesIO(data)
            def isatty(self):
                return False
            def read(self):
                # This should not be called - we use buffer.read() for encoding detection
                raise RuntimeError("Should use buffer.read()")
        
        monkeypatch.setattr('sys.stdin', MockStdin(stdin_bytes))
        
        out_path = tmp_path / "report_stdin_utf16.pdf"
        
        # Run CLI with --in -
        exit_code = main([
            "report",
            "--in", "-",
            "--out", str(out_path),
        ])
        
        assert exit_code == 0
        assert out_path.exists()
        assert out_path.stat().st_size > 0
    
    def test_report_cli_stdin_auto_detect(self, tmp_path: Path, monkeypatch):
        """Test CLI report command with implicit stdin (no --in, non-TTY)."""
        import io
        from siw_intent_brain.cli import main
        
        # Create test JSONL content
        card = _make_valid_lead_card()
        jsonl_content = json.dumps(card) + "\n"
        stdin_bytes = jsonl_content.encode('utf-8')
        
        class MockStdin:
            def __init__(self, data: bytes):
                self.buffer = io.BytesIO(data)
            def isatty(self):
                return False  # Non-TTY means stdin should be read
            def read(self):
                return self.buffer.read().decode('utf-8')
        
        monkeypatch.setattr('sys.stdin', MockStdin(stdin_bytes))
        
        out_path = tmp_path / "report_stdin_auto.pdf"
        
        # Run CLI without --in (should auto-detect stdin)
        exit_code = main([
            "report",
            "--out", str(out_path),
        ])
        
        assert exit_code == 0
        assert out_path.exists()
        assert out_path.stat().st_size > 0

