# Signalix refactor session closeout

> **STATUS: CURRENT HANDOFF · SESSION CLOSED · 2026-09-02 14:36 ICT**
> Owner: Arm · Final gate: Lite
> Previous closeout: `2026-09-02-1312-signalix-session-close-handoff.md`
> Authority: `docs/START-HERE.md`, `docs/current/2026-09-02-documentation-authority-matrix.md`, `vault/Architecture.md`, `vault/Components.md`, `vault/Execution-Pipeline.md`

## Timeline

All timestamps are Asia/Bangkok (ICT).

- `2026-09-02 13:15` — Documentation authority matrix and `START-HERE.md` created; current/historical routing reconciled.
- `2026-09-02 13:30` — Canonical chart-read seam independently reviewed and verified.
- `2026-09-02 13:45` — Freshness-lineage seam extracted; focused tests and import checks passed.
- `2026-09-02 14:10` — Candidate builder finalization seam extracted; two-axis review found and remediation closed wide interface, repeated validation, and setup mutation findings.
- `2026-09-02 14:30` — Backend/dashboard reloaded; public API and UI re-probed.
- `2026-09-02 14:36` — Closeout written; no further safe policy-neutral refactor selected.

## Refactor waves closed

- Route dispatcher: canonical and legacy/audit handlers explicit.
- Canonical setup projection: validation, ordering, filters, pagination, counts, freshness/provenance, diagnostics in `canonical_setup_projection.py`; `mvp_api` compatibility import preserved.
- Chart read: SQL retrieval, provisional aggregation, ordering, labels, and timestamp metadata in `canonical_chart_read.py`; `chart_rows` compatibility adapter preserved.
- Freshness lineage: sidecar comparison/merge in `canonical_freshness_lineage.py`; route wrapper preserved; Daily lineage remains unchanged.
- Candidate builder: typed `_CandidateRowContext` and `_CandidateRowResult`; aggregate universe/freshness/process-pool/observability remain in the orchestrator; mutable engine setup is copied at the seam.

## Verification

### Documentation — PASS

- `docs/START-HERE.md` is the first-read router.
- Authority matrix exists and names one authority per concern.
- Historical review and implementation plan are archived with replacement links.
- `CONTEXT.md` is glossary + pointers, not a duplicate decision ledger.
- Cleanup report: `docs/Documentation-Cleanup-Review.html`; browser 390px containment passed (`scrollWidth=375`, `clientWidth=375`).

### Source/tests — PASS with environment caveat

- Chart-focused suite: `76 passed, 1 skipped`.
- Freshness/read-model/API suite: `84 passed`.
- Builder-focused suite: passed independently; canonical route/ranking/decision tests passed.
- Full suite: `797 passed, 10 skipped, 3 failed`.
- The 3 failures are environment-only `psycopg2.OperationalError` failures because the host test process cannot resolve Docker hostname `postgres` in `backend/test_screening.py`; no Signalix refactor test failed.
- `py_compile` and `git diff --check`: PASS.
- Two-axis Codex reviews and Lite inspection: PASS after remediation.

### Runtime/API/browser — PASS

- `signalix_backend`, `signalix_dashboard`, PostgreSQL, and Redis running.
- Local `/health/readiness`: HTTP 200, DB/Redis up.
- Public `/api/setup-candidates`: HTTP 200, `237 evaluated`, `50 returned`.
- Public `/mvp`: HTTP 200; Daily/60m freshness and cards/controls rendered.
- Public `/api/chart-db/SIS`: 1D/1W/60M/1M HTTP 200; candles oldest→newest; `latest_time`, `as_of`, and provisional flags verified.
- Backend `/chart/SIS?timeframe=1W`: HTTP 200; ordering/provisional contract verified.
- Public `/dashboard.html`: HTTP 404.
- Real browser card → drawer → chart journey: PASS; provisional current candle and Wave Evidence visible.
- Host/container hashes for changed bind-mounted modules: MATCH.

## Git state

- Branch: `release/signalix-mvp-stable`
- Local HEAD: `3a06f25f39298b7d80d4060004421c9a7eae0a0b`
- Remote HEAD: `fd915e8c58fe2aa66c9484fa4e2efdfee946ab5f`
- Local ahead: 7 commits; not pushed.
- Tracked worktree: clean.
- Protected untracked owner artifact: `.scratch/codex-intraday-chart/`; untouched and must not be deleted/normalized.

## Deliberately deferred

- Evaluator transition/persistence refactor: requires Arm decision on automatic evaluator caller and lifecycle persistence boundary.
- Legacy VCP/dashboard deletion: compatibility/audit callers, tests, rollback dependencies, and deprecation sign-off must be separately proven.
- Full-suite Docker hostname fix: separate test-environment task; not silently changed during refactor.
- No alerts, broker execution, auto-trading, database migration, or production data changes.

## Resume boundary

```text
manual product use → Arm feedback or explicit policy decision
→ grill-with-docs/domain-modeling → focused spec/ticket if needed
→ Codex bounded implementation → Lite source/test/runtime/UI gate
```
