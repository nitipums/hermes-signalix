#!/usr/bin/env python3
"""Independent Signalix Daily EOD freshness and scan monitor."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2

from set_market_day_guard import SET_CLOSED_DATES

UTC = dt.timezone.utc
BANGKOK = ZoneInfo("Asia/Bangkok")
DEFAULT_SERVICE = "signalix-update.service"
DEFAULT_STATE_FILE = "/var/lib/signalix/eod_healthcheck_observations.json"


def as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def expected_market_date(now=None):
    """Return the latest completed SET session date in Bangkok time.

    During a trading day before the EOD publication cutoff, the current date is
    still in progress, so the expected official EOD is the prior trading day.
    After the cutoff, the current session may be published by the updater.
    """
    current = (now or dt.datetime.now(UTC)).astimezone(BANGKOK)
    local = current.date()
    original_date = local
    while local.weekday() >= 5 or local.isoformat() in SET_CLOSED_DATES:
        local -= dt.timedelta(days=1)
    if (original_date == current.date()
            and current.hour < 18
            and local == current.date()):
        local -= dt.timedelta(days=1)
        while local.weekday() >= 5 or local.isoformat() in SET_CLOSED_DATES:
            local -= dt.timedelta(days=1)
    return local


def _tolerated_exit(service_state):
    """Whether a failed systemd state is an expected pipeline outcome.

    update_data returns 1 when the intraday full-universe pass ends
    partial_success (a bounded number of Settrade symbols return empty
    responses). That is a known ops condition, not an EOD failure; data
    freshness is independently verified below.
    """
    result = service_state.get("Result", "unknown")
    try:
        exec_status = int(service_state.get("ExecMainStatus", -1))
    except (TypeError, ValueError):
        exec_status = -1
    return result == "exit-code" and exec_status == 1


def evaluate_health(service_state, eod_date, scan_date, expected_date, now=None):
    """Return deterministic alert records for EOD/data/scan failures."""
    alerts = []
    result = service_state.get("Result", "unknown")
    try:
        exec_status = int(service_state.get("ExecMainStatus", -1))
    except (TypeError, ValueError):
        exec_status = -1
    if (result not in ("success", "") or exec_status != 0) and not _tolerated_exit(service_state):
        alerts.append({
            "code": "service_failed",
            "result": result,
            "exec_main_status": exec_status,
        })
    if eod_date is None:
        alerts.append({"code": "eod_data_missing"})
    elif eod_date < expected_date:
        alerts.append({
            "code": "eod_data_stale",
            "latest_date": eod_date.isoformat(),
            "expected_date": expected_date.isoformat(),
        })
    if scan_date is None:
        alerts.append({"code": "daily_scan_missing"})
    elif scan_date < expected_date:
        alerts.append({
            "code": "daily_scan_stale",
            "latest_date": scan_date.isoformat(),
            "expected_date": expected_date.isoformat(),
        })
    return alerts


def render_payload(alerts, expected_date, eod_date, scan_date, now=None,
                   service=DEFAULT_SERVICE, coverage=None):
    now = as_utc(now or dt.datetime.now(UTC))
    payload = {
        "level": "ALERT" if alerts else "HEALTHY",
        "component": "signalix_eod",
        "checked_at": now.isoformat(),
        "service": service,
        "expected_market_date": expected_date.isoformat(),
        "eod_latest_date": eod_date.isoformat() if eod_date else None,
        "scan_latest_date": scan_date.isoformat() if scan_date else None,
        "alerts": alerts,
    }
    if coverage is not None:
        payload["coverage"] = coverage
        payload["data_completeness"] = coverage.get("status", "NOT_VERIFIED")
    return json.dumps(payload, sort_keys=True)


def read_service_state(service=DEFAULT_SERVICE):
    result = subprocess.run(
        ["systemctl", "show", service, "--property=Result", "--property=ExecMainStatus"],
        check=True, text=True, capture_output=True,
    )
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def get_pg():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "signalix"),
        password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
        dbname=os.getenv("POSTGRES_DB", "signalix"),
    )


def read_freshness(pg, expected_date=None):
    """Read date freshness and classify every active Thai ORD symbol.

    Process freshness and data completeness are intentionally separate: an EOD
    run can be current while illiquid, unavailable, or newly listed symbols have
    stale/no history. The coverage object makes that boundary explicit.
    """
    cur = pg.cursor()
    try:
        cur.execute("SELECT MAX(date) FROM price_data")
        eod_date = cur.fetchone()[0]
        cur.execute("""SELECT scan_date, evaluated_symbol_count FROM daily_scan_runs
                       WHERE scanner_version='signalix/daily-state-v2'
                         AND source_lineage->>'source'='price_data'
                         AND COALESCE(source_lineage->>'mode','') <> 'historical_backfill'
                       ORDER BY scan_date DESC, run_timestamp DESC, id DESC LIMIT 1""")
        row = cur.fetchone()
        scan_date = row[0] if row else None
        scan_evaluated = row[1] if row else None
        boundary = expected_date or eod_date
        if boundary is None:
            coverage = {
                "active_ord": 0,
                "current_session": 0,
                "stale_history": 0,
                "no_history": 0,
                "future_session": 0,
                "scan_evaluated": scan_evaluated,
                "status": "NOT_VERIFIED",
            }
            return eod_date, scan_date, coverage
        cur.execute("""
            WITH active AS (
                SELECT symbol
                FROM symbol_master
                WHERE status='active' AND instrument_type='ORD'
            ), latest AS (
                SELECT active.symbol, MAX(price_data.date) AS latest_date
                FROM active
                LEFT JOIN price_data
                  ON price_data.symbol=active.symbol AND price_data.market='TH'
                GROUP BY active.symbol
            )
            SELECT
                COUNT(*),
                COUNT(*) FILTER (WHERE latest_date=%s),
                COUNT(*) FILTER (WHERE latest_date<%s),
                COUNT(*) FILTER (WHERE latest_date IS NULL),
                COUNT(*) FILTER (WHERE latest_date>%s)
            FROM latest
        """, (boundary, boundary, boundary))
        active_ord, current_session, stale_history, no_history, future_session = cur.fetchone()
        coverage = {
            "active_ord": active_ord,
            "current_session": current_session,
            "stale_history": stale_history,
            "no_history": no_history,
            "future_session": future_session,
            "scan_evaluated": scan_evaluated,
            "status": "COMPLETE" if current_session == active_ord else "PARTIAL",
        }
        return eod_date, scan_date, coverage
    finally:
        cur.close()


def write_observation(payload, path=DEFAULT_STATE_FILE):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(payload + "\n", encoding="utf-8")
    os.replace(temp, target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--expected-date", help="override expected Bangkok YYYY-MM-DD date")
    parser.add_argument("--outside-session", action="store_true",
                        help="emit a canonical healthy skip record")
    parser.add_argument("--observation-file", default=DEFAULT_STATE_FILE)
    args = parser.parse_args(argv)
    now = dt.datetime.now(UTC)
    expected = dt.date.fromisoformat(args.expected_date) if args.expected_date else expected_market_date(now)
    if args.outside_session:
        payload = json.dumps({
            "level": "HEALTHY", "component": "signalix_eod",
            "checked_at": now.isoformat(), "service": args.service,
            "status": "outside_session_skipped",
        }, sort_keys=True)
        print(payload, flush=True)
        write_observation(payload, args.observation_file)
        return 0
    try:
        service_state = read_service_state(args.service)
        pg = get_pg()
        try:
            eod_date, scan_date, coverage = read_freshness(pg, expected)
        finally:
            pg.close()
        alerts = evaluate_health(service_state, eod_date, scan_date, expected, now)
        payload = render_payload(
            alerts, expected, eod_date, scan_date, now, args.service, coverage
        )
        print(payload, flush=True)
        write_observation(payload, args.observation_file)
        return 1 if alerts else 0
    except Exception as exc:
        payload = json.dumps({
            "level": "ALERT", "component": "signalix_eod",
            "checked_at": now.isoformat(), "service": args.service,
            "alerts": [{"code": "watchdog_failed", "error": repr(exc)[:300]}],
        }, sort_keys=True)
        print(payload, flush=True)
        try:
            write_observation(payload, args.observation_file)
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
