# Signalix Documentation Governance

> **Status:** CURRENT — governance layer
> **Last reviewed:** 2026-08-26
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
| Active work state, owner, dependency, retry, run state | `Execution-Pipeline.md` + focused plans under `/root/signalix/.hermes/plans/` | Kanban board is audit/archive only; do not dispatch from it |
| Historical incidents and migration evidence | `Postmortems/` and dated handoffs | current product direction |
| Durable cross-session invariants | compact MEMORY / `fact_store` | raw sessions, task progress, secrets |
| Repeatable procedures | one primary Hermes skill per workflow | copied instructions in many notes |

## Status vocabulary

Use one of these banners at the top of project notes:

- `STATUS: CURRENT` — authoritative for its named concern.
- `STATUS: HISTORICAL` — preserved evidence; not current direction.
- `STATUS: SUPERSEDED` — explicitly replaced by another note/decision.
- `STATUS: ARCHIVED` — retained for audit/search only.
- `STATUS: REVIEW_REQUIRED` — currentness or ownership is unresolved.

## Current canonical set

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

## Historical set

Dated handoffs and postmortems remain valuable as evidence.

## Known conflict — resolved 2026-08-23

Arm chose Markdown `Execution-Pipeline.md` and linked focused plans as the product-scope/acceptance authority. Kanban is the active durable execution/orchestration state for the current gated run (named workers, dependencies, heartbeats, retries, and evidence handoffs); live card status must not be copied into vault notes.

## Cleanup policy

1. Reconcile current notes before archiving history.
2. Never delete a note merely because it is old; mark status and link replacement.
3. Never copy active Kanban status into vault or facts.
4. Remove/compact superseded facts only after replacement is explicit.
5. Never store credentials, tokens, passwords, OAuth data, or `.env` contents.
6. Treat generated HTML, JSON snapshots, logs, and worktree files as artifacts—not documentation authorities.
7. Use `Documentation-Cleanup-Review.html` as the visual inventory report; regenerate after each cleanup batch.

## Skill overlap matrix (2026-08-23)

| Domain | Primary skill | Complementary | Superseded |
|---|---|---|---|
| Dashboard verification | `signalix-dashboard-verification` | `signalix-dashboard-contracts` (defines contracts) | `signalix-dashboard-review`, `signalix-served-artifact-verification` |
| Pipeline reliability | `signalix-pipeline-reliability` | `signalix-data-feed-reliability` (feed-specific) | `signalix-pipeline-stability-review` |
| Fetch monitoring | `signalix-fetch-monitor` | — | — |
| Canonical run remediation | `signalix-history-lineage` | — | — |
| Backfill & parity | `signalix-backfill-and-parity` | — | — |
| Acceptance / QA | `signalix-read-only-acceptance` | `signalix-state-contracts` | `signalix-canonical-acceptance-review`, `signalix-evidence-reconciliation` |
| Product strategy | `signalix-product-strategy` | — | `signalix-product-strategy-review`, `signalix-product-roadmap` |
| UI changes | `signalix-dashboard-ui` | `signalix-dashboard-interaction-contracts` | — |
| Screening | `signalix-screening-layering` | `signalix-screen-vs-db` | — |
| Ops / delivery | `signalix-ops` | `signalix-delivery-ops` | — |
| UI recovery | `signalix-ui-implementation-recovery` | — | — |
| Documentation governance | `signalix-documentation-governance` | — | — |
| Kanban | — | — | `signalix-kanban-worker-common`, `signalix-kanban-execution-loop`, `signalix-team-operating-playbook` |

**Total superseded skills: 12**
