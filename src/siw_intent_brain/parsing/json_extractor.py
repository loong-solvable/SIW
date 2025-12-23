"""
JSON extraction from LLM output.

Supports three modes:
  - strict: json.loads() succeeds directly
  - extracted: JSON found between first '{' and last '}'
  - fail_closed: no valid JSON found (raises ParseError)

NEVER uses eval. Only standard json module.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from ..contracts import ParserMode
from ..errors import ParseError, E_PARSE_JSON


def extract_json(text: str) -> Tuple[Dict[str, Any], ParserMode]:
    """
    Extract JSON object from LLM output text.
    
    Attempts parsing in order:
      1. Direct json.loads() → "strict"
      2. Extract substring from first '{' to last '}' → "extracted"
      3. Failure → raises ParseError
    
    Args:
        text: Raw LLM output text.
    
    Returns:
        Tuple of (parsed_dict, parser_mode).
        parser_mode is "strict" or "extracted".
    
    Raises:
        ParseError: If no valid JSON object can be extracted.
    """
    if text is None:
        raise ParseError(f"{E_PARSE_JSON}: input text is None")
    
    s = str(text).strip()
    
    if not s:
        raise ParseError(f"{E_PARSE_JSON}: input text is empty")
    
    # --- Attempt 1: Strict JSON parse ---
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj, "strict"
        # If parsed but not a dict, fall through to extraction
    except json.JSONDecodeError:
        pass
    
    # --- Attempt 2: Extract JSON substring ---
    start_idx = s.find("{")
    end_idx = s.rfind("}")
    
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        raise ParseError(f"{E_PARSE_JSON}: no JSON object braces found in text")
    
    candidate = s[start_idx:end_idx + 1]
    
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj, "extracted"
        else:
            raise ParseError(
                f"{E_PARSE_JSON}: extracted JSON is not an object (got {type(obj).__name__})"
            )
    except json.JSONDecodeError as e:
        raise ParseError(
            f"{E_PARSE_JSON}: extracted substring is invalid JSON: {e}"
        ) from e


def extract_json_safe(text: str) -> Tuple[Dict[str, Any], ParserMode, str]:
    """
    Safe version that never raises - returns error string instead.
    
    Returns:
        Tuple of (obj_or_empty, parser_mode, error_msg).
        If successful: (obj, mode, "")
        If failed: ({}, "fail_closed", error_message)
    """
    try:
        obj, mode = extract_json(text)
        return obj, mode, ""
    except ParseError as e:
        return {}, "fail_closed", str(e)
    except Exception as e:
        return {}, "fail_closed", f"{E_PARSE_JSON}: unexpected error: {e}"

