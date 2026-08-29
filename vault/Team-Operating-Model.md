# Signalix Team Operating Model & Provider Allocation

**Status:** CURRENT · standard team adopted 2026-08-29. Current work source is `vault/Execution-Pipeline.md` (Kanban is audit/archive only).

## Authority and workflow

- **Arm** is owner.
- **Lite** is orchestrator, product lead, and final quality gate. No helper declares a user-facing release ready.
- **Codex CLI** is the coding/review/implementation agent and must work from bounded briefs.
- **Ploy** is the trader/product/risk challenger.
- Khim and Nida are no longer active default Signalix team members; their historical outputs remain audit evidence only.

## Team lanes

| Member | Role | Provider/model | Boundary |
|---|---|---|---|
| `lite` | Orchestrator + final quality gate | Hermes / `gpt-5.6-luna-900k` | Defines briefs, controls scope, verifies source→tests→runtime→browser, and owns PASS/FAIL/REVISE/NOT VERIFIED. |
| `codex` | Coding/review/implementation | Codex CLI / `gpt-5.6-luna` via ChatGPT subscription | Bounded code changes and review; no reset/stash/commit/push; never final release authority. |
| `ploy` | Trader/product/risk challenger | On-demand helper | Challenges setup, trigger, risk wording, actionability, and trader usefulness. |

Historical members `khim`, `nida`, `prae`, `mali`, and `view` are retained in dated notes for audit context but are not part of the default active team.

## Verified runtime

- Codex CLI `0.150.1` is installed system-wide and ChatGPT subscription login is verified.
- Standard Codex calls preserve Lite's Hermes HOME, set `CODEX_HOME=/root/.codex`, use `gpt-5.6-luna`, and run from `/root/signalix` or a disposable temp Git workspace.
- Ploy remains an on-demand trader/product/risk challenger; no default coding or QA helper is required.
- Vault writes stay under Lite/owner governance and never contain secrets.

## Review loop

1. Lite clarifies objective, scope, dependencies, acceptance, and no-go areas.
2. Codex reviews or implements bounded changes with focused tests; it does not self-approve release readiness.
3. Ploy challenges market/product decision language, setup, trigger, risk, and actionability when relevant.
4. Lite independently verifies diff, tests, source→DB→scan→API→served UI lineage, and desktop/mobile/error journeys.
5. Lite delivers the final PASS/FAIL/REVISE/NOT VERIFIED verdict to Arm.

## Verification rule

A Codex response or green test is implementation evidence only. User-facing Signalix work still requires the applicable rendered UI, live endpoint, freshness/lineage, and failure-state checks before Lite marks it ready.
