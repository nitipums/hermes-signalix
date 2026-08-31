"""Real PostgreSQL integration coverage for lifecycle persistence (T9A)."""

import datetime as dt
import json
import os
from decimal import Decimal

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor, register_json

from lifecycle_persistence import (
    IdempotencyConflict,
    ImmutableConflict,
    REVIEW_EVENTS,
    build_candidate_record,
    build_review_event_id,
    build_setup_identity,
    build_snapshot_record,
    init_lifecycle_schema,
    persist_completed_60m_candidate,
    persist_evaluation,
    persist_review,
)


PG = {
    "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "user": os.getenv("POSTGRES_USER", "signalix"),
    "password": os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
}


def _connect(database):
    return psycopg2.connect(**PG, dbname=database, connect_timeout=2)


def _postgres_reachable():
    try:
        conn = _connect("signalix")
        conn.close()
        return True
    except psycopg2.Error:
        return False


POSTGRES_AVAILABLE = _postgres_reachable()
pytestmark = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL is unreachable")


@pytest.fixture(scope="module")
def test_database():
    name = f"signalix_t9_test_{os.getpid()}"
    admin = None
    conn = None
    try:
        admin = _connect("signalix")
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            cur.execute(f'CREATE DATABASE "{name}"')
        conn = _connect(name)
        conn.autocommit = False
        with conn.cursor() as cur:
            init_lifecycle_schema(cur)
            init_lifecycle_schema(cur)
        conn.commit()
        yield name
    finally:
        if conn is not None:
            conn.close()
        if admin is not None:
            admin.close()
            admin = None
        if admin is None:
            try:
                admin = _connect("signalix")
                admin.autocommit = True
            except psycopg2.Error:
                admin = None
        if admin is not None:
            # The test database is still reachable after the test connection is closed;
            # verify the expected schema exists before dropping this ephemeral database.
            check = None
            try:
                check = _connect(name)
                with check.cursor() as cur:
                    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'lifecycle_%'")
                    assert {row[0] for row in cur.fetchall()} == {
                        "lifecycle_candidates", "lifecycle_snapshots", "lifecycle_review_events",
                    }
            finally:
                if check is not None:
                    check.close()
            with admin.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            admin.close()


@pytest.fixture
def db(test_database):
    conn = _connect(test_database)
    register_json(conn, loads=lambda value: json.loads(value, parse_float=Decimal))
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _records(symbol="ABC"):
    candidate = build_candidate_record(symbol, "2026-08-31T00:00:00Z", "p1", {"symbol": symbol, "ok": True})
    plan = {"trigger": 12.5, "trade_stop": 10, "target_1": 17.5, "targets": [17.5]}
    snapshot = build_snapshot_record(
        candidate["candidate_id"], build_setup_identity(candidate["candidate_id"], plan),
        "2026-08-31T10:00:00+07:00", "p1", "test", plan, {"ok": True}, "ACTIVE", [],
    )
    return candidate, snapshot


def _row(cur, table, key, value):
    cur.execute(f"SELECT * FROM {table} WHERE {key} = %s", (value,))
    return cur.fetchone()


def test_migration_is_idempotent_and_creates_contract(db):
    with db.cursor() as cur:
        init_lifecycle_schema(cur)
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'lifecycle_%'")
        assert {r[0] for r in cur.fetchall()} == {"lifecycle_candidates", "lifecycle_snapshots", "lifecycle_review_events"}
        cur.execute("SELECT constraint_name FROM information_schema.table_constraints WHERE table_schema='public' AND table_name LIKE 'lifecycle_%'")
        constraints = {r[0] for r in cur.fetchall()}
        assert "lifecycle_candidates_pkey" in constraints
        assert "lifecycle_snapshots_pkey" in constraints
        assert "lifecycle_review_events_idempotency_key_key" in constraints
        cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname LIKE 'lifecycle_%'")
        indexes = {r[0] for r in cur.fetchall()}
        assert "lifecycle_snapshots_candidate_idx" in indexes
        assert "lifecycle_review_events_snapshot_idx" in indexes
        cur.execute("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE 'lifecycle_%'")
        assert {r[0] for r in cur.fetchall()} == {
            "lifecycle_candidates_append_only", "lifecycle_snapshots_append_only", "lifecycle_review_events_append_only",
        }


def test_persist_evaluation_happy_path_and_repeat_is_idempotent(db):
    candidate, snapshot = _records()
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        persist_evaluation(cur, candidate, snapshot)
        persist_evaluation(cur, candidate, snapshot)
        cur.execute("SELECT count(*) AS n FROM lifecycle_candidates")
        assert cur.fetchone()["n"] == 1
        cur.execute("SELECT count(*) AS n FROM lifecycle_snapshots")
        assert cur.fetchone()["n"] == 1
        assert _row(cur, "lifecycle_candidates", "candidate_id", candidate["candidate_id"])["symbol"] == "ABC"
        assert _row(cur, "lifecycle_snapshots", "snapshot_id", snapshot["snapshot_id"])["source"] == "test"


def test_immutable_conflicts_are_detected(db):
    candidate, snapshot = _records()
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        persist_evaluation(cur, candidate, snapshot)
        changed_candidate = dict(candidate, symbol="OTHER")
        with pytest.raises(ImmutableConflict):
            persist_evaluation(cur, changed_candidate, snapshot)
        changed_snapshot = dict(snapshot, machine_payload={"changed": True})
        with pytest.raises(ImmutableConflict):
            persist_evaluation(cur, candidate, changed_snapshot)


def test_all_review_events_and_idempotency_conflicts(db):
    candidate, snapshot = _records()
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        persist_evaluation(cur, candidate, snapshot)
        for index, event in enumerate(sorted(REVIEW_EVENTS)):
            record = {"event_id": build_review_event_id(f"key-{index}"), "candidate_id": candidate["candidate_id"],
                      "setup_id": snapshot["setup_id"], "snapshot_id": snapshot["snapshot_id"], "event": event,
                      "reviewer": "arm", "note": "note", "idempotency_key": f"key-{index}"}
            assert persist_review(cur, record)["event"] == event
            assert persist_review(cur, record)["event_id"] == record["event_id"]
        duplicate = dict(record, note="different")
        with pytest.raises(IdempotencyConflict):
            persist_review(cur, duplicate)
        with pytest.raises(ValueError):
            persist_review(cur, dict(record, event="NOT_AN_EVENT", idempotency_key="invalid-python"))
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("INSERT INTO lifecycle_review_events (event_id,candidate_id,setup_id,snapshot_id,event,reviewer,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        ("bad", candidate["candidate_id"], snapshot["setup_id"], snapshot["snapshot_id"], "BAD", "arm", "invalid-db"))


def test_foreign_keys_reject_missing_snapshot_and_candidate(db):
    candidate, snapshot = _records()
    with db.cursor() as cur:
        cur.execute("SAVEPOINT missing_snapshot")
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("INSERT INTO lifecycle_review_events (event_id,candidate_id,setup_id,snapshot_id,event,reviewer,idempotency_key) VALUES ('e','missing','s','missing','NOTE','arm','fk1')")
        cur.execute("ROLLBACK TO SAVEPOINT missing_snapshot")
        cur.execute("SAVEPOINT missing_candidate")
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("INSERT INTO lifecycle_snapshots (snapshot_id,candidate_id,setup_id,observation_as_of,policy_version,source,setup_plan,machine_payload,lifecycle_status) VALUES ('s','missing','setup',NOW(),'p','x','{}','{}','ACTIVE')")
        cur.execute("ROLLBACK TO SAVEPOINT missing_candidate")


def test_append_only_triggers_allow_continuation_after_savepoint_rollback(db):
    candidate, snapshot = _records()
    with db.cursor() as cur:
        persist_evaluation(cur, candidate, snapshot)
        review = ("event", candidate["candidate_id"], snapshot["setup_id"], snapshot["snapshot_id"], "NOTE", "arm", "n", "append-key")
        cur.execute("INSERT INTO lifecycle_review_events (event_id,candidate_id,setup_id,snapshot_id,event,reviewer,note,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", review)
        for table, key, value in (("lifecycle_candidates", "candidate_id", candidate["candidate_id"]),
                                  ("lifecycle_snapshots", "snapshot_id", snapshot["snapshot_id"]),
                                  ("lifecycle_review_events", "event_id", "event")):
            cur.execute("SAVEPOINT failed_mutation")
            with pytest.raises(psycopg2.errors.RaiseException, match="append-only"):
                cur.execute(f"UPDATE {table} SET {key} = {key} WHERE {key} = %s", (value,))
            cur.execute("ROLLBACK TO SAVEPOINT failed_mutation")
            cur.execute("SAVEPOINT failed_delete")
            with pytest.raises(psycopg2.errors.RaiseException, match="append-only"):
                cur.execute(f"DELETE FROM {table} WHERE {key} = %s", (value,))
            cur.execute("ROLLBACK TO SAVEPOINT failed_delete")
        cur.execute("SELECT count(*) FROM lifecycle_review_events")
        assert cur.fetchone()[0] == 1


def test_delete_candidate_with_snapshot_is_restricted(db):
    candidate, snapshot = _records()
    with db.cursor() as cur:
        persist_evaluation(cur, candidate, snapshot)
        with pytest.raises(psycopg2.errors.RaiseException, match="append-only"):
            cur.execute("DELETE FROM lifecycle_candidates WHERE candidate_id=%s", (candidate["candidate_id"],))


def test_postgres_datetime_decimal_json_readback_is_idempotent(db):
    candidate, snapshot = _records()
    with db.cursor() as cur:
        cur.execute("INSERT INTO lifecycle_candidates (candidate_id,symbol,thesis_as_of,policy_version,payload) VALUES (%s,%s,%s,%s,%s::jsonb)",
                    (candidate["candidate_id"], candidate["symbol"], candidate["thesis_as_of"], candidate["policy_version"], '{"symbol":"ABC","ok":true}'))
        cur.execute("INSERT INTO lifecycle_snapshots (snapshot_id,candidate_id,setup_id,observation_as_of,policy_version,source,setup_plan,machine_payload,lifecycle_status,expiry_reasons) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb)",
                    (snapshot["snapshot_id"], candidate["candidate_id"], snapshot["setup_id"], snapshot["observation_as_of"], "p1", "test", '{"target_1":17.50,"targets":[17.50],"trade_stop":10,"trigger":12.50}', '{"ok":true}', "ACTIVE", '[]'))
        cur.execute("SELECT thesis_as_of, setup_plan FROM lifecycle_snapshots JOIN lifecycle_candidates USING (candidate_id) WHERE snapshot_id=%s", (snapshot["snapshot_id"],))
        readback = cur.fetchone()
        assert isinstance(readback[0], dt.datetime)
        # The db fixture registers a Decimal-parsing JSON loader; the production
        # connection uses the default float loader.  Both shapes must compare
        # equal after persist_evaluation's normalization, so assert the numeric
        # value rather than a specific loader type.
        assert float(readback[1]["trigger"]) == 12.5
        persist_evaluation(cur, candidate, snapshot)


def test_completed_fresh_60m_candidate_persists_and_repeats(db):
    candidate = {"symbol": "XYZ", "as_of": "2026-08-31T00:00:00Z", "data_status": {"sufficient": True, "intraday_60m_freshness": "fresh", "intraday_60m_as_of": "2026-08-31T10:00:00+07:00"}, "wave": {"primary_state": "EARLY_WAVE_3"}, "setup": {"timeframe": "60m", "trigger": 12.5, "invalidation": 10, "targets": [17.5], "rr": {"to_target_1": 2}}, "provenance": {"policy_version": "p1", "source": "test"}}
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        first = persist_completed_60m_candidate(cur, candidate)
        second = persist_completed_60m_candidate(cur, candidate)
        assert first["snapshot"]["snapshot_id"] == second["snapshot"]["snapshot_id"]
        cur.execute("SELECT count(*) AS n FROM lifecycle_candidates")
        assert cur.fetchone()["n"] == 1
        cur.execute("SELECT count(*) AS n FROM lifecycle_snapshots")
        assert cur.fetchone()["n"] == 1
