"""
Heuristic lead tiering calculation.

Fixed formula - DO NOT modify thresholds or weights.

Formula:
  base = 0.25*U + 0.30*P + 0.30*C + 0.15*S
  score = base * (0.5 + 0.5*conf)

Thresholds:
  S: score >= 0.78
  A: score >= 0.62
  B: score >= 0.46
  C: score >= 0.30
  D: else
"""

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
    Compute lead tier using fixed heuristic formula.
    
    Args:
        urgency: Urgency score [0, 1]
        pain: Pain point intensity score [0, 1]
        commercial: Commercial relevance score [0, 1]
        seeking: Solution seeking score [0, 1]
        confidence: Model confidence [0, 1]
    
    Returns:
        LeadTier: "S", "A", "B", "C", or "D"
    
    Formula:
        base = 0.25*U + 0.30*P + 0.30*C + 0.15*S
        score = base * (0.5 + 0.5*conf)
        
    Thresholds:
        S >= 0.78
        A >= 0.62
        B >= 0.46
        C >= 0.30
        D < 0.30
    """
    # Fixed weights - DO NOT CHANGE
    base = (
        0.25 * urgency +
        0.30 * pain +
        0.30 * commercial +
        0.15 * seeking
    )
    
    # Confidence modulation: at conf=0, multiplier=0.5; at conf=1, multiplier=1.0
    score = base * (0.5 + 0.5 * confidence)
    
    # Fixed thresholds - DO NOT CHANGE
    if score >= 0.78:
        return "S"
    if score >= 0.62:
        return "A"
    if score >= 0.46:
        return "B"
    if score >= 0.30:
        return "C"
    return "D"

