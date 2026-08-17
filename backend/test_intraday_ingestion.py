import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import update_data as u


def candle(ts=1_700_000_000):
    return {
        "time": [ts],
        "open": [10],
        "high": [11],
        "low": [9],
        "close": [10.5],
        "volume": [100],
    }


class FakeMarket:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.symbols = []

    def get_candlestick(self, **kwargs):
        self.symbols.append(kwargs["symbol"])
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return candle()


class IntradayBatchIngestionTests(unittest.TestCase):
    @patch("update_data.insert_intraday_rows")
    def test_initializes_one_session_and_upserts_configured_batches(self, insert_rows):
        market = FakeMarket()
        factory = MagicMock(return_value=market)
        sleeps = []
        insert_rows.side_effect = lambda _pg, rows, **_kw: len(rows)

        summary = u.ingest_shortlist_intraday(
            MagicMock(), {}, symbols=["AAA", "BBB", "CCC"], batch_size=2,
            batch_delay=1.0, batch_jitter=0.25, per_symbol_delay=0,
            session_retries=1, market_factory=factory,
            sleep_fn=sleeps.append, jitter_fn=lambda _a, _b: 0.2,
        )

        factory.assert_called_once_with()
        self.assertEqual(market.symbols, ["AAA", "BBB", "CCC"])
        self.assertEqual([len(c.args[1]) for c in insert_rows.call_args_list], [2, 1])
        self.assertEqual(sleeps, [1.2])
        self.assertEqual(summary["status"], "full_success")
        self.assertEqual(summary["symbols_attempted"], 3)
        self.assertEqual(summary["symbols_succeeded"], 3)
        self.assertEqual(summary["symbols_failed"], 0)

    @patch("update_data.insert_intraday_rows")
    def test_u102_during_initial_session_creation_recovers_within_bound(self, insert_rows):
        recovered = FakeMarket([candle()])
        factory = MagicMock(side_effect=[
            RuntimeError("U-102: UserSession is unavailable"), recovered,
        ])
        insert_rows.side_effect = lambda _pg, rows, **_kw: len(rows)

        summary = u.ingest_shortlist_intraday(
            MagicMock(), {}, symbols=["AAA"], batch_size=1,
            batch_delay=0, batch_jitter=0, per_symbol_delay=0,
            session_retries=1, retry_backoff=0, market_factory=factory,
            sleep_fn=lambda _seconds: None, jitter_fn=lambda _a, _b: 0,
        )

        self.assertEqual(factory.call_count, 2)
        self.assertEqual(summary["retry_count"], 1)
        self.assertEqual(summary["status"], "full_success")

    @patch("update_data.insert_intraday_rows")
    def test_u102_reauthenticates_and_retries_only_failed_batch(self, insert_rows):
        first = FakeMarket([candle(), candle(), RuntimeError("U-102: UserSession is unavailable")])
        recovered = FakeMarket([candle(), candle()])
        factory = MagicMock(side_effect=[first, recovered])
        insert_rows.side_effect = lambda _pg, rows, **_kw: len(rows)

        summary = u.ingest_shortlist_intraday(
            MagicMock(), {}, symbols=["AAA", "BBB", "CCC", "DDD"], batch_size=2,
            batch_delay=0, batch_jitter=0, per_symbol_delay=0,
            session_retries=1, retry_backoff=0, market_factory=factory,
            sleep_fn=lambda _seconds: None, jitter_fn=lambda _a, _b: 0,
        )

        self.assertEqual(factory.call_count, 2)
        self.assertEqual(first.symbols, ["AAA", "BBB", "CCC"])
        self.assertEqual(recovered.symbols, ["CCC", "DDD"])
        self.assertEqual(summary["retry_count"], 1)
        self.assertEqual(summary["status"], "full_success")
        self.assertEqual([c.args[1][0][0] for c in insert_rows.call_args_list], ["AAA", "CCC"])

    @patch("update_data.insert_intraday_rows")
    def test_empty_symbol_response_prevents_false_full_success(self, insert_rows):
        market = FakeMarket([{}, candle()])
        insert_rows.side_effect = lambda _pg, rows, **_kw: len(rows)

        summary = u.ingest_shortlist_intraday(
            MagicMock(), {}, symbols=["AAA", "BBB"], batch_size=2,
            batch_delay=0, batch_jitter=0, per_symbol_delay=0,
            session_retries=0, market_factory=MagicMock(return_value=market),
            sleep_fn=lambda _seconds: None, jitter_fn=lambda _a, _b: 0,
        )

        self.assertEqual(summary["status"], "partial_success")
        self.assertEqual(summary["failed_symbols"], ["AAA"])
        self.assertFalse(insert_rows.call_args.kwargs["record_fetch_status"])

    @patch("update_data.insert_intraday_rows")
    def test_partial_failure_continues_and_never_advances_success_timestamp(self, insert_rows):
        market = FakeMarket([RuntimeError("bad AAA"), candle(), candle()])
        insert_rows.side_effect = lambda _pg, rows, **_kw: len(rows)

        summary = u.ingest_shortlist_intraday(
            MagicMock(), {}, symbols=["AAA", "BBB", "CCC"], batch_size=2,
            batch_delay=0, batch_jitter=0, per_symbol_delay=0,
            session_retries=0, market_factory=MagicMock(return_value=market),
            sleep_fn=lambda _seconds: None, jitter_fn=lambda _a, _b: 0,
        )

        self.assertEqual(market.symbols, ["AAA", "BBB", "CCC"])
        self.assertEqual(summary["status"], "partial_success")
        self.assertEqual(summary["symbols_succeeded"], 2)
        self.assertEqual(summary["symbols_failed"], 1)
        self.assertEqual(summary["failed_symbols"], ["AAA"])
        self.assertTrue(all(c.kwargs["record_fetch_status"] is False
                            for c in insert_rows.call_args_list))
        self.assertEqual(len(summary["batches"]), 2)
        self.assertEqual(summary["batches"][0]["db_upsert_result"], 1)

    @patch("update_data.insert_intraday_rows")
    def test_rerun_uses_existing_current_candle_upsert_contract(self, insert_rows):
        market = FakeMarket([candle(), candle()])
        insert_rows.side_effect = lambda _pg, rows, **_kw: len(rows)
        kwargs = dict(
            symbols=["AAA"], batch_size=1, batch_delay=0, batch_jitter=0,
            per_symbol_delay=0, session_retries=0,
            sleep_fn=lambda _seconds: None, jitter_fn=lambda _a, _b: 0,
        )

        u.ingest_shortlist_intraday(MagicMock(), {}, market_factory=MagicMock(return_value=market), **kwargs)
        u.ingest_shortlist_intraday(MagicMock(), {}, market_factory=MagicMock(return_value=market), **kwargs)

        self.assertEqual(insert_rows.call_count, 2)
        for invocation in insert_rows.call_args_list:
            self.assertEqual(invocation.args[1][0][0:3], ("AAA", "60m", invocation.args[1][0][2]))


class IntradayUpsertContractTests(unittest.TestCase):
    def test_schema_contains_separate_intraday_run_status_table(self):
        pg = MagicMock()

        u.ensure_intraday_table(pg)

        schema = pg.cursor.return_value.execute.call_args.args[0]
        self.assertIn("CREATE TABLE IF NOT EXISTS intraday_ingestion_runs", schema)
        self.assertIn("symbols_succeeded INTEGER NOT NULL", schema)
        self.assertIn("db_upsert_result JSONB NOT NULL", schema)

    @patch("update_data.psycopg2.extras.execute_values")
    def test_batch_upsert_can_commit_without_advancing_canonical_freshness(self, execute_values):
        pg = MagicMock()
        rows = [("AAA", "60m", "2026-08-14T10:00:00+07:00", 1, 2, 1, 2, 100)]

        offered = u.insert_intraday_rows(pg, rows, record_fetch_status=False)

        self.assertEqual(offered, 1)
        execute_values.assert_called_once()
        self.assertFalse(any("data_fetch_status" in str(c.args[0])
                             for c in pg.cursor.return_value.execute.call_args_list))
        pg.commit.assert_called_once_with()

    def test_partial_run_status_is_persisted_without_touching_canonical_freshness(self):
        pg = MagicMock()
        summary = {
            "run_id": "run-1", "status": "partial_success",
            "symbols_attempted": 3, "symbols_succeeded": 2, "symbols_failed": 1,
            "retry_count": 1, "fetch_started_at": "2026-08-14T03:15:00+00:00",
            "fetch_completed_at": "2026-08-14T03:16:00+00:00",
            "rows_offered": 2, "failed_symbols": ["AAA"], "batches": [],
        }

        u.record_intraday_run_summary(pg, summary)

        sql = pg.cursor.return_value.execute.call_args.args[0]
        self.assertIn("intraday_ingestion_runs", sql)
        self.assertNotIn("data_fetch_status", sql)
        pg.commit.assert_called_once_with()


class IntradayRunExitTests(unittest.TestCase):
    @patch("update_data.get_pg")
    @patch("update_data._intraday_shortlist", return_value=["AAA"])
    @patch("update_data.ingest_shortlist_intraday")
    def test_partial_run_returns_nonzero_and_records_summary(self, ingest, _shortlist, get_pg):
        ingest.return_value = {
            "run_id": "run-1", "status": "partial_success",
            "symbols_attempted": 1, "symbols_succeeded": 0, "symbols_failed": 1,
            "retry_count": 1, "fetch_started_at": "a", "fetch_completed_at": "b",
            "rows_offered": 0, "failed_symbols": ["AAA"], "batches": [],
        }
        args = SimpleNamespace(
            intraday_only=True, intraday_mode="tier1", intraday_interval="60m",
            dry_run=False, intraday_limit=8, intraday_batch_size=5,
            intraday_batch_delay=1.0, intraday_batch_jitter=0.2,
            intraday_session_retries=1, intraday_retry_backoff=2.0,
        )

        with patch("update_data.ensure_intraday_table"), \
             patch("update_data.record_intraday_run_summary") as record:
            exit_code = u.run(args)

        self.assertEqual(exit_code, 1)
        record.assert_called_once_with(get_pg.return_value, ingest.return_value)
        get_pg.return_value.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
