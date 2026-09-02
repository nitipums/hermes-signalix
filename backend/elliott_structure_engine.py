"""Production Elliott engine — Variant C + Dual-Degree (AWC lock 2026-08-31).

Variant C: Enhanced Swing 5%/5bars volume-weighted + 5-day hysteresis.

Question: Does adding volume-weighted swing strength + strict Early definition
improve discrimination vs current 5%/5bars baseline?

Approach C = refined current:
  - Swing filter: >=5% move AND >=5 bars (same as current)
  - NEW: volume-weighted swing strength — advance (up) legs require avg volume
    during leg > 20-day avg volume (advance volume > avg). Pullback legs exempt.
    Weak-volume up legs de-weighted (flagged, not counted as significant unless
    volume confirms). Falls back to price-only if no Volume column.
  - Hysteresis: 5-day persistence (already in current) — WAVE_1 kept MEDIUM for
    up to 5 days after last WAVE_1 if measurable_advance + holds above low.
  - Early Wave 3: High >= 0.98*WH AND (close within 2% OR volume > 20d avg)
    (strict 0.98/2% threshold). Identical to current tightened rule.

Throwaway prototype — no DB writes, no side effects.
Mirrors elliott_structure_engine.classify_wave_candidate API.
"""

from __future__ import annotations

import math
import pandas as pd

from wave3_candidate_engine import classify_frame as classify_wave3_candidate

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

VARIANT = "C_enhanced_swing_volume_hysteresis"
SWING_PCT = 0.05
SWING_BARS = 5
HYSTERESIS_WINDOW = 5
NEAR_HIGH_THR = 0.98  # High >= 0.98 * WH
CLOSE_THR = 0.98      # Close >= 0.98*WH or >=0.98*High

# Dual-degree (AWC lock): Large 5%/5bars vs Small 3%/2bars inside large Wave3 window
# Large degree controls state; small degree is evidence-only (does not alter state).
LARGE_SWING_PCT = SWING_PCT
LARGE_SWING_BARS = SWING_BARS
SMALL_SWING_PCT = 0.03
SMALL_SWING_BARS = 2
DUAL_DEGREE_WINDOW_BARS = 60  # fallback window when no wave1

# ---------------------------------------------------------------------------
# helpers (copied from engine, annotated)
# ---------------------------------------------------------------------------

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


def _valid_ohlc(daily_df: pd.DataFrame | None) -> bool:
    """Return whether the complete Daily OHLC input is usable for pivots."""
    def positive_finite(value) -> bool:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return False
        return math.isfinite(numeric) and numeric > 0

    required = ("Open", "High", "Low", "Close")
    if daily_df is None or len(daily_df) == 0 or not all(column in daily_df for column in required):
        return False
    if any(len(daily_df[column]) != len(daily_df) or not daily_df[column].index.equals(daily_df.index)
           for column in required):
        return False
    values = daily_df[list(required)].apply(pd.to_numeric, errors="coerce")
    if not values.apply(lambda column: column.map(positive_finite)).all().all():
        return False
    return bool(
        ((values["High"] >= values[["Open", "Close"]].max(axis=1)) &
         (values["Low"] <= values[["Open", "Close"]].min(axis=1)) &
         (values["High"] >= values["Low"])).all()
    )


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


def _swing_legs_ohlc(daily_df: pd.DataFrame, pct: float = 0.05, min_bars: int = 5) -> list[dict]:
    """Large-degree swing legs using Low for bottoms and High for tops (not Close).

    Direction is derived from Close monotonic runs (same segmentation as _swing_legs),
    but pivot prices are replaced with actual OHLC extremes:
      - up leg: start = min(Low) in segment, end = max(High) in segment
      - down leg: start = max(High) in segment, end = min(Low) in segment
    Invalid or incomplete OHLC returns no legs. Filter 5%/5bars on extreme prices.
    """
    try:
        if not _valid_ohlc(daily_df):
            return []
        close = pd.to_numeric(daily_df["Close"], errors="coerce")
        if len(close) < 2:
            return []
        high = pd.to_numeric(daily_df["High"], errors="coerce")
        low = pd.to_numeric(daily_df["Low"], errors="coerce")
        values = [float(v) for v in close if math.isfinite(float(v))]
        if len(values) < 2:
            return []
        # same segmentation on close
        legs_idx: list[tuple[int,int,int]] = []  # direction, start, end
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
                legs_idx.append((current, start, end))
                start = end
                current = sign
        legs_idx.append((current, start, len(values) - 1))
        # replace prices with pivot extremes (Low at bottoms, High at tops)
        legs: list[dict] = []
        for direction, s, e in legs_idx:
            try:
                if direction == 1:
                    # up: Low at start bar, High at end bar
                    sp = float(low.iloc[s])
                    ep = float(high.iloc[e])
                    start_price = sp
                    end_price = ep
                else:
                    sp = float(high.iloc[s])
                    ep = float(low.iloc[e])
                    start_price = sp
                    end_price = ep
            except Exception:
                return []
            legs.append({"direction": direction, "start": s, "end": e,
                         "start_price": start_price, "end_price": end_price})
        # filter by pct/bars on extremes
        sig: list[dict] = []
        for leg in legs:
            move = abs(leg["end_price"] - leg["start_price"]) / max(abs(leg["start_price"]), 1e-9)
            bars = leg["end"] - leg["start"]
            if move >= pct and bars >= min_bars:
                sig.append(leg)
        if not sig:
            return []
        # merge same direction after filtering
        merged = [dict(sig[0])]
        for leg in sig[1:]:
            if leg["direction"] == merged[-1]["direction"]:
                merged[-1]["end"] = leg["end"]
                merged[-1]["end_price"] = leg["end_price"]
                # keep start_price as lowest low / highest high of merged window
                # for up legs, start_price should remain min(Low) of combined window
                # recompute from daily_df for accuracy
                try:
                    s = merged[-1]["start"]; e = merged[-1]["end"]
                    if leg["direction"] == 1:
                        merged[-1]["start_price"] = float(low.iloc[s])
                        merged[-1]["end_price"] = float(high.iloc[e])
                    else:
                        merged[-1]["start_price"] = float(high.iloc[s])
                        merged[-1]["end_price"] = float(low.iloc[e])
                except Exception:
                    return []
            else:
                merged.append(dict(leg))
        return merged
    except Exception:
        return []


def _best_wave1_anchor(daily_df: pd.DataFrame, ohlc_legs: list[dict], pct: float = 0.05, min_bars: int = 5) -> dict | None:
    """Find lowest Low in last 120 bars that yields >=pct advance to a subsequent High.

    Scans candidates sorted by Low ascending, picks first that has a qualifying up leg after it.
    Returns synthetic wave1 dict with Low/High extremes.
    """
    try:
        if daily_df is None or "Low" not in daily_df or "High" not in daily_df:
            return None
        n = len(daily_df)
        if n < 5:
            return None
        window = min(n, 180)
        start = n - window
        low = pd.to_numeric(daily_df["Low"], errors="coerce")
        high = pd.to_numeric(daily_df["High"], errors="coerce")
        # candidate indices sorted by Low price ascending
        win_low = low.iloc[start:]
        # get sorted order
        sorted_idx = win_low.sort_values().index
        # need positional mapping: low.index is Date index, not positional; use iloc positions
        # Build list of (pos, price)
        candidates: list[tuple[int,float]] = []
        for pos in range(start, n):
            try:
                v = float(low.iloc[pos])
                if math.isfinite(v):
                    candidates.append((pos, v))
            except Exception:
                continue
        candidates.sort(key=lambda x: x[1])
        for cand_pos, cand_price in candidates:
            # find first up leg after cand_pos
            for leg in ohlc_legs:
                if leg["direction"] != 1:
                    continue
                if leg["end"] <= cand_pos:
                    continue
                # leg must start at or after cand_pos (or overlap)
                # Effective start is cand_pos, effective end is leg["end"]
                eff_start = cand_pos
                eff_end = int(leg["end"])
                eff_high = float(leg["end_price"])
                # if leg starts after cand, high is still leg high, low is cand_price (more extreme)
                # check bars and pct from cand_price to eff_high
                bars = eff_end - eff_start
                if bars < min_bars:
                    continue
                pct_move = (eff_high - cand_price) / cand_price if cand_price else 0
                if pct_move < pct:
                    continue
                # qualifies — return synthetic anchor
                # also compute actual High as max High between cand and leg end
                try:
                    seg_high = high.iloc[eff_start:eff_end+1].dropna()
                    if len(seg_high):
                        eff_high = float(seg_high.max())
                        # find its position
                        eff_end = int(high.iloc[eff_start:eff_end+1].idxmax() is not None and daily_df.index.get_loc(high.iloc[eff_start:eff_end+1].idxmax())) if hasattr(high.iloc[eff_start:eff_end+1], 'idxmax') else eff_end
                        # fallback to leg end if mapping fails
                        if not isinstance(eff_end, int):
                            eff_end = int(leg["end"])
                except Exception:
                    pass
                return {
                    "wave1_low": float(cand_price),
                    "wave1_start_idx": int(eff_start),
                    "wave1_high": float(eff_high),
                    "wave1_end_idx": int(eff_end),
                    "anchor_leg": leg,
                }
        return None
    except Exception:
        return None


def _enforce_wave2_gt_wave1(daily_df: pd.DataFrame, w1: dict, ohlc_legs: list[dict]) -> dict:
    """Strict rule Wave2 low > Wave1 low. If violated, re-anchor Wave1 to lower low via best anchor.

    Mutates w1 in place and returns it. Loops at most 3 times.
    """
    try:
        if daily_df is None or "Low" not in daily_df or w1.get("wave1_low") is None or w1.get("wave1_end_idx") is None:
            return w1
        low = pd.to_numeric(daily_df["Low"], errors="coerce")
        high = pd.to_numeric(daily_df["High"], errors="coerce")
        n = len(daily_df)
        for _ in range(3):
            wave1_low = w1.get("wave1_low")
            wave1_end = w1.get("wave1_end_idx")
            if wave1_low is None or wave1_end is None or wave1_end + 1 >= n:
                break
            # actual pullback low = min Low after wave1_end
            post_low = low.iloc[wave1_end+1:]
            if post_low.dropna().empty:
                break
            # need positional
            post_vals = low.values[wave1_end+1:]
            # find min not nan
            valid = [(i, v) for i, v in enumerate(post_vals) if math.isfinite(float(v))]
            if not valid:
                break
            min_rel, min_val = min(valid, key=lambda x: x[1])
            actual_low = float(min_val)
            actual_idx = wave1_end + 1 + min_rel
            # update pullback metrics to actual Low extremes
            w1["pullback_low"] = actual_low
            w1["pullback_high"] = float(w1.get("wave1_high")) if w1.get("wave1_high") is not None else None
            # duration
            try:
                w1["pullback_duration_days"] = int(actual_idx - int(wave1_end))
            except Exception:
                pass
            # retracement
            try:
                rng = w1["wave1_high"] - w1["wave1_low"] if w1.get("wave1_high") is not None else None
                if rng and rng > 0 and w1.get("pullback_high") is not None:
                    w1["retracement_pct"] = round(float(w1["pullback_high"] - actual_low) / rng * 100, 2)
            except Exception:
                pass
            # strict holds check on actual Low vs Wave1 Low
            if actual_low > wave1_low:
                w1["holds_above_wave1_low"] = True
                break
            # violation: actual_low <= wave1_low
            w1["holds_above_wave1_low"] = False
            # re-anchor to best anchor (lowest Low yielding advance)
            anchored = _best_wave1_anchor(daily_df, ohlc_legs, pct=LARGE_SWING_PCT, min_bars=LARGE_SWING_BARS)
            if anchored is None:
                break
            # if anchored already equals current, can't fix further
            if abs(anchored["wave1_low"] - wave1_low) < 1e-9 and anchored["wave1_start_idx"] == wave1_end:
                break
            # adopt anchored wave1
            w1["wave1_low"] = anchored["wave1_low"]
            w1["wave1_start_idx"] = anchored["wave1_start_idx"]
            w1["wave1_high"] = anchored["wave1_high"]
            w1["wave1_end_idx"] = anchored["wave1_end_idx"]
            # recompute holds loop will re-evaluate
            continue
        return w1
    except Exception:
        return w1


def _volume_for_leg(daily_df: pd.DataFrame, start: int, end: int) -> float | None:
    """Avg volume over leg window (inclusive). Requires Volume column."""
    if daily_df is None or "Volume" not in daily_df:
        return None
    try:
        vol = pd.to_numeric(daily_df["Volume"], errors="coerce")
        # slice by positional index (daily_df is date-asc)
        window = vol.iloc[start:end + 1].dropna()
        if len(window) == 0:
            return None
        v = float(window.mean())
        return v if math.isfinite(v) else None
    except Exception:
        return None


def _avg20_volume(daily_df: pd.DataFrame) -> float | None:
    if daily_df is None or "Volume" not in daily_df:
        return None
    try:
        vol = pd.to_numeric(daily_df["Volume"], errors="coerce").dropna()
        if len(vol) < 2:
            return None
        if len(vol) > 21:
            avg20 = float(vol.iloc[-21:-1].mean())
        else:
            avg20 = float(vol.iloc[:-1].mean())
        return avg20 if math.isfinite(avg20) and avg20 > 0 else None
    except Exception:
        return None


def _wave1_metrics(close: pd.Series, legs: list[dict]) -> dict:
    out: dict = {
        "wave1_high": None, "wave1_low": None, "wave1_start_idx": None, "wave1_end_idx": None,
        "pullback_low": None, "pullback_high": None, "pullback_duration_days": None,
        "retracement_pct": None, "holds_above_wave1_low": None,
        "close_above_wave1_high": None, "tested_high_only": None,
    }
    if not legs:
        return out
    values = [float(v) for v in close if math.isfinite(float(v))]
    if not values:
        return out
    directions = [l["direction"] for l in legs]
    wave1_idx = None
    pullback_idx = None
    if len(legs) >= 2 and directions[-1] == -1 and directions[-2] == 1:
        wave1_idx = len(legs) - 2
        pullback_idx = len(legs) - 1
    elif len(legs) >= 1 and directions[-1] == 1:
        if len(legs) >= 3 and directions[-3:] == [1, -1, 1]:
            wave1_idx = len(legs) - 3
            pullback_idx = len(legs) - 2
        else:
            wave1_idx = len(legs) - 1
    elif len(legs) >= 1 and directions[-1] == -1:
        for i in range(len(legs) - 2, -1, -1):
            if legs[i]["direction"] == 1:
                wave1_idx = i
                pullback_idx = len(legs) - 1
                break
    if wave1_idx is None:
        for i, l in enumerate(legs):
            if l["direction"] == 1:
                wave1_idx = i
        if wave1_idx is None:
            return out
    wave1 = legs[wave1_idx]
    out["wave1_high"] = float(wave1["end_price"])
    out["wave1_low"] = float(wave1["start_price"])
    out["wave1_start_idx"] = int(wave1["start"])
    out["wave1_end_idx"] = int(wave1["end"])
    wave1_range = out["wave1_high"] - out["wave1_low"]
    if pullback_idx is not None and pullback_idx < len(legs) and legs[pullback_idx]["direction"] == -1:
        pb = legs[pullback_idx]
        out["pullback_high"] = float(pb["start_price"])
        out["pullback_low"] = float(pb["end_price"])
        out["pullback_duration_days"] = int(pb["end"] - pb["start"])
        if wave1_range and wave1_range > 0:
            retrace = (out["pullback_high"] - out["pullback_low"]) / wave1_range
            out["retracement_pct"] = round(float(retrace) * 100.0, 2)
        out["holds_above_wave1_low"] = bool(out["pullback_low"] is not None and out["pullback_low"] > out["wave1_low"])
    last_close = float(values[-1])
    out["close_above_wave1_high"] = bool(last_close > out["wave1_high"]) if out["wave1_high"] is not None else None
    return out


def _wave1_hysteresis_check(daily_df: pd.DataFrame, swing_evidence: dict | None, *, _disable: bool = False) -> bool:
    if _disable or daily_df is None or len(daily_df) < 24:
        return False
    for offset in (1, 2, 3, 4, 5):
        if len(daily_df) <= 21 + offset:
            continue
        truncated = daily_df.iloc[:-offset]
        try:
            res = classify_wave_candidate(truncated, swing_evidence, _hysteresis_disable=True)
        except Exception:
            continue
        if res.get("state") == "WAVE_1_ADVANCE" and res.get("confidence") in ("MEDIUM", "HIGH"):
            return True
    return False

def _compute_small_degree(
    close: pd.Series,
    wave1_metrics: dict,
    daily_df: pd.DataFrame | None = None,
) -> dict:
    """Compute small degree (1),(2),(3) as 3%/2bars inside large Wave3 window.

    Day-only. Large degree is authoritative; small degree is evidence-only and
    never alters large state. Exposed as small_wave_legs / small_wave_labels.
    Window: from large wave1_start_idx to end of series (fallback last 60 bars).
    """
    try:
        n = len(close)
        if n < 5:
            return {"small_wave_legs": [], "small_wave_labels": [], "small_legs": [], "small_waves": [], "small_degree_window": None, "small_degree_source": "Daily 3%/2bars"}
        wave1_start = wave1_metrics.get("wave1_start_idx") if isinstance(wave1_metrics, dict) else None
        if wave1_start is not None and isinstance(wave1_start, int) and 0 <= wave1_start < n:
            win_start = int(wave1_start)
        else:
            win_start = max(0, n - DUAL_DEGREE_WINDOW_BARS)
        window_close = close.iloc[win_start:]
        if len(window_close) < 3:
            return {"small_wave_legs": [], "small_wave_labels": [], "small_legs": [], "small_waves": [], "small_degree_window": [win_start, n - 1], "small_degree_source": "Daily 3%/2bars"}
        raw = _swing_legs(window_close)
        small = []
        for leg in raw:
            move = abs(leg["end_price"] - leg["start_price"]) / max(abs(leg["start_price"]), 1e-9)
            bars = leg["end"] - leg["start"]
            if move >= SMALL_SWING_PCT and bars >= SMALL_SWING_BARS:
                adj = dict(leg)
                adj["start"] = int(leg["start"] + win_start)
                adj["end"] = int(leg["end"] + win_start)
                adj["pct"] = round(move * 100, 2)
                adj["bars"] = int(bars)
                small.append(adj)
        if len(small) >= 2:
            merged = [dict(small[0])]
            for leg in small[1:]:
                if leg["direction"] == merged[-1]["direction"]:
                    merged[-1]["end"] = leg["end"]
                    merged[-1]["end_price"] = leg["end_price"]
                    merged[-1]["bars"] = int(merged[-1]["end"] - merged[-1]["start"])
                    try:
                        merged[-1]["pct"] = round(abs(merged[-1]["end_price"] - merged[-1]["start_price"]) / max(abs(merged[-1]["start_price"]), 1e-9) * 100, 2)
                    except Exception:
                        pass
                else:
                    merged.append(dict(leg))
            small = merged
        labels = [f"({i+1})" for i in range(len(small))]
        annotated = []
        for i, leg in enumerate(small):
            try:
                annotated.append({"label": f"({i+1})", "direction": int(leg["direction"]), "start": int(leg["start"]), "end": int(leg["end"]), "start_price": float(leg["start_price"]), "end_price": float(leg["end_price"])})
            except Exception:
                annotated.append({"label": f"({i+1})"})
        return {
            "small_wave_legs": small,
            "small_wave_labels": labels,
            "small_legs": small,
            "small_waves": annotated,
            "small_degree_window": [int(win_start), int(n - 1)],
            "small_degree_source": "Daily 3%/2bars",
            "small_degree_window_bars": int(n - win_start),
        }
    except Exception as e:
        return {"small_wave_legs": [], "small_wave_labels": [], "small_legs": [], "small_waves": [], "small_degree_window": None, "small_degree_source": f"error:{e}"}


def classify_wave_candidate(
    daily_df: pd.DataFrame,
    swing_evidence: dict | None = None,
    _hysteresis_disable: bool = False,
) -> dict:
    """Variant C classifier — same API as elliott_structure_engine.classify_wave_candidate."""
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
        "variant": VARIANT,
    }
    structure_failed = evidence.get("structure_intact") is False
    if structure_failed and _hysteresis_disable:
        result["evidence"]["small_wave_legs"] = []
        result["evidence"]["small_wave_labels"] = []
        result["evidence"]["small_legs"] = []
        result["evidence"]["small_waves"] = []
        result["evidence"]["dual_degree"] = {"large": {"pct": LARGE_SWING_PCT, "bars": LARGE_SWING_BARS, "label": "1,2,3"}, "small": {"pct": SMALL_SWING_PCT, "bars": SMALL_SWING_BARS, "label": "(1),(2),(3)"}}
        return result
    if not _close_available(daily_df) or not _valid_ohlc(daily_df):
        if _close_available(daily_df) and "daily_ohlcv" not in missing:
            missing.append("daily_ohlcv")
        result["evidence"]["variant"] = VARIANT
        result["evidence"]["small_wave_legs"] = []
        result["evidence"]["small_wave_labels"] = []
        result["evidence"]["small_legs"] = []
        result["evidence"]["small_waves"] = []
        result["evidence"]["dual_degree"] = {"large": {"pct": LARGE_SWING_PCT, "bars": LARGE_SWING_BARS, "label": "1,2,3"}, "small": {"pct": SMALL_SWING_PCT, "bars": SMALL_SWING_BARS, "label": "(1),(2),(3)"}}
        return result

    close = pd.to_numeric(daily_df["Close"], errors="coerce")
    if len(close) < 21:
        result["evidence"]["missing_evidence"].append("measurable_daily_structure")
        result["evidence"]["variant"] = VARIANT
        result["evidence"]["small_wave_legs"] = []
        result["evidence"]["small_wave_labels"] = []
        result["evidence"]["small_legs"] = []
        result["evidence"]["small_waves"] = []
        result["evidence"]["dual_degree"] = {"large": {"pct": LARGE_SWING_PCT, "bars": LARGE_SWING_BARS, "label": "1,2,3"}, "small": {"pct": SMALL_SWING_PCT, "bars": SMALL_SWING_BARS, "label": "(1),(2),(3)"}}
        return result

    high_series = None
    if "High" in daily_df:
        high_series = pd.to_numeric(daily_df["High"], errors="coerce").dropna()

    recent_10 = _pct(close, 10)
    recent_20 = _pct(close, 20)
    recent_5 = _pct(close, 5)
    prior_20 = _pct(close.iloc[:-20], 10) if len(close) > 30 else None
    recent_high = float(close.iloc[-20:-5].max())
    drawdown = (float(close.iloc[-1]) / recent_high - 1.0) * 100.0
    advance = recent_10 is not None and recent_10 > 0 and (prior_20 is None or prior_20 > 0)
    rebound = drawdown <= -3.0 and recent_5 is not None and recent_5 > 0 and (recent_10 or 0) < 0
    pullback = drawdown <= -3.0 and (recent_10 or 0) < 0 and (prior_20 or 0) > 0
    breakout_close = advance and float(close.iloc[-1]) > float(close.iloc[-21:-1].max())

    # --- Large degree: OHLC extremes (Low for bottoms, High for tops) ---
    # Use OHLC swing legs only when the complete Daily OHLC input is valid.
    legs_close = _swing_legs(close)
    directions_close = [leg["direction"] for leg in legs_close]
    has_ohlc = _valid_ohlc(daily_df)
    ohlc_legs_raw = _swing_legs_ohlc(daily_df, pct=SWING_PCT, min_bars=SWING_BARS) if has_ohlc else []
    legs = ohlc_legs_raw
    directions = [leg["direction"] for leg in legs]
    result["evidence"]["daily_swing_legs"] = [
        {"direction": leg["direction"], "start": leg["start"], "end": leg["end"],
         "start_price": leg["start_price"], "end_price": leg["end_price"]}
        for leg in legs
    ]
    result["evidence"]["daily_swing_legs_close"] = [
        {"direction": leg["direction"], "start": leg["start"], "end": leg["end"],
         "start_price": leg["start_price"], "end_price": leg["end_price"]}
        for leg in legs_close
    ]
    result["evidence"]["measurable_wave_sequence"] = directions
    result["evidence"]["measurable_wave_sequence_close"] = directions_close
    if has_ohlc:
        result["evidence"]["ohlc_swing_legs"] = legs
    if has_ohlc and ohlc_legs_raw:
        base_sig = legs
    else:
        base_sig = [l for l in legs if abs(l["end_price"] - l["start_price"]) / max(l["start_price"], 1e-9) >= SWING_PCT and (l["end"] - l["start"]) >= SWING_BARS]

    # Volume-weighted refinement: up legs require avg leg volume > 20d avg
    avg20 = _avg20_volume(daily_df)
    sig_legs: list[dict] = []
    volume_weighted_flags: list[dict] = []
    for leg in base_sig:
        enriched = dict(leg)
        leg_avg = _volume_for_leg(daily_df, leg["start"], leg["end"])
        enriched["avg_volume"] = round(leg_avg, 2) if leg_avg is not None else None
        enriched["volume_above_avg20"] = bool(leg_avg is not None and avg20 is not None and leg_avg > avg20) if leg_avg is not None else None
        # For up legs (advance), require volume confirmation if volume data present
        # Soft threshold: leg_avg > 0.95*avg20 keeps (avoids filtering single monotonic WAVE_1 on tiny diff);
        # single-leg WAVE_1 exempt to avoid false filtering when leg spans whole window.
        if leg["direction"] == 1 and avg20 is not None and leg_avg is not None:
            keep_thr = 0.95 * avg20
            is_single_wave1 = len(base_sig) == 1
            if leg_avg >= keep_thr or is_single_wave1:
                # keep, but flag strength
                enriched["volume_weighted_keep"] = bool(leg_avg > avg20)
                enriched["volume_strength"] = "strong" if leg_avg > avg20 else "soft_weak_exempt" if is_single_wave1 else "soft"
                sig_legs.append(enriched)
            else:
                enriched["volume_weighted_keep"] = False
                enriched["volume_strength"] = "weak_filtered"
                # do NOT count weak-volume up legs as significant (conservative)
            volume_weighted_flags.append(enriched)
        else:
            # pullback legs or no volume data: keep as-is (volume agnostic)
            enriched["volume_weighted_keep"] = True if leg["direction"] == -1 or avg20 is None else None
            sig_legs.append(enriched)
            if leg["direction"] == 1:
                volume_weighted_flags.append(enriched)
    # If no volume data, sig_legs == base_sig (price-only fallback)
    if avg20 is None:
        sig_legs = [dict(l, avg_volume=None, volume_above_avg20=None, volume_weighted_keep=None) for l in base_sig]

    sig_dirs = [l["direction"] for l in sig_legs]
    result["evidence"]["significant_swing_legs"] = sig_legs
    result["evidence"]["base_significant_legs"] = base_sig
    result["evidence"]["volume_weighted_flags"] = volume_weighted_flags
    result["evidence"]["volume_avg20"] = round(avg20, 2) if avg20 is not None else None
    result["evidence"]["variant_config"] = {"swing_pct": SWING_PCT, "swing_bars": SWING_BARS, "near_high_thr": NEAR_HIGH_THR, "close_thr": CLOSE_THR, "hysteresis": HYSTERESIS_WINDOW, "volume_weighted": True}
    result["evidence"]["measurable_wave_sequence_sig"] = sig_dirs
    # if volume filtered away all legs, fallback to base for wave detection but flag
    effective_sig = sig_legs if sig_legs else base_sig
    effective_dirs = sig_dirs if sig_dirs else [l["direction"] for l in base_sig]
    if not sig_legs and base_sig:
        result["evidence"]["volume_filter_fallback"] = True

    measured_continuation = (
        effective_dirs[-3:] == [1, -1, 1]
        and len(effective_sig) >= 3
        and effective_sig[-2]["start_price"] > 0
        and (effective_sig[-2]["start_price"] - effective_sig[-2]["end_price"]) / effective_sig[-2]["start_price"] >= 0.05
        and effective_sig[-1]["end_price"] > effective_sig[-3]["end_price"]
    )
    measured_continuation_raw = (
        directions[-3:] == [1, -1, 1]
        and len(legs) >= 3
        and legs[-2]["start_price"] > 0
        and (legs[-2]["start_price"] - legs[-2]["end_price"]) / legs[-2]["start_price"] >= 0.05
        and legs[-1]["end_price"] > legs[-3]["end_price"]
    )
    measured_continuation = measured_continuation or measured_continuation_raw
    result["evidence"]["measurable_continuation"] = measured_continuation

    # Use price-only base for wave1 anchoring if volume filtered away up legs
    w1_legs_for_metrics = effective_sig if effective_sig and any(l.get("direction")==1 for l in effective_sig) else base_sig
    w1 = _wave1_metrics(close, w1_legs_for_metrics if w1_legs_for_metrics else legs)
    # --- Wave1 anchor: lowest Low in last 120 bars yielding >=5% advance (Low/High extremes) ---
    if has_ohlc and ohlc_legs_raw:
        # anchor uses price-only significant legs (base_sig/raw) not volume-filtered, to keep Jan Wave1 even with weak volume
        anchor_legs = base_sig if base_sig else ohlc_legs_raw
        if not anchor_legs:
            anchor_legs = ohlc_legs_raw
        # Only re-anchor when wave1 is degenerately anchored (first leg) or violated, to avoid breaking multi-leg WAVE_4/5.
        # For CRC fix: Sep close wave1 (earliest leg) gets corrected to Jan low when a lower qualified low exists.
        cur_low = w1.get("wave1_low")
        cur_start = w1.get("wave1_start_idx")
        should_try_anchor = False
        if cur_low is None or cur_start is None:
            should_try_anchor = True
        elif w1.get("holds_above_wave1_low") is False:
            should_try_anchor = True
        elif cur_start == 0 and len(anchor_legs) <= 2:
            # degenerate single-wave case: check if a lower low exists
            should_try_anchor = True
        elif len(anchor_legs) == 1 and cur_start is not None:
            should_try_anchor = True
        # also check if pullback violates on actual Low extremes
        if cur_low is not None and w1.get("wave1_end_idx") is not None:
            try:
                import math as _m
                low_s = __import__("pandas").to_numeric(daily_df["Low"], errors="coerce")
                post = low_s.iloc[w1["wave1_end_idx"]+1:]
                if not post.dropna().empty:
                    vals = low_s.values[w1["wave1_end_idx"]+1:]
                    valid = [v for v in vals if _m.isfinite(float(v))]
                    if valid and min(valid) <= cur_low:
                        should_try_anchor = True
            except Exception:
                pass
        if should_try_anchor:
            anchored = _best_wave1_anchor(daily_df, anchor_legs, pct=LARGE_SWING_PCT, min_bars=LARGE_SWING_BARS)
            if anchored is not None:
                if cur_low is None or anchored["wave1_low"] < cur_low - 1e-9:
                    w1["wave1_low"] = anchored["wave1_low"]
                    w1["wave1_start_idx"] = anchored["wave1_start_idx"]
                    w1["wave1_high"] = anchored["wave1_high"]
                    w1["wave1_end_idx"] = anchored["wave1_end_idx"]
                    w1["pullback_high"] = anchored["wave1_high"]
                    w1["pullback_low"] = None
                    w1["retracement_pct"] = None
                    w1["holds_above_wave1_low"] = None
                    result["evidence"]["wave1_anchor_overridden"] = True
                    result["evidence"]["wave1_anchor_low"] = anchored["wave1_low"]
                    result["evidence"]["wave1_anchor_high"] = anchored["wave1_high"]
        # strict Wave2 > Wave1 enforcement on actual Low extremes (always)
        w1 = _enforce_wave2_gt_wave1(daily_df, w1, anchor_legs)
        result["evidence"]["wave1_enforced"] = True
    if high_series is not None and len(high_series) == len(close) and w1.get("wave1_high") is not None:
        last_high_val = float(high_series.iloc[-1])
        last_close_val = float(close.iloc[-1])
        wh = float(w1["wave1_high"])
        w1["close_above_wave1_high"] = bool(last_close_val > wh)
        w1["tested_high_only"] = bool(last_high_val > wh and last_close_val <= wh)

    w1["near_high_breakout"] = False
    w1["is_near_high"] = None
    w1["volume_above_avg"] = None
    w1["close_within_3pct"] = None
    w1["close_within_2pct"] = None
    w1["volume_condition_met"] = None
    if w1.get("wave1_high") is not None and high_series is not None and len(high_series) == len(close):
        try:
            last_high_val = float(high_series.iloc[-1])
            last_close_val = float(close.iloc[-1])
            wh = float(w1["wave1_high"])
            threshold = NEAR_HIGH_THR * wh
            is_near_high = bool(last_high_val >= threshold)
            w1["is_near_high"] = is_near_high
            close_within = bool(last_close_val >= CLOSE_THR * wh) or bool(last_close_val >= CLOSE_THR * last_high_val) if last_high_val else bool(last_close_val >= CLOSE_THR * wh)
            w1["close_within_3pct"] = close_within
            w1["close_within_2pct"] = close_within
            volume_above = None
            if "Volume" in daily_df:
                vol_series = pd.to_numeric(daily_df["Volume"], errors="coerce").dropna()
                if len(vol_series) >= 2:
                    if len(vol_series) > 21:
                        avg20_local = float(vol_series.iloc[-21:-1].mean())
                    else:
                        avg20_local = float(vol_series.iloc[:-1].mean())
                    last_vol = float(vol_series.iloc[-1])
                    if math.isfinite(avg20_local) and avg20_local > 0 and math.isfinite(last_vol):
                        volume_above = bool(last_vol > avg20_local)
                    w1["volume_avg_20"] = round(float(avg20_local), 2) if math.isfinite(avg20_local) else None
                    w1["last_volume"] = last_vol
                else:
                    w1["volume_avg_20"] = None
                    w1["last_volume"] = None
            w1["volume_above_avg"] = volume_above
            volume_condition = bool(volume_above is True) or bool(close_within)
            w1["volume_condition_met"] = volume_condition
            w1["near_high_breakout"] = bool(is_near_high and volume_condition)
        except Exception:
            pass

    # --- Dual-degree: small (1),(2),(3) as 3%/2bars inside large Wave3 window (AWC lock) ---
    # Day-only, evidence-only — does not alter large state. Large stays 5%/5bars volume-weighted.
    try:
        _small = _compute_small_degree(close, w1, daily_df)
        result["evidence"]["small_wave_legs"] = _small.get("small_wave_legs", [])
        result["evidence"]["small_wave_labels"] = _small.get("small_wave_labels", [])
        result["evidence"]["small_legs"] = _small.get("small_legs", [])
        result["evidence"]["small_waves"] = _small.get("small_waves", [])
        result["evidence"]["small_degree_window"] = _small.get("small_degree_window")
        result["evidence"]["small_degree_source"] = _small.get("small_degree_source")
        result["evidence"]["small_degree_window_bars"] = _small.get("small_degree_window_bars")
        result["evidence"]["dual_degree"] = {
            "large": {"pct": LARGE_SWING_PCT, "bars": LARGE_SWING_BARS, "label": "1,2,3"},
            "small": {"pct": SMALL_SWING_PCT, "bars": SMALL_SWING_BARS, "label": "(1),(2),(3)"},
        }
    except Exception:
        result["evidence"]["small_wave_legs"] = []
        result["evidence"]["small_wave_labels"] = []
        result["evidence"]["small_legs"] = []
        result["evidence"]["small_waves"] = []

    result["evidence"].update({
        "daily_advance_10d_pct": round(recent_10, 2) if recent_10 is not None else None,
        "daily_advance_20d_pct": round(recent_20, 2) if recent_20 is not None else None,
        "daily_rebound_5d_pct": round(recent_5, 2) if recent_5 is not None else None,
        "daily_drawdown_from_10d_high_pct": round(drawdown, 2),
        "measurable_advance": advance,
        "measurable_pullback": pullback,
        "measurable_rebound": rebound,
        "measurable_breakout": breakout_close or bool(w1.get("close_above_wave1_high")),
        "wave1_high": w1.get("wave1_high"),
        "wave1_low": w1.get("wave1_low"),
        "retracement_pct": w1.get("retracement_pct"),
        "pullback_duration_days": w1.get("pullback_duration_days"),
        "holds_above_wave1_low": w1.get("holds_above_wave1_low"),
        "close_above_wave1_high": w1.get("close_above_wave1_high"),
        "tested_high_only": w1.get("tested_high_only"),
        "is_near_high": w1.get("is_near_high"),
        "near_high_breakout": w1.get("near_high_breakout"),
        "volume_above_avg": w1.get("volume_above_avg"),
        "close_within_3pct": w1.get("close_within_3pct"),
        "close_within_2pct": w1.get("close_within_2pct"),
        "volume_condition_met": w1.get("volume_condition_met"),
        "volume_avg_20": w1.get("volume_avg_20"),
        "last_volume": w1.get("last_volume"),
        "variant": VARIANT,
    })
    retrace = w1.get("retracement_pct")
    duration = w1.get("pullback_duration_days")
    holds = w1.get("holds_above_wave1_low")
    close_above = w1.get("close_above_wave1_high")
    tested_only = w1.get("tested_high_only")
    near_high_breakout = w1.get("near_high_breakout")

    sustained_days_above = 0
    breakout_above_20d_high = False
    prolonged_wave4_fallback = False
    sustained_w3_cont = False
    try:
        wh_for_sustain = w1.get("wave1_high")
        if wh_for_sustain is not None and len(close) >= 4:
            vals = close.tolist() if hasattr(close, "tolist") else list(close)
            cnt = 0
            for v in reversed(vals):
                if float(v) > float(wh_for_sustain):
                    cnt += 1
                else:
                    break
            sustained_days_above = cnt
        if len(close) >= 21:
            breakout_above_20d_high = bool(float(close.iloc[-1]) > float(close.iloc[-21:-1].max()))
        if sustained_days_above >= 3 and recent_20 is not None and recent_20 > 10 and bool(close_above):
            sustained_w3_cont = True
        elif sustained_days_above >= 10 and bool(close_above):
            sustained_w3_cont = True
        elif sustained_days_above >= 5 and bool(close_above) and recent_20 is not None and recent_20 > 5:
            sustained_w3_cont = True
        result["evidence"]["sustained_days_above_wave1_high"] = sustained_days_above
        result["evidence"]["breakout_above_20d_high"] = breakout_above_20d_high
        result["evidence"]["sustained_w3_cont_signal"] = sustained_w3_cont
    except Exception:
        result["evidence"]["sustained_days_above_wave1_high"] = sustained_days_above
        result["evidence"]["breakout_above_20d_high"] = breakout_above_20d_high
        result["evidence"]["sustained_w3_cont_signal"] = False
    try:
        check_dirs_tmp = effective_dirs if len(effective_dirs) >= 4 else directions
        is_wave4_pattern = check_dirs_tmp[-4:] == [1, -1, 1, -1]
        if is_wave4_pattern and recent_20 is not None and recent_20 > 12 and breakout_above_20d_high:
            wave1_end = w1.get("wave1_end_idx")
            stuck_days = (len(close) - int(wave1_end)) if wave1_end is not None else 999
            if stuck_days > 20 or recent_20 > 12:
                prolonged_wave4_fallback = True
        result["evidence"]["prolonged_wave4_fallback"] = prolonged_wave4_fallback
    except Exception:
        result["evidence"]["prolonged_wave4_fallback"] = False

    state: str | None = None
    # Spec §3: above 60% retracement or break of Wave 1 low is correction/unknown territory
    retrace_ok_for_w3 = (retrace is None or retrace <= 60) and (holds is not False)
    # T2 owner gate (spec §2.7, 2026-08-31): Early Wave 3 / W3 continuation require a
    # Daily Close above Wave 1 high. A wick alone is TESTED_HIGH evidence and can
    # never promote; breakout volume is supporting evidence, not a standalone gate.
    close_gate = bool(close_above)
    check_dirs = effective_dirs if len(effective_dirs) >= 4 else directions
    if check_dirs[-5:] == [1, -1, 1, -1, 1]:
        state = "WAVE_5_ADVANCE"
    elif sustained_w3_cont and close_gate and retrace_ok_for_w3:
        state = "WAVE_3_CONTINUATION"
    elif prolonged_wave4_fallback and close_gate and retrace_ok_for_w3:
        state = "EARLY_WAVE_3"
    elif check_dirs[-4:] == [1, -1, 1, -1] and not prolonged_wave4_fallback and not sustained_w3_cont and retrace_ok_for_w3:
        if close_gate and ((recent_20 is not None and recent_20 > 8) or (recent_10 is not None and recent_10 > 8)):
            state = "WAVE_3_CONTINUATION"
        else:
            state = "WAVE_4_CORRECTION"
    elif measured_continuation and close_gate and retrace_ok_for_w3:
        state = "WAVE_3_CONTINUATION"
    elif rebound and close_gate and retrace_ok_for_w3:
        state = "EARLY_WAVE_3"
    elif close_gate and not pullback and (retrace is not None or (len(effective_sig) >= 2 and any(l["direction"] == -1 for l in effective_sig))) and ((recent_20 is not None and recent_20 > 8) or (recent_10 is not None and recent_10 > 8) or (breakout_above_20d_high and recent_20 is not None and recent_20 > 5)) and retrace_ok_for_w3:
        state = "EARLY_WAVE_3"
    elif pullback:
        if "fib_zone" in evidence:
            state = "WAVE_2_NEAR_COMPLETION" if evidence.get("fib_zone") else "WAVE_2_FORMING"
        elif retrace is not None:
            if retrace > 60 or (holds is False):
                state = "WAVE_4_CORRECTION" if directions[-4:] == [1, -1, 1, -1] else None
            elif 30 <= retrace <= 60 and duration is not None and 5 <= duration <= 25 and holds:
                state = "WAVE_2_NEAR_COMPLETION"
            elif retrace < 30:
                state = "WAVE_2_FORMING"
            elif 30 <= retrace <= 60:
                state = "WAVE_2_FORMING"
            else:
                state = None
        else:
            state = "WAVE_2_FORMING" if not evidence.get("fib_zone") else "WAVE_2_NEAR_COMPLETION"
        if state is None and retrace is None:
            state = "WAVE_2_FORMING"
    elif advance:
        state = "WAVE_1_ADVANCE"
    elif prolonged_wave4_fallback:
        state = "WAVE_1_ADVANCE"

    if state is None:
        confirmed_pivots = len(effective_sig) if effective_sig else len(legs)
        has_two_pivots = confirmed_pivots >= 2
        only_anchor_missing = all(
            m in ("confirmed_swing_anchors", "structure_intact", "prior_advance")
            for m in result["evidence"]["missing_evidence"]
        )
        holds_ok = w1.get("holds_above_wave1_low") is not False
        if advance and (holds_ok or w1.get("holds_above_wave1_low") is None):
            if has_two_pivots and "confirmed_swing_anchors" in result["evidence"]["missing_evidence"]:
                only_anchor_missing = True
            if only_anchor_missing and not _hysteresis_disable:
                if _wave1_hysteresis_check(daily_df, swing_evidence, _disable=False):
                    result["state"] = "WAVE_1_ADVANCE"
                    relaxed = [m for m in result["evidence"]["missing_evidence"] if m not in ("confirmed_swing_anchors", "structure_intact", "prior_advance")]
                    result["evidence"]["missing_evidence"] = relaxed
                    result["evidence"]["wave1_persistence"] = True
                    result["evidence"]["wave1_hysteresis_window"] = HYSTERESIS_WINDOW
                    result["evidence"]["confirmed_pivots"] = confirmed_pivots
                    result["confidence"] = "MEDIUM"
                    try:
                        _small = _compute_small_degree(close, w1, daily_df)
                        result["evidence"]["small_wave_legs"] = _small.get("small_wave_legs", [])
                        result["evidence"]["small_wave_labels"] = _small.get("small_wave_labels", [])
                        result["evidence"]["small_legs"] = _small.get("small_legs", [])
                        result["evidence"]["small_waves"] = _small.get("small_waves", [])
                        result["evidence"]["small_degree_window"] = _small.get("small_degree_window")
                        result["evidence"]["small_degree_source"] = _small.get("small_degree_source")
                        result["evidence"]["dual_degree"] = {"large": {"pct": LARGE_SWING_PCT, "bars": LARGE_SWING_BARS, "label": "1,2,3"}, "small": {"pct": SMALL_SWING_PCT, "bars": SMALL_SWING_BARS, "label": "(1),(2),(3)"}}
                    except Exception:
                        pass
                    return result
                if has_two_pivots and holds_ok:
                    result["state"] = "WAVE_1_ADVANCE"
                    relaxed = [m for m in result["evidence"]["missing_evidence"] if m not in ("confirmed_swing_anchors", "structure_intact", "prior_advance")]
                    result["evidence"]["missing_evidence"] = relaxed
                    result["evidence"]["confirmed_pivots"] = confirmed_pivots
                    result["evidence"]["wave1_two_pivot_relax"] = True
                    result["confidence"] = "MEDIUM"
                    try:
                        _small = _compute_small_degree(close, w1, daily_df)
                        result["evidence"]["small_wave_legs"] = _small.get("small_wave_legs", [])
                        result["evidence"]["small_wave_labels"] = _small.get("small_wave_labels", [])
                        result["evidence"]["small_legs"] = _small.get("small_legs", [])
                        result["evidence"]["small_waves"] = _small.get("small_waves", [])
                        result["evidence"]["small_degree_window"] = _small.get("small_degree_window")
                        result["evidence"]["small_degree_source"] = _small.get("small_degree_source")
                        result["evidence"]["dual_degree"] = {"large": {"pct": LARGE_SWING_PCT, "bars": LARGE_SWING_BARS, "label": "1,2,3"}, "small": {"pct": SMALL_SWING_PCT, "bars": SMALL_SWING_BARS, "label": "(1),(2),(3)"}}
                    except Exception:
                        pass
                    return result
        # UNKNOWN fallback still expose small degree (evidence-only)
        try:
            _small = _compute_small_degree(close, w1, daily_df)
            result["evidence"]["small_wave_legs"] = _small.get("small_wave_legs", [])
            result["evidence"]["small_wave_labels"] = _small.get("small_wave_labels", [])
            result["evidence"]["small_legs"] = _small.get("small_legs", [])
            result["evidence"]["small_waves"] = _small.get("small_waves", [])
            result["evidence"]["small_degree_window"] = _small.get("small_degree_window")
            result["evidence"]["small_degree_source"] = _small.get("small_degree_source")
            result["evidence"]["dual_degree"] = {"large": {"pct": LARGE_SWING_PCT, "bars": LARGE_SWING_BARS, "label": "1,2,3"}, "small": {"pct": SMALL_SWING_PCT, "bars": SMALL_SWING_BARS, "label": "(1),(2),(3)"}}
        except Exception:
            pass
        return result
    if structure_failed:
        if state != "WAVE_1_ADVANCE":
            # still expose small degree before fail-closed
            try:
                _small = _compute_small_degree(close, w1, daily_df)
                result["evidence"]["small_wave_legs"] = _small.get("small_wave_legs", [])
                result["evidence"]["small_wave_labels"] = _small.get("small_wave_labels", [])
                result["evidence"]["small_legs"] = _small.get("small_legs", [])
                result["evidence"]["small_waves"] = _small.get("small_waves", [])
                result["evidence"]["small_degree_window"] = _small.get("small_degree_window")
                result["evidence"]["small_degree_source"] = _small.get("small_degree_source")
                result["evidence"]["dual_degree"] = {"large": {"pct": LARGE_SWING_PCT, "bars": LARGE_SWING_BARS, "label": "1,2,3"}, "small": {"pct": SMALL_SWING_PCT, "bars": SMALL_SWING_BARS, "label": "(1),(2),(3)"}}
            except Exception:
                pass
            return result
        if not (advance and (w1.get("holds_above_wave1_low") is not False)):
            try:
                _small = _compute_small_degree(close, w1, daily_df)
                result["evidence"]["small_wave_legs"] = _small.get("small_wave_legs", [])
                result["evidence"]["small_wave_labels"] = _small.get("small_wave_labels", [])
                result["evidence"]["small_legs"] = _small.get("small_legs", [])
                result["evidence"]["small_waves"] = _small.get("small_waves", [])
                result["evidence"]["small_degree_window"] = _small.get("small_degree_window")
                result["evidence"]["small_degree_source"] = _small.get("small_degree_source")
                result["evidence"]["dual_degree"] = {"large": {"pct": LARGE_SWING_PCT, "bars": LARGE_SWING_BARS, "label": "1,2,3"}, "small": {"pct": SMALL_SWING_PCT, "bars": SMALL_SWING_BARS, "label": "(1),(2),(3)"}}
            except Exception:
                pass
            return result
    result["state"] = state
    measurable_states = {"WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3", "WAVE_3_CONTINUATION"}
    if state in measurable_states:
        relaxed_missing = [m for m in result["evidence"]["missing_evidence"] if m not in ("prior_advance", "confirmed_swing_anchors", "structure_intact") or evidence.get(m) is False]
        if advance or pullback or rebound or measured_continuation or close_above:
            relaxed_missing = [m for m in result["evidence"]["missing_evidence"] if m not in ("prior_advance", "confirmed_swing_anchors")]
            if advance:
                relaxed_missing = [m for m in relaxed_missing if m != "structure_intact"]
        result["evidence"]["missing_evidence"] = relaxed_missing
        if not relaxed_missing or "measurable_daily_structure" not in relaxed_missing:
            if result["confidence"] == "INSUFFICIENT":
                result["confidence"] = "MEDIUM"
            elif result["confidence"] == "PARTIAL":
                result["confidence"] = "MEDIUM"
            if state == "WAVE_2_NEAR_COMPLETION" and retrace is not None and 30 <= retrace <= 60 and duration is not None and 5 <= duration <= 25 and holds:
                result["confidence"] = "HIGH" if evidence.get("fib_zone") else "MEDIUM"
                if evidence.get("fib_zone"):
                    result["confidence"] = "HIGH"
            elif state == "EARLY_WAVE_3" and close_above:
                result["confidence"] = "HIGH"
            elif state == "EARLY_WAVE_3" and near_high_breakout:
                result["confidence"] = "MEDIUM"
            elif state == "EARLY_WAVE_3":
                result["confidence"] = "HIGH" if evidence.get("breakout_confirmed") else "MEDIUM"
            elif state == "WAVE_3_CONTINUATION":
                result["confidence"] = "MEDIUM"
                if evidence.get("wave_3_continuation") or close_above:
                    result["confidence"] = "HIGH"
            elif state == "WAVE_1_ADVANCE":
                result["confidence"] = "MEDIUM"
    else:
        if result["confidence"] == "INSUFFICIENT":
            relaxed = [m for m in result["evidence"]["missing_evidence"] if m not in ("prior_advance", "confirmed_swing_anchors", "structure_intact")]
            if not relaxed or relaxed == ["daily_ohlcv"]:
                result["confidence"] = "MEDIUM"
                result["evidence"]["missing_evidence"] = relaxed
        elif result["confidence"] == "PARTIAL":
            result["confidence"] = "MEDIUM"
    return result


# ---------------------------------------------------------------------------
# Production contract boundary (T2, spec §2.2) — wave interpretation exposed to
# the setup-candidates contract. Machine-generated candidate evidence, never an
# objectively confirmed count.
# ---------------------------------------------------------------------------

_WAVE_CONTRACT_STATES = set(WAVE_STATES)

_NEXT_PLAUSIBLE = {
    "WAVE_1_ADVANCE": "WAVE_2_FORMING",
    "WAVE_2_FORMING": "WAVE_2_NEAR_COMPLETION",
    "WAVE_2_NEAR_COMPLETION": "EARLY_WAVE_3",
    "EARLY_WAVE_3": "WAVE_3_CONTINUATION",
    "WAVE_3_CONTINUATION": "WAVE_4_CORRECTION",
    "WAVE_4_CORRECTION": "WAVE_5_ADVANCE",
    "WAVE_5_ADVANCE": "UNKNOWN",
}

_CONFIDENCE_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
_WAVE_CONTEXT_RULE_VERSION = "elliott-full-wave-context-v1"
_WAVE_CONTEXT_SECONDARY_MARKERS = {"WAVE_3_EXTENDED"}


def _evidence_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return sorted({str(item) for item in value if item is not None})
    return [str(value)]


def _build_wave_context(legacy_raw: dict, swing_evidence: dict | None) -> dict:
    """Project the reachable full-wave result as evidence, never authority."""
    raw = legacy_raw if isinstance(legacy_raw, dict) else {}
    evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
    raw_state = raw.get("state")
    valid_state = raw_state in _WAVE_CONTRACT_STATES
    state = raw_state if valid_state else "UNKNOWN"
    raw_confidence = str(raw.get("confidence") or "").upper()
    confidence = {"PARTIAL": "MEDIUM", "INSUFFICIENT": "LOW"}.get(
        raw_confidence, raw_confidence
    )
    if confidence not in _CONFIDENCE_ORDER or state == "UNKNOWN":
        confidence = "LOW"
    supporting = _supporting_evidence(evidence, state)
    contradicting = _contradicting_evidence(evidence, state)
    missing = _evidence_list(evidence.get("missing_evidence"))
    if not valid_state:
        contradicting.append("invalid_structural_context_state")
    if raw.get("timeframe", "daily") != "daily":
        contradicting.append("invalid_context_source_timeframe")
    secondary = []
    if (state == "WAVE_3_CONTINUATION"
            and isinstance(swing_evidence, dict)
            and swing_evidence.get("wave_3_extended") is True):
        secondary.append("WAVE_3_EXTENDED")
    return {
        "mapped_state": state,
        "secondary_markers": secondary,
        "confidence": confidence,
        "rule_version": _WAVE_CONTEXT_RULE_VERSION,
        "source_timeframe": "daily",
        "supporting_evidence": sorted(set(supporting)),
        "contradicting_evidence": sorted(set(contradicting)),
        "missing_evidence": missing,
        "rationale": (
            f"Deterministic full-wave engine mapped {state} as Daily context evidence."
        ),
    }


def _contradicting_evidence(evidence: dict, state: str) -> list[str]:
    """Observable facts that argue against the emitted primary state."""
    out: list[str] = []
    retrace = evidence.get("retracement_pct")
    if state in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"}:
        if evidence.get("close_above_wave1_high") is False:
            out.append("daily_close_not_above_wave1_high")
        if retrace is not None and retrace > 60:
            out.append("wave2_retracement_above_60pct")
        if evidence.get("holds_above_wave1_low") is False:
            out.append("wave1_low_broken")
    if state == "WAVE_2_NEAR_COMPLETION":
        if retrace is not None and not 30 <= retrace <= 60:
            out.append("retracement_outside_30_60")
        duration = evidence.get("pullback_duration_days")
        if duration is not None and not 5 <= duration <= 25:
            out.append("duration_outside_5_25")
        if evidence.get("holds_above_wave1_low") is False:
            out.append("wave1_low_broken")
    if state == "WAVE_1_ADVANCE" and evidence.get("structure_intact") is False:
        out.append("structure_intact_false")
    return out


def _supporting_evidence(evidence: dict, state: str) -> list[str]:
    out: list[str] = []
    if evidence.get("measurable_advance"):
        out.append("measurable_advance")
    if state in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"}:
        if evidence.get("close_above_wave1_high"):
            out.append("daily_close_above_wave1_high")
        if evidence.get("volume_above_avg"):
            out.append("breakout_volume_above_20d_avg")
    if state in {"WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION"}:
        if evidence.get("retracement_pct") is not None:
            out.append("measured_retracement")
        if evidence.get("holds_above_wave1_low"):
            out.append("holds_above_wave1_low")
        if evidence.get("fib_zone"):
            out.append("fib_retracement_zone")
    if state == "WAVE_1_ADVANCE" and evidence.get("holds_above_wave1_low") is True:
        out.append("structure_holds_above_wave1_low")
    return out


def _missing_evidence(evidence: dict, state: str) -> list[str]:
    out = list(evidence.get("missing_evidence") or [])
    retrace = evidence.get("retracement_pct")
    if state in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"} and retrace is None:
        out.append("wave2_retracement_unmeasured")
    return out


def _marker_timestamp(frame, index: int | None):
    """Return the source timestamp without manufacturing one."""
    if index is None or frame is None or index < 0 or index >= len(frame):
        return None
    if "date" in frame:
        value = frame.iloc[index].get("date")
        return None if value is None else _normalize_marker_timestamp(value)
    try:
        value = frame.index[index]
        return _normalize_marker_timestamp(value)
    except (IndexError, TypeError):
        return None


def _normalize_marker_timestamp(value) -> str | None:
    """Normalize source timestamps for the Daily chart's date-only candles."""
    if value is None:
        return None
    raw = value.isoformat() if hasattr(value, "isoformat") else str(value)
    raw = raw.strip()
    if not raw:
        return None
    return raw[:10] if len(raw) >= 10 else raw


def _marker_index(frame, price, column: str, start: int = 0, end: int | None = None):
    """Find an exact source row for a known pivot price."""
    if price is None or frame is None or column not in frame:
        return None
    stop = len(frame) if end is None else min(len(frame), end + 1)
    try:
        values = pd.to_numeric(frame[column], errors="coerce")
        matches = [i for i in range(max(0, start), stop)
                   if pd.notna(values.iloc[i]) and float(values.iloc[i]) == float(price)]
        return matches[-1] if matches else None
    except (TypeError, ValueError, IndexError):
        return None


def _first_marker_index(frame, predicate, start: int = 0):
    """Find the first source row where an observable event occurs."""
    if frame is None:
        return None
    for index in range(max(0, start), len(frame)):
        try:
            if predicate(frame.iloc[index]):
                return index
        except (TypeError, ValueError, KeyError):
            continue
    return None


def _evidence_marker(kind: str, timeframe: str, timestamp, price, label: str,
                     wave_role: str, source: str, confidence: str,
                     evidence_refs: list[str], snapshot_id: str | None,
                     explanation: dict) -> dict:
    return _json_value({
        "id": "elliott-" + kind.lower().replace("_", "-"),
        "kind": kind,
        "timeframe": timeframe,
        "timestamp": timestamp,
        "price": price,
        "label": label,
        "wave_role": wave_role,
        "source": source,
        "confidence": confidence,
        "evidence_refs": evidence_refs,
        "snapshot_id": snapshot_id,
        "snapshot_identity": snapshot_id,
        "explanation": explanation,
    })


def build_wave_evidence_markers(daily_df, evidence: dict, *, confidence: str = "LOW",
                                snapshot_id: str | None = None) -> list[dict]:
    """Project only source-linked Daily Elliott observations onto chart markers."""
    evidence = evidence or {}
    legs = evidence.get("ohlc_swing_legs") or []
    markers = []
    refs = ["daily_ohlcv", "ohlc_swing_legs"]
    w1_low, w1_high = evidence.get("wave1_low"), evidence.get("wave1_high")
    w1_leg = next((leg for leg in legs if leg.get("start_price") == w1_low
                   and leg.get("end_price") == w1_high), None)
    pullback_leg = None
    if w1_leg is not None:
        low_idx, high_idx = int(w1_leg["start"]), int(w1_leg["end"])
        markers.extend([
            _evidence_marker("WAVE_1_LOW", "daily", _marker_timestamp(daily_df, low_idx), w1_low,
                             "Wave 1 low", "WAVE_1", "daily_ohlcv", confidence, refs, snapshot_id,
                             {"rule": "Wave 1 advance begins at the observed swing low.", "evidence": refs,
                              "alternative": evidence.get("alternative_state"), "missing": [],
                              "policy": "elliott-v1-observable-proxy"}),
            _evidence_marker("WAVE_1_HIGH", "daily", _marker_timestamp(daily_df, high_idx), w1_high,
                             "Wave 1 high", "WAVE_1", "daily_ohlcv", confidence, refs, snapshot_id,
                             {"rule": "Wave 1 advance ends at the observed swing high.", "evidence": refs,
                              "alternative": evidence.get("alternative_state"), "missing": [],
                              "policy": "elliott-v1-observable-proxy"}),
        ])
        markers.append(_evidence_marker(
            "THESIS_INVALIDATION", "daily", _marker_timestamp(daily_df, low_idx), w1_low,
            "Thesis invalidation", "THESIS_INVALIDATION", "daily_ohlcv", confidence,
            ["wave1_low"], snapshot_id,
            {"rule": "Daily structure is invalid below the Wave 1 low.", "evidence": ["wave1_low"],
             "alternative": None, "missing": [], "policy": "elliott-v1-observable-proxy"}))
        pullback = next((leg for leg in legs if leg.get("direction") == -1
                         and int(leg.get("start", -1)) > high_idx), None)
        if pullback is not None:
            pullback_leg = pullback
            idx = int(pullback["end"])
            markers.append(_evidence_marker(
                "WAVE_2_PULLBACK_LOW", "daily", _marker_timestamp(daily_df, idx),
                pullback.get("end_price"), "Wave 2 pullback low", "WAVE_2",
                "daily_ohlcv", confidence, refs, snapshot_id,
                {"rule": "Pullback low is the next observed Daily down-swing low.", "evidence": refs,
                 "alternative": None, "missing": [], "policy": "elliott-v1-observable-proxy"}))
    last_idx = len(daily_df) - 1 if daily_df is not None else None
    if evidence.get("close_above_wave1_high") is True and last_idx is not None:
        # Confirmation is an as-of observation: the completed latest Daily
        # candle is the source row that confirms the currently served thesis.
        # Structural markers above remain anchored to their historical pivots.
        event_idx = last_idx
        close = daily_df.iloc[event_idx].get("Close")
        markers.append(_evidence_marker(
            "WAVE_3_CLOSE_CONFIRMATION", "daily", _marker_timestamp(daily_df, event_idx), close,
            "Wave 3 close confirmation", "WAVE_3", "daily_ohlcv", confidence,
            ["daily_close_above_wave1_high"], snapshot_id,
            {"rule": "Daily Close must finish above Wave 1 high; a wick alone is not confirmation.",
             "evidence": ["daily_close_above_wave1_high"], "alternative": None,
             "missing": [], "policy": "elliott-v1-observable-proxy"}))
    if evidence.get("tested_high_only") is True:
        idx = _first_marker_index(
            daily_df,
            lambda row: float(row.get("High")) > float(w1_high),
            start=(int(pullback_leg["end"]) + 1 if pullback_leg is not None
                   else high_idx + 1 if w1_leg is not None else 0),
        )
        markers.append(_evidence_marker(
            "TESTED_HIGH", "daily", _marker_timestamp(daily_df, idx),
            daily_df.iloc[idx].get("High") if idx is not None else None,
            "Tested high (wick only)", "WAVE_3", "daily_ohlcv", confidence,
            ["tested_high_only"], snapshot_id,
            {"rule": "A wick through the reference is tested-high evidence, not a breakout.",
             "evidence": ["tested_high_only"], "alternative": None, "missing": ["daily_close_above_wave1_high"],
             "policy": "elliott-v1-observable-proxy"}))
    if evidence.get("holds_above_wave1_low") is False:
        idx = _first_marker_index(
            daily_df,
            lambda row: float(row.get("Low")) <= float(w1_low),
            start=(high_idx + 1 if w1_leg is not None else 0),
        )
        markers.append(_evidence_marker(
            "STRUCTURE_BREAK", "daily", _marker_timestamp(daily_df, idx), w1_low,
            "Daily structure break", "THESIS_INVALIDATION", "daily_ohlcv", confidence,
            ["wave1_low_broken"], snapshot_id,
            {"rule": "A Daily low at or below Wave 1 low breaks the thesis structure.",
             "evidence": ["wave1_low_broken"], "alternative": None, "missing": [],
             "policy": "elliott-v1-observable-proxy"}))
    return [marker for marker in markers if marker.get("timestamp") is not None
            and marker.get("price") is not None]


def build_wave_contract(daily_df, swing_evidence: dict | None = None, *, snapshot_id: str | None = None) -> dict:
    """Classify the Daily series and project the canonical wave contract.

    Emits ``primary_state``, ``alternative_state``, ``confidence``
    (LOW/MEDIUM/HIGH), and supporting/contradicting/missing evidence arrays per
    spec §2.2. ``UNKNOWN`` still exposes explicit evidence arrays. Never claims
    an objectively confirmed count; dual-degree small waves remain evidence-only
    inside ``evidence`` and never alter the large primary state.
    """
    # The full-wave classifier remains available only as explicit compatibility
    # evidence.  The canonical producer is deliberately narrower and fails
    # closed when a current Wave-3 interpretation is not structurally verifiable.
    legacy_raw = classify_wave_candidate(daily_df, swing_evidence)
    candidate = classify_wave3_candidate(daily_df)
    published = candidate.get("published_state", "NOT_VERIFIABLE")
    state = published if published in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"} else "NOT_VERIFIABLE"
    confidence = candidate.get("confidence") if state != "NOT_VERIFIABLE" else "LOW"
    if confidence not in _CONFIDENCE_ORDER:
        confidence = "LOW"
    alternative = "WAVE_3_CONTINUATION" if state == "EARLY_WAVE_3" else "NOT_VERIFIABLE"
    anchors = candidate.get("anchors") or {}
    evidence = {
        **dict(candidate.get("evidence") or {}),
        "anchors": anchors,
        "retracement": candidate.get("retracement"),
        "close_vs_wick_confirmation": candidate.get("close_vs_wick_confirmation"),
        "follow_through": candidate.get("follow_through"),
        "rejection_reasons": list(candidate.get("rejection_reasons") or []),
    }
    supporting = []
    if anchors.get("w1_low") and anchors.get("w1_high") and anchors.get("w2_low"):
        supporting.append("ordered_w1_low_w1_high_w2_low")
    if candidate.get("close_vs_wick_confirmation") == "CLOSE":
        supporting.append("daily_close_above_wave1_high")
    if (candidate.get("follow_through") or {}).get("status") == "PASS":
        supporting.append("daily_close_follow_through")
    if evidence.get("trend_support"):
        supporting.append("ma_trend_support_confidence_only")
    if evidence.get("volume_support"):
        supporting.append("volume_support_confidence_only")
    contradicting = list(candidate.get("rejection_reasons") or [])
    missing = contradicting if state == "NOT_VERIFIABLE" else []
    contract = {
        "timeframe": "daily",
        "primary_state": state,
        "state": state,
        "alternative_state": alternative,
        "confidence": confidence,
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "missing_evidence": missing,
        "evidence": evidence,
        "policy": "wave3-confirmed-pivots-v1",
        "context": _build_wave_context(legacy_raw, swing_evidence),
        "audit_compatibility": {
            "legacy_full_wave": _json_value(legacy_raw),
            "raw_candidate_state": candidate.get("raw_state"),
        },
    }
    as_of = _marker_timestamp(daily_df, len(daily_df) - 1) if daily_df is not None and len(daily_df) else None
    identity = snapshot_id or ("daily:" + as_of if as_of is not None else None)
    contract["snapshot_id"] = identity
    marker_specs = [
        ("WAVE_1_LOW", anchors.get("w1_low"), "Wave 1 low", "WAVE_1"),
        ("WAVE_1_HIGH", anchors.get("w1_high"), "Wave 1 high", "WAVE_1"),
        ("WAVE_2_PULLBACK_LOW", anchors.get("w2_low"), "Wave 2 pullback low", "WAVE_2"),
        ("WAVE_3_CLOSE_CONFIRMATION", anchors.get("breakout_confirmation"),
         "Wave 3 close confirmation", "WAVE_3"),
    ]
    contract["evidence_markers"] = [
        _evidence_marker(kind, "daily", anchor.get("date"), anchor.get("price"), label,
                         role, "daily_ohlcv", confidence,
                         ["ordered_confirmed_daily_pivots", "daily_close"], identity,
                         {"rule": "Confirmed Daily Wave-3 candidate anchor.",
                          "evidence": ["daily_ohlcv"], "alternative": alternative,
                          "missing": missing, "policy": contract["policy"]})
        for kind, anchor, label, role in marker_specs if anchor
    ]
    contract["markers"] = contract["evidence_markers"]
    contract["evidence_explanation"] = {
        "rule": "Daily Wave-3 candidate uses ordered confirmed pivots and close-only confirmation.",
        "evidence": contract["supporting_evidence"],
        "alternative": alternative,
        "missing": contract["missing_evidence"],
        "policy": contract["policy"],
    }
    return _json_value(contract)
