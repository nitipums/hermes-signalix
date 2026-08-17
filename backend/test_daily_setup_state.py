import unittest

from daily_setup_state import classify_daily_state


BASE = {
    "close": 100.0,
    "rolling_trigger": 100.0,
    "volume_ratio_50": 1.5,
    "rsi_daily": 60.0,
    "trend_template_conditions": 8,
    "range_20d_pct": 20.0,
    "near_pullback_reference": False,
    "pre_break_pivot_low": 94.0,
}


def evidence(**overrides):
    value = dict(BASE)
    value.update(overrides)
    return value


class DailySetupStateTests(unittest.TestCase):
    def test_touching_trigger_stays_breakout_setup(self):
        result = classify_daily_state(evidence(close=100.0))
        self.assertEqual(result["primary_state"], "breakout_setup")
        self.assertEqual(result["distance_badge"], "near")

    def test_close_one_percent_above_trigger_with_volume_is_fresh_breakout(self):
        result = classify_daily_state(evidence(close=101.0))
        self.assertEqual(result["primary_state"], "fresh_breakout")
        self.assertEqual(result["origin"], "continuation")
        self.assertEqual(result["stage"], "fresh")

    def test_weak_volume_break_stays_setup(self):
        result = classify_daily_state(evidence(close=102.0, volume_ratio_50=1.19))
        self.assertEqual(result["primary_state"], "breakout_setup")
        self.assertEqual(result["failure_reason"], "weak_volume_break")

    def test_reversal_origin_is_attribute_not_competing_primary_state(self):
        result = classify_daily_state(evidence(close=102.0, trend_template_conditions=5))
        self.assertEqual(result["primary_state"], "fresh_breakout")
        self.assertEqual(result["origin"], "reversal")

    def test_active_event_in_three_percent_band_is_retest(self):
        result = classify_daily_state(
            evidence(close=101.5),
            event={"trigger_price": 100.0, "age_sessions": 2, "pivot_low": 94.0},
        )
        self.assertEqual(result["primary_state"], "breakout_retest")
        self.assertEqual(result["stage"], "retest")

    def test_active_event_with_rsi_75_is_extended_before_retest(self):
        result = classify_daily_state(
            evidence(close=101.0, rsi_daily=75.0),
            event={"trigger_price": 100.0, "age_sessions": 2, "pivot_low": 94.0},
        )
        self.assertEqual(result["primary_state"], "breakout_extended")

    def test_failure_uses_tighter_of_pivot_and_four_percent_risk_cap(self):
        result = classify_daily_state(
            evidence(close=95.9, pre_break_pivot_low=90.0),
            event={"trigger_price": 100.0, "age_sessions": 2, "pivot_low": 90.0},
        )
        self.assertEqual(result["failure_level"], 96.0)
        self.assertEqual(result["primary_state"], "no_long_setup")
        self.assertEqual(result["failure_reason"], "false_breakout")

    def test_qualified_fib_reference_is_trend_pullback_when_no_event(self):
        result = classify_daily_state(
            evidence(close=90.0, rolling_trigger=110.0, near_pullback_reference=True)
        )
        self.assertEqual(result["primary_state"], "trend_pullback")


if __name__ == "__main__":
    unittest.main()
