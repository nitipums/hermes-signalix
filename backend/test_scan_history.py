"""TDD contract tests for immutable daily full-scan history."""
import datetime as dt
import json
import unittest
from unittest.mock import MagicMock


class DailyScanHistoryTests(unittest.TestCase):
    def _results(self):
        return [
            {
                "symbol": "QUAL",
                "last_date": "2026-08-13",
                "close": 12.5,
                "scan_group": "breakout_new",
                "group_reason": "qualified",
                "trend_template": {"pass": True, "conditions_met": 8, "rs_rating": 95.0},
                "trade_readiness": {"status": "BUY"},
                "derived": {"stop": 11.4},
            },
            {
                "symbol": "AVOID",
                "last_date": "2026-08-13",
                "close": 3.2,
                "scan_group": "down_or_broken",
                "group_reason": "weak trend",
                "trend_template": {"pass": False, "conditions_met": 2, "rs_rating": 4.0},
                "trade_readiness": {"status": "WAIT"},
                "derived": {"stop": 2.9},
            },
        ]

    def test_snapshot_persists_every_evaluated_symbol_including_avoid(self):
        from scan_history import persist_daily_scan_snapshot

        pg = MagicMock()
        result = persist_daily_scan_snapshot(
            pg,
            self._results(),
            scan_date=dt.date(2026, 8, 13),
            scanner_version="signalix/full-scan-v1",
            source_lineage={"source": "price_data", "freshness": "eod_archive"},
            run_timestamp=dt.datetime(2026, 8, 13, 11, 0, tzinfo=dt.timezone.utc),
        )

        self.assertEqual(result["observation_count"], 2)
        execute_calls = pg.cursor.return_value.execute.call_args_list
        observation_params = [call.args[1] for call in execute_calls if "daily_scan_observations" in call.args[0]]
        self.assertEqual([params[2] for params in observation_params], ["QUAL", "AVOID"])
        self.assertEqual(observation_params[1][3], "down_or_broken")

    def test_each_rerun_gets_a_new_run_and_preserves_full_payload(self):
        from scan_history import persist_daily_scan_snapshot

        pg = MagicMock()
        first = persist_daily_scan_snapshot(pg, self._results(), scan_date=dt.date(2026, 8, 13))
        changed = self._results()
        changed[1]["close"] = 999.0
        second = persist_daily_scan_snapshot(pg, changed, scan_date=dt.date(2026, 8, 13), retry_of_run_id=first["run_id"])

        self.assertNotEqual(first["run_id"], second["run_id"])
        calls = pg.cursor.return_value.execute.call_args_list
        observation_params = [call.args[1] for call in calls if "daily_scan_observations" in call.args[0]]
        first_avoid_payload = json.loads(observation_params[1][-1])
        second_avoid_payload = json.loads(observation_params[3][-1])
        self.assertEqual(first_avoid_payload["close"], 3.2)
        self.assertEqual(second_avoid_payload["close"], 999.0)
        self.assertEqual(second["retry_of_run_id"], first["run_id"])

    def test_snapshot_mapping_uses_scan_date_for_no_data_and_error_rows(self):
        from scan_history import persist_daily_scan_snapshot

        scan_date = dt.date(2026, 8, 13)
        results = [
            {
                "symbol": "MISSING",
                "analysis_status": "INSUFFICIENT_HISTORY",
                "reason_codes": ["missing_price_data"],
                "scan_group": "insufficient_history",
                "group_reason": "no daily price data",
                "trend_template": {"conditions_met": 0, "pass": False},
                "trade_readiness": {"status": "INSUFFICIENT_HISTORY"},
                "close": None,
                "last_date": None,
            },
            {
                "symbol": "ERROR",
                "analysis_status": "NOT_VERIFIED",
                "reason_codes": ["analysis_exception"],
                "scan_group": "not_verified",
                "group_reason": "analysis failed",
                "trend_template": {"conditions_met": 0, "pass": False},
                "trade_readiness": {"status": "NOT_VERIFIED"},
                "close": None,
                "last_date": None,
            },
        ]

        pg = MagicMock()
        result = persist_daily_scan_snapshot(pg, results, scan_date=scan_date)

        snapshot_calls = [
            call for call in pg.cursor.return_value.execute.call_args_list
            if "INSERT INTO daily_analysis_snapshots" in call.args[0]
        ]
        assert result["observation_count"] == 2
        assert [call.args[1][4] for call in snapshot_calls] == [scan_date, scan_date]
        for call in snapshot_calls:
            params = call.args[1]
            assert params[5] is None  # close
            assert params[6] is None  # volume
            assert params[7] is None  # ma20
            assert json.loads(params[-1]) == {}

        observation_calls = [
            call for call in pg.cursor.return_value.execute.call_args_list
            if "INSERT INTO daily_scan_observations" in call.args[0]
        ]
        missing_payload = json.loads(observation_calls[0].args[1][-1])
        error_payload = json.loads(observation_calls[1].args[1][-1])
        assert missing_payload["analysis_status"] == "INSUFFICIENT_HISTORY"
        assert missing_payload["reason_codes"] == ["missing_price_data"]
        assert error_payload["analysis_status"] == "NOT_VERIFIED"
        assert error_payload["reason_codes"] == ["analysis_exception"]

    def test_snapshot_mapping_keeps_normal_analysis_date_and_values(self):
        from scan_history import persist_daily_scan_snapshot

        pg = MagicMock()
        persist_daily_scan_snapshot(
            pg,
            [{
                "symbol": "NORMAL",
                "last_date": "2026-08-12",
                "close": 12.5,
                "scan_group": "breakout_new",
                "trend_template": {"conditions_met": 8, "pass": True, "rs_rating": 95.0},
                "analysis_metrics": {"volume": 1000.0, "ma20": 12.0},
                "trade_readiness": {"status": "BUY"},
            }],
            scan_date=dt.date(2026, 8, 13),
        )

        snapshot_call = next(
            call for call in pg.cursor.return_value.execute.call_args_list
            if "INSERT INTO daily_analysis_snapshots" in call.args[0]
        )
        params = snapshot_call.args[1]
        assert params[4] == dt.date(2026, 8, 12)
        assert params[5] == 12.5
        assert params[6] == 1000.0
        assert params[7] == 12.0

    def test_retry_persists_explicit_parent_and_deterministic_original_root(self):
        from scan_history import persist_daily_scan_snapshot

        pg = MagicMock()
        parent_run_id = "00000000-0000-0000-0000-000000000002"
        original_run_id = "00000000-0000-0000-0000-000000000001"
        pg.cursor.return_value.fetchone.return_value = (original_run_id,)

        result = persist_daily_scan_snapshot(
            pg,
            self._results(),
            scan_date=dt.date(2026, 8, 13),
            retry_of_run_id=parent_run_id,
        )

        execute_calls = pg.cursor.return_value.execute.call_args_list
        root_lookup = next(call for call in execute_calls if "COALESCE(retry_root_run_id, id)" in call.args[0])
        self.assertEqual(root_lookup.args[1], (parent_run_id,))
        run_insert = next(call for call in execute_calls if "INSERT INTO daily_scan_runs" in call.args[0])
        self.assertEqual(run_insert.args[1][5], parent_run_id)
        self.assertEqual(run_insert.args[1][6], original_run_id)
        self.assertEqual(result["retry_root_run_id"], original_run_id)

    def test_schema_blocks_updates_and_deletes_to_snapshots(self):
        from scan_history import init_daily_scan_history_schema

        pg = MagicMock()
        init_daily_scan_history_schema(pg)

        sql = "\n".join(call.args[0] for call in pg.cursor.return_value.execute.call_args_list)
        self.assertIn("CREATE TABLE IF NOT EXISTS daily_scan_runs", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS daily_scan_observations", sql)
        self.assertIn("daily_scan_history_reject_mutation", sql)
        self.assertIn("BEFORE UPDATE OR DELETE", sql)

    def test_schema_has_audited_canonical_selection_and_quarantine_views(self):
        from scan_history import init_daily_scan_history_schema

        pg = MagicMock()
        init_daily_scan_history_schema(pg)
        sql = "\n".join(call.args[0] for call in pg.cursor.return_value.execute.call_args_list)
        self.assertIn("daily_scan_run_selection_audit", sql)
        self.assertIn("selection_status IN ('selected','quarantined','legacy','excluded')", sql)
        self.assertIn("daily_scan_run_audit_coverage", sql)
        self.assertIn("legacy_scanner_version_excluded_from_canonical", sql)
        self.assertIn("duplicate_backfill_run", sql)
        self.assertIn("daily_canonical_scan_runs", sql)
        self.assertIn("daily_canonical_breakout_event_observations", sql)
        self.assertIn("observed_on_run_scan_date_mismatch", sql)
        self.assertIn("daily_canonical_breakout_events", sql)

    def test_active_lifecycle_sql_uses_distinct_canonical_dates(self):
        from scan_history import active_breakout_events

        pg = MagicMock()
        pg.cursor.return_value.fetchall.return_value = []
        active_breakout_events(pg)
        sql = pg.cursor.return_value.execute.call_args.args[0]
        self.assertIn("COUNT(DISTINCT r.scan_date)", sql)
        self.assertIn("daily_canonical_scan_runs", sql)
        self.assertIn("daily_canonical_breakout_event_observations", sql)
        self.assertNotIn("FROM daily_scan_runs r WHERE r.scan_date", sql)


if __name__ == "__main__":
    unittest.main()
