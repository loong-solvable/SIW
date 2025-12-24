#!/usr/bin/env python3
"""
SIW Intent Brain - Online Demo Script

This script demonstrates real LLM-powered intent scoring.
Requires OPENROUTER_API_KEY to be set.

Usage:
    python scripts/demo_score.py

Output:
    3 LeadCard JSON objects (stdout) with validation results.
"""

from __future__ import annotations

import json
import os
import sys
from rich import print_json


def main() -> int:
    """
    Run online demo with real OpenRouter API calls.
    
    Returns:
        0: All samples scored and validated successfully
        1: Missing API key or validation failure
    """
    # Check for API key first
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or not api_key.strip():
        print("=" * 60, file=sys.stderr)
        print("ERROR: OPENROUTER_API_KEY not set", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(file=sys.stderr)
        print("This demo requires a valid OpenRouter API key.", file=sys.stderr)
        print(file=sys.stderr)
        print("Set it using:", file=sys.stderr)
        print(file=sys.stderr)
        print("  Windows PowerShell:", file=sys.stderr)
        print('    $env:OPENROUTER_API_KEY = "sk-or-v1-your-key-here"', file=sys.stderr)
        print(file=sys.stderr)
        print("  Linux/macOS:", file=sys.stderr)
        print('    export OPENROUTER_API_KEY="sk-or-v1-your-key-here"', file=sys.stderr)
        print(file=sys.stderr)
        print("Then run this script again.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        return 1
    
    # Import after key check to avoid import errors on missing deps
    try:
        from siw_intent_brain import IntentBrain, validate_lead_card
    except ImportError as e:
        print(f"ERROR: Failed to import siw_intent_brain: {e}", file=sys.stderr)
        print("Make sure the package is installed: pip install -e .", file=sys.stderr)
        return 1
    
    # Sample texts with different intent levels
    samples = [
        {
            "name": "High Intent",
            "text": (
                "I've been using ToolX for 6 months now and it's $59/mo. "
                "Honestly, it's way too expensive for what I get. "
                "Looking for a cheaper alternative that can monitor a few subreddits "
                "for brand mentions. Budget is around $20-30/mo max. "
                "Anyone have recommendations?"
            ),
            "context": {
                "subreddit": "SaaS",
                "title": "Cheaper alternative to ToolX?",
                "author": "startup_founder",
            },
        },
        {
            "name": "Low Intent",
            "text": (
                "Just discovered Rust last week and I'm absolutely loving it! "
                "The borrow checker seemed scary at first but now I get it. "
                "Anyone else remember that 'aha' moment when ownership clicked?"
            ),
            "context": {
                "subreddit": "rust",
                "title": "Loving Rust!",
                "author": "new_rustacean",
            },
        },
        {
            "name": "Noise",
            "text": "lol same",
            "context": {
                "subreddit": "funny",
                "title": "",
                "author": "anon123",
            },
        },
    ]
    
    print("=" * 70, file=sys.stderr)
    print("SIW Intent Brain - Online Demo (Real API Calls)", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(file=sys.stderr)
    
    # Initialize brain
    try:
        brain = IntentBrain.from_env()
        print(f"Model: {brain.cfg.model}", file=sys.stderr)
        print(f"Timeout: {brain.cfg.timeout_s}s", file=sys.stderr)
        print(file=sys.stderr)
    except Exception as e:
        print(f"ERROR: Failed to initialize IntentBrain: {e}", file=sys.stderr)
        return 1
    
    all_valid = True
    
    for i, sample in enumerate(samples, 1):
        print("-" * 70, file=sys.stderr)
        print(f"Sample {i}/3: {sample['name']}", file=sys.stderr)
        print(f"Text: {sample['text'][:60]}...", file=sys.stderr)
        print(file=sys.stderr)
        
        try:
            # Score the text
            card = brain.score(text=sample["text"], context=sample["context"])
            
            # Output LeadCard JSON to stdout
            print_json(json.dumps(card, ensure_ascii=False, indent=2))
            
            # Validate and report
            errors = validate_lead_card(card)
            if errors:
                print(f"Validation: INVALID", file=sys.stderr)
                for err in errors:
                    print(f"  - {err}", file=sys.stderr)
                all_valid = False
            else:
                tier = card.get("lead_tier", "?")
                next_step = card.get("recommended_next_step", "?")
                confidence = card.get("confidence", 0)
                latency = card.get("meta", {}).get("latency_ms", 0)
                print(f"Validation: VALID", file=sys.stderr)
                print(f"  Tier: {tier} | Next: {next_step} | Confidence: {confidence:.2f} | Latency: {latency}ms", file=sys.stderr)
            
            print(file=sys.stderr)
            
        except Exception as e:
            print(f"ERROR scoring sample: {e}", file=sys.stderr)
            all_valid = False
    
    print("=" * 70, file=sys.stderr)
    
    if all_valid:
        print("Demo completed successfully. All 3 LeadCards are VALID.", file=sys.stderr)
        return 0
    else:
        print("Demo completed with some validation errors.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

