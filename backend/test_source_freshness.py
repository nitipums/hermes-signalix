"""Source freshness tracking tests (task t_453a00bd).

Contract under test:
- record_source_fetch persists last successful fetch per dataset (no invented values).
- source_freshness reads only what the system observed: missing row => status
  "unknown", data_fetched_at None, never a fabricated timestamp.
- Thresholds come from the centralized provenance contract.
- Availability comes from observed intraday_feed_status rows only.
"""
import datetime as dt
import unittest
from unittest.mock import MagicMock

from source_freshness import attach_freshness, record_source_fetch, source_freshness


NOW = dt.datetime(2026, 8, 22, 12, 0, tzinfo=dt.timezone.utc)


def _pg_with_rows(rows):
    pg = MagicMock()
    cur = pg.cursor.return_value.__enter__.return_value if hasattr(
        pg.cursor.return_value, "__enter__") else pg.cursor.return_value
    cur.fetchall.return_value = rows
    return pg


class RecordFetchTests(unittest.TestCase):
    def test_record_upserts_observed_fetch_time(self):
        pg = MagicMock()
        fetched = dt.datetime(2026, 8, 22, 11, 0, tzinfo=dt.timezone.utc)
        record_source_fetch(pg, "dashboard_intraday", fetched_at=fetched,
                            source="settrade_intraday_60m")
        sql = pg.cursor.return_value.execute.call_args.args[0]
        args = pg.cursor.return_value.execute.call_args.args[1]
        self.assertIn("INSERT INTO data_fetch_status", sql)
        self.assertIn("ON CONFLICT (dataset) DO UPDATE", sql)
        self.assertIn("data_fetched_at", sql)
        self.assertEqual(args[0], "dashboard_intraday")
        self.assertEqual(args[1], fetched)
        self.assertEqual(args[2], "settrade_intraday_60m")
        pg.commit.assert_called_once()

    def test_record_requires_a_real_timestamp(self):
        with self.assertRaises(ValueError):
            record_source_fetch(MagicMock(), "x", fetched_at=None, source="s")


class ReadFreshnessTests(unittest.TestCase):
    def _reader(self, rows):
        pg = MagicMock()
        pg.cursor.return_value.fetchall.return_value = rows
        return source_freshness(pg, now=NOW)

    def test_missing_row_is_unknown_never_invented(self):
        out = self._reader([])
        entry = out["sources"]["dashboard_intraday"]
        self.assertEqual(entry["status"], "unknown")
        self.assertIsNone(entry["data_fetched_at"])
        self.assertIsNone(entry["age_hours"])
        self.assertNotIn("display", entry) or True

    def test_fresh_aging_stale_boundaries_follow_contract(self):
        fresh = self._reader([("dashboard_intraday", NOW - dt.timedelta(minutes=30), "settrade_intraday_60m")])
        aging = self._reader([("us_daily_eod", NOW - dt.timedelta(hours=48), "yahoo")])
        stale = self._reader([("legacy_set", NOW - dt.timedelta(hours=100), "old")])
        self.assertEqual(fresh["sources"]["dashboard_intraday"]["status"], "fresh")
        self.assertEqual(aging["sources"]["us_daily_eod"]["status"], "aging")
        self.assertEqual(stale["sources"]["legacy_set"]["status"], "stale")

    def test_availability_reflects_only_observed_feed_status(self):
        rows = [
            ("dashboard_intraday", NOW - dt.timedelta(minutes=5), "settrade_intraday_60m"),
            ("us_daily_eod", NOW - dt.timedelta(minutes=5), "yahoo"),
        ]
        feed_rows = [("STGT", "degraded")]
        pg = MagicMock()
        pg.cursor.return_value.fetchall.side_effect = [rows, feed_rows]
        out = source_freshness(pg, now=NOW)
        src = out["sources"]
        self.assertTrue(src["dashboard_intraday"]["available"])
        # degraded feed observed => source not fully available; reported, not guessed
        self.assertFalse(src["dashboard_intraday"]["all_feeds_available"])
        self.assertEqual(out["feeds"]["STGT"], "degraded")

    def test_no_feed_status_table_rows_means_available_by_absence_of_failures(self):
        rows = [("dashboard_intraday", NOW - dt.timedelta(minutes=5), "settrade_intraday_60m")]
        pg = MagicMock()
        pg.cursor.return_value.fetchall.side_effect = [rows, []]
        out = source_freshness(pg, now=NOW)
        self.assertTrue(out["sources"]["dashboard_intraday"]["all_feeds_available"])

    def test_payload_exposes_thresholds_and_generated_at(self):
        out = self._reader([])
        self.assertEqual(out["thresholds"]["stale_after_hours"], 72)
        self.assertEqual(out["thresholds"]["fresh_within_hours"], 1)
        self.assertIn("generated_at", out)


class AttachTests(unittest.TestCase):
    def test_attach_adds_sources_block_without_touching_accounts(self):
        health = {"accounts": [{"display_account_id": "a"}], "state": "monitor_p0_1"}
        fresh = {"sources": {"dashboard_intraday": {"status": "fresh"}}}
        merged = attach_freshness(health, fresh)
        self.assertEqual(merged["source_freshness"], fresh)
        self.assertEqual(len(merged["accounts"]), 1)


if __name__ == "__main__":
    unittest.main()
