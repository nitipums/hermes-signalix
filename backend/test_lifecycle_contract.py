import copy
import json

import pytest

from lifecycle_contract import (
    REVIEW_EVENTS,
    append_review_event,
    append_snapshot,
    lifecycle_projection,
    make_candidate_id,
    make_setup_id,
    revalidate_setup,
)


def snapshot(level=12.5, status="READY"):
    candidate_id = make_candidate_id("ABC", "2026-08-30", "policy-v1")
    setup = {"levels": {"support": 11}, "trigger": level, "stop": 10,
             "targets": [17.5, 20], "as_of": "2026-08-30T10:00:00Z"}
    return {"snapshot_id": f"snap-{level}", "candidate_id": candidate_id,
            "setup_id": make_setup_id(candidate_id, setup), **setup,
            "status": status}


def test_candidate_and_setup_ids_are_distinct_and_immutable():
    assert make_candidate_id("ABC", "2026-08-30", "policy-v1") != make_candidate_id("ABC", "2026-08-31", "policy-v1")
    first = snapshot()
    assert first["candidate_id"] != first["setup_id"]
    assert make_setup_id(first["candidate_id"], first) == first["setup_id"]
    assert make_setup_id(first["candidate_id"], {**first, "trigger": 13}) != first["setup_id"]


def test_append_snapshot_preserves_history_and_rejects_rewrite():
    first, second = snapshot(), snapshot(13)
    history = append_snapshot([], first)
    original = copy.deepcopy(history)
    result = append_snapshot(history, second)
    assert history == original
    assert [row["snapshot_id"] for row in result] == ["snap-12.5", "snap-13"]
    assert append_snapshot(result, copy.deepcopy(first)) == result
    with pytest.raises(ValueError, match="cannot be rewritten"):
        append_snapshot(result, {**first, "status": "INVALIDATED"})


def test_all_review_events_are_valid_and_references_are_exact():
    events = []
    for index, event in enumerate(REVIEW_EVENTS):
        events = append_review_event(events, "candidate", "setup", "snapshot", event,
                                     note="review", created_at=f"2026-08-30T10:0{index}:00Z")
    assert [row["event"] for row in events] == list(REVIEW_EVENTS)
    assert all(row["candidate_id"] == "candidate" and row["setup_id"] == "setup"
               and row["snapshot_id"] == "snapshot" for row in events)
    with pytest.raises(ValueError, match="invalid review event"):
        append_review_event(events, "candidate", "setup", "snapshot", "BUY")
    assert append_review_event(events, "candidate", "setup", "snapshot", "NOTE",
                              snapshot_as_of="2026-08-30")[-1]["created_at"] == "2026-08-30"


def test_revalidation_expiry_paths_and_active_unchanged():
    base = {"trigger": 12.5, "stop": 10, "targets": [17.5],
            "thesis_valid": True, "data_current": True, "rr": {"to_target_1": 2.0}}
    assert revalidate_setup(base, dict(base)) == {"status": "ACTIVE", "reasons": []}
    cases = [
        ("trigger", {**base, "trigger": 13}, "STRUCTURE_CHANGED"),
        ("thesis", {**base, "thesis_valid": False}, "THESIS_INVALIDATED"),
        ("data", {**base, "data_current": False}, "DATA_NOT_CURRENT"),
        ("rr", {**base, "rr": {"to_target_1": 1.99}}, "RR_BELOW_MINIMUM"),
    ]
    for _, current, reason in cases:
        result = revalidate_setup(base, current)
        assert result["status"] == "EXPIRED"
        assert reason in result["reasons"]


def test_projection_retains_historical_records_and_is_json_safe():
    old = snapshot(status="EXPIRED")
    stopped = snapshot(13, status="INVALIDATED")
    reviews = append_review_event([], old["candidate_id"], old["setup_id"], old["snapshot_id"], "NOTE",
                                  note="historical", snapshot_as_of=old["as_of"])
    projected = lifecycle_projection([old, stopped], reviews)
    group = projected["candidates"][old["candidate_id"]]
    assert group["latest_setup"] == stopped["setup_id"]
    assert [row["status"] for row in group["snapshots"]] == ["EXPIRED", "INVALIDATED"]
    assert group["reviews"][0]["snapshot_id"] == old["snapshot_id"]
    serialized = json.dumps(projected, sort_keys=True)
    assert json.loads(serialized) == projected
    # Caller-owned nested values are not retained by reference.
    old["status"] = "CHANGED_AFTER_PROJECTION"
    assert group["snapshots"][0]["status"] == "EXPIRED"
