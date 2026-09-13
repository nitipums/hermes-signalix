# Signalix Memory Cleanup Candidates

> **STATUS: CURRENT**
> This note records cleanup already completed and remaining candidates only.
> **Last reviewed:** 2026-09-01 · Level-1 memory consolidated; Level-3 fact_store reduced to 25 compact facts; Wallet detail and obsolete Signalix progress facts removed.

## Keep / current candidates

- User identity/preferences and memory policy: facts 23, 25, 200, 208, 211.
- Current Signalix contract/Wave semantics: facts 215, 219, 220, 226.
- Current release/automation boundary: facts 227, 229; canonical detail is in the current handoff and Execution-Pipeline.
- Browser/Git safety: facts 71, 228 and current verification skills.
- Portfolio Copilot bounded-context direction: fact 50; detailed execution remains future work.

## Superseded/removed cleanup record

- Old VCP-first serving, old 15m/stage/L2 details, old checkpoint/provider/margin duplicates, Wallet transaction/account details, and contradictory quota/liquidity facts were removed from fact_store after current replacements were verified.
- Old Daily Shortlist/All Explorer product contract remains in vault as `STATUS: SUPERSEDED`, preserving historical design evidence.
- Old implementation handoffs and postmortems remain historical unless their header says `STATUS: CURRENT`.

## Skill consolidation — 2026-09-13

- Legacy Signalix procedures were consolidated into a small active set and archived reversibly through Hermes Curator.
- Current core: `signalix-skill-router`, `signalix-product-strategy`, `signalix-trend-map`, `signalix-data-lineage`, `signalix-screening-research`, `signalix-dashboard-acceptance`, and `signalix-production-ops`.
- Support: `signalix-lite-codex-owner-loop`, `signalix-local-development-environment`, and `signalix-documentation-governance`.
- Archived originals remain available for restore if a focused procedure is later proven necessary.


Facts about Kanban adoption, provider allocation, worker monitoring, browser quirks, and completed fixes should remain only when they are durable operating rules. One-off task outcomes, card IDs, old counts, old provider states, and profile-specific bookkeeping should not be promoted to Lite permanent memory.

## Work-management fact — resolved
Arm chose Markdown `vault/Execution-Pipeline.md` plus linked focused plans as the product-scope and acceptance authority. Kanban is the active durable execution/orchestration state for the current gated run; live card status is not mirrored into vault notes. Older audit-only wording is superseded by the 2026-08-28 terminal-reporting decision.

## Profile cleanup — 2026-09-13

Signalix currently uses Lite as sole orchestrator/final gate. Ploy is available alone only when Arm explicitly requests a trader/product challenge. Other Signalix sub-agents are not dispatched unless Arm changes this rule. Wallie remains outside Signalix.

## Safety

- No secrets, credentials, tokens, OAuth data, or `.env` values.
- Do not delete a fact solely because it is old; verify the replacement first.
- Prefer replacing a cluster with one current invariant over retaining many near-duplicates.
