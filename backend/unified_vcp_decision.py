"""Pure compact serving projection for one 60m VCP result."""
from __future__ import annotations

from copy import deepcopy


_STRUCTURAL_KEYS = (
    "prior_trend_pass",
    "price_contraction_pass",
    "base_pass",
    "leg_volume_pass",
)
_DECISIONS = {
    "FORMING": "WAIT",
    "READY": "WAIT",
    "NEAR_TRIGGER": "WAIT",
    "BREAKOUT_WATCH": "WAIT",
    "CONFIRMED": "REVIEW",
    "EXTENDED": "WAIT",
    "FAILED": "AVOID",
}
_EVENT_LANES = {
    "PRICE_VOLUME_BREAKOUT",
    "PIVOT_TOUCH_VOLUME_WATCH",
    "CLOSE_BREAKOUT_VOLUME_PENDING",
}


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _data_is_sufficient(result, override):
    state = result.get("state")
    if state in {"STALE", "NOT_VERIFIED"}:
        return False
    if override is False:
        return False
    data = result.get("data") or {}
    usable = (
        data.get("freshness") == "fresh"
        and data.get("feed_status") in {"ok", "available"}
    )
    return bool(usable and (override is None or override is True))


def _quality(result, sufficient):
    if not sufficient:
        return "UNKNOWN"
    state = result.get("state")
    if state == "FAILED":
        return "FAIL"
    evidence = result.get("evidence") or {}
    if all(evidence.get(key) is True for key in _STRUCTURAL_KEYS):
        return "PASS"
    if result.get("review_lane") in _EVENT_LANES or state == "BREAKOUT_WATCH":
        return "PARTIAL"
    return "PARTIAL"


def project_unified_vcp_decision(
    result: dict,
    daily_context: dict | None = None,
    *,
    data_sufficient: bool | None = None,
) -> dict:
    """Return one JSON-safe serving decision without mutating ``result``."""
    source = result if isinstance(result, dict) else {}
    sufficient = _data_is_sufficient(source, data_sufficient)
    state = source.get("state") if sufficient else None
    price = source.get("price") or {}
    breakout = source.get("breakout") or {}
    evidence = source.get("evidence") or {}
    volume_value = breakout.get("volume_confirmed")
    if volume_value is None and "breakout_volume_pass" in evidence:
        volume_value = evidence.get("breakout_volume_pass")
    volume_confirmation = None if volume_value is None else bool(volume_value)

    return {
        "state": state,
        "decision": _DECISIONS.get(state),
        "quality": _quality(source, sufficient),
        "data_sufficient": sufficient,
        "evidence": {
            "timeframe": "60m",
            "trigger": _number(price.get("pivot_high")),
            "invalidation": _number(price.get("invalidation")),
            "distance_to_trigger_pct": _number(price.get("distance_to_pivot_pct")),
            "volume_confirmation": volume_confirmation,
            "daily_context": deepcopy(daily_context) if isinstance(daily_context, dict) else {},
        },
    }
