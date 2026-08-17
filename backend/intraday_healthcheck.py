#!/usr/bin/env python3
"""Independent intraday pipeline freshness and service-state monitor."""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys

import psycopg2


UTC = dt.timezone.utc
DEFAULT_SERVICE = "signalix-intraday.service"
DEFAULT_OBSERVATION_FILE = "/root/signalix/intraday_healthcheck_observations.json"
JOURNAL_LOOKBACK_HOURS = 2


def render_healthy_payload(now=None, service=DEFAULT_SERVICE, status=None):
    now = _as_utc(now or dt.datetime.now(UTC))
    payload = {
        "level": "HEALTHY",
        "component": "signalix_intraday",
        "checked_at": now.isoformat(),
        "service": service,
    }
    if status:
        payload["status"] = status
    return json.dumps(payload, sort_keys=True)


def _as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _age_minutes(value, now):
    return round((now - _as_utc(value)).total_seconds() / 60.0, 1)


def evaluate_health(service_state, price_ts, evaluated_at, now=None,
                    max_age_minutes=None, price_max_age_minutes=90,
                    state_max_age_minutes=30, failed_invocations=None):
    """Return deterministic alert records for all unhealthy checks."""
    now = _as_utc(now or dt.datetime.now(UTC))
    if max_age_minutes is not None:
        price_max_age_minutes = state_max_age_minutes = max_age_minutes
    alerts = []
    result = service_state.get("Result", "unknown")
    try:
        exec_status = int(service_state.get("ExecMainStatus", -1))
    except (TypeError, ValueError):
        exec_status = -1
    if result not in ("success", "") or exec_status != 0:
        alerts.append({
            "code": "service_failed",
            "result": result,
            "exec_main_status": exec_status,
        })
    elif failed_invocations:
        alerts.append({
            "code": "service_failed",
            "result": result,
            "exec_main_status": exec_status,
            "failed_invocations": failed_invocations,
        })

    freshness = (
        ("price_data", price_ts, "price_data_stale", "price_data_missing",
         price_max_age_minutes),
        ("intraday_state", evaluated_at, "intraday_state_stale", "intraday_state_missing",
         state_max_age_minutes),
    )
    for dataset, value, stale_code, missing_code, threshold in freshness:
        if value is None:
            alerts.append({"code": missing_code, "dataset": dataset})
            continue
        age = _age_minutes(value, now)
        if age > threshold:
            alerts.append({
                "code": stale_code,
                "dataset": dataset,
                "age_minutes": age,
                "max_age_minutes": threshold,
                "latest_at": _as_utc(value).isoformat(),
            })
    return alerts


def render_alert_payload(alerts, now=None, service=DEFAULT_SERVICE):
    now = _as_utc(now or dt.datetime.now(UTC))
    return json.dumps({
        "level": "ALERT",
        "component": "signalix_intraday",
        "checked_at": now.isoformat(),
        "service": service,
        "operator_hint": (
            "Inspect journalctl for Settrade U-102/source-session failure; "
            "the evaluator is configured as ExecStopPost and should still run on stored candles."
        ),
        "alerts": alerts,
    }, sort_keys=True)


def read_service_state(service=DEFAULT_SERVICE):
    result = subprocess.run(
        ["systemctl", "show", service, "--property=Result", "--property=ExecMainStatus"],
        check=True,
        text=True,
        capture_output=True,
    )
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def _journal_failure_records(records):
    """Return failed service invocation records correlated by journal invocation id."""
    failures = []
    seen_invocation_ids = set()
    for record in records:
        message = record.get("MESSAGE", "")
        is_failure = (
            ("Main process exited" in message and "/FAILURE" in message)
            or "Failed with result" in message
        )
        invocation_id = (
            record.get("INVOCATION_ID")
            or record.get("_SYSTEMD_INVOCATION_ID")
            or record.get("__CURSOR")
        )
        if not is_failure or not invocation_id or invocation_id in seen_invocation_ids:
            continue
        seen_invocation_ids.add(invocation_id)
        timestamp = record.get("__REALTIME_TIMESTAMP")
        if timestamp:
            failed_at = dt.datetime.fromtimestamp(int(timestamp) / 1_000_000, UTC).isoformat()
        else:
            failed_at = None
        failures.append({
            "invocation_id": invocation_id,
            "failed_at": failed_at,
            "message": message,
        })
    return failures


def read_failed_invocations(service=DEFAULT_SERVICE, lookback_hours=JOURNAL_LOOKBACK_HOURS):
    """Read a bounded durable journal window; no upstream request is made."""
    result = subprocess.run(
        ["journalctl", "--unit", service, "--since", f"-{lookback_hours}h",
         "--output=json", "--no-pager"],
        check=True,
        text=True,
        capture_output=True,
    )
    records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    return _journal_failure_records(records)


def read_failure_observations(path=DEFAULT_OBSERVATION_FILE):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {"seen_invocation_ids": []}
    if not isinstance(data, dict) or not isinstance(data.get("seen_invocation_ids", []), list):
        raise ValueError("invalid healthcheck observation state")
    return data


def record_failure_observations(observations, failures, now, path=DEFAULT_OBSERVATION_FILE):
    seen = list(observations.get("seen_invocation_ids", []))
    seen.extend(failure["invocation_id"] for failure in failures if failure["invocation_id"] not in seen)
    data = {
        "observed_at": _as_utc(now).isoformat(),
        "seen_invocation_ids": seen[-100:],
    }
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, sort_keys=True)
        handle.write("\n")
    os.replace(temp_path, path)


def unobserved_failures(failures, observations):
    seen = set(observations.get("seen_invocation_ids", []))
    return [failure for failure in failures if failure["invocation_id"] not in seen]


def read_freshness(pg):
    cur = pg.cursor()
    try:
        cur.execute("SELECT MAX(ts) FROM intraday_price_data WHERE interval='60m'")
        price_ts = cur.fetchone()[0]
        cur.execute("SELECT MAX(evaluated_at) FROM intraday_state")
        evaluated_at = cur.fetchone()[0]
        return price_ts, evaluated_at
    finally:
        cur.close()


def get_pg():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "signalix"),
        password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
        dbname=os.getenv("POSTGRES_DB", "signalix"),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--max-age-minutes", type=float,
                        help="legacy override: apply one threshold to both checks")
    parser.add_argument("--price-max-age-minutes", type=float, default=90,
                        help="60m candle timestamp threshold (default: 90)")
    parser.add_argument("--state-max-age-minutes", type=float, default=30,
                        help="evaluator timestamp threshold (default: 30)")
    parser.add_argument("--outside-session", action="store_true",
                        help="emit the canonical JSONL skip record without checking dependencies")
    args = parser.parse_args(argv)
    now = dt.datetime.now(UTC)
    if args.outside_session:
        print(render_healthy_payload(now=now, service=args.service,
                                    status="outside_session_skipped"), flush=True)
        return 0
    try:
        service_state = read_service_state(args.service)
        observations = read_failure_observations()
        failed_invocations = unobserved_failures(
            read_failed_invocations(args.service), observations
        )
        pg = get_pg()
        try:
            price_ts, evaluated_at = read_freshness(pg)
        finally:
            pg.close()
        alerts = evaluate_health(
            service_state,
            price_ts,
            evaluated_at,
            now=now,
            max_age_minutes=args.max_age_minutes,
            price_max_age_minutes=args.price_max_age_minutes,
            state_max_age_minutes=args.state_max_age_minutes,
            failed_invocations=failed_invocations,
        )
        record_failure_observations(observations, failed_invocations, now)
    except Exception as exc:
        alerts = [{"code": "healthcheck_error", "error": f"{type(exc).__name__}: {exc}"}]

    if alerts:
        print(render_alert_payload(alerts, now=now, service=args.service), flush=True)
        return 2
    print(render_healthy_payload(now=now, service=args.service), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
