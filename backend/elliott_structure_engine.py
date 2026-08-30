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


def _swing_legs(close: pd.Series) -> list[dict]:
    """Compress monotonic Daily close runs into observable swing legs."""
    values = [float(value) for value in close if math.isfinite(float(value))]
    if len(values) < 2:
        return []
    direction = []
    for left, right in zip(values, values[1:]):
        sign = 1 if right > left else -1 if right < left else 0
        if sign and (not direction or direction[-1] != sign):
            direction.append(sign)
    if not direction:
        return []
    legs = []
    start = 0
    current = 0
    for index in range(1, len(values)):
        sign = 1 if values[index] > values[index - 1] else -1 if values[index] < values[index - 1] else 0
        if not sign:
            continue
        if not current:
            current = sign
            continue
        if sign != current:
            end = index - 1
            legs.append({"direction": current, "start": start, "end": end,
                         "start_price": values[start], "end_price": values[end]})
            start = end
            current = sign
    legs.append({"direction": current, "start": start, "end": len(values) - 1,
                 "start_price": values[start], "end_price": values[-1]})
    return legs


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

    legs = _swing_legs(close)
    directions = [leg["direction"] for leg in legs]
    result["evidence"]["daily_swing_legs"] = [
        {"direction": leg["direction"], "start": leg["start"], "end": leg["end"],
         "start_price": leg["start_price"], "end_price": leg["end_price"]}
        for leg in legs
    ]
    result["evidence"]["measurable_wave_sequence"] = directions
    measured_continuation = (
        directions[-3:] == [1, -1, 1]
        and len(legs) >= 3
        and legs[-2]["start_price"] > 0
        and (legs[-2]["start_price"] - legs[-2]["end_price"]) / legs[-2]["start_price"] >= 0.03
        and legs[-1]["end_price"] > legs[-3]["end_price"]
    )
    result["evidence"]["measurable_continuation"] = measured_continuation

    # These states are only emitted for a measurable alternating sequence.
    # The extra completed impulse leg is the v1 proxy separating Wave 4/5
    # from the first advance/correction/rebound sequence.
    if directions[-5:] == [1, -1, 1, -1, 1]:
        state = "WAVE_5_ADVANCE"
    elif directions[-4:] == [1, -1, 1, -1]:
        state = "WAVE_4_CORRECTION"
    elif measured_continuation:
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
