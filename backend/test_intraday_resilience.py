import datetime as dt
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import update_data


UTC = dt.timezone.utc


class IntradayUpsertAccountingTests(unittest.TestCase):
    @patch("update_data.publish_canonical_read_model")
    @patch("update_data.refresh_dashboard_from_existing_scan")
    @patch("update_data.run_vcp_after_ingestion")
    @patch("update_data.record_intraday_run_summary")
    @patch("update_data.update_intraday_feed_status")
    @patch("update_data.ingest_intraday")
    @patch("update_data.ensure_intraday_table")
    @patch("update_data._intraday_universe", return_value=["AAA"])
    @patch("update_data.get_pg")
    def test_intraday_run_publishes_once_at_shared_boundary(
        self, get_pg, universe, ensure_table, ingest, update_status,
        record_summary, run_vcp, refresh, publish,
    ):
        ingest.return_value = {
            "run_id": "60m-run-1", "status": "full_success",
            "fetch_completed_at": "2026-09-02T09:00:00+00:00",
            "symbols_attempted": 1, "rows_offered": 1, "symbols_failed": 0,
        }
        args = SimpleNamespace(
            intraday_only=True,
            intraday_mode="full",
            intraday_interval="60m",
            dry_run=False,
            scan=False,
            intraday_full_universe=False,
            intraday_shortlist=False,
            intraday_universe="marginable_long",
            intraday_limit=None,
            intraday_batch_size=1,
            intraday_batch_delay=0,
            intraday_batch_jitter=0,
            intraday_session_retries=0,
            intraday_retry_backoff=0,
        )

        self.assertEqual(update_data.run(args), 0)
        # Intraday refresh must not rebuild/publish Daily decisions.
        publish.assert_not_called()

    @patch("mvp_api.resolve_universe", side_effect=[
        (["AAA"], {"universe_filter": "marginable_long"}),
        (["AAA", "BBB", "CCC"], {"universe_filter": "active_ord"}),
    ])
    def test_intraday_default_scope_is_canonical_and_active_ord_is_explicit(self, resolver):
        assert update_data._intraday_universe(MagicMock(), "marginable_long") == ["AAA"]
        assert update_data._intraday_universe(MagicMock(), "active_ord") == ["AAA", "BBB", "CCC"]
        assert [call.args[1] for call in resolver.call_args_list] == ["marginable_long", "active_ord"]

    @patch("update_data.time.sleep")
    @patch("update_data._parse_settrade_intraday", return_value=[("AAA", "bar")])
    @patch("update_data._settrade_market")
    @patch("update_data._intraday_universe", return_value=["AAA"])
    def test_legacy_fetch_intraday_returns_rows_without_undefined_summary(
        self, universe, market_factory, parse, sleep,
    ):
        market_factory.return_value.get_candlestick.return_value = {"time": []}

        rows = update_data.fetch_intraday(MagicMock(), {}, limit=4)

        assert rows == [("AAA", "bar")]
        market_factory.return_value.get_candlestick.assert_called_once_with(
            symbol="AAA", interval="60m", limit=4, normalized=update_data.SETTRADE_NORMALIZED)

    def test_intraday_only_rejects_scan_to_prevent_overlapping_rounds(self):
        args = SimpleNamespace(intraday_only=True, scan=True)
        with self.assertRaisesRegex(ValueError, "not allowed"):
            update_data.run(args)

    @patch("update_data.publish_canonical_read_model")
    @patch("build_dashboard.build", return_value={"ok": True})
    @patch("update_data.get_pg")
    def test_intraday_refresh_does_not_publish_before_shared_boundary(self, get_pg, build, publish):
        pg = get_pg.return_value
        pg.cursor.return_value.fetchone.return_value = ("daily-run-1",)
        pg.cursor.return_value.fetchall.return_value = [({"symbol": "AAA"},)]

        self.assertEqual(update_data.refresh_dashboard_from_existing_scan(), {"ok": True})
        build.assert_called_once_with(scanned=[{"symbol": "AAA"}], run_id="daily-run-1")
        publish.assert_not_called()

    @patch("read_model_publisher.publish_builder_result")
    @patch("update_data.get_pg")
    def test_read_model_publish_uses_persisted_daily_and_intraday_lineage(self, get_pg, publish):
        daily_date = dt.date(2026, 9, 1)
        daily_timestamp = dt.datetime(2026, 9, 1, 11, 0, tzinfo=UTC)
        intraday_completed = dt.datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
        pg = get_pg.return_value
        pg.cursor.return_value.fetchone.side_effect = [
            ("daily-run-1", daily_date, daily_timestamp, {"source": "price_data"}),
            ("60m-run-1", "partial_success", intraday_completed),
        ]

        update_data.publish_canonical_read_model()

        kwargs = publish.call_args.kwargs
        assert kwargs["source_versions"] == {
            "daily": {
                "run_id": "daily-run-1",
                "as_of": "2026-09-01",
                "run_timestamp": "2026-09-01T11:00:00+00:00",
                "source_lineage": {"source": "price_data"},
            },
            "intraday": {
                "run_id": "60m-run-1",
                "status": "partial_success",
                "as_of": "2026-09-02T09:00:00+00:00",
            },
        }
        assert kwargs["market"] == "TH"
        from read_model_publisher import DEFAULT_ROOT
        assert kwargs["root"] == str(DEFAULT_ROOT)
        pg.close.assert_called_once()

    @patch.dict("os.environ", {"SIGNALIX_READ_MODEL_ROOT": "/tmp/signalix-test-read-model"})
    @patch("read_model_publisher.publish_builder_result")
    @patch("update_data.get_pg")
    def test_read_model_publish_preserves_root_override(self, get_pg, publish):
        daily_date = dt.date(2026, 9, 1)
        daily_timestamp = dt.datetime(2026, 9, 1, 11, 0, tzinfo=UTC)
        pg = get_pg.return_value
        pg.cursor.return_value.fetchone.side_effect = [
            ("daily-run-1", daily_date, daily_timestamp, {"source": "price_data"}),
            ("60m-run-1", "full_success", "2026-09-02T09:00:00+00:00"),
        ]

        update_data.publish_canonical_read_model()

        assert publish.call_args.kwargs["root"] == "/tmp/signalix-test-read-model"

    @patch("read_model_publisher.publish_builder_result")
    @patch("update_data.get_pg")
    def test_read_model_publish_skips_without_both_completed_lineages(self, get_pg, publish):
        pg = get_pg.return_value
        pg.cursor.return_value.fetchone.side_effect = [(None,), ("60m-run-1", "full_success", "now")]

        assert update_data.publish_canonical_read_model() is None
        publish.assert_not_called()

    @patch("mvp_routes._acquire_setup_candidates_pg")
    def test_api_metadata_overlay_uses_latest_completed_run_without_rebuilding(self, acquire):
        pg = MagicMock()
        pg.cursor.return_value.fetchone.return_value = (
            "60m-new", "partial_success", dt.datetime(2026, 9, 2, 9, tzinfo=UTC))
        acquire.return_value = (pg, MagicMock())
        payload = {"freshness": {}, "provenance": {"source_versions": {
            "intraday": {"run_id": "60m-old", "as_of": "2026-09-02T08:00:00+00:00"}}}}
        actual = __import__("mvp_routes")._overlay_latest_intraday_metadata(payload)
        assert actual["freshness"]["intraday_latest_run_id"] == "60m-new"
        assert actual["intraday_latest_run"]["fetch_completed_at"] == "2026-09-02T09:00:00+00:00"
        assert actual["provenance"]["source_versions"]["intraday"] == {
            "run_id": "60m-new", "status": "partial_success",
            "as_of": "2026-09-02T09:00:00+00:00",
        }
        assert actual["provenance"]["intraday_as_of"] == "2026-09-02T09:00:00+00:00"

    @patch("mvp_routes._acquire_setup_candidates_pg")
    def test_api_metadata_overlay_preserves_read_model_identity_and_daily_lineage(self, acquire):
        pg = MagicMock()
        pg.cursor.return_value.fetchone.return_value = (
            "60m-new", "full_success", "2026-09-02T09:00:00+00:00")
        acquire.return_value = (pg, MagicMock())
        payload = {
            "source_version": "immutable-read-model-id",
            "provenance": {"as_of": "2026-09-01", "intraday_as_of": "old",
                            "source_versions": {
                                "daily": {"run_id": "daily-1", "as_of": "2026-09-01"},
                                "intraday": {"run_id": "60m-old", "as_of": "old"}}},
        }

        actual = __import__("mvp_routes")._overlay_latest_intraday_metadata(payload)

        assert actual["source_version"] == "immutable-read-model-id"
        assert actual["provenance"]["source_versions"]["daily"] == {
            "run_id": "daily-1", "as_of": "2026-09-01"}
        assert payload["provenance"]["intraday_as_of"] == "old"

    def test_vcp_handoff_skips_provenance_incomplete_success(self):
        pg = MagicMock()

        result = update_data.run_vcp_after_ingestion(pg, {
            "run_id": None,
            "status": "full_success",
            "fetch_completed_at": "2026-08-29T09:00:00+00:00",
        })

        self.assertIsNone(result)
        pg.cursor.assert_not_called()

    @patch("update_data.psycopg2.extras.execute_values")
    def test_upsert_reports_inserted_and_updated_rows(self, execute_values):
        execute_values.return_value = [(True,), (False,), (False,)]
        pg = MagicMock()
        rows = [
            ("A", "60m", "2026-08-14T12:00:00+07:00", 1, 1, 1, 1, 1),
            ("B", "60m", "2026-08-14T12:00:00+07:00", 2, 2, 2, 2, 2),
            ("C", "60m", "2026-08-14T12:00:00+07:00", 3, 3, 3, 3, 3),
        ]
        stats = {}

        offered = update_data.insert_intraday_rows(pg, rows, stats=stats)

        self.assertEqual(offered, 3)
        self.assertEqual(stats["intraday_inserted"], 1)
        self.assertEqual(stats["intraday_updated"], 2)
        self.assertIn("RETURNING (xmax = 0)", execute_values.call_args.args[1])
        self.assertTrue(execute_values.call_args.kwargs["fetch"])

    def test_run_log_has_timestamp_run_id_and_explicit_counts(self):
        line = update_data.format_intraday_run_log(
            run_id="intraday-20260814T052500Z-abcd1234",
            timestamp=dt.datetime(2026, 8, 14, 5, 25, tzinfo=UTC),
            interval="60m",
            symbols=3,
            offered=5,
            inserted=2,
            updated=3,
            failed=1,
        )

        self.assertIn("timestamp=2026-08-14T05:25:00+00:00", line)
        self.assertIn("run_id=intraday-20260814T052500Z-abcd1234", line)
        self.assertIn("2 inserted / 3 updated", line)
        self.assertIn("failed=1", line)

    @patch("update_data.insert_intraday_rows")
    def test_batched_ingestion_aggregates_inserted_and_updated_counts(self, insert_rows):
        market = MagicMock()
        market.get_candlestick.return_value = {
            "time": [1_786_680_000], "open": [1], "high": [1],
            "low": [1], "close": [1], "volume": [100],
        }

        def account(_pg, rows, **kwargs):
            batch_stats = kwargs["stats"]
            if rows[0][0] == "AAA":
                batch_stats.update(intraday_inserted=1, intraday_updated=0)
            else:
                batch_stats.update(intraday_inserted=0, intraday_updated=1)
            return len(rows)

        insert_rows.side_effect = account
        summary = update_data.ingest_intraday(
            MagicMock(), {}, symbols=["AAA", "BBB"], batch_size=1,
            batch_delay=0, batch_jitter=0, per_symbol_delay=0,
            session_retries=0, market_factory=MagicMock(return_value=market),
            sleep_fn=MagicMock(), jitter_fn=MagicMock(return_value=0),
        )

        self.assertEqual(summary["rows_inserted"], 1)
        self.assertEqual(summary["rows_updated"], 1)
        self.assertEqual(summary["attempted_symbols"], ["AAA", "BBB"])
        self.assertEqual(summary["batches"][0]["rows_inserted"], 1)
        self.assertEqual(summary["batches"][1]["rows_updated"], 1)


class SystemdResilienceContractTests(unittest.TestCase):
    def test_evaluator_runs_as_exec_stop_post_after_fetch_failure(self):
        unit = Path(__file__).with_name("signalix-intraday.service").read_text()

        self.assertIn("ExecStopPost=", unit)
        self.assertIn("-m backend.run_intraday_evaluation", unit)
        self.assertNotIn("ExecStartPost=", unit)
        self.assertIn("--intraday-universe marginable_long", unit)
        self.assertIn("--no-scan", unit)


if __name__ == "__main__":
    unittest.main()
