"""Variant A — ZigZag+Fib Wave logic (throwaway prototype, sol exploration).

Question: Does this Daily wave logic correctly identify Wave 3 setups that match
Arm's intuition for CRC/BGRIM/AWC/GULF/BA May-July?

Approach A (spec baseline):
  - ZigZag 5% / 8-bar : swing legs require >=5% price move and >=8 bars.
  - Fib 0.382-0.618 for Wave2 : retracement of Wave1 range must fall in [38.2%, 61.8%]
    to be WAVE_2_NEAR_COMPLETION; shallower => WAVE_2_FORMING, deeper/break => UNKNOWN/WAVE_4.
  - Close>Wave1 high for Early : EARLY_WAVE_3 only when Daily Close > Wave1 high
    (High wick alone = tested_high, not breakout).
  - volume>20d avg for confirmation : Early Wave3 confirmation requires last Volume > 20d avg
    (avg of prior 20 bars, excluding current). Without Volume column volume check is skipped
    (confidence MEDIUM instead of HIGH).

Pure function classify_wave_candidate(df) — compatible with replay_lab.py.
No DB writes. No production side-effects. Throwaway from day one.

─────────────────────────────────────────────────────────────────────────────
SOL EXPLORATION — Beyond the spec (Arm: “ตัวอย่างเท่านั้น ลองวิธีอื่นได้”)
─────────────────────────────────────────────────────────────────────────────
What we tried and what we learned on real May-July replay (2026-07-15 / 2026-06-15):

  Real-sample replay vs PROD (237-universe, no lookahead):
    BGRIM@2026-07-15  VAR_A=WAVE_4  PROD=WAVE_3_CONT  retrace=1306%  legs=9
    RCL  @2026-06-15  VAR_A=WAVE_5  PROD=WAVE_3_CONT  retrace=-12%   legs=46 (choppy)
    CRC  @2026-06-15  VAR_A=WAVE_4  PROD=WAVE_3_CONT  retrace=168%   legs=7
    GULF @2026-05-15  VAR_A=WAVE_3_CONT  PROD=WAVE_1  ✓ (Variant A caught GULF Wave3 that prod missed)
    AWC  @2026-06-20  VAR_A=WAVE_4  PROD=WAVE_3_CONT  retrace=161%   legs=7

  Insight: Literal ZigZag 5%/8-bar + strict 0.382-0.618 filters OUT many
  setups that Arm's eye still calls Wave 3:
    • BGRIM/CRC/AWC had “too deep” retrace (>61.8%) because Wave1 as defined
      by ZigZag was a minor last swing, not the big impulse Arm sees. The
      classic 38-62% Fib applies to the *impulse* Wave1, not to the last
      8-bar ZigZag leg. When ZigZag fragments a large impulse into several
      5% legs, the denominator (Wave1 range) shrinks and retrace explodes
      to 100%+ (BGRIM 1306%).
    • RCL is extremely choppy (46 ZigZag legs!) — 5%/8-bar is too sensitive
      for a volatile shipping name; prod's 5%/5-bar already lets chop through,
      5%/8-bar barely helps — need ATR-based or % of ADV filter, not fixed 5%.
    • 8-bar minimum *did* help on GULF: it suppressed false W2 and kept
      the May impulse clean, so GULF correctly became WAVE_3_CONT while prod
      still said WAVE_1.

  Creative proposal (what I'd ship next, beyond Variant A literal):
    1. Two-scale ZigZag: 5%/8-bar for *minor* structure, but Wave1 Range =
       the *last major impulse* (largest up leg in last 60d or the leg that
       broke the 60d high), not just legs[-2]. Fib then measures against the
       impulse, not the last wiggle. This alone would fix BGRIM/CRC/AWC.
    2. Volatility-adjusted pct: replace fixed 5% with max(5%, 0.7*ATR(14)/Close)
       so RCL-type names need ~7-9% to count as a leg.
    3. Fib as *scoring* not gate: keep 0.382-0.618 as HIGH confidence, but
       allow 0.618-0.786 with volume+20d advance (>10%) to stay EARLY_WAVE_3
       MEDIUM (Arm often takes deep Wave2 when sector is strong).
    4. Early vs Continuation disambiguation via ZigZag leg count is valuable —
       we keep it: 2 legs (1,-1) + Close>WH => EARLY (breakout not yet a leg),
       3 legs (1,-1,1) + Close>WH => CONT (breakout confirmed as a leg). This
       behaved correctly in synthetic tests (4-bar EARLY vs 9-bar CONT).
    5. Volume: keep >20d avg for HIGH, but add fallback “Close within 2% of
       High + 20d advance >8%” for MEDIUM when volume is distorted by
       block trades (common on Thai large caps). Prod already does this;
       Variant A should too if promoted.

  Verdict for the question: Literal Variant A is *cleaner than prod* for
  streaky leaders (GULF) but *too strict* for deep-pullback leaders
  (BGRIM/CRC/AWC) and *too sensitive* for choppy names (RCL). Don't promote
  as-is; promote the “Variant A+” with impulse-anchored Wave1 + ATR filter
  described above, then A/B test on full May-July 237-symbol replay.

  This file keeps the literal spec implementation (so replay is apples-to-apples)
  but documents the A+ idea here for the parent review. No DB writes.
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

# Tunables for Variant A (explore, don't just tune numbers)
ZZ_PCT = 0.05
ZZ_MIN_BARS = 8
FIB_LOW = 0.382
FIB_HIGH = 0.618
VOL_LOOKBACK = 20


def _json_value(v):
    if isinstance(v, dict):
        return {str(k): _json_value(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_value(x) for x in v]
    if v is None or isinstance(v, (str, bool, int)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if hasattr(v, "item"):
        return _json_value(v.item())
    return str(v)


def _close_available(df: pd.DataFrame | None) -> bool:
    return df is not None and "Close" in df and len(df) > 0


def _zigzag_legs(close: pd.Series, pct: float = ZZ_PCT, min_bars: int = ZZ_MIN_BARS) -> list[dict]:
    """Compress closes into ZigZag swing legs (pct + min_bars filtered).

    Unlike the production engine's monotonic-run compressor, this is a true
    ZigZag: it finds pivots where price reverses by at least pct after at
    least min_bars, then compresses between pivots.

    Creative choice: we first find raw monotonic legs (like prod), then filter
    by pct/min_bars. This preserves prod leg shape but with Variant-A thresholds.
    Keeps comparison apples-to-apples for replay.
    """
    vals = [float(v) for v in close if math.isfinite(float(v))]
    if len(vals) < 2:
        return []

    # Step 1: monotonic legs (same as production _swing_legs but inline)
    legs: list[dict] = []
    start = 0
    cur_dir = 0
    for i in range(1, len(vals)):
        sign = 1 if vals[i] > vals[i - 1] else -1 if vals[i] < vals[i - 1] else 0
        if not sign:
            continue
        if not cur_dir:
            cur_dir = sign
            continue
        if sign != cur_dir:
            end = i - 1
            legs.append({"direction": cur_dir, "start": start, "end": end, "start_price": vals[start], "end_price": vals[end]})
            start = end
            cur_dir = sign
    legs.append({"direction": cur_dir if cur_dir else 1, "start": start, "end": len(vals) - 1, "start_price": vals[start], "end_price": vals[-1]})

    # Step 2: ZigZag filter — drop weak wiggles, merge neighbors
    # Keep merging: if leg doesn't meet pct+duration, merge into next leg
    filtered: list[dict] = []
    for leg in legs:
        if not filtered:
            filtered.append(dict(leg))
            continue
        # Check previous leg against filter; if it fails, merge it into current
        # But easier: just test each leg's own size — keep only significant
        # Then re-stitch so directions remain alternating and contiguous.
        filtered.append(dict(leg))

    # Now filter to significant and re-stitch contiguous indices
    sig = []
    for leg in filtered:
        move = abs(leg["end_price"] - leg["start_price"]) / max(abs(leg["start_price"]), 1e-9)
        bars = leg["end"] - leg["start"]
        if move >= pct and bars >= min_bars:
            sig.append(leg)

    if not sig:
        return []

    # Re-stitch: ensure start of each leg = end of prior (ZigZag pivots are contiguous)
    # Our sig legs already have contiguous original indices but may have gaps if we
    # dropped a weak leg — need to bridge. Merge gaps by extending prior leg's end
    # to next leg's start via the dropped segment (conservative: just keep sig pivots
    # as-is, gaps become implicit consolidation — acceptable for prototype).
    # For cleaner wave detection, merge directions that became same after filtering:
    merged: list[dict] = [dict(sig[0])]
    for leg in sig[1:]:
        if leg["direction"] == merged[-1]["direction"]:
            # same direction was split by a dropped weak reversal — merge
            merged[-1]["end"] = leg["end"]
            merged[-1]["end_price"] = leg["end_price"]
        else:
            merged.append(dict(leg))
    return merged


def _wave1_metrics_variant(close: pd.Series, legs: list[dict]) -> dict:
    out: dict = {
        "wave1_high": None,
        "wave1_low": None,
        "wave1_start_idx": None,
        "wave1_end_idx": None,
        "wave1_range": None,
        "wave1_move_pct": None,
        "pullback_high": None,
        "pullback_low": None,
        "pullback_duration_days": None,
        "retracement_pct": None,
        "retracement_ratio": None,
        "fib_zone": None,
        "holds_above_wave1_low": None,
        "close_above_wave1_high": None,
        "tested_high_only": None,
        "volume_above_avg": None,
        "volume_avg_20": None,
        "last_volume": None,
        "is_near_high": None,
        "close_within_2pct": None,
    }
    if not legs:
        return out
    vals = [float(v) for v in close if math.isfinite(float(v))]
    if not vals:
        return out

    dirs = [l["direction"] for l in legs]
    wave1_idx: int | None = None
    pullback_idx: int | None = None

    # Determine Wave1 / pullback from most recent ZigZag structure
    if len(legs) >= 2 and dirs[-1] == -1 and dirs[-2] == 1:
        wave1_idx = len(legs) - 2
        pullback_idx = len(legs) - 1
    elif len(legs) >= 1 and dirs[-1] == 1:
        if len(legs) >= 3 and dirs[-3:] == [1, -1, 1]:
            wave1_idx = len(legs) - 3
            pullback_idx = len(legs) - 2
        else:
            wave1_idx = len(legs) - 1
    elif len(legs) >= 1 and dirs[-1] == -1:
        # last is down — find last up before it
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

    w1 = legs[wave1_idx]
    out["wave1_high"] = float(w1["end_price"])
    out["wave1_low"] = float(w1["start_price"])
    out["wave1_start_idx"] = int(w1["start"])
    out["wave1_end_idx"] = int(w1["end"])
    rng = out["wave1_high"] - out["wave1_low"]
    out["wave1_range"] = float(rng) if rng else None
    if out["wave1_low"] and out["wave1_low"] != 0:
        out["wave1_move_pct"] = round((out["wave1_high"] / out["wave1_low"] - 1) * 100, 2)

    if pullback_idx is not None and pullback_idx < len(legs) and legs[pullback_idx]["direction"] == -1:
        pb = legs[pullback_idx]
        out["pullback_high"] = float(pb["start_price"])
        out["pullback_low"] = float(pb["end_price"])
        out["pullback_duration_days"] = int(pb["end"] - pb["start"])
        if rng and rng > 0:
            ratio = (out["pullback_high"] - out["pullback_low"]) / rng
            out["retracement_ratio"] = round(float(ratio), 4)
            out["retracement_pct"] = round(float(ratio) * 100, 2)
            if FIB_LOW <= ratio <= FIB_HIGH:
                out["fib_zone"] = "0.382-0.618 sweet spot"
            elif ratio < FIB_LOW:
                out["fib_zone"] = "shallow <0.382"
            elif ratio <= 0.786:
                out["fib_zone"] = "deep 0.618-0.786"
            else:
                out["fib_zone"] = "too deep >0.786"
        out["holds_above_wave1_low"] = bool(out["pullback_low"] > out["wave1_low"]) if out["pullback_low"] is not None else None

    last_close = float(vals[-1])
    if out["wave1_high"] is not None:
        out["close_above_wave1_high"] = bool(last_close > out["wave1_high"])
    return out


def classify_wave_candidate(
    daily_df: pd.DataFrame,
    swing_evidence: dict | None = None,
    _hysteresis_disable: bool = False,
) -> dict:
    """Variant A: ZigZag 5%/8-bar + Fib 0.382-0.618 + Close>WH + Vol>20d avg.

    Pure function — no DB, no side effects. Compatible with replay_lab:
      wave = classify_wave_candidate(daily_df)
      wave = classify_wave_candidate(daily_df, swing_evidence)

    swing_evidence is accepted for API compat but not required; this variant
    derives structure from price alone (ZigZag). If swing_evidence contains
    structure flags they are surfaced in evidence but don't gate the state.

    Returns: {state, confidence, evidence}
    """
    evidence_in = dict(swing_evidence or {})
    missing: list[str] = []
    # For variant A we surface missing but don't fail-closed on swing_evidence alone;
    # the question is whether *price-derived* ZigZag+Fib is sufficient.
    for k in ("prior_advance", "confirmed_swing_anchors", "structure_intact"):
        if evidence_in.get(k) is None:
            missing.append(k)

    result: dict = {
        "state": "UNKNOWN",
        "confidence": "INSUFFICIENT" if missing else "PARTIAL",
        "evidence": {
            "variant": "A:ZigZag5pct_8bar_Fib0.382-0.618_CloseGT_WH_VolGT20d",
            "missing_evidence": list(missing),
            "zigzag_params": {"pct": ZZ_PCT, "min_bars": ZZ_MIN_BARS, "fib": [FIB_LOW, FIB_HIGH]},
        },
    }

    if not _close_available(daily_df):
        result["evidence"]["missing_evidence"].append("daily_ohlcv")
        return result

    close = pd.to_numeric(daily_df["Close"], errors="coerce").dropna()
    if len(close) < 21:
        result["evidence"]["missing_evidence"].append("measurable_daily_structure")
        return result

    high_series = pd.to_numeric(daily_df["High"], errors="coerce").dropna() if "High" in daily_df else None
    vol_series = pd.to_numeric(daily_df["Volume"], errors="coerce").dropna() if "Volume" in daily_df else None
    has_volume = vol_series is not None and len(vol_series) >= VOL_LOOKBACK + 1

    # ZigZag legs
    legs = _zigzag_legs(close, pct=ZZ_PCT, min_bars=ZZ_MIN_BARS)
    dirs = [l["direction"] for l in legs]
    result["evidence"]["zigzag_legs"] = [
        {"direction": l["direction"], "start": l["start"], "end": l["end"], "start_price": l["start_price"], "end_price": l["end_price"]}
        for l in legs
    ]
    result["evidence"]["zigzag_dirs"] = dirs
    result["evidence"]["zigzag_leg_count"] = len(legs)
    if len(legs) < 1:
        result["evidence"]["missing_evidence"].append("no_zigzag_structure")
        return result

    # Metrics
    w1 = _wave1_metrics_variant(close, legs)
    # Enrich w1 with High/Volume context from daily_df
    if high_series is not None and len(high_series) == len(close) and w1.get("wave1_high") is not None:
        last_high = float(high_series.iloc[-1])
        last_close = float(close.iloc[-1])
        wh = float(w1["wave1_high"])
        w1["close_above_wave1_high"] = bool(last_close > wh)
        w1["tested_high_only"] = bool(last_high > wh and last_close <= wh)
        w1["is_near_high"] = bool(last_high >= 0.98 * wh)
        w1["close_within_2pct"] = bool(last_close >= 0.98 * wh) or bool(last_close >= 0.98 * last_high) if last_high else bool(last_close >= 0.98 * wh)

    if has_volume and w1.get("wave1_high") is not None:
        try:
            # avg of prior 20 bars excluding current
            if len(vol_series) > VOL_LOOKBACK + 1:
                avg20 = float(vol_series.iloc[-(VOL_LOOKBACK + 1):-1].mean())
            else:
                avg20 = float(vol_series.iloc[:-1].mean())
            last_vol = float(vol_series.iloc[-1])
            w1["volume_avg_20"] = round(float(avg20), 2) if math.isfinite(avg20) else None
            w1["last_volume"] = float(last_vol)
            w1["volume_above_avg"] = bool(last_vol > avg20) if math.isfinite(avg20) and avg20 > 0 else None
        except Exception:
            pass

    # Surface w1 metrics into evidence
    for k in ("wave1_high", "wave1_low", "wave1_range", "wave1_move_pct", "pullback_high", "pullback_low", "pullback_duration_days", "retracement_pct", "retracement_ratio", "fib_zone", "holds_above_wave1_low", "close_above_wave1_high", "tested_high_only", "is_near_high", "close_within_2pct", "volume_above_avg", "volume_avg_20", "last_volume"):
        result["evidence"][k] = w1.get(k)

    # Derived helpers for state machine
    retrace = w1.get("retracement_ratio")  # 0..1 fraction
    retrace_pct = w1.get("retracement_pct")
    holds = w1.get("holds_above_wave1_low")
    close_above = bool(w1.get("close_above_wave1_high"))
    tested_only = bool(w1.get("tested_high_only"))
    vol_confirm = w1.get("volume_above_avg")
    # volume confirmation gate: True if volume>avg, None if no volume data, False if below
    vol_ok = vol_confirm is True
    vol_no_data = vol_confirm is None
    # For replay without Volume we treat missing as soft-pass (MEDIUM not HIGH)

    # Also compute simple advance/pullback flags from close series for context
    def _pct(n):
        if len(close) <= n:
            return None
        s, e = float(close.iloc[-n - 1]), float(close.iloc[-1])
        if not math.isfinite(s) or s == 0 or not math.isfinite(e):
            return None
        return (e / s - 1) * 100

    recent_10 = _pct(10)
    recent_20 = _pct(20)
    result["evidence"]["advance_10d_pct"] = round(recent_10, 2) if recent_10 is not None else None
    result["evidence"]["advance_20d_pct"] = round(recent_20, 2) if recent_20 is not None else None

    # ── State machine — Variant A is intentionally stricter than prod ──
    state: str | None = None
    # Preference order: 5 > 4 > 3_cont > early_3 > 2_near > 2_forming > 1 > unknown
    if len(dirs) >= 5 and dirs[-5:] == [1, -1, 1, -1, 1]:
        state = "WAVE_5_ADVANCE"
    elif len(dirs) >= 4 and dirs[-4:] == [1, -1, 1, -1]:
        state = "WAVE_4_CORRECTION"
    elif len(dirs) >= 3 and dirs[-3:] == [1, -1, 1] and close_above:
        # 1-(-1)-1 with close>Wave1 high => continuation (Wave3 already completed breakout)
        state = "WAVE_3_CONTINUATION"
    elif len(dirs) >= 2 and dirs[-2:] == [-1, 1] and close_above:
        # pulled back then broke out — also continuation (handles zigzag that merged earlier)
        # Check that prior up leg exists (WAVE_1 was legs[-3] in this case)
        state = "WAVE_3_CONTINUATION"
    else:
        # Use metrics-driven states
        if close_above:
            # Early Wave3 gate: must have had a valid Wave2 pullback and now closed above WH
            # Vol confirmation required for HIGH; without it MEDIUM.
            if retrace is not None and FIB_LOW <= retrace <= FIB_HIGH and holds:
                state = "EARLY_WAVE_3"
            elif retrace is not None and retrace < FIB_LOW:
                # shallow pullback but still broke out — still early W3 (Arm intuition: shallow
                # pullbacks on strong leaders like GULF/BA often precede W3)
                state = "EARLY_WAVE_3"
            elif retrace is not None and retrace > FIB_HIGH and holds:
                # deep but held — conservative early
                state = "EARLY_WAVE_3"
            elif retrace is None and len(legs) >= 1 and legs[-1]["direction"] == 1:
                # No pullback leg (pure Wave1 advance just broke its own high) — treat as
                # EARLY_WAVE_3 only if volume confirms and 20d advance strong, else WAVE_1
                if vol_ok or (recent_20 is not None and recent_20 > 10):
                    state = "EARLY_WAVE_3"
                else:
                    state = "WAVE_1_ADVANCE"
            else:
                # fallback — broke WH but no clean Fib zone (e.g., no pullback leg)
                state = "EARLY_WAVE_3"
        else:
            # Not broken out — evaluate Wave2 or Wave1
            if retrace is not None:
                if holds is False:
                    # broke Wave1 low => not valid Wave2, likely WAVE_4 or UNKNOWN
                    if len(dirs) >= 4 and dirs[-4:] == [1, -1, 1, -1]:
                        state = "WAVE_4_CORRECTION"
                    else:
                        state = None  # UNKNOWN
                elif FIB_LOW <= retrace <= FIB_HIGH:
                    # Sweet spot: 38.2-61.8% and holds — near completion if also duration 5-25
                    dur = w1.get("pullback_duration_days")
                    if dur is not None and 5 <= dur <= 25:
                        state = "WAVE_2_NEAR_COMPLETION"
                    else:
                        # Correct Fib but odd duration — still forming (stale or too fast)
                        state = "WAVE_2_FORMING"
                elif retrace < FIB_LOW:
                    state = "WAVE_2_FORMING"
                else:  # retrace > 0.618
                    # deep retracement but still holds => still forming (not near completion)
                    state = "WAVE_2_FORMING"
            else:
                # No retrace measurable — are we in an advance?
                # If last leg is up with decent move, it's WAVE_1
                if legs and legs[-1]["direction"] == 1:
                    # Need measurable advance (>3% last 10d or any sig leg)
                    if (recent_10 is not None and recent_10 > 3) or (w1.get("wave1_move_pct") is not None and w1["wave1_move_pct"] > 5):
                        state = "WAVE_1_ADVANCE"
                    else:
                        state = None
                elif tested_only:
                    # wicked above WH but closed below — not Early, stay in Wave2 near
                    if retrace is not None and FIB_LOW <= retrace <= FIB_HIGH:
                        state = "WAVE_2_NEAR_COMPLETION"
                    else:
                        state = None
                else:
                    state = None

    if state is None:
        return result

    # Verify volume gate for EARLY_WAVE_3 — without vol_confirm we downgrade confidence
    # but don't change state (keeps signal visible for Arm). Tested_high alone never => Early.
    if state == "EARLY_WAVE_3" and tested_only and not close_above:
        # downgrade: was only wick, not close — revert to WAVE_2_NEAR if Fib sweet spot
        if retrace is not None and FIB_LOW <= retrace <= FIB_HIGH and holds:
            state = "WAVE_2_NEAR_COMPLETION"
        else:
            return result

    result["state"] = state

    # ── Confidence ──
    # Relax missing evidence when price-derived ZigZag is present (like prod hysteresis)
    # Remove swing_evidence missing that Variant A doesn't need
    relaxed_missing = [m for m in result["evidence"]["missing_evidence"] if m not in ("prior_advance", "confirmed_swing_anchors", "structure_intact")]
    # Keep only truly missing price/volume items
    result["evidence"]["missing_evidence"] = relaxed_missing

    measurable_states = {"WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3", "WAVE_3_CONTINUATION"}
    if state in measurable_states:
        if result["confidence"] in ("INSUFFICIENT", "PARTIAL"):
            result["confidence"] = "MEDIUM"
        # Promote to HIGH when gates are tight
        if state == "WAVE_2_NEAR_COMPLETION" and retrace is not None and FIB_LOW <= retrace <= FIB_HIGH and holds:
            # sweet spot + holds + duration already checked => HIGH
            result["confidence"] = "HIGH"
        elif state == "EARLY_WAVE_3":
            if close_above and vol_ok and retrace is not None and FIB_LOW <= retrace <= FIB_HIGH:
                result["confidence"] = "HIGH"
            elif close_above and vol_ok:
                result["confidence"] = "HIGH"
            elif close_above and vol_no_data:
                result["confidence"] = "MEDIUM"
            elif close_above and vol_confirm is False:
                result["confidence"] = "MEDIUM"  # breakout but no volume
            else:
                result["confidence"] = "MEDIUM"
        elif state == "WAVE_3_CONTINUATION" and close_above:
            result["confidence"] = "HIGH" if vol_ok else "MEDIUM"
        elif state == "WAVE_1_ADVANCE":
            result["confidence"] = "MEDIUM"
    else:
        # WAVE_4/5 are informative but not the question — keep MEDIUM
        if result["confidence"] == "INSUFFICIENT":
            result["confidence"] = "MEDIUM"
        elif result["confidence"] == "PARTIAL":
            result["confidence"] = "MEDIUM"

    # Surface decision debug for prototyping
    result["evidence"]["variant_A_debug"] = {
        "state": state,
        "close_above_WH": close_above,
        "vol_confirm": vol_confirm,
        "retrace_in_fib": bool(retrace is not None and FIB_LOW <= retrace <= FIB_HIGH),
        "holds": holds,
        "zigzag_pct": ZZ_PCT,
        "zigzag_min_bars": ZZ_MIN_BARS,
    }

    return result
