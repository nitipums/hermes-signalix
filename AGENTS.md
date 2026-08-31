# AGENTS.md — Signalix collaboration contract

> **STATUS: CURRENT** · Owner-aligned working instructions for Lite and Codex.
> **Last reconciled:** 2026-08-31
> **Authority:** owner-approved direction in `docs/superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md`, with current acceptance/evidence rules in `vault/Execution-Pipeline.md`.

## Product identity

Signalix is a setup-to-decision system for experienced, self-directed Thai swing traders. It finds and prepares candidate setups; **Arm reviews the evidence, checks the chart, and makes the final trade decision**. It is not a generic market-information portal, stock-tip list, or automatic trading system.

The product flow is:

```text
Verified Market View
→ Trend / Strength / 52W-ATH context
→ Daily Elliott candidate (Wave 1 / Wave 2 / Early Wave 3)
→ 60m confirmation and entry timing
→ Trigger + invalidation + Fib target + R:R
→ VCP as bonus evidence
→ Arm review and decision
```

## Current product direction — clean replacement

The primary decision spine is **Trend + Elliott candidate + Trade Setup**. This replaces VCP-first serving as the product authority; it does not delete valid historical VCP data or old observations.

- **Daily** is authoritative for big-picture trend, strength, 52W/ATH, and Elliott structural candidates.
- **60m** is for early Wave 3 confirmation, lower-timeframe structure, trigger, and entry timing.
- Daily and 60m evidence must stay explicitly separated. Never label 60m-derived values as Daily evidence.
- Primary candidates cover the observable progression around **Wave 1 advance → Wave 2 pullback/near completion → early Wave 3 / continuation**. Elliott output is a conservative machine-generated evidence interpretation, not an objectively confirmed count.
- Trend/strength is first-class evidence: uptrend/emerging uptrend, 20d/60d advance, relative strength, distance to 52W High, 52W breakout, ATH breakout, and distance from the reference.
- Sector/industry and peer breadth/leadership are context and ranking evidence, not silent hard exclusions.
- VCP, contraction, and breakout-volume evidence remain optional `bonus_evidence`; VCP must not remove a valid non-VCP candidate.
- R:R is deterministic evidence, not a standalone reason to accept a setup. Trigger, technically meaningful invalidation, explicit target method, and sufficient/fresh data are also required.
- `REVIEW` means worth chart review only. It is not permission, personalized advice, or an executable order.

### Decision and state boundaries

Structural `wave.state` uses only:

```text
WAVE_1_ADVANCE | WAVE_2_FORMING | WAVE_2_NEAR_COMPLETION
EARLY_WAVE_3 | WAVE_3_CONTINUATION | WAVE_4_CORRECTION
WAVE_5_ADVANCE | UNKNOWN
```

- `INVALIDATED` and `EXTENDED` belong to the setup/risk layer, not the Elliott state. Setup status is `FORMING`, `PRE_TRIGGER`, `TESTED_TRIGGER`, `TRIGGERED`, `EXTENDED`, `INVALIDATED`, `EXPIRED`, or `DATA_BLOCKED`.

User-facing decision lanes are:

```text
REVIEW_NOW | SETUP_FORMING | DAILY_CANDIDATE | WAIT | AVOID | DATA_BLOCKED
```

T1–T7 implementation layers are complete in the prototype branch; T8 full-universe ranking and served acceptance remains pending. Stale, missing, invalid, incoherent, or insufficient evidence must fail closed into an explicit unknown/blocked state. Never infer a metric, wave label, target, or risk value from a similarly named field.

## How to use this file

`AGENTS.md` is the **entrypoint, routing map, and safety contract** for coding agents. It is not a second product specification. Durable product/architecture/operations details belong in the canonical documents below.

Before any task, Codex must:

1. Read this file.
2. Classify the task by concern and read the smallest relevant authority from the routing table.
3. Check the authority document's status/date and inspect the real source/tests/runtime relevant to the task.
4. If two current sources conflict, stop before editing and report the conflict, affected files, and which owner decision is needed. Do not resolve semantic conflicts from memory or by choosing the newest filename.
5. In the handoff, name the authority documents read and state whether the change requires a documentation sync.

### Authority routing table

| Task concern | Read first | Update when the contract changes |
|---|---|---|
| Product thesis, user, surfaces, non-goals, roadmap | `vault/Product-Strategy-Market-to-Action.md` | Product strategy + focused design/spec |
| Current setup-candidate direction and API contract | `docs/superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md` | Focused design/spec + `AGENTS.md` routing/guardrail only if agent behavior changes |
| Current product acceptance sequence and evidence | `vault/Execution-Pipeline.md` | Execution pipeline |
| Vault authority/index and note status | `vault/INDEX.md`, `vault/Documentation-Governance.md` | Index/status banners when notes are added, moved, superseded, or archived |
| Current architecture/component behavior | `vault/Architecture.md`, `vault/Components.md` | The relevant architecture/component note |
| Deployment, timers, served runtime, ingress | `vault/Deployment.md` | Deployment/runbook note with real verification evidence |
| VCP compatibility, audit, replay, marginable-long evidence | `vault/VCP-Finder-MVP.md`, `vault/2026-08-30-Signalix-V2-Marginable-Serving-Closeout.md` | Focused VCP/replay/closeout note; do not silently rewrite the new product contract |
| Codex roles, provider, model, invocation | `vault/Codex-Standard-Workflow-2026-08-29.md` | Codex workflow note and this file only when the worker contract changes |

### Documentation sync protocol

- **Code behavior change:** update the owning source-of-truth document in the same bounded task when the documented contract is now different; do not update unrelated notes or generated artifacts.
- **Product decision change:** update the focused design/decision authority first, then update this file only with a concise routing rule or invariant. Do not copy the whole decision into `AGENTS.md`.
- **Runtime/deployment change:** update the deployment authority with command, timestamp/as-of, environment, and evidence; never claim served state from source changes alone.
- **Legacy migration:** preserve historical/audit evidence and mark old routes/notes as compatibility, superseded, or historical. Never make two documents appear equally authoritative.
- **Before handoff:** run a reference scan for the old contract/labels, inspect the complete diff, and list any intentionally untouched documents plus unresolved conflicts.

## Serving and migration boundary

- The target canonical API is `/api/setup-candidates`; `/mvp` should consume one setup-candidate contract.
- During migration, `/api/vcp-finder` and VCP artifacts may remain for compatibility, audit, replay, or rollback, but they are not the new primary decision authority.
- Do not create a second competing visible decision label by mixing legacy Stage/Phase/Daily/VCP labels into the new primary contract. Keep compatibility fields in an explicit audit/legacy namespace.
- Retain and reuse validated Thai ORD universe, Daily/60m ingestion, freshness/provenance, MA/RS/52W/ATH, Fib/risk/target math, sector data, VCP evidence, and append-only lifecycle foundations.
- Current operational research scope is `marginable_long` = active Thai ORD ∩ owner-supplied marginable list ∩ `can_buy=true`; current validated counts are **931 active ORD**, **237 eligible**, **694 excluded**. Preserve explicit `active_ord` audit/rollback mode. Do not silently generalize replay evidence to excluded symbols.
- `EVENT_WATCH` is an uncapped discovery/watch-only lane when used by the current transition surface. Incomplete volume is evidence/warning, not a discovery blocker. `REVIEW_NOW` is the only actionable lane in that legacy/current transition contract; event evidence alone cannot create confirmation or actionability.
- Alerts and auto-trading are off. Do not enable them, add broker execution, or expand beyond Thai ORD without explicit owner scope.

## Agent roles

- **Arm** — owner and decision maker; approves product scope and production-impacting side effects.
- **Lite** — sole orchestrator and final quality gate. Lite defines the brief, controls scope, independently checks source → tests → runtime → browser, and owns `PASS` / `FAIL` / `REVISE` / `NOT VERIFIED`.
- **Codex CLI** — bounded coding/review/implementation worker using `gpt-5.6-luna`. Codex supplies evidence and changes; it never self-approves production readiness.
- **Ploy** — on-demand trader/product/risk challenger. Feedback is input, not acceptance authority.

Khim and Nida are historical references, not default active Signalix team members.

## Working-tree and safety rules

1. Before work, run `git status --short --branch` and inspect the relevant diff.
2. Existing uncommitted changes are owner-owned. Do not reset, stash, checkout, rebase, clean, delete, overwrite, format, regenerate, or normalize unrelated work.
3. Never run multiple coding agents concurrently against the same worktree. Use a dedicated worktree when isolation is required.
4. Do not commit, push, deploy, restart services, migrate, write databases, or alter production data unless the task explicitly includes that side effect.
5. Work only in the named files/behavior. Avoid broad refactors and unrelated formatting.
6. Never read, print, modify, or commit `.env*`, credentials, tokens, private keys, production dumps, or other secrets. Do not put secrets in prompts or output files.
7. Preserve identifiers, API fields, database keys, timestamps, and literal values exactly unless the task explicitly changes the contract.
8. Treat Docker files, live containers, volumes, sockets, and databases as runtime state; inspect read-only evidence first.

## Codex runtime contract

Use the ChatGPT subscription credentials explicitly and pin the model every time:

```bash
cd /root/signalix
HOME=/root/.hermes/profiles/lite/home \
CODEX_HOME=/root/.codex \
codex exec --ephemeral -m gpt-5.6-luna -s read-only \
  "<bounded review brief; do not edit, commit, reset, stash, or read secrets>"
```

For an explicitly approved bounded implementation, use `-s workspace-write` instead of `read-only`. Always:

- run from `/root/signalix` or a disposable Git worktree, never `/root`;
- preserve the active Hermes `HOME` and set only `CODEX_HOME=/root/.codex`;
- capture `git status --short --branch` before starting;
- state exact files, tests, acceptance criteria, and no-go areas in the brief;
- run a small non-destructive inference probe before a substantial run when the lane has not been checked;
- prohibit reset/stash/checkout/rebase/commit/push/deploy/restart/database writes unless explicitly in scope;
- never use `--dangerously-bypass-approvals-and-sandbox`;
- do not assume Hermes memory, skills, or fact stores are available—provide only curated task context;
- do not run Codex concurrently with another coding agent in this worktree.

Codex may report a missing `bubblewrap` binary while using its bundled fallback; verify behavior rather than treating that warning as a model failure. Free disk space must be checked before large runs.

## Implementation workflow

1. Read the smallest relevant source, schema, tests, and canonical docs before proposing a change.
2. State root cause, exact files in scope, no-go areas, and verification plan.
3. For behavior changes, add/update the smallest behavior-focused test first and prove the intended failure when practical.
4. Implement the smallest compatible change. Keep canonical fields separate from legacy/audit aliases.
5. Run focused tests, relevant broader tests, syntax/type checks, and `git diff --check`.
6. Inspect the complete filesystem diff; Codex's prose, diff proposal, or green self-reported test is not proof.
7. For runtime work, distinguish source, container, database, served artifact, and public ingress. A build or local API response does not prove deployment.
8. Report exact commands/results, warnings, untested paths, and `PASS` / `FAIL` / `REVISE` / `NOT VERIFIED` honestly.

## Acceptance gates owned by Lite

- **Contract:** one primary setup-candidate contract; no competing legacy primary label.
- **Data:** Thai ORD scope, freshness, timezone, provenance, lineage, missing-data handling, and no-lookahead boundaries are explicit.
- **Backend/API:** verify the served endpoint and response contract, not only source/tests. For the new spine, check `/api/setup-candidates`; for transition work, check the relevant VCP route and its explicit legacy status.
- **UI:** verify public URL/IP first at desktop and 390px mobile. Exercise the real candidate/card/drawer journey, readability/layout metrics, and at least one API/error or empty/data-blocked path. Source/CSS/tests alone are not visual acceptance.
- **Decision safety:** no LLM-generated authoritative calculations, Elliott labels, or executable orders; no automatic BUY.
- **Final verdict:** missing runtime, freshness, browser, or failure-state evidence is `NOT VERIFIED`, never silently PASS.

## Handoff format

Every Codex/Lite handoff must include:

- **Scope** — files and behavior touched
- **Root cause / rationale**
- **Changes**
- **Verification** — exact commands and real result summary
- **Runtime/deployment** — served/public status and what was not deployed
- **Git state** — branch, intended diff, remaining pre-existing changes
- **Status** — `PASS`, `FAIL`, `REVISE`, or `NOT VERIFIED` with evidence

Lite delivers the final acceptance decision to Arm.

## Canonical references

Read only the smallest relevant set, in this order:

- Product direction and clean-replacement design:
  `docs/superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md`
- Product scope and acceptance/evidence policy:
  `vault/Execution-Pipeline.md`
- Vault authority map:
  `vault/INDEX.md`
- Current VCP compatibility/audit contract:
  `vault/VCP-Finder-MVP.md`
- Current marginable-long serving/replay evidence:
  `vault/2026-08-30-Signalix-V2-Marginable-Serving-Closeout.md`
- Codex team/runtime workflow:
  `vault/Codex-Standard-Workflow-2026-08-29.md`
