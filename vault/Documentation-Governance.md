# Signalix Documentation Governance

> **STATUS: CURRENT** · governance layer
> **Last reviewed:** 2026-09-19
> **Current reconciliation:** Daily Trend Map (`/trend-map`, `/api/trend-map`) and Market Breadth (`/market-breadth`, `/api/market-breadth`) are the active public read-only surfaces. `/mvp` and `/api/setup-candidates` are `HISTORICAL / SUPERSEDED / DROPPED`; old dashboard and shadow-named active modules are not current routing targets. Lite remains the final gate.
> **Owner:** Nitipum.s / Lite curator
> **Purpose:** define where current direction, decisions, work state, historical evidence, durable memory, and procedures belong.

## Authority rules

| Concern | Canonical authority | Must not be treated as authority |
|---|---|---|
| Product thesis, target user, non-goals, roadmap boundary | `Product-Strategy-Market-to-Action.md` | dated handoffs, worker briefs, fact_store summaries |
| Owner-approved atomic decisions | `Decisions.md` | chat summaries, worker self-reports |
| Current architecture and data flow | `Architecture.md` | old handoffs, worktree copies |
| Current component behavior | `Components.md` | historical implementation notes |
| Current deployment and operations | `Deployment.md` | stale terminal logs, worker workspaces |
| Current execution sequence / acceptance | `Execution-Pipeline.md` | archived Kanban cards, old plans |
| Active work state, owner, dependency, retry, run state | Kanban board `signalix` | Do not mirror live card status into vault notes; `Execution-Pipeline.md` owns scope/acceptance, not live worker state |
| Historical incidents and migration evidence | `Postmortems/` and dated handoffs | current product direction |
| Durable cross-session invariants | compact MEMORY / `fact_store` | raw sessions, task progress, secrets |
| Repeatable procedures | one primary Hermes skill per workflow | copied instructions in many notes |

## Handoff naming and timeline convention

- New Signalix handoffs use `YYYY-MM-DD-HHmm-<topic>-handoff.md`.
- The filename timestamp is always `Asia/Bangkok (ICT)`.
- If multiple handoffs are created within the same minute, use `YYYY-MM-DD-HHmmss-<topic>-handoff.md`.
- Every new handoff must include a `## Timeline` section with timestamped events, evidence-backed status changes, and links to the previous/superseding handoff when applicable.
- Historical handoffs keep their original names for reference integrity; add a timeline and explicit `HISTORICAL`/superseded note rather than silently renaming them.

## Status vocabulary

Use one of these banners at the top of project notes:

- `STATUS: CURRENT` — authoritative for its named concern.
- `STATUS: HISTORICAL` — preserved evidence; not current direction.
- `STATUS: SUPERSEDED` — explicitly replaced by another note/decision.
- `STATUS: ARCHIVED` — retained for audit/search only.
- `STATUS: REVIEW_REQUIRED` — currentness or ownership is unresolved.

## Current canonical set

**First read:** `../docs/START-HERE.md`

**Cleanup matrix:** `../docs/current/2026-09-02-documentation-authority-matrix.md`

1. `Product-Strategy-Market-to-Action.md`
2. `Decisions.md`
3. `Architecture.md`
4. `Components.md`
5. `Deployment.md`
6. `Execution-Pipeline.md`
7. `Phases.md`
8. `Team-Operating-Model.md`
9. `Product-Feedback.md`
10. `Browser-and-Freshness-Verification.md`
11. `INDEX.md`
12. `Documentation-Governance.md`
13. `Memory-Cleanup-Candidates.md`
14. `../docs/current/2026-08-31-elliott-grill-decision-record.md`
15. `../docs/superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md`
16. `../docs/superpowers/specs/2026-08-31-lifecycle-persistence-owner-review-api-design.md` (`LIFECYCLE-T9`)

## Historical set

Dated handoffs and postmortems remain valuable as evidence.

## Known conflict — resolved 2026-08-23

Arm chose Markdown `Execution-Pipeline.md` and linked focused plans/specs as the product-scope/acceptance authority. Kanban owns active named-worker execution state only when a bounded run exists; the 2026-09-02 board was empty. Live card status must not be copied into vault notes.

## Cleanup policy

1. Reconcile current notes before archiving history.
2. Never delete a note merely because it is old; mark status and link replacement.
3. Never copy active Kanban status into vault or facts.
4. Remove/compact superseded facts only after replacement is explicit.
5. Never store credentials, tokens, passwords, OAuth data, or `.env` contents.
6. Treat generated HTML, JSON snapshots, logs, and worktree files as artifacts—not documentation authorities.
7. Use `Documentation-Cleanup-Review.html` as the visual inventory report; regenerate after each cleanup batch.

## Repository cleanup decision — 2026-09-19

The owner approved removal of unused Elliott prototype assets and inactive
legacy helper modules after reference checks. Generated read-model artifacts
are current runtime inputs only, not documentation authorities and not a
current-plus-N retention contract. Only the current pointer and validated
artifacts are serving inputs; Git history is rollback authority. Historical
filenames may retain shadow identity for compatibility/audit evidence, but
internal active Trend Map naming is normalized to Trend Map.

## Cleanup integration gate — 2026-09-19

The owner-approved lean cleanup is a staged, uncommitted integration candidate
in the canonical checkout. Focused Trend Map, Market Breadth, read-model,
retired-route, compile, syntax, and isolated served-route checks pass. After
removing retired MVP/setup test suites, aligning current deterministic chart and
Trend classifier fixtures, and making PostgreSQL smoke tests skip honestly when
the service is unavailable, the full suite is `1,061 passed / 13 skipped /
0 failed` (2 warnings, 4 subtests). Source/test status is `PASS`; runtime,
public ingress, deployment, and commit/push remain separate gates.

## Skill overlap matrix — current consolidated set

| Domain | Primary skill | Notes |
|---|---|---|
| Routing | `signalix-skill-router` | Start here when unsure |
| Product strategy | `signalix-product-strategy` | Contract remains in canonical vault/specs |
| Daily Trend Mapping | `signalix-trend-map` | Current public read-only non-actionable focus |
| Data/lineage/replay | `signalix-data-lineage` | EOD, intraday, freshness, coverage, backfill, replay |
| Screening/research | `signalix-screening-research` | Deterministic screening plus explicitly scoped research/compatibility |
| Dashboard/UI/acceptance | `signalix-dashboard-acceptance` | UI, served artifact, API parity, browser acceptance |
| Runtime/delivery | `signalix-production-ops` | Docker, systemd, delivery, release, recovery |
| Codex tooling | `signalix-lite-codex-owner-loop` | Lite-owned Codex invocation and final review |
| Local development | `signalix-local-development-environment` | Safe laptop/runtime separation |
| Documentation/governance | `signalix-documentation-governance` | Authority and cleanup procedure |

Legacy Signalix procedures remain in the profile archive and are not active routing targets.
