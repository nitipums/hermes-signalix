"""Canonical Trend/Elliott/Trade-Setup candidate contract.

This module is deliberately a pure serialization and projection boundary.  It
does not calculate indicators, query a database, or use VCP as a gate.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Iterable
from decimal import Decimal
from typing import Any


POLICY_VERSION = "setup-candidates-v1"
DECISIONS = {"REVIEW", "WAIT", "AVOID", "DATA_BLOCKED"}


def _json_value(value: Any):
    """Convert pandas/numpy-like values to ordinary JSON-safe values."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value) if math.isfinite(value) else None
    if hasattr(value, "item"):
        return _json_value(value.item())
    if isinstance(value, (Decimal, numbers.Number)):
        number = float(value)
        return number if math.isfinite(number) else None
    # pandas.NA/NaT and similar scalar sentinels are missing values, not text.
    if type(value).__name__ in {"NAType", "NaTType"}:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _peer_rows(peer_data: dict | None) -> list[dict]:
    peers = (peer_data or {}).get("peers")
    if peers is None:
        peers = (peer_data or {}).get("peer_trends")
    if isinstance(peers, dict):
        return [{"symbol": symbol, **(row if isinstance(row, dict) else {"trend": row})}
                for symbol, row in peers.items()]
    if isinstance(peers, Iterable) and not isinstance(peers, (str, bytes)):
        return [row if isinstance(row, dict) else {"symbol": row} for row in peers]
    return []


def _peer_is_up(row: dict) -> bool | None:
    trend = row.get("trend") if isinstance(row.get("trend"), dict) else row
    state = trend.get("state") or trend.get("trend_state")
    if state in {"uptrend", "emerging_uptrend"}:
        return True
    if state in {"downtrend", "falling", "flat"}:
        return False
    return None


def build_peer_context(symbol: str, peer_data: dict | None = None) -> dict:
    """Build explicit sector/industry context without excluding ``symbol``.

    ``peer_data`` accepts authoritative direct fields or peer rows under
    ``peers``/``peer_trends``.  Missing taxonomy and peer observations remain
    visible as ``None``/``UNKNOWN`` rather than being inferred.
    """
    source = dict(peer_data or {})
    rows = _peer_rows(source)
    peer_symbols = source.get("peer_symbols")
    if peer_symbols is None:
        peer_symbols = [row.get("symbol") for row in rows if row.get("symbol")]
    peer_symbols = [str(item) for item in peer_symbols if item]

    breadth_values = [_peer_is_up(row) for row in rows]
    breadth_values = [value for value in breadth_values if value is not None]
    breadth = None
    if breadth_values:
        breadth = f"{sum(breadth_values)}/{len(breadth_values)}"
    elif source.get("peer_trend_breadth") is not None:
        breadth = source["peer_trend_breadth"]

    breakout_count = source.get("peer_breakout_count")
    if breakout_count is None and rows:
        breakout_count = sum(bool(
            row.get("is_52w_high_breakout", row.get("breakout", False))
        ) for row in rows)

    leadership = source.get("sector_leader_or_laggard", source.get("sector_leadership"))
    if leadership is None:
        leadership = source.get("leader_or_laggard")
    if leadership is None:
        if source.get("is_leader") is True:
            leadership = "LEADER"
        elif source.get("is_laggard") is True:
            leadership = "LAGGARD"

    result = {
        "market_regime": source.get("market_regime"),
        "sector": source.get("sector"),
        "industry": source.get("industry"),
        "peer_symbols": peer_symbols,
        "sector_trend": source.get("sector_trend"),
        "peer_trend_breadth": _json_value(breadth),
        "peer_breakout_count": breakout_count,
        "sector_leader_or_laggard": leadership,
        "relative_strength_vs_sector": source.get("relative_strength_vs_sector"),
        "peer_data_status": source.get("peer_data_status") or ("AVAILABLE" if rows else "UNKNOWN"),
    }
    return _json_value(result)


def _has_blocked_data(data_status: dict, wave: dict, setup: dict) -> bool:
    status = str(data_status.get("status", "")).upper()
    freshness = str(data_status.get("freshness", "")).lower()
    if data_status.get("sufficient") is False:
        return True
    if status in {"STALE", "INVALID", "UNAVAILABLE", "NOT_VERIFIED", "INSUFFICIENT"}:
        return True
    if freshness in {"stale", "unknown", "invalid", "unavailable"}:
        return True
    if str(setup.get("status", "")).upper() == "DATA_BLOCKED":
        return True
    if wave.get("timeframe", "daily") not in {None, "daily"}:
        return True
    if setup.get("timeframe", "60m") not in {None, "60m"}:
        return True
    return (wave.get("state") == "UNKNOWN" or
            str(wave.get("confidence", "")).upper() == "INSUFFICIENT")


def _status_token(value: Any) -> str:
    return str(value or "").upper().replace("-", "_").replace(" ", "_")


def _decision(data_status: dict, wave: dict, setup: dict) -> str:
    if _has_blocked_data(data_status, wave, setup):
        return "DATA_BLOCKED"
    setup_status = _status_token(setup.get("status"))
    evidence = wave.get("evidence") or {}
    failed_statuses = {
        "INVALIDATED", "AVOID", "FAILED", "BROKEN", "DO_NOT_CHASE",
        "FAILED_STRUCTURE", "STRUCTURE_FAILED", "BROKEN_STRUCTURE",
        "FAILED_RISK", "RISK_FAILED", "UNACCEPTABLE_RISK",
    }
    risk_status = _status_token(setup.get("risk_status"))
    if (setup_status in failed_statuses or
            setup.get("risk_acceptable") is False or
            risk_status in {"UNACCEPTABLE", "INVALID", "FAILED", "BROKEN",
                             "DO_NOT_CHASE", "FAILED_RISK", "RISK_FAILED",
                             "UNACCEPTABLE_RISK"} or
            evidence.get("structure_intact") is False):
        return "AVOID"
    if setup_status in {"READY", "PRE_TRIGGER", "TESTED_TRIGGER", "TRIGGERED"}:
        return "REVIEW"
    return "WAIT"


def build_setup_candidate(
    symbol: str,
    as_of: str,
    data_status: dict,
    trend: dict,
    wave: dict,
    setup: dict,
    context: dict,
    bonus_evidence: dict,
    provenance: dict,
) -> dict:
    """Build one canonical, JSON-safe setup-candidate item."""
    wave_out = dict(wave or {})
    if wave_out.get("timeframe") is None:
        wave_out["timeframe"] = "daily"
    setup_out = dict(setup or {})
    if setup_out.get("timeframe") is None:
        setup_out["timeframe"] = "60m"
    if wave_out.get("primary_state") is None and wave_out.get("state") is not None:
        wave_out["primary_state"] = wave_out["state"]
    lane = _decision(data_status or {}, wave_out, setup_out)
    item = {
        "symbol": str(symbol),
        "as_of": as_of,
        "data_status": data_status or {},
        "trend": trend or {},
        "wave": wave_out,
        "setup": setup_out,
        "context": context or {},
        "bonus_evidence": bonus_evidence or {},
        "decision_lane": lane,
        "provenance": provenance or {},
    }
    return _json_value(item)


def project_setup_candidate_list(
    items: list[dict],
    *,
    as_of: str | None = None,
    provenance: dict | None = None,
    universe: str = "TH-ORD",
) -> dict:
    """Project the complete evaluated list; presentation never removes rows."""
    safe_items = [_json_value(item) for item in (items or [])]
    dates = [item.get("as_of") for item in safe_items if item.get("as_of")]
    return {
        "items": safe_items,
        "count": len(safe_items),
        "as_of": as_of or (max(dates) if dates else None),
        "policy_version": (provenance or {}).get("policy_version", POLICY_VERSION),
        "universe": universe,
        "provenance": _json_value(provenance or {}),
    }


# Descriptive compatibility alias for callers that prefer the API wording.
project_setup_candidates = project_setup_candidate_list
build_setup_candidate_list = project_setup_candidate_list
build_context = build_peer_context
