import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from eod_healthcheck import evaluate_health, expected_market_date, render_payload, write_observation

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 14, 14, 0, tzinfo=UTC)  # 21:00 Bangkok


class EodHealthcheckTests(unittest.TestCase):
    def test_expected_market_date_skips_weekend(self):
        saturday = dt.datetime(2026, 8, 15, 2, 0, tzinfo=UTC)
        self.assertEqual(expected_market_date(saturday), dt.date(2026, 8, 14))

    def test_stale_eod_and_scan_are_alerted(self):
        alerts = evaluate_health(
            {"Result": "success", "ExecMainStatus": "0"},
            dt.date(2026, 8, 13), dt.date(2026, 8, 13),
            dt.date(2026, 8, 14), NOW,
        )
        self.assertEqual([a["code"] for a in alerts], ["eod_data_stale", "daily_scan_stale"])

    def test_failed_service_is_alerted_even_with_fresh_data(self):
        alerts = evaluate_health(
            {"Result": "failed", "ExecMainStatus": "1"},
            dt.date(2026, 8, 14), dt.date(2026, 8, 14),
            dt.date(2026, 8, 14), NOW,
        )
        self.assertEqual(alerts[0]["code"], "service_failed")

    def test_fresh_pipeline_is_healthy(self):
        alerts = evaluate_health(
            {"Result": "success", "ExecMainStatus": "0"},
            dt.date(2026, 8, 14), dt.date(2026, 8, 14),
            dt.date(2026, 8, 14), NOW,
        )
        self.assertEqual(alerts, [])
        payload = json.loads(render_payload([], dt.date(2026, 8, 14),
                                            dt.date(2026, 8, 14), NOW))
        self.assertEqual(payload["level"], "HEALTHY")

    def test_observation_write_is_atomic_and_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            write_observation('{"level":"HEALTHY"}', path)
            self.assertEqual(json.loads(path.read_text())["level"], "HEALTHY")
            self.assertFalse(path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
