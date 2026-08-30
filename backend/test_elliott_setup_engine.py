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


def wave_frame():
    return frame(range(1, 81))


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
    result = classify_wave_candidate(wave_frame(), wave_evidence())
    assert result["state"] in {"WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3"}
    assert result["state"] not in {"INVALIDATED", "EXTENDED"}
    assert "evidence" in result


def test_wave_candidates_cover_observable_phases():
    cases = [
        ({"pullback_depth_pct": None, "fib_zone": None}, "WAVE_1_ADVANCE"),
        ({"fib_zone": None}, "WAVE_2_FORMING"),
        ({}, "WAVE_2_NEAR_COMPLETION"),
        ({"breakout_confirmed": True}, "EARLY_WAVE_3"),
        ({"wave_3_continuation": True}, "WAVE_3_CONTINUATION"),
        ({"wave_4_correction": True}, "WAVE_4_CORRECTION"),
        ({"wave_5_advance": True}, "WAVE_5_ADVANCE"),
    ]
    for overrides, expected in cases:
        assert classify_wave_candidate(wave_frame(), wave_evidence(**overrides))["state"] == expected


def test_wave_missing_evidence_is_unknown_and_json_safe():
    result = classify_wave_candidate(wave_frame(), {"prior_advance": True})
    assert result["state"] == "UNKNOWN"
    assert result["evidence"]["missing_evidence"]
    json.dumps(result)
