"""Pure additive projection of the Daily decision dimensions.

The three dimensions deliberately consume existing serialized Daily evidence;
they do not replace the legacy state, proximity, or action fields.
"""
from __future__ import annotations


def _dimension(state: str, *reason_codes: str, **extra) -> dict:
    result = {"state": state, "reason_codes": list(reason_codes)}
    result.update(extra)
    return result


def _quality(item: dict) -> dict:
    quality = item.get("setup_quality")
    if not isinstance(quality, dict) or "pass" not in quality:
        return _dimension("unknown", "MISSING_SETUP_EVIDENCE")
    reasons = quality.get("reasons") or []
    if any(reason in {"insufficient_history", "missing_data", "unknown"}
           for reason in reasons):
        return _dimension("unknown", "MISSING_SETUP_EVIDENCE")
    return _dimension("pass" if quality.get("pass") is True else "fail",
                      *(str(reason) for reason in reasons))


def _timing(item: dict) -> dict:
    phase = item.get("phase")
    if phase in {"broken", "declining"} or item.get("stage") in {
            "S3_distributing", "S4_down"}:
        return _dimension("invalidated", "SETUP_INVALIDATED")
    proximity = item.get("setup_proximity")
    state = proximity.get("state") if isinstance(proximity, dict) else None
    if state in {"forming", "near_trigger", "action", "extended"}:
        return _dimension(state)
    return _dimension("unknown", "MISSING_EVENT_TIMING")


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _entry_action(item: dict, quality: dict, timing: dict) -> dict:
    queue = item.get("action_queue")
    if quality["state"] == "fail" or timing["state"] == "invalidated":
        return _dimension("avoid", "SETUP_NOT_ACTIONABLE")
    if quality["state"] == "unknown":
        return _dimension("unknown", "MISSING_SETUP_EVIDENCE")
    if timing["state"] == "unknown":
        return _dimension("unknown", "MISSING_EVENT_TIMING")
    if not queue:
        return _dimension("unknown", "MISSING_ENTRY_ACTION")
    if queue == "avoid_new_longs":
        return _dimension("avoid", "AVOID_QUEUE")
    if queue not in {"fresh_breakout", "pre_breakout", "retest_watch",
                     "qualified_pullback"}:
        return _dimension("unknown", "NON_DAILY_ENTRY_QUEUE")
    if queue == "fresh_breakout":
        close = _number(item.get("close"))
        trigger = _number(item.get("breakoutLevel"))
        if (quality["state"] == "pass" and timing["state"] == "action"
                and close is not None and trigger is not None
                and trigger > 0 and close >= trigger):
            return _dimension("confirmed", "TRIGGER_CONFIRMED")
        return _dimension("pending", "TRIGGER_CONFIRMATION_REQUIRED")
    return _dimension("pending", "ENTRY_CONFIRMATION_REQUIRED")


def project_decision_dimensions(item: dict | None) -> dict:
    """Return exactly ``setup_quality``, ``event_timing``, ``entry_action``.

    Unknown and insufficient evidence remains explicit and never becomes a
    positive action. The returned objects are new JSON-safe dictionaries.
    """
    item = item if isinstance(item, dict) else {}
    quality = _quality(item)
    timing = _timing(item)
    return {
        "setup_quality": quality,
        "event_timing": timing,
        "entry_action": _entry_action(item, quality, timing),
    }
