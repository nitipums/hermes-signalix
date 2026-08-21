"""
Signalix — Stage-First Daily classifier (canonical, layer-1 = trend structure).

Replaces the three parallel label systems that caused inconsistency:
  1. scanner.trade_readiness.status  (BUY/HOLD/OVERBOUGHT/BREAK/WAIT)
  2. daily_setup_state.classify_daily_state().primary_state
  3. screening.group_scan_results() v2 group names

LAYERING CONTRACT (per owner's architecture rule, 2026-08-17):
  * Layer 1 (STAGE) = pure trend STRUCTURE from price vs MA stacking + slopes.
    NO volume / liquidity / value filtering here. Every symbol is classified;
    quality is a separate downstream concern.
  * Layer 2+ (QUALITY) = MACD / RSI / volume / liquidity. Reported as `quality`
    hints only — they NEVER change the stage or group. They feed take-action
    gating downstream, not entry into the scan.

STAGE (Minervini/Weinstein) from MA stacking:
  S2_uptrend   : price > MA50 > MA150 > MA200, all slopes up (qualified uptrend)
  S1_basing     : below/around MA200, MAs starting to flatten/stack (base building)
  S3_distributing: MA50 cuts below MA150 or MA200, slope turning down (topping)
  S4_down       : price < MA50 < MA150 < MA200 (declining stack)

All inputs already exist in trend_template / trade_readiness — no new data
source. Pure deterministic function, no LLM, no I/O.
"""
from __future__ import annotations

# ---- Versioned constants (no magic numbers in prose) ----
# MA-stacking slope thresholds (% change over 20 sessions).
MA_SLOPE_RISING_PCT = 0.5          # slope >= this = rising (uptrend contribution)
MA_SLOPE_FALLING_PCT = -0.5        # slope <= this = clearly falling (distribution)
BASE_MAX_RANGE_20D_PCT = 12.0      # S1 base if 20d range <= this
EXTENDED_FROM_TRIGGER_PCT = 0.080  # breakout extended if >= this above trigger
EXTENDED_RSI = 75.0                # breakout extended if RSI >= this
RETEST_TOLERANCE_PCT = 0.030       # within this of trigger = retest
MAX_BREAKOUT_RISK_PCT = 0.040      # failure cut below trigger
MIN_BREAKOUT_VOLUME_RATIO = 1.20   # confirmed breakout volume gate
FRESH_CLOSE_BUFFER_PCT = 0.010     # daily close >= trigger * (1+buffer)
SETUP_PROXIMITY_PCT = 0.050        # within this below trigger = setup watch
SETUP_NEAR_BADGE_PCT = 0.030
# Layer-2 quality thresholds (hints only, never gate the stage).
QUALITY_RSI_OVERBOUGHT = 70.0
QUALITY_RSI_OVERSOLD = 30.0
QUALITY_MACD_FLAT_PCT = 0.0        # MACD (MA50-MA150) <= this = momentum stalling


# Human-readable labels (one source of truth for UI).
STAGE_LABELS = {
    "S1_basing": "Stage 1 · Basing",
    "S2_uptrend": "Stage 2 · Uptrend",
    "S3_distributing": "Stage 3 · Distributing",
    "S4_down": "Stage 4 · Down",
}
PHASE_LABELS = {
    "insufficient_history": "Insufficient history",
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


def _stack(evidence: dict):
    """Resolve MA stacking + explicit above-flags from evidence.

    Honors explicit above_ma* flags when present; infers only when absent.
    """
    price = _f(evidence.get("close"))
    ma50 = _f(evidence.get("ma50"))
    ma150 = _f(evidence.get("ma150"))
    ma200 = _f(evidence.get("ma200"))

    def above(flag_key, level):
        if evidence.get(flag_key) is not None:
            return bool(evidence.get(flag_key))
        return level > 0 and price > level

    above_ma50 = above("above_ma50", ma50)
    above_ma150 = above("above_ma150", ma150)
    above_ma200 = above("above_ma200", ma200)
    return price, ma50, ma150, ma200, above_ma50, above_ma150, above_ma200


def _stage_from_trend(evidence: dict) -> str:
    """Minervini/Weinstein stage from MA stacking (price vs MA50/150/200 + slopes)."""
    price, ma50, ma150, ma200, above_ma50, above_ma150, above_ma200 = _stack(evidence)
    s50 = _f(evidence.get("ma50_slope_20d_pct"))
    s150 = _f(evidence.get("ma150_slope_20d_pct"))
    s200 = _f(evidence.get("ma200_slope_20d_pct"))

    # --- Stage 4: declining stack (price below the MAs, MAs stacked downward) ---
    # Price below MA200 AND (MA50 below MA150, or MA50 below MA200) => downtrend.
    if (not above_ma200) and (ma50 and ma150 and ma50 < ma150):
        return "S4_down"
    if not above_ma200 and (ma50 and ma200 and ma50 < ma200):
        return "S4_down"
    # Explicitly below MA200 with clearly falling long MA slope.
    if (not above_ma200) and s200 < MA_SLOPE_FALLING_PCT:
        return "S4_down"
    # Insufficient history for MA200 (thin names): treat as basing, not a crash.
    if ma200 is None or ma200 <= 0:
        return "S1_basing"

    # --- Stage 2: qualified uptrend (full bullish stack, all slopes up) ---
    bullish_stack = above_ma200 and (ma50 >= ma150 >= ma200 if (ma50 and ma150 and ma200) else above_ma50 and above_ma150)
    slopes_up = (s50 >= MA_SLOPE_RISING_PCT and s150 >= MA_SLOPE_RISING_PCT
                 and s200 >= MA_SLOPE_RISING_PCT)
    if bullish_stack and slopes_up:
        return "S2_uptrend"

    # --- Stage 3: distribution / topping (MA50 cuts below slower MAs) ---
    if ma50 and ma150 and ma50 < ma150:
        return "S3_distributing"
    if ma50 and ma200 and ma50 < ma200:
        return "S3_distributing"
    if s50 < MA_SLOPE_FALLING_PCT or s200 < MA_SLOPE_FALLING_PCT:
        return "S3_distributing"

    # --- Stage 1: basing (not a clean uptrend, not a clean decline) ---
    # Price around/above MA200 but slopes not all up, or below but slope flat.
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
        # rolling trigger path (no persisted event): a Daily close through the
        # 20-day trigger is a breakout — volume is a LAYER-2 quality hint, not a
        # stage/phase gate (per owner's architecture rule).
        if trigger and trigger > 0:
            close_buffer = close / trigger - 1
            if close_buffer >= FRESH_CLOSE_BUFFER_PCT:
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


def _quality_hints(evidence: dict) -> dict:
    """Layer-2 quality signals (MACD / RSI / volume). HINTS ONLY — never gate stage."""
    rsi = _f(evidence.get("rsi_daily"))
    macd = evidence.get("macd")
    volume_ratio = _f(evidence.get("volume_ratio_50"))
    flags = []
    if rsi >= QUALITY_RSI_OVERBOUGHT:
        flags.append("overbought")
    if rsi > 0 and rsi <= QUALITY_RSI_OVERSOLD:
        flags.append("oversold")
    if macd is not None and _f(macd) <= QUALITY_MACD_FLAT_PCT:
        flags.append("macd_stalling")
    if volume_ratio > 0 and volume_ratio < 0.5:
        flags.append("low_volume")
    return {
        "rsi_daily": rsi if rsi else None,
        "macd": _f(macd) if macd is not None else None,
        "volume_ratio_50": volume_ratio if volume_ratio else None,
        "flags": flags,
    }


def _primary_state_from_stage_phase(stage: str, phase: str, evidence: dict, event: dict | None) -> str:
    """Deterministic mapping from (stage, phase, event) to one of the 7 P0 states.

    The 7 canonical primary states:
      breakout_setup, fresh_breakout, breakout_retest, breakout_extended,
      trend_pullback, base_forming, no_long_setup

    `breakdown_candidate` from the legacy daily_setup_state contract is unified
    into `no_long_setup` — it is not a contract state.
    """
    if stage == "S2_uptrend":
        if phase == "breakout_extended":
            return "breakout_extended"
        if phase == "uptrend_pullback":
            return "trend_pullback"
        if phase == "waiting_breakout":
            return "breakout_setup"
        if phase == "broken":
            return "no_long_setup"
        if phase == "breakout_new":
            # Distinguish fresh vs retest via event age + distance to trigger.
            if event:
                age = int(event.get("age_sessions") or 0)
                original = _f(event.get("trigger_price")) or _f(evidence.get("rolling_trigger"))
                if original > 0:
                    distance = _f(evidence.get("close")) / original - 1
                    if age >= 1 and abs(distance) <= RETEST_TOLERANCE_PCT:
                        return "breakout_retest"
                    return "fresh_breakout"
            # No event: rolling trigger close-through => fresh_breakout
            return "fresh_breakout"
    if stage == "S1_basing":
        return "base_forming"
    # S3_distributing (topping) or S4_down (declining/broken)
    return "no_long_setup"


def classify_stage(evidence: dict, event: dict | None = None) -> dict:
    """Return one canonical {stage, phase} + layer-2 quality hints.

    `evidence` keys (all produced by trend_template / trade_readiness):
      close, ma50, ma150, ma200, above_ma50, above_ma150, above_ma200,
      ma50_slope_20d_pct, ma150_slope_20d_pct, ma200_slope_20d_pct,
      rolling_trigger, volume_ratio_50, rsi_daily, macd,
      trend_template_conditions, range_20d_pct, near_pullback_reference, vcp,
      plus breakout-event fields via `event`.
    `event`, when supplied, is immutable breakout-event metadata + current age.
    """
    stage = _stage_from_trend(evidence)
    phase = _phase_within_stage(stage, evidence, event)
    primary_state = _primary_state_from_stage_phase(stage, phase, evidence, event)
    labels = {
        "stage": stage,
        "phase": phase,
        "stage_label": STAGE_LABELS.get(stage, stage),
        "phase_label": PHASE_LABELS.get(phase, phase),
        "primary_state": primary_state,
    }
    # Layer-2 quality (hints only).
    labels["quality"] = _quality_hints(evidence)
    # Presentation-only hints (NOT grouping keys).
    labels["readiness_hint"] = evidence.get("readiness_status")  # trade_readiness.status
    labels["data_freshness"] = evidence.get("data_freshness", "fresh")
    if event:
        labels["event_origin"] = event.get("origin")
    return labels
