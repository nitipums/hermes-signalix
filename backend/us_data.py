"""US daily-EOD ingestion for the curated AI Buildout watchlist.

Yahoo's chart endpoint is functional without an account but is a bootstrap feed,
not an exchange-authoritative source.  Every run labels its provenance so a
future licensed Alpaca/EODHD adapter can replace it without changing scanner
math or storage.
"""
import datetime as dt
import os
import sys

import psycopg2
import psycopg2.extras
import requests

from markets import get_universe

PG = dict(host=os.getenv("POSTGRES_HOST", "postgres"), port=os.getenv("POSTGRES_PORT", "5432"),
          user=os.getenv("POSTGRES_USER", "signalix"), password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
          dbname=os.getenv("POSTGRES_DB", "signalix"))
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=0&period2={end}&interval=1d&events=history"


def normalize_yahoo_chart(symbol, payload):
    """Return split-adjusted technical OHLCV rows in the universal price schema."""
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise ValueError(f"Yahoo returned no chart result for {symbol}")
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    adjusted = (result.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or []
    rows = []
    for i, stamp in enumerate(timestamps):
        values = [quote.get(key, [None] * len(timestamps))[i] for key in ("open", "high", "low", "close", "volume")]
        if any(value is None for value in values):
            continue
        open_, high, low, close, volume = values
        adj_close = adjusted[i] if i < len(adjusted) else close
        factor = float(adj_close) / float(close) if float(close) else 1.0
        day = dt.datetime.fromtimestamp(stamp, tz=dt.timezone.utc).date().isoformat()
        rows.append(("US", symbol, day, round(float(open_) * factor, 6),
                     round(float(high) * factor, 6), round(float(low) * factor, 6),
                     round(float(close) * factor, 6), float(volume), "ORD"))
    return rows


def fetch_symbol(symbol):
    response = requests.get(YAHOO_URL.format(symbol=symbol, end=int(dt.datetime.now(dt.timezone.utc).timestamp())),
                            headers={"User-Agent": "Signalix research/1.0"}, timeout=30)
    response.raise_for_status()
    return normalize_yahoo_chart(symbol, response.json())


def upsert_rows(pg, rows):
    if not rows:
        return 0
    cur = pg.cursor()
    psycopg2.extras.execute_values(cur, """
        INSERT INTO price_data (market,symbol,date,open,high,low,close,volume,instrument_type)
        VALUES %s
        ON CONFLICT (market,symbol,date) DO UPDATE SET
          open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
          close=EXCLUDED.close, volume=EXCLUDED.volume, instrument_type=EXCLUDED.instrument_type
    """, rows, page_size=1000)
    pg.commit(); cur.close()
    return len(rows)


def main():
    universe = get_universe("us_ai_buildout")
    pg = psycopg2.connect(**PG)
    total, failed = 0, []
    try:
        for symbol in (universe.benchmark_symbol,) + universe.symbols:
            try:
                n = upsert_rows(pg, fetch_symbol(symbol))
                total += n
                print(f"{symbol}: {n} rows")
            except Exception as exc:
                failed.append(symbol)
                print(f"{symbol}: FAILED {exc}", file=sys.stderr)
        cur = pg.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS data_fetch_status (
            dataset TEXT PRIMARY KEY, data_fetched_at TIMESTAMPTZ NOT NULL, source TEXT NOT NULL)""")
        cur.execute("""INSERT INTO data_fetch_status(dataset,data_fetched_at,source) VALUES
            ('us_ai_buildout',NOW(),'yahoo_chart_bootstrap_unverified')
            ON CONFLICT (dataset) DO UPDATE SET data_fetched_at=EXCLUDED.data_fetched_at,source=EXCLUDED.source""")
        pg.commit(); cur.close()
    finally:
        pg.close()
    print({"rows": total, "failed": failed, "source": "yahoo_chart_bootstrap_unverified"})
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
