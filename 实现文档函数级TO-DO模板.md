
---

# 0) 统一约定（全项目强制）

* **所有对外返回**都必须符合 `schemas/lead_card.v1.json`
* **任何失败**必须走 `fail_closed` 输出（仍符合 schema）
* **不记录** API key / 原始全文（默认）
* **禁止**输出规避平台规则相关内容（system prompt 也要写死约束）

---

# 1) `pyproject.toml`（最小模板）

```toml
[project]
name = "siw-intent-brain"
version = "0.1.0"
description = "SIW Intent Brain - local-first decision support intent scoring engine"
requires-python = ">=3.10"
dependencies = [
  "requests>=2.31.0",
  "PyYAML>=6.0.1",
  "python-dotenv>=1.0.1"
]

[project.scripts]
siw-brain = "siw_intent_brain.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

---

# 2) `schemas/lead_card.v1.json`（占位 TODO）

> TODO：写完整 JSON Schema（见你前一版实现文档第 5 节字段要求）

---

# 3) `src/siw_intent_brain/__init__.py`

```python
"""
Public package exports.
"""

__all__ = ["IntentBrain", "BrainConfig", "LeadCard"]

from .brain import IntentBrain
from .config import BrainConfig
from .contracts import LeadCard
```

---

# 4) `src/siw_intent_brain/errors.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class SIWError(Exception):
    """Base error for SIW Intent Brain."""


class ConfigError(SIWError):
    """Configuration is missing or invalid."""


class UpstreamError(SIWError):
    """Upstream LLM provider error (HTTP, timeout, empty content)."""


class ParseError(SIWError):
    """Could not parse/interpret model output as JSON."""


class ContractError(SIWError):
    """Output violates lead-card contract/schema."""


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    detail: str
    retryable: bool = False
    http_status: Optional[int] = None


# Error codes (must match README + meta.error_code)
E_CONFIG_MISSING_KEY = "E_CONFIG_MISSING_KEY"
E_UPSTREAM_HTTP = "E_UPSTREAM_HTTP"
E_UPSTREAM_TIMEOUT = "E_UPSTREAM_TIMEOUT"
E_UPSTREAM_EMPTY_CONTENT = "E_UPSTREAM_EMPTY_CONTENT"
E_PARSE_JSON = "E_PARSE_JSON"
E_CONTRACT_INVALID = "E_CONTRACT_INVALID"
```

---

# 5) `src/siw_intent_brain/contracts.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, TypedDict

SchemaVersion = Literal["lead_card.v1"]

LeadTier = Literal["S", "A", "B", "C", "D"]
RecommendedNextStep = Literal["ignore", "monitor", "draft_reply", "ask_question", "offer_resource"]
ParserMode = Literal["strict", "extracted", "fail_closed"]

class Scores(TypedDict):
    urgency: float
    pain_point_intensity: float
    commercial_relevance: float
    solution_seeking: float

class ExtractedSignals(TypedDict):
    problem_summary: str
    constraints: List[str]
    budget_hints: List[str]
    tooling_stack: List[str]
    keywords: List[str]

class Meta(TypedDict, total=False):
    model: str
    provider: str
    latency_ms: int
    retries: int
    parser_mode: ParserMode
    schema_version: SchemaVersion
    error_code: str
    error_detail: str
    validation_error: bool

class LeadCard(TypedDict):
    ok: bool
    scores: Scores
    confidence: float
    lead_tier: LeadTier
    recommended_next_step: RecommendedNextStep
    rationale: str
    extracted_signals: ExtractedSignals
    safety_notes: List[str]
    meta: Meta


# Enums for runtime checks
LEAD_TIERS = {"S", "A", "B", "C", "D"}
NEXT_STEPS = {"ignore", "monitor", "draft_reply", "ask_question", "offer_resource"}
PARSER_MODES = {"strict", "extracted", "fail_closed"}
SCHEMA_VERSION: SchemaVersion = "lead_card.v1"


def default_scores() -> Scores:
    """TODO: return zero scores dict."""
    return {
        "urgency": 0.0,
        "pain_point_intensity": 0.0,
        "commercial_relevance": 0.0,
        "solution_seeking": 0.0,
    }


def default_extracted_signals() -> ExtractedSignals:
    """TODO: return empty extracted_signals."""
    return {
        "problem_summary": "",
        "constraints": [],
        "budget_hints": [],
        "tooling_stack": [],
        "keywords": [],
    }


def build_lead_card(
    ok: bool,
    scores: Scores,
    confidence: float,
    lead_tier: LeadTier,
    recommended_next_step: RecommendedNextStep,
    rationale: str,
    extracted_signals: ExtractedSignals,
    safety_notes: List[str],
    meta: Optional[Meta] = None,
) -> LeadCard:
    """
    TODO: construct LeadCard with required meta defaults:
      - provider="openrouter"
      - parser_mode present
      - schema_version fixed
    """
    meta_out: Meta = meta or {}
    meta_out.setdefault("provider", "openrouter")
    meta_out.setdefault("schema_version", SCHEMA_VERSION)
    meta_out.setdefault("latency_ms", 0)
    meta_out.setdefault("retries", 0)
    meta_out.setdefault("parser_mode", "strict")
    return {
        "ok": ok,
        "scores": scores,
        "confidence": confidence,
        "lead_tier": lead_tier,
        "recommended_next_step": recommended_next_step,
        "rationale": rationale,
        "extracted_signals": extracted_signals,
        "safety_notes": safety_notes,
        "meta": meta_out,
    }


def validate_lead_card(obj: Dict[str, Any]) -> List[str]:
    """
    Lightweight validator (do NOT require network).
    Return list of error strings; empty means valid.
    TODO:
      - check required keys
      - check enums
      - check ranges [0,1] for floats
      - check types (lists/strings)
      - check meta.schema_version
    """
    errors: List[str] = []
    # TODO implement
    return errors
```

---

# 6) `src/siw_intent_brain/config.py`

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .errors import ConfigError, E_CONFIG_MISSING_KEY

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


@dataclass(frozen=True)
class BrainConfig:
    # OpenRouter
    api_key: str
    model: str = "openai/gpt-4o-mini"
    base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    timeout_s: int = 30
    max_retries: int = 3
    backoff_s: float = 1.2
    http_referer: Optional[str] = None
    x_title: Optional[str] = None

    # Brain behavior
    min_confidence: float = 0.35
    max_rationale_chars: int = 400
    max_list_items: int = 50
    response_format_json: bool = True  # allow disabling if model doesn't support


def _load_yaml(path: str) -> Dict[str, Any]:
    """TODO: load YAML into dict with safe_load; raise ConfigError if missing/unreadable."""
    if yaml is None:
        raise ConfigError("pyyaml not installed but YAML config requested.")
    # TODO implement
    return {}


def load_config(config_path: Optional[str] = None) -> BrainConfig:
    """
    TODO:
      - read env vars first
      - optionally read YAML for fallbacks
      - validate api_key exists -> else raise ConfigError(E_CONFIG_MISSING_KEY)
    """
    data: Dict[str, Any] = {}
    if config_path:
        data = _load_yaml(config_path)

    api_key = os.getenv("OPENROUTER_API_KEY") or (data.get("openrouter", {}) or {}).get("api_key")
    if not api_key:
        raise ConfigError(f"{E_CONFIG_MISSING_KEY}: OPENROUTER_API_KEY is required")

    # TODO: read other fields w/ env overrides and defaults
    return BrainConfig(api_key=str(api_key))
```

---

# 7) `src/siw_intent_brain/telemetry/logging.py`

```python
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional


def get_logger(name: str = "siw_intent_brain", level: str = "INFO") -> logging.Logger:
    """
    TODO:
      - configure logger with StreamHandler
      - formatter outputs JSON lines (one event per line)
      - avoid duplicate handlers
    """
    logger = logging.getLogger(name)
    # TODO implement idempotent setup
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


def log_event(logger: logging.Logger, event: str, fields: Optional[Dict[str, Any]] = None) -> None:
    """
    Structured event logging.
    Must NOT log API key or full input text.
    TODO: implement safe JSON serialization.
    """
    payload = {"event": event, **(fields or {})}
    logger.info(json.dumps(payload, ensure_ascii=False))
```

---

# 8) `src/siw_intent_brain/telemetry/metrics.py`

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Metrics:
    total_requests: int = 0
    total_fail_closed: int = 0
    upstream_retries_total: int = 0
    total_latency_ms: int = 0

    def record(self, latency_ms: int, retries: int, fail_closed: bool) -> None:
        """TODO: increment counters and totals."""
        self.total_requests += 1
        self.total_latency_ms += max(0, int(latency_ms))
        self.upstream_retries_total += max(0, int(retries))
        if fail_closed:
            self.total_fail_closed += 1

    def avg_latency_ms(self) -> float:
        """TODO: compute average; 0 if no requests."""
        return (self.total_latency_ms / self.total_requests) if self.total_requests else 0.0
```

---

# 9) `src/siw_intent_brain/llm/types.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user"
    content: str


@dataclass(frozen=True)
class ChatRequest:
    model: str
    messages: List[ChatMessage]
    temperature: float = 0.2
    max_tokens: int = 600
    response_format: Optional[Dict[str, Any]] = None  # {"type":"json_object"} or None


@dataclass(frozen=True)
class ChatResponse:
    content: str
    raw: Dict[str, Any]
    latency_ms: int
    retries: int
    status_code: int
```

---

# 10) `src/siw_intent_brain/llm/openrouter_client.py`

```python
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import requests

from ..config import BrainConfig
from ..errors import UpstreamError, E_UPSTREAM_HTTP, E_UPSTREAM_TIMEOUT, E_UPSTREAM_EMPTY_CONTENT
from .types import ChatRequest, ChatResponse


class OpenRouterClient:
    """
    OpenRouter chat completions client.
    Must support retries and return ChatResponse with latency/retries.
    """

    def __init__(self, cfg: BrainConfig):
        self.cfg = cfg

    def complete(self, req: ChatRequest) -> ChatResponse:
        """
        TODO:
          - build headers (auth + content-type + optional referer/title)
          - POST to cfg.base_url
          - retry on timeout / transient HTTP
          - parse JSON response
          - extract choices[0].message.content
          - if empty -> raise UpstreamError(E_UPSTREAM_EMPTY_CONTENT)
          - return ChatResponse(content, raw, latency_ms, retries, status_code)
        """
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }
        if self.cfg.http_referer:
            headers["HTTP-Referer"] = self.cfg.http_referer
        if self.cfg.x_title:
            headers["X-Title"] = self.cfg.x_title

        payload: Dict[str, Any] = {
            "model": req.model,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        }
        if req.response_format is not None:
            payload["response_format"] = req.response_format

        start = time.time()
        retries = 0
        last_status = 0
        last_err: Optional[Exception] = None

        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                resp = requests.post(
                    self.cfg.base_url,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=self.cfg.timeout_s,
                )
                last_status = resp.status_code
                if resp.status_code >= 400:
                    # TODO: decide retryable status codes (e.g., 429/500/502/503)
                    raise UpstreamError(f"{E_UPSTREAM_HTTP}: HTTP {resp.status_code} {resp.text[:300]}")

                raw = resp.json()
                # TODO: validate shape exists choices[0].message.content
                content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content or not str(content).strip():
                    raise UpstreamError(f"{E_UPSTREAM_EMPTY_CONTENT}: empty content")

                latency_ms = int((time.time() - start) * 1000)
                return ChatResponse(
                    content=str(content),
                    raw=raw,
                    latency_ms=latency_ms,
                    retries=retries,
                    status_code=resp.status_code,
                )

            except requests.Timeout as e:
                last_err = e
                if attempt < self.cfg.max_retries:
                    retries += 1
                    time.sleep(self.cfg.backoff_s * attempt)
                    continue
                raise UpstreamError(f"{E_UPSTREAM_TIMEOUT}: {e}") from e

            except UpstreamError as e:
                last_err = e
                if attempt < self.cfg.max_retries:
                    retries += 1
                    time.sleep(self.cfg.backoff_s * attempt)
                    continue
                raise

            except Exception as e:
                last_err = e
                if attempt < self.cfg.max_retries:
                    retries += 1
                    time.sleep(self.cfg.backoff_s * attempt)
                    continue
                raise UpstreamError(f"{E_UPSTREAM_HTTP}: {e}") from e

        raise UpstreamError(f"{E_UPSTREAM_HTTP}: failed after retries: {last_err}")
```

---

# 11) `src/siw_intent_brain/prompt/system.txt`

> TODO：写 system prompt（必须包含 strict JSON only、禁止规避/自动化发布指导、rationale<=2句、scores 0..1）

示例骨架（工程师自行精炼）：

```
You are an intent-scoring engine for a local-first decision support system.
Output STRICT JSON ONLY (no markdown, no prose).
Do not provide instructions for bypassing platform rules, evading detection, or automating posting.
All scores must be numbers between 0 and 1.
Rationale must be <= 2 sentences.
```

---

# 12) `src/siw_intent_brain/prompt/builder.py`

```python
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ..config import BrainConfig
from ..llm.types import ChatMessage, ChatRequest


def build_chat_request(cfg: BrainConfig, text: str, context: Optional[Dict[str, Any]]) -> ChatRequest:
    """
    TODO:
      - load system prompt from system.txt
      - build user JSON payload:
          {
            "task": "...",
            "context": {...},
            "text": "...",
            "output_schema": {...}
          }
      - set response_format={"type":"json_object"} if cfg.response_format_json
      - return ChatRequest(model=cfg.model, messages=[system,user], ...)
    """
    ctx = context or {}
    system_prompt = _load_system_prompt()

    user_obj = {
        "task": "Score intent and extract signals. Return JSON only.",
        "context": {
            "subreddit": str(ctx.get("subreddit", "")),
            "title": str(ctx.get("title", "")),
            "author": str(ctx.get("author", "")),
            "permalink": str(ctx.get("permalink", "")),
        },
        "text": text,
        "output_schema": {
            "scores": {
                "urgency": "float 0..1",
                "pain_point_intensity": "float 0..1",
                "commercial_relevance": "float 0..1",
                "solution_seeking": "float 0..1"
            },
            "confidence": "float 0..1",
            "lead_tier": "S|A|B|C|D",
            "recommended_next_step": "ignore|monitor|draft_reply|ask_question|offer_resource",
            "rationale": "string <= 2 sentences",
            "extracted_signals": {
                "problem_summary": "string",
                "constraints": "list[string]",
                "budget_hints": "list[string]",
                "tooling_stack": "list[string]",
                "keywords": "list[string]"
            },
            "safety_notes": "list[string] (etiquette/spam-risk reminders only)"
        }
    }

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=json.dumps(user_obj, ensure_ascii=False)),
    ]

    response_format = {"type": "json_object"} if cfg.response_format_json else None
    return ChatRequest(
        model=cfg.model,
        messages=messages,
        temperature=0.2,
        max_tokens=600,
        response_format=response_format,
    )


def _load_system_prompt() -> str:
    """
    TODO:
      - read system.txt adjacent to this file (package data)
      - ensure packaging includes it (pyproject include-package-data)
    """
    # TODO implement robust file loading
    return "TODO: load from system.txt"
```

---

# 13) `src/siw_intent_brain/parsing/json_extractor.py`

```python
from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from ..errors import ParseError, E_PARSE_JSON


def extract_json_object(text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Returns (parser_mode, obj)
    parser_mode: "strict" | "extracted"
    TODO:
      - try json.loads(text)
      - else find first '{' and last '}' and try json.loads(substring)
      - if fail raise ParseError(E_PARSE_JSON)
    """
    s = (text or "").strip()
    try:
        obj = json.loads(s)
        if not isinstance(obj, dict):
            raise ValueError("JSON root must be object")
        return "strict", obj
    except Exception:
        pass

    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        cand = s[start:end + 1]
        try:
            obj = json.loads(cand)
            if not isinstance(obj, dict):
                raise ValueError("JSON root must be object")
            return "extracted", obj
        except Exception as e:
            raise ParseError(f"{E_PARSE_JSON}: extracted parse failed: {e}") from e

    raise ParseError(f"{E_PARSE_JSON}: no JSON object found")
```

---

# 14) `src/siw_intent_brain/parsing/normalizer.py`

```python
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..contracts import LEAD_TIERS, NEXT_STEPS, Scores, ExtractedSignals, default_scores, default_extracted_signals


def clamp01(v: Any) -> float:
    """TODO: convert to float; clamp to [0,1]; on failure return 0.0"""
    try:
        x = float(v)
    except Exception:
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def clean_str(v: Any, max_len: int) -> str:
    """TODO: convert to str, strip, truncate."""
    s = str(v or "").strip()
    return s[:max_len] if len(s) > max_len else s


def clean_list_str(v: Any, max_items: int) -> List[str]:
    """TODO: ensure list[str], filter empties, truncate."""
    if not isinstance(v, list):
        return []
    out: List[str] = []
    for item in v:
        s = str(item or "").strip()
        if s:
            out.append(s)
        if len(out) >= max_items:
            break
    return out


def normalize_model_output(
    obj: Dict[str, Any],
    max_rationale_chars: int,
    max_list_items: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Normalize fields into a partially-valid structure.
    Returns (normalized, flags)
      flags can include:
        - tier_valid: bool
        - next_step_valid: bool
    TODO:
      - scores dict clamp
      - confidence clamp
      - lead_tier keep only if valid enum else set to ""
      - recommended_next_step keep only if valid enum else set to ""
      - rationale truncate
      - extracted_signals normalize + lists
      - safety_notes normalize
    """
    flags = {"tier_valid": True, "next_step_valid": True}

    scores_in = obj.get("scores", {})
    if not isinstance(scores_in, dict):
        scores_in = {}

    scores: Scores = default_scores()
    scores["urgency"] = clamp01(scores_in.get("urgency", 0.0))
    scores["pain_point_intensity"] = clamp01(scores_in.get("pain_point_intensity", 0.0))
    scores["commercial_relevance"] = clamp01(scores_in.get("commercial_relevance", 0.0))
    scores["solution_seeking"] = clamp01(scores_in.get("solution_seeking", 0.0))

    confidence = clamp01(obj.get("confidence", 0.0))

    lead_tier = str(obj.get("lead_tier", "") or "").strip().upper()
    if lead_tier not in LEAD_TIERS:
        flags["tier_valid"] = False
        lead_tier = ""

    next_step = str(obj.get("recommended_next_step", "") or "").strip()
    if next_step not in NEXT_STEPS:
        flags["next_step_valid"] = False
        next_step = ""

    rationale = clean_str(obj.get("rationale", ""), max_rationale_chars) or "No rationale provided."

    extracted_in = obj.get("extracted_signals", {})
    if not isinstance(extracted_in, dict):
        extracted_in = {}

    extracted: ExtractedSignals = default_extracted_signals()
    extracted["problem_summary"] = clean_str(extracted_in.get("problem_summary", ""), 200)
    extracted["constraints"] = clean_list_str(extracted_in.get("constraints", []), max_list_items)
    extracted["budget_hints"] = clean_list_str(extracted_in.get("budget_hints", []), max_list_items)
    extracted["tooling_stack"] = clean_list_str(extracted_in.get("tooling_stack", []), max_list_items)
    extracted["keywords"] = clean_list_str(extracted_in.get("keywords", []), max_list_items)

    safety_notes = clean_list_str(obj.get("safety_notes", []), max_list_items)

    normalized = {
        "scores": scores,
        "confidence": confidence,
        "lead_tier": lead_tier,
        "recommended_next_step": next_step,
        "rationale": rationale,
        "extracted_signals": extracted,
        "safety_notes": safety_notes,
    }
    return normalized, flags
```

---

# 15) `src/siw_intent_brain/heuristics/tiering.py`

```python
from __future__ import annotations

from ..contracts import LeadTier


def compute_lead_tier(
    urgency: float,
    pain: float,
    commercial: float,
    seeking: float,
    confidence: float,
) -> LeadTier:
    """
    Fixed heuristic formula.
    TODO: implement:
      base = 0.25*U + 0.30*P + 0.30*C + 0.15*S
      score = base*(0.5+0.5*conf)
      thresholds -> S/A/B/C/D
    """
    base = 0.25 * urgency + 0.30 * pain + 0.30 * commercial + 0.15 * seeking
    score = base * (0.5 + 0.5 * confidence)

    if score >= 0.78:
        return "S"
    if score >= 0.62:
        return "A"
    if score >= 0.46:
        return "B"
    if score >= 0.30:
        return "C"
    return "D"
```

---

# 16) `src/siw_intent_brain/heuristics/next_step.py`

```python
from __future__ import annotations

from ..contracts import RecommendedNextStep


def compute_next_step(
    pain: float,
    commercial: float,
    seeking: float,
    confidence: float,
) -> RecommendedNextStep:
    """
    Fixed heuristic logic.
    TODO: implement exact thresholds.
    """
    if confidence < 0.35:
        return "monitor"

    composite = (commercial + seeking + pain) / 3.0
    if composite < 0.18:
        return "ignore"
    if commercial >= 0.6 and seeking >= 0.55:
        return "offer_resource"
    if pain >= 0.6 and seeking >= 0.5:
        return "ask_question"
    if composite >= 0.45:
        return "draft_reply"
    return "monitor"
```

---

# 17) `src/siw_intent_brain/brain.py`（主入口 TODO 模板）

```python
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .config import BrainConfig, load_config
from .contracts import (
    LeadCard,
    build_lead_card,
    default_scores,
    default_extracted_signals,
    validate_lead_card,
    SCHEMA_VERSION,
)
from .errors import (
    ConfigError,
    UpstreamError,
    ParseError,
    ContractError,
    E_UPSTREAM_HTTP,
    E_UPSTREAM_TIMEOUT,
    E_UPSTREAM_EMPTY_CONTENT,
    E_PARSE_JSON,
    E_CONTRACT_INVALID,
)
from .heuristics.tiering import compute_lead_tier
from .heuristics.next_step import compute_next_step
from .llm.openrouter_client import OpenRouterClient
from .parsing.json_extractor import extract_json_object
from .parsing.normalizer import normalize_model_output
from .prompt.builder import build_chat_request
from .telemetry.logging import get_logger, log_event
from .telemetry.metrics import Metrics


class IntentBrain:
    """
    Public API: score(text, context) -> LeadCard
    """

    def __init__(self, cfg: BrainConfig, client: Optional[OpenRouterClient] = None):
        self.cfg = cfg
        self.client = client or OpenRouterClient(cfg)
        self.logger = get_logger()
        self.metrics = Metrics()

    @classmethod
    def from_env(cls, config_path: Optional[str] = None) -> "IntentBrain":
        """TODO: load config from env/yaml; create brain."""
        cfg = load_config(config_path)
        return cls(cfg)

    def score(self, text: str, context: Optional[Dict[str, Any]] = None) -> LeadCard:
        """
        Main scoring method.
        Must never throw uncaught exception to caller.
        Must return LeadCard always (valid schema).
        """
        t0 = time.time()
        ctx = context or {}

        # 1) Empty input short-circuit
        if not text or not str(text).strip():
            return self._ok_low_signal("Empty text input.", t0, parser_mode="fail_closed")

        log_event(self.logger, "score_start", {"model": self.cfg.model})

        # 2) Build request
        try:
            req = build_chat_request(self.cfg, text=text, context=ctx)
        except Exception as e:
            return self._fail_closed(f"Prompt build failed: {e}", t0, error_code=E_CONTRACT_INVALID)

        # 3) Call upstream
        try:
            resp = self.client.complete(req)
        except UpstreamError as e:
            # TODO: map to error_code based on message contains E_UPSTREAM_*
            return self._fail_closed(str(e), t0, error_code=E_UPSTREAM_HTTP)
        except Exception as e:
            return self._fail_closed(f"Unexpected upstream error: {e}", t0, error_code=E_UPSTREAM_HTTP)

        # 4) Parse JSON
        try:
            parser_mode, obj = extract_json_object(resp.content)
        except ParseError as e:
            return self._fail_closed(str(e), t0, error_code=E_PARSE_JSON, upstream=resp, parser_mode="fail_closed")

        # 5) Normalize
        normalized, flags = normalize_model_output(
            obj=obj,
            max_rationale_chars=self.cfg.max_rationale_chars,
            max_list_items=self.cfg.max_list_items,
        )

        scores = normalized["scores"]
        confidence = normalized["confidence"]

        # 6) Heuristic fill
        lead_tier = normalized["lead_tier"]
        if not flags.get("tier_valid", True):
            lead_tier = compute_lead_tier(
                urgency=scores["urgency"],
                pain=scores["pain_point_intensity"],
                commercial=scores["commercial_relevance"],
                seeking=scores["solution_seeking"],
                confidence=confidence,
            )

        next_step = normalized["recommended_next_step"]
        if not flags.get("next_step_valid", True):
            next_step = compute_next_step(
                pain=scores["pain_point_intensity"],
                commercial=scores["commercial_relevance"],
                seeking=scores["solution_seeking"],
                confidence=confidence,
            )

        # 7) Fail-closed (soft)
        safety_notes = list(normalized["safety_notes"])
        if confidence < self.cfg.min_confidence:
            lead_tier = "D"
            if next_step not in ("ignore", "monitor"):
                next_step = "monitor"
            safety_notes.append("Low confidence: conservative fallback applied.")

        # 8) Build LeadCard
        latency_ms = int((time.time() - t0) * 1000)
        meta = {
            "model": self.cfg.model,
            "provider": "openrouter",
            "latency_ms": latency_ms,
            "retries": resp.retries,
            "parser_mode": parser_mode,
            "schema_version": SCHEMA_VERSION,
        }

        card = build_lead_card(
            ok=True,
            scores=scores,
            confidence=confidence,
            lead_tier=lead_tier,  # type: ignore
            recommended_next_step=next_step,  # type: ignore
            rationale=normalized["rationale"],
            extracted_signals=normalized["extracted_signals"],
            safety_notes=safety_notes,
            meta=meta,
        )

        # 9) Validate contract
        errs = validate_lead_card(card)
        if errs:
            return self._fail_closed(
                reason="Contract validation failed: " + "; ".join(errs),
                t0=t0,
                error_code=E_CONTRACT_INVALID,
                upstream=resp,
                parser_mode="fail_closed",
            )

        # Telemetry
        self.metrics.record(latency_ms=latency_ms, retries=resp.retries, fail_closed=False)
        log_event(self.logger, "score_end", {"ok": True, "latency_ms": latency_ms, "retries": resp.retries, "parser_mode": parser_mode})
        return card

    # -------------------------
    # Helpers
    # -------------------------

    def _ok_low_signal(self, reason: str, t0: float, parser_mode: str) -> LeadCard:
        """TODO: return ok=true but weak signal (tier D, monitor) with meta."""
        latency_ms = int((time.time() - t0) * 1000)
        meta = {
            "model": self.cfg.model,
            "provider": "openrouter",
            "latency_ms": latency_ms,
            "retries": 0,
            "parser_mode": parser_mode,
            "schema_version": SCHEMA_VERSION,
        }
        card = build_lead_card(
            ok=True,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale=reason,
            extracted_signals=default_extracted_signals(),
            safety_notes=["Low signal input."],
            meta=meta,
        )
        return card

    def _fail_closed(
        self,
        reason: str,
        t0: float,
        error_code: str,
        upstream: Optional[Any] = None,
        parser_mode: str = "fail_closed",
    ) -> LeadCard:
        """
        TODO:
          - build ok=false fail-closed card (tier D, monitor)
          - include error_code + truncated error_detail in meta
          - record metrics/log_event
        """
        latency_ms = int((time.time() - t0) * 1000)
        meta = {
            "model": self.cfg.model,
            "provider": "openrouter",
            "latency_ms": latency_ms,
            "retries": getattr(upstream, "retries", 0) if upstream else 0,
            "parser_mode": parser_mode,
            "schema_version": SCHEMA_VERSION,
            "error_code": error_code,
            "error_detail": (reason[:280] + "...") if len(reason) > 280 else reason,
        }
        card = build_lead_card(
            ok=False,
            scores=default_scores(),
            confidence=0.0,
            lead_tier="D",
            recommended_next_step="monitor",
            rationale="Fail-closed: " + meta["error_detail"],
            extracted_signals=default_extracted_signals(),
            safety_notes=["Fail-closed: conservative output."],
            meta=meta,
        )
        self.metrics.record(latency_ms=latency_ms, retries=meta["retries"], fail_closed=True)
        log_event(self.logger, "fail_closed", {"ok": False, "error_code": error_code, "latency_ms": latency_ms, "retries": meta["retries"]})
        return card
```

---

# 18) `src/siw_intent_brain/cli.py`（CLI TODO 模板）

```python
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional

from .brain import IntentBrain
from .contracts import validate_lead_card


def main(argv: Optional[list[str]] = None) -> int:
    """
    Commands:
      - score: call IntentBrain.score
      - validate: validate a lead card JSON file
    TODO:
      - implement argparse with subcommands
      - support --text / --text-file
      - support --context-json / --context-file
      - output pretty JSON
    """
    parser = argparse.ArgumentParser(prog="siw-brain")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_score = sub.add_parser("score")
    p_score.add_argument("--text", default=None)
    p_score.add_argument("--text-file", default=None)
    p_score.add_argument("--context-json", default=None)
    p_score.add_argument("--context-file", default=None)
    p_score.add_argument("--config", default=None)
    p_score.add_argument("--quiet", action="store_true")

    p_val = sub.add_parser("validate")
    p_val.add_argument("--json-file", required=True)

    args = parser.parse_args(argv)

    if args.cmd == "score":
        text = _read_text(args.text, args.text_file)
        ctx = _read_context(args.context_json, args.context_file)
        brain = IntentBrain.from_env(args.config)
        card = brain.score(text=text, context=ctx)

        if args.quiet:
            print(json.dumps(card, ensure_ascii=False))
        else:
            print(json.dumps(card, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "validate":
        with open(args.json_file, "r", encoding="utf-8") as f:
            obj = json.load(f)
        errs = validate_lead_card(obj)
        if errs:
            print("INVALID:")
            for e in errs:
                print(" -", e)
            return 2
        print("VALID")
        return 0

    return 1


def _read_text(text_arg: Optional[str], file_arg: Optional[str]) -> str:
    """TODO: read text from arg or file; error if both missing."""
    if text_arg:
        return text_arg
    if file_arg:
        with open(file_arg, "r", encoding="utf-8") as f:
            return f.read()
    raise SystemExit("Must provide --text or --text-file")


def _read_context(ctx_json: Optional[str], ctx_file: Optional[str]) -> Dict[str, Any]:
    """TODO: parse JSON from string or file; default {}."""
    if ctx_json:
        return json.loads(ctx_json)
    if ctx_file:
        with open(ctx_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
```

---

# 19) `scripts/demo_score.py`（演示 TODO 模板）

```python
from __future__ import annotations

import json

from siw_intent_brain.brain import IntentBrain


def main() -> None:
    brain = IntentBrain.from_env(None)

    samples = [
        ("ToolX is $59/mo and I'm sick of subscriptions. Any cheaper alternative that monitors a few subreddits?",
         {"subreddit": "someSub", "title": "Cheaper alternative?", "author": "u1", "permalink": "https://..."}),
        ("What do you think about the latest Rust release?", {"subreddit": "rust", "title": "Rust", "author": "u2"}),
        ("help", {"subreddit": "learnprogramming", "title": "", "author": "u3"}),
    ]

    for text, ctx in samples:
        card = brain.score(text=text, context=ctx)
        print(json.dumps(card, ensure_ascii=False, indent=2))
        print("-" * 60)


if __name__ == "__main__":
    main()
```

---

# 20) 测试文件 TODO 模板

## 20.1 `tests/test_json_extractor.py`

```python
import pytest
from siw_intent_brain.parsing.json_extractor import extract_json_object
from siw_intent_brain.errors import ParseError

def test_strict_json():
    mode, obj = extract_json_object('{"a":1}')
    assert mode == "strict"
    assert obj["a"] == 1

def test_extracted_json():
    mode, obj = extract_json_object('prefix {"a":1} suffix')
    assert mode == "extracted"
    assert obj["a"] == 1

def test_fail():
    with pytest.raises(ParseError):
        extract_json_object("no braces here")
```

## 20.2 `tests/test_normalizer.py`

```python
from siw_intent_brain.parsing.normalizer import normalize_model_output

def test_normalize_clamp_and_lists():
    raw = {
        "scores": {"urgency": 2, "pain_point_intensity": -1, "commercial_relevance": "0.5", "solution_seeking": None},
        "confidence": "1.2",
        "lead_tier": "Z",
        "recommended_next_step": "???",
        "rationale": "x" * 999,
        "extracted_signals": {"constraints": ["", "  ok  ", None], "keywords": "not-a-list"},
        "safety_notes": ["", "be polite"]
    }
    norm, flags = normalize_model_output(raw, max_rationale_chars=400, max_list_items=50)
    assert norm["scores"]["urgency"] == 1.0
    assert norm["scores"]["pain_point_intensity"] == 0.0
    assert norm["scores"]["commercial_relevance"] == 0.5
    assert norm["confidence"] == 1.0
    assert flags["tier_valid"] is False
    assert flags["next_step_valid"] is False
    assert len(norm["rationale"]) == 400
    assert norm["extracted_signals"]["constraints"] == ["ok"]
    assert norm["extracted_signals"]["keywords"] == []
    assert norm["safety_notes"] == ["be polite"]
```

## 20.3 `tests/test_heuristics_tiering.py`

```python
from siw_intent_brain.heuristics.tiering import compute_lead_tier

def test_tiering_thresholds():
    # TODO: craft U,P,C,S,conf that hit exact thresholds
    assert compute_lead_tier(1,1,1,1,1) == "S"
```

## 20.4 `tests/test_heuristics_next_step.py`

```python
from siw_intent_brain.heuristics.next_step import compute_next_step

def test_next_step_low_conf():
    assert compute_next_step(pain=1, commercial=1, seeking=1, confidence=0.2) == "monitor"

def test_next_step_offer_resource():
    assert compute_next_step(pain=0.2, commercial=0.7, seeking=0.6, confidence=0.9) == "offer_resource"
```

## 20.5 `tests/test_contracts.py`

```python
from siw_intent_brain.contracts import build_lead_card, default_scores, default_extracted_signals, validate_lead_card

def test_contract_valid_default():
    card = build_lead_card(
        ok=True,
        scores=default_scores(),
        confidence=0.0,
        lead_tier="D",
        recommended_next_step="monitor",
        rationale="ok",
        extracted_signals=default_extracted_signals(),
        safety_notes=[],
        meta={"model":"m","parser_mode":"strict"}
    )
    errs = validate_lead_card(card)
    assert errs == []
```

## 20.6 `tests/test_brain_offline.py`（FakeClient）

```python
import json
from siw_intent_brain.brain import IntentBrain
from siw_intent_brain.config import BrainConfig
from siw_intent_brain.llm.types import ChatResponse

class FakeClient:
    def complete(self, req):
        obj = {
            "scores": {"urgency": 0.8, "pain_point_intensity": 0.9, "commercial_relevance": 0.7, "solution_seeking": 0.95},
            "confidence": 0.9,
            "lead_tier": "S",
            "recommended_next_step": "offer_resource",
            "rationale": "Test rationale.",
            "extracted_signals": {"problem_summary":"x","constraints":[],"budget_hints":[],"tooling_stack":[],"keywords":[]},
            "safety_notes": ["Be polite."]
        }
        return ChatResponse(content=json.dumps(obj), raw={"choices":[{"message":{"content":json.dumps(obj)}}]}, latency_ms=10, retries=0, status_code=200)

def test_brain_offline():
    cfg = BrainConfig(api_key="dummy")
    brain = IntentBrain(cfg, client=FakeClient())
    card = brain.score("hello", {"subreddit":"x"})
    assert card["ok"] is True
    assert card["lead_tier"] in {"S","A","B","C","D"}
```

## 20.7 `tests/test_brain_fail_closed.py`

```python
from siw_intent_brain.brain import IntentBrain
from siw_intent_brain.config import BrainConfig

class BadClient:
    def complete(self, req):
        raise Exception("boom")

def test_brain_fail_closed():
    cfg = BrainConfig(api_key="dummy")
    brain = IntentBrain(cfg, client=BadClient())
    card = brain.score("hello", {"subreddit":"x"})
    assert card["ok"] is False
    assert card["lead_tier"] == "D"
    assert card["recommended_next_step"] == "monitor"
    assert "error_code" in card["meta"]
```

---

# 21) `.env.example`

```
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_TIMEOUT_S=30
OPENROUTER_MAX_RETRIES=3
OPENROUTER_BACKOFF_S=1.2
BRAIN_MIN_CONFIDENCE=0.35
BRAIN_MAX_RATIONALE_CHARS=400
BRAIN_MAX_LIST_ITEMS=50
```

---

# 22) `config.example.yaml`

```yaml
openrouter:
  api_key: ""
  model: "openai/gpt-4o-mini"
  base_url: "https://openrouter.ai/api/v1/chat/completions"
  timeout_s: 30
  max_retries: 3
  backoff_s: 1.2

brain:
  min_confidence: 0.35
  max_rationale_chars: 400
  max_list_items: 50
  response_format_json: true
```

---


