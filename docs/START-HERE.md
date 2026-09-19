# Signalix — Start Here

> **STATUS: CURRENT** · Single entrypoint and routing map only.
> **Last reconciled:** 2026-09-14 ICT
> Product, contract, runtime, and research truth live in the linked authorities below.

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

The former `shadow` naming is retired. The canonical surfaces are:

- `/trend-map`
- `/api/trend-map`

The former `/mvp` and `/api/setup-candidates` setup surfaces are retired from
active scope. Their source/history is retained for audit and future reference,
but current work must not route there.

Alerts, broker execution, and auto-trading: `OFF / OUT OF ACTIVE SCOPE`.

## Read the smallest authority set

| If the task is about… | Read first | Read next only if needed |
|---|---|---|
| Product direction / non-goals | `../vault/Product-Strategy-Market-to-Action.md` | `../vault/Decisions.md` |
| Setup-candidate / Wave contract (only if explicitly resumed) | `superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md` | source + focused tests |
| Private seven-day shadow BUY policy | `superpowers/specs/2026-09-11-private-actionable-signal-design.md` | `../vault/Decisions.md`, source + tests |
| Owner decision | `../vault/Decisions.md` | relevant current decision record |
| Architecture / component boundary | `../vault/Architecture.md` | `../vault/Components.md`, source |
| Acceptance / evidence gate | `../vault/Execution-Pipeline.md` | focused acceptance evidence |
| Runtime / timers / deployment | `../vault/Deployment.md` | live probes and installed units |
| Manual scanner tuning / threshold change | `scanner-policy-evaluation` + `superpowers/specs/2026-09-13-main-trend-ma-calibration.md` | relevant source + tests + bounded baseline/tuned evidence |
| Main Trend calculation semantics | `current/2026-09-13-main-trend-calculation-contract.md` | `superpowers/specs/2026-09-13-main-trend-ma-calibration.md`, source/tests |
| Explicit AutoResearch / deep playbook research | `../vault/Research-Index.md` | `../vault/Research-Playbook-Bible.md`, named project |
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
