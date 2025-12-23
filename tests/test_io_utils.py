"""
Tests for io_utils module.

Tests encoding handling for Windows PowerShell compatibility:
  - UTF-8 (standard)
  - UTF-8 with BOM (utf-8-sig)
  - UTF-16 with BOM (PowerShell ">" default)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from siw_intent_brain.io_utils import (
    read_text_file,
    read_json_file,
    FileReadError,
    E_FILE_READ,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# =============================================================================
# Test: read_text_file - UTF-8 (standard)
# =============================================================================

class TestReadTextFileUtf8:
    """Tests for read_text_file with UTF-8 encoding."""

    def test_reads_utf8_file(self, temp_dir: Path) -> None:
        """Can read standard UTF-8 file."""
        path = temp_dir / "test.txt"
        path.write_text("Hello, 世界!", encoding="utf-8")
        
        content = read_text_file(path)
        
        assert content == "Hello, 世界!"

    def test_reads_utf8_json(self, temp_dir: Path) -> None:
        """Can read UTF-8 JSON file."""
        path = temp_dir / "test.json"
        data = {"message": "Hello", "name": "测试"}
        path.write_text(json.dumps(data), encoding="utf-8")
        
        content = read_text_file(path)
        parsed = json.loads(content)
        
        assert parsed == data


# =============================================================================
# Test: read_text_file - UTF-8 with BOM (utf-8-sig)
# =============================================================================

class TestReadTextFileUtf8Sig:
    """Tests for read_text_file with UTF-8-sig (BOM) encoding."""

    def test_reads_utf8_bom_file(self, temp_dir: Path) -> None:
        """Can read UTF-8 file with BOM."""
        path = temp_dir / "test_bom.txt"
        # Write with BOM
        path.write_text("Hello with BOM!", encoding="utf-8-sig")
        
        content = read_text_file(path)
        
        # BOM should be stripped
        assert content == "Hello with BOM!"
        assert not content.startswith("\ufeff")

    def test_reads_utf8_bom_json(self, temp_dir: Path) -> None:
        """Can read UTF-8-sig JSON and parse it."""
        path = temp_dir / "test_bom.json"
        data = {"ok": True, "lead_tier": "A"}
        path.write_text(json.dumps(data), encoding="utf-8-sig")
        
        content = read_text_file(path)
        parsed = json.loads(content)
        
        assert parsed == data


# =============================================================================
# Test: read_text_file - UTF-16 (Windows PowerShell default)
# =============================================================================

class TestReadTextFileUtf16:
    """Tests for read_text_file with UTF-16 encoding (PowerShell ">")."""

    def test_reads_utf16_le_with_bom(self, temp_dir: Path) -> None:
        """Can read UTF-16-LE file with BOM (Windows default)."""
        path = temp_dir / "test_utf16.txt"
        # UTF-16 encoding writes BOM automatically
        path.write_text("PowerShell output!", encoding="utf-16")
        
        content = read_text_file(path)
        
        assert "PowerShell output!" in content

    def test_reads_utf16_json(self, temp_dir: Path) -> None:
        """Can read UTF-16 JSON file (PowerShell redirect)."""
        path = temp_dir / "test_utf16.json"
        data = {"ok": True, "scores": {"urgency": 0.5}}
        # Simulate PowerShell ">" redirect
        path.write_text(json.dumps(data), encoding="utf-16")
        
        content = read_text_file(path)
        parsed = json.loads(content)
        
        assert parsed == data

    def test_reads_utf16_leadcard(self, temp_dir: Path) -> None:
        """Can read UTF-16 LeadCard JSON (real-world scenario)."""
        path = temp_dir / "leadcard_utf16.json"
        lead_card = {
            "ok": True,
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
                "problem_summary": "User seeking alternative",
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
        path.write_text(json.dumps(lead_card), encoding="utf-16")
        
        content = read_text_file(path)
        parsed = json.loads(content)
        
        assert parsed["ok"] is True
        assert parsed["lead_tier"] == "A"


# =============================================================================
# Test: read_text_file - Error Cases
# =============================================================================

class TestReadTextFileErrors:
    """Tests for read_text_file error handling."""

    def test_file_not_found_raises_error(self) -> None:
        """Missing file raises FileReadError."""
        with pytest.raises(FileReadError) as exc_info:
            read_text_file("/nonexistent/path/file.txt")
        
        assert exc_info.value.error_code == E_FILE_READ
        assert "not found" in str(exc_info.value).lower()

    def test_directory_raises_error(self, temp_dir: Path) -> None:
        """Directory path raises FileReadError."""
        with pytest.raises(FileReadError) as exc_info:
            read_text_file(temp_dir)
        
        assert "not a file" in str(exc_info.value).lower()

    def test_error_has_suggestion(self, temp_dir: Path) -> None:
        """Error message includes helpful suggestion."""
        # Create binary file that can't be decoded as text
        path = temp_dir / "binary.bin"
        path.write_bytes(b"\x80\x81\x82\x83\x84\x85")
        
        with pytest.raises(FileReadError) as exc_info:
            read_text_file(path)
        
        # Should suggest using Out-File -Encoding utf8
        assert "Out-File" in str(exc_info.value) or "utf8" in str(exc_info.value).lower()


# =============================================================================
# Test: read_json_file
# =============================================================================

class TestReadJsonFile:
    """Tests for read_json_file function."""

    def test_reads_utf8_json(self, temp_dir: Path) -> None:
        """Can read and parse UTF-8 JSON."""
        path = temp_dir / "data.json"
        data = {"key": "value", "number": 42}
        path.write_text(json.dumps(data), encoding="utf-8")
        
        result = read_json_file(path)
        
        assert result == data

    def test_reads_utf16_json(self, temp_dir: Path) -> None:
        """Can read and parse UTF-16 JSON."""
        path = temp_dir / "data_utf16.json"
        data = {"ok": True, "tier": "S"}
        path.write_text(json.dumps(data), encoding="utf-16")
        
        result = read_json_file(path)
        
        assert result == data

    def test_invalid_json_raises_error(self, temp_dir: Path) -> None:
        """Invalid JSON content raises FileReadError."""
        path = temp_dir / "bad.json"
        path.write_text("{ not valid json", encoding="utf-8")
        
        with pytest.raises(FileReadError) as exc_info:
            read_json_file(path)
        
        assert "Invalid JSON" in str(exc_info.value)

    def test_file_not_found_raises_error(self) -> None:
        """Missing file raises FileReadError."""
        with pytest.raises(FileReadError) as exc_info:
            read_json_file("/nonexistent/file.json")
        
        assert exc_info.value.error_code == E_FILE_READ


# =============================================================================
# Test: CLI validate with different encodings
# =============================================================================

class TestCLIValidateEncodings:
    """Tests for CLI validate command with different file encodings."""

    def test_validate_utf16_file(self, temp_dir: Path) -> None:
        """validate command can read UTF-16 encoded file."""
        from siw_intent_brain.cli import main
        
        lead_card = {
            "ok": True,
            "scores": {
                "urgency": 0.5,
                "pain_point_intensity": 0.5,
                "commercial_relevance": 0.5,
                "solution_seeking": 0.5,
            },
            "confidence": 0.8,
            "lead_tier": "B",
            "recommended_next_step": "draft_reply",
            "rationale": "Test.",
            "extracted_signals": {
                "problem_summary": "Test",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
            "meta": {
                "model": "test",
                "provider": "openrouter",
                "latency_ms": 100,
                "retries": 0,
                "parser_mode": "strict",
                "schema_version": "lead_card.v1",
            },
        }
        
        # Write as UTF-16 (PowerShell default)
        path = temp_dir / "card_utf16.json"
        path.write_text(json.dumps(lead_card), encoding="utf-16")
        
        result = main(["validate", "--json-file", str(path)])
        
        # Should be valid (not crash with encoding error)
        assert result == 0

    def test_validate_utf8_sig_file(self, temp_dir: Path) -> None:
        """validate command can read UTF-8-sig (BOM) file."""
        from siw_intent_brain.cli import main
        
        lead_card = {
            "ok": True,
            "scores": {
                "urgency": 0.5,
                "pain_point_intensity": 0.5,
                "commercial_relevance": 0.5,
                "solution_seeking": 0.5,
            },
            "confidence": 0.8,
            "lead_tier": "B",
            "recommended_next_step": "monitor",
            "rationale": "Test with BOM.",
            "extracted_signals": {
                "problem_summary": "Test",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": [],
            "meta": {
                "model": "test",
                "provider": "openrouter",
                "latency_ms": 100,
                "retries": 0,
                "parser_mode": "strict",
                "schema_version": "lead_card.v1",
            },
        }
        
        # Write as UTF-8 with BOM
        path = temp_dir / "card_bom.json"
        path.write_text(json.dumps(lead_card), encoding="utf-8-sig")
        
        result = main(["validate", "--json-file", str(path)])
        
        assert result == 0

    def test_validate_invalid_utf16_still_invalid(self, temp_dir: Path, capsys) -> None:
        """validate with UTF-16 invalid LeadCard returns INVALID (not crash)."""
        from siw_intent_brain.cli import main
        
        # Invalid LeadCard (missing required fields)
        bad_card = {"ok": True, "scores": {"urgency": 0.5}}
        
        path = temp_dir / "bad_utf16.json"
        path.write_text(json.dumps(bad_card), encoding="utf-16")
        
        result = main(["validate", "--json-file", str(path)])
        
        # Should return 2 (INVALID), not crash
        assert result == 2
        captured = capsys.readouterr()
        assert "INVALID" in captured.out

