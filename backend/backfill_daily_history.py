"""Resumable append-only historical scan backfill.

Uses the current DB scanner against each historical trading session.  It never
writes scan_results.json or changes the latest run.  Default is dry-run; pass
--commit to append immutable runs/events/observations.
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, sys, time
from pathlib import Path

from screening import get_pg, _active_scan_symbols, scan_universe, group_scan_results
from scan_history import (init_daily_scan_history_schema, persist_daily_scan_snapshot,
                          persist_breakout_lifecycle, BACKFILL_LOCK_KEY)

VERSION = "signalix/daily-state-v2-backfill"
LOG = Path(__file__).with_name("backfill_history.log")

def sessions(pg, count):
    cur = pg.cursor()
    cur.execute("SELECT MAX(date) FROM price_data WHERE market='TH'")
    latest = cur.fetchone()[0]
    cur.execute("SELECT DISTINCT date FROM price_data WHERE market='TH' AND date < %s ORDER BY date DESC LIMIT %s", (latest, count))
    out = [r[0] for r in cur.fetchall()]
    cur.close(); return list(reversed(out))

def existing(pg, day):
    cur = pg.cursor()
    cur.execute("SELECT 1 FROM daily_scan_runs WHERE scan_date=%s AND scanner_version=%s LIMIT 1", (day, VERSION))
    row = cur.fetchone(); cur.close(); return str(row[0]) if row else None

def events_before(pg, day):
    cur = pg.cursor()
    cur.execute("""SELECT DISTINCT ON (e.symbol) e.symbol,e.id,e.trigger_price,e.origin,
                   e.pre_break_pivot_low,e.qualified_on
                   FROM daily_breakout_events e
                   JOIN daily_canonical_scan_runs er ON er.id=e.scan_run_id
                   LEFT JOIN LATERAL (SELECT stage FROM daily_canonical_breakout_event_observations
                     WHERE event_id=e.id ORDER BY observed_on DESC,created_at DESC LIMIT 1) o ON TRUE
                   WHERE e.qualified_on <= %s AND COALESCE(o.stage,'') <> 'failed'
                   ORDER BY e.symbol,e.qualified_on DESC,e.created_at DESC""", (day,))
    result = {}
    for sym, eid, trigger, origin, pivot, qualified in cur.fetchall():
        cur2 = pg.cursor(); cur2.execute("SELECT COUNT(DISTINCT scan_date) FROM daily_canonical_scan_runs WHERE scan_date>%s AND scan_date<=%s", (qualified, day)); age = cur2.fetchone()[0]; cur2.close()
        result[sym] = {"event_id": str(eid), "trigger_price": float(trigger), "origin": origin,
                       "pivot_low": float(pivot), "age_sessions": int(age), "qualified_on": str(qualified)}
    cur.close(); return result

def append_log(entry):
    with LOG.open("a", encoding="utf-8") as f: f.write(json.dumps(entry, default=str, sort_keys=True)+"\n")

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=100)
    ap.add_argument("--commit", action="store_true", help="append rows; default is dry-run")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    pg = get_pg(); started = time.time(); locked = False
    try:
        if args.commit:
            # Prevent two wrappers from racing after a host-side timeout/kill.
            cur = pg.cursor(); cur.execute("SELECT pg_advisory_lock(%s)", (BACKFILL_LOCK_KEY,)); cur.close(); locked = True
            init_daily_scan_history_schema(pg)
        days = sessions(pg, args.sessions)
        symbols = _active_scan_symbols(pg, market="TH")
        if args.limit: symbols = symbols[:args.limit]
        report = {"mode": "commit" if args.commit else "dry_run", "scanner_version": VERSION,
                  "requested_sessions": args.sessions, "session_count": len(days),
                  "active_ord_symbols": len(symbols), "sessions": [], "errors": []}
        for i, day in enumerate(days, 1):
            if args.commit and existing(pg, day):
                report["sessions"].append({"date": str(day), "status": "already_present"}); continue
            try:
                # Never use latest active filter as an as-of filter: the universe is
                # the active ORD universe, while each symbol's bars are historical.
                scanned, near = scan_universe(min_conditions=0, pg=pg, market="TH",
                    symbols=symbols, as_of_date=day, annotate_ath=False)
                events = events_before(pg, day) if args.commit else {}
                groups = group_scan_results(scanned, events=events)
                rows = [r for values in groups.values() for r in values]
                item = {"date": str(day), "status": "planned" if not args.commit else "committed",
                        "evaluated": len(rows), "groups": {k: len(v) for k,v in groups.items()}}
                if args.commit and rows:
                    snap = persist_daily_scan_snapshot(pg, rows, scan_date=day,
                        scanner_version=VERSION, source_lineage={"source":"price_data","mode":"historical_backfill",
                        "universe":"active_TH_ORD","as_of_date":str(day),"scanner":"current"})
                    life = persist_breakout_lifecycle(pg, rows, snap["run_id"], VERSION)
                    item.update({"run_id": snap["run_id"], **life})
                report["sessions"].append(item)
                append_log({"date":str(day), "status":item["status"], "evaluated":len(rows)})
                print(f"[{i}/{len(days)}] {day} {item['status']} evaluated={len(rows)}", flush=True)
            except Exception as exc:
                pg.rollback(); entry={"date":str(day), "error":repr(exc)}; report["errors"].append(entry); append_log(entry); print(entry, file=sys.stderr, flush=True)
        report["elapsed_seconds"] = round(time.time()-started, 2)
        report["coverage"] = {"dates_with_rows": sum(1 for x in report["sessions"] if x.get("evaluated",0)>0),
                               "total_observations": sum(x.get("evaluated",0) for x in report["sessions"])}
        out = Path(__file__).with_name("backfill_history_report.json")
        out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(json.dumps(report, indent=2, default=str))
        return 1 if report["errors"] else 0
    finally:
        if locked:
            cur = pg.cursor(); cur.execute("SELECT pg_advisory_unlock(%s)", (BACKFILL_LOCK_KEY,)); cur.close()
        pg.close()

if __name__ == "__main__": raise SystemExit(main())
