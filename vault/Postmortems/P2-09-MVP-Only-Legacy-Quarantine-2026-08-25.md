# P2-09 — MVP-Only Server and Legacy Quarantine

> **STATUS: CURRENT** · Production quarantine completed 2026-08-25
> Release: `signalix-mvp-stable-20260825.3` · commit `47fab54`

## Production boundary

The dashboard container now runs `backend/mvp_server.py`, which imports only the MVP route/API modules and serves `frontend/`. It does not import or expose legacy routes.

```text
/mvp                  200
/api/daily-shortlist  200
/api/explorer         200
/api/chart/PTT        200
/dashboard.html       404
/portal               404
/portfolio            404
```

Dashboard healthcheck now probes `/mvp`, not `/dashboard.html`.

## Quarantined legacy files

Moved out of the release tree and retained at:

```text
/root/signalix-legacy-quarantine-20260825/
```

The release removed:

```text
backend/dashboard_server.py
backend/dashboard_template.html
backend/legacy_routes.py
backend/legacy_server.py
backend/portal.html
backend/portfolio.html
backend/verify_scan_dashboard.py
legacy generated dashboard/snapshot/scan artifacts
```

The old production source remains at `/root/signalix` for rollback; no old data tables were deleted.

## EOD boundary

`signalix-update.service` now runs the stable release updater and `verify_mvp_only.py`. The verifier checks only canonical MVP snapshot lineage, count, manifest run ID, and MVP snapshot hash. Legacy HTML is no longer an EOD acceptance dependency.

## Acceptance evidence

```text
MVP-focused regression: 65 passed
MVP imports: PASS
MVP full-ORD 60m dry-run: 931 symbols
MVP verifier: PASS
production containers: all healthy
browser Daily Shortlist: loaded
browser console errors: 0
browser horizontal overflow: none
```

## Remaining deliberate compatibility scope

`app.py` remains because it owns scan, screen, health, and DB APIs. `scanner.py` remains transitional until a separate import-trace/quarantine wave proves it is unused by production runtime. PostgreSQL remains shared; this change is route/artifact quarantine, not physical database separation.
