"""
Tests for heuristics/next_step.py - Next step calculation.

Tests cover:
  - Low confidence (< 0.35) => monitor
  - Low composite (< 0.18) => ignore
  - offer_resource condition (C >= 0.6 and S >= 0.55)
  - ask_question condition (P >= 0.6 and S >= 0.5)
  - draft_reply condition (composite >= 0.45)
  - Default monitor
"""

import pytest

from siw_intent_brain.heuristics.next_step import compute_next_step


# =============================================================================
# Helper: Calculate composite
# =============================================================================

def calc_composite(p: float, c: float, s: float) -> float:
    """Calculate composite score."""
    return (c + s + p) / 3.0


# =============================================================================
# Test Low Confidence => Monitor
# =============================================================================

class TestLowConfidence:
    def test_conf_0_returns_monitor(self):
        """conf=0 always returns monitor."""
        step = compute_next_step(1.0, 1.0, 1.0, 0.0)
        assert step == "monitor"
    
    def test_conf_034_returns_monitor(self):
        """conf=0.34 (just below 0.35) returns monitor."""
        step = compute_next_step(1.0, 1.0, 1.0, 0.34)
        assert step == "monitor"
    
    def test_conf_0349_returns_monitor(self):
        """conf=0.349 returns monitor."""
        step = compute_next_step(1.0, 1.0, 1.0, 0.349)
        assert step == "monitor"
    
    def test_conf_035_allows_other_logic(self):
        """conf=0.35 allows other logic to proceed."""
        # With high scores, should not return monitor due to low conf
        step = compute_next_step(1.0, 1.0, 1.0, 0.35)
        assert step != "monitor" or calc_composite(1.0, 1.0, 1.0) < 0.45


# =============================================================================
# Test Low Composite => Ignore
# =============================================================================

class TestLowComposite:
    def test_composite_0_returns_ignore(self):
        """composite=0 returns ignore."""
        step = compute_next_step(0.0, 0.0, 0.0, 0.5)
        assert step == "ignore"
    
    def test_composite_017_returns_ignore(self):
        """composite=0.17 (just below 0.18) returns ignore."""
        # Need (P + C + S) / 3 = 0.17 => P + C + S = 0.51
        # Use P=0.17, C=0.17, S=0.17 => sum=0.51, comp=0.17
        step = compute_next_step(0.17, 0.17, 0.17, 0.5)
        composite = calc_composite(0.17, 0.17, 0.17)
        assert composite < 0.18
        assert step == "ignore"
    
    def test_composite_018_not_ignore(self):
        """composite=0.18 does not return ignore."""
        # P=0.18, C=0.18, S=0.18 => comp=0.18
        step = compute_next_step(0.18, 0.18, 0.18, 0.5)
        composite = calc_composite(0.18, 0.18, 0.18)
        assert composite == pytest.approx(0.18, abs=1e-9)
        assert step != "ignore"


# =============================================================================
# Test offer_resource (C >= 0.6 and S >= 0.55)
# =============================================================================

class TestOfferResource:
    def test_exact_thresholds(self):
        """C=0.6, S=0.55 returns offer_resource."""
        step = compute_next_step(0.0, 0.6, 0.55, 0.5)
        assert step == "offer_resource"
    
    def test_high_commercial_seeking(self):
        """High C and S returns offer_resource."""
        step = compute_next_step(0.0, 0.8, 0.7, 0.5)
        assert step == "offer_resource"
    
    def test_commercial_below_06_not_offer(self):
        """C=0.59 does not trigger offer_resource."""
        step = compute_next_step(0.0, 0.59, 0.6, 0.5)
        assert step != "offer_resource"
    
    def test_seeking_below_055_not_offer(self):
        """S=0.54 does not trigger offer_resource."""
        step = compute_next_step(0.0, 0.7, 0.54, 0.5)
        assert step != "offer_resource"
    
    def test_offer_resource_priority_over_ask(self):
        """offer_resource takes priority when both conditions met."""
        # P=0.7, C=0.7, S=0.6 => both offer_resource and ask_question conditions
        step = compute_next_step(0.7, 0.7, 0.6, 0.5)
        assert step == "offer_resource"


# =============================================================================
# Test ask_question (P >= 0.6 and S >= 0.5)
# =============================================================================

class TestAskQuestion:
    def test_exact_thresholds(self):
        """P=0.6, S=0.5 returns ask_question (when not offer_resource)."""
        # C < 0.6 to avoid offer_resource
        step = compute_next_step(0.6, 0.5, 0.5, 0.5)
        assert step == "ask_question"
    
    def test_high_pain_seeking(self):
        """High P and S (low C) returns ask_question."""
        step = compute_next_step(0.8, 0.4, 0.7, 0.5)
        assert step == "ask_question"
    
    def test_pain_below_06_not_ask(self):
        """P=0.59 does not trigger ask_question."""
        step = compute_next_step(0.59, 0.4, 0.6, 0.5)
        assert step != "ask_question"
    
    def test_seeking_below_05_not_ask(self):
        """S=0.49 does not trigger ask_question."""
        step = compute_next_step(0.7, 0.4, 0.49, 0.5)
        assert step != "ask_question"


# =============================================================================
# Test draft_reply (composite >= 0.45)
# =============================================================================

class TestDraftReply:
    def test_exact_threshold_045(self):
        """composite=0.45 returns draft_reply (when no higher priority)."""
        # Need (P + C + S) / 3 = 0.45 => P + C + S = 1.35
        # Use P=0.45, C=0.45, S=0.45 => comp=0.45
        # But C < 0.6 and P < 0.6 to avoid other triggers
        step = compute_next_step(0.45, 0.45, 0.45, 0.5)
        composite = calc_composite(0.45, 0.45, 0.45)
        assert composite == pytest.approx(0.45, abs=1e-9)
        assert step == "draft_reply"
    
    def test_composite_above_045(self):
        """composite > 0.45 returns draft_reply (when no higher priority)."""
        step = compute_next_step(0.5, 0.5, 0.5, 0.5)
        composite = calc_composite(0.5, 0.5, 0.5)
        assert composite == 0.5
        assert step == "draft_reply"
    
    def test_composite_below_045_not_draft(self):
        """composite < 0.45 does not return draft_reply."""
        step = compute_next_step(0.4, 0.4, 0.4, 0.5)
        composite = calc_composite(0.4, 0.4, 0.4)
        assert composite < 0.45
        assert step != "draft_reply"


# =============================================================================
# Test Default Monitor
# =============================================================================

class TestDefaultMonitor:
    def test_mid_range_returns_monitor(self):
        """Mid-range scores not hitting any trigger => monitor."""
        # composite >= 0.18 but < 0.45, no specific triggers
        step = compute_next_step(0.3, 0.3, 0.3, 0.5)
        composite = calc_composite(0.3, 0.3, 0.3)
        assert composite == 0.3
        assert 0.18 <= composite < 0.45
        assert step == "monitor"
    
    def test_composite_044_returns_monitor(self):
        """composite=0.44 returns monitor."""
        # 0.44 * 3 = 1.32, use 0.44 each
        step = compute_next_step(0.44, 0.44, 0.44, 0.5)
        composite = calc_composite(0.44, 0.44, 0.44)
        assert composite == pytest.approx(0.44, abs=1e-9)
        assert step == "monitor"


# =============================================================================
# Test Priority Order
# =============================================================================

class TestPriorityOrder:
    def test_low_conf_beats_all(self):
        """Low confidence overrides everything."""
        step = compute_next_step(1.0, 1.0, 1.0, 0.3)
        assert step == "monitor"
    
    def test_ignore_beats_offer_resource(self):
        """Low composite (ignore) checked before offer_resource."""
        # This is impossible: if C >= 0.6 and S >= 0.55, composite >= 0.38
        # So ignore condition can't be hit with offer_resource conditions
        pass
    
    def test_offer_beats_ask(self):
        """offer_resource beats ask_question when both apply."""
        step = compute_next_step(0.7, 0.7, 0.7, 0.5)
        assert step == "offer_resource"
    
    def test_offer_beats_draft(self):
        """offer_resource beats draft_reply."""
        step = compute_next_step(0.3, 0.7, 0.6, 0.5)
        assert step == "offer_resource"
    
    def test_ask_beats_draft(self):
        """ask_question beats draft_reply."""
        step = compute_next_step(0.7, 0.3, 0.6, 0.5)
        assert step == "ask_question"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    def test_all_zeros_high_conf(self):
        """All zeros with high conf => ignore."""
        step = compute_next_step(0.0, 0.0, 0.0, 1.0)
        assert step == "ignore"
    
    def test_all_ones_high_conf(self):
        """All ones with high conf => offer_resource."""
        step = compute_next_step(1.0, 1.0, 1.0, 1.0)
        assert step == "offer_resource"
    
    def test_boundary_conf_035(self):
        """Exactly conf=0.35 proceeds to next checks."""
        step = compute_next_step(1.0, 1.0, 1.0, 0.35)
        # Should hit offer_resource, not monitor
        assert step == "offer_resource"

