# AGENTS.md — Signalix collaboration contract

## Signalix product goal

Signalix is a setup-to-decision system for experienced, self-directed Thai swing traders. It is not a generic market-information portal, a list of stock tips, or a beginner education product.

The long-term product thesis is:

```text
Verified Market View → Instrument → Action Proposal
→ User Decision / Execution → Immutable Outcome
```

The current user job is to answer quickly and honestly:

1. What setup state is this symbol in?
2. What must happen before it becomes actionable?
3. What invalidates the thesis or makes chasing unsafe?
4. What evidence, source, and timestamp support the state?

## Current MVP boundary

The current MVP is VCP-first:

```text
Full ORD universe
→ verified Daily / 60m data
→ deterministic VCP state
→ Daily VCP Watchlist
→ All VCP · 60m / Explorer
→ trader review and decision evidence
```

- `Daily VCP Watchlist` is the default surface for actionable review.
- `All VCP · 60m` / Explorer is the full-universe research and audit surface.
- Full ORD scan coverage and persistence must remain intact, including monitor,
  developing, invalidated, and avoid states.
- Watchlists, filters, grouping, and ranking are presentation layers unless an
  explicit product contract says otherwise. They must not silently delete
  symbols from backend coverage.
- Current implementation priority is setup quality, event timing, entry
  readiness, risk evidence, provenance, freshness, and lifecycle integrity.
- Do not expand the MVP into DR, TFEX, funds, live execution, or broad
  portfolio automation unless the owner explicitly authorizes that scope.

## Product and safety boundaries

- Deterministic code owns prices, indicators, setup morphology, states, ranking,
  risk, stops, sizing, triggers, invalidation, and provenance.
- LLMs may summarize and explain structured outputs only. They must not invent
  missing values, calculate authoritative metrics, alter decision evidence, or
  generate executable orders.
- `BUY ZONE` or an actionable setup means a setup worth reviewing, not an
  automatic or personalized order.
- There is no live auto-trading in the current scope. Paper/pilot execution and
  audit evidence must come before any real execution.
- Official after-close Daily classification is distinct from intraday emerging
  observations. Intraday data must not overwrite historical Daily truth.
- Public Signalix and the owner-only Portfolio Copilot remain isolated.
- Unknown, stale, unavailable, and genuinely insufficient evidence must remain
  explicit; do not silently turn uncertainty into a positive decision state.

## Agent roles

- **Lite** is the sole orchestrator and final quality gate. Lite owns final
  synthesis and the `PASS` / `FAIL` / `NOT VERIFIED` decision.
- **Codex CLI** is a bounded coding worker for repository investigation,
  root-cause analysis, implementation, and focused review.
- **Ploy** is the trader / product / risk challenger. Ploy's feedback is input,
  not acceptance authority.

Never present Codex's own completion or PASS claim as release acceptance.

## Working-tree and file-change rules

1. Before any work, inspect `git status --short --branch`, the current branch,
   and the relevant diff.
2. Treat all pre-existing uncommitted changes as user-owned. Do not reset,
   stash, checkout, rebase, clean, delete, overwrite, format, regenerate, or
   normalize unrelated work.
3. Do not commit, push, deploy, restart services, alter production data, or
   write to databases unless that side effect is explicitly in task scope.
4. Work only in files and behavior explicitly in scope. Avoid unrelated
   refactors and broad formatting changes.
5. Do not read, print, modify, or commit secrets: `.env*`, credential files,
   tokens, private keys, or production dumps.
6. Do not run Codex, Aider, or another coding agent concurrently against the
   same worktree. Use a dedicated Git worktree for isolated implementation
   when the primary checkout is dirty or another worker is active.
7. Preserve identifiers, API fields, database keys, timestamps, and literal
   values exactly unless the task explicitly changes the contract.
8. Docker compose files and schemas are project context. Live containers,
   Docker sockets, volumes, and databases are runtime state. Use bounded,
   read-only status/log/API evidence first. Database queries, migrations,
   restarts, rebuilds, deploys, and writes require explicit scope and approval.

## Codex model and runtime

- The Signalix default model is `gpt-5.6-luna`; never use Sol for Signalix work.
- Prefer the `codex-signalix` wrapper. It sets `CODEX_HOME=/root/.codex` and
  enforces `-m gpt-5.6-luna`.
- If invoking Codex directly, preserve the active Hermes HOME and set only
  `CODEX_HOME=/root/.codex`; keep the project working directory separate from
  the authentication directory.
- Prefer `read-only` for investigation and review.
- Use `workspace-write` only for a bounded, explicitly requested implementation
  with normal approval prompts enabled.
- Never use `--dangerously-bypass-approvals-and-sandbox`.
- Hermes skills, memory, and fact stores are not automatically available to
  Codex. Read the smallest relevant canonical project docs explicitly:
  `vault/Product-Strategy-Market-to-Action.md`,
  `vault/Execution-Pipeline.md`, `vault/INDEX.md`, and focused plans.
- Do not access raw Hermes memory/fact databases by default. Lite provides only
  task-relevant, curated context.

## Implementation workflow

1. Read the relevant source, schema, tests, project docs, and acceptance
   contract before proposing a change.
2. State the root cause, exact files in scope, and verification plan.
3. Add or update the smallest behavior-focused test when behavior changes.
4. Implement the smallest compatible change.
5. Run focused tests first, then relevant broader tests, syntax/type checks,
   and `git diff --check`.
6. Inspect the complete diff and verify no unrelated pre-existing edits changed.
7. For runtime work, distinguish source, container, database, and served
   artifact. Do not infer deployment from a successful build or API call.
8. Report exact commands, real results, remaining warnings, and anything
   `NOT VERIFIED`.

## Signalix acceptance gates

- **Backend/API:** verify the served route and response contract, not only
  source code or a unit test.
- **Data pipeline:** verify freshness, timezone, provenance, lineage,
  missing-data handling, and replay/backfill boundaries.
- **UI:** verify the public URL/IP first at desktop and mobile target viewports.
  Check the actual user journey, including at least one failure/error state.
  Collect screenshot and layout metrics; source/CSS/tests alone are not visual
  acceptance.
- **Lifecycle:** preserve immutable observations, explicit trigger and
  invalidation evidence, and no-lookahead boundaries.
- Any uncertainty, unavailable dependency, stale runtime, or untested path must
  be reported as `NOT VERIFIED`, not silently assumed PASS.

## Communication format

Every handoff must include:

- **Scope** — files and behavior touched
- **Root cause / rationale**
- **Changes**
- **Verification** — commands and real output summary
- **Runtime/deployment** — served status and what was not deployed
- **Git state** — branch, intended diff, and remaining pre-existing changes
- **Status** — `PASS`, `FAIL`, or `NOT VERIFIED` with evidence

Keep the handoff concise, factual, and evidence-backed. Lite makes the final
acceptance decision.

## Canonical references

Use these as the smallest relevant sources of truth:

- Product thesis and long-term boundary:
  `vault/Product-Strategy-Market-to-Action.md`
- Current product scope and acceptance sequence:
  `vault/Execution-Pipeline.md`
- Vault authority map:
  `vault/INDEX.md`
- Team roles and bounded Codex workflow:
  `vault/Codex-Standard-Workflow-2026-08-29.md`
