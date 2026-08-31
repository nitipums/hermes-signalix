"""Focused unit coverage for the T9A persistence seam (no database required)."""

import datetime as dt
import json
import unittest

from lifecycle_persistence import (
    IdempotencyConflict, ImmutableConflict, REVIEW_EVENTS, build_candidate_record,
    build_snapshot_identity, build_snapshot_record, canonicalize_plan,
    build_setup_identity, build_review_event_id, init_lifecycle_schema, persist_evaluation, persist_review,
    persist_completed_60m_candidate, revalidate_setup,
)


class Cursor:
    def __init__(self):
        self.calls = []
        self.rows = []
        self.commits = 0

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class LifecyclePersistenceTests(unittest.TestCase):
    def test_plan_rounding_and_target_order_are_deterministic(self):
        self.assertEqual(canonicalize_plan({"trigger": 10.126, "trade_stop": 9.994, "targets": [15.555, 12.124]}),
                         {"trigger": 10.13, "trade_stop": 9.99, "targets": [12.12, 15.55]})

    def test_ids_are_stable_and_snapshot_identity_includes_lineage(self):
        args = ("candidate_x", "setup_x", dt.datetime(2026, 8, 31, tzinfo=dt.timezone.utc), "p1", "daily")
        self.assertEqual(build_snapshot_identity(*args), build_snapshot_identity(*args))
        self.assertNotEqual(build_snapshot_identity(*args), build_snapshot_identity(*args[:-1], "60m"))

    def test_setup_identity_ignores_noise_and_canonicalizes_prices(self):
        first = {"trigger": 10.124, "trade_stop": 9.876, "target_1": 14.994,
                 "targets": [20.004, 15.555], "current_price": 11, "status": "FORMING"}
        equivalent = {"trigger": 10.125, "trade_stop": 9.875, "target_1": 14.995,
                      "targets": [15.554, 20.005], "current_price": 12, "status": "TRIGGERED"}
        self.assertEqual(build_setup_identity("candidate_x", first),
                         build_setup_identity("candidate_x", equivalent))
        for key in ("trigger", "trade_stop", "target_1", "targets"):
            changed = dict(first)
            changed[key] = ([15.55, 20.01] if key == "targets" else first[key] + 0.01)
            self.assertNotEqual(build_setup_identity("candidate_x", first),
                                build_setup_identity("candidate_x", changed))

    def test_revalidation_has_each_explicit_reason_and_active(self):
        base = {"trigger": 10, "trade_stop": 9, "targets": [14],
                "thesis_valid": True, "data_current": True,
                "rr": {"to_target_1": 2}}
        self.assertEqual(revalidate_setup(base, dict(base)), {"status": "ACTIVE", "reasons": []})
        for current, reason in (
            ({**base, "trigger": 11}, "STRUCTURE_CHANGED"),
            ({**base, "thesis_valid": False}, "THESIS_INVALIDATED"),
            ({**base, "data_current": False}, "DATA_NOT_CURRENT"),
            ({**base, "rr": {"to_target_1": 1.99}}, "RR_BELOW_MINIMUM"),
        ):
            result = revalidate_setup(base, current)
            self.assertEqual(result["status"], "EXPIRED")
            self.assertEqual(result["reasons"], [reason])

    def test_revalidation_canonicalizes_levels_and_normalizes_envelopes(self):
        previous = {
            "symbol": "ABC", "as_of": "2026-08-31",
            "data_status": {"sufficient": True, "freshness": "fresh"},
            "setup": {"timeframe": "60m", "trigger": 10.124,
                      "invalidation": 9.876, "targets": [15.555, 12.124]},
        }
        current = {"trigger": 10.125, "trade_stop": 9.875,
                   "target_1": 12.124, "targets": [15.554, 12.125],
                   "data_current": True, "rr": {"to_target_1": 2}}
        self.assertEqual(revalidate_setup(previous, current),
                         {"status": "ACTIVE", "reasons": []})
        for key, value in (("trigger", 10.13), ("trade_stop", 9.99),
                           ("targets", [12.12, 15.56])):
            changed = dict(current)
            changed[key] = value
            result = revalidate_setup(previous, changed)
            self.assertEqual(result["status"], "EXPIRED")
            self.assertEqual(result["reasons"], ["STRUCTURE_CHANGED"])

    def test_revalidation_missing_or_invalid_rr_is_below_minimum(self):
        base = {"trigger": 10, "trade_stop": 9, "targets": [14],
                "thesis_valid": True, "data_current": True}
        for rr in (None, {"to_target_1": "bad"}, {"to_target_1": float("nan")}):
            current = dict(base)
            if rr is not None:
                current["rr"] = rr
            result = revalidate_setup(base, current)
            self.assertEqual(result, {"status": "EXPIRED",
                                      "reasons": ["RR_BELOW_MINIMUM"]})

    def test_revalidation_envelope_prior_normalizes_trade_stop_and_invalidation(self):
        flat_current = {"trigger": 10.125, "trade_stop": 9.875,
                        "target_1": 12.124, "targets": [15.554, 12.125],
                        "data_current": True, "rr": {"to_target_1": 2}}
        for prior_setup in (
                {"trigger": 10.124, "trade_stop": 9.876,
                 "target_1": 12.124, "targets": [15.555, 12.124]},
                {"trigger": 10.124, "invalidation": 9.876,
                 "target_1": 12.124, "targets": [15.555, 12.124]},
                {"trigger": 10.124, "stop": 9.876,
                 "target_1": 12.124, "targets": [15.555, 12.124]}):
            previous = {"setup": prior_setup, "rr": {"to_target_1": 2}}
            self.assertEqual(revalidate_setup(previous, flat_current),
                             {"status": "ACTIVE", "reasons": []})

    def test_records_are_json_safe(self):
        candidate = build_candidate_record("ABC", dt.date(2026, 8, 31), "p1", {"ok": True})
        snapshot = build_snapshot_record(candidate["candidate_id"], "setup", dt.datetime(2026, 8, 31, tzinfo=dt.timezone.utc), "p1", "daily", {"trigger": 1.234}, {}, "ACTIVE")
        json.dumps(candidate)
        json.dumps(snapshot)
        self.assertEqual(snapshot["setup_plan"]["trigger"], 1.23)

    def test_migration_is_single_idempotent_sql_unit_with_guards(self):
        cur = Cursor()
        init_lifecycle_schema(cur)
        sql = cur.calls[0][0]
        for table in ("lifecycle_candidates", "lifecycle_snapshots", "lifecycle_review_events"):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)
        self.assertIn("CREATE OR REPLACE FUNCTION lifecycle_persistence_reject_mutation", sql)
        self.assertIn("BEFORE UPDATE OR DELETE", sql)
        self.assertIn("ON DELETE RESTRICT", sql)

    def test_insert_sql_is_append_only_and_never_commits(self):
        cur = Cursor()
        candidate = build_candidate_record("ABC", "2026-08-31T00:00:00Z", "p1", {})
        snapshot = build_snapshot_record(candidate["candidate_id"], "setup", "2026-08-31T01:00:00Z", "p1", "daily", {}, {}, "ACTIVE")
        cur.rows = [dict(candidate), dict(snapshot)]
        persist_evaluation(cur, candidate, snapshot)
        self.assertFalse(any("UPDATE" in sql.upper() or "DELETE" in sql.upper() for sql, _ in cur.calls if "INSERT" in sql.upper()))
        self.assertEqual(cur.commits, 0)

    def test_immutable_conflict(self):
        cur = Cursor()
        candidate = build_candidate_record("ABC", "2026-08-31", "p1", {})
        snapshot = build_snapshot_record(candidate["candidate_id"], "setup", "2026-08-31T01:00:00Z", "p1", "daily", {}, {}, "ACTIVE")
        cur.rows = [{**candidate, "symbol": "OTHER"}]
        with self.assertRaises(ImmutableConflict):
            persist_evaluation(cur, candidate, snapshot)

    def test_idempotency_conflict_and_no_commit(self):
        cur = Cursor()
        record = {"event_id": "e1", "candidate_id": "c", "setup_id": "s", "snapshot_id": "x", "event": "NOTE", "reviewer": "arm", "note": "one", "idempotency_key": "k"}
        cur.rows = [dict(record)]
        self.assertEqual(persist_review(cur, record)["event_id"], "e1")
        cur.rows = [{**record, "note": "two"}]
        with self.assertRaises(IdempotencyConflict):
            persist_review(cur, record)
        self.assertEqual(cur.commits, 0)

    def test_review_event_id_is_stable_for_same_idempotency_key(self):
        self.assertEqual(build_review_event_id(" retry "), build_review_event_id("retry"))
        self.assertNotEqual(build_review_event_id("retry"), build_review_event_id("other"))

    def test_all_review_events_and_missing_reviewer_are_validated(self):
        for index, event in enumerate(sorted(REVIEW_EVENTS)):
            cur = Cursor()
            record = {"event_id": f"e{index}", "candidate_id": "c", "setup_id": "s",
                      "snapshot_id": "x", "event": event, "reviewer": "arm",
                      "note": None, "idempotency_key": f"k{index}"}
            cur.rows = [dict(record)]
            self.assertEqual(persist_review(cur, record)["event"], event)
        cur = Cursor()
        with self.assertRaises(ValueError):
            persist_review(cur, {"event": "NOTE", "idempotency_key": "k"})

    def test_postgres_datetime_and_json_readback_is_idempotent(self):
        cur = Cursor()
        candidate = build_candidate_record("ABC", "2026-08-31T00:00:00Z", "p1", {"ok": True})
        snapshot = build_snapshot_record(candidate["candidate_id"], "setup", "2026-08-31T01:00:00Z", "p1", "daily", {"trigger": 1.234}, {"ok": True}, "ACTIVE")
        cur.rows = [
            {**candidate, "thesis_as_of": dt.datetime(2026, 8, 31, tzinfo=dt.timezone.utc), "payload": {"ok": True}},
            {**snapshot, "observation_as_of": dt.datetime(2026, 8, 31, 1, tzinfo=dt.timezone.utc), "setup_plan": {"trigger": 1.23}, "machine_payload": {"ok": True}},
        ]
        persist_evaluation(cur, candidate, snapshot)

    def test_completed_60m_adapter_persists_canonical_candidate_atomically(self):
        from mvp_api import persist_setup_candidate_lifecycle
        candidate = {
            "symbol": "ABC", "as_of": "2026-08-31T00:00:00Z",
            "data_status": {"sufficient": True, "freshness": "fresh",
                            "intraday_60m_freshness": "fresh",
                            "intraday_60m_as_of": "2026-08-31T10:00:00+07:00"},
            "trend": {"state": "uptrend"}, "wave": {"primary_state": "EARLY_WAVE_3"},
            "setup": {"timeframe": "60m", "trigger": 12.5, "invalidation": 10,
                      "targets": [17.5], "rr": {"to_target_1": 2.0}},
            "provenance": {"policy_version": "setup-candidates-v1", "source": "test"},
        }
        cur = Cursor()
        candidate_record = build_candidate_record("ABC", candidate["as_of"], "setup-candidates-v1", candidate)
        setup_id = build_setup_identity(candidate_record["candidate_id"], {
            "trigger": 12.5, "trade_stop": 10, "target_1": 17.5, "targets": [17.5]})
        snapshot = build_snapshot_record(candidate_record["candidate_id"], setup_id,
                                         candidate["data_status"]["intraday_60m_as_of"],
                                         "setup-candidates-v1", "test",
                                         {"trigger": 12.5, "trade_stop": 10,
                                          "target_1": 17.5, "targets": [17.5]}, candidate,
                                         "ACTIVE", [])
        cur.rows = [dict(candidate_record), dict(snapshot)]
        result = persist_setup_candidate_lifecycle(cur, candidate, observation_as_of="2026-08-31T10:00:00+07:00")
        self.assertEqual(result["snapshot"]["setup_id"], setup_id)
        self.assertEqual(result["revalidation"], {"status": "ACTIVE", "reasons": []})
        self.assertEqual(cur.commits, 0)

    def test_completed_60m_adapter_is_explicitly_blocked_without_fresh_context(self):
        candidate = {"symbol": "ABC", "as_of": "2026-08-31", "data_status": {},
                     "wave": {}, "setup": {"timeframe": "60m"}, "provenance": {}}
        with self.assertRaisesRegex(ValueError, "completed fresh 60m"):
            persist_completed_60m_candidate(Cursor(), candidate)

    def test_completed_60m_adapter_fails_closed_for_stale_or_wrong_timeframe(self):
        base = {"symbol": "ABC", "as_of": "2026-08-31", "wave": {},
                "setup": {"timeframe": "60m"}, "provenance": {"policy_version": "p1", "source": "s"},
                "data_status": {"sufficient": True, "intraday_60m_freshness": "fresh"}}
        for candidate in (
            {**base, "data_status": {"sufficient": True, "intraday_60m_freshness": "stale"}},
            {**base, "setup": {"timeframe": "1h"}},
        ):
            with self.assertRaisesRegex(ValueError, "completed fresh 60m"):
                persist_completed_60m_candidate(Cursor(), candidate)

    def test_completed_60m_adapter_repeat_is_idempotent_at_db_boundary(self):
        from mvp_api import persist_setup_candidate_lifecycle
        candidate = {
            "symbol": "ABC", "as_of": "2026-08-31T00:00:00Z",
            "data_status": {"sufficient": True, "intraday_60m_freshness": "fresh",
                            "intraday_60m_as_of": "2026-08-31T10:00:00+07:00"},
            "wave": {"primary_state": "EARLY_WAVE_3"},
            "setup": {"timeframe": "60m", "trigger": 12.5, "invalidation": 10,
                      "targets": [17.5], "rr": {"to_target_1": 2}},
            "provenance": {"policy_version": "p1", "source": "test"},
        }
        candidate_record = build_candidate_record("ABC", candidate["as_of"], "p1", candidate)
        snapshot = build_snapshot_record(candidate_record["candidate_id"],
                                         build_setup_identity(candidate_record["candidate_id"],
                                                              {"trigger": 12.5, "trade_stop": 10,
                                                               "target_1": 17.5, "targets": [17.5]}),
                                         candidate["data_status"]["intraday_60m_as_of"], "p1", "test",
                                         {"trigger": 12.5, "trade_stop": 10, "target_1": 17.5,
                                          "targets": [17.5]}, candidate, "ACTIVE", [])
        cur = Cursor()
        cur.rows = [dict(candidate_record), dict(snapshot)]
        first = persist_setup_candidate_lifecycle(cur, candidate)
        cur.rows = [dict(candidate_record), dict(snapshot)]
        second = persist_setup_candidate_lifecycle(cur, candidate)
        self.assertEqual(first["snapshot"]["snapshot_id"], second["snapshot"]["snapshot_id"])
        self.assertEqual(sum("ON CONFLICT (snapshot_id) DO NOTHING" in sql for sql, _ in cur.calls), 2)


if __name__ == "__main__":
    unittest.main()
