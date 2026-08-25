# P2-07/P2-08 — MVP Data Independence and Stable Pipeline

> **STATUS: CURRENT** · Audit date: 2026-08-25
> Stable release: `signalix-mvp-stable-20260825.2` · commit `c84ecb4`

## Final verdict

```text
MVP canonical artifact independence from legacy snapshot: PASS
MVP route/API legacy fallback: PASS — no fallback, fail-closed 503
MVP chart DB adapter: PASS — read-only price_data/intraday_price_data queries
EOD fetcher source path: PASS — stable release candidate
Intraday refresh source path: PASS — stable release candidate
Intraday artifact refresh lineage: PASS — raw_payload from canonical DB run
MVP physical database separation: NO — PostgreSQL remains shared
Overall full isolation: NOT CLAIMED — shared DB and compatibility build remain
```

## Evidence

### EOD service

```text
signalix-update.timer: enabled/active
WorkingDirectory: /root/signalix-release-candidate/backend
ExecStart: /root/.venv_img/bin/python /root/signalix-release-candidate/backend/update_data.py
ExecStartPost: /root/.venv_img/bin/python /root/signalix-release-candidate/backend/verify_mvp_release.py
ExecCondition: release-candidate set_market_day_guard.py
```

The previous legacy `verify_scan_dashboard.py` post-check is no longer the EOD acceptance gate. The new verifier checks the canonical MVP contract, latest canonical Daily run, item count, manifest run ID, and SHA-256 of `mvp_snapshot.json` and `dashboard.html`.

### Intraday service

```text
signalix-intraday.timer: enabled/active
cadence: 30 minutes in guarded SET windows
interval: 60m
universe: full active ORD
source path: /root/signalix-release-candidate/backend
```

Intraday-only rebuild now queries the latest canonical `daily_scan_runs` and `daily_scan_observations.raw_payload` directly. It passes `scanned` and `run_id` explicitly to the builder; it does not load `scan_results.json` for this refresh path. This prevents `run_id=None` from overwriting the MVP artifact.

### Test/live evidence

```text
focused tests: 26 passed
canonical verifier: PASS
MVP API: HTTP 200
Postgres/Redis/backend/dashboard/delivery: healthy
```

## Remaining boundary

The PostgreSQL database remains shared by Signalix contexts. This is logical/artifact isolation, not a physically separate MVP database. The compatibility builder still emits legacy artifacts for `/dashboard.html` and legacy routes; MVP does not read those artifacts. Full removal of legacy output requires a separate compatibility-build decision and regression window.
