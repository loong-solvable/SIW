"""
Normalization of LLM output fields.

Ensures all values conform to schema constraints:
  - Scores clamped to [0, 1]
  - Strings trimmed and length-limited
  - Lists cleaned (filter empties, limit items)
  - Enums validated (invalid → empty for heuristic fallback)

NEVER silently ignores errors - always produces valid output or flags issues.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..contracts import (
    LEAD_TIERS,
    NEXT_STEPS,
    PARSER_MODES,
    ExtractedSignals,
    Scores,
    default_extracted_signals,
    default_scores,
)


# =============================================================================
# Clamping Functions
# =============================================================================

def clamp_score(value: Any) -> float:
    """
    Clamp a value to [0, 1] range.
    
    - Converts to float if possible
    - Returns 0.0 on conversion failure
    - Clamps to [0, 1] bounds
    
    Args:
        value: Any value that might be a score.
    
    Returns:
        Float in [0, 1].
    """
    if value is None:
        return 0.0
    
    try:
        f = float(value)
    except (ValueError, TypeError):
        return 0.0
    
    # Handle NaN/Inf
    if f != f:  # NaN check
        return 0.0
    if f == float("inf"):
        return 1.0
    if f == float("-inf"):
        return 0.0
    
    # Clamp to [0, 1]
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def clamp_confidence(value: Any) -> float:
    """
    Clamp confidence value to [0, 1].
    
    Alias for clamp_score with identical behavior.
    """
    return clamp_score(value)


# =============================================================================
# String Cleaning
# =============================================================================

def clean_string(value: Any, max_length: int) -> str:
    """
    Clean and truncate a string value.
    
    - Converts to string
    - Strips whitespace
    - Truncates to max_length
    
    Args:
        value: Any value to convert to string.
        max_length: Maximum allowed length.
    
    Returns:
        Cleaned string, at most max_length chars.
    """
    if value is None:
        return ""
    
    s = str(value).strip()
    
    if len(s) > max_length:
        return s[:max_length]
    return s


def clean_string_list(value: Any, max_items: int, max_item_length: int = 500) -> List[str]:
    """
    Clean a list of strings.
    
    - Ensures input is a list
    - Converts items to strings
    - Strips and filters empty strings
    - Truncates to max_items
    - Truncates individual items to max_item_length
    
    Args:
        value: Any value that should be a list of strings.
        max_items: Maximum number of items.
        max_item_length: Maximum length per item.
    
    Returns:
        List of non-empty strings.
    """
    if not isinstance(value, list):
        return []
    
    result: List[str] = []
    for item in value:
        if item is None:
            continue
        s = str(item).strip()
        if not s:
            continue
        # Truncate individual item
        if len(s) > max_item_length:
            s = s[:max_item_length]
        result.append(s)
        if len(result) >= max_items:
            break
    
    return result


# =============================================================================
# Scores Normalization
# =============================================================================

def normalize_scores(raw_scores: Any) -> Scores:
    """
    Normalize scores object from LLM output.
    
    - Ensures dict structure
    - Clamps all four score fields to [0, 1]
    - Missing fields default to 0.0
    
    Args:
        raw_scores: Raw scores object from LLM.
    
    Returns:
        Valid Scores TypedDict with all fields in [0, 1].
    """
    if not isinstance(raw_scores, dict):
        return default_scores()
    
    return {
        "urgency": clamp_score(raw_scores.get("urgency")),
        "pain_point_intensity": clamp_score(raw_scores.get("pain_point_intensity")),
        "commercial_relevance": clamp_score(raw_scores.get("commercial_relevance")),
        "solution_seeking": clamp_score(raw_scores.get("solution_seeking")),
    }


# =============================================================================
# Extracted Signals Normalization
# =============================================================================

def normalize_extracted_signals(
    raw_signals: Any,
    max_list_items: int = 50,
    max_summary_length: int = 200,
) -> ExtractedSignals:
    """
    Normalize extracted_signals object from LLM output.
    
    - Ensures dict structure
    - Cleans problem_summary string
    - Cleans all list fields
    
    Args:
        raw_signals: Raw extracted_signals from LLM.
        max_list_items: Max items per list field.
        max_summary_length: Max length for problem_summary.
    
    Returns:
        Valid ExtractedSignals TypedDict.
    """
    if not isinstance(raw_signals, dict):
        return default_extracted_signals()
    
    return {
        "problem_summary": clean_string(
            raw_signals.get("problem_summary"), 
            max_summary_length
        ),
        "constraints": clean_string_list(
            raw_signals.get("constraints"), 
            max_list_items
        ),
        "budget_hints": clean_string_list(
            raw_signals.get("budget_hints"), 
            max_list_items
        ),
        "tooling_stack": clean_string_list(
            raw_signals.get("tooling_stack"), 
            max_list_items
        ),
        "keywords": clean_string_list(
            raw_signals.get("keywords"), 
            max_list_items
        ),
    }


# =============================================================================
# Enum Validation
# =============================================================================

def validate_lead_tier(value: Any) -> Tuple[str, bool]:
    """
    Validate lead_tier enum value.
    
    Returns:
        Tuple of (normalized_value, is_valid).
        If invalid, normalized_value is empty string.
    """
    if value is None:
        return "", False
    
    s = str(value).strip().upper()
    if s in LEAD_TIERS:
        return s, True
    return "", False


def validate_next_step(value: Any) -> Tuple[str, bool]:
    """
    Validate recommended_next_step enum value.
    
    Returns:
        Tuple of (normalized_value, is_valid).
        If invalid, normalized_value is empty string.
    """
    if value is None:
        return "", False
    
    s = str(value).strip().lower()
    if s in NEXT_STEPS:
        return s, True
    return "", False


def validate_parser_mode(value: Any) -> Tuple[str, bool]:
    """
    Validate parser_mode enum value.
    
    Returns:
        Tuple of (normalized_value, is_valid).
        If invalid, normalized_value is empty string.
    """
    if value is None:
        return "", False
    
    s = str(value).strip().lower()
    if s in PARSER_MODES:
        return s, True
    return "", False


# =============================================================================
# Full Output Normalization
# =============================================================================

class NormalizationFlags:
    """Flags indicating which fields needed fallback/correction."""
    
    def __init__(self):
        self.tier_valid: bool = True
        self.next_step_valid: bool = True
        self.scores_defaulted: bool = False
        self.signals_defaulted: bool = False


def normalize_llm_output(
    raw: Dict[str, Any],
    max_rationale_chars: int = 400,
    max_list_items: int = 50,
) -> Tuple[Dict[str, Any], NormalizationFlags]:
    """
    Normalize complete LLM output object.
    
    Produces a partially-valid structure ready for heuristic fill-in.
    Invalid enums are set to empty string for heuristic fallback.
    
    Args:
        raw: Raw parsed JSON from LLM.
        max_rationale_chars: Max length for rationale.
        max_list_items: Max items in list fields.
    
    Returns:
        Tuple of (normalized_dict, flags).
        normalized_dict contains:
          - scores: Scores (clamped)
          - confidence: float (clamped)
          - lead_tier: str (valid enum or "")
          - recommended_next_step: str (valid enum or "")
          - rationale: str (truncated)
          - extracted_signals: ExtractedSignals
          - safety_notes: List[str]
        flags indicates which fields needed correction.
    """
    flags = NormalizationFlags()
    
    # --- Scores ---
    raw_scores = raw.get("scores")
    if not isinstance(raw_scores, dict):
        flags.scores_defaulted = True
    scores = normalize_scores(raw_scores)
    
    # --- Confidence ---
    confidence = clamp_confidence(raw.get("confidence"))
    
    # --- Lead Tier ---
    tier_value, tier_valid = validate_lead_tier(raw.get("lead_tier"))
    flags.tier_valid = tier_valid
    
    # --- Next Step ---
    step_value, step_valid = validate_next_step(raw.get("recommended_next_step"))
    flags.next_step_valid = step_valid
    
    # --- Rationale ---
    rationale = clean_string(raw.get("rationale"), max_rationale_chars)
    if not rationale:
        rationale = "No rationale provided."
    
    # --- Extracted Signals ---
    raw_signals = raw.get("extracted_signals")
    if not isinstance(raw_signals, dict):
        flags.signals_defaulted = True
    extracted_signals = normalize_extracted_signals(raw_signals, max_list_items)
    
    # --- Safety Notes ---
    safety_notes = clean_string_list(raw.get("safety_notes"), max_list_items)
    
    normalized = {
        "scores": scores,
        "confidence": confidence,
        "lead_tier": tier_value,
        "recommended_next_step": step_value,
        "rationale": rationale,
        "extracted_signals": extracted_signals,
        "safety_notes": safety_notes,
    }
    
    return normalized, flags

