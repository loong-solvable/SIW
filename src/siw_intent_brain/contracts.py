"""
Lead Card contract definitions and validation.

This module defines the output contract for SIW Intent Brain.
All outputs must conform to schemas/lead_card.v1.json.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict

# =============================================================================
# Type Literals (Enums)
# =============================================================================

SchemaVersion = Literal["lead_card.v1"]
LeadTier = Literal["S", "A", "B", "C", "D"]
RecommendedNextStep = Literal["ignore", "monitor", "draft_reply", "ask_question", "offer_resource"]
ParserMode = Literal["strict", "extracted", "fail_closed"]

# Runtime enum sets for validation
LEAD_TIERS = {"S", "A", "B", "C", "D"}
NEXT_STEPS = {"ignore", "monitor", "draft_reply", "ask_question", "offer_resource"}
PARSER_MODES = {"strict", "extracted", "fail_closed"}
SCHEMA_VERSION: SchemaVersion = "lead_card.v1"


# =============================================================================
# TypedDict Definitions
# =============================================================================

class Scores(TypedDict):
    """Four-dimensional intent scores, all in [0, 1]."""
    urgency: float
    pain_point_intensity: float
    commercial_relevance: float
    solution_seeking: float


class ExtractedSignals(TypedDict):
    """Extracted intent signals from text."""
    problem_summary: str
    constraints: List[str]
    budget_hints: List[str]
    tooling_stack: List[str]
    keywords: List[str]


class Meta(TypedDict, total=False):
    """Request metadata. Required fields are enforced by validation."""
    model: str
    provider: str
    latency_ms: int
    retries: int
    parser_mode: ParserMode
    schema_version: SchemaVersion
    # Optional (only present when ok=false)
    error_code: str
    error_detail: str
    validation_error: bool


class LeadCard(TypedDict):
    """The complete Lead Card output contract."""
    ok: bool
    scores: Scores
    confidence: float
    lead_tier: LeadTier
    recommended_next_step: RecommendedNextStep
    rationale: str
    extracted_signals: ExtractedSignals
    safety_notes: List[str]
    meta: Meta


# =============================================================================
# Default Builders
# =============================================================================

def default_scores() -> Scores:
    """Return zero-initialized scores dict."""
    return {
        "urgency": 0.0,
        "pain_point_intensity": 0.0,
        "commercial_relevance": 0.0,
        "solution_seeking": 0.0,
    }


def default_extracted_signals() -> ExtractedSignals:
    """Return empty extracted_signals dict."""
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
    Construct a LeadCard with required meta defaults.
    
    Ensures:
      - provider="openrouter"
      - schema_version="lead_card.v1"
      - latency_ms, retries, parser_mode have defaults
    """
    meta_out: Meta = dict(meta) if meta else {}  # type: ignore
    
    # Required meta fields with defaults
    meta_out.setdefault("provider", "openrouter")
    meta_out.setdefault("schema_version", SCHEMA_VERSION)
    meta_out.setdefault("latency_ms", 0)
    meta_out.setdefault("retries", 0)
    meta_out.setdefault("parser_mode", "strict")
    
    # model is required but has no default - must be provided or set to empty
    meta_out.setdefault("model", "")
    
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


# =============================================================================
# Allowed Keys (for additionalProperties: false enforcement)
# =============================================================================

_ALLOWED_TOP_KEYS = {
    "ok", "scores", "confidence", "lead_tier",
    "recommended_next_step", "rationale", "extracted_signals",
    "safety_notes", "meta"
}
_ALLOWED_SCORES_KEYS = {"urgency", "pain_point_intensity", "commercial_relevance", "solution_seeking"}
_ALLOWED_SIGNALS_KEYS = {"problem_summary", "constraints", "budget_hints", "tooling_stack", "keywords"}
_ALLOWED_META_KEYS = {
    "model", "provider", "latency_ms", "retries", "parser_mode", "schema_version",
    "error_code", "error_detail", "validation_error"  # Optional fields for ok=false
}


# =============================================================================
# Lightweight Validator
# =============================================================================

def validate_lead_card(obj: Dict[str, Any]) -> List[str]:
    """
    Lightweight contract validator (no network required).
    
    Returns a list of error strings; empty list means valid.
    Does NOT raise exceptions - always returns a list.
    
    Enforces additionalProperties: false on top-level, scores, extracted_signals, and meta.
    """
    errors: List[str] = []
    
    if not isinstance(obj, dict):
        errors.append("Root must be an object/dict")
        return errors
    
    # --- Required top-level keys ---
    required_keys = list(_ALLOWED_TOP_KEYS)
    for key in required_keys:
        if key not in obj:
            errors.append(f"Missing required key: {key}")
    
    # If missing critical keys, return early
    if errors:
        return errors
    
    # --- Check for unexpected top-level keys (additionalProperties: false) ---
    extra_top = set(obj.keys()) - _ALLOWED_TOP_KEYS
    if extra_top:
        errors.append(f"Unexpected top-level keys: {sorted(extra_top)}")
    
    # --- ok: boolean ---
    if not isinstance(obj["ok"], bool):
        errors.append("'ok' must be a boolean")
    
    # --- scores: object with 4 float fields in [0,1] ---
    scores = obj.get("scores")
    if not isinstance(scores, dict):
        errors.append("'scores' must be an object")
    else:
        # Check for unexpected keys in scores
        extra_scores = set(scores.keys()) - _ALLOWED_SCORES_KEYS
        if extra_scores:
            errors.append(f"Unexpected keys in scores: {sorted(extra_scores)}")
        
        score_keys = ["urgency", "pain_point_intensity", "commercial_relevance", "solution_seeking"]
        for sk in score_keys:
            if sk not in scores:
                errors.append(f"scores.{sk} is missing")
            else:
                val = scores[sk]
                if not isinstance(val, (int, float)):
                    errors.append(f"scores.{sk} must be a number")
                elif val < 0 or val > 1:
                    errors.append(f"scores.{sk} must be in [0, 1], got {val}")
    
    # --- confidence: float in [0,1] ---
    confidence = obj.get("confidence")
    if not isinstance(confidence, (int, float)):
        errors.append("'confidence' must be a number")
    elif confidence < 0 or confidence > 1:
        errors.append(f"'confidence' must be in [0, 1], got {confidence}")
    
    # --- lead_tier: enum (sorted output for stable error messages) ---
    lead_tier = obj.get("lead_tier")
    if lead_tier not in LEAD_TIERS:
        errors.append(f"'lead_tier' must be one of {sorted(LEAD_TIERS)}, got '{lead_tier}'")
    
    # --- recommended_next_step: enum (sorted output for stable error messages) ---
    next_step = obj.get("recommended_next_step")
    if next_step not in NEXT_STEPS:
        errors.append(f"'recommended_next_step' must be one of {sorted(NEXT_STEPS)}, got '{next_step}'")
    
    # --- rationale: string, maxLength 400 ---
    rationale = obj.get("rationale")
    if not isinstance(rationale, str):
        errors.append("'rationale' must be a string")
    elif len(rationale) > 400:
        errors.append(f"'rationale' exceeds maxLength 400, got {len(rationale)}")
    
    # --- extracted_signals: object with required sub-fields ---
    signals = obj.get("extracted_signals")
    if not isinstance(signals, dict):
        errors.append("'extracted_signals' must be an object")
    else:
        # Check for unexpected keys in extracted_signals
        extra_signals = set(signals.keys()) - _ALLOWED_SIGNALS_KEYS
        if extra_signals:
            errors.append(f"Unexpected keys in extracted_signals: {sorted(extra_signals)}")
        
        # problem_summary: string
        if not isinstance(signals.get("problem_summary"), str):
            errors.append("extracted_signals.problem_summary must be a string")
        
        # List fields
        list_fields = ["constraints", "budget_hints", "tooling_stack", "keywords"]
        for lf in list_fields:
            val = signals.get(lf)
            if not isinstance(val, list):
                errors.append(f"extracted_signals.{lf} must be an array")
            elif len(val) > 50:
                errors.append(f"extracted_signals.{lf} exceeds maxItems 50, got {len(val)}")
            else:
                for i, item in enumerate(val):
                    if not isinstance(item, str):
                        errors.append(f"extracted_signals.{lf}[{i}] must be a string")
                        break  # Only report first type error per field
    
    # --- safety_notes: array of strings, maxItems 50 ---
    safety_notes = obj.get("safety_notes")
    if not isinstance(safety_notes, list):
        errors.append("'safety_notes' must be an array")
    elif len(safety_notes) > 50:
        errors.append(f"'safety_notes' exceeds maxItems 50, got {len(safety_notes)}")
    else:
        for i, item in enumerate(safety_notes):
            if not isinstance(item, str):
                errors.append(f"safety_notes[{i}] must be a string")
                break
    
    # --- meta: object with required fields ---
    meta = obj.get("meta")
    if not isinstance(meta, dict):
        errors.append("'meta' must be an object")
    else:
        # Check for unexpected keys in meta
        extra_meta = set(meta.keys()) - _ALLOWED_META_KEYS
        if extra_meta:
            errors.append(f"Unexpected keys in meta: {sorted(extra_meta)}")
        
        # Required meta keys
        meta_required = ["model", "provider", "latency_ms", "retries", "parser_mode", "schema_version"]
        for mk in meta_required:
            if mk not in meta:
                errors.append(f"meta.{mk} is missing")
        
        # model: string
        if "model" in meta and not isinstance(meta["model"], str):
            errors.append("meta.model must be a string")
        
        # provider: must be "openrouter"
        if "provider" in meta and meta["provider"] != "openrouter":
            errors.append(f"meta.provider must be 'openrouter', got '{meta.get('provider')}'")
        
        # latency_ms: integer >= 0
        if "latency_ms" in meta:
            lat = meta["latency_ms"]
            if not isinstance(lat, int):
                errors.append("meta.latency_ms must be an integer")
            elif lat < 0:
                errors.append(f"meta.latency_ms must be >= 0, got {lat}")
        
        # retries: integer >= 0
        if "retries" in meta:
            ret = meta["retries"]
            if not isinstance(ret, int):
                errors.append("meta.retries must be an integer")
            elif ret < 0:
                errors.append(f"meta.retries must be >= 0, got {ret}")
        
        # parser_mode: enum (sorted output for stable error messages)
        if "parser_mode" in meta and meta["parser_mode"] not in PARSER_MODES:
            errors.append(f"meta.parser_mode must be one of {sorted(PARSER_MODES)}, got '{meta.get('parser_mode')}'")
        
        # schema_version: must be "lead_card.v1"
        if "schema_version" in meta and meta["schema_version"] != "lead_card.v1":
            errors.append(f"meta.schema_version must be 'lead_card.v1', got '{meta.get('schema_version')}'")
    
    return errors

