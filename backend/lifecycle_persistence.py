"""Pure record builders and parameterized PostgreSQL helpers for lifecycle history."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from copy import deepcopy
from typing import Any

from lifecycle_contract import revalidate_setup


REVIEW_EVENTS = frozenset({
    "AGREE", "WATCH", "DISAGREE_WAVE", "REJECT_SETUP", "MISSED_CANDIDATE", "NOTE",
})


class ImmutableConflict(ValueError):
    """An immutable identity was reused with different content."""


class IdempotencyConflict(ValueError):
    """An idempotency key was reused with different content."""


def build_review_event_id(idempotency_key: str) -> str:
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    return "event_" + _digest({"idempotency_key": idempotency_key.strip()})


def _json_safe(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("value must be JSON-safe")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError("value must be JSON-safe")


def _canonical(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _price(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("setup prices must be finite numbers or null")
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("setup prices must be finite numbers or null") from exc
    if not price.is_finite():
        raise ValueError("setup prices must be finite numbers or null")
    # Keep the project's established Python display/rounding semantics while
    # accepting Decimal values returned by PostgreSQL.
    return round(float(price), 2)


def canonicalize_plan(plan: dict) -> dict:
    """Detach a setup plan and canonicalize only its explicit price fields."""
    if not isinstance(plan, dict):
        raise ValueError("plan must be a dict")
    result = _json_safe(deepcopy(plan))
    for key in ("trigger", "trade_stop", "target_1"):
        if key in result:
            result[key] = _price(result[key])
    if "targets" in result:
        targets = result["targets"]
        if targets is None:
            result["targets"] = None
        elif isinstance(targets, list):
            result["targets"] = sorted((_price(target) for target in targets), key=lambda x: (x is None, x))
        else:
            raise ValueError("targets must be a list or null")
    return result


def build_setup_identity(candidate_id: str, setup_plan: dict) -> str:
    """Build identity from immutable plan levels only.

    Observation/status/freshness fields are deliberately excluded.  Prices
    are canonicalized before hashing so PostgreSQL numeric values and display
    precision cannot create a second identity.
    """
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("candidate_id is required")
    plan = canonicalize_plan(setup_plan)
    targets = plan.get("targets")
    target_1 = plan.get("target_1")
    if target_1 is not None:
        target_1 = _price(target_1)
    return "setup_" + _digest({
        "candidate_id": candidate_id,
        "trigger": _price(plan.get("trigger")) if "trigger" in plan else None,
        "trade_stop": _price(plan.get("trade_stop")) if "trade_stop" in plan else None,
        "target_1": target_1,
        "targets": targets,
    })


def build_snapshot_identity(candidate_id: str, setup_id: str, observation_as_of: Any,
                            policy_version: str, source: str) -> str:
    return "snapshot_" + _digest({
        "candidate_id": candidate_id, "observation_as_of": observation_as_of,
        "policy_version": policy_version, "setup_id": setup_id, "source": source,
    })


def build_candidate_record(symbol: str, thesis_as_of: Any, policy_version: str,
                           payload: dict, created_at: Any = None) -> dict:
    record = {
        "candidate_id": "candidate_" + _digest({
            "policy_version": policy_version, "symbol": symbol, "thesis_as_of": thesis_as_of,
        }),
        "symbol": symbol, "thesis_as_of": thesis_as_of, "policy_version": policy_version,
        "payload": payload,
    }
    if created_at is not None:
        record["created_at"] = created_at
    return _json_safe(record)


def build_snapshot_record(candidate_id: str, setup_id: str, observation_as_of: Any,
                          policy_version: str, source: str, setup_plan: dict,
                          machine_payload: dict, lifecycle_status: str,
                          expiry_reasons: list | None = None, created_at: Any = None) -> dict:
    record = {
        "snapshot_id": build_snapshot_identity(candidate_id, setup_id, observation_as_of, policy_version, source),
        "candidate_id": candidate_id, "setup_id": setup_id,
        "observation_as_of": observation_as_of, "policy_version": policy_version, "source": source,
        "setup_plan": canonicalize_plan(setup_plan), "machine_payload": machine_payload,
        "lifecycle_status": lifecycle_status, "expiry_reasons": [] if expiry_reasons is None else expiry_reasons,
    }
    if created_at is not None:
        record["created_at"] = created_at
    return _json_safe(record)


MIGRATION_SQL = open(__file__.replace("lifecycle_persistence.py", "migrations/007_lifecycle_persistence.sql"), encoding="utf-8").read()


def init_lifecycle_schema(cur) -> None:
    """Apply the standalone migration using the caller's cursor."""
    cur.execute(MIGRATION_SQL)


def _db_json(value: Any) -> str:
    return _canonical(value)


def _comparison_value(value: Any) -> Any:
    """Make text/JSON/date/Decimal driver representations compare alike."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in "[{":
            try:
                return _comparison_value(json.loads(stripped))
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        try:
            parsed = dt.datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            value = parsed
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        # PostgreSQL JSONB drivers may return a JSON number as Decimal while
        # the input record contains an int or float.  Decimal(str(...)) keeps
        # numeric comparison exact without making strings numeric.
        return Decimal(str(value))
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _comparison_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_comparison_value(v) for v in value]
    return value


def persist_completed_60m_candidate(
    cur, candidate: dict, *, previous_snapshot: dict | None = None,
    observation_as_of: Any = None, policy_version: str | None = None,
    source: str | None = None,
) -> dict:
    """Adapt one completed canonical producer result to lifecycle persistence.

    This is an explicit caller-owned transaction seam.  It intentionally does
    not run the producer, obtain a connection, or commit.  The completed-60m
    caller decides when this opt-in adapter is invoked.
    """
    if not isinstance(candidate, dict):
        raise ValueError("canonical candidate must be a dict")
    required = ("symbol", "as_of", "data_status", "wave", "setup", "provenance")
    if any(key not in candidate for key in required):
        raise ValueError("canonical candidate envelope is incomplete")
    data_status = candidate["data_status"]
    setup = candidate["setup"]
    provenance = candidate["provenance"]
    if not isinstance(data_status, dict) or not isinstance(setup, dict) or not isinstance(provenance, dict):
        raise ValueError("canonical candidate groups must be dicts")
    if (data_status.get("sufficient") is not True
            or data_status.get("intraday_60m_freshness") != "fresh"
            or setup.get("timeframe") != "60m"):
        raise ValueError("completed fresh 60m evaluation is required")
    policy = policy_version or provenance.get("policy_version")
    lineage = source or provenance.get("source")
    if not isinstance(policy, str) or not policy.strip() or not isinstance(lineage, str) or not lineage.strip():
        raise ValueError("policy_version and source are required")

    candidate_record = build_candidate_record(
        candidate["symbol"], candidate["as_of"], policy, candidate,
    )
    candidate_id = candidate_record["candidate_id"]
    plan = {
        "trigger": setup.get("trigger"),
        "trade_stop": setup.get("trade_stop", setup.get("invalidation")),
        "target_1": setup.get("target_1") or ((setup.get("targets") or [None])[0]),
        "targets": setup.get("targets") or [],
    }
    current = {**plan, "rr": {"to_target_1": (setup.get("rr") or {}).get("to_target_1")},
               "data_status": data_status}
    prior = previous_snapshot.get("machine_payload", previous_snapshot) if previous_snapshot else current
    revalidation = revalidate_setup(prior, current)
    observed = observation_as_of or data_status.get("intraday_60m_as_of") or setup.get("provenance", {}).get("as_of") or candidate["as_of"]
    setup_id = build_setup_identity(candidate_id, plan)
    snapshot = build_snapshot_record(
        candidate_id, setup_id, observed, policy, lineage, plan, candidate,
        revalidation["status"], revalidation["reasons"],
    )
    persist_evaluation(cur, candidate_record, snapshot)
    return {"candidate": candidate_record, "snapshot": snapshot, "revalidation": revalidation}


def _same(row: dict | None, record: dict, ignored: set[str] = frozenset()) -> bool:
    if row is None:
        return False
    return all(_comparison_value(row.get(key)) == _comparison_value(value)
               for key, value in record.items() if key not in ignored)


def persist_evaluation(cur, candidate_record: dict, snapshot_record: dict) -> None:
    cur.execute("""INSERT INTO lifecycle_candidates
        (candidate_id, symbol, thesis_as_of, policy_version, payload, created_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, COALESCE(%s, NOW()))
        ON CONFLICT (candidate_id) DO NOTHING""", (
        candidate_record["candidate_id"], candidate_record["symbol"], candidate_record["thesis_as_of"],
        candidate_record["policy_version"], _db_json(candidate_record["payload"]), candidate_record.get("created_at"),
    ))
    cur.execute("SELECT candidate_id, symbol, thesis_as_of, policy_version, payload, created_at FROM lifecycle_candidates WHERE candidate_id = %s",
                (candidate_record["candidate_id"],))
    row = cur.fetchone()
    if row and not isinstance(row, dict):
        row = dict(zip(("candidate_id", "symbol", "thesis_as_of", "policy_version", "payload", "created_at"), row))
    if not _same(row, candidate_record, {"created_at"}):
        raise ImmutableConflict("candidate_id cannot be rewritten")

    cur.execute("""INSERT INTO lifecycle_snapshots
        (snapshot_id, candidate_id, setup_id, observation_as_of,
         policy_version, source, setup_plan, machine_payload, lifecycle_status, expiry_reasons, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, COALESCE(%s, NOW()))
        ON CONFLICT (snapshot_id) DO NOTHING""", (
        snapshot_record["snapshot_id"], snapshot_record["candidate_id"], snapshot_record["setup_id"],
        snapshot_record["observation_as_of"],
        snapshot_record["policy_version"], snapshot_record["source"],
        _db_json(snapshot_record["setup_plan"]), _db_json(snapshot_record["machine_payload"]),
        snapshot_record["lifecycle_status"], _db_json(snapshot_record["expiry_reasons"]), snapshot_record.get("created_at"),
    ))
    cur.execute("SELECT snapshot_id, candidate_id, setup_id, observation_as_of, policy_version, source, setup_plan, machine_payload, lifecycle_status, expiry_reasons, created_at FROM lifecycle_snapshots WHERE snapshot_id = %s",
                (snapshot_record["snapshot_id"],))
    row = cur.fetchone()
    if row and not isinstance(row, dict):
        row = dict(zip(("snapshot_id", "candidate_id", "setup_id", "observation_as_of", "policy_version", "source", "setup_plan", "machine_payload", "lifecycle_status", "expiry_reasons", "created_at"), row))
    if not _same(row, snapshot_record, {"created_at"}):
        raise ImmutableConflict("snapshot_id cannot be rewritten")


def persist_review(cur, review_record: dict) -> dict | None:
    if not isinstance(review_record.get("reviewer"), str) or not review_record["reviewer"].strip():
        raise ValueError("trusted reviewer is required explicitly")
    if review_record.get("event") not in REVIEW_EVENTS:
        raise ValueError("invalid review event")
    if not isinstance(review_record.get("idempotency_key"), str) or not review_record["idempotency_key"].strip():
        raise ValueError("idempotency_key is required")
    cur.execute("""INSERT INTO lifecycle_review_events
        (event_id, candidate_id, setup_id, snapshot_id, event, reviewer, note, idempotency_key, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()))
        ON CONFLICT (idempotency_key) DO NOTHING""", tuple(
        review_record.get(key) for key in ("event_id", "candidate_id", "setup_id", "snapshot_id", "event", "reviewer", "note", "idempotency_key", "created_at")
    ))
    cur.execute("SELECT event_id, candidate_id, setup_id, snapshot_id, event, reviewer, note, idempotency_key, created_at FROM lifecycle_review_events WHERE idempotency_key = %s",
                (review_record["idempotency_key"],))
    row = cur.fetchone()
    columns = ("event_id", "candidate_id", "setup_id", "snapshot_id", "event", "reviewer", "note", "idempotency_key", "created_at")
    if row and not isinstance(row, dict):
        row = dict(zip(columns, row))
    if not row:
        return None
    if not _same(row, review_record, {"created_at"}):
        raise IdempotencyConflict("idempotency key was reused with a different review")
    return row


def read_candidate(cur, candidate_id: str):
    cur.execute("SELECT candidate_id, symbol, thesis_as_of, policy_version, payload, created_at FROM lifecycle_candidates WHERE candidate_id = %s", (candidate_id,))
    return cur.fetchone()


def read_snapshot(cur, snapshot_id: str):
    cur.execute("SELECT snapshot_id, candidate_id, setup_id, observation_as_of, policy_version, source, setup_plan, machine_payload, lifecycle_status, expiry_reasons, created_at FROM lifecycle_snapshots WHERE snapshot_id = %s", (snapshot_id,))
    return cur.fetchone()


def read_reviews(cur, candidate_id=None, setup_id=None, snapshot_id=None):
    clauses, params = [], []
    for key, value in (("candidate_id", candidate_id), ("setup_id", setup_id), ("snapshot_id", snapshot_id)):
        if value is not None:
            clauses.append(f"{key} = %s")
            params.append(value)
    sql = "SELECT event_id, candidate_id, setup_id, snapshot_id, event, reviewer, note, idempotency_key, created_at FROM lifecycle_review_events"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at ASC, event_id ASC"
    cur.execute(sql, tuple(params))
    return cur.fetchall()
