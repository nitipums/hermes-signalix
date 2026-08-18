"""Smoke/integration test for the DB-backed screening engine.

Run from host (with POSTGRES_HOST=127.0.0.1) or inside the backend container:
    POSTGRES_HOST=127.0.0.1 POSTGRES_PASSWORD=signalix_pass \
        /root/.venv_img/bin/python test_screening.py
"""
import os
import sys

# When run from host, point at the mapped port.
if os.getenv("POSTGRES_HOST") is None:
    os.environ["POSTGRES_HOST"] = "127.0.0.1"
if os.getenv("POSTGRES_PASSWORD") is None:
    os.environ["POSTGRES_PASSWORD"] = "signalix_pass"

import pytest
from screening import analyze_symbol_db, scan_universe, load_symbol, load_market


pytestmark = pytest.mark.integration


def test_load_symbol():
    df = load_symbol("SET")
    assert df is not None and len(df) > 1000, "SET index should have long history"
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    print(f"[ok] load_symbol SET -> {len(df)} rows, last {df.index[-1].date()}")


def test_analyze_single():
    r = analyze_symbol_db("PTT")  # plain ticker, long history
    if r is None:
        print("[skip] PTT not present / insufficient history")
        return
    tt = r["trend_template"]
    assert "conditions_met" in tt and "rs_rating" in tt
    print(f"[ok] analyze PTT -> close={r['close']} TT={tt['conditions_met']}/8 "
          f"RS={tt['rs_rating']} VCP={r['vcp']['is_vcp']} stop={r['suggested_stop']}")


def test_scan():
    cands, near = scan_universe(min_conditions=8)
    print(f"[ok] scan min_conditions=8 -> {len(cands)} candidates, {len(near)} near-miss")
    for c in cands[:10]:
        tt = c["trend_template"]
        print(f"     {c['symbol']:10s} {c['close']:>9.2f} RS={tt['rs_rating']:5.1f} "
              f"TT={tt['conditions_met']}/8 VCP={c['vcp']['is_vcp']}")
    # also report near-misses for visibility
    near_rescan = [c for c in scan_universe(min_conditions=6)[0] if c["trend_template"]["conditions_met"] == 6]
    print(f"[info] near-miss (6/8): {len(near_rescan)} symbols")


if __name__ == "__main__":
    print("=== Signalix screening smoke test ===")
    test_load_symbol()
    test_analyze_single()
    test_scan()
    print("=== done ===")
