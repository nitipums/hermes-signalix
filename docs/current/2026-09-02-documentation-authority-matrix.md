# Signalix Documentation Authority Matrix

> **STATUS: CURRENT** · Cleanup control record; not a replacement for the authorities listed below.
> **Created:** 2026-09-02 · **Owner:** Arm · **Curator:** Lite

## Purpose

This matrix makes the minimum reading path explicit. It separates current authority, supporting records, historical evidence, runtime artifacts, and unresolved cleanup work.

## Authority matrix

| Concern | One authority | Supporting evidence | Historical / non-authority | Cleanup action |
|---|---|---|---|---|
| Product thesis, target user, non-goals, roadmap | `vault/Product-Strategy-Market-to-Action.md` | `vault/Decisions.md` | old VCP/stage plans, handoffs | Keep authority; remove duplicate product prose from navigation notes |
| Owner-approved atomic decisions | `vault/Decisions.md` | `docs/current/2026-08-31-elliott-grill-decision-record.md` | chat, worker reports, old plans | Reconcile current vs historical sections; retain evidence links |
| Setup-candidate contract | `docs/superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md` | `backend/setup_candidate_contract.py`, API/frontend tests | implementation plan after closeout | Mark plan as historical implementation evidence after reference scan |
| Lifecycle persistence/API | `docs/superpowers/specs/2026-08-31-lifecycle-persistence-owner-review-api-design.md` (`LIFECYCLE-T9`) | `backend/lifecycle_*`, lifecycle tests | old T9 references | Use qualified identifier `LIFECYCLE-T9` |
| User-validation/browser contract | `docs/superpowers/specs/2026-09-01-user-validation-refresh-card-wave-contract.md` and navigation/filter spec | frontend source, browser harness/evidence | completed handoffs | Use qualified identifiers `UI-T06`–`UI-T09`; separate design target from served proof |
| Architecture/data flow | `vault/Architecture.md` | `vault/Components.md`, source tree | old flow sections/postmortems | Retired dashboard/snapshot flow is labelled compatibility/history; current canonical dispatcher/projection seams are explicit |
| Runtime/deployment/timers | `vault/Deployment.md` | compose/systemd/source + live probes | terminal logs, handoffs | Keep runtime claims dated and evidence-backed |
| Acceptance/evidence | `vault/Execution-Pipeline.md` | focused tests, browser evidence, current handoffs | archived review packets | Reconcile narrow 390px PASS vs broader acceptance boundaries |
| Browser/freshness procedure | `vault/Browser-and-Freshness-Verification.md` | public `/mvp`, API probes | old screenshots/logs | Keep procedure; link current evidence, do not duplicate claims |
| Team/Codex workflow | `vault/Team-Operating-Model.md`, `vault/Codex-Standard-Workflow-2026-08-29.md` | AGENTS routing | old roster notes | Keep one worker procedure; historical helpers remain archive |
| Governance/navigation | `vault/Documentation-Governance.md`, `vault/INDEX.md`, `docs/START-HERE.md` | this matrix, `docs/README.md` | old cleanup reports | Make START-HERE the first read; INDEX remains catalog |
| Active execution state | Kanban board `signalix` when cards exist | current task handoff | `vault/Roadmap-Kanban.md`, archived cards | Do not mirror live board state into docs; current board was empty at closeout |
| Historical incidents/replay/migration | `vault/Postmortems/`, `vault/archive/`, `docs/archive/` | dated handoffs | none | Preserve; add replacement/status links, never delete by age |
| Runtime/generated data | live DB, read-model, snapshots, served artifacts | tests and run lineage | documentation notes | Never treat generated artifacts as documentation authority |

## Findings from Wave 0

1. `vault/INDEX.md` and `vault/Documentation-Governance.md` are useful catalogs but too large for first-read navigation.
2. `AGENTS.md` correctly states it is a routing/safety contract, but it still repeats substantial product contract prose; future simplification should be bounded and owner-reviewed.
3. `CONTEXT.md` contains valuable vocabulary but overlaps with the focused spec and AGENTS; it should become a compact glossary/pointer page, not a second decision record.
4. Runtime acceptance wording is split between the current closeouts and older specs/plans. A narrow 390px failure→Retry→recovery PASS must remain distinct from broader desktop/drawer/chart acceptance.
5. `T9` is overloaded across lifecycle persistence, overall implementation history, and UI/browser work. Use domain-qualified labels in new work; preserve old identifiers in historical records.
6. Legacy VCP/dashboard code and notes are compatibility/audit evidence. They are not safe delete candidates until callers, tests, timers, and rollback dependencies are proven absent.
7. Stable tracked worktree is clean at `fd915e8`; `.scratch/codex-intraday-chart/` is an owner-owned untracked worktree with uncommitted changes and is protected.

## Current cleanup decisions

- No historical evidence is deleted in this wave.
- No Kanban cards are created.
- No runtime, database, deployment, or generated artifact is changed.
- Archive candidates require a reference scan and explicit status/replacement link before moving.
- Runtime refactor is complete for the route dispatcher and canonical projection seam; further legacy deletion remains a separate bounded decision.

## Wave exit criteria

- [x] Start page exists.
- [x] One authority is named per concern.
- [x] Protected artifacts are recorded.
- [x] Conflicting authority notes reconciled.
- [x] Archive candidates reference-scanned and moved only if safe.
- [x] `CONTEXT.md` compacted.
- [x] One bounded runtime refactor independently tested and served-verified.

## Final boundary

This cleanup makes navigation and route ownership clearer without changing the product contract. Further legacy deletion, T9 evaluator auto-caller work, broader UI semantic acceptance, and any new product policy remain separate bounded decisions.