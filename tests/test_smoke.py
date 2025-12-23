"""
Smoke test - verifies basic project structure is working.
This test should always pass if the project is properly installed.
"""

import pytest


def test_import_package():
    """Verify the main package can be imported."""
    import siw_intent_brain
    assert hasattr(siw_intent_brain, "__version__")
    assert siw_intent_brain.__version__ == "0.1.0"


def test_import_contracts():
    """Verify contracts module exports are available."""
    from siw_intent_brain import (
        LeadCard,
        Scores,
        SCHEMA_VERSION,
        build_lead_card,
        validate_lead_card,
    )
    assert SCHEMA_VERSION == "lead_card.v1"


def test_cli_import():
    """Verify CLI module can be imported."""
    from siw_intent_brain import cli
    assert hasattr(cli, "main")
    assert callable(cli.main)


def test_cli_help():
    """Verify CLI --help works without error."""
    from siw_intent_brain.cli import main
    # --help causes SystemExit with code 0
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_cli_version():
    """Verify CLI --version works."""
    from siw_intent_brain.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_cli_no_args():
    """Verify CLI with no args prints help and exits cleanly."""
    from siw_intent_brain.cli import main
    result = main([])
    assert result == 0


def test_cli_score_with_fake_brain():
    """Verify score command works with fake brain (offline)."""
    import json
    from siw_intent_brain.cli import main, set_brain_factory
    from siw_intent_brain import BrainConfig, validate_lead_card
    from siw_intent_brain.brain import IntentBrain
    from siw_intent_brain.llm.types import ChatRequest, ChatResponse
    
    class FakeClient:
        def complete(self, req: ChatRequest) -> ChatResponse:
            return ChatResponse(
                content=json.dumps({
                    "scores": {"urgency": 0.5, "pain_point_intensity": 0.5,
                               "commercial_relevance": 0.5, "solution_seeking": 0.5},
                    "confidence": 0.8,
                    "lead_tier": "B",
                    "recommended_next_step": "monitor",
                    "rationale": "Test",
                    "extracted_signals": {"problem_summary": "", "constraints": [],
                                          "budget_hints": [], "tooling_stack": [], "keywords": []},
                    "safety_notes": [],
                }),
                raw={},
                latency_ms=10,
                retries=0,
                status_code=200,
            )
    
    def fake_factory(config_path=None, **kwargs):
        cfg = BrainConfig(api_key="test-key")
        return IntentBrain(cfg, client=FakeClient())
    
    set_brain_factory(fake_factory)
    try:
        result = main(["score", "--text", "test"])
        assert result == 0
    finally:
        set_brain_factory(None)
