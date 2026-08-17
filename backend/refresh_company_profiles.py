"""Refresh cached company identity metadata for Signalix detail cards.

SET OpenAPI v2 quote endpoint provides quote/fundamental ratios but not company
name, sector, industry, or business description. This utility keeps those
slow-changing fields in PostgreSQL, sourced from Yahoo Finance as a fallback.
It never participates in price/signal decisions.
"""
import argparse
import os
import time
from datetime import datetime, timezone

import psycopg2
import yfinance as yf

DSN = {"host": os.getenv("POSTGRES_HOST", "127.0.0.1"), "port": os.getenv("POSTGRES_PORT", "5432"),
       "user": os.getenv("POSTGRES_USER", "signalix"), "password": os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
       "dbname": os.getenv("POSTGRES_DB", "signalix")}
DDL = """CREATE TABLE IF NOT EXISTS company_profiles (
 symbol TEXT PRIMARY KEY, company_name TEXT, sector TEXT, industry TEXT,
 business_summary TEXT, source TEXT NOT NULL, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)"""
FAIL_DDL = """CREATE TABLE IF NOT EXISTS company_profile_refresh_failures (
 symbol TEXT PRIMARY KEY, last_error TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 1,
 last_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)"""

def clean(value, limit):
    value = " ".join(str(value or "").split())
    return value[:limit] if value else None

def main():
    ap = argparse.ArgumentParser(description="Cache non-price company identity metadata.")
    ap.add_argument("symbols", nargs="*", help="SET symbols; omit for symbols missing profiles")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.35)
    ap.add_argument("--all-ord", action="store_true", help="Use current ORD symbols from price_data; never scans DR/history")
    ap.add_argument("--retry-failed", action="store_true", help="Include failures whose retry time has arrived")
    args = ap.parse_args()
    pg = psycopg2.connect(**DSN); cur = pg.cursor(); cur.execute(DDL); cur.execute(FAIL_DDL); pg.commit()
    symbols = [x.upper() for x in args.symbols]
    if not symbols:
        # Explicitly constrain the automatic universe. Historical price_data also
        # contains thousands of expired DRs and legacy symbols.
        cur.execute("""SELECT DISTINCT p.symbol FROM price_data p
          LEFT JOIN company_profiles c ON c.symbol=p.symbol
          LEFT JOIN company_profile_refresh_failures f ON f.symbol=p.symbol
          WHERE p.instrument_type='ORD' AND c.symbol IS NULL
            AND (%s OR f.symbol IS NULL OR f.next_attempt_at <= NOW())
          ORDER BY p.symbol""", (args.retry_failed,))
        symbols = [r[0] for r in cur.fetchall()]
    elif args.all_ord:
        cur.execute("SELECT DISTINCT symbol FROM price_data WHERE instrument_type='ORD' AND symbol = ANY(%s)", (symbols,))
        symbols = [r[0] for r in cur.fetchall()]
    if args.limit:
        symbols = symbols[:args.limit]
    ok = failed = 0
    for n, symbol in enumerate(symbols, 1):
        try:
            info = yf.Ticker(symbol + ".BK").get_info()
            name = clean(info.get("longName") or info.get("shortName"), 180)
            sector = clean(info.get("sector"), 100)
            industry = clean(info.get("industry"), 140)
            summary = clean(info.get("longBusinessSummary"), 900)
            if not name:
                raise ValueError("no company name returned")
            cur.execute("""INSERT INTO company_profiles(symbol,company_name,sector,industry,business_summary,source,fetched_at)
                           VALUES(%s,%s,%s,%s,%s,'yfinance',NOW())
                           ON CONFLICT(symbol) DO UPDATE SET company_name=EXCLUDED.company_name,sector=EXCLUDED.sector,
                           industry=EXCLUDED.industry,business_summary=EXCLUDED.business_summary,source=EXCLUDED.source,fetched_at=EXCLUDED.fetched_at""",
                        (symbol, name, sector, industry, summary))
            pg.commit(); ok += 1; print(f"{n}/{len(symbols)} {symbol}: {name}")
        except Exception as exc:
            pg.rollback(); failed += 1
            msg = clean(exc, 300) or type(exc).__name__
            cur.execute("""INSERT INTO company_profile_refresh_failures(symbol,last_error,attempts,last_attempt_at,next_attempt_at)
              VALUES(%s,%s,1,NOW(),NOW()+INTERVAL '1 day')
              ON CONFLICT(symbol) DO UPDATE SET last_error=EXCLUDED.last_error,
              attempts=company_profile_refresh_failures.attempts+1,last_attempt_at=NOW(),
              next_attempt_at=NOW()+LEAST(INTERVAL '30 days', INTERVAL '1 day' * POWER(2, LEAST(company_profile_refresh_failures.attempts,5)))""", (symbol, msg))
            pg.commit(); print(f"{n}/{len(symbols)} {symbol}: failed {msg[:120]}")
        if n < len(symbols): time.sleep(args.sleep)
    print({"requested":len(symbols),"updated":ok,"failed":failed,"scope":"active_ord" if not args.symbols else "explicit","at":datetime.now(timezone.utc).isoformat()})
    cur.close(); pg.close()
if __name__ == '__main__': main()
