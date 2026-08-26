# Signalix Memory Cleanup Candidates

> **STATUS: CURRENT**
> This note records cleanup already completed and remaining candidates only.
> Last reviewed: 2026-08-26.

## Keep / current candidates

- VCP MVP/current surfaces: facts 175, 178, 180.
- VCP type candidate taxonomy: fact 181.
- Database scope/cleanup: fact 182.
- Stable SET50/SET100 sync: fact 183.
- Current 60m cadence: fact 179.
- Full ORD / deterministic / provenance architecture: facts 121, 112, 147.
- Current browser/verification safety: fact 71 and current verification skills.

## Superseded/removed cleanup record

- Old 718-symbol taxonomy, old 15m cadence, old checkpoint/provider/margin duplicates, and contradictory quota/liquidity facts were removed from fact_store after current replacements were verified.
- Old Daily Shortlist/All Explorer product contract remains in vault as `STATUS: SUPERSEDED`, preserving historical design evidence.
- Old implementation handoffs and postmortems remain historical unless their header says `STATUS: CURRENT`.

## Skill consolidation — 2026-08-26

- 24 overlapping Signalix skills were archived reversibly under `_archived_consolidation_20260826`.
- Active umbrellas: `signalix-production-delivery`, `signalix-dashboard`, `signalix-screening-replay`.
- Hermes umbrellas created: `hermes-operations`, `memory-documentation-governance`.
- The original skills remain available for restore if an umbrella loses a needed procedure.


Facts about Kanban adoption, provider allocation, worker monitoring, browser quirks, and completed fixes should remain only when they are durable operating rules. One-off task outcomes, card IDs, old counts, and old provider states should not be promoted to permanent memory.

## Work-management fact — resolved

Arm chose Markdown `vault/Execution-Pipeline.md` plus linked focused plans as the active work source. Kanban is audit/archive only. Any older fact saying Kanban is operational source should be removed/compacted after this replacement is confirmed.

## Safety

- No secrets, credentials, tokens, OAuth data, or `.env` values.
- Do not delete a fact solely because it is old; verify the replacement first.
- Prefer replacing a cluster with one current invariant over retaining many near-duplicates.
