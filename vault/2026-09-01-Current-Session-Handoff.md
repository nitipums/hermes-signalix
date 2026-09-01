# Signalix — Current Session Handoff

> **STATUS: CURRENT HANDOFF** · Reconciled 2026-09-01
> **Owner:** Arm / Lite
> **Full evidence:** [[../.scratch/2026-09-01-signalix-session-close-handoff]]

## Current release

- Branch: `release/signalix-mvp-stable`
- Canonical HEAD: `4311c37`
- Source/API/runtime/UI primary gates: **PASS**
- Containers healthy: backend, dashboard, PostgreSQL, Redis
- `kanban.auto_decompose=false`
- Codex policy: every implementation/package card uses `openai-codex:gpt-5.6-luna`; Lite remains final gate

## Performance decision

Arm approved a pragmatic release target:

- cold request `<=15s`
- warm request `<=1s`
- full `237/237` evaluation retained
- single-flight/cache observability required
- strict cold `<=3s` deferred optimization, not a release blocker

Latest measured runtime after reload:

- cold: `7.03s` — **PASS**
- warm: `0.62s` — **PASS**
- concurrent: HTTP 200, approximately `1.18–1.23s` — **PASS**

## User-visible evidence

- Public `/mvp`: canonical `Trend · Elliott · Trade Setup` surface — **PASS**
- VCP shown only as `Audit · Compatibility / Rollback` — **PASS**
- Pagination: `50/page`, `5 pages`, `237 evaluated` — **PASS**
- 390px mobile no horizontal overflow — **PASS**
- Drawer: chart, TradingView link, Wave Evidence toggle, explanation, supporting evidence, alternative state, policy, snapshot identity — **PASS**
- Freshness: `Daily EOD: fresh`, `60m: fresh` — **PASS**
- `/dashboard.html`: retired `404` — **PASS**

## Final-gate result

- **Recoverable browser error + Retry:** `PASS` (2026-09-01)
  - isolated `agent-browser` session at public `/mvp`, mobile `390×844`
  - only `**/api/setup-candidates*` was intercepted; other browser networking remained enabled
  - failure showed visible error + actionable Retry, content hidden, cards `0`
  - route was restored, real Retry clicked, HTTP 200 returned, and `50` rows rendered from `237 evaluated`
  - screenshots, DOM state, request logs, and empty console/error logs: `.scratch/2026-09-01-browser-failure-retry-final2/`

The browser failure-state gate is closed. Overall release closeout still requires final suite/report reconciliation and the separate evaluator auto-caller decision. Preserve historical handoff evidence; do not reset, stash, or broad-stage unrelated owner docs.

## Related authority

- [[Execution-Pipeline]]
- [[Decisions]]
- [[Deployment]]
- [[Documentation-Governance]]
