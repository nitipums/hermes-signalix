"""Tests for the canonical stage-first classifier (no DB needed)."""
import unittest

from stage_classifier import classify_stage, STAGE_LABELS, PHASE_LABELS


def ev(**kw):
    base = {
        "close": 10.0, "ma50": 9.5, "ma150": 9.2, "ma200": 9.0,
        "above_ma50": True, "above_ma150": True, "above_ma200": True,
        "ma50_slope_20d_pct": 1.0, "ma150_slope_20d_pct": 1.0, "ma200_slope_20d_pct": 1.0,
        "macd": 0.3, "rolling_trigger": None, "volume_ratio_50": 1.0,
        "rsi_daily": 55.0, "trend_template_conditions": 8, "range_20d_pct": 8.0,
        "near_pullback_reference": False, "vcp": False, "readiness_status": "HOLD",
        "data_freshness": "fresh",
    }
    base.update(kw)
    return base


class StageClassifierTests(unittest.TestCase):
    # ---- Stage 2: full bullish MA stack, all slopes up ----
    def test_S2_uptrend_full_stack(self):
        r = classify_stage(ev())
        self.assertEqual(r["stage"], "S2_uptrend")
        self.assertIn(r["phase"], ("uptrend_pullback", "waiting_breakout", "breakout_new"))

    # ---- Stage 4: declining stack (price below MA200, MA50<MA150) ----
    def test_S4_down_when_ma50_below_ma150(self):
        r = classify_stage(ev(close=8.0, ma50=8.5, ma150=9.0, ma200=9.2,
                              above_ma50=False, above_ma150=False, above_ma200=False,
                              ma50_slope_20d_pct=-2.0, ma150_slope_20d_pct=-2.0, ma200_slope_20d_pct=-2.0))
        self.assertEqual(r["stage"], "S4_down")
        self.assertEqual(r["phase"], "declining")

    def test_S4_down_below_ma200_falling_slope(self):
        r = classify_stage(ev(close=8.0, ma200=9.0, above_ma200=False, ma200_slope_20d_pct=-2.0))
        self.assertEqual(r["stage"], "S4_down")

    # ---- Stage 3: distribution (MA50 cuts below MA150) ----
    def test_S3_distributing_ma50_below_ma150(self):
        r = classify_stage(ev(close=10.0, ma50=8.8, ma150=9.0, ma200=8.5,
                              above_ma50=False, above_ma150=True, above_ma200=True,
                              ma50_slope_20d_pct=-1.0, ma150_slope_20d_pct=0.2, ma200_slope_20d_pct=0.3))
        self.assertEqual(r["stage"], "S3_distributing")
        self.assertEqual(r["phase"], "topping")

    # ---- Stage 1: basing (around MA200, slopes not all up) ----
    def test_S1_basing_flat_slopes(self):
        r = classify_stage(ev(close=9.5, ma50=9.2, ma150=9.1, ma200=9.0,
                              above_ma50=True, above_ma150=True, above_ma200=True,
                              ma50_slope_20d_pct=0.2, ma150_slope_20d_pct=0.1, ma200_slope_20d_pct=0.2))
        self.assertEqual(r["stage"], "S1_basing")
        self.assertIn(r["phase"], ("base_early", "base_tight"))

    def test_S1_base_tight_with_vcp(self):
        r = classify_stage(ev(close=9.5, ma50=9.2, ma150=9.1, ma200=9.0,
                              above_ma50=True, above_ma150=True, above_ma200=True,
                              ma50_slope_20d_pct=0.2, ma150_slope_20d_pct=0.1, ma200_slope_20d_pct=0.2,
                              vcp=True, range_20d_pct=8.0))
        self.assertEqual(r["stage"], "S1_basing")
        self.assertEqual(r["phase"], "base_tight")

    # ---- Phase within S2 ----
    def test_S2_uptrend_pullback(self):
        r = classify_stage(ev(ma200_slope_20d_pct=1.5, near_pullback_reference=True))
        self.assertEqual(r["stage"], "S2_uptrend")
        self.assertEqual(r["phase"], "uptrend_pullback")

    def test_S2_breakout_new_via_trigger(self):
        # Volume is NOT a gate (layer-2 hint only); a close through the 20d
        # trigger is a breakout regardless of volume.
        r = classify_stage(ev(ma200_slope_20d_pct=2.0, rolling_trigger=9.8,
                              close=10.0, volume_ratio_50=0.3))
        self.assertEqual(r["stage"], "S2_uptrend")
        self.assertEqual(r["phase"], "breakout_new")

    def test_breakout_phase_independent_of_volume(self):
        # Same setup, low vs high volume -> identical phase (volume is quality only).
        low = classify_stage(ev(rolling_trigger=9.8, close=10.0, volume_ratio_50=0.2))
        high = classify_stage(ev(rolling_trigger=9.8, close=10.0, volume_ratio_50=3.0))
        self.assertEqual(low["phase"], high["phase"])
        self.assertEqual(low["phase"], "breakout_new")

    def test_S2_waiting_breakout_near_trigger(self):
        r = classify_stage(ev(ma200_slope_20d_pct=2.0, rolling_trigger=10.3,
                              close=10.1, volume_ratio_50=0.8))
        self.assertEqual(r["stage"], "S2_uptrend")
        self.assertEqual(r["phase"], "waiting_breakout")

    # ---- Quality layer is separate (never changes stage) ----
    def test_quality_hints_present_and_independent(self):
        r = classify_stage(ev(rsi_daily=82, macd=-0.1, volume_ratio_50=0.3))
        self.assertIn("quality", r)
        self.assertIn("overbought", r["quality"]["flags"])
        self.assertIn("macd_stalling", r["quality"]["flags"])
        self.assertIn("low_volume", r["quality"]["flags"])
        # quality must NOT have flipped the stage away from a clean uptrend
        self.assertEqual(r["stage"], "S2_uptrend")

    def test_readiness_is_hint_not_group(self):
        r = classify_stage(ev(readiness_status="BUY"))
        self.assertEqual(r["readiness_hint"], "BUY")
        self.assertNotIn("readiness_status", r)  # not a grouping key

    # ---- Determinism + single stage/phase ----
    def test_deterministic_same_input_same_output(self):
        a = classify_stage(ev())
        b = classify_stage(ev())
        self.assertEqual(a["stage"], b["stage"])
        self.assertEqual(a["phase"], b["phase"])

    def test_single_stage_phase_no_overlap(self):
        r = classify_stage(ev())
        self.assertIn(r["stage"], STAGE_LABELS)
        self.assertIn(r["phase"], PHASE_LABELS)
        # exactly one stage, one phase
        self.assertIsInstance(r["stage"], str)
        self.assertIsInstance(r["phase"], str)


if __name__ == "__main__":
    unittest.main()
