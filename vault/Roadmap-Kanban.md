# Roadmap — Kanban Board (Signalix)

> **Human-readable mirror** of live Kanban board `signalix` at `~/.hermes/kanban/boards/signalix/kanban.db`.
> **Operational source of truth:** Kanban DB. This file is not used to dispatch or mutate work.
> Live audit: **2026-08-22**.

## Board snapshot

| Status | Count |
|---|---:|
| done | 18 |
| scheduled | 27 |
| running | 0 |
| blocked | 0 |
| ready / todo / triage | 0 |

## Current operating rule

1. PM maintains task scope, assignee, dependencies, acceptance criteria, and current status in Kanban.
2. Workers use the assigned card as the execution source; no work begins from a roadmap paragraph alone.
3. Specs, product decisions, and architecture remain curated Markdown/vault artifacts and are linked from cards where relevant.
4. Bee is final quality gate: no card reaches a user-facing “ready” claim without Bee’s evidence review.
5. When state changes materially, regenerate this mirror from the live board; never hand-edit it to invent board state.

## Scheduled backlog themes

- **P0 contracts:** provenance/freshness, daily setup state, immutable breakout lifecycle, browser/mobile acceptance
- **P1 product:** radar pattern evidence, risk/reward, saved views, watchlist/delivery, action queue, alert builder, outcome log, industry/group, fundamentals
- **Strategy:** SaaS entitlement/webhook hardening, paper portfolio, DR/TFEX/fund proposals, controlled execution gate, UX research
- **Portfolio:** health/reconciliation, monitor-first UI, Thai equity engine, TFEX monitor, UAT/safety
- **QA:** product-feedback regression pack

## Sync procedure

```bash
env -u HERMES_DELEGATED_CHILD_CONTEXT hermes kanban list --board signalix --json > /tmp/kanban_export.json
```

Use the live board output to regenerate this mirror. Do not include secrets, raw logs, or credentials.
