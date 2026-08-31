import json

import pandas as pd

from test_elliott_setup_engine import daily_wave_two_evidence, rising_60m_frame
from trade_setup_engine import ANCHOR_POLICY, _intraday_anchors, build_trade_setup


class GoodFib:
    @staticmethod
    def compute_fib_targets(*args):
        swing_low, swing_high, pullback_low = args
        return {"fib_1272": swing_high + 2 * (swing_high - swing_low),
                "fib_1618": swing_high + 3 * (swing_high - swing_low),
                "status": "OK"}


def anchor_frame(closes):
    frame = pd.DataFrame(
        {
            "Open": closes,
            "High": [value + 1 for value in closes],
            "Low": [value - 1 for value in closes],
            "Close": closes,
            "Volume": [100] * len(closes),
        },
        index=pd.date_range("2026-08-31", periods=len(closes), freq="h"),
    )
    frame.attrs["timeframe"] = "60m"
    return frame


def test_one_bar_up_leg_and_pullback_produce_versioned_anchors():
    anchors = _intraday_anchors(anchor_frame([110, 100, 104, 103]))

    assert ANCHOR_POLICY == "relaxed-1bar-scaled-20260831"
    assert anchors["anchor_policy"] == ANCHOR_POLICY
    assert anchors["trigger"] == 105
    assert anchors["invalidation"] == 99
    assert anchors["pullback_low"] == 102


def test_one_bar_pullback_between_one_and_three_pct_passes():
    assert _intraday_anchors(anchor_frame([100, 98, 102, 101]))


def test_one_bar_pullback_noise_below_one_pct_fails_closed():
    assert _intraday_anchors(anchor_frame([100, 99.8, 104, 103])) == {}


def test_one_bar_advance_between_one_and_three_pct_passes():
    assert _intraday_anchors(anchor_frame([104, 100, 102, 101]))


def test_one_bar_advance_noise_below_one_pct_fails_closed():
    assert _intraday_anchors(anchor_frame([104, 100, 100.2, 100.1])) == {}


def test_two_bar_pullback_still_requires_three_pct():
    assert _intraday_anchors(anchor_frame([100, 99, 98, 100, 102, 101])) == {}


def test_two_bar_advance_still_requires_three_pct():
    assert _intraday_anchors(anchor_frame([104, 102, 100, 101, 102, 101])) == {}


def test_no_up_step_returns_no_anchors():
    assert _intraday_anchors(anchor_frame([110, 105, 100, 99])) == {}


def test_flat_or_insufficient_intraday_data_fails_closed():
    assert _intraday_anchors(anchor_frame([100, 100, 100])) == {}
    assert _intraday_anchors(anchor_frame([100, 96])) == {}


def test_wick_test_is_not_a_completed_trigger():
    tested = rising_60m_frame()
    tested.loc[tested.index[-1], ["Open", "High", "Low", "Close"]] = [117, 119, 116, 117]
    triggered = tested.copy()
    triggered.loc[triggered.index[-1], ["Open", "High", "Low", "Close"]] = [118, 119, 116, 118]
    assert build_trade_setup(daily_wave_two_evidence(), tested, risk_helper=GoodFib)["status"] == "TESTED_TRIGGER"
    assert build_trade_setup(daily_wave_two_evidence(), triggered, risk_helper=GoodFib)["status"] == "TRIGGERED"


def test_entry_zone_is_bounded_by_risk():
    result = build_trade_setup(daily_wave_two_evidence(), rising_60m_frame(), risk_helper=GoodFib)
    trigger = result["trigger"]
    invalidation = result["invalidation"]
    risk = trigger - invalidation
    assert result["entry_zone"] == {
        "low": round(trigger - 0.25 * risk, 4),
        "high": round(trigger + 0.5 * risk, 4),
    }


def test_target_one_rr_is_the_minimum_gate():
    class LowFib(GoodFib):
        @staticmethod
        def compute_fib_targets(*args):
            _, high, _ = args
            return {"fib_1272": high + 1, "fib_1618": high + 100, "status": "OK"}

    low = build_trade_setup(daily_wave_two_evidence(), rising_60m_frame(), risk_helper=LowFib)
    good = build_trade_setup(daily_wave_two_evidence(), rising_60m_frame(), risk_helper=GoodFib)
    assert low["status"] == "EXTENDED"
    assert low["reason"] == "do_not_chase_below_2_to_1"
    assert good["rr"]["to_target_1"] >= 2
    assert good["status"] != "EXTENDED"


def test_invalidation_precedes_extension():
    frame = rising_60m_frame()
    frame.loc[frame.index[-1], ["Low", "Close", "High"]] = [90, 160, 161]
    result = build_trade_setup(daily_wave_two_evidence(), frame, risk_helper=GoodFib)
    assert result["status"] == "INVALIDATED"


def test_expiry_uses_as_of_without_wall_clock():
    frame = rising_60m_frame()
    frame.attrs["as_of"] = frame.index[-1] + pd.Timedelta(days=4)
    expired = build_trade_setup(daily_wave_two_evidence(), frame, risk_helper=GoodFib)
    assert expired["status"] == "EXPIRED"
    frame.attrs["as_of"] = frame.index[-1] + pd.Timedelta(days=2)
    assert build_trade_setup(daily_wave_two_evidence(), frame, risk_helper=GoodFib)["status"] != "EXPIRED"


def test_thesis_invalidation_is_separate_from_trade_stop():
    wave = {**daily_wave_two_evidence(), "thesis_invalidation": 10.8}
    result = build_trade_setup(wave, rising_60m_frame(), risk_helper=GoodFib)
    assert result["thesis_invalidation"] == 10.8
    assert result["thesis_invalidation"] != result["trade_stop"]
    assert result["risk_stop_separate"] is True
    json.dumps(result)
