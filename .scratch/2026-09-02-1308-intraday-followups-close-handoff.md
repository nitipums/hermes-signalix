# Signalix intraday follow-ups close handoff

> **STATUS: CLOSED AFTER CODE + SCHEMA + RUNTIME + PUBLIC UI VERIFICATION · 2026-09-02 13:08 ICT**
> Owner: Arm · Final gate: Lite
> Supersedes the two bounded REVISE items in `2026-09-02-1250-intraday-chart-runtime-close-handoff.md`.

## Timeline

All timestamps are Asia/Bangkok (ICT).

- `2026-09-02 13:00` — Codex bounded implementation completed in isolated worktree; source/test gate passed.
- `2026-09-02 13:02` — Lite independently ran full backend suite and compile/diff checks; commit `d56580e` cherry-picked into stable as `1573d5c`.
- `2026-09-02 13:04` — Idempotent `fetch_universe` schema upgrade applied to canonical PostgreSQL; no destructive migration.
- `2026-09-02 13:05–13:08` — Backend/dashboard recreated; new product run `9d6c6c77e9ef4f7ca0422d15afd97bfd` completed `full_success`; sidecar published and public API/browser verified.

## Closed follow-ups

- Request-time `_overlay_latest_intraday_metadata()` no longer acquires or queries PostgreSQL. It reads the small atomic `backend/read-model/intraday-latest.json` seam and falls back to embedded read-model metadata when absent, malformed, or older.
- `intraday_ingestion_runs.fetch_universe` is persisted via idempotent `ensure_intraday_table` upgrade. Canonical product lineage selects only `marginable_long`; `active_ord` and legacy/null rows fail closed.
- Sidecar publication occurs only after committed successful/partial `marginable_long` ingestion; audit runs cannot overwrite product freshness.

## Verification

### Source/tests — PASS

- Focused: `pytest -q test_intraday_resilience.py test_read_model_publisher.py` — PASS.
- Full backend: `pytest -q` — PASS; 9 skipped.
- `python -m compileall -q backend` — PASS.
- `git diff --check` — PASS.
- Source probe confirmed overlay contains no DB acquisition or `intraday_ingestion_runs` SQL.

### Schema/runtime/data — PASS

- `ensure_intraday_table` ran against canonical DB; `fetch_universe` column upgrade passed.
- Product run: `9d6c6c77e9ef4f7ca0422d15afd97bfd`, `full_success`, completed `2026-09-02 13:05:55 ICT`, universe `marginable_long`.
- Sidecar: `backend/read-model/intraday-latest.json`, schema `signalix.intraday-metadata.v1`, same run/universe/status.
- `/health/readiness`: HTTP 200, DB/Redis up.
- Public `/api/setup-candidates`: HTTP 200, `237 evaluated`; freshness reads sidecar run `9d6c6c77e9ef4f7ca0422d15afd97bfd`.
- Public `/mvp` browser: title `Signalix · Setup Candidates`; Daily/60m freshness visible, cards and controls rendered, no runtime failure observed.

### Git/release — PASS

- Branch: `release/signalix-mvp-stable`
- Release commit: `1573d5c`
- Runtime source was recreated from stable worktree.
- Intentional pre-existing untracked Codex worktree `.scratch/codex-intraday-chart/` remains untouched; no dirty owner files were removed.

## Remaining boundaries

- Daily gaps remain explicit: `3BBIF`, `COM7`, `PR9`.
- Alerts, evaluator auto-caller, broker execution, and automatic trading remain OFF/PENDING.
- No Elliott policy or setup/risk math changed.
