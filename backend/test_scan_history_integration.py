"""Integration contract: /scan snapshots the entire evaluated universe."""
import os
import unittest
from unittest.mock import MagicMock, patch


class RunScanHistoryIntegrationTests(unittest.TestCase):
    def test_run_scan_persists_all_groups_not_only_published_candidates(self):
        import app

        ready = {
            "symbol": "READY", "last_date": "2026-08-12", "scan_group": "breakout_new",
            "trend_template": {"conditions_met": 8, "rs_rating": 90},
            "trade_readiness": {"status": "BUY"},
        }
        avoid = {
            "symbol": "AVOID", "last_date": "2026-08-13", "scan_group": "down_or_broken",
            "trend_template": {"conditions_met": 2, "rs_rating": 4},
            "trade_readiness": {"status": "WAIT"},
        }
        groups = {"breakout_new": [ready], "retest_watch": [], "down_or_broken": [avoid]}
        pg = MagicMock()

        with patch.object(app, "scan_universe", return_value=([ready, avoid], [])), \
             patch.object(app, "group_scan_results", return_value=groups), \
             patch.object(app, "get_pg", return_value=pg), \
             patch.object(app, "_publish_screen"), \
             patch.object(app, "_write_scan_json"), \
             patch.object(app, "persist_daily_scan_snapshot") as persist, \
             patch("build_dashboard.build"):
            app.run_scan(push=False)

        persisted_rows = persist.call_args.args[1]
        self.assertEqual([row["symbol"] for row in persisted_rows], ["READY", "AVOID"])
        self.assertEqual(persist.call_args.kwargs["scanner_version"], "signalix/daily-state-v2")
        self.assertEqual(persist.call_args.kwargs["scan_date"].isoformat(), "2026-08-13")
        self.assertEqual(persist.call_args.kwargs["source_lineage"]["source"], "price_data")

    def test_run_scan_passes_explicit_retry_parent_to_snapshot(self):
        import app

        ready = {
            "symbol": "READY", "last_date": "2026-08-13", "scan_group": "breakout_new",
            "trend_template": {"conditions_met": 8, "rs_rating": 90},
            "trade_readiness": {"status": "BUY"},
        }
        parent_run_id = "00000000-0000-0000-0000-000000000001"
        groups = {"breakout_new": [ready], "retest_watch": []}

        # Invoke the decorated /scan handler itself; all external seams are
        # mocked, so this test cannot contact the service database.
        with patch.object(app, "scan_universe", return_value=([ready], [])), \
             patch.object(app, "group_scan_results", return_value=groups), \
             patch.object(app, "get_pg", return_value=MagicMock()), \
             patch.object(app, "_publish_screen"), \
             patch.object(app, "_write_scan_json"), \
             patch.object(app, "persist_daily_scan_snapshot") as persist, \
             patch("build_dashboard.build"):
            app.run_scan(push=False, retry_of_run_id=parent_run_id)

        self.assertEqual(persist.call_args.kwargs["retry_of_run_id"], parent_run_id)

    def test_startup_does_not_apply_schema_in_default_validate_mode(self):
        import app

        with patch.dict(os.environ, {"SIGNALIX_SCHEMA_MODE": "validate"}), \
             patch.object(app, "init_db") as init_db:
            app.startup()

        init_db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
