"""
Parsing module - JSON extraction and normalization.

Provides tolerant parsing of LLM output with strict normalization.
"""

from .json_extractor import extract_json, extract_json_safe
from .normalizer import (
    NormalizationFlags,
    clamp_confidence,
    clamp_score,
    clean_string,
    clean_string_list,
    normalize_extracted_signals,
    normalize_llm_output,
    normalize_scores,
    validate_lead_tier,
    validate_next_step,
    validate_parser_mode,
)

__all__ = [
    # JSON extraction
    "extract_json",
    "extract_json_safe",
    # Clamping
    "clamp_score",
    "clamp_confidence",
    # String cleaning
    "clean_string",
    "clean_string_list",
    # Normalization
    "normalize_scores",
    "normalize_extracted_signals",
    "normalize_llm_output",
    "NormalizationFlags",
    # Validation
    "validate_lead_tier",
    "validate_next_step",
    "validate_parser_mode",
]
