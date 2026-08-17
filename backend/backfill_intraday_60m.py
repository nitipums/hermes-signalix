#!/usr/bin/env python3
"""One-shot 60m intraday backfill for the FULL ORD universe (1-time).

Reuses the day-fetch concurrency pattern (ThreadPoolExecutor, 30 workers) that
made the Saturday Settrade EOD run fast. Only the interval/limit differ:
  - interval='60m'  (not '1d')
  - limit=400        (≈100 trading sessions of hourly bars)
Upsert is idempotent (ON CONFLICT DO UPDATE), so re-running is safe.
"""
from __future__ import annotations
import os
import sys
import time
import json
import uuid
import datetime as dt
import concurrent.futures

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if os.getenv("POSTGRES_HOST", "postgres") == "postgres":
    os.environ["POSTGRES_HOST"] = "127.0.0.1"

import update_data as u  # reuse _settrade_market, _parse_settrade_intraday, insert_intraday_rows, get_pg

WORKERS = int(os.getenv("SETTRADE_DAILY_WORKERS", "30"))
LIMIT = int(os.getenv("BACKFILL_60M_LIMIT", "400"))
INTERVAL = "60m"
MARKET = "TH"
SLEEP_PER_SYMBOL = float(os.getenv("SETTRADE_SLEEP_SECONDS", "0.1"))


def full_ord_universe(pg):
    """Every ORD symbol present in price_data (no recency filter)."""
    cur = pg.cursor()
    cur.execute(
        "SELECT DISTINCT symbol, instrument_type FROM price_data "
        "WHERE market=%s AND instrument_type='ORD' ORDER BY symbol",
        (MARKET,),
    )
    syms = cur.fetchall()
    cur.close()
    return syms


def fetch_one(market, sym, itype):
    try:
        with u.settrade_request_timeout():
            res = market.get_candlestick(
                symbol=sym, interval=INTERVAL, limit=LIMIT,
                normalized=u.SETTRADE_NORMALIZED,
            )
        return sym, u._parse_settrade_intraday(sym, INTERVAL, res, {}), None
    except Exception as exc:
        return sym, None, repr(exc)[:200]


def main() -> int:
    started = dt.datetime.now(dt.timezone.utc)
    run_id = f"backfill-60m-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    print(f"run_id={run_id} workers={WORKERS} limit={LIMIT} interval={INTERVAL}")
    pg = u.get_pg()
    try:
        u.ensure_intraday_table(pg)
        syms = full_ord_universe(pg)
        print(f"universe ORD symbols: {len(syms)}")
        market = u._settrade_market()

        # Reuse the day-fetch concurrency shape: a bounded thread pool of WORKERS.
        jobs = [(s, t) for s, t in syms]
        stats = {"offered": 0, "inserted": 0, "updated": 0, "failed": 0,
                 "empty": 0, "errors": []}
        all_rows = []
        failed_syms = []

        def worker(job):
            # NOTE: do NOT wrap in u.settrade_request_timeout() here — that uses
            # signal.setitimer(SIGALRM) which only works in the MAIN thread.
            # Inside ThreadPoolExecutor worker threads it raises
            # "signal only works in main thread". The day-fetch path
            # (fetch_settrade) avoids this same trap by calling get_candlestick
            # directly when worker_count > 1. The SDK carries its own HTTP
            # timeout via _install_settrade_http_timeout, so requests are still
            # bounded.
            sym, itype = job
            try:
                res = market.get_candlestick(
                    symbol=sym, interval=INTERVAL, limit=LIMIT,
                    normalized=u.SETTRADE_NORMALIZED,
                )
                rows = u._parse_settrade_intraday(sym, INTERVAL, res, {})
                return sym, rows, None
            except Exception as exc:
                return sym, None, repr(exc)[:200]

        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(worker, job): job for job in jobs}
            for fut in concurrent.futures.as_completed(futures):
                sym, rows, err = fut.result()
                done += 1
                if err:
                    stats["failed"] += 1
                    failed_syms.append(sym)
                    stats["errors"].append(f"{sym}: {err}")
                    if done % 100 == 0 or len(failed_syms) <= 5:
                        print(f"  ! {sym} failed: {err}")
                elif not rows:
                    stats["empty"] += 1
                else:
                    all_rows.extend(rows)
                    stats["offered"] += len(rows)
                if done % 200 == 0:
                    print(f"  ... {done}/{len(jobs)} symbols | offered={stats['offered']} failed={stats['failed']}")
        print(f"fetch complete: offered_rows={stats['offered']} empty={stats['empty']} failed={stats['failed']}")

        # Batch upsert (idempotent).
        if all_rows:
            bstats = {}
            u.insert_intraday_rows(pg, all_rows, stats=bstats, record_fetch_status=True)
            stats["inserted"] = bstats.get("intraday_inserted", 0)
            stats["updated"] = bstats.get("intraday_updated", 0)
            print(f"upsert: inserted={stats['inserted']} updated={stats['updated']}")

        # Coverage report.
        cur = pg.cursor()
        cur.execute("SELECT COUNT(DISTINCT symbol) FROM intraday_price_data WHERE interval=%s", (INTERVAL,))
        have = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM intraday_price_data WHERE interval=%s", (INTERVAL,))
        total_rows = cur.fetchone()[0]
        cur.close()
        print(f"COVERAGE: symbols_with_60m={have} (was {len(syms)-stats['empty']-stats['failed']} before this run's new names) total_60m_rows={total_rows}")
        if failed_syms:
            print(f"FAILED ({len(failed_syms)}): {','.join(failed_syms[:50])}")
        print(json.dumps({"run_id": run_id, **stats, "failed_symbols": failed_syms}, default=str))
        return 0
    finally:
        pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
