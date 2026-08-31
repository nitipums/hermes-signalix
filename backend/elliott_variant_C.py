"""Variant C: Enhanced Swing 5%/5bars volume-weighted + 5-day hysteresis.

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
        return result
    if not _close_available(daily_df):
        result["evidence"]["variant"] = VARIANT
        return result

    close = pd.to_numeric(daily_df["Close"], errors="coerce").dropna()
    if len(close) < 21:
        result["evidence"]["missing_evidence"].append("measurable_daily_structure")
        result["evidence"]["variant"] = VARIANT
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

    legs = _swing_legs(close)
    directions = [leg["direction"] for leg in legs]
    result["evidence"]["daily_swing_legs"] = [
        {"direction": leg["direction"], "start": leg["start"], "end": leg["end"],
         "start_price": leg["start_price"], "end_price": leg["end_price"]}
        for leg in legs
    ]
    result["evidence"]["measurable_wave_sequence"] = directions

    # Base significant filter 5%/5bars
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

    w1 = _wave1_metrics(close, effective_sig if effective_sig else legs)
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
    check_dirs = effective_dirs if len(effective_dirs) >= 4 else directions
    if check_dirs[-5:] == [1, -1, 1, -1, 1]:
        state = "WAVE_5_ADVANCE"
    elif sustained_w3_cont:
        state = "WAVE_3_CONTINUATION"
    elif prolonged_wave4_fallback and close_above:
        state = "EARLY_WAVE_3"
    elif prolonged_wave4_fallback and near_high_breakout:
        state = "EARLY_WAVE_3"
    elif check_dirs[-4:] == [1, -1, 1, -1] and not prolonged_wave4_fallback and not sustained_w3_cont:
        if close_above and ((recent_20 is not None and recent_20 > 8) or (recent_10 is not None and recent_10 > 8)):
            state = "WAVE_3_CONTINUATION"
        elif near_high_breakout and ((recent_20 is not None and recent_20 > 8) or (recent_10 is not None and recent_10 > 8)):
            state = "EARLY_WAVE_3"
        else:
            state = "WAVE_4_CORRECTION"
    elif measured_continuation and close_above:
        state = "WAVE_3_CONTINUATION"
    elif measured_continuation:
        state = "WAVE_3_CONTINUATION"
    elif rebound and close_above:
        state = "EARLY_WAVE_3"
    elif rebound and near_high_breakout:
        state = "EARLY_WAVE_3"
    elif rebound and evidence.get("breakout_confirmed"):
        state = "EARLY_WAVE_3"
    elif rebound and tested_only:
        if near_high_breakout:
            state = "EARLY_WAVE_3"
        elif evidence:
            state = "EARLY_WAVE_3"
        else:
            state = None
    elif rebound:
        if near_high_breakout:
            state = "EARLY_WAVE_3"
        elif evidence.get("breakout_confirmed") or evidence.get("early_wave_3") or evidence.get("wave_3_continuation") or evidence:
            state = "EARLY_WAVE_3"
        else:
            state = None
    elif (close_above or near_high_breakout) and not pullback and (retrace is not None or (len(effective_sig) >= 2 and any(l["direction"] == -1 for l in effective_sig))) and ((recent_20 is not None and recent_20 > 8) or (recent_10 is not None and recent_10 > 8) or (breakout_above_20d_high and recent_20 is not None and recent_20 > 5)):
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
                    return result
                if has_two_pivots and holds_ok:
                    result["state"] = "WAVE_1_ADVANCE"
                    relaxed = [m for m in result["evidence"]["missing_evidence"] if m not in ("confirmed_swing_anchors", "structure_intact", "prior_advance")]
                    result["evidence"]["missing_evidence"] = relaxed
                    result["evidence"]["confirmed_pivots"] = confirmed_pivots
                    result["evidence"]["wave1_two_pivot_relax"] = True
                    result["confidence"] = "MEDIUM"
                    return result
        return result
    if structure_failed:
        if state != "WAVE_1_ADVANCE":
            return result
        if not (advance and (w1.get("holds_above_wave1_low") is not False)):
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
