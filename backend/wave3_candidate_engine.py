"""Conservative Daily Wave-3 candidate detector.

Only ``EARLY_WAVE_3``, ``WAVE_3_CONTINUATION``, and ``NOT_VERIFIABLE`` are
published.  Wave-1/Wave-2 names are evidence anchors, not published counts.
Centred pivots need three right-hand Daily bars, so every result can be replayed
from an as-of prefix without future data.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import mean
from typing import Any

import pandas as pd


POLICY_VERSION = "wave3-confirmed-pivots-v1"
PUBLISHABLE_STATES = {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"}
LEFT_BARS = RIGHT_BARS = 3
MIN_HISTORY = 60
MIN_ADVANCE = 0.08
MIN_LEG_BARS = 5
MIN_RETRACE = 0.236
MAX_RETRACE = 0.786
APPROACH_RATIO = 0.95
FOLLOW_THROUGH_WINDOW = 5
POST_IMPULSE_DRAWDOWN = 0.20


@dataclass(frozen=True)
class Pivot:
    kind: str
    index: int
    confirmed_index: int
    date: str
    price: float


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        return _safe(value.item())
    return str(value)


def _date(value: Any) -> str:
    raw = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return raw[:10]


def frame_to_candles(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    """Convert the production DataFrame shape without manufacturing OHLCV."""
    if frame is None:
        return []
    columns = {str(c).lower(): c for c in frame.columns}
    candles = []
    for position, (index, row) in enumerate(frame.iterrows()):
        stamp = row.get(columns["date"]) if "date" in columns else index
        candles.append({
            "date": _date(stamp),
            "open": row.get(columns.get("open")),
            "high": row.get(columns.get("high")),
            "low": row.get(columns.get("low")),
            "close": row.get(columns.get("close")),
            "volume": row.get(columns.get("volume")),
            "source_index": position,
        })
    return candles


def _blank(reason: str, bars: int = 0, as_of: str | None = None) -> dict:
    return {
        "policy_version": POLICY_VERSION,
        "raw_state": "NOT_VERIFIABLE",
        "published_state": "NOT_VERIFIABLE",
        "confidence": "INSUFFICIENT",
        "as_of": as_of,
        "bars": bars,
        "anchors": {"w1_low": None, "w1_high": None, "w2_low": None,
                    "breakout_confirmation": None, "post_impulse_peak": None},
        "retracement": None,
        "close_vs_wick_confirmation": "NONE",
        "follow_through": {"status": "NONE", "closes_above_w1_high": 0,
                           "window_bars": FOLLOW_THROUGH_WINDOW},
        "evidence": {"timeframe": "Daily", "no_lookahead": True,
                     "state_creator": "ordered confirmed pivots + valid retracement + Daily close"},
        "rejection_reasons": [reason],
    }


def _validate(candles: list[dict]) -> list[dict]:
    if len(candles) < MIN_HISTORY:
        raise ValueError(f"short_history:{len(candles)}<{MIN_HISTORY}")
    last_date = None
    out = []
    for raw in candles:
        if any(raw.get(k) is None for k in ("date", "open", "high", "low", "close", "volume")):
            raise ValueError("missing_daily_ohlcv")
        row = {"date": str(raw["date"]), **{k: float(raw[k]) for k in ("open", "high", "low", "close", "volume")}}
        if not all(math.isfinite(row[k]) for k in ("open", "high", "low", "close", "volume")):
            raise ValueError("non_finite_daily_ohlcv")
        if row["volume"] < 0 or row["low"] > min(row["open"], row["close"], row["high"]) or row["high"] < max(row["open"], row["close"], row["low"]):
            raise ValueError(f"invalid_ohlcv:{row['date']}")
        if last_date is not None and row["date"] <= last_date:
            raise ValueError("dates_not_strictly_increasing")
        last_date = row["date"]
        out.append(row)
    return out


def _pivots(bars: list[dict]) -> list[Pivot]:
    raw = []
    for i in range(LEFT_BARS, len(bars) - RIGHT_BARS):
        window = bars[i - LEFT_BARS:i + RIGHT_BARS + 1]
        highs, lows = [r["high"] for r in window], [r["low"] for r in window]
        if bars[i]["high"] == max(highs) and highs.count(max(highs)) == 1:
            raw.append(Pivot("H", i, i + RIGHT_BARS, bars[i]["date"], bars[i]["high"]))
        if bars[i]["low"] == min(lows) and lows.count(min(lows)) == 1:
            raw.append(Pivot("L", i, i + RIGHT_BARS, bars[i]["date"], bars[i]["low"]))
    raw.sort(key=lambda p: (p.index, p.kind))
    alternating = []
    for pivot in raw:
        if alternating and alternating[-1].kind == pivot.kind:
            better = pivot.price > alternating[-1].price if pivot.kind == "H" else pivot.price < alternating[-1].price
            if better:
                alternating[-1] = pivot
        else:
            alternating.append(pivot)
    return alternating


def _anchor(pivot: Pivot) -> dict:
    return {"date": pivot.date, "price": pivot.price, "index": pivot.index,
            "confirmed_index": pivot.confirmed_index}


def anchor_contradictions(anchors: dict) -> list[str]:
    low, high, w2 = anchors.get("w1_low"), anchors.get("w1_high"), anchors.get("w2_low")
    if not all((low, high, w2)):
        return ["missing_ordered_w1_w2_anchors"]
    reasons = []
    if not low["index"] < high["index"] < w2["index"]:
        reasons.append("anchor_dates_not_strictly_increasing")
    if not low["price"] < w2["price"] < high["price"]:
        reasons.append("invalid_w2_relation_requires_w1_low<w2_low<w1_high")
    return reasons


def _raw(candles: list[dict]) -> dict:
    try:
        bars = _validate(candles)
    except (TypeError, ValueError) as exc:
        return _blank(str(exc), len(candles), candles[-1].get("date") if candles else None)
    sequences = []
    pivots = _pivots(bars)
    for i in range(len(pivots) - 2):
        low, high, w2 = pivots[i:i + 3]
        if (low.kind, high.kind, w2.kind) != ("L", "H", "L"):
            continue
        if not (low.index < high.index < w2.index and low.price < w2.price < high.price):
            continue
        if high.index - low.index < MIN_LEG_BARS or w2.index - high.index < MIN_LEG_BARS:
            continue
        if high.price / low.price - 1 < MIN_ADVANCE:
            continue
        retrace = (high.price - w2.price) / (high.price - low.price)
        if MIN_RETRACE <= retrace <= MAX_RETRACE:
            sequences.append((low, high, w2, retrace))
    if not sequences:
        return _blank("no_valid_ordered_w1_w2_retracement", len(bars), bars[-1]["date"])

    low, high, w2, retrace = sequences[-1]
    anchors = {"w1_low": _anchor(low), "w1_high": _anchor(high), "w2_low": _anchor(w2),
               "breakout_confirmation": None, "post_impulse_peak": None}
    contradictions = anchor_contradictions(anchors)
    if contradictions:
        result = _blank(contradictions[0], len(bars), bars[-1]["date"])
        result["rejection_reasons"] = contradictions
        return result
    breakout_i = next((i for i in range(w2.index + 1, len(bars)) if bars[i]["close"] > high.price), None)
    if breakout_i is not None:
        anchors["breakout_confirmation"] = {"date": bars[breakout_i]["date"], "price": bars[breakout_i]["close"], "index": breakout_i}
        peak_i = max(range(breakout_i, len(bars)), key=lambda i: bars[i]["high"])
        anchors["post_impulse_peak"] = {"date": bars[peak_i]["date"], "price": bars[peak_i]["high"], "index": peak_i}
    else:
        peak_i = None

    last = bars[-1]
    close_above = last["close"] > high.price
    wick_only = last["high"] > high.price >= last["close"]
    recent = bars[max(w2.index + 1, len(bars) - FOLLOW_THROUGH_WINDOW):]
    closes_above = sum(row["close"] > high.price for row in recent)
    follow = breakout_i is not None and close_above and closes_above >= 2
    correction = None
    peak_confirmed = False
    if peak_i is not None:
        peak = anchors["post_impulse_peak"]["price"]
        impulse = peak - w2.price
        correction = (peak - last["close"]) / impulse if impulse > 0 else 0.0
        peak_confirmed = peak_i + RIGHT_BARS < len(bars)
    post_correction = bool(breakout_i is not None and ((peak_confirmed and correction is not None and correction >= POST_IMPULSE_DRAWDOWN) or not close_above))
    reasons = []
    if post_correction:
        state = "NOT_VERIFIABLE"; reasons.append("post_impulse_correction_excluded")
    elif follow:
        state = "WAVE_3_CONTINUATION"
    elif breakout_i is None and last["close"] >= high.price * APPROACH_RATIO:
        state = "EARLY_WAVE_3"; reasons.append("awaiting_sustained_daily_close_confirmation")
    elif breakout_i is not None and close_above:
        state = "EARLY_WAVE_3"; reasons.append("daily_close_break_present_but_follow_through_not_yet_sustained")
    else:
        state = "NOT_VERIFIABLE"; reasons.append("not_approaching_or_holding_above_w1_high")

    ma20, ma50 = mean(r["close"] for r in bars[-20:]), mean(r["close"] for r in bars[-50:])
    prior_volume = mean(r["volume"] for r in bars[-21:-1])
    volume_ratio = last["volume"] / prior_volume if prior_volume else None
    trend_support, volume_support = last["close"] > ma20 > ma50, volume_ratio is not None and volume_ratio > 1
    confidence = "INSUFFICIENT" if state == "NOT_VERIFIABLE" else ("HIGH" if state == "WAVE_3_CONTINUATION" and trend_support and volume_support else "MEDIUM" if trend_support or volume_support or close_above else "LOW")
    return _safe({
        "policy_version": POLICY_VERSION, "raw_state": state, "published_state": state,
        "confidence": confidence, "as_of": last["date"], "bars": len(bars), "anchors": anchors,
        "retracement": round(retrace, 4),
        "close_vs_wick_confirmation": "CLOSE" if close_above else "WICK_ONLY" if wick_only else "NONE",
        "follow_through": {"status": "PASS" if follow else "ABSENT", "closes_above_w1_high": closes_above, "window_bars": FOLLOW_THROUGH_WINDOW},
        "evidence": {"timeframe": "Daily", "no_lookahead": True,
                     "state_creator": "ordered confirmed pivots + valid retracement + Daily close",
                     "ma20": round(ma20, 4), "ma50": round(ma50, 4), "trend_support": trend_support,
                     "volume_ratio_vs_prior_20d": round(volume_ratio, 4) if volume_ratio is not None else None,
                     "volume_support": volume_support, "post_impulse_peak_confirmed": peak_confirmed,
                     "correction_from_post_impulse_peak": round(correction, 4) if correction is not None else None},
        "rejection_reasons": reasons,
    })


def classify_candles(candles: list[dict]) -> dict:
    """Apply adjacent-as-of stability before publishing a candidate."""
    current = _raw(candles)
    previous = _raw(candles[:-1]) if len(candles) > 1 else _blank("no_previous_as_of")
    adjacent = [previous["raw_state"], current["raw_state"]]
    current["evidence"]["adjacent_as_of_raw_states"] = adjacent
    current["evidence"]["hysteresis_rule"] = "same candidate state on two adjacent as-of prefixes"
    if current["raw_state"] not in PUBLISHABLE_STATES or adjacent[0] != adjacent[1]:
        current["published_state"] = "NOT_VERIFIABLE"
        if current["raw_state"] in PUBLISHABLE_STATES and adjacent[0] != adjacent[1]:
            current["rejection_reasons"].append("adjacent_as_of_hysteresis_not_satisfied")
    return _safe(current)


def classify_frame(frame: pd.DataFrame | None) -> dict:
    return classify_candles(frame_to_candles(frame))
