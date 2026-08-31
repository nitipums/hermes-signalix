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
DECISION_LANES = {
    "REVIEW_NOW", "SETUP_FORMING", "DAILY_CANDIDATE", "WAIT", "AVOID", "DATA_BLOCKED",
}
_LANE_ORDER = {
    "REVIEW_NOW": 0, "SETUP_FORMING": 1, "DAILY_CANDIDATE": 2,
    "WAIT": 3, "AVOID": 4, "DATA_BLOCKED": 5,
}
_CONFIDENCE_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


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


def attach_bonus_vcp(item: dict, vcp_evidence: dict | None) -> dict:
    """Attach optional VCP evidence; its absence never blocks a candidate.

    Only an explicitly present, verified VCP observation is positive.  All
    other inputs remain an explicit non-computed observation so missing VCP
    data cannot be mistaken for a failed or positive screening result.
    """
    evidence = vcp_evidence if isinstance(vcp_evidence, dict) else {}
    present = evidence.get("present")
    quality = evidence.get("quality")
    if present is True and quality != "NOT_VERIFIED":
        vcp = {
            "present": True,
            "quality": quality,
            "source": evidence.get("source"),
        }
    else:
        vcp = {
            "present": None if present is not False else False,
            "quality": quality,
            "source": "not_computed",
        }
    bonus_evidence = item.get("bonus_evidence")
    if not isinstance(bonus_evidence, dict):
        bonus_evidence = {}
        item["bonus_evidence"] = bonus_evidence
    bonus_evidence["vcp"] = _json_value(vcp)
    return item


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
    wave_state = wave.get("primary_state", wave.get("state"))
    return (wave_state == "UNKNOWN" or
            str(wave.get("confidence", "")).upper() == "INSUFFICIENT")


def _status_token(value: Any) -> str:
    return str(value or "").upper().replace("-", "_").replace(" ", "_")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _wave_confidence(wave: dict) -> str:
    """Normalize legacy classifier tokens at the projection boundary."""
    confidence = _status_token(wave.get("confidence"))
    return {"INSUFFICIENT": "LOW", "PARTIAL": "MEDIUM"}.get(confidence, confidence)


def _has_plan(setup: dict) -> bool:
    targets = setup.get("targets")
    if not isinstance(targets, (list, tuple)):
        targets = [targets] if targets is not None else []
    return (_number(setup.get("trigger")) is not None
            and _number(setup.get("invalidation")) is not None
            and any(_number(target) is not None for target in targets))


def project_decision_lane(data_status: dict, wave: dict, setup: dict,
                          trend: dict | None = None) -> str:
    """Project one canonical item into the fail-closed user decision lanes."""
    data_status, wave, setup = data_status or {}, wave or {}, setup or {}
    if _has_blocked_data(data_status, wave, setup):
        return "DATA_BLOCKED"

    setup_status = _status_token(setup.get("status"))
    wave_state = _status_token(wave.get("primary_state") or wave.get("state"))
    evidence = wave.get("evidence") or {}
    failed_statuses = {
        "INVALIDATED", "AVOID", "FAILED", "BROKEN", "DO_NOT_CHASE",
        "FAILED_STRUCTURE", "STRUCTURE_FAILED", "BROKEN_STRUCTURE",
        "FAILED_RISK", "RISK_FAILED", "UNACCEPTABLE_RISK", "EXPIRED", "EXTENDED",
    }
    risk_status = _status_token(setup.get("risk_status"))
    if (setup_status in failed_statuses
            or setup.get("risk_acceptable") is False
            or risk_status in {"UNACCEPTABLE", "INVALID", "FAILED", "BROKEN",
                               "DO_NOT_CHASE", "FAILED_RISK", "RISK_FAILED",
                               "UNACCEPTABLE_RISK"}
            or wave.get("structure_intact") is False
            or evidence.get("structure_intact") is False):
        return "AVOID"

    confidence = _wave_confidence(wave)
    has_plan = _has_plan(setup)
    rr = _number((setup.get("rr") or {}).get("to_target_1"))
    review_status = setup_status in {"PRE_TRIGGER", "TESTED_TRIGGER", "TRIGGERED"}
    if (review_status and confidence in {"MEDIUM", "HIGH"} and has_plan
            and rr is not None and rr >= 2):
        return "REVIEW_NOW"
    if has_plan and (confidence == "LOW" or setup_status == "FORMING"
                     or (rr is not None and rr < 2)):
        return "SETUP_FORMING"
    if wave_state not in {"", "UNKNOWN", "INSUFFICIENT"}:
        return "DAILY_CANDIDATE"
    return "WAIT"


def _decision(data_status: dict, wave: dict, setup: dict) -> str:
    # Compatibility entry point; callers get the new canonical projection.
    return project_decision_lane(data_status, wave, setup)


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
    lane = project_decision_lane(data_status or {}, wave_out, setup_out, trend or {})
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


def project_lane_order(item: dict) -> tuple:
    """Return the deterministic, explainable T8 presentation key.

    Missing observations are explicitly ranked after present observations. No
    value is derived from a similarly named field or from a financial metric.
    """
    lane = _status_token(item.get("decision_lane"))
    wave = item.get("wave") or {}
    confidence = _wave_confidence(wave)
    trend = item.get("trend") or {}
    trend_state = str(trend.get("state", "")).lower()
    setup = item.get("setup") or {}
    close = _number(setup.get("close"))
    if close is None:
        close = _number(item.get("close"))
    if close is None:
        close = _number((item.get("trend") or {}).get("close"))
    def descending(value, neutral=1):
        number = _number(value)
        return (0, -number) if number is not None else (neutral, 0)

    def present_first(value, true_rank=0, false_rank=1):
        if value is True:
            return true_rank
        if value is False:
            return false_rank
        return 2

    setup_status = _status_token(setup.get("status"))
    review_status_order = {"PRE_TRIGGER": 0, "TESTED_TRIGGER": 1, "TRIGGERED": 2}
    status_rank = (review_status_order.get(setup_status, 3)
                   if lane == "REVIEW_NOW" else 3)

    trigger = _number(setup.get("trigger"))
    proximity = (abs(close - trigger) / trigger
                 if close is not None and trigger not in (None, 0) else None)
    proximity_key = (0, proximity) if proximity is not None else (1, 0)
    rr = _number((setup.get("rr") or {}).get("to_target_1"))

    strength = descending(trend.get("rise_20d_pct"))
    strength_60 = descending(trend.get("rise_60d_pct"))
    relative_strength = descending(trend.get("relative_strength"))
    high_breakout = present_first(trend.get("is_52w_high_breakout"))
    ath_breakout = present_first(trend.get("is_ath_breakout"))
    near_high = present_first(trend.get("near_52w_high"))

    context = item.get("context") or {}
    sector_trend = str(context.get("sector_trend") or "").lower()
    sector_trend_rank = {"uptrend": 0, "emerging_uptrend": 1}.get(sector_trend, 2)
    peer_breadth = context.get("peer_trend_breadth")
    breadth = None
    if isinstance(peer_breadth, str) and "/" in peer_breadth:
        try:
            up, total = peer_breadth.split("/", 1)
            if float(total) > 0:
                breadth = float(up) / float(total)
        except (TypeError, ValueError):
            breadth = None
    peer_breakouts = descending(context.get("peer_breakout_count"))
    sector_leadership = str(context.get("sector_leader_or_laggard") or "").upper()
    leadership_rank = {"LEADER": 0, "LAGGARD": 2}.get(sector_leadership, 1)
    peer_context_status = 0 if context.get("peer_data_status") == "AVAILABLE" else 1

    vcp = (item.get("bonus_evidence") or {}).get("vcp") or {}
    vcp_rank = (0 if vcp.get("present") is True else 1
                if vcp.get("present") is False else 2)
    symbol = str(item.get("symbol") or "")
    return (
        _LANE_ORDER.get(lane, 9),
        _CONFIDENCE_ORDER.get(confidence, 3),
        {"uptrend": 0, "emerging_uptrend": 1}.get(trend_state, 2),
        status_rank,
        proximity_key,
        (0, -rr) if rr is not None else (1, 0),
        strength, strength_60, relative_strength,
        high_breakout, ath_breakout, near_high,
        sector_trend_rank, (0, -breadth) if breadth is not None else (1, 0),
        peer_breakouts, leadership_rank, peer_context_status,
        vcp_rank,
        symbol,
    )


def sort_setup_candidates(items: list[dict]) -> list[dict]:
    """Sort candidates by the explainable lane ordering without mutating input."""
    return sorted(items or [], key=project_lane_order)


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
