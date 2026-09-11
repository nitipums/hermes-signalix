# Signalix Execution Pipeline

> **STATUS: CURRENT** · `CANONICAL_FOR: product acceptance sequence and evidence standard`.
> **Reconciled:** 2026-09-02 12:50 ICT · release `5bf3d9a` promoted; intraday scope/metadata and provisional Day/Week chart display verified; Kanban stale R4/R5 graph archived; evaluator auto-caller remains separate.
> Markdown owns scope/acceptance; Kanban `signalix` owns active worker execution state and handoffs.

> **Status:** Canonical Markdown pipeline, migrated from the retired Signalix Kanban board on 2026-08-15.
>
> Use this document for product scope, acceptance sequence, and evidence policy; use [[Decisions]] for durable choices, focused current specs under `../docs/superpowers/specs/` for contracts, and the Kanban board only for active named-worker state, dependencies, heartbeats, retries, and evidence handoffs. Do not copy live card status into vault notes.

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

## Current verified baseline — 2026-09-02

- The primary product spine is **Daily Trend/Strength + Elliott candidate → 60m Trade Setup → Arm review**.
- Intraday UI evidence distinguishes `60m fetched` (`fetch_completed_at`) from `latest completed 60m candle`; a fetch round at 16:45 may correctly expose a 16:00 candle.
- The canonical API is `/api/setup-candidates`; it preserves all 237 `marginable_long` rows and six fail-closed lanes: `REVIEW_NOW`, `SETUP_FORMING`, `DAILY_CANDIDATE`, `WAIT`, `AVOID`, `DATA_BLOCKED`.
- T1–T9 source and release promotion are complete. Live `:3001` serves the new DB-built contract with honest blocked/avoid states; public 390px failure→Retry→recovery journey is `PASS` with direct DOM/screenshot evidence. Broader desktop/drawer regression evidence and evaluator auto-caller remain separate.
- VCP, contraction, and breakout-volume are bonus/compatibility evidence. `/api/vcp-finder` and old VCP surfaces are audit/rollback only.
- 931 active ORD remains explicit audit/rollback coverage; `marginable_long` = 237 eligible symbols. Alerts, auto-trading, and broker execution remain off.
- Alerts, automatic trading, and broker execution are `PENDING / FUTURE FEATURE` and remain OFF. The evaluator auto-caller is a separate `PENDING / OWNER DECISION` for automatic lifecycle-evidence persistence only; it is not order execution.
- Intraday service defaults to canonical `marginable_long`, runs 60m fetch/evaluation with `--no-scan`, and retains `active_ord` only as explicit audit/rollback scope. Daily scan remains the after-close operation to avoid overlapping 30-minute rounds.
- `/api/setup-candidates` overlays the latest completed intraday run while preserving immutable read-model identity and Daily lineage. Current runtime evidence: `237 evaluated`, latest run `fb01ef8fbe70408e82ad3f78b2700fe8`, `full_success`.

## Private actionable-signal transition — 2026-09-11

- Owner-approved direction: a visible private, market-only `BUY_NOW` paper/shadow
  tab covering the trailing seven calendar days. Portfolio data is not required
  for market discovery; position-aware hold/sell logic is later work.
- Phase 1 UI: `/mvp` tab `Shadow Buy Signals · 7D`, backed by the
  token-free `/api/shadow-buy-signals?days=7` point-in-time replay.
  `/api/setup-candidates` remains the unchanged evidence contract.
- Confidence is `EVIDENCE_SCORE` with `NOT_CALIBRATED` probability status.
- Phase 1 source policy, bounded seven-day replay, read-only dashboard route,
  and shadow UI are present. Focused policy/replay/contract/UI tests pass, and
  the local browser verifies the token-free tab and replay control. Runtime replay
  data, public ingress, outcome calibration, alerts, position-aware sells, and
  execution remain `NOT VERIFIED` until separately gated.
- Broker execution and alerts remain OFF.
- **Team Facts API v1 (current public runtime):** `GET /api/team/setup-candidates` and `GET /api/team/setup-candidates/{symbol}/history?timeframe=1D|60m&limit=...` are public, unauthenticated, read-only market-data endpoints over the current published 237-symbol `marginable_long` scope. The feed contains no secrets or private fields and is facts-only; it has no buy, order, or other trading-action semantics. It returns `api_version=team-facts-v1` with deterministic `momentum`, `near_high`, and `pullback` views. Compact items contain identity, current facts from the actual latest price timeframe, neutral deterministic indicators, the latest completed 60m OHLCV bar when available, and provenance. History returns one symbol and one requested timeframe (`price_data`/`1D` or `intraday_price_data`/`60m`), with completed-60m filtering and bounded limits. No setup, wave, lane, trigger, risk, target, mapped label, or order instruction is returned. `volume_ratio_20` is `current_daily_volume / mean(previous_20_daily_volumes)` and is null when fewer than 20 prior Daily volume observations exist. Root freshness metadata is preserved, while missing/stale/incomplete data are evaluated per symbol and excluded with explicit per-view counts/reasons; every applicable view requires a completed 60m bar. The routes use the published read model plus bounded read-only OHLCV queries and never scan, rebuild, load legacy snapshots, write PostgreSQL, send alerts, or execute broker actions. Runtime read-back on 2026-09-10 returned HTTP 200 with `base_active_ord_count=932`, `eligible_count=237`, `excluded_count=695`, views `momentum=16`, `near_high=13`, `pullback=58`, and freshness `partial` due to missing Daily baselines for `3BBIF`, `COM7`, and `PR9`.
- Team item `can_buy=true` is derived from validated membership in the canonical `marginable_long` universe, not inferred as a stock signal; any explicit per-item value must agree, and unknown/non-canonical universes fail closed.
- Team Facts freshness is authoritative only when derived once per symbol from the response rows, `now`, and explicit Daily/60m thresholds. Item provenance, facts, 60m `daily_baseline`, and list/history run envelopes reuse that result; producer values remain under the explicitly non-authoritative `source_metadata` shape `{scope: "published_read_model_report", authoritative: false, reported: {...}}`, with raw freshness keys available only under `reported`. `overall_status` is `fresh` only for complete fresh coverage, `partial` when valid symbols remain beside stale/missing symbols, `stale` when the requested scope is wholly unusable, and `unknown` when freshness cannot be computed. Daily dates and completed 60m timestamps remain distinct; list `as_of` uses latest completed 60m with Daily fallback, while history uses the requested source timestamp.
- `/api/chart-db/{symbol}` uses current-session 60m data as a provisional Day/Week aggregate before EOD; `as_of` is the period key and `latest_time` is the actual latest stored candle timestamp. Browser status was verified with `2026-09-02T05:00:00+00:00`.

## Current OHLCV window and Team Facts acceptance — 2026-09-10

The deterministic chart contract is served by `GET /api/chart-db/{symbol}?timeframe=1D|1W|60M|1M` under policy `technical-indicators-v1`. It exposes OHLCV candles, MA5/10/20/60/120/240, MACD(12,26,9), Wilder RSI(14), Wilder ATR(14), and `indicators.latest.window_summary` for 5/10/20/60/120/240/260 candles. Each window contains Open, High, Low, Close, total/average volume, Change %, Range %, MA where applicable, availability, and provenance. Daily 260 candles is the 52-week trading range; other timeframes label it `260 candles`. Missing or insufficient history is `NOT_VERIFIED`, never inferred.

The Team Facts surface is public unauthenticated read-only by owner decision. It must remain facts-only and separate from `/api/setup-candidates`; no setup, Wave, lane, trigger, risk, target, alert, order, or broker semantics may be exposed. Runtime evidence after release `28f7947`: Team Facts HTTP 200, `marginable_long`, 237 eligible / 695 excluded from 932 active ORD, views momentum 16 / near_high 13 / pullback 58, Daily freshness partial with explicit `3BBIF`, `COM7`, `PR9` missing and intraday fresh. Readiness was `status=ok`, `db=up`, `redis=up`.

## Current user-validation loop — 2026-09-01

The release is handed to Arm for manual use. Elliott Wave output remains machine-generated candidate/evidence, not unquestionable truth. Review/confirm Wave identification from the rendered chart first; do not tune semantics from assumptions. Any confirmed product issue becomes a new bounded `grill-with-docs → to-spec → to-tickets → implement` cycle.

- Lite preflight is `PASS` for the rendered usability journey (desktop/mobile load, tabs/filters, candidate→drawer, chart, Wave Evidence visibility after drawer scroll, TradingView link, and no overflow). Semantic Wave correctness remains `NOT VERIFIED` until Arm reviews and confirms the interpretation from the chart.

## Current session closeout — 2026-09-02 12:50 ICT

- Code review found and remediated chart route scope, `/api/chart-db` bypass, and weekly reverse-order defects before final promotion. Focused and full backend tests passed; `compileall`, `git diff --check`, and `systemd-analyze verify` passed.
- Promoted commits: `2d43a59`, `31ed535`, `211a30e`, `3a9b113`, `1da2e00`, `5bf3d9a`; remote `release/signalix-mvp-stable` matches `5bf3d9a`.
- Runtime: installed intraday unit/timer byte-identical to source; timer active; backend/dashboard recreated; readiness `ok`; public `/mvp`, setup API, and chart API returned HTTP 200.
- Remaining review follow-up is `REVISE`: request-time intraday metadata overlay should later use a bounded cache/published metadata seam, and audit-run universe identity should be explicit so `active_ord` cannot contaminate `marginable_long` metadata. This is a follow-up, not silently marked complete.
- Handoff: `.scratch/2026-09-02-1250-intraday-chart-runtime-close-handoff.md`.

## Prior session closeout — 2026-09-02

- Code/runtime fix promoted and pushed: `2efed71` (full-universe freshness aggregation) and `cfc2c22` (separate intraday fetch time from completed-candle time).
- Public verification: `/mvp` 200; setup API `237 evaluated / 50 returned`; `/dashboard.html` retired 404; UI showed `60m fetched 01 Sept 2026 16:47 ICT` and `latest completed 60m candle 01 Sept 2026 16:00 ICT`; TradingView href and mobile drawer scroll owner verified.
- Data boundary remains explicit: `BKIH` latest stored 60m is 15:00 ICT pending the next guarded intraday run; `3BBIF`, `COM7`, `PR9` lack official Daily rows. A bounded Settrade Daily retry for `2026-09-01` returned zero rows, so no fabricated/fallback official EOD data was written. Next repair windows are intraday from 10:00 ICT and EOD from 18:30 ICT.
- Kanban `signalix`: stale R4/R5 todo/blocked graph archived (not force-closed/purged); active todo/blocked/ready/running/review are zero; historical done count is 168.
- Remaining owner-owned/untracked artifacts: `.scratch/2026-09-02-signalix-session-close-handoff.md` and `factsheets/factsheets.jsonl`; do not stage, reset, clean, or delete broadly.

## Historical baseline — VCP-first MVP (superseded 2026-09-01)

The following older VCP-first baseline is retained as audit history, not current product authority.

## Current reliability status — 2026-08-21

The intraday E2E path is now explicit and verified: full active ORD 60m fetch → DB upsert → evaluator → rebuild dashboard from existing Daily scan → served `:3001` → browser `Last Scanned`. `partial_success` is expected for a bounded Settrade-empty tail and is tolerated when freshness is healthy. The morning no-agent monitor checks the chain every 15 minutes and can self-heal a dashboard freshness mismatch once before alerting.

This closes the previous “DB updated but dashboard stale” gap. Unexpected source/credential/network/code failures still alert for operator action; the system does not silently modify source code.


## Historical team-review inputs — 2026-09-01

`../docs/archive/reviews/2026-09-01-signalix-independent-review.md` is a historical review packet, not a mandatory current preflight. It remains useful evidence for DATA_BLOCKED semantics, latency/pagination, chart markers, and staged legacy quarantine. New work starts from `docs/START-HERE.md`, the relevant current spec/decision, and a fresh source/runtime baseline.

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
