# Signalix Execution Pipeline

> **STATUS: CURRENT** · `CANONICAL_FOR: product acceptance sequence and evidence standard`.
> **Reconciled:** 2026-09-01 · T1–T9 promoted; public 390px failure→Retry→recovery gate PASS; evaluator auto-caller remains separate.
> Markdown owns scope/acceptance; Kanban `signalix` owns active worker execution state and handoffs.

> **Status:** Canonical Markdown pipeline, migrated from the retired Signalix Kanban board on 2026-08-15.
>
> Use this document for product scope, acceptance sequence, and evidence policy; use [[Decisions]] for durable choices, focused implementation plans under `/root/signalix/.hermes/plans/` for executable detail, and the Kanban board for named-worker state, dependencies, heartbeats, retries, and evidence handoffs. Do not copy live card status into vault notes.

## Product contract

**Signalix is a setup-to-decision system for Thai swing traders.** It is not a generic market-information portal or a list of stock tips.

```text
Verified data → Daily official setup state → trigger / invalidation / proof needed
→ user review or alert → saved watchlist / decision → immutable outcome evidence
```

The product must let a user answer, quickly and honestly:

1. What setup state is this symbol in?
2. What must happen before it is actionable?
3. What invalidates the thesis or makes chasing unsafe?
4. What evidence and source time support the state?

### Non-negotiable rules
- Deterministic code owns technical calculations, risk, stops, sizing, states, and provenance; LLMs may summarize only.
- Official after-close EOD classification is distinct from intraday emerging observations.
- Public Signalix and the owner-only Portfolio Copilot remain isolated.
- No live auto-trading. Paper/pilot execution comes before any real execution.
- The overview must be usable before detail/chart data load; unknown compact-card data must never cause all symbols to disappear.
- Drawer metadata and decision evidence are separate contracts: genuine missing/insufficient VCP evidence remains `NOT_VERIFIED`; optional canonical metadata shows `Loading…` while `/api/symbol/{symbol}` is pending and `Unavailable` when that request fails. Chart unavailability is reported separately.

## Current verified baseline — 2026-09-01

- The primary product spine is **Daily Trend/Strength + Elliott candidate → 60m Trade Setup → Arm review**.
- The canonical API is `/api/setup-candidates`; it preserves all 237 `marginable_long` rows and six fail-closed lanes: `REVIEW_NOW`, `SETUP_FORMING`, `DAILY_CANDIDATE`, `WAIT`, `AVOID`, `DATA_BLOCKED`.
- T1–T9 source and release promotion are complete. Live `:3001` serves the new DB-built contract with honest blocked/avoid states; public 390px failure→Retry→recovery journey is `PASS` with direct DOM/screenshot evidence. Broader desktop/drawer regression evidence and evaluator auto-caller remain separate.
- VCP, contraction, and breakout-volume are bonus/compatibility evidence. `/api/vcp-finder` and old VCP surfaces are audit/rollback only.
- 931 active ORD remains explicit audit/rollback coverage; `marginable_long` = 237 eligible symbols. Alerts, auto-trading, and broker execution remain off.
- Alerts, automatic trading, and broker execution are `PENDING / FUTURE FEATURE` and remain OFF. The evaluator auto-caller is a separate `PENDING / OWNER DECISION` for automatic lifecycle-evidence persistence only; it is not order execution.

## Current user-validation loop — 2026-09-01

The release is handed to Arm for manual use. Elliott Wave output remains machine-generated candidate/evidence, not unquestionable truth. Review/confirm Wave identification from the rendered chart first; do not tune semantics from assumptions. Any confirmed product issue becomes a new bounded `grill-with-docs → to-spec → to-tickets → implement` cycle.

Lite preflight is `PASS` for the rendered usability journey (desktop/mobile load, tab/filter interaction, candidate→drawer, chart, Wave Evidence visibility after drawer scroll, TradingView link, and no overflow). Semantic Wave correctness remains `NOT VERIFIED` until Arm reviews and confirms the interpretation from the chart.

## Historical baseline — VCP-first MVP (superseded 2026-09-01)

The following older VCP-first baseline is retained as audit history, not current product authority.

## Current reliability status — 2026-08-21

The intraday E2E path is now explicit and verified: full active ORD 60m fetch → DB upsert → evaluator → rebuild dashboard from existing Daily scan → served `:3001` → browser `Last Scanned`. `partial_success` is expected for a bounded Settrade-empty tail and is tolerated when freshness is healthy. The morning no-agent monitor checks the chain every 15 minutes and can self-heal a dashboard freshness mismatch once before alerting.

This closes the previous “DB updated but dashboard stale” gap. Unexpected source/credential/network/code failures still alert for operator action; the system does not silently modify source code.


## Current team-review gate — 2026-09-01

Before any implementation change, use `docs/current/2026-09-01-signalix-independent-review.md` as the review packet. Lite, Codex, and Ploy agree on four `REVISE` areas: DATA_BLOCKED semantics/reason codes, cold-path latency and pagination, chart-ready Elliott evidence markers, and staged legacy quarantine. AskMatt must settle the product decisions and card boundaries first; then use Kanban for one bounded card at a time with independent acceptance.

Only pull one tightly scoped implementation item at a time. Lite is the final evidence gate; worker completion is not final approval. Every active-chain card terminal outcome (`PASS`, `DONE`, `REVISE`, `FAIL`, or `BLOCKED`) requires a delivered report to the owner; `REVISE`/`FAIL` requires bounded remediation or an explicit blocker.

### Now — P0 product/data integrity

| Order | Deliverable | Outcome / acceptance gate | Origin of migrated Kanban work |
|---|---|---|---|
| 1 | **Dashboard VCP decision contract + compact artifact** | **Current dashboard focus:** Daily VCP Watchlist for actionable review plus All VCP · 60m / Explorer for full-universe research/audit. UI/API tests and served endpoints are verified. Alert delivery is paused separately. | Owner-approved dashboard-first MVP scope |
| 2 | **Active ORD instrument master** | An authoritative, active-ORD-only instrument record with symbol, venue, asset class, currency, timezone, session, source, freshness, and active state. No guessed universe expansion. | `signalix-p0-instrument-master` |
| 3 | **Provenance and freshness contract** | Canonical `data_fetched_at`, source, as-of market date, freshness status, and limitations appear consistently in API/UI; never substitute candle timestamp or page-render time. Add regression tests for stale/unknown. | `signalix-p0-provenance-freshness`, timestamp-fix lineage |
| 4 | **Daily vs intraday event boundary** | Persist intraday emerging events append-only against an official Daily baseline. Full EOD scan alone owns the final daily class and reconciles earlier events as confirmed/expired/invalidated/not-confirmed. | `signalix-p0-intraday-emerging-event-ledger`, `signalix-p0-eod-scan-reconciliation` |
| 5 | **Three-dimensional setup contract** | Separate `setup_quality`, `event_timing`, and `entry_action`; retain explainable inputs for liquidity, extension, volume, stop risk, and freshness. Recovery/base/weak names cannot enter an actionable queue from a generic label. | `signalix-p0-scan-criteria-three-dimension-contract` |

### Deferred — do not start until the P0 sequence is accepted

| Deliverable | Boundary |
|---|---|
| Action Queue redesign | Surface Intraday Emerging, Fresh Breakout, Pre-breakout, Retest Watch, Qualified Pullback, and Monitor Only only after the data contracts above exist. |
| Alert Builder MVP | Horizontal level, OHLC snap, trigger, stop/target, expiry, cooldown, audit; no TradingView clone. |
| Recommendation / outcome tracking | Immutable proposal, user decision, simulated/real mode distinction, expiry/invalidation, MFE/MAE and outcome evidence. |
| Paper/pilot portfolio | Isolated simulated portfolio only; no real broker account, credential, routing, or execution mixing. |
| Fundamental/news/factor layer and content drafts | Sourced, period-dated evidence only. No automatic public posting and no invented news or fundamental facts. |

## Retained evidence and lessons from the retired board

### Intraday cadence and source health
- A deployed systemd unit and its drop-ins, not an uncommitted source unit, are the authority for operational verification.
- Separate fetch invocation, fetch result, DB write, and evaluator execution in evidence. A successful later run can otherwise mask an earlier fetch failure.
- Settrade session failures require bounded, observable retry/backoff and explicit partial-success semantics. A successful timestamp may advance only after the relevant data were fetched and upserted.
- Independent freshness monitoring must identify failed invocation, stale intraday bars, or stale evaluator state without creating additional source sessions.

### Data-history integrity
- Keep full-universe scan snapshots immutable and complete; do not retain only published candidates.
- Preserve raw payload, scanner/policy version, source/freshness lineage, run identity, and explicit retry parent/original lineage.
- Intraday observations are events, not changes to the official daily record.
- Daily EOD operational acceptance includes a post-scan `verify_scan_dashboard.py` consistency gate and a scheduled freshness watchdog; service exit 0 alone is not sufficient evidence of a complete run.

### Review discipline
- Bee verifies source, test evidence, deployment status, and UI behavior before final acceptance.
- A migration or restart must never be described as absent when it actually happened; report deployment/schema provenance exactly.
- Work plans must state no-go areas, disposable-test requirements, and production side-effect boundaries explicitly.

## Archived / superseded scope

The following migrated board categories are retained as references but are not active public-product work:

- Owner-only Portfolio Copilot account linking, position calculation, health response, monitor UI, reconciliation, and evidence flows belong to the private module and remain isolated from public Signalix.
- Market View → Instrument → Action contracts, DR/TFEX/fund mapping, and recommendation schemas remain strategic foundation work in [[Product-Strategy-Market-to-Action]]. They do not displace the P0 public scanner/data integrity sequence.
- Public SaaS auth/entitlement and webhook retry work remain later hardening scope.

## Loop prevention — mandatory after 2026-08-28 retrospective (LOCKED 2026-08-28 — owner approved, enforce on every card)

Derived from **260 cards / 355 runs / 154 logs** (`vault/Lesson-Learned-2026-08-28-Loop-Retrospective.md` + `vault/Lesson-Learned-Full-Board-260-Cards-2026-08-28.md` + `hermes-kanban-ops/references/signalix-2026-08-28-loop-retrospective.md`).

**Violating these gates is a process failure, not a worker mistake. Orchestrator must reject or split cards that violate them before dispatch.**

1. **Card scoping (files list mandatory):** One card = one authority. Split every remediation into (a) code + focused tests, (b) `docker compose up -d --build backend && python build_dashboard.py`, (c) live probe + browser. **Card body must list `files:`, `tests:`, `live endpoints:`, `first artifact deadline 15m`**. No `files:` → no dispatch. Prevents `prep 409` loops (`t_7cca0a57`).
2. **Stale runtime gate:** After any MVP/API/frontend edit, Lite must probe `:3001/mvp`, `:3001/api/vcp-finder?...daily_watchlist=true`, and `:8000/health/readiness`; compare served source to the release checkout. `/dashboard.html` is retired and must return 404. Mismatch → REVISE `stale_runtime`. Deploy only via Lite/approved path.
3. **Resource gate:** Docker-heavy or dirty-repo cards use `max_retries=1`. On `load>1.8 or swap<500M` block 10 min with reason; do not instant reclaim. `t_925028aa` (5 runs, timed_out 23m, 262× terminal) must not repeat.
4. **Browser locality:** QA primary evidence is `curl :3001/mvp + curl :3001/api/vcp-finder?...daily_watchlist=true + curl :8000/health/readiness + read_file /worktree/*.json`. `browser_open localhost` is screenshot-only; 119× blocked prepares on `t_cbd7e900` is forbidden.
5. **Completion schema:** `kanban_complete` requires non-empty `artifacts` — at minimum one probe JSON (`sl8000_after.json`). Pure-logic fix without file must still emit a probe. Mirror `artifacts` inside metadata.
6. **Heartbeat checkpoint:** Orchestrator watches `last_heartbeat_at` with empty artifacts. >15 min → bounded checkpoint: complete with artifacts or block with root cause in 10 min. Heartbeat-only (`t_3755a74f` 17 heartbeats, `t_7e1964f8` 59) not acceptable.
7. **No parallel workers** for full-universe or docker rebuild cards (owner directive 2026-08-19).
8. **Stagger + crash-cluster pause:** Do not open >2 large P0/UI cards concurrently (08-22/23 had 29–33 waste runs/day). If `crashed` >3 in 1 min, pause dispatch 10 min (08-19/21 clusters). Lite sole orchestrator enforces.

## Evidence standard for every pull

Before a row above can be marked complete in this document, record:

1. exact files changed;
2. focused RED → GREEN test evidence and relevant regression results;
3. source/freshness/provenance impact;
4. deployment status (including explicitly **not deployed** when applicable);
5. browser/mobile verification when UI changes;
6. Bee final-gate verdict.
7. For any `daily_shortlist.py` change, also record `curl :8000` live probe vs source diff (stale-runtime check) and resource-gate result.
