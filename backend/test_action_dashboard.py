import unittest

from build_dashboard import (determine_action, MIN_DAILY_TURNOVER_THB, quality_flags, serialize,
                             breakout_evidence, pullback_reference_status)
from screening import group_scan_results


def row(met=8, status="HOLD", rs=80, close=10.0, **tr):
    readiness = {
        "status": status,
        "breakout_20d": False,
        "volume_ratio_50": 1.0,
        "near_buy_zone": False,
        "above_ma50": True,
        "above_ma200": True,
        "ma200_slope_20d_pct": 1.0,
        "ma150_slope_20d_pct": 1.0,
        "rsi_rising": False,
        "ma50_slope_20d_pct": 1.0,
        "range_20d_pct": 20.0,
        "rsi_daily": 55,
        "stop_loss": 9.0,
        "breakout_level_20d": 11.0,
        "buy_zones_90d": {"50": 9.0, "62": 9.7},
    }
    readiness.update(tr)
    return {
        "symbol": "TEST", "close": close,
        "trend_template": {"conditions_met": met, "rs_rating": rs,
                            "ma": {"ma50": 9.5, "ma150": 9.2, "ma200": 9.0}},
        "trade_readiness": readiness,
        "ath_breakout_close": False,
    }


class ActionGroupingTests(unittest.TestCase):
    def test_every_result_has_exactly_one_action_group(self):
        samples = [
            row(status="BUY", near_buy_zone=True),
            row(breakout_20d=True, volume_ratio_50=1.4),
            row(near_buy_zone=True), row(),
            row(met=7),
            row(met=5, rsi_rising=True, ma50_slope_20d_pct=-1),
            row(met=4, range_20d_pct=8), row(met=2, above_ma50=False),
        ]
        groups = group_scan_results(samples)
        self.assertEqual(sum(map(len, groups.values())), len(samples))
        self.assertEqual(len({id(r) for values in groups.values() for r in values}), len(samples))

    def test_weak_trend_is_down_or_broken(self):
        groups = group_scan_results([row(met=2, above_ma50=False, above_ma200=False,
                                          ma50=8.5, ma150=9.0, ma200=9.2,
                                          ma50_slope_20d_pct=-2.0, ma150_slope_20d_pct=-2.0,
                                          ma200_slope_20d_pct=-2.0)])
        self.assertEqual(groups["down_or_broken"][0]["scan_group"], "down_or_broken")

    def test_breakout_records_one_level_breakout_new(self):
        groups = group_scan_results([row(close=11.2, breakout_level_20d=11.0,
                                          breakout_20d=True, volume_ratio_50=1.4)])
        self.assertEqual(len(groups["breakout_new"]), 1)

    def test_transition_breakout_is_fresh_with_reversal_origin(self):
        groups = group_scan_results([
            row(met=5, rs=44, close=11.2, breakout_level_20d=11.0,
                breakout_20d=True, volume_ratio_50=3.0,
                above_ma50=True, above_ma200=True, rsi_rising=True)
        ])
        self.assertEqual(len(groups["breakout_new"]), 1)
        # Stage-first state exposes stage/phase; event origin is optional.
        self.assertEqual(groups["breakout_new"][0]["daily_state"]["stage"], "S2_uptrend")

    def test_qualified_stock_within_four_percent_of_fib_is_uptrend_pullback(self):
        groups = group_scan_results([row(near_buy_zone=False, breakout_level_20d=12.0)])
        self.assertEqual(len(groups["uptrend_pullback"]), 1)

    def test_six_of_eight_near_breakout_is_waiting_breakout_not_base(self):
        groups = group_scan_results([
            row(met=6, close=10.8, breakout_level_20d=11.0,
                above_ma50=True, above_ma200=True, rsi_daily=67, rsi_rising=False,
                ma50_slope_20d_pct=1.0, ma150_slope_20d_pct=1.0, ma200_slope_20d_pct=1.0,
                range_20d_pct=7)
        ])
        self.assertEqual(len(groups["waiting_breakout"]), 1)

    def test_ready_requires_liquidity(self):
        readiness = row(status="BUY", near_buy_zone=True)["trade_readiness"]
        zones = {"50": 9.5, "62": 10.2}
        action, _ = determine_action("uptrend_pullback", readiness,
                                     {"close": 10, "turnover": MIN_DAILY_TURNOVER_THB + 1}, zones,
                                     phase="uptrend_pullback")
        self.assertEqual(action, "HOLD IF SUPPORT DEFENDS")

    def test_risk_group_has_unambiguous_action(self):
        action, _ = determine_action("down_or_broken", {"rsi_daily": 40, "stop_loss": 9},
                                     {"close": 10}, {}, phase="declining")
        self.assertEqual(action, "NO LONG SETUP")

    def test_extended_breakout_is_do_not_chase_and_quality_is_visible(self):
        r = row(met=5, rs=39, close=15.0, breakout_20d=True,
                rsi_daily=86, volume_ratio_50=.2)
        r["daily_state"] = {"stage": "S2_uptrend", "phase": "breakout_extended"}
        item = serialize("breakout_new", r, {"close": 15, "turnover": 1_000_000,
                                              "daily_turnover": 1_000_000})
        codes = {x["code"] for x in item["qualityFlags"]}
        self.assertEqual(item["action"], "DO NOT CHASE")
        self.assertTrue({"extended", "weak_quality", "low_rs", "low_liquidity", "low_volume"} <= codes)
        self.assertEqual(item["liquidity"]["source"], "Daily EOD")

    def test_fresh_breakout_does_not_change_daily_group(self):
        r = row(close=11.2, breakout_20d=True, volume_ratio_50=1.4)
        r["daily_state"] = {"stage": "S2_uptrend", "phase": "breakout_new"}
        item = serialize("breakout_new", r, {"close": 11.2, "turnover": 8_000_000})
        self.assertEqual(item["group"], "breakout_new")
        self.assertEqual(item["action"], "VALIDATE FRESH BREAKOUT")

    def test_extended_breakout_is_not_fresh_opportunity(self):
        r = row(close=15, breakout_20d=True, rsi_daily=82)
        r["daily_state"] = {"stage": "S2_uptrend", "phase": "breakout_extended"}
        item = serialize("breakout_new", r, {"close": 15, "daily_date": "2026-08-14",
                                              "turnover": 9_000_000, "daily_turnover": 9_000_000})
        self.assertFalse(item["lifecycle"]["fresh_opportunity"])
        self.assertTrue(item["lifecycle"]["extended"])
        self.assertIn("Stage 2", item["lifecycle"]["label"])
        self.assertNotEqual(item["action"], "VALIDATE FRESH BREAKOUT")

    def test_quality_gate_blocks_ready_for_low_rs_and_volume(self):
        r = row(status="BUY", near_buy_zone=True, rs=39, volume_ratio_50=.2)
        item = serialize("uptrend_pullback", r, {"close": 10, "daily_date": "2026-08-14",
                                               "turnover": 1_000_000, "daily_turnover": 1_000_000})
        self.assertIn(item["action"], {"CHECK QUALITY", "WAIT", "MONITOR ONLY"})
        self.assertNotIn(item["action"], {"READY TO VALIDATE", "VALIDATE FRESH BREAKOUT"})

    def test_pullback_low_liquidity_is_monitor_only_and_retained(self):
        r = row(status="HOLD", rs=80, volume_ratio_50=.2, near_buy_zone=True)
        item = serialize("uptrend_pullback", r, {"close": 9.5, "daily_date": "2026-08-14",
                                                 "turnover": 1_000_000, "daily_turnover": 1_000_000})
        self.assertEqual(item["action"], "MONITOR ONLY")
        self.assertEqual(item["baseGroup"], "uptrend_pullback")

    def test_breakout_evidence_is_explicitly_not_triggered(self):
        evidence = breakout_evidence({"breakout_level_20d": 11.6, "volume_ratio_50": .71}, {"close": 11.4})
        self.assertEqual(evidence["status"], "NOT TRIGGERED")
        self.assertEqual(evidence["close"], 11.4)
        self.assertEqual(evidence["trigger"], 11.6)
        self.assertEqual(evidence["volume_requirement"], 1.20)
        self.assertIn("11.40", evidence["reason"])
        self.assertIn("1.20×", evidence["reason"])

    def test_pullback_reference_status_compares_current_to_reference(self):
        row_data = {"daily_state": {"reference_level": 46.68}}
        self.assertEqual(pullback_reference_status(row_data, {"close": 48.25})["status"], "PULLBACK HOLDING REFERENCE")
        self.assertEqual(pullback_reference_status(row_data, {"close": 46.67})["status"], "UNDER REFERENCE")

    def test_serialization_exposes_setup_evidence(self):
        r = row(close=11.4, breakout_level_20d=11.6, volume_ratio_50=.71)
        r["daily_state"] = {"stage": "S2_uptrend", "phase": "waiting_breakout", "reference_level": 11.6}
        item = serialize("waiting_breakout", r, {"close": 11.4, "daily_date": "2026-08-14", "daily_turnover": 10000000})
        self.assertEqual(item["breakoutEvidence"]["status"], "NOT TRIGGERED")
        self.assertEqual(item["breakoutEvidence"]["trigger"], 11.6)

        r = row()
        item = serialize("base", r, {"close": 10, "daily_close": 10,
                                      "daily_date": "2026-08-14", "price_source": "60m",
                                      "date": "2026-08-14T06:00:00+00:00", "turnover": 9_000_000,
                                      "daily_turnover": 9_000_000})
        self.assertIn("intraday_stale", item)
        self.assertEqual(item["decision_source"], "Daily EOD")
        self.assertEqual(item["decision_source_as_of"], "2026-08-14")
        self.assertEqual(item["dailyEodDecision"]["source"], "Daily EOD")
        self.assertEqual(item["dailyEodDecision"]["as_of"], "2026-08-14")
        self.assertEqual(item["intradayFreshness"]["status"], "stale")
        self.assertEqual(item["daily_eod_freshness"]["status"], "latest_available")
        self.assertFalse(item["orderBook"]["available"])
        self.assertIn("not Level 2", item["orderBook"]["note"])


if __name__ == "__main__":
    unittest.main()
