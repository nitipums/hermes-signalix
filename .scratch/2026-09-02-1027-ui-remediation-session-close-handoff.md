# Signalix UI/data remediation — session close handoff

> STATUS: CLOSED AFTER CODEX + LITE REVIEW · 2026-09-02 10:27 ICT
> Owner: Arm · Final gate: Lite
> Supersedes only the UI/data-remediation resume note for this session. Prior owner artifacts remain untouched.

## Timeline

All timestamps are Asia/Bangkok (ICT).

- `2026-09-02 09:52` — Rebaseline found Daily gaps (`3BBIF`, `COM7`, `PR9`) and one stale 60m symbol (`BKIH`); these were operational freshness items, not this UI change.
- `2026-09-02 10:12` — Codex `gpt-5.6-luna` started in isolated worktree.
- `2026-09-02 10:20` — Initial implementation committed and promoted; first canonical read-model rebuild failed closed on exact-envelope validation.
- `2026-09-02 10:22–10:25` — Codex follow-up aligned the strict canonical metadata allowlist; focused tests passed.
- `2026-09-02 10:26` — Canonical read model rebuilt successfully and backend/dashboard reloaded.
- `2026-09-02 10:27` — Public API/UI happy path and 390px drawer gate passed; browser error-state gate remained `NOT VERIFIED` because retained browser cache hid the blocked response.
- `2026-09-02 follow-up` — Fresh CDP-controlled mobile run forced the same-origin setup-candidates request to fail, verified visible error + hidden cards + actionable Retry, restored networking, clicked Retry, and verified real cards recovered; error-state gate closed `PASS`.
- `2026-09-02 10:30` — Release and handoff pushed; timestamped filename convention applied.

## Scope

Owner-approved mobile-first cleanup and canonical detail metadata correction:
- compact primary controls/header presentation;
- mobile full-screen detail drawer;
- long Wave explanation moved to Method / Evidence Guide;
- state-aware `Setup forming` / `Awaiting 60m structure` / `Not ready` copy;
- point-in-time Daily 52W/ATH and normalized as-of index membership in canonical setup detail.

No Elliott algorithm, eligibility, setup/R:R math, lifecycle, alerts, trading, DB schema, or generated artifact source changes.

## Codex evidence

- Model/provider: `openai-codex:gpt-5.6-luna`
- Workspace: `/root/signalix/.scratch/codex-ui-remediation`
- Initial transcript: `/tmp/signalix_codex_ui_transcript.log`
- Initial last message: `/tmp/signalix_codex_ui_last.md`
- Follow-up transcript: `/tmp/signalix_codex_ui_followup_transcript.log`
- Follow-up last message: `/tmp/signalix_codex_ui_followup_last.md`
- Codex process was independently observed as `codex exec`.
- Initial implementation commit: `729aa4380e8eb68104257cd66caaf9b8350820be`
- Contract follow-up commit: `f58be1064699cf43bc7da66af5956cd5057e05b3`
- Promoted release commits: `0e0976f`, `9b0bd2d`

## Verification

### Source/contract — PASS

- Focused suite after follow-up: `85 passed, 1 skipped`.
- Full suite in isolated worktree: `774 passed, 11 skipped, 3 failed`.
- The 3 failures are existing live-DB tests run outside Docker; they cannot resolve Docker hostname `postgres` from the host. No changed-file regression indicated.
- `node --check backend/frontend/app.js`: PASS.
- Python compileall: PASS.
- `git diff --check`: PASS.
- Exact canonical envelope remains fail-closed: only the six allowlisted metadata fields are accepted; arbitrary extras remain rejected.

### Runtime/data — PASS

- Canonical read-model rebuild initially failed safely because the new metadata fields were not yet in the exact-envelope allowlist; no partial artifact was written.
- Codex follow-up fixed the contract seam.
- Canonical publisher then succeeded:
  - `source_version=read-model-a4b5d18cf5199ee7`
  - `count=237`
  - path: `/root/signalix/backend/read-model/versions/read-model-a4b5d18cf5199ee7.json`
- Runtime containers reloaded: backend + dashboard.
- `/health/readiness`: HTTP 200, DB up, Redis up.
- Public `/mvp`: HTTP 200.
- Public `/api/setup-candidates`: 237/237 unique rows across five pages.
- Real served metadata:
  - BBL: 52W `204/147`, ATH `260/14.2926`, `SET100 · SET50`
  - DIF: 52W `10.4/8.1`, ATH `18/7.25`, no index membership in current normalized source
  - EGCO: 52W `143/107`, ATH `396/23.5`, `SET100 · SET50`
  - CENTEL: 52W `43.5/27`, ATH `60/0.3651`, `SET100`
- Current response freshness remains honest: Daily aggregate unknown because 3 official Daily gaps remain; intraday fresh after the 10:00 ICT run.

### Public browser/UI — PASS for happy path

Public URL: `http://91.98.72.120:3001/mvp`

At 390px target:
- `innerWidth=390`, `scrollWidth=375` before drawer; no horizontal page overflow.
- header measured 42px; primary toolbar 124px.
- drawer opened from BBL; mobile panel computed height `844px` and full-screen behavior passed.
- card visibly shows `Setup forming`, `R:R Not ready`, `Target 1 Not ready`, `Stop Not ready` for structurally insufficient 60m setup.
- drawer visibly shows `SET100 · SET50`, `52W High / Low 204.00 / 147.00`, `ATH High / Low 260.00 / 14.29`.
- `Open guide` moved long wave explanation out of drawer; guide opened and populated with actual evidence.
- no browser console/page errors observed during happy-path checks.

### Error/failure UI — PASS

Fresh mobile browser verification at `390×844` used a deterministic same-origin request failure for `/api/setup-candidates`:
- visible `Unable to load setup candidates: Failed to fetch (E2E simulated outage)` panel;
- actionable `Retry` button visible and enabled;
- setup cards absent from the rendered failure surface;
- network/fetch restored immediately;
- real `Retry` click recovered the API-backed cards, including BBL;
- error panel and visible Retry button were gone after recovery;
- final mobile width remained `390px` with document `scrollWidth=375`.

The failure-state caveat is now closed as `PASS`; no network blocking remains.

## Git/release

- Branch: `release/signalix-mvp-stable`
- Local HEAD: `9b0bd2d8e48934c66eee1e5eb8548bf7778ed621`
- Remote branch SHA: `9b0bd2d8e48934c66eee1e5eb8548bf7778ed621`
- Tracked worktree clean; untouched untracked owner/runtime artifacts remain:
  - `factsheets/`
  - `backend/read-model/`
  - `.scratch/2026-09-02-performance-read-model*`
  - `.scratch/codex-ui-remediation/`

## Product/operational boundary

- Wave labels remain machine-generated candidate evidence for Arm review; no algorithm tuning was performed.
- R/R/Target/Stop are not fabricated when 60m structure is insufficient.
- Alerts, evaluator auto-caller, broker execution, and automatic trading remain OFF/PENDING.
- Kanban `signalix` remains reconciled with no active ready/running cards; historical archived graph was not force-closed or modified.

## Next validation loop

`manual use → Arm feedback → grill-with-docs → to-spec → to-tickets → TDD/Codex → Lite independent source/test/runtime/UI gate`.

The browser recoverable-error journey is closed `PASS` after the fresh deterministic mobile verification above. Remaining product work is manual owner validation and any new bounded feedback/spec cycle; no alerts, auto-trading, broker execution, or evaluator auto-caller was enabled.
