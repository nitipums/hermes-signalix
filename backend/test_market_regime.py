"""Signalix — Market Regime Test Fixtures (Contract v0.2.0 §7, §8).

Fixtures per Canonical Contract:
- FX-REGIME-001: atr_pct_20d=4.0, finite spread, no liquidity event → HIGH_VOLATILITY
- FX-REGIME-002: volatility below 4, liquidity_event_flag=true → LIQUIDITY_EVENT
- FX-REGIME-003: volatility below 4, no liquidity event, spread exactly 25 → LOW_SPREAD
- FX-REGIME-004: all valid, volatility below 4, spread above 25 → NORMAL
- FX-REGIME-101: atr_pct_20d=NaN → NORMAL, INVALID_NONFINITE_INPUT
- FX-REGIME-102: negative spread → invalid input, no LOW_SPREAD classification
- FX-REGIME-103: missing volatility → NORMAL, REGIME_INPUT_MISSING, never guessed
"""

import math
import pytest
from market_regime import (
    compute_regime,
    RegimeInputs,
    REGIME_POLICY_VERSION,
    REASON_REGIME_INPUT_MISSING,
    REASON_INVALID_NEGATIVE_INPUT,
    REASON_INVALID_NONFINITE_INPUT,
)


class TestRegimeFixtures:
    """Contract v0.2.0 §7 Valid/Invalid Fixtures."""

    # ----- Valid Fixtures -----

    def test_FX_REGIME_001_high_volatility(self):
        """V=4.0, finite spread, no liquidity event → HIGH_VOLATILITY"""
        inputs = RegimeInputs(
            atr_pct_20d=4.0,
            median_spread_bps=30.0,
            liquidity_event_flag=False,
            breadth_pct_above_ma50=55.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "HIGH_VOLATILITY"
        assert result.reason_codes == []
        assert result.policy_version == REGIME_POLICY_VERSION

    def test_FX_REGIME_002_liquidity_event(self):
        """V<4, liquidity_event_flag=true → LIQUIDITY_EVENT"""
        inputs = RegimeInputs(
            atr_pct_20d=3.5,
            median_spread_bps=30.0,
            liquidity_event_flag=True,
            breadth_pct_above_ma50=55.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "LIQUIDITY_EVENT"
        assert result.reason_codes == []

    def test_FX_REGIME_003_low_spread(self):
        """V<4, no liquidity event, spread exactly 25 → LOW_SPREAD"""
        inputs = RegimeInputs(
            atr_pct_20d=3.0,
            median_spread_bps=25.0,
            liquidity_event_flag=False,
            breadth_pct_above_ma50=55.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "LOW_SPREAD"
        assert result.reason_codes == []

    def test_FX_REGIME_004_normal(self):
        """All valid, V<4, spread>25 → NORMAL"""
        inputs = RegimeInputs(
            atr_pct_20d=2.5,
            median_spread_bps=30.0,
            liquidity_event_flag=False,
            breadth_pct_above_ma50=55.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "NORMAL"
        assert result.reason_codes == []

    # ----- Invalid Fixtures -----

    def test_FX_REGIME_101_nan_volatility(self):
        """atr_pct_20d=NaN → NORMAL, INVALID_NONFINITE_INPUT"""
        inputs = RegimeInputs(
            atr_pct_20d=float("nan"),
            median_spread_bps=30.0,
            liquidity_event_flag=False,
            breadth_pct_above_ma50=55.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "NORMAL"
        assert REASON_INVALID_NONFINITE_INPUT in result.reason_codes

    def test_FX_REGIME_102_negative_spread(self):
        """negative spread → invalid input, no LOW_SPREAD classification"""
        inputs = RegimeInputs(
            atr_pct_20d=3.0,
            median_spread_bps=-5.0,
            liquidity_event_flag=False,
            breadth_pct_above_ma50=55.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "NORMAL"
        assert REASON_INVALID_NEGATIVE_INPUT in result.reason_codes
        # Must NOT be LOW_SPREAD despite spread <= 25
        assert result.regime_state != "LOW_SPREAD"

    def test_FX_REGIME_103_missing_volatility(self):
        """missing volatility → NORMAL, REGIME_INPUT_MISSING, never guessed"""
        inputs = RegimeInputs(
            atr_pct_20d=None,
            median_spread_bps=30.0,
            liquidity_event_flag=False,
            breadth_pct_above_ma50=55.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "NORMAL"
        assert REASON_REGIME_INPUT_MISSING in result.reason_codes


class TestRegimeBoundaryBehavior:
    """Contract v0.2.0 §3.2 Boundary behavior tests."""

    def test_V_equals_4_is_high_volatility(self):
        """V = 4.0 → HIGH_VOLATILITY"""
        inputs = RegimeInputs(
            atr_pct_20d=4.0,
            median_spread_bps=20.0,  # would be LOW_SPREAD if not for HIGH_VOL
            liquidity_event_flag=True,  # would be LIQUIDITY_EVENT if not for HIGH_VOL
            breadth_pct_above_ma50=50.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "HIGH_VOLATILITY"

    def test_S_equals_25_is_low_spread_when_no_higher_precedence(self):
        """S = 25.0 → LOW_SPREAD only when neither HIGH_VOL nor LIQUIDITY"""
        inputs = RegimeInputs(
            atr_pct_20d=3.9,  # < 4.0
            median_spread_bps=25.0,
            liquidity_event_flag=False,
            breadth_pct_above_ma50=50.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "LOW_SPREAD"

    def test_negative_V_invalid_input(self):
        """Negative V → NORMAL + INVALID_NEGATIVE_INPUT"""
        inputs = RegimeInputs(
            atr_pct_20d=-1.0,
            median_spread_bps=20.0,
            liquidity_event_flag=False,
            breadth_pct_above_ma50=50.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "NORMAL"
        assert REASON_INVALID_NEGATIVE_INPUT in result.reason_codes

    def test_infinity_V_invalid_input(self):
        """Infinity V → NORMAL + INVALID_NONFINITE_INPUT"""
        inputs = RegimeInputs(
            atr_pct_20d=float("inf"),
            median_spread_bps=20.0,
            liquidity_event_flag=False,
            breadth_pct_above_ma50=50.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "NORMAL"
        assert REASON_INVALID_NONFINITE_INPUT in result.reason_codes

    def test_negative_S_invalid_input(self):
        """Negative S → NORMAL + INVALID_NEGATIVE_INPUT, never LOW_SPREAD"""
        inputs = RegimeInputs(
            atr_pct_20d=3.0,
            median_spread_bps=-10.0,
            liquidity_event_flag=False,
            breadth_pct_above_ma50=50.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "NORMAL"
        assert REASON_INVALID_NEGATIVE_INPUT in result.reason_codes


class TestRegimePrecedence:
    """Verify precedence: HIGH_VOL > LIQUIDITY_EVENT > LOW_SPREAD > NORMAL"""

    def test_high_vol_beats_liquidity_event(self):
        """HIGH_VOLATILITY takes precedence over LIQUIDITY_EVENT"""
        inputs = RegimeInputs(
            atr_pct_20d=5.0,  # HIGH_VOL
            median_spread_bps=20.0,
            liquidity_event_flag=True,  # would be LIQUIDITY_EVENT
            breadth_pct_above_ma50=50.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "HIGH_VOLATILITY"

    def test_liquidity_event_beats_low_spread(self):
        """LIQUIDITY_EVENT takes precedence over LOW_SPREAD"""
        inputs = RegimeInputs(
            atr_pct_20d=3.0,  # < 4.0
            median_spread_bps=20.0,  # would be LOW_SPREAD
            liquidity_event_flag=True,  # LIQUIDITY_EVENT
            breadth_pct_above_ma50=50.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "LIQUIDITY_EVENT"

    def test_low_spread_beats_normal(self):
        """LOW_SPREAD takes precedence over NORMAL"""
        inputs = RegimeInputs(
            atr_pct_20d=3.0,
            median_spread_bps=20.0,  # LOW_SPREAD
            liquidity_event_flag=False,
            breadth_pct_above_ma50=50.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)
        assert result.regime_state == "LOW_SPREAD"


class TestRegimeOutputContract:
    """Verify output contract compliance."""

    def test_output_has_all_required_fields(self):
        """RegimeOutput must have all §3.1 fields"""
        inputs = RegimeInputs(
            atr_pct_20d=3.0,
            median_spread_bps=30.0,
            liquidity_event_flag=False,
            breadth_pct_above_ma50=55.0,
            benchmark_at_or_above_ma50=True,
        )
        result = compute_regime(inputs)

        # Check all required fields present
        d = result.to_dict()
        assert "regime_state" in d
        assert "reason_codes" in d
        assert "inputs" in d
        assert "policy_version" in d
        assert "data_timestamp_utc" in d
        assert "computed_at_utc" in d

        # Timestamps must be ISO-8601 UTC with Z suffix
        assert d["data_timestamp_utc"].endswith("Z")
        assert d["computed_at_utc"].endswith("Z")

        # Policy version must match
        assert d["policy_version"] == REGIME_POLICY_VERSION

    def test_reason_codes_deduplicated(self):
        """Reason codes should be deduplicated"""
        inputs = RegimeInputs(
            atr_pct_20d=None,
            median_spread_bps=None,
            liquidity_event_flag=None,
            breadth_pct_above_ma50=None,
            benchmark_at_or_above_ma50=None,
        )
        result = compute_regime(inputs)
        # Should only have one REGIME_INPUT_MISSING despite multiple missing
        assert result.reason_codes.count(REASON_REGIME_INPUT_MISSING) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])