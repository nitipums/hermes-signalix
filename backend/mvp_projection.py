"""Compatibility projection boundary.

The legacy dashboard snapshot is retained for audit/replay only. The
canonical setup-candidates route does not call this module or use its output
as a fallback.
"""
from __future__ import annotations

import json
from pathlib import Path

CONTRACT_VERSION = "signalix.mvp.v1"

COMPATIBILITY_DEPRECATION = {
    "status": "audit_only",
    "boundary": "one_day",
    "message": "Legacy snapshot projection is retained for audit/replay only; use /api/setup-candidates.",
}


def project_legacy_snapshot(payload: dict) -> dict:
    """Translate a legacy snapshot root into the canonical MVP payload."""
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("MVP projection requires an items list")
    dashboard_meta = payload.get("dashboard_meta") or {}
    freshness = {
        "status": payload.get("data_freshness_status") or dashboard_meta.get("data_freshness_status") or "unknown",
        "source": payload.get("data_freshness_source") or dashboard_meta.get("data_freshness_source"),
        "as_of": payload.get("last_valid_session") or (payload.get("market_session") or {}).get("last_valid_session"),
        "data_fetched_at": payload.get("data_fetched_at") or dashboard_meta.get("data_fetched_at"),
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "audit_only": True,
        "deprecation": dict(COMPATIBILITY_DEPRECATION),
        "scan_time": payload.get("scan_time"),
        "scan_run_id": payload.get("scan_run_id"),
        "decision_state": payload.get("decision_state"),
        "freshness": freshness,
        "items": [dict(item) for item in items if isinstance(item, dict)],
    }


def load_mvp_snapshot(path: str | Path) -> dict:
    path = Path(path)
    with path.open(encoding="utf-8") as handle:
        return project_legacy_snapshot(json.load(handle))
