"""
Signalix — Stage-First Daily classifier (DRAFT for Khim review).

Replaces the three parallel label systems that caused inconsistency:
  1. scanner.trade_readiness.status  (BUY/HOLD/OVERBOUGHT/BREAK/WAIT)
  2. daily_setup_state.classify_daily_state().primary_state
  3. screening.group_scan_results() v2 group names

New contract: ONE classifier returns {stage, phase, evidence}. Stage is the
Minervini/Weinstein primary bucket (trend first). Phase is the actionable
sub-state within the stage. trade_readiness.status is demoted to a hint only.

All inputs already exist in trend_template / trade_readiness — no new data
source. Pure deterministic function, no LLM, no I/O.
"""
from __future__ import annotations

# ---- Versioned constants (no magic numbers in prose) ----
MA200_SLOPE_POSITIVE_PCT = 0.0      # MA200 slope >= this (over lookback) = rising
S3_MA200_SLOPE_FLAT_PCT = -0.5       # between flat and this = distributing watch
BASE_MAX_RANGE_20D_PCT = 12.0        # S1 base if range <= this
EXTENDED_FROM_TRIGGER_PCT = 0.080    # breakout extended if >= this above trigger
EXTENDED_RSI = 75.0                  # breakout extended if RSI >= this
RETEST_TOLERANCE_PCT = 0.030         # within this of trigger = retest
MAX_BREAKOUT_RISK_PCT = 0.040        # failure cut below trigger
MIN_BREAKOUT_VOLUME_RATIO = 1.20     # confirmed breakout volume gate
FRESH_CLOSE_BUFFER_PCT = 0.010       # daily close >= trigger * (1+buffer)
SETUP_PROXIMITY_PCT = 0.050          # within this below trigger = setup watch
SETUP_NEAR_BADGE_PCT = 0.030


# Human-readable labels (one source of truth for UI).
STAGE_LABELS = {
    "S1_basing": "Stage 1 · Basing",
    "S2_uptrend": "Stage 2 · Uptrend",
    "S3_distributing": "Stage 3 · Distributing",
    "S4_down": "Stage 4 · Down",
}
PHASE_LABELS = {
    "base_early": "Base early",
    "base_tight": "Base tight (VCP)",
    "breakout_new": "Breakout new",
    "breakout_extended": "Breakout extended",
    "uptrend_pullback": "Uptrend pullback",
    "waiting_breakout": "Waiting breakout",
    "topping": "Topping",
    "declining": "Declining",
    "broken": "Broken setup",
}


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stage_from_trend(evidence: dict) -> str:
    """Minervini/Weinstein stage from MA structure (price vs MA200 + slope)."""
    price = _f(evidence.get("close"))
    ma200 = _f(evidence.get("ma200"))
    ma200_slope = _f(evidence.get("ma200_slope_20d_pct"))  # % change over lookback
    above_ma200 = bool(evidence.get("above_ma200")) or (ma200 > 0 and price > ma200)

    if above_ma200 and ma200_slope >= MA200_SLOPE_POSITIVE_PCT:
        return "S2_uptrend"
    if above_ma200 and ma200_slope < MA200_SLOPE_POSITIVE_PCT:
        # Still above MA200 but slope flattening/falling -> distributing watch,
        # unless slope is only marginally negative (treat as late S2 until S4).
        if ma200_slope < S3_MA200_SLOPE_FLAT_PCT:
            return "S3_distributing"
        return "S2_uptrend"
    # price <= MA200 (or unknown) -> not in a qualified uptrend
    if ma200_slope < MA200_SLOPE_POSITIVE_PCT:
        return "S4_down"
    return "S1_basing"


def _phase_within_stage(stage: str, evidence: dict, event: dict | None) -> str:
    close = _f(evidence.get("close"))
    trigger = evidence.get("rolling_trigger")
    trigger = _f(trigger) if trigger is not None else None
    volume_ratio = _f(evidence.get("volume_ratio_50"))
    rsi = _f(evidence.get("rsi_daily"))
    met = int(evidence.get("trend_template_conditions") or 0)
    range_20d = _f(evidence.get("range_20d_pct"), 999)
    near_pullback = bool(evidence.get("near_pullback_reference"))
    vcp = bool(evidence.get("vcp"))

    if stage == "S1_basing":
        # base_tight when VCP detected and range already tight; else base_early
        return "base_tight" if (vcp and range_20d <= BASE_MAX_RANGE_20D_PCT) else "base_early"

    if stage == "S2_uptrend":
        if event:
            original = _f(event.get("trigger_price")) or trigger
            if original > 0:
                failure_level = max(_f(event.get("pivot_low")) or original,
                                    original * (1 - MAX_BREAKOUT_RISK_PCT))
                distance = close / original - 1
                age = int(event.get("age_sessions") or 0)
                if close < failure_level:
                    return "broken"
            if distance >= EXTENDED_FROM_TRIGGER_PCT or rsi >= EXTENDED_RSI:
                return "breakout_extended"
            if age >= 1 and abs(distance) <= RETEST_TOLERANCE_PCT:
                return "breakout_new"  # retest
            if age <= 2:
                return "breakout_new"  # fresh
        # rolling trigger path (no persisted event)
        if trigger and trigger > 0:
            close_buffer = close / trigger - 1
            if close_buffer >= FRESH_CLOSE_BUFFER_PCT and volume_ratio >= MIN_BREAKOUT_VOLUME_RATIO:
                return "breakout_new"
            if abs(close_buffer) <= SETUP_PROXIMITY_PCT:
                return "waiting_breakout"
        if met >= 8 and near_pullback:
            return "uptrend_pullback"
        if range_20d <= BASE_MAX_RANGE_20D_PCT:
            return "waiting_breakout"
        return "uptrend_pullback"  # trend intact, no specific trigger -> monitor

    if stage == "S3_distributing":
        return "topping"

    # S4_down
    if event and close < max(_f(event.get("pivot_low")) or _f(event.get("trigger_price")),
                             _f(event.get("trigger_price")) * (1 - MAX_BREAKOUT_RISK_PCT)):
        return "broken"
    return "declining"


def classify_stage(evidence: dict, event: dict | None = None) -> dict:
    """Return exactly one {stage, phase} for a symbol from deterministic evidence.

    `evidence` keys (all already produced by trend_template / trade_readiness):
      close, ma200, ma200_slope_20d_pct, above_ma200, rolling_trigger,
      volume_ratio_50, rsi_daily, trend_template_conditions, range_20d_pct,
      near_pullback_reference, vcp, plus breakout-event fields via `event`.
    `event`, when supplied, is immutable breakout-event metadata + current age.
    """
    stage = _stage_from_trend(evidence)
    phase = _phase_within_stage(stage, evidence, event)
    labels = {
        "stage": stage,
        "phase": phase,
        "stage_label": STAGE_LABELS.get(stage, stage),
        "phase_label": PHASE_LABELS.get(phase, phase),
    }
    # Presentation-only hints (NOT grouping keys).
    readiness_status = evidence.get("readiness_status")  # trade_readiness.status
    labels["readiness_hint"] = readiness_status
    labels["data_freshness"] = evidence.get("data_freshness", "fresh")
    if event:
        labels["event_origin"] = event.get("origin")
    return labels
