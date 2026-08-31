#!/usr/bin/env python3
"""
Variant B: MA Trend + Breakout Close logic (sol exploration) — THROWAWAY PROTOTYPE

Question: Does MA-filtered Elliott (trend + breakout Close) produce cleaner
         Wave 1/2/early-3 separation than pure swing-leg logic?

Approach B (Variant B):
  - WAVE_1: Close > MA50 AND MA20 > MA50  (trend filter)
  - WAVE_2: retracement 30-60% of Wave1 + holds above MA50 (not just Wave1 low)
  - EARLY_WAVE_3: Close > Wave1 high + Close > MA20 + volume > avg20

Pure function, no DB writes, no persistence.
Location: prototypes/elliott-state-replay/variant_B.py  (throwaway)
Mirror:   backend/elliott_variant_B.py

Run:  python prototypes/elliott-state-replay/variant_B.py
      python backend/elliott_variant_B.py
"""
from __future__ import annotations

import math
from typing import Any

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

# ---------------------------------------------------------------------------
# Helpers (copied minimal from elliott_structure_engine, no import)
# ---------------------------------------------------------------------------

def _pct(close: pd.Series, lookback: int):
    if len(close) <= lookback:
        return None
    start, end = float(close.iloc[-lookback - 1]), float(close.iloc[-1])
    if not math.isfinite(start) or start == 0 or not math.isfinite(end):
        return None
    return (end / start - 1.0) * 100.0


def _swing_legs(close: pd.Series) -> list[dict]:
    values = [float(v) for v in close if math.isfinite(float(v))]
    if len(values) < 2:
        return []
    legs: list[dict] = []
    start = 0
    current = 0
    for idx in range(1, len(values)):
        sign = 1 if values[idx] > values[idx - 1] else -1 if values[idx] < values[idx - 1] else 0
        if not sign:
            continue
        if not current:
            current = sign
            continue
        if sign != current:
            end = idx - 1
            legs.append({"direction": current, "start": start, "end": end,
                         "start_price": values[start], "end_price": values[end]})
            start = end
            current = sign
    legs.append({"direction": current, "start": start, "end": len(values) - 1,
                 "start_price": values[start], "end_price": values[-1]})
    return legs


def _wave1_metrics(close: pd.Series, legs: list[dict]) -> dict:
    out: dict[str, Any] = {
        "wave1_high": None, "wave1_low": None,
        "wave1_start_idx": None, "wave1_end_idx": None,
        "pullback_low": None, "pullback_high": None,
        "pullback_duration_days": None,
        "retracement_pct": None,
        "holds_above_wave1_low": None,
    }
    if not legs:
        return out
    values = [float(v) for v in close if math.isfinite(float(v))]
    if not values:
        return out
    directions = [l["direction"] for l in legs]
    wave1_idx: int | None = None
    pullback_idx: int | None = None
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
        for i, leg in enumerate(legs):
            if leg["direction"] == 1:
                wave1_idx = i
                break
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
        out["holds_above_wave1_low"] = bool(out["pullback_low"] > out["wave1_low"])
    last_close = float(values[-1])
    out["close_above_wave1_high"] = bool(last_close > out["wave1_high"]) if out["wave1_high"] is not None else None
    return out


# ---------------------------------------------------------------------------
# Variant B core — MA trend + breakout Close
# ---------------------------------------------------------------------------

def _ma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def classify_variant_B(daily_df: pd.DataFrame | None, *, strict_volume: bool = True) -> dict:
    """
    Pure function: Variant B — MA trend + breakout Close.

    Rules
    -----
    WAVE_1_ADVANCE:
        Close > MA50  AND  MA20 > MA50  AND  measurable_advance (recent 10d >0)
        — trend filter eliminates counter-trend pops.

    WAVE_2 (FORMING / NEAR_COMPLETION):
        Retracement 30-60% AND pullback_low > MA50 AND holds_above_wave1_low
        - 30-60% + holds MA50 + duration 5-25d => NEAR_COMPLETION
        - otherwise FORMING (too shallow / too deep / broke MA50)

    EARLY_WAVE_3:
        Close > Wave1 high (Close, not High wick)
        AND Close > MA20
        AND volume > avg20 (if strict_volume, else volume OR close within 2% of high)

    Returns dict with: state, confidence, evidence, missing, etc.
    No side effects.
    """
    evidence: dict[str, Any] = {}
    missing: list[str] = []

    # --- guard ---
    if daily_df is None or "Close" not in daily_df or len(daily_df) < 50:
        # need 50 for MA50
        if daily_df is None or len(daily_df) < 20:
            missing.append("daily_ohlcv_or_too_short")
        elif len(daily_df) < 50:
            missing.append("need_50_bars_for_MA50")
        return {
            "variant": "B",
            "approach": "MA trend + breakout Close",
            "state": "UNKNOWN",
            "confidence": "INSUFFICIENT",
            "evidence": evidence,
            "missing": missing,
        }

    close = pd.to_numeric(daily_df["Close"], errors="coerce").dropna()
    high = pd.to_numeric(daily_df["High"], errors="coerce").dropna() if "High" in daily_df else close
    vol = pd.to_numeric(daily_df["Volume"], errors="coerce").dropna() if "Volume" in daily_df else None

    if len(close) < 50:
        missing.append("need_50_bars_for_MA50")
        return {"variant": "B", "approach": "MA trend + breakout Close",
                "state": "UNKNOWN", "confidence": "INSUFFICIENT",
                "evidence": evidence, "missing": missing}

    ma20 = _ma(close, 20)
    ma50 = _ma(close, 50)

    last_close = float(close.iloc[-1])
    last_ma20 = float(ma20.iloc[-1]) if math.isfinite(float(ma20.iloc[-1])) else None
    last_ma50 = float(ma50.iloc[-1]) if math.isfinite(float(ma50.iloc[-1])) else None
    last_high = float(high.iloc[-1]) if len(high) == len(close) else last_close

    close_above_ma50 = bool(last_ma50 is not None and last_close > last_ma50)
    ma20_above_ma50 = bool(last_ma20 is not None and last_ma50 is not None and last_ma20 > last_ma50)
    close_above_ma20 = bool(last_ma20 is not None and last_close > last_ma20)

    # volume vs avg20
    volume_above_avg: bool | None = None
    volume_avg20: float | None = None
    last_volume: float | None = None
    if vol is not None and len(vol) >= 21:
        try:
            if len(vol) > 21:
                avg20 = float(vol.iloc[-21:-1].mean())
            else:
                avg20 = float(vol.iloc[:-1].mean())
            last_volume = float(vol.iloc[-1])
            volume_avg20 = round(avg20, 2) if math.isfinite(avg20) else None
            if math.isfinite(avg20) and avg20 > 0 and math.isfinite(last_volume):
                volume_above_avg = bool(last_volume > avg20)
        except Exception:
            pass

    # close within 2% of high (strong close) — fallback when volume not available
    close_within_2pct = bool(last_close >= 0.98 * last_high) if last_high else False
    volume_condition = (volume_above_avg is True) if strict_volume else (volume_above_avg is True or close_within_2pct)

    recent_10 = _pct(close, 10)
    recent_20 = _pct(close, 20)
    recent_5 = _pct(close, 5)

    legs = _swing_legs(close)
    w1 = _wave1_metrics(close, legs)

    # also refine tested_high_only using High series
    tested_high_only: bool | None = None
    close_above_wave1_high: bool | None = w1.get("close_above_wave1_high")
    if high is not None and len(high) == len(close) and w1.get("wave1_high") is not None:
        wh = float(w1["wave1_high"])
        tested_high_only = bool(last_high > wh and last_close <= wh)
        close_above_wave1_high = bool(last_close > wh)

    retrace = w1.get("retracement_pct")
    duration = w1.get("pullback_duration_days")
    holds_wave1_low = w1.get("holds_above_wave1_low")
    pullback_low = w1.get("pullback_low")

    # holds above MA50: pullback low (or current close if in pullback) stays above MA50
    # Use pullback_low if available else last_close; compare against MA50 at pullback end
    holds_above_ma50: bool | None = None
    if pullback_low is not None and last_ma50 is not None:
        holds_above_ma50 = bool(pullback_low > last_ma50)
    elif last_ma50 is not None:
        holds_above_ma50 = bool(last_close > last_ma50)

    # evidence bundle
    evidence.update({
        "last_close": round(last_close, 2),
        "last_high": round(last_high, 2),
        "ma20": round(last_ma20, 2) if last_ma20 is not None else None,
        "ma50": round(last_ma50, 2) if last_ma50 is not None else None,
        "close_above_ma50": close_above_ma50,
        "ma20_above_ma50": ma20_above_ma50,
        "close_above_ma20": close_above_ma20,
        "trend_filter_pass": bool(close_above_ma50 and ma20_above_ma50),
        "daily_advance_10d_pct": round(recent_10, 2) if recent_10 is not None else None,
        "daily_advance_20d_pct": round(recent_20, 2) if recent_20 is not None else None,
        "daily_rebound_5d_pct": round(recent_5, 2) if recent_5 is not None else None,
        "wave1_high": w1.get("wave1_high"),
        "wave1_low": w1.get("wave1_low"),
        "retracement_pct": retrace,
        "pullback_duration_days": duration,
        "holds_above_wave1_low": holds_wave1_low,
        "holds_above_ma50": holds_above_ma50,
        "close_above_wave1_high": close_above_wave1_high,
        "tested_high_only": tested_high_only,
        "volume_above_avg": volume_above_avg,
        "volume_avg_20": volume_avg20,
        "last_volume": last_volume,
        "close_within_2pct_of_high": close_within_2pct,
        "volume_condition_met": volume_condition if strict_volume else bool(volume_above_avg is True or close_within_2pct),
        "strict_volume": strict_volume,
    })

    # --- State selection (owner-priority order, now MA-gated) ---

    # Pullback present => evaluate Wave 2 first
    is_pullback = False
    if legs and legs[-1]["direction"] == -1:
        is_pullback = True
    # also consider 10d negative + recent drawdown as pullback hint
    if not is_pullback and recent_10 is not None and recent_10 < 0:
        # check if we just had a Wave1 before
        if any(l["direction"] == 1 for l in legs):
            is_pullback = True

    state: str | None = None
    confidence = "PARTIAL"

    if is_pullback:
        # retrace 30-60 + holds MA50 => NEAR_COMPLETION
        if retrace is not None and 30 <= retrace <= 60 and holds_above_ma50 and holds_wave1_low:
            if duration is not None and 5 <= duration <= 25:
                state = "WAVE_2_NEAR_COMPLETION"
                confidence = "HIGH"
            else:
                state = "WAVE_2_NEAR_COMPLETION"
                confidence = "MEDIUM"  # duration imperfect but retrace + MA hold
        elif retrace is not None and retrace < 30:
            state = "WAVE_2_FORMING"
            confidence = "MEDIUM"
        elif retrace is not None and 30 <= retrace <= 60 and (not holds_above_ma50 or not holds_wave1_low):
            # broke MA50 or Wave1 low => not near completion
            state = "WAVE_2_FORMING"
            confidence = "MEDIUM"
        elif retrace is not None and retrace > 60:
            state = "WAVE_4_CORRECTION" if not holds_wave1_low else "WAVE_2_FORMING"
            confidence = "MEDIUM"
        else:
            state = "WAVE_2_FORMING"
            confidence = "MEDIUM"
        # MA filter: if Close < MA50 during pullback, downgrade confidence
        if not close_above_ma50 and state == "WAVE_2_NEAR_COMPLETION":
            confidence = "MEDIUM"  # held retrace but lost MA50 => not HIGH
    else:
        # Not in pullback => check Early Wave3 vs Wave1
        # Early Wave3: Close > Wave1 high + Close > MA20 + volume
        if close_above_wave1_high and close_above_ma20:
            if volume_condition or not strict_volume:
                # need trend filter too for clean Early 3
                if close_above_ma50 and ma20_above_ma50:
                    state = "EARLY_WAVE_3"
                    confidence = "HIGH" if volume_above_avg else "MEDIUM"
                else:
                    state = "EARLY_WAVE_3"
                    confidence = "MEDIUM"  # breakout but trend filter weak
            else:
                # breakout without volume => not yet Early 3
                if close_above_ma50 and ma20_above_ma50:
                    state = "WAVE_1_ADVANCE"
                    confidence = "MEDIUM"
                else:
                    state = None
        elif tested_high_only:
            # wick only => stay Wave1
            if close_above_ma50 and ma20_above_ma50:
                state = "WAVE_1_ADVANCE"
                confidence = "MEDIUM"
        else:
            # Wave1 advance: Close > MA50 + MA20>MA50 + positive 10d
            if close_above_ma50 and ma20_above_ma50 and recent_10 is not None and recent_10 > 0:
                state = "WAVE_1_ADVANCE"
                confidence = "MEDIUM"
            elif close_above_ma50 and ma20_above_ma50:
                # trending but no measurable 10d advance yet => still forming?
                state = "WAVE_1_ADVANCE"
                confidence = "MEDIUM"

    if state is None:
        return {
            "variant": "B",
            "approach": "MA trend + breakout Close",
            "state": "UNKNOWN",
            "confidence": "INSUFFICIENT",
            "evidence": evidence,
            "missing": missing or ["no_ma_trend_or_breakout_signal"],
        }

    return {
        "variant": "B",
        "approach": "MA trend + breakout Close",
        "state": state,
        "confidence": confidence,
        "evidence": evidence,
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# Throwaway sample harness — synthetic + deterministic
# ---------------------------------------------------------------------------

def _make_df(prices: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    import datetime as dt
    n = len(prices)
    base = dt.date(2026, 1, 1)
    dates = [base + dt.timedelta(days=i) for i in range(n)]
    highs = [p * 1.01 for p in prices]
    lows = [p * 0.99 for p in prices]
    vols = volumes if volumes is not None else [1_000_000] * n
    return pd.DataFrame({
        "Date": dates,
        "Open": prices,
        "High": highs,
        "Low": lows,
        "Close": prices,
        "Volume": vols,
    })


def _run_samples():
    print("=" * 72)
    print("Variant B — MA Trend + Breakout Close  (throwaway prototype)")
    print("Rules: WAVE_1: Close>MA50 & MA20>MA50 | WAVE_2: 30-60% + hold MA50 | EARLY_3: Close>Wave1 high + Close>MA20 + vol")
    print("=" * 72)

    cases: list[tuple[str, pd.DataFrame]] = []

    # 1) WAVE_1_ADVANCE — steady uptrend, should pass MA filter
    # 60 days: MA50 = ~110 after ramp; MA20 > MA50; Close > MA50
    base = [100 + i * 0.6 + (i % 5) * 0.2 for i in range(60)]
    cases.append(("WAVE_1 ideal (expect WAVE_1_ADVANCE)", _make_df(base)))

    # 2) WAVE_1 but flat MA (no trend) — MA20 roughly = MA50 => should be UNKNOWN
    flat = [100] * 50 + [101, 101, 100.5, 101, 100.8, 101.2, 101, 100.9, 101.1, 101]
    cases.append(("WAVE_1 flat trend (expect UNKNOWN — fails MA20>MA50)", _make_df(flat)))

    # 3) WAVE_2_NEAR_COMPLETION — Wave1 100->130 (60d), then pullback 30-60% holding MA50
    # Build: 50d ramp 100->130, then 10d pullback 130->118 (40% retrace of 30 range = 12 pts)
    wave1 = [100 + i * 0.6 for i in range(50)]  # 100..129.4
    wave1_high = wave1[-1]
    wave1_low = wave1[0]
    wave1_range = wave1_high - wave1_low  # ~29.4
    # pullback 40% => 11.76 drop => low ~117.6
    pullback = [wave1_high - i * 1.2 for i in range(1, 11)]  # 10 days down
    prices3 = wave1 + pullback  # 60 bars
    # ensure MA50 still below pullback low
    cases.append(("WAVE_2 near-completion (40% retrace, hold MA50 → expect NEAR_COMPLETION)", _make_df(prices3)))

    # 4) WAVE_2 but broke MA50 — deep pullback 65% => WAVE_4 or FORMING, and breaks MA50
    wave1b = [100 + i * 0.8 for i in range(50)]  # 100..139.2 range 39.2
    deep_pull = [wave1b[-1] - i * 2.5 for i in range(1, 13)]  # 12 days deep
    prices4 = wave1b + deep_pull
    cases.append(("WAVE_2 deep 65% broke MA50 (expect FORMING or WAVE_4)", _make_df(prices4)))

    # 5) EARLY_WAVE_3 with volume — prior wave1 100->120, pullback 115, then close > wave1 high + >MA20 + vol spike
    w1 = [100 + i * 0.5 for i in range(40)]  # 100..119.5
    pb = [w1[-1] - i * 1.0 for i in range(1, 9)]  # pullback to ~111.5
    w3 = [pb[-1] + i * 1.8 for i in range(1, 13)]  # rally to ~132
    prices5 = w1 + pb + w3  # 61 bars
    vols5 = [1_000_000] * (len(prices5) - 1) + [2_500_000]  # spike last bar
    cases.append(("EARLY_WAVE_3 with volume spike (expect EARLY_WAVE_3)", _make_df(prices5, vols5)))

    # 6) EARLY_WAVE_3 wick only (tested high, close below wave1 high) — should NOT be EARLY_3
    w1c = [100 + i * 0.5 for i in range(40)]
    pbc = [w1c[-1] - i * 0.8 for i in range(1, 9)]
    w3c = [pbc[-1] + i * 0.6 for i in range(1, 8)]  # rally but stays below w1 high (119.5)
    # force last high wick above but close below
    prices6 = w1c + pbc + w3c
    df6 = _make_df(prices6)
    # manually set last High above wave1 high
    df6.loc[df6.index[-1], "High"] = max(w1c) + 2  # wick above
    df6.loc[df6.index[-1], "Close"] = max(w1c) - 1  # close below
    cases.append(("EARLY_WAVE_3 wick only (expect WAVE_1, not EARLY_3)", df6))

    # 7) EARLY_WAVE_3 without volume (strict) — Close > wave1 high + >MA20 but volume flat
    prices7 = w1 + pb + w3
    vols7 = [1_000_000] * len(prices7)  # no spike
    cases.append(("EARLY_WAVE_3 breakout no volume strict (expect WAVE_1 not EARLY_3)", _make_df(prices7, vols7)))

    for name, df in cases:
        res = classify_variant_B(df, strict_volume=True)
        print(f"\n--- {name}")
        print(f"  state={res['state']}  confidence={res['confidence']}")
        ev = res["evidence"]
        print(f"  Close={ev.get('last_close')}  MA20={ev.get('ma20')}  MA50={ev.get('ma50')}  trend_pass={ev.get('trend_filter_pass')}")
        print(f"  wave1_high={ev.get('wave1_high')} wave1_low={ev.get('wave1_low')} retrace={ev.get('retracement_pct')}% hold_MA50={ev.get('holds_above_ma50')}")
        print(f"  close>WH={ev.get('close_above_wave1_high')} close>MA20={ev.get('close_above_ma20')} vol>avg={ev.get('volume_above_avg')} vol_cond={ev.get('volume_condition_met')} tested_only={ev.get('tested_high_only')}")

    print("\n--- strict_volume=False check (case 7 should promote) ---")
    df7 = cases[6][1]
    res_loose = classify_variant_B(df7, strict_volume=False)
    print(f"  strict=False → state={res_loose['state']} confidence={res_loose['confidence']} vol_cond={res_loose['evidence'].get('volume_condition_met')}")

    print("\nDone. Variant B prototype — no DB writes.")


if __name__ == "__main__":
    _run_samples()
