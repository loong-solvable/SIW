"""
Tests for heuristics/tiering.py - Lead tier calculation.

Tests cover:
  - Exact threshold boundaries (0.78, 0.62, 0.46, 0.30)
  - Confidence modulation (conf=0 gives multiplier=0.5)
  - All tier outcomes (S, A, B, C, D)
"""

import pytest

from siw_intent_brain.heuristics.tiering import compute_lead_tier


# =============================================================================
# Helper: Calculate score for given inputs
# =============================================================================

def calc_score(u: float, p: float, c: float, s: float, conf: float) -> float:
    """Calculate the raw score using the formula."""
    base = 0.25 * u + 0.30 * p + 0.30 * c + 0.15 * s
    return base * (0.5 + 0.5 * conf)


# =============================================================================
# Test Tier S (score >= 0.78)
# =============================================================================

class TestTierS:
    def test_all_max_conf_1(self):
        """All scores 1.0, conf 1.0 => S (score = 1.0)."""
        tier = compute_lead_tier(1.0, 1.0, 1.0, 1.0, 1.0)
        assert tier == "S"
        assert calc_score(1.0, 1.0, 1.0, 1.0, 1.0) == 1.0
    
    def test_exact_threshold_078(self):
        """Score exactly 0.78 => S."""
        # Need to find inputs that give exactly 0.78
        # base * (0.5 + 0.5*conf) = 0.78
        # With all scores = 1, base = 1.0
        # 1.0 * (0.5 + 0.5*conf) = 0.78
        # 0.5 + 0.5*conf = 0.78
        # conf = 0.56
        tier = compute_lead_tier(1.0, 1.0, 1.0, 1.0, 0.56)
        score = calc_score(1.0, 1.0, 1.0, 1.0, 0.56)
        assert score == pytest.approx(0.78, abs=1e-9)
        assert tier == "S"
    
    def test_just_above_078(self):
        """Score just above 0.78 => S."""
        tier = compute_lead_tier(1.0, 1.0, 1.0, 1.0, 0.57)
        assert tier == "S"


# =============================================================================
# Test Tier A (0.62 <= score < 0.78)
# =============================================================================

class TestTierA:
    def test_just_below_078(self):
        """Score just below 0.78 => A."""
        # conf = 0.55 gives score = 0.775
        tier = compute_lead_tier(1.0, 1.0, 1.0, 1.0, 0.55)
        score = calc_score(1.0, 1.0, 1.0, 1.0, 0.55)
        assert score < 0.78
        assert score >= 0.62
        assert tier == "A"
    
    def test_exact_threshold_062(self):
        """Score exactly 0.62 => A."""
        # 1.0 * (0.5 + 0.5*conf) = 0.62
        # conf = 0.24
        tier = compute_lead_tier(1.0, 1.0, 1.0, 1.0, 0.24)
        score = calc_score(1.0, 1.0, 1.0, 1.0, 0.24)
        assert score == pytest.approx(0.62, abs=1e-9)
        assert tier == "A"
    
    def test_mid_range_A(self):
        """Score in middle of A range."""
        tier = compute_lead_tier(1.0, 1.0, 1.0, 1.0, 0.40)
        score = calc_score(1.0, 1.0, 1.0, 1.0, 0.40)
        assert 0.62 <= score < 0.78
        assert tier == "A"


# =============================================================================
# Test Tier B (0.46 <= score < 0.62)
# =============================================================================

class TestTierB:
    def test_just_below_062(self):
        """Score just below 0.62 => B."""
        tier = compute_lead_tier(1.0, 1.0, 1.0, 1.0, 0.23)
        score = calc_score(1.0, 1.0, 1.0, 1.0, 0.23)
        assert score < 0.62
        assert score >= 0.46
        assert tier == "B"
    
    def test_exact_threshold_046(self):
        """Score exactly 0.46 => B."""
        # base = 1.0, need 1.0 * (0.5 + 0.5*conf) = 0.46
        # But minimum with conf=0 is 0.5, so need lower base
        # With base = 0.92: 0.92 * 0.5 = 0.46 (conf=0)
        # base = 0.25*U + 0.30*P + 0.30*C + 0.15*S = 0.92
        # Try U=P=C=S=0.92 => base = 0.92
        tier = compute_lead_tier(0.92, 0.92, 0.92, 0.92, 0.0)
        score = calc_score(0.92, 0.92, 0.92, 0.92, 0.0)
        assert score == pytest.approx(0.46, abs=1e-9)
        assert tier == "B"
    
    def test_mid_range_B(self):
        """Score in middle of B range."""
        tier = compute_lead_tier(1.0, 1.0, 1.0, 1.0, 0.08)
        score = calc_score(1.0, 1.0, 1.0, 1.0, 0.08)
        assert 0.46 <= score < 0.62
        assert tier == "B"


# =============================================================================
# Test Tier C (0.30 <= score < 0.46)
# =============================================================================

class TestTierC:
    def test_just_below_046(self):
        """Score just below 0.46 => C."""
        # base = 0.90, conf = 0 => score = 0.45
        tier = compute_lead_tier(0.90, 0.90, 0.90, 0.90, 0.0)
        score = calc_score(0.90, 0.90, 0.90, 0.90, 0.0)
        assert score < 0.46
        assert score >= 0.30
        assert tier == "C"
    
    def test_exact_threshold_030(self):
        """Score exactly 0.30 => C."""
        # base = 0.60, conf = 0 => score = 0.30
        tier = compute_lead_tier(0.60, 0.60, 0.60, 0.60, 0.0)
        score = calc_score(0.60, 0.60, 0.60, 0.60, 0.0)
        assert score == pytest.approx(0.30, abs=1e-9)
        assert tier == "C"
    
    def test_mid_range_C(self):
        """Score in middle of C range."""
        tier = compute_lead_tier(0.75, 0.75, 0.75, 0.75, 0.0)
        score = calc_score(0.75, 0.75, 0.75, 0.75, 0.0)
        assert 0.30 <= score < 0.46
        assert tier == "C"


# =============================================================================
# Test Tier D (score < 0.30)
# =============================================================================

class TestTierD:
    def test_just_below_030(self):
        """Score just below 0.30 => D."""
        tier = compute_lead_tier(0.58, 0.58, 0.58, 0.58, 0.0)
        score = calc_score(0.58, 0.58, 0.58, 0.58, 0.0)
        assert score < 0.30
        assert tier == "D"
    
    def test_all_zero(self):
        """All scores 0 => D (score = 0)."""
        tier = compute_lead_tier(0.0, 0.0, 0.0, 0.0, 0.0)
        assert tier == "D"
        assert calc_score(0.0, 0.0, 0.0, 0.0, 0.0) == 0.0
    
    def test_low_scores(self):
        """Low scores => D."""
        tier = compute_lead_tier(0.2, 0.2, 0.2, 0.2, 0.0)
        score = calc_score(0.2, 0.2, 0.2, 0.2, 0.0)
        assert score == pytest.approx(0.1, abs=1e-9)  # 0.2 * 0.5
        assert tier == "D"


# =============================================================================
# Test Confidence Modulation
# =============================================================================

class TestConfidenceModulation:
    def test_conf_0_gives_half(self):
        """conf=0 gives multiplier of 0.5."""
        # All 1s with conf=0: base=1.0, score=0.5
        tier = compute_lead_tier(1.0, 1.0, 1.0, 1.0, 0.0)
        score = calc_score(1.0, 1.0, 1.0, 1.0, 0.0)
        assert score == 0.5
        assert tier == "B"  # 0.5 is in B range [0.46, 0.62)
    
    def test_conf_1_gives_full(self):
        """conf=1 gives multiplier of 1.0."""
        tier = compute_lead_tier(1.0, 1.0, 1.0, 1.0, 1.0)
        score = calc_score(1.0, 1.0, 1.0, 1.0, 1.0)
        assert score == 1.0
        assert tier == "S"
    
    def test_conf_05_gives_075(self):
        """conf=0.5 gives multiplier of 0.75."""
        tier = compute_lead_tier(1.0, 1.0, 1.0, 1.0, 0.5)
        score = calc_score(1.0, 1.0, 1.0, 1.0, 0.5)
        assert score == 0.75
        assert tier == "A"  # 0.75 is in A range [0.62, 0.78)
    
    def test_low_base_high_conf(self):
        """Low base scores but high confidence."""
        # base = 0.5, conf = 1.0 => score = 0.5 * 1.0 = 0.5
        tier = compute_lead_tier(0.5, 0.5, 0.5, 0.5, 1.0)
        score = calc_score(0.5, 0.5, 0.5, 0.5, 1.0)
        assert score == 0.5
        assert tier == "B"
    
    def test_high_base_low_conf(self):
        """High base scores but low confidence."""
        # base = 1.0, conf = 0 => score = 0.5
        tier = compute_lead_tier(1.0, 1.0, 1.0, 1.0, 0.0)
        score = calc_score(1.0, 1.0, 1.0, 1.0, 0.0)
        assert score == 0.5
        assert tier == "B"


# =============================================================================
# Test Weight Distribution
# =============================================================================

class TestWeights:
    def test_urgency_weight_025(self):
        """Urgency contributes 0.25 to base."""
        # Only urgency = 1, others = 0, conf = 1
        tier = compute_lead_tier(1.0, 0.0, 0.0, 0.0, 1.0)
        score = calc_score(1.0, 0.0, 0.0, 0.0, 1.0)
        assert score == 0.25
        assert tier == "D"
    
    def test_pain_weight_030(self):
        """Pain contributes 0.30 to base."""
        tier = compute_lead_tier(0.0, 1.0, 0.0, 0.0, 1.0)
        score = calc_score(0.0, 1.0, 0.0, 0.0, 1.0)
        assert score == 0.30
        assert tier == "C"
    
    def test_commercial_weight_030(self):
        """Commercial contributes 0.30 to base."""
        tier = compute_lead_tier(0.0, 0.0, 1.0, 0.0, 1.0)
        score = calc_score(0.0, 0.0, 1.0, 0.0, 1.0)
        assert score == 0.30
        assert tier == "C"
    
    def test_seeking_weight_015(self):
        """Seeking contributes 0.15 to base."""
        tier = compute_lead_tier(0.0, 0.0, 0.0, 1.0, 1.0)
        score = calc_score(0.0, 0.0, 0.0, 1.0, 1.0)
        assert score == 0.15
        assert tier == "D"
    
    def test_weights_sum_to_1(self):
        """All weights sum to 1.0."""
        assert 0.25 + 0.30 + 0.30 + 0.15 == 1.0

