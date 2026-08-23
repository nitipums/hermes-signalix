# Signalix Memory Cleanup Candidates

> **STATUS: REVIEW_REQUIRED**
> This note is a candidate list only. It does not delete or rewrite fact_store entries.
> Last reviewed: 2026-08-23.

## Keep / current candidates

- Stage-first / FULL ORD / LAYER1-LAYER2 architecture: facts 117, 121, 112.
- Current feed-availability boundary: fact 142.
- Current generated-artifact safety lesson: fact 156.
- Current dashboard provenance: fact 135.
- Current team/review model: facts 145, 147, 149, 158.
- Product direction: canonical strategy note; fact 58/45 are supporting context only.
- English-only product UI preference: fact 15, subject to current product strategy.

## Superseded candidates to compact/remove after replacement check

- Fact 5 — original Signalix architecture, explicitly superseded.
- Fact 29 — older Portfolio Copilot boundary, explicitly superseded.
- Fact 55 — five-group daily screener, superseded by stage-first.
- Fact 56 — old breakout lifecycle, superseded by stage-first.
- Fact 60 — old 718-symbol / price-floor policy, superseded by FULL ORD.
- Fact 76 — old taxonomy repair backlog, superseded by stage-first.

## Task-progress / operational facts to review

Facts about Kanban adoption, provider allocation, worker monitoring, browser quirks, and completed fixes should remain only when they are durable operating rules. One-off task outcomes, card IDs, old counts, and old provider states should not be promoted to permanent memory.

## Work-management fact — resolved

Arm chose Markdown `vault/Execution-Pipeline.md` plus linked focused plans as the active work source. Kanban is audit/archive only. Any older fact saying Kanban is operational source should be removed/compacted after this replacement is confirmed.

## Safety

- No secrets, credentials, tokens, OAuth data, or `.env` values.
- Do not delete a fact solely because it is old; verify the replacement first.
- Prefer replacing a cluster with one current invariant over retaining many near-duplicates.
