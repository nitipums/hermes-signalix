"""R1 remediation (t_3ae98ae4): breakout_retest phase must be emitted.

Contract: stage_classifier.classify_stage emits phase="breakout_retest"
when a persisted breakout event exists, age_sessions >= 1, and the close is
within RETEST_TOLERANCE_PCT of the original trigger. action_queue maps that
phase to retest_watch. This closes Ploy challenge C1 (Retest Watch was
unreachable because no classifier path produced the phase).
"""
import unittest

from stage_classifier import classify_stage
from action_queue import assign_action_queue


def ev(**kw):
    base = {
        "close": 10.0,
        "ma50": 9.0, "ma150": 8.5, "ma200": 8.0,
        "above_ma50": True, "above_ma150": True, "above_ma200": True,
        "ma50_slope_20d_pct": 1.0, "ma150_slope_20d_pct": 1.0,
        "ma200_slope_20d_pct": 1.0,
        "rolling_trigger": 9.8,
        "volume_ratio_50": 1.0,
        "rsi_daily": 60.0,
        "trend_template_conditions": 8,
        "range_20d_pct": 10.0,
    }
    base.update(kw)
    return base


class BreakoutRetestPhaseTests(unittest.TestCase):
    def test_event_retest_window_emits_breakout_retest_phase(self):
        r = classify_stage(ev(), event={
            "trigger_price": 9.8, "age_sessions": 2, "pivot_low": 9.4})
        self.assertEqual(r["stage"], "S2_uptrend")
        self.assertEqual(r["phase"], "breakout_retest")
        self.assertEqual(r["primary_state"], "breakout_retest")

    def test_fresh_event_within_two_sessions_is_not_retest(self):
        # close well above trigger, age<=2 -> fresh, not retest
        r = classify_stage(ev(close=10.5), event={
            "trigger_price": 9.8, "age_sessions": 0, "pivot_low": 9.4})
        self.assertEqual(r["phase"], "breakout_new")
        self.assertEqual(r["primary_state"], "fresh_breakout")

    def test_no_event_never_yields_retest_phase(self):
        r = classify_stage(ev())
        self.assertNotEqual(r["phase"], "breakout_retest")

    def test_classifier_phase_feeds_retest_watch_queue(self):
        r = classify_stage(ev(), event={
            "trigger_price": 9.8, "age_sessions": 2, "pivot_low": 9.4})
        q = assign_action_queue(
            stage=r["stage"], phase=r["phase"],
            quality_pass=True, proximity_state=None,
            intraday_event={"status": "active", "trigger_price": 9.8,
                            "age_sessions": 2, "pivot_low": 9.4})
        self.assertEqual(q, "retest_watch")


if __name__ == "__main__":
    unittest.main()
