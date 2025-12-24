"""
CLI entry point for siw-brain command.

Commands:
  - score: Score intent from text and output LeadCard JSON
  - validate: Validate a lead card JSON file
  - doctor: Check system environment and dependencies
  - demo: Run offline demo with sample texts

Usage:
  siw-brain score --text "..." --context-json '{...}'
  siw-brain score --text-file input.txt --context-file ctx.json
  echo "hello" | siw-brain score --context-json "{}"
  siw-brain validate --json-file output.json
  siw-brain doctor
  siw-brain demo

NEVER prints API key or sensitive data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .contracts import validate_lead_card
from .io_utils import read_text_file, read_json_file, FileReadError

if TYPE_CHECKING:
    from .brain import IntentBrain


# Factory function for IntentBrain - can be replaced in tests
_brain_factory: Optional[Callable[..., "IntentBrain"]] = None


def set_brain_factory(factory: Optional[Callable[..., "IntentBrain"]]) -> None:
    """
    Set custom brain factory for testing.
    
    Pass None to reset to default (IntentBrain.from_env).
    """
    global _brain_factory
    _brain_factory = factory


def _get_brain(config_path: Optional[str] = None, **kwargs: Any) -> "IntentBrain":
    """
    Get IntentBrain instance.
    
    Uses custom factory if set (for testing), otherwise IntentBrain.from_env.
    """
    if _brain_factory is not None:
        return _brain_factory(config_path=config_path, **kwargs)
    
    from .brain import IntentBrain
    return IntentBrain.from_env(config_path=config_path)


# Harvester factory for testing
_harvester_factory: Optional[Callable[[], Any]] = None


def set_harvester_factory(factory: Optional[Callable[[], Any]]) -> None:
    """Set custom harvester factory for testing."""
    global _harvester_factory
    _harvester_factory = factory


def _get_harvester():
    """Get harvester instance (uses factory if set)."""
    if _harvester_factory is not None:
        return _harvester_factory()
    
    from .harvester import RedditHarvester
    return RedditHarvester()


def main(argv: Optional[list[str]] = None) -> int:
    """
    Main CLI entry point.
    
    Commands:
      - score: Score intent from text
      - validate: Validate a lead card JSON file
      - doctor: Check system environment
      - demo: Run offline demo
    
    Returns:
      0: Success
      1: Input/file/config error
      2: Validation failed (validate command)
    """
    parser = argparse.ArgumentParser(
        prog="siw-brain",
        description="SIW Intent Brain - Decision support intent scoring engine",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # =========================================================================
    # score command
    # =========================================================================
    score_parser = subparsers.add_parser(
        "score",
        help="Score intent from text",
        description="Analyze text for commercial intent signals and return LeadCard JSON.",
    )
    
    # Input: text
    text_group = score_parser.add_mutually_exclusive_group()
    text_group.add_argument(
        "--text",
        help="Text to score (direct string)",
    )
    text_group.add_argument(
        "--text-file",
        help="File containing text to score",
    )
    
    # Input: context
    context_group = score_parser.add_mutually_exclusive_group()
    context_group.add_argument(
        "--context-json",
        help="Context as JSON string",
    )
    context_group.add_argument(
        "--context-file",
        help="File containing context JSON",
    )
    
    # Config options
    score_parser.add_argument(
        "--config",
        help="Path to config YAML file (optional, uses .env by default)",
    )
    score_parser.add_argument(
        "--min-confidence",
        type=float,
        help="Override min_confidence threshold (0.0-1.0)",
    )
    
    # Output options
    score_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Output compact JSON (no indentation)",
    )
    score_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable logging output to stderr (default: off)",
    )
    
    # =========================================================================
    # validate command
    # =========================================================================
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a lead card JSON file",
        description="Check if a JSON file conforms to the LeadCard schema.",
    )
    validate_parser.add_argument(
        "--json-file",
        required=True,
        help="JSON file to validate",
    )
    
    # =========================================================================
    # doctor command
    # =========================================================================
    subparsers.add_parser(
        "doctor",
        help="Check system environment and dependencies",
        description="Verify Python version, package imports, schema files, and configuration.",
    )
    
    # =========================================================================
    # demo command
    # =========================================================================
    demo_parser = subparsers.add_parser(
        "demo",
        help="Run offline demo with sample texts",
        description="Run offline demo with 3 sample texts (no API key required).",
    )
    demo_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable logging output to stderr (default: off)",
    )
    
    # =========================================================================
    # harvest command
    # =========================================================================
    harvest_parser = subparsers.add_parser(
        "harvest",
        help="Harvest and score Reddit posts",
        description="Fetch posts from Reddit and score them for commercial intent.",
    )
    harvest_parser.add_argument(
        "--sub",
        required=True,
        help="Subreddit name (without r/)",
    )
    harvest_parser.add_argument(
        "--query",
        help="Search query (optional)",
    )
    harvest_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of posts to fetch (default: 10)",
    )
    harvest_parser.add_argument(
        "--sort",
        choices=["new", "hot", "top"],
        default="new",
        help="Sort order (default: new)",
    )
    harvest_parser.add_argument(
        "--config",
        help="Path to config YAML file",
    )
    harvest_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output to stderr",
    )
    
    # Parse arguments
    args = parser.parse_args(argv)
    
    if args.command is None:
        parser.print_help()
        return 0
    
    if args.command == "score":
        return _cmd_score(args)
    
    if args.command == "validate":
        return _cmd_validate(args.json_file)
    
    if args.command == "doctor":
        return _cmd_doctor()
    
    if args.command == "demo":
        return _cmd_demo(args)
    
    if args.command == "harvest":
        return _cmd_harvest(args)
    
    return 1


def _cmd_score(args: argparse.Namespace) -> int:
    """
    Execute score command.
    
    Returns:
      0: Success (outputs LeadCard JSON)
      1: Input error (missing text, file not found, etc.)
    """
    # --- Enable logging if --verbose ---
    if getattr(args, "verbose", False):
        from .telemetry.logging import enable_logging
        enable_logging(True)
    
    # --- Read text (with stdin fallback) ---
    text = _read_text_with_stdin(
        getattr(args, "text", None),
        getattr(args, "text_file", None),
    )
    if text is None:
        print("ERROR: Must provide --text, --text-file, or pipe text via stdin", file=sys.stderr)
        return 1
    
    # --- Read context ---
    context = _read_context(
        getattr(args, "context_json", None),
        getattr(args, "context_file", None),
    )
    if context is None:
        # Error already printed
        return 1
    
    # --- Get brain ---
    try:
        brain = _get_brain(config_path=getattr(args, "config", None))
    except Exception as e:
        # Don't expose API key in error message
        error_msg = str(e)
        if "api_key" in error_msg.lower() or "key" in error_msg.lower():
            print("ERROR: Configuration error (check OPENROUTER_API_KEY)", file=sys.stderr)
        else:
            print(f"ERROR: {error_msg}", file=sys.stderr)
        return 1
    
    # --- Override min_confidence if specified ---
    if getattr(args, "min_confidence", None) is not None:
        # Create new config with overridden min_confidence
        from .config import BrainConfig
        old_cfg = brain.cfg
        brain.cfg = BrainConfig(
            api_key=old_cfg.api_key,
            model=old_cfg.model,
            base_url=old_cfg.base_url,
            timeout_s=old_cfg.timeout_s,
            max_retries=old_cfg.max_retries,
            backoff_s=old_cfg.backoff_s,
            http_referer=old_cfg.http_referer,
            x_title=old_cfg.x_title,
            min_confidence=args.min_confidence,
            max_rationale_chars=old_cfg.max_rationale_chars,
            max_list_items=old_cfg.max_list_items,
            response_format_json=old_cfg.response_format_json,
        )
    
    # --- Score ---
    card = brain.score(text=text, context=context)
    
    # --- Output ---
    if getattr(args, "quiet", False):
        print(json.dumps(card, ensure_ascii=False))
    else:
        print(json.dumps(card, ensure_ascii=False, indent=2))
    
    return 0


def _cmd_validate(json_file: str) -> int:
    """
    Validate a lead card JSON file against the schema.
    
    Supports multiple encodings (utf-8, utf-8-sig, utf-16) for Windows compatibility.
    
    Returns:
      0: Valid
      1: File error (not found, invalid JSON, encoding error)
      2: Invalid (schema validation failed)
    """
    try:
        obj: Dict[str, Any] = read_json_file(json_file)
    except FileReadError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: Could not read file: {e}", file=sys.stderr)
        return 1
    
    if not isinstance(obj, dict):
        print("ERROR: JSON file must contain an object", file=sys.stderr)
        return 1
    
    errors = validate_lead_card(obj)
    
    if errors:
        print("INVALID")
        for err in errors:
            print(f"  - {err}")
        return 2
    
    print("VALID")
    return 0


def _cmd_doctor() -> int:
    """
    Check system environment and dependencies.
    
    Checks:
      - Python version >= 3.10
      - Package imports work
      - Schema file exists
      - CWD is writable
      - OPENROUTER_API_KEY is set (shows yes/no, not the value)
    
    Returns:
      0: All checks pass
      1: Some checks failed
    """
    checks: List[tuple[str, bool, str]] = []
    
    # 1. Python version
    py_version = sys.version_info
    py_ok = py_version >= (3, 10)
    py_msg = f"Python {py_version.major}.{py_version.minor}.{py_version.micro}"
    if not py_ok:
        py_msg += " (requires >= 3.10)"
    checks.append(("Python version", py_ok, py_msg))
    
    # 2. Package imports
    imports_ok = True
    imports_msg = "All core modules"
    try:
        from . import brain, config, contracts, errors
        from .parsing import json_extractor, normalizer
        from .heuristics import tiering, next_step
        from .llm import openrouter_client, types
        from .prompt import builder
    except ImportError as e:
        imports_ok = False
        imports_msg = f"Import failed: {e}"
    checks.append(("Package imports", imports_ok, imports_msg))
    
    # 3. Schema file exists
    schema_path = Path(__file__).parent.parent.parent / "schemas" / "lead_card.v1.json"
    schema_ok = schema_path.exists()
    schema_msg = str(schema_path) if schema_ok else f"Not found: {schema_path}"
    checks.append(("Schema file", schema_ok, schema_msg))
    
    # 4. CWD writable
    cwd = Path.cwd()
    try:
        test_file = cwd / ".siw_brain_write_test"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()
        cwd_ok = True
        cwd_msg = str(cwd)
    except Exception:
        cwd_ok = True  # Non-critical, still OK
        cwd_msg = f"{cwd} (read-only, non-critical)"
    checks.append(("CWD writable", cwd_ok, cwd_msg))
    
    # 5. OPENROUTER_API_KEY
    api_key = os.getenv("OPENROUTER_API_KEY")
    key_ok = bool(api_key and api_key.strip())
    key_msg = "Set" if key_ok else "Not set (required for score command)"
    checks.append(("OPENROUTER_API_KEY", key_ok, key_msg))
    
    # Print results
    all_ok = True
    print("SIW Intent Brain - Doctor")
    print("=" * 50)
    
    for name, ok, msg in checks:
        status = "OK" if ok else "FAIL"
        # API key check is warning, not failure (doctor should still return 0)
        if name == "OPENROUTER_API_KEY" and not ok:
            status = "WARN"
        else:
            if not ok:
                all_ok = False
        print(f"[{status:4}] {name}: {msg}")
    
    print("=" * 50)
    
    if all_ok:
        print("All checks passed!")
        if not key_ok:
            print("\nNote: Set OPENROUTER_API_KEY to use the score command.")
        return 0
    else:
        print("\nSome checks failed. Please fix the issues above.")
        return 1


def _cmd_demo(args: argparse.Namespace) -> int:
    """
    Run offline demo with sample texts.
    
    Uses FakeClient - no API key required, no network requests.
    Outputs 3 sample LeadCards to stdout and validates each.
    All informational messages go to stderr.
    
    Returns:
      0: Success
      1: Error (should not happen)
    """
    # --- Enable logging if --verbose ---
    if getattr(args, "verbose", False):
        from .telemetry.logging import enable_logging
        enable_logging(True)
    
    from .config import BrainConfig
    from .brain import IntentBrain
    from .llm.types import ChatRequest, ChatResponse
    
    # Pre-defined responses for each sample (indexed by sample number)
    demo_responses = [
        # Sample 1: High intent
        {
            "scores": {"urgency": 0.7, "pain_point_intensity": 0.85, 
                       "commercial_relevance": 0.9, "solution_seeking": 0.95},
            "confidence": 0.92,
            "lead_tier": "S",
            "recommended_next_step": "offer_resource",
            "rationale": "Strong purchase intent with budget constraints. Actively seeking alternatives.",
            "extracted_signals": {
                "problem_summary": "User frustrated with high subscription cost",
                "constraints": ["budget", "monthly cost"],
                "budget_hints": ["$59/mo too expensive"],
                "tooling_stack": ["ToolX"],
                "keywords": ["alternative", "cheaper", "monitor", "subreddits"],
            },
            "safety_notes": ["Avoid aggressive sales pitch."],
        },
        # Sample 2: Low intent
        {
            "scores": {"urgency": 0.1, "pain_point_intensity": 0.05,
                       "commercial_relevance": 0.05, "solution_seeking": 0.1},
            "confidence": 0.88,
            "lead_tier": "D",
            "recommended_next_step": "ignore",
            "rationale": "General enthusiasm post. No commercial intent detected.",
            "extracted_signals": {
                "problem_summary": "Positive experience sharing",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": ["Rust"],
                "keywords": ["rust", "borrow checker"],
            },
            "safety_notes": [],
        },
        # Sample 3: Noise
        {
            "scores": {"urgency": 0.0, "pain_point_intensity": 0.0,
                       "commercial_relevance": 0.0, "solution_seeking": 0.0},
            "confidence": 0.15,
            "lead_tier": "D",
            "recommended_next_step": "monitor",
            "rationale": "Insufficient text to analyze intent.",
            "extracted_signals": {
                "problem_summary": "",
                "constraints": [],
                "budget_hints": [],
                "tooling_stack": [],
                "keywords": [],
            },
            "safety_notes": ["Text too short for reliable analysis."],
        },
    ]
    
    # Sample texts with different intent levels
    samples = [
        {
            "text": "ToolX is $59/mo and I'm sick of subscriptions. Any cheaper alternative that can monitor a few subreddits for mentions?",
            "context": {"subreddit": "SaaS", "title": "Cheaper alternative to ToolX?"},
            "description": "High intent - seeking alternatives with budget constraints",
            "response_idx": 0,
        },
        {
            "text": "Just discovered Rust and it's amazing! Anyone else enjoying the borrow checker?",
            "context": {"subreddit": "rust", "title": "Loving Rust"},
            "description": "Low intent - general discussion, no commercial signal",
            "response_idx": 1,
        },
        {
            "text": "help",
            "context": {"subreddit": "learnprogramming", "title": ""},
            "description": "Noise - too short/vague to analyze",
            "response_idx": 2,
        },
    ]
    
    # FakeClient that returns pre-defined responses based on sample index
    class DemoFakeClient:
        def __init__(self):
            self.call_count = 0
        
        def complete(self, req: ChatRequest) -> ChatResponse:
            # Use call count to determine which response to return
            idx = min(self.call_count, len(demo_responses) - 1)
            self.call_count += 1
            
            return ChatResponse(
                content=json.dumps(demo_responses[idx]),
                raw={},
                latency_ms=25,
                retries=0,
                status_code=200,
            )
    
    # Info messages go to stderr, only LeadCard JSON goes to stdout
    print("SIW Intent Brain - Offline Demo", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("Running with FakeClient (no API key required, no network)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(file=sys.stderr)
    
    # Create brain with fake client
    cfg = BrainConfig(api_key="demo-offline-key")
    brain = IntentBrain(cfg, client=DemoFakeClient())
    
    all_valid = True
    
    for i, sample in enumerate(samples, 1):
        print(f"Sample {i}: {sample['description']}", file=sys.stderr)
        print("-" * 60, file=sys.stderr)
        print(f"Text: {sample['text'][:80]}{'...' if len(sample['text']) > 80 else ''}", file=sys.stderr)
        print(file=sys.stderr)
        
        card = brain.score(text=sample["text"], context=sample["context"])
        # LeadCard JSON goes to stdout
        print(json.dumps(card, ensure_ascii=False, indent=2))
        
        # Validate
        errors = validate_lead_card(card)
        if errors:
            print(f"\nValidation: INVALID", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            all_valid = False
        else:
            print(f"\nValidation: VALID", file=sys.stderr)
        
        print(file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(file=sys.stderr)
    
    if all_valid:
        print("Demo completed successfully. All outputs are valid LeadCards.", file=sys.stderr)
        return 0
    else:
        print("Demo completed with validation errors.", file=sys.stderr)
        return 1


def _read_text_with_stdin(
    text_arg: Optional[str],
    file_arg: Optional[str],
) -> Optional[str]:
    """
    Read text from argument, file, or stdin.
    
    Priority:
      1. --text argument
      2. --text-file (supports utf-8, utf-8-sig, utf-16)
      3. stdin (if not a TTY)
    
    Returns:
      Text string on success.
      None if no input provided or file error.
    """
    if text_arg is not None:
        return text_arg
    
    if file_arg is not None:
        try:
            return read_text_file(file_arg)
        except FileReadError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"ERROR: Could not read text file: {e}", file=sys.stderr)
            return None
    
    # Try stdin if not a TTY
    if not sys.stdin.isatty():
        try:
            text = sys.stdin.read()
            if text and text.strip():
                return text
        except Exception:
            pass
    
    return None


def _read_context(
    json_arg: Optional[str],
    file_arg: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Read context from JSON string or file.
    
    File reading supports utf-8, utf-8-sig, utf-16 for Windows compatibility.
    
    Returns:
      Context dict on success (empty dict if neither provided).
      None on error (file not found, invalid JSON).
    """
    if json_arg is not None:
        try:
            ctx = json.loads(json_arg)
            if not isinstance(ctx, dict):
                print("ERROR: Context JSON must be an object", file=sys.stderr)
                return None
            return ctx
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid context JSON: {e}", file=sys.stderr)
            return None
    
    if file_arg is not None:
        try:
            ctx = read_json_file(file_arg)
            if not isinstance(ctx, dict):
                print("ERROR: Context file must contain a JSON object", file=sys.stderr)
                return None
            return ctx
        except FileReadError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"ERROR: Could not read context file: {e}", file=sys.stderr)
            return None
    
    # No context provided - return empty dict (valid)
    return {}


def _cmd_harvest(args: argparse.Namespace) -> int:
    """
    Execute harvest command.
    
    Fetches posts from Reddit and scores them.
    
    Output: JSONL to stdout (one JSON object per line)
    Progress: To stderr
    
    Returns:
      0: Success (may have fewer items than limit)
      1: Config/module error
    """
    # --- Enable logging if --verbose ---
    if getattr(args, "verbose", False):
        from .telemetry.logging import enable_logging
        enable_logging(True)
    
    # --- Get parameters ---
    subreddit = args.sub
    query = getattr(args, "query", None)
    limit = getattr(args, "limit", 10)
    sort = getattr(args, "sort", "new")
    
    # --- Initialize harvester ---
    harvester = _get_harvester()
    
    # --- Initialize brain ---
    try:
        brain = _get_brain(config_path=getattr(args, "config", None))
    except Exception as e:
        error_msg = str(e)
        if "api_key" in error_msg.lower() or "key" in error_msg.lower():
            print("ERROR: Configuration error (check OPENROUTER_API_KEY)", file=sys.stderr)
        else:
            print(f"ERROR: {error_msg}", file=sys.stderr)
        return 1
    
    # --- Harvest ---
    query_info = f" query='{query}'" if query else ""
    print(f"Fetching from r/{subreddit}{query_info}...", file=sys.stderr)
    
    result = harvester.fetch_posts(subreddit, query=query, limit=limit, sort=sort)
    
    # --- Check for errors ---
    if result.error_message:
        print(f"WARN: {result.error_message}", file=sys.stderr)
    
    # --- Score and output ---
    scored_count = 0
    
    for item in result.items:
        # Score
        card = brain.score(text=item["text"], context=item["context"])
        
        # Output (include source_meta)
        output = {
            "card": card,
            "source_meta": item.get("_meta", {}),
        }
        print(json.dumps(output, ensure_ascii=False))
        scored_count += 1
    
    # --- Summary ---
    print(
        f"Done: {scored_count} scored, {result.skipped_count} skipped (empty)",
        file=sys.stderr
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
