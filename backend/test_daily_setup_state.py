import unittest

from daily_setup_state import classify_daily_state, PRIMARY_STATES


BASE = {
    "close": 100.0,
    "rolling_trigger": 100.0,
    "volume_ratio_50": 1.5,
    "rsi_daily": 60.0,
    "trend_template_conditions": 8,
    "range_20d_pct": 20.0,
    "near_pullback_reference": False,
    "pre_break_pivot_low": 94.0,
    "ma50": 101.0, "ma150": 100.0, "ma200": 99.0,
    "above_ma50": True, "above_ma150": True, "above_ma200": True,
    "ma50_slope_20d_pct": 1.0, "ma150_slope_20d_pct": 1.0, "ma200_slope_20d_pct": 1.0,
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
        self.assertEqual(result["stage"], "S2_uptrend")

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
        self.assertEqual(result["stage"], "S2_uptrend")

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

    # --- P0 contract: exactly 7 canonical states, no extras ---
    def test_canonical_state_set_has_exactly_seven(self):
        self.assertEqual(len(PRIMARY_STATES), 7)
        self.assertSetEqual(set(PRIMARY_STATES), {
            "breakout_setup", "fresh_breakout", "breakout_retest", "breakout_extended",
            "trend_pullback", "base_forming", "no_long_setup",
        })

    def test_breakdown_candidate_maps_to_no_long_setup(self):
        """breakdown_candidate is not a contract state; must unify to no_long_setup."""
        result = classify_daily_state(evidence(close=80.0, change_pct=-10.0,
                                               above_ma50=False, above_ma150=False,
                                               above_ma200=False,
                                               ma50_slope_20d_pct=-1.0,
                                               ma150_slope_20d_pct=-1.0,
                                               ma200_slope_20d_pct=-1.0))
        self.assertEqual(result["primary_state"], "no_long_setup")
        self.assertEqual(result["failure_reason"], "recent_breakdown")

    def test_base_forming_state_when_no_trigger(self):
        result = classify_daily_state(evidence(close=100.0, rolling_trigger=None,
                                               range_20d_pct=8.0,
                                               near_pullback_reference=False,
                                               change_pct=0.0,
                                               trend_template_conditions=8))
        self.assertEqual(result["primary_state"], "base_forming")

    def test_no_long_setup_when_no_qualified_structure(self):
        result = classify_daily_state(evidence(close=100.0, rolling_trigger=None,
                                               range_20d_pct=20.0,
                                               near_pullback_reference=False,
                                               change_pct=0.0,
                                               trend_template_conditions=8))
        self.assertEqual(result["primary_state"], "no_long_setup")
        self.assertEqual(result["failure_reason"], "no_qualified_structure")

    def test_result_has_all_contract_fields(self):
        result = classify_daily_state(evidence(close=100.0))
        for field in ("primary_state", "origin", "stage", "reference_level",
                      "failure_level", "proof_needed", "failure_reason",
                      "distance_badge", "trendState", "setupState",
                      "lifecycleState", "action", "eligibility", "dataFreshness"):
            self.assertIn(field, result, f"missing {field}")

    def test_stage_is_always_minervini_s1_s4(self):
        for close in (100.0, 101.0, 95.9, 90.0):
            result = classify_daily_state(evidence(close=close))
            self.assertIn(result["stage"], ("S1_basing", "S2_uptrend", "S3_distributing", "S4_down"))

    def test_stage_s4_on_breakdown(self):
        result = classify_daily_state(evidence(close=80.0, change_pct=-10.0,
                                               above_ma50=False, above_ma150=False,
                                               above_ma200=False,
                                               ma50=8.5, ma150=9.0, ma200=9.2,
                                               ma50_slope_20d_pct=-2.0,
                                               ma150_slope_20d_pct=-2.0,
                                               ma200_slope_20d_pct=-2.0))
        self.assertEqual(result["stage"], "S4_down")

    def test_trend_pullback_has_origin_continuation(self):
        result = classify_daily_state(
            evidence(close=90.0, rolling_trigger=110.0, near_pullback_reference=True)
        )
        self.assertEqual(result["origin"], "continuation")

    def test_failure_level_null_when_no_event_or_breakdown(self):
        result = classify_daily_state(evidence(close=100.0))
        # No active event and no breakdown => failure_level only set for no_long/failure
        self.assertIsNone(result["failure_level"])

    def test_action_field_present_for_every_state(self):
        states_to_test = [
            evidence(close=100.0),  # breakout_setup
            evidence(close=101.0),  # fresh_breakout
            evidence(close=100.5, rolling_trigger=100.0, volume_ratio_50=1.5),  # breakout_setup (near)
            evidence(close=80.0, change_pct=-10.0, above_ma50=False,
                     ma50_slope_20d_pct=-2.0, ma200_slope_20d_pct=-2.0),  # no_long_setup
        ]
        for ev in states_to_test:
            r = classify_daily_state(ev)
            self.assertIn(r["action"], (
                "WAIT", "VALIDATE_FRESH", "DO_NOT_CHASE", "WAIT_FOR_RETEST",
                "HOLD_IF_SUPPORT_DEFENDS", "AVOID_BROKEN_SETUP", "NO_LONG_SETUP",
            ))


if __name__ == "__main__":
    unittest.main()
