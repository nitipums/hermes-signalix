import json

import pandas as pd

from test_elliott_setup_engine import daily_wave_two_evidence, rising_60m_frame
from trade_setup_engine import build_trade_setup


class GoodFib:
    @staticmethod
    def compute_fib_targets(*args):
        swing_low, swing_high, pullback_low = args
        return {"fib_1272": swing_high + 2 * (swing_high - swing_low),
                "fib_1618": swing_high + 3 * (swing_high - swing_low),
                "status": "OK"}


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
