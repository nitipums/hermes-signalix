"""Canonical MVP snapshot built from one deterministic scan projection."""
from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "signalix.mvp.v1"

# Legacy projection fields are not canonical MVP decision data.  Keeping them
# in the artifact lets an old group/date leak beside the current Stage/Phase.
LEGACY_PROJECTION_FIELDS = frozenset({
    "evidence_summary",
    "old_group_mapping",
    "lifecycle_badge",
})


def sanitize_mvp_item(raw: dict) -> dict:
    """Keep canonical scan fields; remove stale legacy presentation labels."""
    if not isinstance(raw, dict):
        raise ValueError("MVP item must be an object")
    return {key: value for key, value in raw.items() if key not in LEGACY_PROJECTION_FIELDS}


def validate_mvp_snapshot(payload: dict, *, expected_run_id=None, expected_item_count=None) -> None:
    if payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("invalid MVP contract_version")
    if not isinstance(payload.get("items"), list):
        raise ValueError("MVP snapshot items must be a list")
    if expected_run_id is not None and payload.get("run_id") != expected_run_id:
        raise ValueError("MVP snapshot run_id mismatch")
    if expected_item_count is not None and len(payload["items"]) != expected_item_count:
        raise ValueError("MVP snapshot item count mismatch")


def daily_freshness_from_run(run_timestamp, scan_date, source_lineage, market_session):
    """Build Daily freshness from the committed scan run, not intraday registry."""
    session = market_session or {}
    return {
        "status": "market_closed" if session.get("status") == "market_closed" else "fresh",
        "source": (source_lineage or {}).get("source") or "unknown",
        "as_of": str(scan_date) if scan_date is not None else session.get("last_valid_session"),
        "data_fetched_at": str(run_timestamp) if run_timestamp is not None else None,
    }


def build_mvp_snapshot(items: list[dict], *, run_id: str | None,
                       scan_time: str | None, freshness: dict,
                       decision_state: str | None = None,
                       market: str = "TH") -> dict:
    """Build the stable MVP root contract from the current scan's serialized items."""
    if not isinstance(items, list):
        raise ValueError("MVP snapshot items must be a list")
    if not isinstance(freshness, dict):
        raise ValueError("MVP snapshot freshness must be an object")
    normalized = []
    for raw in items:
        item = sanitize_mvp_item(raw)
        provenance = dict(item.get("provenance") or {})
        if run_id is not None:
            provenance["scan_run_id"] = run_id
        if scan_time is not None:
            provenance["scan_time"] = scan_time
        if provenance:
            item["provenance"] = provenance
        normalized.append(item)
    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "scan_time": scan_time,
        "market": market,
        "decision_state": decision_state,
        "freshness": dict(freshness),
        "items": normalized,
    }


def load_mvp_artifact(path):
    """Load an already-canonical MVP artifact and validate its root contract."""
    import json
    from pathlib import Path
    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("invalid MVP contract_version")
    if not isinstance(payload.get("items"), list):
        raise ValueError("MVP artifact requires an items list")
    payload["items"] = [sanitize_mvp_item(item) for item in payload["items"]]
    return payload
