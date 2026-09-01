# 05: Legacy Route and Function Quarantine

**What to build:** Remove competing legacy behavior from the primary product while preserving audit/rollback evidence. Hide the VCP tab immediately, prohibit canonical fallback, audit accidental reuse, and remove/410 only paths with no consumers after a one-day deprecation window.

**Blocked by:** 02 — Data-Block and No-Setup State Contract; 03 — Cold-Path Performance and Pagination; 04 — Elliott Wave Chart Evidence and Markers

**Status:** ready-for-agent

## Files
- `backend/mvp_routes.py`
- `backend/mvp_api.py`
- `backend/mvp_projection.py`
- `backend/mvp_snapshot.py`
- `backend/frontend/app.js`
- `backend/frontend/index.html`
- `backend/build_dashboard.py`
- `backend/daily_shortlist.py`
- `backend/stage_classifier.py`
- `backend/test_legacy_routes.py`
- `backend/test_mvp_frontend_contract.py`
- `vault/Architecture.md`
- `vault/Deployment.md`

## Tests
- Route/import/timer/consumer reachability inventory
- Canonical route no-fallback tests
- Compatibility/audit route and rollback tests
- Served primary UI and retired-route desktop/mobile/error checks

## Live endpoints
- `http://127.0.0.1:3001/mvp`
- `http://127.0.0.1:3001/api/setup-candidates?page=1&page_size=50`
- `http://127.0.0.1:3001/api/vcp-finder`
- `http://127.0.0.1:8000/health/readiness`

## Acceptance criteria
- [ ] VCP tab is absent from primary navigation.
- [ ] `/api/setup-candidates` never calls or falls back to legacy snapshots/projections/decision fields.
- [ ] `/api/vcp-finder` is explicitly audit-only for one day with deprecation marker.
- [ ] Code/import scan identifies accidental reuse of old functions and proves canonical callers are migrated.
- [ ] After one day, remove/410 only zero-consumer paths; preserve raw VCP/replay data and rollback path.
- [ ] Produce route/import/reuse audit artifact by the first 15-minute checkpoint.
