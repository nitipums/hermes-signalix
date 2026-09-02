# Signalix intraday scope + provisional chart runtime closeout

> **STATUS: CLOSED AFTER CODE REVIEW + PROMOTION + RUNTIME/UI VERIFICATION · 2026-09-02 12:50 ICT**
> Owner: Arm · Final gate: Lite
> Supersedes [`2026-09-02-1027-ui-remediation-session-close-handoff.md`](./2026-09-02-1027-ui-remediation-session-close-handoff.md) for this bounded slice; prior owner artifacts remain untouched.

## Timeline

All timestamps are Asia/Bangkok (ICT) unless noted.

- `2026-09-02 11:49` — Fresh runtime baseline: backend/DB/Redis healthy; intraday timer active; latest fetch succeeded but canonical metadata lagged and `/api/chart-db` still served the old chart adapter.
- `2026-09-02 12:06` — Source commit `2d43a59` existed locally; code review started against `b822dda`.
- `2026-09-02 12:24` — Two-axis review found a chart endpoint `NameError` blocker, request-time metadata DB dependency, and explicit audit-scope identity risk.
- `2026-09-02 12:25–12:45` — Bounded Codex follow-ups fixed chart route scope, `/api/chart-db` integration, latest timestamp metadata, and weekly candle ordering. Lite independently reran tests and found/fixed the runtime ordering regression before final acceptance.
- `2026-09-02 12:46` — Installed intraday service/timer updated; daemon reloaded; backend/dashboard recreated.
- `2026-09-02 12:48` — Public API and browser verification passed for Day/Week provisional charts and latest timestamp display.
- `2026-09-02 12:50` — Documentation synchronized, release pushed, and session closed with two bounded review follow-ups retained.

## Scope

Owner-approved changes:

- Keep Daily scan out of every 30-minute intraday round (`--no-scan`) to avoid overlapping expensive Daily scans.
- Default intraday fetch scope to canonical `marginable_long`; retain `active_ord` only as explicit audit/rollback mode.
- Align served canonical metadata with the latest completed intraday ingestion run without changing Daily decision provenance.
- Make `/api/chart-db` Day/Week use current-session 60m data as a provisional/as-is aggregate before official EOD.
- Expose `latest_time` as the actual latest stored candle timestamp while retaining `as_of` as the chart period key.

No Elliott policy, setup/risk math, DB schema, alerts, auto-trading, broker execution, or evaluator auto-caller changes.

## Code review

### Fixed before promotion — PASS

- `chart_data()` undefined `has_provisional` route defect.
- Browser `/api/chart-db` bypassed the new provisional chart logic.
- Weekly candles were returned in reverse order.
- Weekly `as_of` was confused with the actual latest intraday timestamp.

### Remaining bounded follow-up — REVISE

- `_overlay_latest_intraday_metadata()` still performs request-time read-only DB lookup; later replace with bounded cache/published metadata seam if latency evidence requires it.
- `intraday_ingestion_runs` does not yet persist an explicit fetch-universe identity; later prevent an `active_ord` audit run from being selected as `marginable_long` product metadata.

These are documented follow-ups, not silently marked complete.

## Verification

### Source/tests — PASS

- `pytest -q backend` — all tests passed.
- Focused chart/API/frontend tests passed after each bounded follow-up.
- `python -m compileall -q backend` — PASS.
- `git diff --check` — PASS.
- `systemd-analyze verify` for intraday service/timer — PASS.

### Runtime/data — PASS for this slice

- Installed unit/timer byte-identical to `/root/signalix/backend` source.
- `signalix-intraday.timer` active; effective command uses `--intraday-universe marginable_long --no-scan`.
- Backend readiness: DB/Redis `ok`.
- Latest observed intraday run: `fb01ef8fbe70408e82ad3f78b2700fe8`, `full_success`, fetch completed `2026-09-02 12:30:38 ICT`.
- Canonical setup API: `237 evaluated / 237 total`, latest intraday metadata aligned; Daily provenance remains `2026-09-01`.
- Known Daily gaps remain explicit: `3BBIF`, `COM7`, `PR9`.

### Public UI/chart — PASS

- Public `/mvp`: HTTP 200.
- `/api/chart-db/BBL?timeframe=1D`: current `2026-09-02` bar, provisional, `latest_time=2026-09-02T05:00:00+00:00`.
- `/api/chart-db/BBL?timeframe=1W`: ascending candles, latest period key `2026-08-31`, actual `latest_time=2026-09-02T05:00:00+00:00`, final period provisional.
- Browser BBL drawer: chart rendered, Week control active, status showed `Provisional · current candle · 2026-09-02T05:00:00+00:00`, no visible horizontal overflow.

## Git/release

- Branch: `release/signalix-mvp-stable`
- Remote SHA: `5bf3d9ac3e77b9f139ce2f84e0d6e27546a95fa4`
- Local/remote aligned at closeout.
- Intentional untracked artifact: `.scratch/codex-intraday-chart/` isolated Codex worktree with uncommitted changes; preserved and not deleted under worktree safety rules.
- Owner artifacts and unrelated worktrees untouched.

## Next validation loop

`manual use → Arm feedback → grill-with-docs → to-spec → to-tickets → TDD/Codex → Lite independent source/test/runtime/UI gate`.

Alerts, auto-trading, broker execution, and evaluator auto-caller remain OFF/PENDING.
