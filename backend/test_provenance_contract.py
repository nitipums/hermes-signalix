"""Regression tests for the Provenance/Freshness Contract (P0, t_7cca0a57).

Locks in the canonical field shapes and deterministic status boundaries so
that TH (dashboard) and US (watchlist) provenance metadata stay aligned.
"""
import datetime as dt
import unittest

from provenance_contract import (
    compute_freshness,
    display_fetched_at,
    FRESH,
    AGING,
    STALE,
    UNKNOWN,
    INTRADAY_STALE_HOURS,
)


class FreshStatusBoundariesTests(unittest.TestCase):
    def test_no_timestamp_is_unknown(self):
        now = dt.datetime(2026, 8, 21, 12, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(compute_freshness(None, now=now), UNKNOWN)

    def test_invalid_string_is_unknown(self):
        now = dt.datetime(2026, 8, 21, 12, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(compute_freshness("not-a-date", now=now), UNKNOWN)

    def test_fresh_below_one_hour(self):
        now = dt.datetime(2026, 8, 21, 12, 0, tzinfo=dt.timezone.utc)
        fetched = now - dt.timedelta(minutes=59, seconds=59)
        self.assertEqual(compute_freshness(fetched, now=now), FRESH)

    def test_stale_at_one_hour_boundary(self):
        # At exactly 1h the contract returns AGING (fresh < 1h, aging <= 72h, stale > 72h)
        now = dt.datetime(2026, 8, 21, 12, 0, tzinfo=dt.timezone.utc)
        fetched = now - dt.timedelta(hours=1)
        self.assertEqual(compute_freshness(fetched, now=now), AGING)

    def test_aging_between_one_hour_and_seventy_two(self):
        now = dt.datetime(2026, 8, 21, 12, 0, tzinfo=dt.timezone.utc)
        fetched = now - dt.timedelta(hours=25)
        self.assertEqual(compute_freshness(fetched, now=now), AGING)

    def test_stale_after_seventy_two_hours(self):
        now = dt.datetime(2026, 8, 21, 12, 0, tzinfo=dt.timezone.utc)
        fetched = now - dt.timedelta(hours=73)
        self.assertEqual(compute_freshness(fetched, now=now), STALE)

    def test_naive_datetime_treated_as_utc(self):
        now = dt.datetime(2026, 8, 21, 12, 0, tzinfo=dt.timezone.utc)
        fetched = now - dt.timedelta(minutes=30)
        fetched_naive = fetched.replace(tzinfo=None)
        self.assertEqual(compute_freshness(fetched_naive, now=now), FRESH)

    def test_iso_string_with_z_suffix(self):
        now = dt.datetime(2026, 8, 21, 12, 0, tzinfo=dt.timezone.utc)
        fetched_str = (now - dt.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(compute_freshness(fetched_str, now=now), FRESH)


class DisplayContractTests(unittest.TestCase):
    def test_none_displays_unknown(self):
        self.assertEqual(display_fetched_at(None), "Unknown / Stale")

    def test_invalid_string_displays_unknown(self):
        self.assertEqual(display_fetched_at("garbage"), "Unknown / Stale")

    def test_valid_timestamp_displays_bkk_format(self):
        ts = "2026-08-21T15:33:53.994979+00:00"
        result = display_fetched_at(ts)
        self.assertIn("ICT (Bangkok)", result)
        self.assertTrue(result != "Unknown / Stale")


class UsPayloadContractTests(unittest.TestCase):
    """The US watchlist payload must compute freshness, not hardcode 'unknown'."""

    def _write_fixture(self, tmp_path, scan_time):
        import json, os
        payload = {
            "universe": "us_ai_buildout",
            "market": "US",
            "benchmark_symbol": "SPY",
            "source": "yahoo_chart_bootstrap_unverified",
            "scan_time": scan_time,
            "results": [
                {"symbol": "MU", "close": 971.66, "scan_time": scan_time},
                {"symbol": "TSM", "close": 158.0, "scan_time": scan_time},
            ],
        }
        path = tmp_path / "us_scan.json"
        path.write_text(json.dumps(payload))
        return str(path)

    def test_us_status_fresh(self, tmp_path=None):
        import tempfile, os, sys
        with tempfile.TemporaryDirectory() as d:
            scan_path = self._write_fixture(type("P", (), {"__truediv__": lambda self, x: os.path.join(d, x)})() / "us.json",
                                            "2026-08-21T12:00:00+00:00") \
                          if tmp_path else None
        # Simpler inline fixture
        import json, tempfile
        fresh = dt.datetime(2026, 8, 21, 12, 0, tzinfo=dt.timezone.utc)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({
                "universe": "us_ai_buildout", "market": "US", "benchmark_symbol": "SPY",
                "source": "yahoo_chart_bootstrap_unverified", "scan_time": fresh.isoformat(),
                "results": [{"symbol": "MU", "close": 971.66, "scan_time": fresh.isoformat()}],
            }, f)
            path = f.name
        try:
            from app import us_watchlist_overview_payload
            payload = us_watchlist_overview_payload(path)
            self.assertEqual(payload["market"], "US")
            self.assertIsNotNone(payload["data_fetched_at"])
            self.assertEqual(payload["data_freshness_source"], "yahoo_chart_bootstrap_unverified")
            self.assertNotEqual(payload["data_freshness_status"], "unknown")
        finally:
            os.unlink(path)

    def test_us_status_unknown_when_no_scan_time(self):
        import json, tempfile, os
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({
                "universe": "us_ai_buildout", "market": "US", "benchmark_symbol": "SPY",
                "source": "yahoo_chart_bootstrap_unverified", "scan_time": None,
                "results": [{"symbol": "MU", "close": 971.66}],
            }, f)
            path = f.name
        try:
            from app import us_watchlist_overview_payload
            payload = us_watchlist_overview_payload(path)
            self.assertIsNone(payload["data_fetched_at"])
            self.assertEqual(payload["data_freshness_status"], UNKNOWN)
        finally:
            os.unlink(path)


class DashboardSnapshotContractTests(unittest.TestCase):
    """dashboard_snapshot.json must expose top-level provenance fields.

    The runtime API (app.dashboard_snapshot) adds these from the DB at
    request time; the static file may carry them under dashboard_meta or
    at root if pre-computed at build time.  This test verifies the contract
    shape regardless of where the fields live.
    """

    def test_snapshot_has_canonical_provenance_fields(self):
        import json, os
        path = os.path.join(os.path.dirname(__file__), "dashboard_snapshot.json")
        if not os.path.exists(path):
            self.skipTest("dashboard_snapshot.json not present")
        snap = json.load(open(path))
        # Root-level fields OR dashboard_meta must carry the contract
        # fields. Some snapshots store them under dashboard_meta.
        meta = snap.get("dashboard_meta") or {}
        for key in ("data_fetched_at", "data_freshness_source",
                    "data_freshness_status", "market_session", "last_valid_session"):
            root_val = snap.get(key)
            meta_val = meta.get(key)
            self.assertTrue(
                root_val is not None or meta_val is not None,
                f"provenance field {key!r} missing from root and dashboard_meta",
            )
        session = snap.get("market_session") or meta.get("market_session") or {}
        if isinstance(session, dict):
            for key in ("status", "is_open", "timezone", "source"):
                self.assertIn(key, session, f"market_session missing {key!r}")
        # data_freshness_status must be a canonical contract value
        status = snap.get("data_freshness_status") or meta.get("data_freshness_status")
        self.assertIn(status, {FRESH, AGING, STALE, UNKNOWN, "market_closed"},
                       f"non-canonical status: {status}")

    def test_build_dashboard_serializer_emits_canonical_freshness_fields(self):
        """serialize() must embed intradayFreshness/daily_eod_freshness with
        canonical status values (stale/fresh/unavailable, latest_available/unavailable)."""
        from build_dashboard import serialize
        row = {"symbol": "TEST", "trade_readiness": {}, "trend_template": {}}
        snapshot = {"date": "2026-08-21T09:00:00+00:00", "close": 10,
                    "daily_date": "2026-08-21", "daily_turnover": 8_000_000}
        item = serialize("uptrend_pullback", row, snapshot)
        self.assertIn("intradayFreshness", item)
        self.assertIn("daily_eod_freshness", item)
        self.assertIn("decision_source", item)
        self.assertIn("decision_source_as_of", item)
        self.assertIn("freshness_badge", item)
        # intraday status must be a canonical value
        self.assertIn(item["intradayFreshness"]["status"],
                      {"stale", "fresh", "unavailable"})
        # daily status must be canonical
        self.assertIn(item["daily_eod_freshness"]["status"],
                      {"latest_available", "unavailable"})
        # freshness_badge is derived from the canonical statuses
        self.assertIn(item["freshness_badge"], {"fresh", "stale", "unknown"})


if __name__ == "__main__":
    unittest.main()
