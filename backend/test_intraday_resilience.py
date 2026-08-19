import datetime as dt
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import update_data


UTC = dt.timezone.utc


class IntradayUpsertAccountingTests(unittest.TestCase):
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
        self.assertEqual(summary["batches"][0]["rows_inserted"], 1)
        self.assertEqual(summary["batches"][1]["rows_updated"], 1)


class SystemdResilienceContractTests(unittest.TestCase):
    def test_evaluator_runs_as_exec_stop_post_after_fetch_failure(self):
        unit = Path(__file__).with_name("signalix-intraday.service").read_text()

        self.assertIn("ExecStopPost=", unit)
        self.assertIn("-m backend.run_intraday_evaluation", unit)
        self.assertNotIn("ExecStartPost=", unit)


if __name__ == "__main__":
    unittest.main()
