# Signalix Intraday E2E Reliability Incident — 2026-08-21

**Date:** 2026-08-21 Asia/Bangkok
**Owner / final gate:** Bee (lite)
**Status:** FIXED — live E2E verified; morning watchdog scheduled

## User symptom

The 60m intraday job appeared to run, but entering the dashboard showed an old snapshot and old `Last Scanned` time. Systemd also showed noisy failed/invalid-looking states.

## Root causes

1. `--intraday-only --no-scan` fetched and upserted 60m data, then evaluated stored candles, but returned before rebuilding `dashboard.html` and `dashboard_snapshot.json`. DB freshness advanced while the static user artifact stayed old.
2. The dashboard is a static served artifact. HTTP 200 and a healthy backend do not prove that the served dashboard reflects the latest intraday ingestion.
3. `partial_success` (Settrade empty responses for a bounded tail) returned exit 1 and was reported by the intraday watchdog as `service_failed`, although the useful portion of the run succeeded.
4. The watchdog labelled intraday candle freshness as generic `price_data_*`, obscuring which dataset was stale.
5. A 30-minute candle-age threshold was too tight for a 60m feed during a normal session; 90 minutes is the cadence-aware price threshold. Evaluator state remains 30 minutes.

## Fixes

- `update_data.py` now calls `build_dashboard.build()` after every intraday upsert/evaluation, using the existing Daily scan artifact. It does not rerun Daily scan or change Daily membership/classification.
- `intraday_healthcheck.py` tolerates exit-code 1 when the latest ingestion run is `partial_success`, while real failures still alert.
- Watchdog freshness codes now explicitly use `intraday_price_data_stale` / `intraday_price_data_missing`.
- Deployed watchdog threshold is `--price-max-age-minutes 90 --state-max-age-minutes 30`.
- Morning no-agent monitor checks ingest → DB → dashboard → served HTML and can self-heal a dashboard timestamp mismatch by running the supported existing-scan build once.

## Live evidence

At the verified production-like run:

```text
924 symbols attempted
913 succeeded
11 persistent empty responses
3,652 rows offered
intraday evaluator completed
Dashboard rebuild completed
```

Served browser evidence subsequently showed:

```text
Ready · 885 cards · Snapshot
Last Scanned: 21 Aug 2026, 10:47:43 ICT
```

The live watchdog returned `HEALTHY`, systemd `Result=success`, `ExecMainStatus=0` after the tolerance/threshold fix.

Focused regression suite: **30 tests passed**. `systemd-analyze verify` passed.

## Follow-up root cause found after factsheet integration

The first factsheet-enriched 60m run exposed a second serialization defect: PostgreSQL `NUMERIC` values (for example `market_cap`) reached dashboard items as `Decimal`, and `json.dump/json.dumps` had no encoder. The fetch and DB upsert succeeded, but dashboard rebuild raised `TypeError: Object of type Decimal is not JSON serializable`, leaving the previous dashboard artifact served.

Fix: `build_dashboard._json_default()` converts `Decimal` to float and datetime values to ISO strings for both snapshot JSON and embedded HTML. Regression coverage was added. A live rebuild now produces identical local/served `intraday_scan_time` matching the latest ingestion completion.

Automatic recovery covers:

- one bounded retry for genuinely empty Settrade responses;
- failed-symbol retry within the ingestion session;
- next systemd timer invocation after a partial or failed run;
- dashboard rebuild after every completed intraday run;
- one dashboard rebuild by the morning monitor when served freshness lags DB ingestion.

It does **not** silently modify source code or repair external Settrade credential/network outages. Those remain alerts requiring Bee/operator action.

## Monitoring

Temporary morning monitor:

- Cron job: `efb2d7ea8822`
- no-agent script: `signalix_intraday_morning_watchdog.py`
- every 15 minutes, 8 runs, through approximately 12:50 Bangkok
- reports PASS/ALERT and dashboard self-heal result

## Commits

- `6ffb62e` — refresh dashboard after 60m ingestion
- `d7b8a39` — watchdog partial-success tolerance and 60m cadence threshold
