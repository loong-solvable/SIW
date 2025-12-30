"""
Curator module for sorting, selecting, and computing statistics.

Provides:
  - select_top(): Sort and select top N lead cards by tier and scores
  - compute_stats(): Compute summary statistics from records

All operations are deterministic (stable sort, deterministic Counter ordering).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Tuple


# Tier ranking: S is best (0), D is worst (4)
TIER_RANK: Dict[str, int] = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}


def _get_sort_key(record: Dict[str, Any]) -> Tuple:
    """
    Generate sort key for lead card.
    
    Sort order (ascending):
      - tier_rank (S=0 best, D=4 worst)
      - -confidence (higher first)
      - -commercial_relevance
      - -solution_seeking
      - -pain_point_intensity
      - -urgency
    """
    tier = record.get("lead_tier", "D")
    tier_rank = TIER_RANK.get(tier, 4)
    
    confidence = record.get("confidence", 0.0)
    
    scores = record.get("scores", {})
    commercial_relevance = scores.get("commercial_relevance", 0.0)
    solution_seeking = scores.get("solution_seeking", 0.0)
    pain_point_intensity = scores.get("pain_point_intensity", 0.0)
    urgency = scores.get("urgency", 0.0)
    
    return (
        tier_rank,
        -confidence,
        -commercial_relevance,
        -solution_seeking,
        -pain_point_intensity,
        -urgency,
    )


def select_top(
    records: List[Dict[str, Any]],
    top_n: int,
    *,
    filter_ok: bool = True,
) -> List[Dict[str, Any]]:
    """
    Sort and select top N lead cards.
    
    Args:
        records: List of LeadCard dicts.
        top_n: Number of records to return. If <= 0, returns [].
        filter_ok: If True (default), only include records where ok=True.
    
    Returns:
        List of top_n LeadCard dicts, sorted by tier and scores.
    
    Notes:
        - Uses stable sort to maintain determinism
        - Missing scores default to 0.0
    """
    if top_n <= 0:
        return []
    
    # Filter if requested
    if filter_ok:
        filtered = [r for r in records if r.get("ok", False) is True]
    else:
        filtered = list(records)
    
    # Sort by key (stable)
    sorted_records = sorted(filtered, key=_get_sort_key)
    
    return sorted_records[:top_n]


def compute_stats(
    records: List[Dict[str, Any]],
    invalid_lines: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Compute summary statistics from lead card records.
    
    Args:
        records: List of valid LeadCard dicts.
        invalid_lines: List of invalid line records (for count).
    
    Returns:
        Stats dict with schema:
          - total: int (total records + invalid)
          - valid: int (valid records count)
          - invalid: int (invalid lines count)
          - excluded_ok_false: int (records with ok=False)
          - tier_counts: {"S": 0, "A": 0, ...}
          - next_step_counts: {...}
          - means: {
              "confidence": 0.0,
              "urgency": 0.0,
              "pain_point_intensity": 0.0,
              "commercial_relevance": 0.0,
              "solution_seeking": 0.0
            }
          - top_keywords: [(keyword, count), ...] (top 10)
          - top_budget_hints: [(hint, count), ...] (top 10)
    
    Notes:
        - Means are computed only from ok=True records
        - If no valid records, means default to 0.0
        - Keyword/budget lists are sorted by (count desc, token asc)
    """
    invalid_count = len(invalid_lines) if invalid_lines else 0
    valid_count = len(records)
    
    # Separate ok=True and ok=False
    ok_true = [r for r in records if r.get("ok", False) is True]
    ok_false_count = valid_count - len(ok_true)
    
    # Tier counts (from ok=True only)
    tier_counts: Dict[str, int] = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
    for r in ok_true:
        tier = r.get("lead_tier", "D")
        if tier in tier_counts:
            tier_counts[tier] += 1
    
    # Next step counts (from ok=True only)
    next_step_counter: Counter[str] = Counter()
    for r in ok_true:
        step = r.get("recommended_next_step", "monitor")
        next_step_counter[step] += 1
    
    # Means (from ok=True only)
    n = len(ok_true)
    if n > 0:
        sum_confidence = sum(r.get("confidence", 0.0) for r in ok_true)
        sum_urgency = sum(r.get("scores", {}).get("urgency", 0.0) for r in ok_true)
        sum_pain = sum(r.get("scores", {}).get("pain_point_intensity", 0.0) for r in ok_true)
        sum_commercial = sum(r.get("scores", {}).get("commercial_relevance", 0.0) for r in ok_true)
        sum_solution = sum(r.get("scores", {}).get("solution_seeking", 0.0) for r in ok_true)
        
        means = {
            "confidence": round(sum_confidence / n, 4),
            "urgency": round(sum_urgency / n, 4),
            "pain_point_intensity": round(sum_pain / n, 4),
            "commercial_relevance": round(sum_commercial / n, 4),
            "solution_seeking": round(sum_solution / n, 4),
        }
    else:
        means = {
            "confidence": 0.0,
            "urgency": 0.0,
            "pain_point_intensity": 0.0,
            "commercial_relevance": 0.0,
            "solution_seeking": 0.0,
        }
    
    # Top keywords (from ok=True only)
    keyword_counter: Counter[str] = Counter()
    for r in ok_true:
        signals = r.get("extracted_signals", {})
        keywords = signals.get("keywords", [])
        if isinstance(keywords, list):
            for kw in keywords:
                if isinstance(kw, str) and kw.strip():
                    keyword_counter[kw.strip()] += 1
    
    # Sort by (count desc, token asc) and take top 10
    top_keywords = _sorted_counter_items(keyword_counter, 10)
    
    # Top budget hints (from ok=True only)
    budget_counter: Counter[str] = Counter()
    for r in ok_true:
        signals = r.get("extracted_signals", {})
        hints = signals.get("budget_hints", [])
        if isinstance(hints, list):
            for hint in hints:
                if isinstance(hint, str) and hint.strip():
                    budget_counter[hint.strip()] += 1
    
    top_budget_hints = _sorted_counter_items(budget_counter, 10)
    
    return {
        "total": valid_count + invalid_count,
        "valid": valid_count,
        "invalid": invalid_count,
        "excluded_ok_false": ok_false_count,
        "tier_counts": tier_counts,
        "next_step_counts": dict(next_step_counter),
        "means": means,
        "top_keywords": top_keywords,
        "top_budget_hints": top_budget_hints,
    }


def _sorted_counter_items(
    counter: Counter[str],
    limit: int,
) -> List[Tuple[str, int]]:
    """
    Sort counter items by (count desc, token asc) and return top N.
    
    Returns:
        List of (token, count) tuples.
    """
    # Sort by (-count, token) for deterministic ordering
    items = sorted(counter.items(), key=lambda x: (-x[1], x[0]))
    return items[:limit]

