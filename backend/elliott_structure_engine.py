"""Conservative, observable Daily Elliott candidate evidence."""

from __future__ import annotations

import math

import pandas as pd


WAVE_STATES = {
    "WAVE_1_ADVANCE",
    "WAVE_2_FORMING",
    "WAVE_2_NEAR_COMPLETION",
    "EARLY_WAVE_3",
    "WAVE_3_CONTINUATION",
    "WAVE_4_CORRECTION",
    "WAVE_5_ADVANCE",
    "UNKNOWN",
}


def _json_value(value):
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        return _json_value(value.item())
    return str(value)


def _close_available(daily_df: pd.DataFrame | None) -> bool:
    return daily_df is not None and "Close" in daily_df and len(daily_df) > 0


def _pct(close: pd.Series, lookback: int):
    if len(close) <= lookback:
        return None
    start, end = float(close.iloc[-lookback - 1]), float(close.iloc[-1])
    if not math.isfinite(start) or start == 0 or not math.isfinite(end):
        return None
    return (end / start - 1.0) * 100.0


def classify_wave_candidate(
    daily_df: pd.DataFrame,
    swing_evidence: dict | None = None,
) -> dict:
    """Return a cautious structural candidate, never an authoritative count."""
    evidence = dict(swing_evidence or {})
    missing = []
    required = ("prior_advance", "confirmed_swing_anchors", "structure_intact")
    for key in required:
        if evidence.get(key) is None:
            missing.append(key)
    if not _close_available(daily_df):
        missing.append("daily_ohlcv")

    evidence_out = _json_value(evidence)
    evidence_out["missing_evidence"] = missing
    result = {
        "timeframe": "daily",
        "state": "UNKNOWN",
        "confidence": "INSUFFICIENT" if missing else "PARTIAL",
        "evidence": evidence_out,
    }
    if evidence.get("structure_intact") is False:
        return result

    close = pd.to_numeric(daily_df["Close"], errors="coerce").dropna()
    if len(close) < 21:
        result["evidence"]["missing_evidence"].append("measurable_daily_structure")
        return result
    recent_10 = _pct(close, 10)
    recent_20 = _pct(close, 20)
    recent_5 = _pct(close, 5)
    # Measure the advance before the most recent pullback/rebound window.
    prior_20 = _pct(close.iloc[:-20], 10) if len(close) > 30 else None
    recent_high = float(close.iloc[-20:-5].max())
    drawdown = (float(close.iloc[-1]) / recent_high - 1.0) * 100.0
    advance = recent_10 is not None and recent_10 > 0 and (prior_20 is None or prior_20 > 0)
    rebound = drawdown <= -3.0 and recent_5 is not None and recent_5 > 0 and (recent_10 or 0) < 0
    pullback = drawdown <= -3.0 and (recent_10 or 0) < 0 and (prior_20 or 0) > 0
    breakout = advance and float(close.iloc[-1]) > float(close.iloc[-21:-1].max())
    result["evidence"].update({
        "daily_advance_10d_pct": round(recent_10, 2) if recent_10 is not None else None,
        "daily_advance_20d_pct": round(recent_20, 2) if recent_20 is not None else None,
        "daily_rebound_5d_pct": round(recent_5, 2) if recent_5 is not None else None,
        "daily_drawdown_from_10d_high_pct": round(drawdown, 2),
        "measurable_advance": advance,
        "measurable_pullback": pullback,
        "measurable_rebound": rebound,
        "measurable_breakout": breakout,
    })

    claimed_state = str(evidence.get("candidate_state") or evidence.get("phase") or "").upper()
    if (
        evidence.get("wave_4_correction")
        or evidence.get("wave_5_advance")
        or claimed_state in {"WAVE_4_CORRECTION", "WAVE_5_ADVANCE"}
    ):
        # V1 cannot distinguish these waves from the measured frame.
        return result

    # Caller labels are retained as review context, but cannot select a state.
    # The observable frame can identify an advance, pullback, or rebound; it
    # cannot objectively distinguish Wave 4 from Wave 2, or Wave 5 from a
    # generic advance, so those marker-only claims remain UNKNOWN.
    if rebound and breakout:
        state = "WAVE_3_CONTINUATION"
    elif rebound:
        state = "EARLY_WAVE_3"
    elif pullback:
        state = "WAVE_2_NEAR_COMPLETION" if evidence.get("fib_zone") else "WAVE_2_FORMING"
    elif advance:
        state = "WAVE_1_ADVANCE"
    else:
        return result
    result["state"] = state
    return result
