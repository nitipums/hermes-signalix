"""Pure append-only lifecycle and owner-review contract.

The functions in this module deliberately operate on ordinary JSON values only.
They do not persist records, obtain timestamps, or mutate caller-owned objects.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from typing import Any


REVIEW_EVENTS = (
    "AGREE",
    "WATCH",
    "DISAGREE_WAVE",
    "REJECT_SETUP",
    "MISSED_CANDIDATE",
    "NOTE",
)
_REVIEW_EVENT_SET = frozenset(REVIEW_EVENTS)
_REVALIDATION_REASONS = (
    "STRUCTURE_CHANGED",
    "THESIS_INVALIDATED",
    "DATA_NOT_CURRENT",
    "RR_BELOW_MINIMUM",
)


def _json_copy(value: Any) -> Any:
    """Validate and detach a JSON value, rejecting non-JSON values."""
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        return json.loads(encoded)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("value must be JSON-safe") from exc


def _canonical(value: Any) -> str:
    value = _json_copy(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


def _digest(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def make_candidate_id(symbol: str, thesis_as_of: Any, policy_version: str) -> str:
    """Return the stable identity of one Daily trend/Elliott thesis."""
    return _digest("candidate_", {
        "policy_version": policy_version,
        "symbol": symbol,
        "thesis_as_of": thesis_as_of,
    })


def make_setup_id(candidate_id: str, setup_snapshot: dict) -> str:
    """Return the stable identity of an immutable entry attempt."""
    if not isinstance(setup_snapshot, dict):
        raise ValueError("setup_snapshot must be a dict")
    immutable = {
        key: setup_snapshot.get(key)
        for key in ("levels", "trigger", "stop", "targets", "as_of")
    }
    return _digest("setup_", {"candidate_id": candidate_id, "snapshot": immutable})


def _record_id(record: dict, name: str) -> str:
    value = record.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} is required")
    return value


def append_snapshot(history: list[dict], snapshot: dict) -> list[dict]:
    """Append a detached machine snapshot without permitting rewrites."""
    if not isinstance(history, list) or not isinstance(snapshot, dict):
        raise ValueError("history and snapshot must be JSON records")
    copied_history = _json_copy(history)
    copied_snapshot = _json_copy(snapshot)
    candidate_id = _record_id(copied_snapshot, "candidate_id")
    setup_id = _record_id(copied_snapshot, "setup_id")
    snapshot_id = _record_id(copied_snapshot, "snapshot_id")
    for prior in copied_history:
        if not isinstance(prior, dict):
            raise ValueError("history records must be dicts")
        if prior.get("snapshot_id") == snapshot_id:
            if prior != copied_snapshot:
                raise ValueError("existing snapshot_id cannot be rewritten")
            return copied_history
    # Accesses above are intentional validation: these identities are required
    # even though the record itself remains otherwise opaque to this layer.
    _ = candidate_id, setup_id
    return copied_history + [copied_snapshot]


def append_review_event(
    events: list[dict],
    candidate_id: str,
    setup_id: str,
    snapshot_id: str,
    event: str,
    note: str | None = None,
    created_at: Any = None,
    snapshot_as_of: Any = None,
) -> list[dict]:
    """Append an owner review attached to an exact machine snapshot identity."""
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    if event not in _REVIEW_EVENT_SET:
        raise ValueError(f"invalid review event: {event!r}")
    for name, value in (("candidate_id", candidate_id), ("setup_id", setup_id),
                        ("snapshot_id", snapshot_id)):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} is required")
    copied_events = _json_copy(events)
    if created_at is None:
        # ``snapshot_as_of`` is the machine observation's deterministic time.
        # The identity fallback keeps the function deterministic when callers
        # only have the required reference fields available.
        created_at = snapshot_as_of if snapshot_as_of is not None else snapshot_id
    event_record = _json_copy({
        "event_id": _digest("review_", {
            "candidate_id": candidate_id,
            "created_at": created_at,
            "event": event,
            "note": note,
            "setup_id": setup_id,
            "snapshot_id": snapshot_id,
        }),
        "candidate_id": candidate_id,
        "setup_id": setup_id,
        "snapshot_id": snapshot_id,
        "event": event,
        "note": note,
        "created_at": created_at,
    })
    for prior in copied_events:
        if not isinstance(prior, dict):
            raise ValueError("event records must be dicts")
        if prior.get("event_id") == event_record["event_id"]:
            if prior != event_record:
                raise ValueError("existing event_id cannot be rewritten")
            return copied_events
    return copied_events + [event_record]


def _value(record: dict, key: str) -> Any:
    """Read an explicit field from a flattened or canonical candidate record."""
    if key in record:
        return record[key]
    setup = record.get("setup")
    if isinstance(setup, dict) and key in setup:
        return setup[key]
    setup_plan = record.get("setup_plan")
    if isinstance(setup_plan, dict) and key in setup_plan:
        return setup_plan[key]
    return None


def _canonical_price(value: Any) -> float | None:
    """Return the persistence contract's two-decimal price representation."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not price.is_finite():
        return None
    return round(float(price), 2)


def _comparison_plan(record: dict) -> dict:
    """Normalize full envelopes, snapshot plans, and flattened plans alike."""
    targets = _value(record, "targets")
    if targets is None:
        target_1 = _value(record, "target_1")
        targets = [] if target_1 is None else [target_1]
    elif not isinstance(targets, (list, tuple)):
        targets = [targets]
    normalized_targets = sorted(
        (_canonical_price(target) for target in targets),
        key=lambda value: (value is None, value),
    )
    target_1 = _value(record, "target_1")
    if target_1 is None and normalized_targets:
        target_1 = normalized_targets[0]
    return {
        "trigger": _canonical_price(_value(record, "trigger")),
        "stop": _canonical_price(_stop(record)),
        "target_1": _canonical_price(target_1),
        "targets": normalized_targets,
    }


def _rr(record: dict) -> Any:
    rr = record.get("rr")
    if rr is None and isinstance(record.get("setup"), dict):
        rr = record["setup"].get("rr")
    if rr is None and isinstance(record.get("setup_plan"), dict):
        rr = record["setup_plan"].get("rr")
    return rr.get("to_target_1") if isinstance(rr, dict) else None


def _stop(record: dict) -> Any:
    if "stop" in record:
        return record["stop"]
    if "trade_stop" in record:
        return record["trade_stop"]
    if "invalidation" in record:
        return record["invalidation"]
    setup = record.get("setup")
    if isinstance(setup, dict):
        return setup.get("stop", setup.get("trade_stop", setup.get("invalidation")))
    setup_plan = record.get("setup_plan")
    if isinstance(setup_plan, dict):
        return setup_plan.get("stop", setup_plan.get("trade_stop", setup_plan.get("invalidation")))
    return None


def revalidate_setup(previous: dict, current: dict) -> dict:
    """Revalidate an attempt using only explicit previous/current observations."""
    if not isinstance(previous, dict) or not isinstance(current, dict):
        raise ValueError("previous and current must be dicts")
    reasons: list[str] = []
    if _comparison_plan(previous) != _comparison_plan(current):
        reasons.append("STRUCTURE_CHANGED")

    thesis = current.get("thesis") if isinstance(current.get("thesis"), dict) else {}
    thesis_valid = _value(current, "thesis_valid")
    thesis_invalidated = _value(current, "thesis_invalidated")
    if thesis_valid is None:
        thesis_valid = thesis.get("valid")
    if thesis_invalidated is None:
        thesis_invalidated = thesis.get("invalidated")
    if thesis_invalidated is None:
        thesis_invalidated = thesis.get("status") == "INVALIDATED"
    if thesis_valid is False or thesis_invalidated is True:
        reasons.append("THESIS_INVALIDATED")

    data_current = _value(current, "data_current")
    data_status = _value(current, "data_status")
    if isinstance(data_status, dict):
        if data_current is None:
            data_current = data_status.get("current")
        data_status = data_status.get("status", data_status.get("freshness"))
    if data_current is False or (isinstance(data_status, str)
                                 and data_status.upper() not in {"CURRENT", "FRESH"}):
        reasons.append("DATA_NOT_CURRENT")

    rr = _rr(current)
    if isinstance(rr, bool) or not isinstance(rr, (int, float)) or not math.isfinite(rr):
        # Missing/invalid risk evidence is explicitly not current enough to
        # claim an active setup; it is not silently inferred from price fields.
        reasons.append("RR_BELOW_MINIMUM")
    elif rr < 2:
        reasons.append("RR_BELOW_MINIMUM")
    return {"status": "EXPIRED" if reasons else "ACTIVE", "reasons": reasons}


def lifecycle_projection(snapshots: list[dict], reviews: list[dict]) -> dict:
    """Return a deterministic, lossless candidate-grouped lifecycle view."""
    snapshot_rows = _json_copy(snapshots)
    review_rows = _json_copy(reviews)
    groups: dict[str, dict] = {}
    for row in snapshot_rows:
        if not isinstance(row, dict):
            raise ValueError("snapshot records must be dicts")
        candidate_id = _record_id(row, "candidate_id")
        _record_id(row, "setup_id")
        group = groups.setdefault(candidate_id, {
            "candidate_id": candidate_id,
            "latest_setup": None,
            "snapshots": [],
            "reviews": [],
        })
        group["snapshots"].append(row)
        group["latest_setup"] = row["setup_id"]
    for row in review_rows:
        if not isinstance(row, dict):
            raise ValueError("review records must be dicts")
        candidate_id = _record_id(row, "candidate_id")
        _record_id(row, "setup_id")
        _record_id(row, "snapshot_id")
        groups.setdefault(candidate_id, {
            "candidate_id": candidate_id,
            "latest_setup": None,
            "snapshots": [],
            "reviews": [],
        })["reviews"].append(row)
    return {"candidates": groups, "snapshot_count": len(snapshot_rows),
            "review_count": len(review_rows)}
