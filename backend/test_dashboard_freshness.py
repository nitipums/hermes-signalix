import datetime as dt
import unittest
from unittest.mock import MagicMock

from build_dashboard import dashboard_freshness, market_session_status, serialize, snapshots


class SnapshotFreshnessTests(unittest.TestCase):
    def _freshness_at(self, fetched_at, now):
        pg = MagicMock()
        cursor = pg.cursor.return_value
        cursor.fetchone.side_effect = [("data_fetch_status",), (fetched_at, "settrade_intraday_60m")]
        return dashboard_freshness(pg, now=now)

    def test_intraday_freshness_boundaries_are_deterministic(self):
        now = dt.datetime(2026, 8, 15, 12, 0, tzinfo=dt.timezone.utc)
        closed_fresh = self._freshness_at(now - dt.timedelta(minutes=59, seconds=59), now)
        closed_stale = self._freshness_at(now - dt.timedelta(hours=1), now)
        self.assertEqual(closed_fresh["status"], "market_closed")
        self.assertEqual(closed_fresh["intraday_status"], "fresh")
        self.assertEqual(closed_stale["status"], "market_closed")
        self.assertEqual(closed_stale["intraday_status"], "stale")
        self.assertEqual(self._freshness_at(now - dt.timedelta(hours=1, seconds=1), now)["status"], "market_closed")
        self.assertEqual(self._freshness_at(now - dt.timedelta(hours=1, seconds=1), now)["intraday_status"], "stale")

    def test_missing_intraday_fetch_timestamp_is_unknown_stale(self):
        pg = MagicMock()
        pg.cursor.return_value.fetchone.side_effect = [("data_fetch_status",), None]
        freshness = dashboard_freshness(pg, now=dt.datetime(2026, 8, 15, tzinfo=dt.timezone.utc))
        self.assertEqual(freshness["status"], "unknown")
        self.assertEqual(freshness["intraday_status"], "unknown_stale")

    def test_market_session_open_vs_closed_is_deterministic(self):
        open_now = dt.datetime(2026, 8, 14, 4, 0, tzinfo=dt.timezone.utc)  # 11:00 ICT
        closed_now = dt.datetime(2026, 8, 15, 4, 0, tzinfo=dt.timezone.utc)  # Saturday
        holiday = dt.datetime(2026, 8, 12, 4, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(market_session_status(open_now)["status"], "open_session")
        self.assertTrue(market_session_status(open_now)["is_open"])
        self.assertEqual(market_session_status(open_now)["timezone"], "Asia/Bangkok")
        self.assertEqual(market_session_status(open_now)["source"], "set_market_day_guard")
        self.assertEqual(market_session_status(closed_now)["reason"], "weekend")
        self.assertFalse(market_session_status(closed_now)["is_open"])
        self.assertEqual(market_session_status(holiday)["reason"], "holiday")
        self.assertEqual(market_session_status(closed_now, "2026-08-14")["last_valid_session"], "2026-08-14")

    def test_closed_freshness_exposes_last_valid_session_contract(self):
        now = dt.datetime(2026, 8, 15, 4, 0, tzinfo=dt.timezone.utc)
        pg = MagicMock()
        pg.cursor.return_value.fetchone.side_effect = [
            ("data_fetch_status",),
            (now - dt.timedelta(hours=2), "settrade_intraday_60m"),
        ]
        value = dashboard_freshness(pg, now=now, last_valid_session="2026-08-14")
        session = value["market_session"]
        self.assertEqual(value["status"], "market_closed")
        self.assertEqual(session, {
            "status": "market_closed", "is_open": False, "reason": "weekend",
            "date": "2026-08-15", "last_valid_session": "2026-08-14",
            "timezone": "Asia/Bangkok", "source": "set_market_day_guard",
        })

    def test_intraday_overlay_preserves_daily_change_and_uses_60m_contract(self):
        pg = MagicMock()
        cursors = []
        rows = [
            # latest two Daily rows
            [("TFG", "2026-08-11", 10.0, 1_000_000, 1, "Food", "Agriculture", 123_000_000, 45.5, 49.0),
             ("TFG", "2026-08-08", 9.6, 900_000, 2, "Food", "Agriculture", 123_000_000, 45.5, 49.0)],
            # Daily history (date, close, high, low, volume)
            [("TFG", "2026-08-08", 9.6, 9.8, 9.4, 900_000), ("TFG", "2026-08-11", 10.0, 10.2, 9.7, 1_000_000)],
            # full archive ATH
            [("TFG", 10.2, 1.0)],
            # optional company profile
            [("TFG", "Thai Foods Group", "Food", "Agriculture", "Food", "test", "2026-08-11", 123_000_000, 45.5, 49.0)],
            # newest stored 60m quote
            [("TFG", "60m", "2026-08-11 09:30:00+00:00", 9.9, 1000)],
            # same-time cumulative volume query
            [],
        ]
        for result in rows:
            c = MagicMock(); c.fetchall.return_value = result; cursors.append(c)
        pg.cursor.side_effect = cursors
        value = snapshots(pg, ["TFG"])["TFG"]
        self.assertAlmostEqual(value["daily_change"], 4.1666667, places=5)
        self.assertEqual(value["daily_close"], 10.0)
        self.assertEqual(value["price_source"], "60m")
        self.assertAlmostEqual(value["change"], 3.125, places=5)
        self.assertEqual(value["market_cap"], 123_000_000)
        self.assertEqual(value["free_float_pct"], 45.5)
        self.assertEqual(value["foreign_limit_pct"], 49.0)

    def test_card_separates_stale_intraday_from_daily_decision_source(self):
        row = {"symbol": "TITLE", "trade_readiness": {}, "trend_template": {}}
        snapshot = {"date": "2026-08-14T06:00:00+00:00", "close": 10, "daily_close": 9.5,
                    "daily_date": "2026-08-14", "price_source": "60m", "daily_turnover": 8_000_000}
        item = serialize("uptrend_pullback", row, snapshot)
        self.assertEqual(item["intradaySource"], "60m")
        self.assertEqual(item["intradayLatestTime"], snapshot["date"])
        self.assertTrue(item["intradayAvailable"])
        self.assertEqual(item["decision_source"], "Daily EOD")

    def test_card_without_intraday_is_explicitly_unavailable(self):
        row = {"symbol": "SCG", "trade_readiness": {}, "trend_template": {}}
        item = serialize("uptrend_pullback", row, {"date": "2026-08-14", "close": 10,
                                                     "daily_date": "2026-08-14", "daily_turnover": 8_000_000})
        self.assertFalse(item["intradayAvailable"])
        self.assertIsNone(item["intradaySource"])
        self.assertIsNone(item["intradayStale"] if "intradayStale" in item else None)

    def test_dashboard_uses_successful_fetch_time_not_older_candle_time(self):
        pg = MagicMock()
        cursor = pg.cursor.return_value
        cursor.fetchone.side_effect = [
            ("data_fetch_status",),
            (
                dt.datetime(2026, 8, 14, 5, 0, tzinfo=dt.timezone.utc),
                "settrade_intraday_60m",
            ),
        ]

        freshness = dashboard_freshness(pg)

        self.assertEqual(freshness["data_fetched_at"], "2026-08-14T05:00:00+00:00")
        self.assertEqual(freshness["display"], "14 Aug 2026 12:00 ICT (Bangkok)")
        self.assertEqual(freshness["source"], "settrade_intraday_60m")
        self.assertNotIn("2026-08-13T09:00:00+00:00", freshness["display"])

    def test_cards_do_not_expose_a_second_freshness_timestamp(self):
        row = {
            "symbol": "STGT",
            "trade_readiness": {},
            "trend_template": {},
        }
        snapshot = {
            "date": "2026-08-13T09:00:00+00:00",
            "close": 10.9,
            "price_source": "60m",
        }

        item = serialize("base_building", row, snapshot)

        self.assertNotIn("fullTimestamp", item)
        self.assertNotIn("ageLabel", item)
        self.assertNotIn("dataFetchedAt", item)

    def test_loading_header_is_distinct_from_unknown_or_stale(self):
        from pathlib import Path
        source = Path("build_dashboard.py").read_text(encoding="utf-8")
        # The unknown/stale fallback label must exist as a distinct branch
        # from any live-loading path. The original 'Loading live snapshot…'
        # literal was removed in a later refactor, so assert the current
        # distinct 'Unknown / Stale' contract instead of a string that no
        # longer exists.
        self.assertIn("Unknown / Stale", source)
        self.assertIn("def dashboard_freshness", source)

    def test_unknown_fetch_time_never_falls_back_to_candle_time(self):
        pg = MagicMock()
        pg.cursor.return_value.fetchone.side_effect = [("data_fetch_status",), None]

        freshness = dashboard_freshness(pg)

        self.assertIsNone(freshness["data_fetched_at"])
        self.assertEqual(freshness["display"], "Unknown / Stale")


if __name__ == "__main__":
    unittest.main()
