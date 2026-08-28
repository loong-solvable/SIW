from __future__ import annotations

import json

from siw_intent_brain.smoke import run_smoke


class FakeBrain:
    def __init__(self, card):
        self.card = card

    def score(self, text, context):
        assert "secret" not in text.lower()
        assert context == {"source": "production_smoke"}
        return self.card


def test_smoke_returns_only_safe_metadata() -> None:
    card = {
        "ok": True,
        "rationale": "secret provider output",
        "meta": {
            "model": "example/model",
            "provider": "compatible",
            "total_tokens": 15,
            "reported_cost_usd_micros": 9,
        },
    }

    result = run_smoke(lambda: FakeBrain(card))

    assert result == {
        "ok": True,
        "model": "example/model",
        "provider": "compatible",
        "total_tokens": 15,
        "reported_cost_usd_micros": 9,
    }
    assert "secret provider output" not in json.dumps(result)


def test_smoke_redacts_configuration_errors() -> None:
    def fail():
        raise RuntimeError("https://secret.invalid?token=top-secret")

    result = run_smoke(fail)

    assert result == {"ok": False, "error_code": "MODEL_SMOKE_FAILED"}
    assert "top-secret" not in json.dumps(result)
