"""Tests for the draft stage-first classifier (no DB needed)."""
import unittest

from stage_classifier import classify_stage, STAGE_LABELS, PHASE_LABELS


def ev(**kw):
    base = {
        "close": 10.0, "ma200": 9.0, "ma200_slope_20d_pct": 1.0,
        "above_ma200": True, "rolling_trigger": None, "volume_ratio_50": 1.0,
        "rsi_daily": 55.0, "trend_template_conditions": 8, "range_20d_pct": 8.0,
        "near_pullback_reference": False, "vcp": False, "readiness_status": "HOLD",
        "data_freshness": "fresh",
    }
    base.update(kw)
    return base


class StageClassifierTests(unittest.TestCase):
    def test_S4_down_when_below_ma200(self):
        r = classify_stage(ev(close=8.0, ma200=9.0, above_ma200=False,
                              ma200_slope_20d_pct=-2.0))
        self.assertEqual(r["stage"], "S4_down")
        self.assertEqual(r["phase"], "declining")

    def test_S1_basing_flat_ma200(self):
        r = classify_stage(ev(close=9.0, ma200=9.0, above_ma200=False,
                              ma200_slope_20d_pct=0.2))
        self.assertEqual(r["stage"], "S1_basing")
        self.assertIn(r["phase"], ("base_early", "base_tight"))

    def test_S1_base_tight_with_vcp(self):
        r = classify_stage(ev(close=9.0, ma200=9.0, above_ma200=False,
                              ma200_slope_20d_pct=0.2, vcp=True,
                              range_20d_pct=8.0))
        self.assertEqual(r["stage"], "S1_basing")
        self.assertEqual(r["phase"], "base_tight")

    def test_S2_uptrend_pullback(self):
        r = classify_stage(ev(ma200_slope_20d_pct=1.5, near_pullback_reference=True))
        self.assertEqual(r["stage"], "S2_uptrend")
        self.assertEqual(r["phase"], "uptrend_pullback")

    def test_S2_breakout_new_via_trigger(self):
        r = classify_stage(ev(ma200_slope_20d_pct=2.0, rolling_trigger=9.8,
                              volume_ratio_50=1.5, close=10.0))
        self.assertEqual(r["stage"], "S2_uptrend")
        self.assertEqual(r["phase"], "breakout_new")

    def test_S2_waiting_breakout_near_trigger(self):
        r = classify_stage(ev(ma200_slope_20d_pct=2.0, rolling_trigger=10.3,
                              close=10.1, volume_ratio_50=0.8))
        self.assertEqual(r["stage"], "S2_uptrend")
        self.assertEqual(r["phase"], "waiting_breakout")

    def test_S3_distributing_falling_slope_above_ma(self):
        r = classify_stage(ev(close=11.0, ma200=10.0, above_ma200=True,
                              ma200_slope_20d_pct=-1.0))
        self.assertEqual(r["stage"], "S3_distributing")
        self.assertEqual(r["phase"], "topping")

    def test_event_false_breakout_is_broken(self):
        r = classify_stage(ev(ma200_slope_20d_pct=2.0, rolling_trigger=10.0, close=9.4),
                          event={"trigger_price": 10.0, "pivot_low": 9.5,
                                 "age_sessions": 3})
        self.assertEqual(r["phase"], "broken")

    def test_event_extended(self):
        r = classify_stage(ev(ma200_slope_20d_pct=2.0, rolling_trigger=10.0,
                              rsi_daily=80.0, close=11.0),
                          event={"trigger_price": 10.0, "pivot_low": 9.5,
                                 "age_sessions": 1})
        self.assertEqual(r["phase"], "breakout_extended")

    def test_deterministic_same_input_same_output(self):
        a = classify_stage(ev(ma200_slope_20d_pct=1.5, near_pullback_reference=True))
        b = classify_stage(ev(ma200_slope_20d_pct=1.5, near_pullback_reference=True))
        self.assertEqual(a, b)

    def test_single_stage_phase_no_overlap(self):
        r = classify_stage(ev(ma200_slope_20d_pct=1.5, near_pullback_reference=True))
        self.assertIn(r["stage"], STAGE_LABELS)
        self.assertIn(r["phase"], PHASE_LABELS)
        self.assertEqual(len([k for k in r if k in ("stage", "phase")]), 2)

    def test_readiness_is_hint_not_group(self):
        r = classify_stage(ev(readiness_status="BUY"))
        # readiness_status must be a hint field, not change the stage/phase
        self.assertNotIn("BUY", (r["stage"], r["phase"]))
        self.assertEqual(r["readiness_hint"], "BUY")


if __name__ == "__main__":
    unittest.main()
