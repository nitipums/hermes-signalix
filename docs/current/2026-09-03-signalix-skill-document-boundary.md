# Signalix Skill / Document Boundary

> **STATUS: CURRENT** · Cleanup control record; this note is not product authority.
> **Created:** 2026-09-03 ICT · **Owner:** Arm · **Curator:** Lite

## Purpose

Signalix skills are procedures and routers. Durable product, data, UI, acceptance, runtime, and owner decisions belong to the canonical documents below. A skill must link to the authority; it must not copy a second full specification into `SKILL.md`.

## Authority routing

| Concern | Canonical authority | Skill role |
|---|---|---|
| Product thesis, users, non-goals, roadmap | `vault/Product-Strategy-Market-to-Action.md` | Route strategy questions; capture approved decisions in the authority |
| Setup-candidate and Elliott/Trend/Trade-Setup contract | `docs/superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md` | Route implementation/review to the focused spec |
| State/lane vocabulary and acceptance sequence | `vault/Execution-Pipeline.md` and `vault/Decisions.md` | Verify producer/API/UI consistency; do not redefine enums |
| Architecture and component responsibilities | `vault/Architecture.md`, `vault/Components.md` | Trace source seams and report drift |
| Dashboard/card/drawer behavior | `vault/Components.md` plus current focused UI specs | Run UI/API/browser checks; do not own the contract prose |
| Data freshness, provenance, replay, lineage | `vault/Execution-Pipeline.md`, `vault/Deployment.md`, focused current specs | Run probes and reconcile evidence |
| Runtime/deployment/timers | `vault/Deployment.md` | Verify served state; never claim deployment from source alone |
| Historical incidents and milestones | dated handoffs, `Postmortems/`, `docs/archive/` | Read only when the current authority links to the history |

## Active procedural skill set

- Single Signalix skill router: `signalix-skill-router`
- Product routing: `signalix-product-strategy`
- Current delivery: `signalix-trend-map`
- Data/lineage/replay: `signalix-data-lineage`
- Screening/research: `signalix-screening-research`
- Dashboard/UI/acceptance: `signalix-dashboard-acceptance`
- Runtime/delivery: `signalix-production-ops`
- Codex tooling: `signalix-lite-codex-owner-loop`
- Local development support: `signalix-local-development-environment`
- Documentation/governance support: `signalix-documentation-governance`

## Consolidation rules

1. A product rule, enum, threshold, API field, or owner decision is documented once in its authority.
2. A skill may summarize the routing implication, but the exact contract is read from the authority at task time.
3. Runtime facts are dated evidence, not permanent skill instructions.
4. Historical alternatives remain marked historical/superseded; they do not compete with the current skill router.
5. Acceptance skills report source/tests, runtime/API, data lineage, and browser/UI verdicts separately.
6. Do not archive a low-use safety procedure solely from its count; inspect its authority links and failure coverage first.

## Review candidates

These are not automatically deleted. They need a separate bounded review after this wave:

- `signalix-replay-gating`
- `signalix-evidence-gated-projection`
- `signalix-ploy-requirements-consultation`
- `signalix-lifecycle-blocker-triage`
- `signalix-worktree-maintenance`
- `equity-wave3-dashboard`
- `dr-cross-market-vcp-screening`

Archived in the profile (reversible; not an active skill):

- `signalix-data-lineage-gates` → `/root/.hermes/profiles/lite/skills/_archived/finance/signalix-data-lineage-gates`
- `signalix-remediation-gate` → `/root/.hermes/profiles/lite/skills/_archived/finance/signalix-remediation-gate`

## Scope and verification boundary

This wave changes documentation navigation and skill loading only. It does not change Signalix source, tests, database, deployment, runtime, read models, or product policy. A documentation cleanup PASS is not a source/runtime/UI acceptance PASS.
