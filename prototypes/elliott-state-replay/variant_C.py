"""Prototypes copy of Variant C — importable as prototypes.elliott-state-replay.variant_C
This file re-exports backend/elliott_variant_C for replay_lab and standalone testing.
No DB writes; pure function wrapper.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend on path
_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from elliott_variant_C import classify_wave_candidate, VARIANT, SWING_PCT, SWING_BARS, HYSTERESIS_WINDOW, NEAR_HIGH_THR, CLOSE_THR  # noqa: F401,E402

__all__ = ["classify_wave_candidate", "VARIANT"]

if __name__ == "__main__":
    # quick smoke test with synthetic data
    import pandas as pd

    def make_df(closes, volumes=None, highs=None):
        import datetime as dt
        n = len(closes)
        base = dt.date(2026, 1, 1)
        dates = [base + dt.timedelta(days=i) for i in range(n)]
        data = {"Close": closes}
        data["High"] = highs if highs is not None else [c * 1.01 for c in closes]
        data["Low"] = [c * 0.99 for c in closes]
        data["Open"] = closes
        data["Volume"] = volumes if volumes is not None else [1_000_000] * n
        data["Date"] = dates
        return pd.DataFrame(data)

    # Case 1: WAVE_1 advance — 10d rise, strong volume on up legs
    closes = [10 + i * 0.5 for i in range(25)]  # steady advance
    vols = [1_000_000] * 15 + [3_000_000] * 10  # high volume on advance
    df = make_df(closes, vols)
    r = classify_wave_candidate(df)
    print("WAVE_1 case:", r["state"], r["confidence"], r["evidence"].get("volume_avg20"), "sig legs", len(r["evidence"].get("significant_swing_legs", [])))

    # Case 2: weak-volume advance (should be filtered)
    vols_weak = [3_000_000] * 15 + [500_000] * 10  # weak volume on advance leg
    df2 = make_df(closes, vols_weak)
    r2 = classify_wave_candidate(df2)
    print("Weak volume:", r2["state"], r2["confidence"], "sig legs", len(r2["evidence"].get("significant_swing_legs", [])), "fallback", r2["evidence"].get("volume_filter_fallback"))

    # Case 3: Early wave 3 near-high with volume vs without
    # Build wave1 high 20 then pullback to 14 then reclaim 19.8 (0.99*20) with strong close
    closes3 = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 19, 18, 17, 16, 15, 14, 15, 16, 17, 18, 19, 19.8, 19.9, 20.1]
    highs3 = [c * 1.02 for c in closes3]
    highs3[-2] = 19.9  # High 19.9 >=0.98*20=19.6
    vols3 = [1_000_000] * 24 + [3_000_000]
    df3 = make_df(closes3, vols3, highs3)
    r3 = classify_wave_candidate(df3)
    print("Near-high Early:", r3["state"], r3["confidence"], r3["evidence"].get("near_high_breakout"), r3["evidence"].get("is_near_high"), r3["evidence"].get("volume_above_avg"))

    # Case 4: Hysteresis — WAVE_1 then flat 3 days
    closes4 = [10 + i * 0.5 for i in range(22)] + [21, 21, 21]
    vols4 = [2_000_000] * 25
    df4 = make_df(closes4, vols4)
    r4 = classify_wave_candidate(df4)
    print("Hysteresis:", r4["state"], r4["confidence"], r4["evidence"].get("wave1_persistence"), r4["evidence"].get("wave1_hysteresis_window"))

    print("Variant:", VARIANT, f"{SWING_PCT}/{SWING_BARS} bars, hysteresis {HYSTERESIS_WINDOW}d, near-high {NEAR_HIGH_THR}/{CLOSE_THR}")
    print("All synthetic checks done — no DB writes.")
