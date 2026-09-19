#!/usr/bin/env python3
"""Freeze deterministic 1Y Daily OHLCV fixtures for Elliott contract tests.

Read-only: reuses replay_lab's PIT loaders (SELECT-only, readonly session).
Writes backend/fixtures/elliott/<SYMBOL>_daily_1y.json (last 260 rows, no timestamps
inside the fixture so it stays byte-deterministic).

Usage: /root/signalix/.analysis-venv/bin/python backend/fixtures/elliott/generate_fixtures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO / "prototypes" / "elliott-state-replay"))

import replay_lab  # noqa: E402  (bootstraps backend engines path)

AS_OF = "2026-08-28"
SYMBOLS = ["CRC", "BGRIM", "AWC"]
MAX_ROWS = 260  # 1Y trading days headroom; wave1 anchor scans last 120 bars
OUT_DIR = Path(__file__).resolve().parent


def main() -> int:
    import elliott_structure_engine  # noqa: E402

    conn = replay_lab._get_conn()
    try:
        for symbol in SYMBOLS:
            daily_df, latest_date = replay_lab.load_daily_pit(conn, symbol, replay_lab.dt.date.fromisoformat(AS_OF))
            if daily_df is None or len(daily_df) == 0:
                print(f"{symbol}: NO DATA", file=sys.stderr)
                return 1
            full_state = elliott_structure_engine.classify_wave_candidate(daily_df)
            trimmed = daily_df.tail(MAX_ROWS).reset_index(drop=True)
            trim_state = elliott_structure_engine.classify_wave_candidate(trimmed)
            same = (full_state.get("state") == trim_state.get("state"))
            ev = full_state.get("evidence", {})
            tev = trim_state.get("evidence", {})
            keys = ("retracement_pct", "close_above_wave1_high", "holds_above_wave1_low", "wave1_low", "wave1_high")
            same = same and all(ev.get(k) == tev.get(k) for k in keys)
            rows = [
                {
                    "date": str(idx.date() if hasattr(idx, "date") else idx),
                    "open": float(r["Open"]),
                    "high": float(r["High"]),
                    "low": float(r["Low"]),
                    "close": float(r["Close"]),
                    "volume": int(r["Volume"]) if r.get("Volume") == r.get("Volume") else None,
                }
                for idx, r in trimmed.iterrows()
            ]
            fixture = {
                "symbol": symbol,
                "as_of": AS_OF,
                "interval": "1d",
                "source": "price_data market=TH via replay_lab.load_daily_pit (read-only)",
                "rows": rows,
            }
            out = OUT_DIR / f"{symbol}_daily_1y.json"
            out.write_text(json.dumps(fixture, indent=1, sort_keys=True) + "\n")
            print(
                f"{symbol}: rows={len(rows)} latest={rows[-1]['date']} "
                f"full_state={full_state.get('state')} trim_state={trim_state.get('state')} same={same} "
                f"retrace={ev.get('retracement_pct')} close_above_wh={ev.get('close_above_wave1_high')} "
                f"holds={ev.get('holds_above_wave1_low')} tested_only={ev.get('tested_high_only')} "
                f"w1_low={ev.get('wave1_low')} w1_high={ev.get('wave1_high')}"
            )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
