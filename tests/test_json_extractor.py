"""
Tests for parsing/json_extractor.py - JSON extraction from LLM output.
"""

import pytest

from siw_intent_brain.parsing.json_extractor import (
    extract_json,
    extract_json_safe,
)
from siw_intent_brain.errors import ParseError, E_PARSE_JSON


# =============================================================================
# Test extract_json - Strict Mode
# =============================================================================

class TestExtractJsonStrict:
    """Tests for direct JSON parsing (strict mode)."""
    
    def test_pure_json_object(self):
        """Pure JSON object parses as strict."""
        text = '{"a": 1, "b": "hello"}'
        obj, mode = extract_json(text)
        assert mode == "strict"
        assert obj == {"a": 1, "b": "hello"}
    
    def test_json_with_whitespace(self):
        """JSON with surrounding whitespace is strict."""
        text = '   \n  {"key": "value"}  \n  '
        obj, mode = extract_json(text)
        assert mode == "strict"
        assert obj == {"key": "value"}
    
    def test_nested_json(self):
        """Nested JSON object parses correctly."""
        text = '{"outer": {"inner": [1, 2, 3]}}'
        obj, mode = extract_json(text)
        assert mode == "strict"
        assert obj["outer"]["inner"] == [1, 2, 3]
    
    def test_empty_object(self):
        """Empty object {} parses as strict."""
        text = "{}"
        obj, mode = extract_json(text)
        assert mode == "strict"
        assert obj == {}
    
    def test_json_with_unicode(self):
        """JSON with unicode parses correctly."""
        text = '{"msg": "你好世界", "emoji": "🎉"}'
        obj, mode = extract_json(text)
        assert mode == "strict"
        assert obj["msg"] == "你好世界"
        assert obj["emoji"] == "🎉"


# =============================================================================
# Test extract_json - Extracted Mode
# =============================================================================

class TestExtractJsonExtracted:
    """Tests for JSON extraction from surrounding text."""
    
    def test_json_with_prefix(self):
        """JSON with prefix text uses extracted mode."""
        text = 'Here is the result: {"a": 1}'
        obj, mode = extract_json(text)
        assert mode == "extracted"
        assert obj == {"a": 1}
    
    def test_json_with_suffix(self):
        """JSON with suffix text uses extracted mode."""
        text = '{"a": 1} That\'s all!'
        obj, mode = extract_json(text)
        assert mode == "extracted"
        assert obj == {"a": 1}
    
    def test_json_with_prefix_and_suffix(self):
        """JSON with both prefix and suffix."""
        text = 'Result:\n{"key": "value"}\nEnd of response.'
        obj, mode = extract_json(text)
        assert mode == "extracted"
        assert obj == {"key": "value"}
    
    def test_json_in_markdown_code_block(self):
        """JSON in markdown code block."""
        text = '''Here's the output:
```json
{"score": 0.8, "tier": "A"}
```
Done.'''
        obj, mode = extract_json(text)
        assert mode == "extracted"
        assert obj["score"] == 0.8
        assert obj["tier"] == "A"
    
    def test_multiple_braces_uses_outer(self):
        """Multiple brace pairs uses first '{' to last '}'."""
        text = 'prefix {"outer": {"inner": 1}} suffix'
        obj, mode = extract_json(text)
        assert mode == "extracted"
        assert obj == {"outer": {"inner": 1}}
    
    def test_nested_json_extracted(self):
        """Complex nested JSON extracted correctly."""
        text = '''Response:
{
  "scores": {"urgency": 0.5, "pain": 0.8},
  "items": ["a", "b", "c"]
}
End.'''
        obj, mode = extract_json(text)
        assert mode == "extracted"
        assert obj["scores"]["urgency"] == 0.5
        assert obj["items"] == ["a", "b", "c"]


# =============================================================================
# Test extract_json - Failure Cases
# =============================================================================

class TestExtractJsonFail:
    """Tests for parse failures."""
    
    def test_no_braces(self):
        """Text without braces raises ParseError."""
        text = "This is just plain text without JSON"
        with pytest.raises(ParseError) as exc_info:
            extract_json(text)
        assert E_PARSE_JSON in str(exc_info.value)
        assert "no JSON object braces" in str(exc_info.value)
    
    def test_only_opening_brace(self):
        """Only opening brace raises ParseError."""
        text = "{ start but never close"
        with pytest.raises(ParseError) as exc_info:
            extract_json(text)
        assert E_PARSE_JSON in str(exc_info.value)
    
    def test_only_closing_brace(self):
        """Only closing brace raises ParseError."""
        text = "end with } but no start"
        with pytest.raises(ParseError) as exc_info:
            extract_json(text)
        assert E_PARSE_JSON in str(exc_info.value)
    
    def test_invalid_json_between_braces(self):
        """Invalid JSON between braces raises ParseError."""
        text = "{ not: valid, json here }"
        with pytest.raises(ParseError) as exc_info:
            extract_json(text)
        assert E_PARSE_JSON in str(exc_info.value)
        assert "invalid JSON" in str(exc_info.value)
    
    def test_json_array_not_object(self):
        """JSON array (not object) is extracted but fails."""
        text = '[1, 2, 3]'
        with pytest.raises(ParseError) as exc_info:
            extract_json(text)
        assert E_PARSE_JSON in str(exc_info.value)
    
    def test_empty_text(self):
        """Empty text raises ParseError."""
        text = ""
        with pytest.raises(ParseError) as exc_info:
            extract_json(text)
        assert E_PARSE_JSON in str(exc_info.value)
        assert "empty" in str(exc_info.value)
    
    def test_whitespace_only(self):
        """Whitespace-only text raises ParseError."""
        text = "   \n\t   "
        with pytest.raises(ParseError) as exc_info:
            extract_json(text)
        assert E_PARSE_JSON in str(exc_info.value)
    
    def test_none_input(self):
        """None input raises ParseError."""
        with pytest.raises(ParseError) as exc_info:
            extract_json(None)  # type: ignore
        assert E_PARSE_JSON in str(exc_info.value)
        assert "None" in str(exc_info.value)
    
    def test_brace_order_wrong(self):
        """Closing brace before opening raises ParseError."""
        text = "} before { is wrong"
        with pytest.raises(ParseError) as exc_info:
            extract_json(text)
        assert E_PARSE_JSON in str(exc_info.value)


# =============================================================================
# Test extract_json_safe
# =============================================================================

class TestExtractJsonSafe:
    """Tests for safe extraction (never raises)."""
    
    def test_success_returns_empty_error(self):
        """Successful parse returns empty error string."""
        text = '{"a": 1}'
        obj, mode, error = extract_json_safe(text)
        assert obj == {"a": 1}
        assert mode == "strict"
        assert error == ""
    
    def test_failure_returns_fail_closed(self):
        """Failed parse returns fail_closed mode."""
        text = "no json here"
        obj, mode, error = extract_json_safe(text)
        assert obj == {}
        assert mode == "fail_closed"
        assert E_PARSE_JSON in error
    
    def test_none_input_safe(self):
        """None input handled safely."""
        obj, mode, error = extract_json_safe(None)  # type: ignore
        assert obj == {}
        assert mode == "fail_closed"
        assert "None" in error


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestExtractJsonEdgeCases:
    """Edge cases and special scenarios."""
    
    def test_json_with_escaped_quotes(self):
        """JSON with escaped quotes parses correctly."""
        text = '{"msg": "He said \\"hello\\""}'
        obj, mode = extract_json(text)
        assert obj["msg"] == 'He said "hello"'
    
    def test_json_with_newlines_in_string(self):
        """JSON with escaped newlines in strings."""
        text = '{"text": "line1\\nline2"}'
        obj, mode = extract_json(text)
        assert obj["text"] == "line1\nline2"
    
    def test_very_nested_json(self):
        """Deeply nested JSON parses correctly."""
        text = '{"a": {"b": {"c": {"d": {"e": 5}}}}}'
        obj, mode = extract_json(text)
        assert obj["a"]["b"]["c"]["d"]["e"] == 5
    
    def test_json_with_numbers(self):
        """JSON with various number formats."""
        text = '{"int": 42, "float": 3.14, "neg": -7, "exp": 1.5e10}'
        obj, mode = extract_json(text)
        assert obj["int"] == 42
        assert obj["float"] == 3.14
        assert obj["neg"] == -7
        assert obj["exp"] == 1.5e10
    
    def test_json_with_boolean_null(self):
        """JSON with boolean and null values."""
        text = '{"yes": true, "no": false, "nothing": null}'
        obj, mode = extract_json(text)
        assert obj["yes"] is True
        assert obj["no"] is False
        assert obj["nothing"] is None

