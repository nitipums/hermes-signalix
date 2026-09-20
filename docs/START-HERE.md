# Signalix — Start Here

> **STATUS: CURRENT** · Single entrypoint and routing map only.
> **Last reconciled:** 2026-09-19 ICT
> Product, contract, runtime, and research truth live in the linked authorities below.

## Current active-only boundary — 2026-09-20

The only current public product targets are the deterministic, read-only,
non-actionable routes `/trend-map`, `/api/trend-map`, `/market-breadth`, and
`/api/market-breadth`. `/mvp`, `/api/setup-candidates`, Team Facts,
Wave/Elliott/VCP research, private signals, alerts, broker execution, and
auto-trading are historical, deferred, or audit-only and are not navigation
targets. See the [active-only contract freeze](current/2026-09-20-active-only-contract-freeze.md)
for the boundary and the [pointer/artifact inventory](current/2026-09-20-pointer-artifact-inventory.md)
for promotion evidence. Source/tests, artifact, runtime/API, freshness,
browser, deployment, and rollback verdicts remain separate.

## Signalix in one minute

Signalix is Daily Trend Mapping: deterministic, public, read-only evidence for
Arm's chart review. It is not a setup engine, signal generator, order system,
or automatic trading system.

```text
Daily market data
→ Daily Trend Mapping
→ data quality / freshness review
→ Arm chart review
```

The active product surfaces are:

- `/trend-map`
- `/api/trend-map`
- `/market-breadth`
- `/api/market-breadth`

The former shadow naming is retired for active Trend Map modules and routes.
`/mvp` and `/api/setup-candidates` are `HISTORICAL / SUPERSEDED / DROPPED`;
their source/history is retained for audit only. Current work must not route to
those routes, the old dashboard builder/server, or shadow-named active modules.

Alerts, broker execution, and auto-trading: `OFF / OUT OF ACTIVE SCOPE`.

## Read the smallest authority set

| If the task is about… | Read first | Read next only if needed |
|---|---|---|
| Product direction / non-goals | `../vault/Product-Strategy-Market-to-Action.md` | `../vault/Decisions.md` |
| Historical setup-candidate / Wave contract (owner resume required) | `superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md` | source + focused tests; do not route current work |
| Historical private seven-day shadow BUY policy (owner resume required) | `superpowers/specs/2026-09-11-private-actionable-signal-design.md` | `../vault/Decisions.md`, source + tests; do not route current work |
| Owner decision | `../vault/Decisions.md` | relevant current decision record |
| Architecture / component boundary | `../vault/Architecture.md` | `../vault/Components.md`, source |
| Acceptance / evidence gate | `../vault/Execution-Pipeline.md` | focused acceptance evidence |
| Runtime / timers / deployment | `../vault/Deployment.md` | live probes and installed units |
| Manual scanner tuning / threshold change | `scanner-policy-evaluation` + `superpowers/specs/2026-09-13-main-trend-ma-calibration.md` | relevant source + tests + bounded baseline/tuned evidence |
| Main Trend calculation semantics | `current/2026-09-13-main-trend-calculation-contract.md` | `superpowers/specs/2026-09-13-main-trend-ma-calibration.md`, source/tests |
| Explicit AutoResearch / deep playbook research | `../vault/Research-Index.md` | `../vault/Research-Playbook-Bible.md`, named project |
| Current Trend Map / Market Breadth focus | `../vault/Deployment.md` | `../vault/Execution-Pipeline.md`, current API/browser evidence |
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
- Generated read-model artifacts are runtime inputs only, not documentation
  authorities and not a current-plus-N retention contract. Serving uses only
  the current pointer and validated artifact; Git history is rollback authority.

## Current baseline pointer

- Release branch: `release/signalix-mvp-stable`
- Current source/release: verify with `git status`, `git log`, and the live route before making a new claim.
- **Cleanup integration status — `SOURCE_TEST_PASS / RUNTIME_REVIEW_REQUIRED`:** the owner-approved lean cleanup is staged in the canonical checkout but is not committed or deployed. Focused active-surface tests and isolated port-3011 read-back pass; the repository-wide suite is now `1,061 passed / 13 skipped / 0 failed` (2 warnings, 4 subtests).
- Retired MVP/setup test suites were removed, obsolete active-surface assertions were aligned to current deterministic contracts, and PostgreSQL-dependent smoke tests skip honestly when the service is unavailable. This is a source/test PASS, not yet a production release PASS.
- Current runtime/data freshness is not live telemetry in this page. Read `../vault/Deployment.md` and probe the relevant endpoint.
- Missing, stale, partial, invalid, or empty data must be reported explicitly as `NOT VERIFIED`, not promoted by HTTP 200 alone.

## Before changing anything

1. Read this page and `../AGENTS.md`.
2. Run `git status --short --branch` and inspect dirty/untracked ownership.
3. Identify one authority for the concern; stop if current authorities conflict.
4. Read source/tests/runtime relevant to the task.
5. Keep source/tests, runtime/API, data freshness, and browser verdicts separate.
6. Preserve owner artifacts and historical evidence; never read or include secrets.
7. Follow the strict Matt loop in `../AGENTS.md`: issue/spec → bounded brief → isolated worktree → test-first where practical → implementation → Standards/Spec review → runtime/data/browser verification → owning-doc sync → scoped closeout.

## Closeout shape

```text
bounded scope
→ source/tests
→ runtime/API/data
→ browser/UI when applicable
→ owning documentation sync
→ PASS / FAIL / REVISE / NOT VERIFIED
```
