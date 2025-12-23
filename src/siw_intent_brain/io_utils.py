"""
I/O utilities for SIW Intent Brain.

Provides encoding-safe file reading to handle Windows PowerShell
redirection quirks (UTF-16LE with BOM, UTF-8 with BOM, etc.).

NEVER raises raw exceptions with tracebacks - provides user-friendly messages.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from .errors import SIWError


# Error code for file read failures
E_FILE_READ = "E_FILE_READ"


class FileReadError(SIWError):
    """
    Error reading a file.
    
    Provides user-friendly message with actionable suggestion.
    """
    
    def __init__(self, path: str, reason: str, suggestion: str = ""):
        self.path = path
        self.reason = reason
        self.suggestion = suggestion
        self.error_code = E_FILE_READ
        
        msg = f"Cannot read file '{path}': {reason}"
        if suggestion:
            msg += f" ({suggestion})"
        
        super().__init__(msg)


def read_text_file(path: Union[str, Path]) -> str:
    """
    Read a text file with automatic encoding detection.
    
    Tries encodings in order to handle Windows PowerShell quirks:
      1. utf-8-sig (UTF-8 with BOM, handles BOM stripping)
      2. utf-8 (standard, for files without BOM)
      3. utf-16 (PowerShell ">" redirection default)
    
    Note: utf-8-sig is tried first because it handles both BOM and non-BOM
    UTF-8 files correctly, and json.loads rejects BOM in plain utf-8.
    
    Args:
        path: Path to the file (string or Path object).
    
    Returns:
        File contents as string (BOM stripped if present).
    
    Raises:
        FileReadError: If file cannot be found or read with any encoding.
            Provides user-friendly message with suggestions.
    
    Examples:
        >>> content = read_text_file("output.json")
        >>> data = json.loads(content)
    """
    path_obj = Path(path)
    
    # Check if file exists
    if not path_obj.exists():
        raise FileReadError(
            str(path),
            "File not found",
            suggestion="Check the file path",
        )
    
    if not path_obj.is_file():
        raise FileReadError(
            str(path),
            "Path is not a file",
            suggestion="Provide a file path, not a directory",
        )
    
    # Try encodings in order:
    # 1. utf-8-sig: handles UTF-8 with BOM (strips BOM automatically)
    # 2. utf-8: standard UTF-8 without BOM
    # 3. utf-16: Windows PowerShell ">" redirect default
    encodings = ["utf-8-sig", "utf-8", "utf-16"]
    
    last_error: Exception | None = None
    
    for encoding in encodings:
        try:
            content = path_obj.read_text(encoding=encoding)
            return content
        except UnicodeDecodeError as e:
            last_error = e
            continue
        except Exception as e:
            # Other errors (permission, etc.) - raise immediately
            raise FileReadError(
                str(path),
                str(e),
                suggestion="Check file permissions",
            ) from e
    
    # All encodings failed
    raise FileReadError(
        str(path),
        "Unable to decode file with any supported encoding (utf-8, utf-8-sig, utf-16)",
        suggestion="Try: Out-File -Encoding utf8 or save as UTF-8 without BOM",
    )


def read_json_file(path: Union[str, Path]) -> dict:
    """
    Read and parse a JSON file with automatic encoding detection.
    
    Combines read_text_file() with JSON parsing.
    
    Args:
        path: Path to the JSON file.
    
    Returns:
        Parsed JSON as dict.
    
    Raises:
        FileReadError: If file cannot be read.
        FileReadError: If JSON parsing fails (with helpful message).
    """
    import json
    
    content = read_text_file(path)
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise FileReadError(
            str(path),
            f"Invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}",
            suggestion="Check JSON syntax",
        ) from e
