#!/usr/bin/env python3
"""Fail-fast consistency check for the latest Daily scan and served dashboard."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import psycopg2


ITEM_PREFIX = "let items="
ITEM_SUFFIX = ";const meta="


def load_dashboard_items(path):
    html = Path(path).read_text(encoding="utf-8")
    start = html.find(ITEM_PREFIX)
    if start < 0:
        raise ValueError("dashboard embedded items assignment not found")
    start += len(ITEM_PREFIX)
    end = html.find(ITEM_SUFFIX, start)
    if end < 0:
        raise ValueError("dashboard embedded items terminator not found")
    items = json.loads(html[start:end])
    if not isinstance(items, list):
        raise ValueError("dashboard items is not a list")
    return items


def latest_db_run():
    pg = psycopg2.connect(
        host="127.0.0.1", port=5432, user="signalix",
        password="signalix_pass", dbname="signalix",
    )
    try:
        cur = pg.cursor()
        cur.execute("""SELECT id, evaluated_symbol_count, scan_date, run_timestamp
                       FROM daily_scan_runs
                       WHERE scanner_version='signalix/daily-state-v2'
                         AND source_lineage->>'source'='price_data'
                         AND COALESCE(source_lineage->>'mode','') <> 'historical_backfill'
                       ORDER BY scan_date DESC, run_timestamp DESC, id DESC LIMIT 1""")
        run = cur.fetchone()
        if not run:
            return None
        cur.execute("SELECT count(*) FROM daily_scan_observations WHERE run_id=%s", (run[0],))
        observations = cur.fetchone()[0]
        return {
            "evaluated_symbol_count": run[1],
            "scan_date": run[2].isoformat(),
            "run_timestamp": run[3].isoformat(),
            "observation_count": observations,
        }
    finally:
        pg.close()


def verify(scan_path, dashboard_path, db_run=None):
    scan = json.loads(Path(scan_path).read_text(encoding="utf-8"))
    groups = scan.get("groups") or {}
    scan_counts = {str(k): len(v) for k, v in groups.items() if isinstance(v, list)}
    scan_total = sum(scan_counts.values())
    items = load_dashboard_items(dashboard_path)
    symbols = [item.get("symbol") for item in items]
    html_counts = dict(Counter(item.get("group") for item in items))
    checks = {
        "scan_total": scan_total,
        "dashboard_items": len(items),
        "dashboard_unique_symbols": len(set(symbols)),
        "scan_group_counts": scan_counts,
        "dashboard_group_counts": html_counts,
        "scan_time": scan.get("scan_time"),
        "db_latest_run": db_run,
    }
    failures = []
    if len(items) != scan_total:
        failures.append("dashboard item count differs from scan group total")
    if len(set(symbols)) != len(items):
        failures.append("dashboard contains duplicate symbols")
    if html_counts != scan_counts:
        failures.append("dashboard group counts differ from scan group counts")
    if db_run:
        if db_run["evaluated_symbol_count"] != scan_total:
            failures.append("DB evaluated count differs from scan group total")
        if db_run["observation_count"] != scan_total:
            failures.append("DB observation count differs from scan group total")
    checks["ok"] = not failures
    checks["failures"] = failures
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", default="/root/signalix/backend/scan_results.json")
    parser.add_argument("--dashboard", default="/root/signalix/backend/dashboard.html")
    parser.add_argument("--no-db", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = verify(args.scan, args.dashboard, None if args.no_db else latest_db_run())
    except Exception as exc:
        print(json.dumps({"ok": False, "failures": [repr(exc)]}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
