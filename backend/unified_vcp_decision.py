"""Pure compact serving projection for one 60m VCP result."""
from __future__ import annotations

import math


_STRUCTURAL_KEYS = (
    "prior_trend_pass",
    "price_contraction_pass",
    "base_pass",
    "leg_volume_pass",
)
_STATES = {
    "FORMING": "FORMING",
    "READY": "READY",
    "NEAR_TRIGGER": "READY",
    "BREAKOUT_WATCH": "READY",
    "CONFIRMED": "CONFIRMED",
    "EXTENDED": "EXTENDED",
    "FAILED": "INVALIDATED",
}
_DECISIONS = {
    "FORMING": "WAIT",
    "READY": "WAIT",
    "CONFIRMED": "REVIEW",
    "EXTENDED": "WAIT",
    "INVALIDATED": "AVOID",
}


def _number(value):
    try:
        number = float(value) if value is not None else None
        return number if number is None or math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {
            key if isinstance(key, str) else str(key): _json_safe(item)
            for key, item in value.items()
        }
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
    values = [evidence.get(key) for key in _STRUCTURAL_KEYS]
    if any(value is False for value in values):
        return "FAIL"
    if all(value is True for value in values):
        return "PASS"
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
    state = _STATES.get(source.get("state")) if sufficient else None
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
            "daily_context": _json_safe(daily_context) if isinstance(daily_context, dict) else {},
        },
    }
