"""
Encoding-safe JSONL reader for LeadCard candidates.

Handles:
  - UTF-8, UTF-8 with BOM, UTF-16 (Windows PowerShell default)
  - Normalization of harvest wrapper format {"card": {...}} to LeadCard
  - Validation with validate_lead_card()
  - Invalid line collection for appendix
  - Stdin with encoding auto-detection (PowerShell UTF-16 pipes)

Security:
  - Never prints API keys or secrets
  - Truncates raw lines for appendix (max 240 chars)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from ..contracts import validate_lead_card
from ..io_utils import read_text_file, FileReadError


# Maximum length for raw line in invalid line record
_MAX_RAW_LEN = 240

# Encodings to try for stdin (order matters)
_STDIN_ENCODINGS = ["utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be"]


def _decode_stdin_bytes(raw_bytes: bytes) -> Tuple[str, bool]:
    """
    Decode stdin bytes with encoding auto-detection.
    
    Tries encodings in order to handle PowerShell UTF-16 pipes:
      1. Check for BOM (UTF-16-LE, UTF-16-BE, UTF-8)
      2. Heuristic: NUL bytes pattern indicates UTF-16
      3. Try: utf-8-sig, utf-8, utf-16, utf-16-le, utf-16-be
      4. Fallback: latin-1 (never fails, but content may be garbled)
    
    Returns:
        Tuple of:
          - Decoded string
          - used_fallback: True if latin-1 fallback was used (may indicate
            encoding issues that could produce garbled content)
    """
    # Quick heuristic: if content has alternating NUL bytes, likely UTF-16
    # UTF-16-LE ASCII text has pattern: char, NUL, char, NUL
    if len(raw_bytes) >= 2:
        # Check for BOM first
        if raw_bytes[:2] == b'\xff\xfe':  # UTF-16-LE BOM
            try:
                return raw_bytes.decode('utf-16'), False
            except UnicodeDecodeError:
                pass
        elif raw_bytes[:2] == b'\xfe\xff':  # UTF-16-BE BOM
            try:
                return raw_bytes.decode('utf-16'), False
            except UnicodeDecodeError:
                pass
        elif raw_bytes[:3] == b'\xef\xbb\xbf':  # UTF-8 BOM
            try:
                return raw_bytes.decode('utf-8-sig'), False
            except UnicodeDecodeError:
                pass
        # Heuristic: check for NUL bytes (common in UTF-16 ASCII text)
        elif b'\x00' in raw_bytes[:100]:
            # Likely UTF-16, try both LE and BE
            for enc in ['utf-16-le', 'utf-16-be', 'utf-16']:
                try:
                    return raw_bytes.decode(enc), False
                except UnicodeDecodeError:
                    continue
    
    # Try standard encodings
    for encoding in _STDIN_ENCODINGS:
        try:
            return raw_bytes.decode(encoding), False
        except UnicodeDecodeError:
            continue
    
    # Last resort: latin-1 (never fails, but may produce garbage)
    # Return flag indicating fallback was used
    return raw_bytes.decode('latin-1'), True


def _truncate(s: str, max_len: int) -> str:
    """Truncate string to max_len, appending '...' if truncated."""
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."


def _normalize_to_lead_card(obj: Any) -> Tuple[Dict[str, Any] | None, str | None]:
    """
    Normalize parsed JSON to LeadCard format.
    
    Handles:
      1. {"card": {...}} wrapper (harvest output)
      2. Direct LeadCard dict
    
    Returns:
      (lead_card_dict, None) on success
      (None, reason) on failure
    """
    if not isinstance(obj, dict):
        return None, "not a JSON object"
    
    # Check for harvest wrapper format
    if "card" in obj and isinstance(obj["card"], dict):
        return obj["card"], None
    
    # Treat as direct LeadCard
    return obj, None


def read_candidates_jsonl(
    path_or_stdin: Union[str, Path, None] = None,
    *,
    from_stdin: bool = False,
    verbose: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Read and parse JSONL file containing LeadCard records.
    
    Args:
        path_or_stdin: File path to read, or None if reading from stdin.
        from_stdin: If True, read from sys.stdin instead of file.
        verbose: If True, emit warnings to stderr (e.g., encoding fallback).
    
    Returns:
        Tuple of:
          - records: List of valid LeadCard dicts
          - invalid_lines: List of invalid line records with schema:
              - line_number: int (1-based)
              - reason: str (short, stable, no raw tracebacks)
              - raw: str (truncated to 240 chars)
    
    Raises:
        FileReadError: If file cannot be read (when not using stdin).
    
    Notes:
        - Skips empty/whitespace-only lines
        - Validates each LeadCard with validate_lead_card()
        - Invalid lines are collected, not raised
        - If stdin encoding cannot be detected, falls back to latin-1
          (warning emitted if verbose=True)
    """
    records: List[Dict[str, Any]] = []
    invalid_lines: List[Dict[str, Any]] = []
    
    # Read content
    if from_stdin:
        try:
            # Read raw bytes from stdin buffer to handle encoding ourselves
            # This is critical for PowerShell which uses UTF-16 for pipes
            if hasattr(sys.stdin, 'buffer'):
                raw_bytes = sys.stdin.buffer.read()
                content, used_fallback = _decode_stdin_bytes(raw_bytes)
                
                # Warn if latin-1 fallback was used (may indicate encoding issues)
                if used_fallback and verbose:
                    print(
                        "WARN: Could not detect stdin encoding, using latin-1 fallback. "
                        "Content may be garbled. Consider using file input instead.",
                        file=sys.stderr
                    )
            else:
                # Fallback for environments without buffer access
                content = sys.stdin.read()
        except Exception as e:
            # Stdin read error - treat as file error
            raise FileReadError(
                "stdin",
                f"Failed to read stdin: {e}",
                suggestion="Check stdin encoding or use file input instead",
            )
    else:
        if path_or_stdin is None:
            raise FileReadError(
                "None",
                "No input path provided",
                suggestion="Provide a file path or use from_stdin=True",
            )
        content = read_text_file(path_or_stdin)
    
    # Split into lines and process
    lines = content.splitlines()
    
    for line_number, line in enumerate(lines, start=1):
        # Skip empty/whitespace-only lines
        stripped = line.strip()
        if not stripped:
            continue
        
        # Try to parse JSON
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as e:
            invalid_lines.append({
                "line_number": line_number,
                "reason": f"JSON parse error: {e.msg}",
                "raw": _truncate(stripped, _MAX_RAW_LEN),
            })
            continue
        
        # Normalize to LeadCard
        card, norm_error = _normalize_to_lead_card(obj)
        if norm_error:
            invalid_lines.append({
                "line_number": line_number,
                "reason": norm_error,
                "raw": _truncate(stripped, _MAX_RAW_LEN),
            })
            continue
        
        # Validate LeadCard schema
        validation_errors = validate_lead_card(card)
        if validation_errors:
            # Join first few errors for reason
            reason_parts = validation_errors[:3]
            if len(validation_errors) > 3:
                reason_parts.append(f"... (+{len(validation_errors) - 3} more)")
            reason = "schema invalid: " + "; ".join(reason_parts)
            
            invalid_lines.append({
                "line_number": line_number,
                "reason": reason,
                "raw": _truncate(stripped, _MAX_RAW_LEN),
            })
            continue
        
        # Valid record
        records.append(card)
    
    return records, invalid_lines

