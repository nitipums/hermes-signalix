#!/usr/bin/env python3
"""One-shot intraday history fill for newly promoted Signalix symbols.

This is deliberately separate from the frequent refresh timer. The normal
refresh requests eight 60m bars; this script is for a symbol that newly enters
the active bucket or has insufficient 60m history.

Example:
  python fill_intraday_history.py --symbols TFG,STGT --limit 48

Do not schedule this every few minutes: it is an exceptional, bounded fill.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys

# Host-side utility: Compose's `postgres` DNS name is unavailable here.
HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
if os.getenv("POSTGRES_HOST", "postgres") == "postgres":
    os.environ["POSTGRES_HOST"] = "127.0.0.1"
import update_data as u  # noqa: E402

REQUIRED = {"60m": 8}


def groups_for_mode(mode: str) -> list[str]:
    return list(u.INTRADAY_GROUPS[mode])


def symbols_from_scan(mode: str) -> list[str]:
    return u._intraday_shortlist(mode)


def counts(symbols: list[str], interval: str) -> dict[str, int]:
    if not symbols:
        return {}
    pg = u.get_pg()
    try:
        with pg.cursor() as cur:
            cur.execute(
                "SELECT symbol, count(*) FROM intraday_price_data "
                "WHERE interval=%s AND symbol = ANY(%s) GROUP BY symbol",
                (interval, symbols),
            )
            return {row[0]: int(row[1]) for row in cur.fetchall()}
    finally:
        pg.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", choices=("60m",), default="60m")
    ap.add_argument("--mode", choices=("active",), default="active")
    ap.add_argument("--symbols", default="", help="comma-separated symbols; preferred explicit input")
    ap.add_argument("--missing-only", action="store_true", help="from current scan bucket, select symbols below threshold")
    ap.add_argument("--limit", type=int, default=120, help="history bars requested for each selected symbol")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.symbols and not args.missing_only:
        ap.error("provide --symbols or --missing-only")
    if args.limit < REQUIRED[args.interval]:
        ap.error(f"--limit must be at least {REQUIRED[args.interval]} for {args.interval}")

    if args.symbols:
        selected = list(dict.fromkeys(s.strip().upper() for s in args.symbols.split(",") if s.strip()))
    else:
        selected = symbols_from_scan(args.mode)
    have = counts(selected, args.interval)
    if args.missing_only:
        selected = [s for s in selected if have.get(s, 0) < REQUIRED[args.interval]]

    print(f"history-fill interval={args.interval} limit={args.limit} selected={len(selected)}")
    print("symbols:", ",".join(selected) if selected else "none")
    if args.dry_run or not selected:
        return 0

    # Fetch one symbol at a time through the same bounded Settrade path. This
    # keeps failures isolated and preserves rows already inserted.
    pg = u.get_pg()
    try:
        u.ensure_intraday_table(pg)
        market = u._settrade_market()
        stats = {"bad_row": 0, "intraday_failed": 0}
        total = 0
        for symbol in selected:
            try:
                with u.settrade_request_timeout():
                    res = market.get_candlestick(symbol=symbol, interval=args.interval,
                                                  limit=args.limit, normalized=u.SETTRADE_NORMALIZED)
                rows = u._parse_settrade_intraday(symbol, args.interval, res, stats)
                total += u.insert_intraday_rows(pg, rows)
                print(f"{symbol}: offered={len(rows)}")
            except Exception as exc:
                stats["intraday_failed"] += 1
                print(f"{symbol}: FAILED {repr(exc)[:160]}")
        print(f"history-fill complete: rows_offered={total} failed={stats['intraday_failed']}")
        return 1 if stats["intraday_failed"] else 0
    finally:
        pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
