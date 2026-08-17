"""Pure, versioned Daily trade-story state classifier for Signalix."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

FRESH_CLOSE_BUFFER_PCT = 0.010
MIN_BREAKOUT_VOLUME_RATIO = 1.20
SETUP_PROXIMITY_PCT = 0.050
SETUP_NEAR_BADGE_PCT = 0.030
RETEST_TOLERANCE_PCT = 0.030
MAX_BREAKOUT_RISK_PCT = 0.040
EXTENDED_FROM_TRIGGER_PCT = 0.080
EXTENDED_RSI = 75.0
BASE_MAX_RANGE_20D_PCT = 12.0
# A qualified base/breakout_setup requires BOTH the Trend Template (>=8) and the
# RS floor. Below either, the name is not in a qualified structure.
RS_FLOOR_DEFAULT = 50.0
# An RSI at/below this is a broken-structure invalidation, not a base/setup.
RSI_INVALIDATION_PCT = 30.0


def canonical_price(value: float | int | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _origin(evidence: dict) -> str:
    met = int(evidence.get("trend_template_conditions") or 0)
    if 4 <= met < 8:
        return "reversal"
    if met >= 8 and float(evidence.get("range_20d_pct") or 999) <= BASE_MAX_RANGE_20D_PCT:
        return "base"
    if met >= 8:
        return "continuation"
    return "unknown"


def _result(primary_state: str, *, origin: str = "unknown", stage: str = "none",
            reference_level=None, failure_level=None, proof_needed: str = "",
            failure_reason=None, distance_badge=None, trend_state=None,
            setup_state=None, lifecycle_state=None, action=None,
            eligibility=None, data_freshness=None) -> dict:
    lifecycle_state = lifecycle_state or ({
        "fresh_breakout": "fresh_breakout", "breakout_extended": "extended_breakout",
        "breakout_retest": "retest", "no_long_setup": "failed_setup_no_event",
        "breakdown_candidate": "failed_setup_no_event",
    }.get(primary_state, "none"))
    trend_state = trend_state or ("trend_pass" if primary_state in
                                  {"trend_pullback", "fresh_breakout", "breakout_extended", "breakout_retest"}
                                  else "trend_partial" if primary_state in {"breakout_setup", "base_forming"}
                                  else "trend_failed")
    setup_state = setup_state or ({
        "trend_pullback": "pullback_holding", "breakout_setup": "pre_breakout",
        "base_forming": "base_forming", "fresh_breakout": "pre_breakout",
        "breakout_extended": "pre_breakout", "breakout_retest": "pre_breakout",
        "breakdown_candidate": "breakdown_candidate", "no_long_setup": "no_long_setup",
    }.get(primary_state, "no_long_setup"))
    action = action or ({
        "fresh_breakout": "VALIDATE_FRESH", "breakout_extended": "DO_NOT_CHASE",
        "breakout_retest": "WAIT_FOR_RETEST", "trend_pullback": "HOLD_IF_SUPPORT_DEFENDS",
        "breakout_setup": "WAIT", "base_forming": "WAIT", "breakdown_candidate": "AVOID_BROKEN_SETUP",
        "no_long_setup": "NO_LONG_SETUP",
    }.get(primary_state, "WAIT"))
    eligibility = eligibility or ("eligible" if primary_state in {"fresh_breakout", "breakout_retest", "trend_pullback"} else "not_eligible")
    return {
        "primary_state": primary_state,
        "origin": origin,
        "stage": stage,
        "reference_level": float(reference_level) if reference_level is not None else None,
        "failure_level": float(failure_level) if failure_level is not None else None,
        "proof_needed": proof_needed,
        "failure_reason": failure_reason,
        "distance_badge": distance_badge,
        "trendState": trend_state, "setupState": setup_state,
        "lifecycleState": lifecycle_state, "action": action,
        "eligibility": eligibility, "dataFreshness": data_freshness or "fresh",
    }


def classify_daily_state(evidence: dict, event: dict | None = None) -> dict:
    """Return exactly one Daily state from same-session deterministic evidence.

    `event`, when supplied, is immutable breakout-event metadata plus its current
    age. It is intentionally separate from rolling trigger evidence.
    """
    close = float(evidence["close"])
    trigger = evidence.get("rolling_trigger")
    trigger = float(trigger) if trigger is not None else None
    volume_ratio = float(evidence.get("volume_ratio_50") or 0)
    rsi = float(evidence.get("rsi_daily") or 0)
    met = int(evidence.get("trend_template_conditions") or 0)

    if event:
        original = float(event["trigger_price"])
        pivot_low = float(event.get("pivot_low") or evidence.get("pre_break_pivot_low") or original)
        failure_level = max(pivot_low, original * (1 - MAX_BREAKOUT_RISK_PCT))
        distance = close / original - 1
        age = int(event.get("age_sessions") or 0)
        if close < failure_level:
            return _result("no_long_setup", origin=event.get("origin") or _origin(evidence),
                           stage="failed", reference_level=original, failure_level=failure_level,
                           proof_needed="Require a new qualified Daily breakout after failure.",
                           failure_reason="false_breakout", lifecycle_state="confirmed_failure",
                           setup_state="no_long_setup", action="AVOID_BROKEN_SETUP", eligibility="not_eligible")
        if distance >= EXTENDED_FROM_TRIGGER_PCT or rsi >= EXTENDED_RSI:
            return _result("breakout_extended", origin=event.get("origin") or _origin(evidence),
                           stage="extended", reference_level=original, failure_level=failure_level,
                           proof_needed="Wait for a new base or controlled reset; do not chase.")
        if age >= 1 and abs(distance) <= RETEST_TOLERANCE_PCT:
            return _result("breakout_retest", origin=event.get("origin") or _origin(evidence),
                           stage="retest", reference_level=original, failure_level=failure_level,
                           proof_needed="Require defended trigger and a 1H higher low.")
        if age <= 2:
            return _result("fresh_breakout", origin=event.get("origin") or _origin(evidence),
                           stage="fresh", reference_level=original, failure_level=failure_level,
                           proof_needed="Hold above trigger or form a 1H higher low.")

    recent_drop = float(evidence.get("change_pct") or 0) <= -5.0
    below_ma50 = evidence.get("above_ma50") is False
    if recent_drop and below_ma50:
        return _result("breakdown_candidate", origin=_origin(evidence), stage="candidate",
                       proof_needed="No persisted breakout event; wait for a new qualified structure.",
                       failure_reason="recent_breakdown", action="AVOID_BROKEN_SETUP",
                       eligibility="not_eligible")
    if trigger is not None and trigger > 0:
        close_buffer = close / trigger - 1
        if close_buffer >= FRESH_CLOSE_BUFFER_PCT and volume_ratio >= MIN_BREAKOUT_VOLUME_RATIO:
            pivot = float(evidence.get("pre_break_pivot_low") or trigger)
            failure_level = max(pivot, trigger * (1 - MAX_BREAKOUT_RISK_PCT))
            return _result("fresh_breakout", origin=_origin(evidence), stage="fresh",
                           reference_level=trigger, failure_level=failure_level,
                           proof_needed="Hold above trigger or form a 1H higher low.")
        if abs(close_buffer) <= SETUP_PROXIMITY_PCT:
            distance = abs(close_buffer)
            badge = "near" if distance <= SETUP_NEAR_BADGE_PCT else "watch"
            reason = "weak_volume_break" if close_buffer >= FRESH_CLOSE_BUFFER_PCT else None
            return _result("breakout_setup", origin=_origin(evidence), stage="pre_break",
                           reference_level=trigger,
                           proof_needed="Require a Daily close at least 1% above trigger with volume ≥1.2×.",
                           failure_reason=reason, distance_badge=badge)

    if met >= 8 and evidence.get("near_pullback_reference"):
        under = evidence.get("pullback_reference") is not None and close < float(evidence["pullback_reference"])
        return _result("trend_pullback", origin="continuation", stage="under_reference" if under else "none",
                       reference_level=evidence.get("pullback_reference"),
                       failure_level=evidence.get("pullback_failure_level"),
                       proof_needed="Require support defense and a 1H higher low.",
                       setup_state="pullback_under_reference" if under else "pullback_holding",
                       action="WAIT_FOR_RETEST" if under else "HOLD_IF_SUPPORT_DEFENDS")
    if float(evidence.get("range_20d_pct") or 999) <= BASE_MAX_RANGE_20D_PCT:
        return _result("base_forming", origin=_origin(evidence), stage="none",
                       proof_needed="Wait for entry into the setup window or a qualified breakout.")
    return _result("no_long_setup", origin=_origin(evidence), stage="none",
                   proof_needed="Wait for a qualified structure.", failure_reason="no_qualified_structure")
