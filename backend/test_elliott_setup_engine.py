import json

import pandas as pd

from elliott_structure_engine import classify_wave_candidate
from trend_strength_engine import compute_trend_strength


def frame(values):
    close = pd.Series(values, dtype=float)
    return pd.DataFrame({"Close": close, "Open": close, "High": close, "Low": close, "Volume": 1})


def rising_daily_frame():
    return frame(list(range(1, 81)))


def test_trend_exposes_high_and_strength_evidence():
    result = compute_trend_strength(rising_daily_frame(), relative_strength=91.0)
    assert result["state"] in {"uptrend", "emerging_uptrend"}
    assert result["relative_strength"] == 91.0
    assert {"near_52w_high", "is_52w_high_breakout", "is_ath_breakout"} <= result.keys()


def test_trend_high_and_ath_breakouts_are_explicit():
    result = compute_trend_strength(frame([10] * 252 + [11]), prior_ath=10)
    assert result["is_52w_high_breakout"] is True
    assert result["is_ath_breakout"] is True
    assert result["near_52w_high"] is True


def test_trend_insufficient_history_keeps_unknown_metrics_explicit():
    result = compute_trend_strength(frame([10, 11, 12]), relative_strength=None)
    assert result["state"] == "UNKNOWN"
    assert result["rise_20d_pct"] is None
    assert result["relative_strength"] is None
    assert result["near_52w_high"] is None
    assert result["is_52w_high_breakout"] is None
    assert result["is_ath_breakout"] is None


def test_short_history_can_use_explicit_ath_but_not_invent_a_52w_reference():
    result = compute_trend_strength(frame([10, 11, 12]), prior_ath=11)
    assert result["is_ath_breakout"] is True
    assert result["near_52w_high"] is None
    assert result["is_52w_high_breakout"] is None


def test_trend_flat_and_falling_states_are_explicit():
    assert compute_trend_strength(frame([10] * 80))["state"] == "flat"
    assert compute_trend_strength(frame(range(80, 0, -1)))["state"] == "downtrend"


def wave_frame():
    return frame(range(1, 81))


def wave_two_frame():
    return frame(list(range(1, 61)) + list(range(60, 39, -1)))


def wave_rebound_frame():
    return frame(list(range(1, 51)) + list(range(50, 29, -1)) + [30.5, 31, 32, 33, 34])


def wave_evidence(**overrides):
    evidence = {
        "prior_advance": True,
        "confirmed_swing_anchors": True,
        "structure_intact": True,
        "pullback_depth_pct": 12.0,
        "pullback_duration_days": 20,
        "fib_zone": "0.5-0.618",
    }
    evidence.update(overrides)
    return evidence


def test_wave_candidate_is_structural_only():
    result = classify_wave_candidate(wave_two_frame(), wave_evidence())
    assert result["state"] in {"WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3"}
    assert result["state"] not in {"INVALIDATED", "EXTENDED"}
    assert "evidence" in result


def test_wave_candidates_cover_observable_phases():
    assert classify_wave_candidate(wave_frame(), wave_evidence(pullback_depth_pct=None, fib_zone=None))["state"] == "WAVE_1_ADVANCE"
    assert classify_wave_candidate(wave_two_frame(), wave_evidence(fib_zone=None))["state"] == "WAVE_2_FORMING"
    assert classify_wave_candidate(wave_two_frame(), wave_evidence())["state"] == "WAVE_2_NEAR_COMPLETION"
    assert classify_wave_candidate(wave_rebound_frame(), wave_evidence(breakout_confirmed=True))["state"] == "EARLY_WAVE_3"
    assert classify_wave_candidate(wave_rebound_frame(), wave_evidence(wave_3_continuation=True))["state"] == "WAVE_3_CONTINUATION"
    assert classify_wave_candidate(wave_two_frame(), wave_evidence(wave_4_correction=True))["state"] == "WAVE_4_CORRECTION"
    assert classify_wave_candidate(wave_frame(), wave_evidence(wave_5_advance=True))["state"] == "WAVE_5_ADVANCE"


def test_arbitrary_markers_cannot_force_wave_state_on_flat_or_falling_data():
    markers = wave_evidence(
        phase="WAVE_5_ADVANCE", candidate_state="EARLY_WAVE_3",
        wave_5_advance=True, wave_4_correction=True,
        wave_3_continuation=True, breakout_confirmed=True, early_wave_3=True,
    )
    for daily in (frame([10] * 80), frame(range(80, 0, -1))):
        result = classify_wave_candidate(daily, markers)
        assert result["state"] == "UNKNOWN"
        assert result["state"] not in {"INVALIDATED", "EXTENDED"}


def test_wave_missing_evidence_is_unknown_and_json_safe():
    result = classify_wave_candidate(frame([10] * 10), {"prior_advance": True})
    assert result["state"] == "UNKNOWN"
    assert result["evidence"]["missing_evidence"]
    json.dumps(result)
