"""Tests for Signalix Risk/Stop/Target calculation module.

Tests both the pure-math functions (fib_targets, position_size) and the
contract adapters that map analyze_symbol_db_ranked output → risk evidence.
"""
import unittest
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import risk_stop_target as rst


class TestFibTargets(unittest.TestCase):
    def test_valid_anchor_extension(self):
        result = rst.compute_fib_targets(10.0, 20.0, 15.0)
        wave_range = 20.0 - 10.0
        self.assertAlmostEqual(result["fib_1272"], round(15.0 + wave_range * 1.272, 4))
        self.assertAlmostEqual(result["fib_1618"], round(15.0 + wave_range * 1.618, 4))
        self.assertEqual(result["status"], "OK")

    def test_missing_anchor_not_verified(self):
        result = rst.compute_fib_targets(None, 20.0, 15.0)
        self.assertIsNone(result["fib_1272"])
        self.assertEqual(result["status"], "NOT_VERIFIED")

    def test_invalid_anchors(self):
        result = rst.compute_fib_targets(20.0, 10.0, 15.0)
        self.assertEqual(result["status"], "NOT_VERIFIED")

    def test_zero_range(self):
        result = rst.compute_fib_targets(10.0, 10.0, 10.0)
        self.assertEqual(result["status"], "NOT_VERIFIED")


class TestPositionSize(unittest.TestCase):
    def test_basic_calculation(self):
        result = rst.compute_position_size(100000, 1.0, 50.0, 45.0)
        self.assertEqual(result["risk_budget"], 1000.0)
        self.assertEqual(result["risk_per_share"], 5.0)
        self.assertEqual(result["shares"], 200)
        self.assertEqual(result["status"], "OK")

    def test_not_verified_when_stop_above_entry(self):
        result = rst.compute_position_size(100000, 1.0, 45.0, 50.0)
        self.assertEqual(result["status"], "NOT_VERIFIED")

    def test_not_verified_when_missing_input(self):
        result = rst.compute_position_size(None, 1.0, 50.0, 45.0)
        self.assertEqual(result["status"], "NOT_VERIFIED")

    def test_not_verified_when_risk_percent_zero(self):
        result = rst.compute_position_size(100000, 0, 50.0, 45.0)
        self.assertEqual(result["status"], "NOT_VERIFIED")


class TestDailyEvidenceExtraction(unittest.TestCase):
    """Tests the adapter that maps analyze_symbol_db_ranked → evidence dict."""

    def _daily_item(self):
        """Simulates real analyze_symbol_db_ranked output structure."""
        return {
            "symbol": "TEST",
            "close": 39.75,
            "last_date": dt.date.today().isoformat(),
            "buy_zone": {
                "wave1_high": 45.0,
                "wave1_low": 30.0,
                "fibs": {"23": 39.52, "38": 41.43, "50": 42.15, "62": 42.87, "78": 43.95},
                "monitor_support": 30.0,
                "stop_loss": 36.97,
            },
            "trade_readiness": {
                "status": "HOLD",
                "breakout_level_20d": 39.5,
                "stop_loss": 36.97,
                "pre_break_pivot_low": 33.5,
                "swing_low_90d": 30.0,
                "swing_high_90d": 45.0,
            },
            "trend_template": {"conditions_met": 8, "rs_rating": 94.0},
        }

    def test_extract_daily_evidence_fields(self):
        ev = rst._extract_daily_evidence(self._daily_item())
        self.assertEqual(ev["trigger"], 39.5)
        self.assertEqual(ev["system_stop"], 36.97)
        self.assertEqual(ev["pivot_low"], 33.5)
        self.assertEqual(ev["swing_low"], 30.0)
        self.assertEqual(ev["swing_high"], 45.0)
        self.assertAlmostEqual(ev["pullback_low"], 42.15)
        self.assertEqual(ev["freshness"], dt.date.today().isoformat())

    def test_fib_targets_from_daily_evidence(self):
        ev = rst._extract_daily_evidence(self._daily_item())
        fib = rst.compute_fib_targets(ev["swing_low"], ev["swing_high"], ev["pullback_low"])
        self.assertEqual(fib["status"], "OK")
        wave_range = 45.0 - 30.0
        expected_1272 = round(42.15 + wave_range * 1.272, 4)
        expected_1618 = round(42.15 + wave_range * 1.618, 4)
        self.assertAlmostEqual(fib["fib_1272"], expected_1272)
        self.assertAlmostEqual(fib["fib_1618"], expected_1618)


class TestRiskStopTarget(unittest.TestCase):
    def _daily_item(self):
        return {
            "symbol": "TEST",
            "close": 50.0,
            "last_date": dt.date.today().isoformat(),
            "buy_zone": {
                "wave1_high": 60.0,
                "wave1_low": 40.0,
                "fibs": {"50": 48.0, "62": 52.0},
                "monitor_support": 40.0,
                "stop_loss": 45.0,
            },
            "trade_readiness": {
                "breakout_level_20d": 50.0,
                "stop_loss": 45.0,
                "pre_break_pivot_low": 42.0,
            },
        }

    def test_daily_contract_ok(self):
        result = rst.compute_risk_stop_target("daily", "TEST", item=self._daily_item())
        self.assertEqual(result["contract"], "daily")
        self.assertIn("status", result)
        self.assertIsNotNone(result["trigger"])
        self.assertEqual(result["trigger"], 50.0)
        self.assertEqual(result["system_stop"], 45.0)
        self.assertIsNotNone(result["fib_1272"])
        self.assertEqual(result["status"], "OK")

    def test_daily_contract_stale_freshness(self):
        item = self._daily_item()
        item["last_date"] = "2000-01-01"  # very stale
        result = rst.compute_risk_stop_target("daily", "TEST", item=item)
        self.assertEqual(result["status"], "NOT_VERIFIED")
        self.assertIn("stale", result["reason"])

    def test_daily_contract_missing_item(self):
        result = rst.compute_risk_stop_target("daily", "TEST", item=None)
        self.assertEqual(result["status"], "NOT_VERIFIED")

    def test_intraday_contract_no_data(self):
        result = rst.compute_risk_stop_target("intraday", "TEST")
        self.assertEqual(result["status"], "NOT_VERIFIED")

    def test_intraday_contract_from_df(self):
        import pandas as pd
        import datetime as dt
        # Build a synthetic 60m DataFrame
        now = dt.datetime.now(dt.timezone.utc)
        times = pd.date_range(now - dt.timedelta(hours=89), now, freq="h")
        df = pd.DataFrame({
            "Open": [100 + i * 0.1 for i in range(90)],
            "High": [105 + i * 0.1 for i in range(90)],
            "Low": [95 + i * 0.1 for i in range(90)],
            "Close": [102 + i * 0.1 for i in range(90)],
            "Volume": [1000] * 90,
        }, index=times)
        result = rst.compute_risk_stop_target("intraday", "TEST", intraday_df=df)
        self.assertEqual(result["contract"], "intraday")
        self.assertEqual(result["status"], "OK")
        self.assertIsNotNone(result["swing_low"])
        self.assertIsNotNone(result["swing_high"])
        self.assertIsNotNone(result["fib_1272"])

    def test_unknown_contract(self):
        result = rst.compute_risk_stop_target("weekly", "TEST", item={})
        self.assertEqual(result["status"], "NOT_VERIFIED")

    def test_warnings_when_planned_stop_above_system(self):
        item = self._daily_item()
        user = {"planned_stop": 46.0}
        result = rst.compute_risk_stop_target("daily", "TEST", item=item, user_inputs=user)
        self.assertIn("STOP ABOVE SYSTEM INVALIDATION", result.get("warnings", []))

    def test_wider_stop_when_planned_stop_below_system(self):
        item = self._daily_item()
        user = {"planned_stop": 43.0}
        result = rst.compute_risk_stop_target("daily", "TEST", item=item, user_inputs=user)
        self.assertIn("WIDER STOP", result.get("warnings", []))

    def test_user_inputs_override_defaults(self):
        item = self._daily_item()
        user = {"planned_entry": 55.0, "planned_stop": 44.0,
                "account_size": 100000, "risk_percent": 1.0}
        result = rst.compute_risk_stop_target("daily", "TEST", item=item, user_inputs=user)
        self.assertEqual(result["planned_entry"], 55.0)
        self.assertEqual(result["planned_stop"], 44.0)
        self.assertEqual(result["sizing"]["shares"], 90)  # 1000 risk / 11 per share
        self.assertEqual(result["status"], "OK_WITH_WARNINGS")  # wider stop warning


if __name__ == "__main__":
    unittest.main()
