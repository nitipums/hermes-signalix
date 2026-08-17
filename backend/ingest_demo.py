"""
Signalix DEMO — ingest a Thai SET EOD zip into a dedicated database.

This is the first stage of the demo pipeline
(ingest -> scan -> dashboard). It:

  * creates a fresh demo database `signalix_demo` (never touches the
    production `signalix` DB),
  * extracts a SET EOD archive zip (set-history_EOD_YYYY-MM-DD.csv files),
  * loads every CSV into `price_data` using the EXACT same instrument
    classification rules as the production ingest.py (single source of
    truth — imported from there),
  * reports stats and verifies the load.

The scanner stage (t_25176a7d) should connect to the SAME database:
    POSTGRES_DB=signalix_demo

Idempotent: re-running just re-inserts with ON CONFLICT DO NOTHING.

Usage:
  python ingest_demo.py                 # uses seed_zip/set-archive_EOD.zip
  python ingest_demo.py --zip /path/to/archive.zip
"""
import os
import sys
import glob
import argparse
import zipfile
import tempfile

import psycopg2
import psycopg2.extras

# Reuse the production classification logic verbatim.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest import classify, init_schema, ingest_file  # noqa: E402

# ---------- config ----------
DEMO_DB = os.getenv("DEMO_DB", "signalix_demo")
DEFAULT_ZIP = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "seed_zip", "set-archive_EOD.zip",
)
PG = dict(
    host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    user=os.getenv("POSTGRES_USER", "signalix"),
    password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
    dbname=os.getenv("POSTGRES_DB", "signalix"),
)


def ensure_demo_db():
    """Create the demo database if it does not exist yet."""
    admin = psycopg2.connect(**PG)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(
        "SELECT 1 FROM pg_database WHERE datname=%s", (DEMO_DB,)
    )
    exists = cur.fetchone()
    if not exists:
        print(f"  creating database '{DEMO_DB}' ...", flush=True)
        cur.execute(f'CREATE DATABASE "{DEMO_DB}"')
    else:
        print(f"  database '{DEMO_DB}' already exists", flush=True)
    cur.close()
    admin.close()


def extract_zip(zip_path, dest):
    os.makedirs(dest, exist_ok=True)
    n = 0
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            # only the per-day CSVs, ignore directory entries / nested junk
            if name.lower().endswith(".csv") and os.path.basename(name):
                out = os.path.join(dest, os.path.basename(name))
                with z.open(name) as src, open(out, "wb") as dst:
                    dst.write(src.read())
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default=DEFAULT_ZIP, help="path to SET EOD archive zip")
    ap.add_argument("--extract-to", default=None,
                    help="where to extract CSVs (default: a temp dir)")
    args = ap.parse_args()

    zip_path = args.zip
    if not os.path.exists(zip_path):
        sys.exit(f"! zip not found: {zip_path}")

    ensure_demo_db()

    print(f"Extracting {zip_path} ...", flush=True)
    if args.extract_to:
        csv_dir = args.extract_to
        n_csv = extract_zip(zip_path, csv_dir)
    else:
        tmp = tempfile.mkdtemp(prefix="signalix_demo_")
        csv_dir = tmp
        n_csv = extract_zip(zip_path, csv_dir)
    print(f"  extracted {n_csv} CSV files -> {csv_dir}", flush=True)

    pg = psycopg2.connect(**{**PG, "dbname": DEMO_DB})
    init_schema(pg)

    files = sorted(glob.glob(os.path.join(csv_dir, "*.csv")))
    stats = {"files": 0, "rows_kept": 0, "dropped": 0, "bad_row": 0}
    for i, p in enumerate(files, 1):
        ingest_file(p, pg, stats)
        if i % 25 == 0 or i == len(files):
            print(f"  ... {i}/{len(files)} files, rows_kept={stats['rows_kept']}, "
                  f"dropped={stats['dropped']}", flush=True)

    cur = pg.cursor()
    cur.execute("SELECT COUNT(*) FROM price_data")
    total_rows = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_data")
    n_sym = cur.fetchone()[0]
    cur.execute("SELECT instrument_type, COUNT(DISTINCT symbol) "
                "FROM price_data GROUP BY instrument_type")
    by_type = cur.fetchall()
    cur.execute("SELECT MIN(date), MAX(date) FROM price_data")
    dmin, dmax = cur.fetchone()
    cur.execute("SELECT symbol, COUNT(*) FROM price_data GROUP BY symbol "
                "ORDER BY 2 DESC LIMIT 5")
    top = cur.fetchall()
    cur.close()
    pg.close()

    print("INGEST (DEMO) COMPLETE")
    print(f"  source zip      : {zip_path}")
    print(f"  target database : {DEMO_DB}  (host={PG['host']})")
    print(f"  files processed : {stats['files']}")
    print(f"  rows kept       : {stats['rows_kept']}")
    print(f"  dropped         : {stats['dropped']}")
    print(f"  bad rows        : {stats['bad_row']}")
    print(f"  DB total rows   : {total_rows}")
    print(f"  distinct symbols: {n_sym}")
    for t, c in by_type:
        print(f"    type {t}: {c} symbols")
    print(f"  date range      : {dmin} -> {dmax}")
    print(f"  top symbols by rows: {top}")


if __name__ == "__main__":
    main()
