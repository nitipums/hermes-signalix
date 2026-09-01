"""Canonical MVP snapshot built from one deterministic scan projection."""
from __future__ import annotations

import copy
from typing import Any

CONTRACT_VERSION = "signalix.mvp.v1"

# Legacy projection fields are not canonical MVP decision data. Keeping them
# in compatibility artifacts preserves audit evidence without letting an old
# group/date leak beside the canonical setup-candidate decision.
LEGACY_PROJECTION_FIELDS = frozenset({
    "evidence_summary",
    "old_group_mapping",
    "lifecycle_badge",
})

CANONICAL_SETUP_FIELDS = frozenset({
    "symbol", "as_of", "data_status", "trend", "wave", "setup",
    "context", "bonus_evidence", "provenance",
})

# These fields describe the retired dashboard/VCP taxonomy.  They may remain
# useful to audit consumers, but must not compete with setup-candidate
# ``decision``/``wave``/``setup`` on the primary MVP item.
LEGACY_PRIMARY_FIELDS = frozenset({
    "group", "baseGroup", "primary_group", "primaryGroup", "primary_label",
    "primaryLabel", "primary_action", "primaryAction", "status", "action",
    "primary_state", "primaryState",
    "lifecycle_badge", "lifecycleState", "action_queue", "actionQueue",
    "setup_proximity", "setupProximity", "legacy_alias", "legacyAlias",
    "evidence_summary", "old_group_mapping",
})


def _is_setup_candidate(item: dict) -> bool:
    return (CANONICAL_SETUP_FIELDS <= set(item)
            and bool({"decision", "decision_lane"}.intersection(item)))


def _nest_legacy_fields(item: dict) -> dict:
    """Move competing labels aside while retaining their exact raw values."""
    result = copy.deepcopy(item)
    audit = dict(result.get("audit") or {})
    legacy = dict(audit.get("legacy_projection") or {})
    for key in LEGACY_PRIMARY_FIELDS:
        if key in result:
            legacy[key] = result.pop(key)
    if legacy:
        audit["legacy_projection"] = legacy

    # A producer may still attach the old VCP detector directly.  Keep it as
    # optional supporting evidence, never as a second primary decision.
    bonus = dict(result.get("bonus_evidence") or {})
    if "vcp" in result:
        vcp = result.pop("vcp")
        if "vcp" in bonus:
            audit["legacy_vcp"] = copy.deepcopy(vcp)
        else:
            bonus["vcp"] = vcp
    if "evidence" in result:
        raw_evidence = result.pop("evidence")
        vcp = bonus.setdefault("vcp", {})
        if isinstance(vcp, dict):
            vcp.setdefault("raw_evidence", raw_evidence)
        else:
            audit.setdefault("raw_evidence", {})["evidence"] = raw_evidence
    result["bonus_evidence"] = bonus
    if audit:
        audit["raw_item"] = copy.deepcopy(item)
        result["audit"] = audit
    return result


def sanitize_mvp_item(raw: dict) -> dict:
    """Sanitize canonical items without deleting legacy/raw audit evidence.

    Legacy-only rows retain their historical shape for the retired/audit
    callers.  Once a row is a setup-candidate item, however, the canonical
    contract is the only primary surface and retired labels are nested.
    """
    if not isinstance(raw, dict):
        raise ValueError("MVP item must be an object")
    if _is_setup_candidate(raw):
        return _nest_legacy_fields(raw)
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
