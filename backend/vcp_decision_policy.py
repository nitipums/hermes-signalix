"""Pure, non-serving Signalix VCP decision projection v2.

This module classifies existing finder evidence only.  It never mutates the
source record and does not replace the live v1 lifecycle or watchlist policy.
"""
from __future__ import annotations

from copy import deepcopy


POLICY_VERSION = "signalix/vcp-decision-shadow-v2"
PROJECTION_MARKER = "signalix/structure-first-candidate-v1"
CANDIDATE_POLICY = "structure_first/volume_not_required_for_candidate"
CORE_STRUCTURE_KEYS = (
    "prior_trend_pass",
    "price_contraction_pass",
    "base_pass",
)
STRUCTURAL_KEYS = (
    "prior_trend_pass",
    "price_contraction_pass",
    "base_pass",
    "leg_volume_pass",
)
FAILURE_CODES = {
    "prior_trend_pass": "PRIOR_TREND_NOT_CONFIRMED",
    "price_contraction_pass": "PRICE_CONTRACTION_NOT_CONFIRMED",
    "base_pass": "BASE_NOT_QUALIFIED",
    "leg_volume_pass": "LEG_VOLUME_NOT_CONTRACTED",
}
EVENT_LANES = {
    "PRICE_VOLUME_BREAKOUT",
    "PIVOT_TOUCH_VOLUME_WATCH",
    "CLOSE_BREAKOUT_VOLUME_PENDING",
}
LANE_RANK = {
    "REVIEW_NOW": 0,
    "PREPARE": 1,
    "EVENT_WATCH": 2,
    "STRUCTURE_WATCH": 2,
    "RESEARCH": 3,
    "DO_NOT_CHASE": 4,
    "DATA_BLOCKED": 5,
}
MIN_AVG_TRADE_VALUE = 10_000_000.0
MIN_PRICE = 0.60


def _float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _quality(result):
    evidence = result.get("evidence") or {}
    passed = [key for key in STRUCTURAL_KEYS if bool(evidence.get(key))]
    failing = [FAILURE_CODES[key] for key in STRUCTURAL_KEYS if not evidence.get(key)]
    return {
        "structural_pass": len(passed) == len(STRUCTURAL_KEYS),
        "structure_pass": all(bool(evidence.get(key)) for key in CORE_STRUCTURE_KEYS),
        "structural_pass_count": len(passed),
        "structural_required_count": len(STRUCTURAL_KEYS),
        "structure_failing_evidence": [FAILURE_CODES[key] for key in CORE_STRUCTURE_KEYS if not evidence.get(key)],
        "failing_evidence": failing,
        "volume_contraction_pass": bool(evidence.get("volume_contraction_pass")),
    }


def _entry(result):
    price = result.get("price") or {}
    breakout = result.get("breakout") or {}
    close = _float(price.get("last_close"))
    pivot = _float(price.get("pivot_high") or breakout.get("pivot_level"))
    invalidation = _float(price.get("invalidation"))
    distance = _float(price.get("distance_to_pivot_pct"))
    coherent = bool(
        close is not None and close > 0 and invalidation is not None
        and 0 < invalidation < close
    )
    close_confirmed = bool(
        breakout.get("close_confirmed") or
        (result.get("evidence") or {}).get("breakout_close_pass")
    )
    volume_confirmed = bool(
        breakout.get("volume_confirmed") or
        (result.get("evidence") or {}).get("breakout_volume_pass")
    )
    near = distance is not None and -5.0 <= distance <= 3.0
    return {
        "last_close": close,
        "pivot": pivot,
        "distance_to_pivot_pct": distance,
        "invalidation": invalidation,
        "invalidation_coherent": coherent,
        "close_confirmed": close_confirmed,
        "volume_confirmed": volume_confirmed,
        "near_pivot": near,
    }


def _tradability(result, entry):
    metrics = (result.get("data") or {}).get("daily_metrics") or {}
    avg_value = _float(metrics.get("avg_trade_value_20"))
    liquidity_pass = avg_value is not None and avg_value >= MIN_AVG_TRADE_VALUE
    marginable_pass = bool((result.get("marginable") or {}).get("is_marginable"))
    price = entry["last_close"]
    price_pass = price is not None and price > MIN_PRICE
    reasons = []
    if not liquidity_pass:
        reasons.append("AVG_TRADE_VALUE_BELOW_10M" if avg_value is not None else "AVG_TRADE_VALUE_NOT_VERIFIED")
    if not marginable_pass:
        reasons.append("NOT_MARGINABLE")
    if not price_pass:
        reasons.append("PRICE_AT_OR_BELOW_0_60" if price is not None else "PRICE_NOT_VERIFIED")
    return {
        "avg_trade_value_20": avg_value,
        "liquidity_pass": liquidity_pass,
        "marginable_pass": marginable_pass,
        "price_pass": price_pass,
        "passes_default_filters": liquidity_pass and marginable_pass and price_pass,
        "reason_codes": reasons,
    }


def _usable_data(result):
    state = result.get("state")
    data = result.get("data") or {}
    return bool(
        state not in {"STALE", "NOT_VERIFIED"}
        and data.get("freshness") == "fresh"
        and data.get("feed_status") != "unavailable"
    )


def _event_evidence(result):
    return bool(
        result.get("review_lane") in EVENT_LANES
        or result.get("daily_context_watch")
        or result.get("insurance_context_watch")
    )


def _context(result):
    trend = result.get("trend") or {}
    fundamental = result.get("fundamental")
    if fundamental is None:
        fundamental = result.get("fundamentals")
    return {
        "daily_trend_pass": bool(trend.get("daily_context_pass")),
        "daily_context": deepcopy(trend.get("daily_context") or {}),
        "fundamental": deepcopy(fundamental) if fundamental is not None else None,
        "context_promotes_lifecycle": False,
    }


def _lane(result, quality, entry):
    state = result.get("state") or "NOT_VERIFIED"
    reasons = []
    if state in {"STALE", "NOT_VERIFIED"} or not _usable_data(result):
        return "DATA_BLOCKED", "NO_ACTION", ["DATA_NOT_USABLE"]
    if state == "FAILED":
        return "DO_NOT_CHASE", "NO_ACTION", ["STRUCTURE_INVALIDATED"]
    if state == "EXTENDED" or result.get("late_watch") is True:
        return "DO_NOT_CHASE", "NO_ACTION", ["EXTENDED_OR_LATE"]
    if not entry["invalidation_coherent"]:
        reasons.append("INVALIDATION_NOT_COHERENT")

    confirmed = entry["close_confirmed"] and entry["volume_confirmed"]
    eligible_state = state in {"READY", "NEAR_TRIGGER", "CONFIRMED"}
    entry_ready = confirmed or (state in {"READY", "NEAR_TRIGGER"} and entry["near_pivot"])
    if quality["structural_pass"] and entry["invalidation_coherent"] and eligible_state and entry_ready:
        reasons.append("STRUCTURE_AND_ENTRY_REVIEWABLE")
        return "REVIEW_NOW", "ACTIONABLE_REVIEW", reasons

    if quality["structure_pass"] and entry["invalidation_coherent"] and eligible_state:
        reasons.append("STRUCTURE_CANDIDATE_VOLUME_PENDING")
        return "STRUCTURE_WATCH", "WATCH_ONLY", reasons

    if _event_evidence(result):
        if not quality["structural_pass"]:
            reasons.append("STRUCTURE_INCOMPLETE")
        reasons.append("EVENT_EVIDENCE_ONLY")
        return "EVENT_WATCH", "WATCH_ONLY", reasons

    if entry["invalidation_coherent"] and quality["structural_pass_count"] >= 3:
        reasons.append("CONFIRMATION_PENDING")
        return "PREPARE", "WATCH_ONLY", reasons

    reasons.append("RESEARCH_ONLY")
    return "RESEARCH", "NO_ACTION", reasons


def _sort_fields(result, lane, quality, entry, tradability):
    state = result.get("state")
    confirmation_score = 3 if (entry["close_confirmed"] and entry["volume_confirmed"]) else (
        2 if state == "NEAR_TRIGGER" else 1 if state == "READY" else 0
    )
    diagnostics = (result.get("pattern") or {}).get("sequence_diagnostics") or {}
    age = _float(diagnostics.get("v2_final_pivot_age_hours"))
    age_key = age if age is not None else 1_000_000.0
    liquidity = tradability["avg_trade_value_20"] or 0.0
    key = [
        LANE_RANK[lane],
        -confirmation_score,
        -quality["structural_pass_count"],
        age_key,
        -liquidity,
        str(result.get("symbol") or ""),
    ]
    return {
        "key": key,
        "entry_confirmation_score": confirmation_score,
        "sequence_age_hours": age,
        "uses_authoritative_rr": False,
    }


def project_vcp_decision_shadow(result: dict) -> dict:
    """Project one finder result into a single non-serving v2 decision lane."""
    source = result if isinstance(result, dict) else {}
    quality = _quality(source)
    entry = _entry(source)
    tradability = _tradability(source, entry)
    lane, actionability, reasons = _lane(source, quality, entry)
    return {
        "policy_version": POLICY_VERSION,
        "projection_marker": PROJECTION_MARKER,
        "candidate_policy": CANDIDATE_POLICY,
        "symbol": source.get("symbol"),
        "lifecycle_state": source.get("state") or "NOT_VERIFIED",
        "decision_lane": lane,
        "actionability": actionability,
        "quality": quality,
        "entry": entry,
        "tradability": tradability,
        "context": _context(source),
        "reason_codes": reasons,
        "sort": _sort_fields(source, lane, quality, entry, tradability),
    }
