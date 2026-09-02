# 03: Cold-Path Performance and Pagination

**What to build:** Make the primary review surface fast and complete: cold API ≤3s, warm API ≤500ms, first meaningful UI ≤2s, compact list payload, default page size 50, and reachable pagination across all 237 symbols.

**Blocked by:** 01 — Diagnostic Data and Setup-Reason Report

**Status:** ready-for-agent

## Files
- `backend/mvp_api.py`
- `backend/mvp_routes.py`
- `backend/frontend/app.js`
- `backend/frontend/index.html`
- `backend/test_setup_candidates_api.py`
- `backend/test_mvp_frontend_contract.py`

## Tests
- Cold/warm/post-ingestion latency at page sizes 50 and full metadata
- Query count, payload bytes, build-stage timing, and concurrent single-flight tests
- Mobile first-content/render and pagination journey

## Live endpoints
- `http://127.0.0.1:3001/mvp`
- `http://127.0.0.1:3001/api/setup-candidates?page=1&page_size=50`
- `http://127.0.0.1:3001/api/setup-candidates?page=2&page_size=50`
- `http://127.0.0.1:8000/health/readiness`

## Acceptance criteria
- [ ] All 237 remain evaluated and are reachable through explicit pagination.
- [ ] Default list page is 50; metadata preserves full eligible/evaluated/total/lane counts.
- [ ] List payload target is roughly ≤200–300KB; heavy wave evidence loads on detail/chart.
- [ ] Cold API ≤3s, warm API ≤500ms, first meaningful UI ≤2s.
- [ ] Concurrent cold requests coalesce into one build.
- [ ] No legacy snapshot/projection fallback is used.
- [ ] Produce timing/bytes/query/artifact evidence by the first 15-minute checkpoint.
