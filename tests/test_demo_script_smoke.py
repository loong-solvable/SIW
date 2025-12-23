"""
Smoke tests for scripts/demo_score.py

Tests that the demo script:
  - Exits with code 1 when OPENROUTER_API_KEY is not set
  - Prints helpful error message

All tests are OFFLINE - no real network requests.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


# Path to demo script
DEMO_SCRIPT = Path(__file__).parent.parent / "scripts" / "demo_score.py"


class TestDemoScriptNoKey:
    """Tests for demo_score.py when API key is missing."""

    def test_exits_with_code_1_without_key(self) -> None:
        """Script exits with code 1 when OPENROUTER_API_KEY is not set."""
        import os
        
        # Copy current environment and remove/empty the API key
        env = os.environ.copy()
        env["OPENROUTER_API_KEY"] = ""
        
        # Run the script as subprocess
        result = subprocess.run(
            [sys.executable, str(DEMO_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        
        assert result.returncode == 1

    def test_prints_helpful_message_without_key(self) -> None:
        """Script prints helpful message when API key is missing."""
        # Run the script as subprocess with empty key
        import os
        env = os.environ.copy()
        env["OPENROUTER_API_KEY"] = ""
        
        result = subprocess.run(
            [sys.executable, str(DEMO_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )
        
        # Should mention the missing key
        assert "OPENROUTER_API_KEY" in result.stderr
        # Should give instructions
        assert "export" in result.stderr.lower() or "$env:" in result.stderr

    def test_does_not_make_network_request_without_key(self) -> None:
        """Script does NOT attempt network request when key is missing."""
        import os
        env = os.environ.copy()
        env["OPENROUTER_API_KEY"] = ""
        
        # If it tried to make a request without key, it would fail differently
        # (connection error or 401). With our check, it exits cleanly.
        result = subprocess.run(
            [sys.executable, str(DEMO_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            timeout=5,  # Should exit quickly, not hang on network
        )
        
        # Should exit with 1 (our key check), not other errors
        assert result.returncode == 1
        # Should NOT contain network-related errors
        assert "connection" not in result.stderr.lower()
        assert "timeout" not in result.stderr.lower()


class TestDemoScriptExists:
    """Basic checks that demo script exists and is valid Python."""

    def test_script_exists(self) -> None:
        """Demo script file exists."""
        assert DEMO_SCRIPT.exists(), f"Demo script not found: {DEMO_SCRIPT}"

    def test_script_is_valid_python(self) -> None:
        """Demo script compiles without syntax errors."""
        import py_compile
        
        # This will raise if there are syntax errors
        py_compile.compile(str(DEMO_SCRIPT), doraise=True)

    def test_script_has_main_function(self) -> None:
        """Demo script has a main() function."""
        content = DEMO_SCRIPT.read_text(encoding="utf-8")
        
        assert "def main(" in content
        assert 'if __name__ == "__main__"' in content

