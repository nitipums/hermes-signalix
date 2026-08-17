"""
Signalix Phase 2 — Data ingestion from SET EOD CSV archive.
Rules (per owner):
  - Keep ONLY ordinary shares (plain tickers) + DRs (foreign depositary receipts).
  - Drop everything else: warrants (-W, NN C/P NN patterns), sector/index (!/$),
    units/ETN/derivs (leading digit), suffix -O/-F/-M/-P.
  - One CSV per trade day: set-history_EOD_YYYY-MM-DD.csv with columns
    <TICKER>,<DTYYYYMMDD>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>

Schema (PostgreSQL):
  price_data(symbol TEXT, date DATE, open REAL, high REAL, low REAL, close REAL,
             volume REAL, instrument_type TEXT, PRIMARY KEY(symbol, date))
  instrument_type: 'ORD' ordinary share, 'DR' foreign depositary receipt
"""
import os
import glob
import csv
import re
import psycopg2
import psycopg2.extras

# ---------- config ----------
DATA_DIR = os.getenv("SEED_DIR", "/root/signalix/seed_data/set-archive_EOD")
PG = dict(host=os.getenv("POSTGRES_HOST", "postgres"), port=5432,
          user=os.getenv("POSTGRES_USER", "signalix"),
          password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
          dbname=os.getenv("POSTGRES_DB", "signalix"))

SUFFIXES = ("-O", "-F", "-M", "-P")
WARRANT_CP_RE = re.compile(r"\d{2}[CP]\d{2}")   # e.g. 01C26 / 13P26

def classify(ticker: str):
    """Return (keep: bool, type: 'ORD'|'DR'|None)."""
    if ticker.endswith(SUFFIXES):
        return False, None
    if ticker.startswith(("!", "$")):
        return False, None
    if ticker[0:1].isdigit():
        return False, None
    if "-W" in ticker:
        return False, None
    if WARRANT_CP_RE.search(ticker):   # warrant -> cut, keep DRs like AAPL01
        return False, None
    # kept: ordinary if pure letters, else DR (has trailing digits, e.g. AAPL01)
    if ticker.isalpha():
        return True, "ORD"
    return True, "DR"

def init_schema(pg):
    cur = pg.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS price_data (
        symbol TEXT NOT NULL,
        date DATE NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        instrument_type TEXT,
        PRIMARY KEY (symbol, date)
    );
    """)
    pg.commit()
    cur.close()

def ingest_file(path, pg, stats):
    rows = []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for r in reader:
            if len(r) < 7:
                continue
            tk = r[0].strip()
            keep, itype = classify(tk)
            if not keep:
                stats["dropped"] += 1
                continue
            try:
                d = f"{r[1][:4]}-{r[1][4:6]}-{r[1][6:8]}"
                rows.append((
                    tk, d,
                    float(r[2]), float(r[3]), float(r[4]), float(r[5]),
                    float(r[6]) if r[6] else 0.0, itype,
                ))
            except Exception:
                stats["bad_row"] += 1
    cur = pg.cursor()
    market_rows = [("TH",) + tuple(row) for row in rows]
    try:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO price_data "
            "(market,symbol,date,open,high,low,close,volume,instrument_type) "
            "VALUES %s ON CONFLICT (market,symbol,date) DO NOTHING",
            market_rows, page_size=1000,
        )
        pg.commit()
    except Exception:
        pg.rollback()
        raise
    finally:
        cur.close()
    stats["files"] += 1
    stats["rows_kept"] += len(rows)

def main():
    pg = psycopg2.connect(**PG)
    init_schema(pg)
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))
    stats = {"files": 0, "rows_kept": 0, "dropped": 0, "bad_row": 0}
    for i, p in enumerate(files, 1):
        ingest_file(p, pg, stats)
        if i % 500 == 0:
            print(f"  ... {i}/{len(files)} files, rows_kept={stats['rows_kept']}, dropped={stats['dropped']}", flush=True)
    cur = pg.cursor()
    cur.execute("SELECT COUNT(*) FROM price_data")
    total_rows = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_data")
    n_sym = cur.fetchone()[0]
    cur.execute("SELECT instrument_type, COUNT(DISTINCT symbol) FROM price_data GROUP BY instrument_type")
    by_type = cur.fetchall()
    cur.execute("SELECT MIN(date), MAX(date) FROM price_data")
    dmin, dmax = cur.fetchone()
    cur.close(); pg.close()
    print("INGEST COMPLETE")
    print(f"  files processed : {stats['files']}")
    print(f"  rows kept       : {stats['rows_kept']}")
    print(f"  dropped         : {stats['dropped']}")
    print(f"  bad rows        : {stats['bad_row']}")
    print(f"  DB total rows   : {total_rows}")
    print(f"  distinct symbols: {n_sym}")
    for t, c in by_type:
        print(f"    type {t}: {c} symbols")
    print(f"  date range      : {dmin} -> {dmax}")

if __name__ == "__main__":
    main()
