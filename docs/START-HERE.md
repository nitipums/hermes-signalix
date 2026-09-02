# Signalix — Start Here

> **STATUS: CURRENT** · Navigation only; product and runtime authority remain in the linked documents.
> **Last reconciled:** 2026-09-02 13:15 ICT

## 1. Current product in one minute

Signalix prepares evidence for an experienced, self-directed Thai swing trader. Arm reviews the chart and evidence and makes the final decision. It is not an automatic trading or order-execution system.

```text
Verified market view
→ Daily trend / strength / 52W-ATH
→ Daily Elliott candidate
→ 60m confirmation and entry timing
→ trigger + invalidation + target + R:R
→ VCP as optional bonus evidence
→ Arm review
```

Canonical product surface:

- API: `/api/setup-candidates`
- UI: `/mvp`
- Product universe: `marginable_long` (`237` currently evaluated; counts are runtime data, not a permanent constant)
- Primary lanes: `REVIEW_NOW`, `SETUP_FORMING`, `DAILY_CANDIDATE`, `WAIT`, `AVOID`, `DATA_BLOCKED`
- Wave labels: machine-generated candidate evidence for Arm review, not truth or an order signal
- Alerts, auto-trading, broker execution, and evaluator auto-caller: OFF/PENDING

## 2. Choose the smallest reading path

| If the task is about… | Read first | Then read only if needed |
|---|---|---|
| Product thesis / roadmap / non-goals | `../vault/Product-Strategy-Market-to-Action.md` | `../vault/Decisions.md` |
| Current setup-candidate contract | `superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md` | `backend/setup_candidate_contract.py`, relevant tests |
| Owner decision / policy | `../vault/Decisions.md` | `docs/current/2026-08-31-elliott-grill-decision-record.md` |
| Architecture / component boundary | `../vault/Architecture.md` | `../vault/Components.md`, source files |
| Daily / 60m pipeline and acceptance | `../vault/Execution-Pipeline.md` | relevant focused plan/spec |
| Runtime / timer / deployment | `../vault/Deployment.md` | `docker-compose.yml`, installed-unit evidence |
| UI / browser / freshness | `../vault/Browser-and-Freshness-Verification.md` | `../vault/Execution-Pipeline.md`, public `/mvp` |
| Lifecycle persistence | `superpowers/specs/2026-08-31-lifecycle-persistence-owner-review-api-design.md` | lifecycle source/tests |
| VCP / replay / migration history | `../vault/VCP-Finder-MVP.md` | `../vault/VCP-Replay-1M-2026-08-26.md`, `archive/` |
| Historical incident / why a decision changed | `../vault/Postmortems/` or `archive/` | dated handoff named by the current note |

## 3. Authority rules

- `AGENTS.md` is the worker safety contract and routing map, not a second product specification.
- `vault/` owns durable product, architecture, deployment, acceptance, and governance notes.
- `docs/superpowers/specs/` owns focused current contracts; `docs/current/` owns concise current decision records.
- `docs/archive/`, `vault/archive/`, dated handoffs, and replay notes are historical evidence, not current direction.
- Kanban owns active execution state only when explicitly used; current board was empty at the 2026-09-02 closeout. Do not mirror card state into docs.
- Generated HTML/JSON, logs, snapshots, worktrees, and scratch directories are artifacts, not authorities.

## 4. Current verified baseline

- Release branch: `release/signalix-mvp-stable`
- Current closeout commit: `fd915e8`
- Local backend readiness: HTTP 200; DB/Redis up
- Public setup API: HTTP 200; `237 evaluated`
- Public `/mvp`: browser loads and renders candidate cards/controls
- Current freshness boundary at 13:14 ICT: Daily EOD unavailable/unknown; 60m fresh from run `9d6c6c77e9ef4f7ca0422d15afd97bfd`
- Known Daily gaps: `3BBIF`, `COM7`, `PR9`

This section is a dated navigation snapshot. For a new runtime claim, probe the live route and update the appropriate deployment/acceptance record; do not treat this file as live telemetry.

## 5. Before changing anything

1. Read `AGENTS.md` and this page.
2. Run `git status --short --branch`, `git worktree list`, and inspect dirty/untracked ownership.
3. Identify the authority document for the concern; stop if two current authorities conflict.
4. Keep source/tests/runtime/browser verdicts separate.
5. Preserve owner artifacts and historical evidence. Never read or include secrets.

## 6. Closeout path

```text
bounded scope → source/test gate → read-model/runtime/API gate → public UI/browser gate
→ documentation sync → explicit PASS / FAIL / REVISE / NOT VERIFIED handoff
```
