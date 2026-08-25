"""TDD contract tests for immutable breakout event lifecycle + stage transitions (P0).

Tests verify:
  - Schema creates daily_breakout_event_stage_transitions table + index
  - persist_breakout_lifecycle records stage transition rows when the stage
    changes between observations for the same event
  - Idempotency: duplicate run does not create duplicate transitions
  - Mutation protection: stage_transitions table is in the immutable trigger set
  - Calibration: stage values from scan_results.json (S1_basing, S2_uptrend,
    S3_distributing, S4_down; phases: breakout_new, breakout_extended, etc.)
  - breakout_event_lifecycle query returns event + observations + transitions
"""
import datetime as dt
import json
import unittest
from unittest.mock import MagicMock, call


def _calibration_scan_results():
    """Historical calibration payload derived from scan_results.json groups.

    Real stage values observed:
      - S1_basing, S2_uptrend, S3_distributing, S4_down (daily_state.stage)
      - base_early, base_tight, breakout_new, breakout_extended,
        uptrend_pullback, waiting_breakout, topping, declining, broken
        (daily_state.phase)
    """
    return [
        {
            "symbol": "BJCHI",
            "last_date": "2026-08-13",
            "close": 2.30,
            "scan_group": "breakout_new",
            "trend_template": {"pass": False, "conditions_met": 4, "rs_rating": 32.0},
            "trade_readiness": {"status": "WAIT", "stop_loss": 0.57,
                                "breakout_level_20d": 0.64,
                                "pre_break_pivot_low": 0.57,
                                "volume_ratio_50": 1.82, "rsi_daily": 85.1},
            "daily_state": {
                "stage": "S2_uptrend",
                "phase": "breakout_extended",
                "stage_label": "Stage 2 · Uptrend",
                "phase_label": "Breakout extended",
                "origin": "unknown",
            },
            "active_breakout_event": {
                "event_id": "952c18c6-a816-4c9b-9ee7-a253507f0df1",
                "trigger_price": 0.64,
                "pivot_low": 0.57,
                "qualified_on": "2026-03-30",
            },
        },
    ]


class BreakoutLifecycleSchemaTests(unittest.TestCase):
    def test_schema_creates_stage_transitions_table(self):
        from scan_history import init_daily_scan_history_schema
        pg = MagicMock()
        init_daily_scan_history_schema(pg)
        sql = "\n".join(c.args[0] for c in pg.cursor.return_value.execute.call_args_list)
        self.assertIn("daily_breakout_event_stage_transitions", sql)
        self.assertIn("from_stage TEXT", sql)
        self.assertIn("to_stage TEXT NOT NULL", sql)
        self.assertIn("UNIQUE(event_id, to_stage, observed_on, scan_run_id)", sql)

    def test_schema_creates_stage_transitions_indexes(self):
        from scan_history import init_daily_scan_history_schema
        pg = MagicMock()
        init_daily_scan_history_schema(pg)
        sql = "\n".join(c.args[0] for c in pg.cursor.return_value.execute.call_args_list)
        self.assertIn("daily_breakout_event_stage_transitions_event_idx", sql)
        self.assertIn("daily_breakout_event_stage_transitions_scan_run_idx", sql)

    def test_stage_transitions_table_is_immutable(self):
        from scan_history import init_daily_scan_history_schema
        pg = MagicMock()
        init_daily_scan_history_schema(pg)
        sql = "\n".join(c.args[0] for c in pg.cursor.return_value.execute.call_args_list)
        # The table must be in the immutability trigger loop.
        trigger_blocks = [block for block in sql.split("CREATE TRIGGER")
                          if "daily_breakout_event_stage_transitions" in block]
        self.assertTrue(trigger_blocks, "stage_transitions table not in immutable trigger loop")
        for block in trigger_blocks:
            self.assertIn("daily_scan_history_reject_mutation", block)


class PersistBreakoutLifecycleTests(unittest.TestCase):
    def _existing_event_row(self):
        """Fake fetchone for the SELECT id FROM daily_breakout_events lookup
        that fires when ON CONFLICT finds an existing event."""
        return "952c18c6-a816-4c9b-9ee7-a253507f0df1"

    def _pg_with_run_and_event(self):
        """MagicMock pg where run lookup and event lookup return rows."""
        pg = MagicMock()
        cur = pg.cursor.return_value
        # persist_breakout_lifecycle first does: SELECT scan_date FROM daily_scan_runs WHERE id=%s
        cur.fetchone.side_effect = [
            ("2026-08-13",),        # run_scan_date lookup
            ("952c18c6-a816-4c9b-9ee7-a253507f0df1",),  # existing event lookup (event_id pre-known)
            (None,),  # prev observation stage lookup (no prior obs -> from_stage=None)
            ("S2_uptrend",),  # next call: for a second symbol with prior obs
        ]
        return pg

    def test_records_stage_transition_on_first_observation(self):
        """When an event has no prior observation, the first observation emits
        a transition from NULL (from_stage) to the current stage."""
        from scan_history import persist_breakout_lifecycle
        pg = self._pg_with_run_and_event()
        row = _calibration_scan_results()[0]
        result = persist_breakout_lifecycle(
            pg, [row], run_id="00000000-0000-0000-0000-000000000001",
            scanner_version="signalix/daily-state-v2",
        )
        sql_calls = [c.args[0] for c in pg.cursor.return_value.execute.call_args_list]
        # Must emit a stage-transitions INSERT.
        self.assertTrue(any("daily_breakout_event_stage_transitions" in s and "INSERT" in s
                            for s in sql_calls),
                        "no stage transition INSERT emitted")
        self.assertEqual(result["observations_appended"], 1)
        self.assertEqual(result["transitions_recorded"], 1)

    def test_records_transition_when_stage_changes(self):
        """If the previous observation stage differs from the current, a
        transition row is written with from_stage set to the old stage."""
        from scan_history import persist_breakout_lifecycle
        pg = MagicMock()
        cur = pg.cursor.return_value
        cur.fetchone.side_effect = [
            ("2026-08-14",),  # run_scan_date
            ("952c18c6-a816-4c9b-9ee7-a253507f0df1",),  # existing event
            ("S2_uptrend",),  # previous stage = S2_uptrend
        ]
        row = _calibration_scan_results()[0]
        row["daily_state"]["stage"] = "S3_distributing"  # stage changed
        row["last_date"] = "2026-08-14"
        result = persist_breakout_lifecycle(
            pg, [row], run_id="00000000-0000-0000-0000-000000000042",
            scanner_version="signalix/daily-state-v2",
        )
        transition_inserts = [
            c for c in cur.execute.call_args_list
            if "daily_breakout_event_stage_transitions" in c.args[0] and "INSERT" in c.args[0]
        ]
        self.assertEqual(len(transition_inserts), 1)
        params = transition_inserts[0].args[1]
        # params: (id, event_id, from_stage, to_stage, observed_on, close,
        #          distance_from_trigger_pct, scan_run_id, failure_reason, raw_evidence)
        self.assertEqual(params[2], "S2_uptrend")   # from_stage
        self.assertEqual(params[3], "S3_distributing")  # to_stage
        self.assertEqual(result["transitions_recorded"], 1)

    def test_no_transition_when_stage_unchanged(self):
        """Same stage as previous observation => no transition row written."""
        from scan_history import persist_breakout_lifecycle
        pg = MagicMock()
        cur = pg.cursor.return_value
        cur.fetchone.side_effect = [
            ("2026-08-14",),  # run_scan_date
            ("952c18c6-a816-4c9b-9ee7-a253507f0df1",),  # existing event
            ("S2_uptrend",),  # previous stage == current
        ]
        row = _calibration_scan_results()[0]
        # stage stays S2_uptrend (same as prior)
        result = persist_breakout_lifecycle(
            pg, [row], run_id="00000000-0000-0000-0000-000000000099",
            scanner_version="signalix/daily-state-v2",
        )
        transition_inserts = [
            c for c in cur.execute.call_args_list
            if "daily_breakout_event_stage_transitions" in c.args[0] and "INSERT" in c.args[0]
        ]
        self.assertEqual(len(transition_inserts), 0)
        self.assertEqual(result["transitions_recorded"], 0)

    def test_creates_new_event_for_fresh_breakout(self):
        """A fresh breakout with no active event ID creates a new event row
        with original trigger_price, pivot_low, and failure_level."""
        from scan_history import persist_breakout_lifecycle
        pg = MagicMock()
        cur = pg.cursor.return_value
        cur.fetchone.side_effect = [
            ("2026-08-13",),  # run_scan_date
            ("new-event-uuid-abc",),  # RETURNING id for the INSERT
            (None,),  # prev observation (no prior obs)
        ]
        row = _calibration_scan_results()[0]
        # Remove active_breakout_event to simulate a fresh breakout
        row.pop("active_breakout_event", None)
        result = persist_breakout_lifecycle(
            pg, [row], run_id="00000000-0000-0000-0000-000000000003",
            scanner_version="signalix/daily-state-v2",
        )
        event_inserts = [
            c for c in cur.execute.call_args_list
            if "daily_breakout_events" in c.args[0] and "INSERT" in c.args[0].upper()
        ]
        self.assertEqual(len(event_inserts), 1)
        self.assertEqual(result["events_created"], 1)
        self.assertEqual(result["transitions_recorded"], 1)  # first obs -> NULL transition

    def test_return_dict_includes_transitions_recorded(self):
        from scan_history import persist_breakout_lifecycle
        pg = MagicMock()
        pg.cursor.return_value.fetchone.side_effect = [
            ("2026-08-13",),
            ("event-123",),
            (None,),
        ]
        result = persist_breakout_lifecycle(
            pg, _calibration_scan_results(),
            run_id="00000000-0000-0000-0000-000000000001",
            scanner_version="signalix/daily-state-v2",
        )
        self.assertIn("transitions_recorded", result)
        self.assertIn("events_created", result)
        self.assertIn("observations_appended", result)


class BreakoutLifecycleSqlShapeTests(unittest.TestCase):
    def test_stage_transition_insert_placeholders_match_parameters(self):
        from scan_history import persist_breakout_lifecycle
        pg = MagicMock()
        cur = pg.cursor.return_value
        cur.fetchone.side_effect = [
            ("2026-08-13",),
            ("952c18c6-a816-4c9b-9ee7-a253507f0df1",),
            (None,),
        ]

        def execute(sql, params=None):
            if "daily_breakout_event_stage_transitions" in sql and "INSERT" in sql.upper():
                self.assertEqual(sql.count("%s"), len(params))

        cur.execute.side_effect = execute
        persist_breakout_lifecycle(
            pg, [_calibration_scan_results()[0]],
            run_id="00000000-0000-0000-0000-000000000001",
            scanner_version="signalix/daily-state-v2",
        )


class BreakoutEventLifecycleQueryTests(unittest.TestCase):
    def test_query_uses_three_tables(self):
        from scan_history import breakout_event_lifecycle
        pg = MagicMock()
        cur = pg.cursor.return_value
        cur.fetchone.side_effect = [
            ("PTT", "unknown", 0.64, dt.date(2026, 3, 30), 0.70, 0.57, 0.51, 45.0, "run-1", dt.datetime(2026, 3, 30, 11, 0, tzinfo=dt.timezone.utc)),
            [],  # observations
            [],  # transitions
        ]
        result = breakout_event_lifecycle(pg, "952c18c6-a816-4c9b-9ee7-a253507f0df1")
        sql_calls = [c.args[0] for c in cur.execute.call_args_list]
        # Must query all three tables
        self.assertEqual(len(sql_calls), 3)
        self.assertIn("daily_breakout_events", sql_calls[0])
        self.assertIn("daily_breakout_event_observations", sql_calls[1])
        self.assertIn("daily_breakout_event_stage_transitions", sql_calls[2])
        # Event row has original trigger / pivot / failure_level
        ev = result["event"]
        self.assertEqual(ev["trigger_price"], 0.64)
        self.assertEqual(ev["pivot_low"], 0.57)
        self.assertEqual(ev["failure_level"], 0.51)
        self.assertEqual(ev["symbol"], "PTT")

    def test_query_returns_none_for_unknown_event(self):
        from scan_history import breakout_event_lifecycle
        pg = MagicMock()
        pg.cursor.return_value.fetchone.return_value = None
        result = breakout_event_lifecycle(pg, "nonexistent")
        self.assertIsNone(result)

    def test_query_returns_chronological_observations_and_transitions(self):
        from scan_history import breakout_event_lifecycle
        pg = MagicMock()
        cur = pg.cursor.return_value
        cur.fetchone.side_effect = [
            ("BJCHI", "unknown", 0.64, dt.date(2026, 3, 30), 0.70, 0.57, 0.51, 45.0, "run-1", dt.datetime(2026, 3, 30, 11, 0, tzinfo=dt.timezone.utc)),
        ]
        cur.fetchall.side_effect = [
            # observations
            [(dt.date(2026, 8, 13), "S2_uptrend", 2.30, 0.45, 85.1, 1.82, None, "run-a")],
            # transitions
            [(None, "S2_uptrend", dt.date(2026, 8, 13), 2.30, 0.45, None, "run-a"),
             ("S2_uptrend", "S3_distributing", dt.date(2026, 8, 14), 1.80, 0.18, "broken_below_failure", "run-b")],
        ]
        result = breakout_event_lifecycle(pg, "evt-456")
        self.assertEqual(len(result["observations"]), 1)
        self.assertEqual(result["observations"][0]["stage"], "S2_uptrend")
        self.assertEqual(len(result["transitions"]), 2)
        self.assertIsNone(result["transitions"][0]["from_stage"])
        self.assertEqual(result["transitions"][0]["to_stage"], "S2_uptrend")
        self.assertEqual(result["transitions"][1]["from_stage"], "S2_uptrend")
        self.assertEqual(result["transitions"][1]["to_stage"], "S3_distributing")


if __name__ == "__main__":
    unittest.main()
