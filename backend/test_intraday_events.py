"""TDD contract tests for intraday emerging event persistence + EOD reconciliation.

Covers the P0 contract:
- Daily is the official/final state; intraday emerging events are append-only.
- Intraday events persist with source_lineage provenance.
- EOD reconciliation classifies each emerging event as:
  confirmed / expired / invalidated / not_confirmed.
- Evidence (source / freshness / baseline) is exposed via get_active_intraday_events.
"""
import datetime as dt
import unittest
from unittest.mock import MagicMock


UTC = dt.timezone.utc
RUN_TS = dt.datetime(2026, 8, 14, 6, 0, tzinfo=UTC)
CANDLE_TS = dt.datetime(2026, 8, 14, 6, 0, tzinfo=UTC)
SCAN_RUN_ID = "00000000-0000-0000-0000-000000000001"
SCAN_DATE = dt.date(2026, 8, 14)


def _pg():
    """Fresh MagicMock cursor. fetchone/fetchall return plain values/tuples."""
    pg = MagicMock()
    cur = MagicMock()
    pg.cursor.return_value = cur
    cur.fetchone.return_value = None
    cur.fetchall.return_value = []
    return pg, cur


def _sample_event(symbol="TEST", trigger=11.0, price=11.5, stage="ready_validate"):
    return {
        "symbol": symbol,
        "origin": "intraday_breakout",
        "trigger_price": trigger,
        "first_candle_ts": CANDLE_TS,
        "interval": "60m",
        "qualification_close": price,
        "qualification_volume_ratio": 1.5,
        "pre_break_pivot_low": 10.0,
        "failure_level": 10.5,
        "trend_template_conditions": 8,
        "rs_rating": 90.0,
        "observations": [{
            "candle_ts": CANDLE_TS,
            "stage": stage,
            "close": price,
            "distance_from_trigger_pct": 4.5,
            "rsi_daily": 60,
            "volume_ratio_50": 1.5,
            "failure_reason": None,
            "raw_evidence": {"base_group": "breakout_new", "action": "WATCH", "reason": "test"},
        }],
    }


class PersistIntradayEventsTests(unittest.TestCase):
    def test_active_events_are_deduped_by_symbol_trigger_interval(self):
        from scan_history import persist_intraday_events

        pg, cur = _pg()
        # First call: no active event -> INSERT
        cur.fetchone.return_value = None
        persist_intraday_events(pg, [_sample_event()], source_lineage={"source": "intraday_evaluator"})
        inserts = [c for c in cur.execute.call_args_list if "INSERT INTO intraday_events" in c.args[0]]
        self.assertEqual(len(inserts), 1)

    def test_existing_active_event_is_reused_not_reinserted(self):
        from scan_history import persist_intraday_events

        pg, cur = _pg()
        # Simulate an existing active emerging event for same symbol/trigger
        cur.fetchone.return_value = ("existing-event-id",)
        events_created = persist_intraday_events(pg, [_sample_event()])
        self.assertEqual(events_created["events_created"], 0)
        inserts = [c for c in cur.execute.call_args_list if "INSERT INTO intraday_events" in c.args[0]]
        self.assertEqual(len(inserts), 0)
        # Observation upsert still runs
        obs_inserts = [c for c in cur.execute.call_args_list if "INSERT INTO intraday_event_observations" in c.args[0]]
        self.assertEqual(len(obs_inserts), 1)

    def test_source_lineage_is_persisted_on_event(self):
        from scan_history import persist_intraday_events

        pg, cur = _pg()
        cur.fetchone.return_value = None
        lineage = {"source": "intraday_evaluator", "mode": "active", "run_id": "run-xyz"}
        persist_intraday_events(pg, [_sample_event()], source_lineage=lineage)
        insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO intraday_events" in c.args[0])
        params = insert_call.args[1]
        # source_lineage is the last positional param in the INSERT
        lineage_json = params[-1]
        import json as _json
        parsed = _json.loads(lineage_json)
        self.assertEqual(parsed["source"], "intraday_evaluator")
        self.assertEqual(parsed["mode"], "active")
        self.assertEqual(parsed["run_id"], "run-xyz")

    def test_empty_events_returns_zero_counts(self):
        from scan_history import persist_intraday_events
        pg, cur = _pg()
        result = persist_intraday_events(pg, [])
        self.assertEqual(result, {"events_created": 0, "observations_appended": 0})

    def test_observation_deduped_by_event_and_candle_ts(self):
        from scan_history import persist_intraday_events
        pg, cur = _pg()
        cur.fetchone.return_value = ("evt-1",)
        persist_intraday_events(pg, [_sample_event()])
        obs_call = next(c for c in cur.execute.call_args_list if "INSERT INTO intraday_event_observations" in c.args[0])
        # Ensure ON CONFLICT includes (event_id, candle_ts)
        self.assertIn("(event_id, candle_ts)", obs_call.args[0])


class ReconcileIntradayEventsTests(unittest.TestCase):
    # Column order for the daily_breakout_events SELECT in reconcile:
    # id, symbol, trigger_price, origin, pre_break_pivot_low, failure_level,
    # qualified_on, qualification_close, qualification_volume_ratio,
    # trend_template_conditions, rs_rating
    def _eod_row(self, symbol="TEST", trigger=11.0):
        return ("daily-event-id-1", symbol, trigger, "daily_breakout",
                10.0, 10.5, SCAN_DATE, 11.5, 1.5, 8, 90.0)

    # Column order for the intraday emerging SELECT in reconcile:
    # id, symbol, trigger_price, first_candle_ts, failure_level,
    # pre_break_pivot_low, intraday_run_id
    def _emerging_row(self, symbol="TEST", trigger=11.0, failure=10.5, pivot=10.0):
        return ("intraday-evt-1", symbol, trigger, CANDLE_TS, failure, pivot, "run-1")

    def test_confirmed_links_to_daily_baseline_event(self):
        from scan_history import reconcile_intraday_events_at_eod

        pg, cur = _pg()
        # fetchone returns (scan_date,) for the first query; the observation
        # lookup fetchone is never reached on the confirmed path.
        cur.fetchone.side_effect = [(SCAN_DATE,), None]
        cur.fetchall.side_effect = [
            [self._eod_row()],           # daily eod events query
            [self._emerging_row()],      # intraday emerging query
        ]
        result = reconcile_intraday_events_at_eod(pg, SCAN_RUN_ID, "signalix/daily-state-v2", symbols=["TEST"])
        self.assertEqual(result["promoted"], 1)
        self.assertEqual(result["expired"], 0)
        self.assertEqual(result["not_confirmed"], 0)

        # Verify the UPDATE sets confidence=confirmed and resolved_daily_event_id
        updates = [c for c in cur.execute.call_args_list
                   if "UPDATE intraday_events" in c.args[0] and "confirmed" in c.args[0]]
        self.assertEqual(len(updates), 1)
        sql, params = updates[0].args
        self.assertIn("resolved_daily_event_id", sql)
        self.assertIn("reconciled_at", sql)
        self.assertEqual(params[0], "daily-event-id-1")

    def test_expired_when_no_eod_breakout_and_not_invalidated(self):
        from scan_history import reconcile_intraday_events_at_eod

        pg, cur = _pg()
        cur.fetchone.side_effect = [(SCAN_DATE,), (11.0,)]  # latest obs close above failure
        cur.fetchall.side_effect = [
            [],                          # no eod events
            [self._emerging_row()],      # intraday emerging
        ]
        result = reconcile_intraday_events_at_eod(pg, SCAN_RUN_ID, "signalix/daily-state-v2")
        self.assertEqual(result["expired"], 1)
        self.assertEqual(result["promoted"], 0)

    def test_invalidated_when_latest_close_below_failure_level(self):
        from scan_history import reconcile_intraday_events_at_eod

        pg, cur = _pg()
        cur.fetchone.side_effect = [(SCAN_DATE,), (10.0,)]  # latest obs close below failure (10.5)
        cur.fetchall.side_effect = [
            [],                          # no eod events
            [self._emerging_row()],      # intraday emerging
        ]
        result = reconcile_intraday_events_at_eod(pg, SCAN_RUN_ID, "signalix/daily-state-v2")
        self.assertEqual(result["invalidated"], 1)
        self.assertEqual(result["expired"], 0)

    def test_not_confirmed_when_eod_has_breakout_different_trigger(self):
        from scan_history import reconcile_intraday_events_at_eod

        pg, cur = _pg()
        cur.fetchone.side_effect = [(SCAN_DATE,), None]
        cur.fetchall.side_effect = [
            [self._eod_row(trigger=12.0)],  # EOD breakout at 12.0, not 11.0
            [self._emerging_row(trigger=11.0)],
        ]
        result = reconcile_intraday_events_at_eod(pg, SCAN_RUN_ID, "signalix/daily-state-v2")
        self.assertEqual(result["not_confirmed"], 1)
        self.assertEqual(result["promoted"], 0)

    def test_only_emerging_events_are_reconciled_others_skipped(self):
        from scan_history import reconcile_intraday_events_at_eod

        pg, cur = _pg()
        cur.fetchone.side_effect = [(SCAN_DATE,), None]
        cur.fetchall.side_effect = [
            [],
            [self._emerging_row()],
        ]
        reconcile_intraday_events_at_eod(pg, SCAN_RUN_ID, "signalix/daily-state-v2")
        where_clauses = [c.args[0] for c in cur.execute.call_args_list
                         if "WHERE" in c.args[0] and "intraday_events" in c.args[0]]
        self.assertTrue(any("confidence = 'emerging'" in wc for wc in where_clauses))

    def test_reconciliation_is_idempotent_for_finalized_rows(self):
        from scan_history import reconcile_intraday_events_at_eod

        pg, cur = _pg()
        cur.fetchone.side_effect = [(SCAN_DATE,)]
        cur.fetchall.side_effect = [
            [],                  # no eod events
            [],                  # no emerging events
        ]
        result = reconcile_intraday_events_at_eod(pg, SCAN_RUN_ID, "signalix/daily-state-v2")
        self.assertEqual(sum(result.values()), 0)


class GetActiveIntradayEventsTests(unittest.TestCase):
    # Column order for get_active_intraday_events SELECT:
    # id, symbol, origin, trigger_price, first_seen, first_candle_ts, interval,
    # confidence, failure_level, pre_break_pivot_low, intraday_run_id,
    # resolved_daily_event_id, reconciled_at
    def _confirmed_row(self):
        return ("evt-1", "TEST", "intraday_breakout", 11.0, RUN_TS, CANDLE_TS,
                "60m", "confirmed", 10.5, 10.0, "run-1", "daily-event-id-1", RUN_TS)

    def _emerging_row(self):
        return ("evt-1", "TEST", "intraday_breakout", 11.0, RUN_TS, CANDLE_TS,
                "60m", "emerging", 10.5, 10.0, "run-xyz", None, None)

    def test_confirmed_event_carries_resolved_daily_event_id_baseline(self):
        from scan_history import get_active_intraday_events

        pg, cur = _pg()
        cur.fetchall.return_value = [self._confirmed_row()]
        out = get_active_intraday_events(pg)
        self.assertEqual(out["TEST"]["confidence"], "confirmed")
        self.assertEqual(out["TEST"]["resolved_daily_event_id"], "daily-event-id-1")
        self.assertEqual(out["TEST"]["reconciled_at"], RUN_TS.isoformat())
        self.assertEqual(out["TEST"]["failure_level"], 10.5)
        self.assertEqual(out["TEST"]["intraday_run_id"], "run-1")

    def test_emerging_event_reports_source_lineage_run_id(self):
        from scan_history import get_active_intraday_events

        pg, cur = _pg()
        cur.fetchall.return_value = [self._emerging_row()]
        out = get_active_intraday_events(pg)
        self.assertEqual(out["TEST"]["confidence"], "emerging")
        self.assertIsNone(out["TEST"]["resolved_daily_event_id"])
        self.assertEqual(out["TEST"]["intraday_run_id"], "run-xyz")

    def test_active_query_filters_to_emerging_and_confirmed(self):
        from scan_history import get_active_intraday_events

        pg, cur = _pg()
        cur.fetchall.return_value = []
        get_active_intraday_events(pg)
        sql = cur.execute.call_args_list[0].args[0]
        self.assertIn("confidence IN ('emerging','confirmed')", sql)


if __name__ == "__main__":
    unittest.main()
