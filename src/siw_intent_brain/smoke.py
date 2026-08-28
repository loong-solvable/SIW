"""Safe production connectivity smoke for the configured SIW model."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .brain import IntentBrain


SmokeResult = dict[str, Any]


def run_smoke(
    brain_factory: Callable[[], IntentBrain] = IntentBrain.from_env,
) -> SmokeResult:
    """Run one tiny real inference and return only non-sensitive metadata."""
    try:
        card = brain_factory().score(
            "A customer is comparing two software tools and wants a demo.",
            {"source": "production_smoke"},
        )
        meta = card.get("meta", {})
        if not card.get("ok"):
            return {
                "ok": False,
                "error_code": meta.get("error_code") or "MODEL_SMOKE_FAILED",
            }

        return {
            "ok": True,
            "model": meta.get("model", ""),
            "provider": meta.get("provider", ""),
            "total_tokens": meta.get("total_tokens", 0),
            "reported_cost_usd_micros": meta.get(
                "reported_cost_usd_micros"
            ),
        }
    except Exception:
        # Configuration and upstream errors may contain URLs or credentials.
        return {"ok": False, "error_code": "MODEL_SMOKE_FAILED"}


def main() -> int:
    result = run_smoke()
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
