"""
Heuristic next step calculation.

Fixed logic - DO NOT modify thresholds or conditions.

Logic:
  1. if conf < 0.35 => monitor
  2. composite = (C + S + P) / 3
  3. if composite < 0.18 => ignore
  4. if C >= 0.6 and S >= 0.55 => offer_resource
  5. elif P >= 0.6 and S >= 0.5 => ask_question
  6. elif composite >= 0.45 => draft_reply
  7. else => monitor
"""

from __future__ import annotations

from ..contracts import RecommendedNextStep


def compute_next_step(
    pain: float,
    commercial: float,
    seeking: float,
    confidence: float,
) -> RecommendedNextStep:
    """
    Compute recommended next step using fixed heuristic logic.
    
    Args:
        pain: Pain point intensity score [0, 1]
        commercial: Commercial relevance score [0, 1]
        seeking: Solution seeking score [0, 1]
        confidence: Model confidence [0, 1]
    
    Returns:
        RecommendedNextStep: One of "ignore", "monitor", "draft_reply", 
                            "ask_question", "offer_resource"
    
    Logic (in order):
        1. if conf < 0.35 => monitor
        2. composite = (C + S + P) / 3
        3. if composite < 0.18 => ignore
        4. if C >= 0.6 and S >= 0.55 => offer_resource
        5. elif P >= 0.6 and S >= 0.5 => ask_question
        6. elif composite >= 0.45 => draft_reply
        7. else => monitor
    """
    # Step 1: Low confidence always returns monitor
    if confidence < 0.35:
        return "monitor"
    
    # Step 2: Compute composite
    composite = (commercial + seeking + pain) / 3.0
    
    # Step 3: Very low composite => ignore
    if composite < 0.18:
        return "ignore"
    
    # Step 4: High commercial + seeking => offer_resource
    if commercial >= 0.6 and seeking >= 0.55:
        return "offer_resource"
    
    # Step 5: High pain + seeking => ask_question
    if pain >= 0.6 and seeking >= 0.5:
        return "ask_question"
    
    # Step 6: Moderate composite => draft_reply
    if composite >= 0.45:
        return "draft_reply"
    
    # Step 7: Default => monitor
    return "monitor"

