"""
Heuristics module - Fallback calculations for tier and next step.

Used when LLM output is missing or invalid.
Formulas and thresholds are fixed - DO NOT modify.
"""

from .tiering import compute_lead_tier
from .next_step import compute_next_step

__all__ = [
    "compute_lead_tier",
    "compute_next_step",
]
