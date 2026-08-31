import json

import pandas as pd

from elliott_structure_engine import classify_wave_candidate
from trade_setup_engine import _valid_ohlcv, build_trade_setup
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


def wave_close_breakout_frame():
    """Wave 1 advance, Wave 2 pullback, then a Daily Close above the Wave 1 high.

    Only one close above the Wave 1 high so the state is Early Wave 3, not an
    already-sustained Wave 3 continuation (spec §2.2 progression semantics).
    """
    return frame(list(range(1, 51)) + list(range(50, 39, -1)) + [50, 51])


def wave_wick_only_frame():
    """Wave 1 advance, Wave 2 pullback, then a High wick that fails to close above."""
    closes = list(range(1, 51)) + list(range(50, 39, -1)) + [48, 48.5, 49, 49.5]
    df = frame(closes)
    df.loc[df.index[-1], "High"] = 55.0
    return df


def wave_three_continuation_frame():
    return frame(list(range(1, 51)) + list(range(50, 29, -1)) + list(range(30, 61)))


def wave_four_frame():
    return frame(list(range(1, 51)) + list(range(50, 34, -1)) + list(range(35, 76)) + list(range(75, 54, -1)))


def wave_five_frame():
    return frame(list(range(1, 51)) + list(range(50, 34, -1)) + list(range(35, 76)) + list(range(75, 54, -1)) + list(range(55, 96)))


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


def test_missing_daily_history_is_unknown_and_fail_closed():
    result = classify_wave_candidate(None, {})
    assert result["state"] == "UNKNOWN"
    assert result["confidence"] == "INSUFFICIENT"
    assert "daily_ohlcv" in result["evidence"]["missing_evidence"]


def test_flat_ohlcv_candle_is_valid():
    flat = frame([10, 10, 10])
    assert _valid_ohlcv(flat)


def test_wave_candidate_is_structural_only():
    result = classify_wave_candidate(wave_two_frame(), wave_evidence())
    assert result["state"] in {"WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3"}
    assert result["state"] not in {"INVALIDATED", "EXTENDED"}
    assert "evidence" in result


def test_wave_candidates_cover_observable_phases():
    assert classify_wave_candidate(wave_frame(), wave_evidence(pullback_depth_pct=None, fib_zone=None))["state"] == "WAVE_1_ADVANCE"
    assert classify_wave_candidate(wave_two_frame(), wave_evidence(fib_zone=None))["state"] == "WAVE_2_FORMING"
    assert classify_wave_candidate(wave_two_frame(), wave_evidence())["state"] == "WAVE_2_NEAR_COMPLETION"
    assert classify_wave_candidate(wave_close_breakout_frame(), wave_evidence())["state"] == "EARLY_WAVE_3"
    assert classify_wave_candidate(wave_three_continuation_frame(), wave_evidence())["state"] == "WAVE_3_CONTINUATION"
    assert classify_wave_candidate(wave_four_frame(), wave_evidence())["state"] == "WAVE_4_CORRECTION"
    assert classify_wave_candidate(wave_five_frame(), wave_evidence())["state"] == "WAVE_5_ADVANCE"


def test_early_wave_three_requires_daily_close_above_wave1_high():
    """Spec §2.7 owner gate: wick alone = TESTED_HIGH, never a promotion."""
    wick = classify_wave_candidate(wave_wick_only_frame(), wave_evidence())
    assert wick["evidence"]["tested_high_only"] is True
    assert wick["state"] != "EARLY_WAVE_3"
    assert wick["state"] != "WAVE_3_CONTINUATION"
    close = classify_wave_candidate(wave_close_breakout_frame(), wave_evidence())
    assert close["evidence"]["close_above_wave1_high"] is True
    assert close["state"] in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"}


def test_wick_and_volume_markers_cannot_promote_without_close():
    """Volume/breakout markers are supporting evidence, never a standalone gate."""
    for markers in (
        wave_evidence(breakout_confirmed=True),
        wave_evidence(early_wave_3=True),
        wave_evidence(wave_3_continuation=True),
    ):
        result = classify_wave_candidate(wave_wick_only_frame(), markers)
        assert result["state"] not in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"}


def test_wave_four_and_five_markers_do_not_force_states_on_generic_rise():
    result = classify_wave_candidate(
        wave_frame(),
        wave_evidence(
            phase="WAVE_4_CORRECTION",
            candidate_state="WAVE_5_ADVANCE",
            wave_4_correction=True,
            wave_5_advance=True,
        ),
    )
    assert result["state"] == "WAVE_1_ADVANCE"
    assert result["state"] not in {"WAVE_4_CORRECTION", "WAVE_5_ADVANCE"}


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


def test_markers_are_metadata_and_cannot_change_a_measured_daily_state():
    daily = wave_three_continuation_frame()
    plain = classify_wave_candidate(daily, wave_evidence())
    marked = classify_wave_candidate(
        daily,
        wave_evidence(
            phase="WAVE_4_CORRECTION", candidate_state="INVALIDATED",
            wave_4_correction=True, wave_5_advance=True,
            wave_3_continuation=False, breakout_confirmed=False,
            early_wave_3=True,
        ),
    )
    assert plain["state"] == marked["state"] == "WAVE_3_CONTINUATION"


def test_markers_cannot_create_wave_four_or_five_from_unsupported_structure():
    daily = wave_frame()
    plain = classify_wave_candidate(daily, wave_evidence())
    marked = classify_wave_candidate(
        daily,
        wave_evidence(
            phase="WAVE_5_ADVANCE", candidate_state="WAVE_4_CORRECTION",
            wave_4_correction=True, wave_5_advance=True,
        ),
    )
    assert marked["state"] == plain["state"] == "WAVE_1_ADVANCE"


def test_wave_missing_evidence_is_unknown_and_json_safe():
    result = classify_wave_candidate(frame([10] * 10), {"prior_advance": True})
    assert result["state"] == "UNKNOWN"
    assert result["evidence"]["missing_evidence"]
    json.dumps(result)


def daily_wave_two_evidence():
    return {"timeframe": "daily", "state": "EARLY_WAVE_3", "evidence": {"structure_intact": True}}


def rising_60m_frame():
    close = list(range(100, 120)) + list(range(119, 109, -1)) + list(range(110, 118)) + [119]
    result = pd.DataFrame(
        {"Open": close, "High": [v + 1 for v in close], "Low": [v - 1 for v in close], "Close": close},
        # Volume is part of the 60m OHLCV contract, even though setup math
        # currently uses price fields only.
        index=pd.date_range("2026-08-30", periods=len(close), freq="h"),
    )
    result["Volume"] = 100
    result.attrs["timeframe"] = "60m"
    return result


def test_one_bar_rise_without_significant_pullback_is_data_blocked():
    frame_ = rising_60m_frame().iloc[:-5].copy()
    frame_.index = pd.date_range("2026-08-30", periods=len(frame_), freq="h")
    frame_.attrs["timeframe"] = "60m"
    result = build_trade_setup(daily_wave_two_evidence(), frame_)
    assert result["status"] == "DATA_BLOCKED"


def test_degenerate_leg_and_missing_pivot_confirmation_are_blocked():
    close = list(range(100, 111)) + list(range(109, 103, -1)) + [104, 105, 106]
    frame_ = pd.DataFrame(
        {"Open": close, "High": [v + 1 for v in close],
         "Low": [v - 1 for v in close], "Close": close,
         "Volume": 100},
        index=pd.date_range("2026-08-30", periods=len(close), freq="h"),
    )
    frame_.attrs["timeframe"] = "60m"
    assert build_trade_setup(daily_wave_two_evidence(), frame_)["status"] == "DATA_BLOCKED"


def test_invalid_timestamp_metadata_is_blocked():
    frame_ = rising_60m_frame()
    frame_.attrs["as_of"] = "not-a-timestamp"
    assert build_trade_setup(daily_wave_two_evidence(), frame_)["status"] == "DATA_BLOCKED"

    frame_ = rising_60m_frame()
    frame_.index = frame_.index[::-1]
    assert build_trade_setup(daily_wave_two_evidence(), frame_)["status"] == "DATA_BLOCKED"


def test_invalid_non_finite_helper_output_is_blocked():
    class BadFib:
        @staticmethod
        def compute_fib_targets(*args):
            return {"fib_1272": float("nan"), "fib_1618": float("inf")}

    result = build_trade_setup(daily_wave_two_evidence(), rising_60m_frame(), risk_helper=BadFib)
    assert result["status"] == "DATA_BLOCKED"


def test_early_wave_three_setup_has_trigger_stop_targets_and_rr():
    result = build_trade_setup(daily_wave_two_evidence(), rising_60m_frame())
    assert result["timeframe"] == "60m"
    assert result["state"] == "EARLY_WAVE_3"
    assert result["trigger"] is not None
    assert result["invalidation"] is not None
    assert result["targets"]
    assert result["rr"]["to_target_1"] >= 0


def test_wave_two_waiting_setup_is_forming_and_wave_state_stays_structural():
    wave = {"timeframe": "daily", "state": "WAVE_2_NEAR_COMPLETION"}
    result = build_trade_setup(wave, rising_60m_frame())
    assert result["status"] == "EXTENDED"
    assert result["state"] == "WAVE_2_NEAR_COMPLETION"
    assert result["state"] not in {"EXTENDED", "INVALIDATED"}


def test_wave_three_continuation_is_triggered():
    wave = {"timeframe": "daily", "state": "WAVE_3_CONTINUATION"}
    result = build_trade_setup(wave, rising_60m_frame())
    assert result["status"] == "EXTENDED"


def test_extended_is_setup_status_not_wave_state():
    frame_ = rising_60m_frame()
    frame_.loc[frame_.index[-1], ["High", "Close"]] = [160, 159]
    result = build_trade_setup(daily_wave_two_evidence(), frame_)
    assert result["status"] == "EXTENDED"
    assert result["state"] != "EXTENDED"


def test_invalidation_breach_is_setup_status_not_wave_state():
    frame_ = rising_60m_frame()
    frame_.loc[frame_.index[-1], ["Low", "Close"]] = [90, 90]
    result = build_trade_setup(daily_wave_two_evidence(), frame_)
    assert result["status"] == "INVALIDATED"
    assert result["state"] != "INVALIDATED"


def test_missing_60m_data_is_blocked_and_json_safe():
    result = build_trade_setup(daily_wave_two_evidence(), None)
    assert result["status"] == "DATA_BLOCKED"
    json.dumps(result)


def test_daily_timeframe_is_required_and_mismatch_is_blocked():
    frame_ = rising_60m_frame()
    assert build_trade_setup({"state": "EARLY_WAVE_3"}, frame_)["status"] == "DATA_BLOCKED"
    assert build_trade_setup({"timeframe": "1d", "state": "EARLY_WAVE_3"}, frame_)["status"] == "DATA_BLOCKED"


def test_intraday_timeframe_metadata_is_required_and_mismatch_is_blocked():
    frame_ = rising_60m_frame()
    frame_.attrs.pop("timeframe")
    assert build_trade_setup(daily_wave_two_evidence(), frame_)["status"] == "DATA_BLOCKED"
    frame_.attrs["timeframe"] = "15m"
    assert build_trade_setup(daily_wave_two_evidence(), frame_)["status"] == "DATA_BLOCKED"


def test_malformed_or_non_positive_ohlcv_is_blocked():
    for column, value in (("Open", float("nan")), ("High", float("inf")),
                          ("Low", 0), ("Close", -1), ("Volume", 0)):
        frame_ = rising_60m_frame()
        frame_[column] = frame_[column].astype(float)
        frame_.loc[frame_.index[-1], column] = value
        assert build_trade_setup(daily_wave_two_evidence(), frame_)["status"] == "DATA_BLOCKED"


def test_flat_structural_break_is_invalidated_not_data_blocked():
    frame_ = rising_60m_frame()
    frame_.loc[frame_.index[-2], ["Open", "High", "Low", "Close"]] = [50, 50, 50, 50]
    frame_.loc[frame_.index[-1], ["Open", "High", "Low", "Close"]] = [50, 50, 50, 50]
    assert build_trade_setup(daily_wave_two_evidence(), frame_)["status"] == "INVALIDATED"


def test_non_positive_reward_or_risk_is_blocked():
    frame_ = rising_60m_frame()

    class BadFib:
        @staticmethod
        def compute_fib_targets(*args):
            return {"fib_1272": args[0], "fib_1618": args[0], "status": "OK"}

    assert build_trade_setup(daily_wave_two_evidence(), frame_, risk_helper=BadFib)["status"] == "DATA_BLOCKED"


def test_status_precedence_and_boundaries_are_deterministic():
    frame_ = rising_60m_frame()
    frame_.loc[frame_.index[-1], ["High", "Close"]] = [160, 159]
    frame_.loc[frame_.index[-1], "Low"] = 90
    result = build_trade_setup(daily_wave_two_evidence(), frame_)
    assert result["status"] == "INVALIDATED"  # invalidation precedes extension

    frame_ = rising_60m_frame()
    frame_.loc[frame_.index[-1], ["Open", "High", "Low", "Close"]] = [117, 118, 116, 118]
    assert build_trade_setup(daily_wave_two_evidence(), frame_)["status"] == "EXTENDED"

    frame_ = rising_60m_frame()
    frame_.loc[frame_.index[-1], ["Open", "High", "Low", "Close"]] = [116, 117, 115, 117]
    assert build_trade_setup(daily_wave_two_evidence(), frame_)["status"] == "EXTENDED"
