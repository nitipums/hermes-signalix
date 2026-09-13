# Signalix — Start Here

> **STATUS: CURRENT** · Single entrypoint and routing map only.
> **Last reconciled:** 2026-09-13 ICT
> Product, contract, runtime, and research truth live in the linked authorities below.

## Signalix in one minute

Signalix prepares deterministic market evidence and private paper/shadow signals for Arm's review. Arm reviews the chart and makes the final decision. Wave output is machine-generated candidate/evidence, not truth, an order, or automatic trading.

```text
Daily market data
→ Trend Mapping
→ data quality / freshness review
→ optional future setup integration
→ Arm review
```

Canonical surfaces:

- **Current delivery focus:** `/trend-map-shadow`, `/api/trend-map-shadow`
- **Active focused closeout:** GitHub [#17 — Daily Trend Map: public read-only delivery closeout](https://github.com/nitipums/hermes-signalix/issues/17)
- Setup trial / future consumer: `/api/setup-candidates`, `/mvp`
- Operational scope: `marginable_long` (runtime counts are not permanent constants)
- Setup decision lanes remain available for the retained trial contract:
  `REVIEW_NOW`, `SETUP_FORMING`, `DAILY_CANDIDATE`, `WAIT`, `AVOID`, `DATA_BLOCKED`
- Elliott Wave: deferred research; not the current delivery gate
- Alerts, broker execution, and auto-trading: `OFF / PENDING`

## Read the smallest authority set

| If the task is about… | Read first | Read next only if needed |
|---|---|---|
| Product direction / non-goals | `../vault/Product-Strategy-Market-to-Action.md` | `../vault/Decisions.md` |
| Setup-candidate / Wave contract | `superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md` | source + focused tests |
| Private seven-day shadow BUY policy | `superpowers/specs/2026-09-11-private-actionable-signal-design.md` | `../vault/Decisions.md`, source + tests |
| Owner decision | `../vault/Decisions.md` | relevant current decision record |
| Architecture / component boundary | `../vault/Architecture.md` | `../vault/Components.md`, source |
| Acceptance / evidence gate | `../vault/Execution-Pipeline.md` | focused acceptance evidence |
| Runtime / timers / deployment | `../vault/Deployment.md` | live probes and installed units |
| Research / AutoResearch | `../vault/Research-Index.md` | `../vault/Research-Playbook-Bible.md`, named project |
| Current Trend Mapping focus | `../vault/Deployment.md` | `../vault/Execution-Pipeline.md`, shadow API/browser evidence |
| Vocabulary | `../GLOSSARY.md` | focused contract, if semantics matter |
| Vault navigation / cleanup | `../vault/INDEX.md`, `../vault/Documentation-Governance.md` | authority matrix |

## Authority boundaries

- `AGENTS.md` is the agent safety contract and routing layer; it is not a second product specification.
- This file is the entrypoint; it is not a contract, decision ledger, runtime monitor, or changelog.
- `../GLOSSARY.md` is the domain glossary; it is not an entrypoint, status ledger, or implementation history.
- `../vault/INDEX.md` is the vault catalog; it is not a decision ledger, backlog, or runtime report.
- Product/acceptance scope belongs to `../vault/Execution-Pipeline.md` and focused specs.
- Runtime/deployment claims belong to `../vault/Deployment.md` and fresh probes.
- Research notes are evidence only and cannot silently change production behavior.
- Current delivery focus is not automatically product/action authority.
- Dated handoffs, archive notes, generated HTML/JSON, logs, snapshots, worktrees, and Kanban history are non-authorities unless an authority explicitly points to them as evidence.

## Current baseline pointer

- Release branch: `release/signalix-mvp-stable`
- Current source/release: verify with `git status`, `git log`, and the live route before making a new claim.
- Current runtime/data freshness is not live telemetry in this page. Read `../vault/Deployment.md` and probe the relevant endpoint.
- Missing, stale, partial, invalid, or empty data must be reported explicitly as `NOT VERIFIED`, not promoted by HTTP 200 alone.

## Before changing anything

1. Read this page and `../AGENTS.md`.
2. Run `git status --short --branch` and inspect dirty/untracked ownership.
3. Identify one authority for the concern; stop if current authorities conflict.
4. Read source/tests/runtime relevant to the task.
5. Keep source/tests, runtime/API, data freshness, and browser verdicts separate.
6. Preserve owner artifacts and historical evidence; never read or include secrets.

## Closeout shape

```text
bounded scope
→ source/tests
→ runtime/API/data
→ browser/UI when applicable
→ owning documentation sync
→ PASS / FAIL / REVISE / NOT VERIFIED
```
