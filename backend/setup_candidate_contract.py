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
    reason_codes = {_status_token(code) for code in (data_status.get("reason_codes") or [])}
    scalar_reason = _status_token(data_status.get("reason_code"))
    if scalar_reason:
        reason_codes.add(scalar_reason)
    if any(code == "NO_DAILY_DATA" or code == "NO_60M_DATA"
           or code.startswith(("STALE_", "INVALID_")) for code in reason_codes):
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


def _normalize_marker_timestamp(value: Any) -> str | None:
    """Match chart candle timestamps without changing date-only Daily values."""
    if value is None:
        return None
    raw = value.isoformat() if hasattr(value, "isoformat") else str(value)
    raw = raw.strip()
    if not raw:
        return None
    if len(raw) > 10 and raw[10] == " ":
        raw = raw[:10] + "T" + raw[11:]
    return raw


def _setup_evidence_markers(setup: dict, wave: dict, provenance: dict) -> list[dict]:
    """Expose setup levels as source-linked 60m markers when timestamped."""
    setup, provenance = setup or {}, provenance or {}
    setup_provenance = setup.get("provenance") if isinstance(setup.get("provenance"), dict) else {}
    timestamp = setup_provenance.get("as_of") or provenance.get("intraday_as_of")
    snapshot_id = setup.get("snapshot_id") or provenance.get("snapshot_id")
    if snapshot_id is None and timestamp is not None:
        snapshot_id = "60m:" + str(timestamp)
    result = []
    for kind, price_key, timestamp_key, label, role, refs in (
        ("TRIGGER", "trigger", "trigger_timestamp", "60m trigger", "SETUP", ["setup.trigger"]),
        ("TRADE_STOP", "trade_stop", "trade_stop_timestamp", "Trade stop", "TRADE_RISK", ["setup.trade_stop"]),
    ):
        price = _number(setup.get(price_key))
        marker_timestamp = _normalize_marker_timestamp(setup.get(timestamp_key) or timestamp)
        if price is None or marker_timestamp is None:
            continue
        result.append(_json_value({
            "id": "setup-" + kind.lower().replace("_", "-"), "kind": kind,
            "timeframe": "60m", "timestamp": str(marker_timestamp), "price": price,
            "label": label, "wave_role": role, "source": "intraday_ohlcv",
            "confidence": "HIGH" if setup.get("status") not in {"DATA_BLOCKED", "FORMING"} else "MEDIUM",
            "evidence_refs": refs, "snapshot_id": snapshot_id,
            "snapshot_identity": snapshot_id,
            "explanation": {"rule": "Deterministic 60m setup level from the trade-setup payload.",
                            "evidence": refs, "alternative": None,
                            "missing": [], "policy": "setup-candidates-v1"},
        }))
    return result


def _wave_confidence(wave: dict) -> str:
    """Normalize legacy classifier tokens at the projection boundary."""
    confidence = _status_token(wave.get("confidence"))
    return {"INSUFFICIENT": "LOW", "PARTIAL": "MEDIUM"}.get(confidence, confidence)


def _normalize_wave_evidence(wave: dict) -> dict:
    """Guarantee the evidence shape for every canonical wave interpretation."""
    result = dict(wave or {})
    state = result.get("primary_state", result.get("state", "UNKNOWN"))
    for field in ("supporting_evidence", "contradicting_evidence", "missing_evidence"):
        value = result.get(field)
        if value is None:
            result[field] = []
        elif not isinstance(value, list):
            result[field] = list(value) if isinstance(value, (tuple, set)) else [value]
    # A producer may provide the legacy state key only; keep the canonical
    # state explicit so downstream consumers do not infer it from evidence.
    if result.get("primary_state") is None and result.get("state") is not None:
        result["primary_state"] = result["state"]
    if state != "UNKNOWN":
        return result
    return result


def _has_plan(setup: dict) -> bool:
    targets = setup.get("targets")
    if not isinstance(targets, (list, tuple)) or not targets:
        return False

    # Compatibility payloads predate named target objects and contain only
    # scalar prices, e.g. ``targets: [120]``.  Keep this narrow adapter
    # separate from the canonical named-target validation below: a mixed list
    # must never silently downgrade into the legacy interpretation.
    scalar_targets = all(
        isinstance(target, numbers.Number) and not isinstance(target, bool)
        and _number(target) is not None
        for target in targets
    )
    if scalar_targets:
        return (_number(setup.get("trigger")) is not None
                and _number(setup.get("invalidation")) is not None)

    target_1 = setup.get("target_1")
    if target_1 is None:
        target_1 = next((target.get("price") for target in targets
                         if isinstance(target, dict) and target.get("name") == "target_1"), None)
    target_1 = _number(target_1)
    ordered_targets = all(
        isinstance(target, dict) and target.get("name") == f"target_{index}"
        and _number(target.get("price")) is not None
        for index, target in enumerate(targets, start=1)
    )
    first_target = targets[0].get("price") if isinstance(targets[0], dict) else None
    return (_number(setup.get("trigger")) is not None
            and _number(setup.get("invalidation")) is not None
            and target_1 is not None
            and ordered_targets
            and _number(first_target) == target_1)


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
    if wave_state not in {"", "UNKNOWN", "INSUFFICIENT", "NOT_VERIFIABLE"}:
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
    canonical_metadata: dict | None = None,
) -> dict:
    """Build one canonical, JSON-safe setup-candidate item."""
    wave_out = _normalize_wave_evidence(wave)
    if wave_out.get("timeframe") is None:
        wave_out["timeframe"] = "daily"
    setup_out = dict(setup or {})
    # Direct engine-to-contract composition can carry this legacy adapter
    # field.  Normalize it into the data layer so setup.reason_code remains a
    # setup-only diagnostic.
    engine_data_reason = setup_out.pop("data_reason_code", None)
    data_status_out = dict(data_status or {})
    reason_codes = list(data_status_out.get("reason_codes") or [])
    if data_status_out.get("reason_code"):
        reason_codes.insert(0, data_status_out["reason_code"])
    if engine_data_reason:
        reason_codes.append(engine_data_reason)
    reason_codes = list(dict.fromkeys(
        _status_token(code) for code in reason_codes if code
    ))
    if reason_codes:
        data_status_out["reason_code"] = reason_codes[0]
        data_status_out["reason_codes"] = reason_codes
    if setup_out.get("timeframe") is None:
        setup_out["timeframe"] = "60m"
    if wave_out.get("primary_state") is None and wave_out.get("state") is not None:
        wave_out["primary_state"] = wave_out["state"]
    lane = project_decision_lane(data_status_out, wave_out, setup_out, trend or {})
    provenance_out = provenance or {}
    daily_markers = (wave_out.get("evidence_markers") or [])
    setup_markers = _setup_evidence_markers(setup_out, wave_out, provenance_out)
    # Explicit timeframe buckets prevent a Daily marker from appearing on a 60m chart.
    chart_evidence = {"daily": {"timeframe": "daily", "markers": daily_markers},
                      "60m": {"timeframe": "60m", "markers": setup_markers,
                              "daily_mapping": None}}
    # Chart-linked evidence is part of the setup presentation payload, not a
    # competing top-level canonical field.  Keeping it nested preserves the
    # exact serving envelope while retaining the Daily/60m boundary.
    if daily_markers or setup_markers:
        setup_out["chart_evidence"] = chart_evidence
    item = {
        "symbol": str(symbol),
        "as_of": as_of,
        "data_status": data_status_out,
        "trend": trend or {},
        "wave": wave_out,
        "setup": setup_out,
        "context": context or {},
        "bonus_evidence": bonus_evidence or {},
        "decision_lane": lane,
        "provenance": provenance_out,
    }
    if isinstance(canonical_metadata, dict):
        for field in ("high52", "low52", "ath_high", "ath_low", "index_membership",
                      "index_membership_evidence"):
            if field in canonical_metadata:
                item[field] = _json_value(canonical_metadata[field])
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


# This is intentionally a presentation projection, not a second candidate
# contract.  The canonical read model remains complete; the symbol detail
# route reads that model directly.  Keep this list small because it is sent
# for every paginated card, while the drawer fetches full evidence by symbol.
_LIST_ITEM_FIELDS = (
    "symbol", "as_of", "data_status", "trend", "wave", "setup",
    "context", "bonus_evidence", "decision_lane", "provenance",
    "high52", "low52", "ath_high", "ath_low", "index_membership",
    "index_membership_evidence",
)
_LIST_NESTED_FIELDS = {
    "data_status": (
        "sufficient", "freshness", "source", "daily_available",
        "daily_final_session_available", "daily_final_session_status",
        "daily_freshness", "intraday_60m_available",
        "intraday_60m_freshness", "intraday_60m_status", "intraday_60m_as_of",
        "reason_code", "reason_codes",
    ),
    "trend": (
        "state", "rise_20d_pct", "rise_60d_pct", "relative_strength",
        "near_52w_high", "is_52w_high_breakout", "is_ath_breakout",
    ),
    "wave": (
        "timeframe", "primary_state", "state", "alternative_state", "confidence",
    ),
    "setup": (
        "timeframe", "state", "status", "minor_structure", "trigger",
        "entry_zone", "invalidation", "trade_stop", "thesis_invalidation",
        "targets", "target_1", "rr", "reason", "reason_code",
    ),
    "context": (
        "market_regime", "sector", "industry", "peer_symbols", "sector_trend",
        "peer_trend_breadth", "peer_breakout_count", "sector_leader_or_laggard",
        "relative_strength_vs_sector", "peer_data_status",
    ),
    "bonus_evidence": ("vcp", "breakout_volume", "contraction"),
    "provenance": (
        "policy_version", "source", "daily_source", "intraday_source", "as_of",
        "intraday_as_of", "freshness", "universe_filter",
        "marginable_schema_version", "marginable_source_document",
        "marginable_effective_date", "source_version", "snapshot_id",
    ),
}


def compact_setup_candidate_for_list(item: dict) -> dict:
    """Return the bounded card projection of one fully evaluated candidate.

    Filtering, sorting, counts, and pagination happen before this function is
    called.  Unknown future fields are deliberately not copied into the list;
    full canonical evidence remains available from symbol detail.
    """
    compact = {}
    for field in _LIST_ITEM_FIELDS:
        value = item.get(field)
        if field not in _LIST_NESTED_FIELDS:
            compact[field] = _json_value(value)
            continue
        source = value if isinstance(value, dict) else {}
        compact[field] = {
            nested: _json_value(source[nested])
            for nested in _LIST_NESTED_FIELDS[field]
            if nested in source
        }
    return compact


def _diagnostic_bucket(count_symbols: list[str]) -> dict:
    symbols = sorted(set(count_symbols))
    return {"count": len(symbols), "symbols": symbols}


def build_setup_candidate_diagnostic(
    items: list[dict], *, as_of: str | None, universe: str,
    returned_count: int,
) -> dict:
    """Summarize every evaluated row without changing the served item page.

    Buckets describe deterministic evidence gaps, not additional decision
    labels.  Missing data buckets take precedence over stale/invalid evidence;
    a row can appear in more than one independent evidence bucket.
    """
    daily_unavailable, intraday_unavailable = [], []
    stale_invalid, no_setup, invalid_risk_fib = [], [], []
    lane_totals = {lane: 0 for lane in (
        "REVIEW_NOW", "SETUP_FORMING", "DAILY_CANDIDATE", "WAIT", "AVOID", "DATA_BLOCKED"
    )}
    for item in items or []:
        symbol = str(item.get("symbol", ""))
        data = item.get("data_status") or {}
        setup = item.get("setup") or {}
        lane = str(item.get("decision_lane", "")).upper()
        if lane in lane_totals:
            lane_totals[lane] += 1

        data_reason_codes = {
            _status_token(code) for code in (data.get("reason_codes") or [])
        }
        scalar_reason = _status_token(data.get("reason_code"))
        if scalar_reason:
            data_reason_codes.add(scalar_reason)
        daily_missing = "NO_DAILY_DATA" in data_reason_codes
        intraday_missing = "NO_60M_DATA" in data_reason_codes
        if daily_missing:
            daily_unavailable.append(symbol)
        if intraday_missing:
            intraday_unavailable.append(symbol)

        stale_or_invalid = any(code.startswith(("STALE_", "INVALID_"))
                               for code in data_reason_codes)
        if stale_or_invalid:
            stale_invalid.append(symbol)

        setup_reason_code = _status_token(setup.get("reason_code"))
        risk_status = str(setup.get("risk_status", "")).upper()
        risk_fib_invalid = (
            setup_reason_code == "RISK_INVALID"
            or risk_status in {"INVALID", "FAILED", "BROKEN", "FAILED_RISK", "RISK_FAILED"}
        )
        if risk_fib_invalid:
            invalid_risk_fib.append(symbol)

        if setup_reason_code == "NO_SETUP_DETECTED" and data.get("sufficient") is not False:
            no_setup.append(symbol)

    return {
        "as_of": as_of,
        "universe": universe,
        "evaluated_count": len(items or []),
        "returned_count": returned_count,
        "decision_lane_totals": lane_totals,
        "daily_unavailable": _diagnostic_bucket(daily_unavailable),
        "intraday_60m_unavailable": _diagnostic_bucket(intraday_unavailable),
        "stale_invalid_evidence": _diagnostic_bucket(stale_invalid),
        "no_setup_detected": _diagnostic_bucket(no_setup),
        "invalid_risk_fib": _diagnostic_bucket(invalid_risk_fib),
    }


# Descriptive compatibility alias for callers that prefer the API wording.
project_setup_candidates = project_setup_candidate_list
build_setup_candidate_list = project_setup_candidate_list
build_context = build_peer_context
