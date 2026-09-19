# Signalix Execution Pipeline

> **STATUS: CURRENT** · `CANONICAL_FOR: product acceptance sequence and evidence standard`.
> **Reconciled:** 2026-09-17 ICT · canonical product line is Daily Trend Mapping at `/trend-map` and `/api/trend-map`; Trend Route artifact `trend-route-cc791d2d85645bce9b5347b8` is served at `/api/trend-map/{symbol}/route`; source/release commit is `cf85be67d15f9e189b7d73bce6e29a576244859a`. Automated EOD publication wiring and Trend Route rollback remain `NOT VERIFIED`. The former shadow naming is retired. `/mvp` and `/api/setup-candidates` are historical/audit only and retained as historical/audit source. Runtime and commit claims require fresh read-back from the checkout and served route.
> Markdown owns scope/acceptance; Kanban `signalix` owns active worker execution state and handoffs.

> **Status:** Canonical Markdown pipeline, migrated from the retired Signalix Kanban board on 2026-08-15.
>
> Use this document for product scope, acceptance sequence, and evidence policy; use [[Decisions]] for durable choices, focused current specs under `../docs/superpowers/specs/` for contracts, and the Kanban board only for active named-worker state, dependencies, heartbeats, retries, and evidence handoffs. Do not copy live card status into vault notes.

## Current acceptance focus — canonical Trend Mapping

The acceptance target is the public Daily Trend Mapping surface at `/trend-map`
and `/api/trend-map`. Verify deterministic source, immutable artifact/pointer,
API schema, freshness/quality distribution, non-actionable boundary, and the
real desktop/mobile chart journey. The retired `/mvp` and
`/api/setup-candidates` surfaces are historical/audit only and are not current
acceptance targets. Latest reload read-back is recorded in `Deployment.md`.

### Trend Route acceptance — 2026-09-17

Trend Route is a symbol-scoped historical evidence extension at
`/api/trend-map/{symbol}/route` and within the existing Trend Map drawer. It
replays the unchanged deterministic Main Trend classifier over up to 260
completed Daily sessions at one market-wide cutoff, from a validated immutable
read model. Current real artifact read-back: `trend-route-cc791d2d85645bce9b5347b8`,
237 routes, 229 `FULL`, 8 explicit `PARTIAL`; public TEAM API and desktop/390px
browser journeys passed. The feature remains `PRODUCTION_READ_ONLY`,
`research_only=false`, and `actionability=NONE`. Source commit is `3733c4d`;
rollback drill for the new route artifact remains `NOT VERIFIED`.

### Daily quality-window boundary

Daily quality gating applies to the same newest bounded analytical window used
for classification (`RETRIEVAL_CAP=430`). Historical invalid OHLCV rows outside
that selected window remain untouched and may be retained as audit evidence, but
must not block the current Trend Map classification. Invalid rows inside the
selected window remain fail-closed as `DATA_BLOCKED` / `INVALID_DATA`.

### Quote/display versus scan boundary

Trend Map classification and scan evidence remain sourced from the immutable
completed Daily/EOD artifact. Display-only `price`, `change`, and `%change` may
be overlaid at the read path from the latest completed 60m intraday bar, using
the immediately prior Daily close as the deterministic change basis. The API
must expose the intraday timeframe/provenance and `provisional=true`; missing
or unusable intraday data must retain the EOD quote and its Daily provenance.
The overlay must not alter `main_trend`, data-quality/status fields, classifier
evidence, artifact `as_of`, or the non-actionable boundary.

The intraday display quote should be prebuilt after the committed intraday
ingestion boundary into a compact validated read model. The public request path
must read that artifact without PostgreSQL access; stale/missing/invalid
artifacts fall back to the immutable EOD quote with explicit provenance.

Intraday and EOD publication boundaries must prebuild compact validated chart
read models for every drawer timeframe: `1D`, `60M`, `1W`, and `1M`. The
The request path reads the selected artifact and uses DB fallback only when that
artifact is unavailable or stale; chart indicators remain deterministic
source-code outputs. This is a Signalix design invariant, not an optional
performance enhancement. Insufficient usable candles must render an explicit
`NOT_VERIFIED`/unavailable state, never a blank canvas.

### Full Trend Map UX remediation boundary

The Trend Map first screen must make the EOD classification versus provisional
completed-60m display quote distinction visible before drawer interaction. The
drawer must have an explicit recoverable script/chart failure path, distinguish
official Daily from derived Daily provenance, preserve stale-response guards,
and support keyboard focus entry, containment, and restoration. Blocked or
invalid Daily classifications remain visible with an explicit reason/filter;
quote availability must not imply classifier availability. At 390px the page
must remain contained while retaining an accessible full-value affordance for
truncated Main Trend labels.

### Trend Map drawer navigation remediation — 2026-09-13 16:34 ICT

- Acceptance contract: opening a Trend Map row and moving to the next/previous row must refresh the chart for the newly selected symbol; horizontal swipe is supported while vertical drawer scrolling remains available.
- Evidence: `pytest -q backend/test_mvp_ui_feedback_contract.py backend/test_shadow_trend_map.py -rA` — `51 passed`; `node --check backend/frontend/shared-drawer.js` — PASS; `git diff --check` — PASS.
- Public browser evidence at 390px: `TEAM`/`RJH`/`KCG` navigation updated both drawer position and exact `/api/chart-db/{symbol}?timeframe=1D` request; horizontal touch swipe advanced the drawer. The surface remained `PRODUCTION_READ_ONLY`, `research_only=false`, and `actionability=NONE`.
- Status: source/test/browser behavior `PASS`; release commit/push `NOT PERFORMED`; unrelated dirty paths remain owner-owned and are not included in this bounded change.

### Fresh promotion evidence — 2026-09-13

- Prior source/runtime baseline for the promotion evidence below was `45095b320fba6bde72ff3af553ffdaa366426bac`; Issue #22 implementation baseline is `f99becb5d5d50a49331419bb8d878ae6b9f6d979`; the bounded drawer working-tree verification is recorded above and no new release promotion is claimed here.
- Focused source gate: fallback/Trend Map command `pytest -q backend/test_derived_daily_fallback.py backend/test_shadow_trend_map.py` returned `52 passed`; publisher/intraday/artifact regressions also passed; Python compile and `git diff --check` passed. The broader `/mvp` frontend contract has 20 pre-existing failures on the base commit and is not attributed to this Trend Map slice.
- Runtime/API: backend/dashboard recreated; readiness `ok`; local and public `/api/trend-map` returned HTTP 200 with `PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`, `VERIFIED`, `FRESH`, and `237/237` rows.
- Browser: desktop 237 rows plus drawer/chart; 390px mobile no overflow (`scrollWidth=390`); failure → Retry showed zero rows and recovery returned 237 rows. Hermes `browser_exec` helper syntax was separately verified after restoring the managed Browser Use CLI path.
- Rollback: `PASS`; isolated source-plus-artifact pairing read back the pre-promotion `6095346` + legacy artifact and the promoted source + artifact, each with 237 verified rows and matching status semantics. No production traffic was switched during the drill.

### Derived Daily fallback closeout — 2026-09-13

- Issue [#22 — bounded derived-Daily fallback and lineage](https://github.com/nitipums/hermes-signalix/issues/22) adds an official-first, per-symbol/per-date fallback for the read-only Trend Map. `price_data` remains official; `derived_daily_price_data` is explicitly non-official Settrade 60m-derived evidence.
- The bounded writer fetches only affected current-session symbols with Settrade 60m, requires complete Bangkok 09:00–16:00 coverage (8 bars), valid OHLCV, a completed cutoff, and writes only the derived table idempotently. It does not mutate `price_data` or enable action paths.
- Prior publication baseline: publisher/API read-back was `237/237`, `232 AVAILABLE`, `5 INVALID_DATA`, `0 NO_DATA`; the final post-commit read-back is recorded in `Deployment.md`.
- Current source verification (Issue #22 commit `f99becb5d5d50a49331419bb8d878ae6b9f6d979`): exact focused fallback/adapter command `pytest -q backend/test_derived_daily_fallback.py backend/test_shadow_trend_map.py` — `52 passed` (11 fallback + 41 Trend Map tests); Python compile and `git diff --check` passed. Final runtime reload and public re-read are recorded below. Trend Map contract remains `PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`.

### Current acceptance reconciliation — 2026-09-13

- **Current focus gate:** Daily Trend Mapping production-served read-only closeout in GitHub Issue #17 is complete; broader setup/Elliott work remains separate.
- **Source/release:** `NOT VERIFIED` for this drawer slice's release promotion — local/remote release HEAD is `ebedae5d0d15cbbfbbd599ed18dcabad0a76a004`, while the drawer fix and related evidence remain uncommitted in the working tree; Issue #22 implementation remains committed/pushed at `f99becb5d5d50a49331419bb8d878ae6b9f6d979`.
- **Runtime/API:** `PASS` for the served `/api/trend-map` production-read-only contract and readiness; `/mvp` and `/api/setup-candidates` are dropped/paused and are not current acceptance targets.
- **Data freshness/coverage:** `PASS` for the published Trend Map artifact (`FRESH`, 237 declared/evaluated/returned with explicit quality states). Official Daily remains unavailable for `3BBIF`, `COM7`, and `PR9`; their Trend Map rows use explicitly non-official derived Daily evidence from complete Settrade 60m sessions.
- **Browser/UI:** `PASS` for Trend Map desktop, drawer/chart, 390px no-overflow, and failure→Retry→recovery; Hermes `browser_exec` helper syntax also verified.
- **Safety:** Wave remains machine-generated evidence for Arm review; the Trend Map is production-served public read-only Daily evidence (`status=PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`); alerts, broker execution, and auto-trading remain `OFF/PENDING`.

The setup-candidate and `/mvp` path is **DROPPED / PAUSED** by owner decision; it is not a current delivery target. Preserve it as audit/future-integration history and require an explicit owner resume decision before work restarts.

Browser verdicts are named per journey. They do not promote partial/stale data to full freshness PASS.

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
- Public Signalix and the separate Portfolio Copilot remain isolated.
- No live auto-trading. Paper/pilot execution comes before any real execution.
- The overview must be usable before detail/chart data load; unknown compact-card data must never cause all symbols to disappear.
- Drawer metadata and decision evidence are separate contracts: genuine missing/insufficient VCP evidence remains `NOT_VERIFIED`; optional canonical metadata shows `Loading…` while `/api/symbol/{symbol}` is pending and `Unavailable` when that request fails. Chart unavailability is reported separately.

## Historical runtime baseline — 2026-09-02

- The primary product spine is **Daily Trend/Strength + Elliott candidate → 60m Trade Setup → Arm review**.
- Intraday UI evidence distinguishes `60m fetched` (`fetch_completed_at`) from `latest completed 60m candle`; a fetch round at 16:45 may correctly expose a 16:00 candle.
- The canonical API is `/api/setup-candidates`; it preserves all 237 `marginable_long` rows and six fail-closed lanes: `REVIEW_NOW`, `SETUP_FORMING`, `DAILY_CANDIDATE`, `WAIT`, `AVOID`, `DATA_BLOCKED`.
- T1–T9 source and release promotion are complete. Live `:3001` serves the new DB-built contract with honest blocked/avoid states; public 390px failure→Retry→recovery journey is `PASS` with direct DOM/screenshot evidence. Broader desktop/drawer regression evidence and evaluator auto-caller remain separate.
- VCP, contraction, and breakout-volume are bonus/compatibility evidence. `/api/vcp-finder` and old VCP surfaces are audit/rollback only.
- 929 active ORD remains explicit audit/rollback coverage; `marginable_long` = 237 eligible symbols. Alerts, auto-trading, and broker execution remain off.
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

The deterministic chart contract is served by `GET /api/chart-db/{symbol}?timeframe=1D|1W|60M|1M` under policy `technical-indicators-v2`. It exposes OHLCV candles, MA5/10/20/50/100/200, MACD(12,26,9), Wilder RSI(14), Wilder ATR(14), and `indicators.latest.window_summary` for 5/10/20/50/100/200/260 candles. Each window contains Open, High, Low, Close, total/average volume, Change %, Range %, MA where applicable, availability, and provenance. Daily 260 candles is a separate 52-week trading range, not an MA. Missing or insufficient history is `NOT_VERIFIED`, never inferred.

The Team Facts surface is public unauthenticated read-only by owner decision. It must remain facts-only and separate from `/api/setup-candidates`; no setup, Wave, lane, trigger, risk, target, alert, order, or broker semantics may be exposed. Runtime evidence after release `28f7947`: Team Facts HTTP 200, `marginable_long`, 237 eligible / 695 excluded from 932 active ORD, views momentum 16 / near_high 13 / pullback 58, Daily freshness partial with explicit `3BBIF`, `COM7`, `PR9` missing and intraday fresh. Readiness was `status=ok`, `db=up`, `redis=up`.

## Current user-validation loop — 2026-09-01

The release is handed to Arm for manual use. Elliott Wave output remains machine-generated candidate/evidence, not unquestionable truth. Review/confirm Wave identification from the rendered chart first; do not tune semantics from assumptions. Any confirmed product issue becomes a new bounded `grill-with-docs → to-spec → to-tickets → implement` cycle.

- Lite preflight is `PASS` for the previously accepted rendered usability journey (desktop/mobile load, tabs/filters, candidate→drawer, chart, TradingView link, and no overflow). The 2026-09-12 owner UI feedback slice intentionally removes the drawer's Wave Evidence toggle/explanation and Evidence Details/provenance section, while retaining source-linked Daily chart markers and the primary Wave summary. The revised desktop/mobile drawer journey is `PASS` by owner confirmation; semantic Wave correctness remains `NOT VERIFIED` until Arm reviews and confirms the interpretation from the chart.

## Current UI decision note — 2026-09-12

- Owner feedback intentionally keeps chart status/timeframe/source diagnostic prose and the drawer's Wave Evidence/Evidence Details sections out of the visible `/mvp` review surface. Deterministic API fields, chart markers, and provenance remain available for audit and machine validation.

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
7. **Bounded concurrency:** Parallel work is allowed when scopes/worktrees do not overlap; serialize overlapping writers and shared runtime side effects.
8. **Stagger + crash-cluster pause:** Keep dispatch bounded and pause on crash clusters. Lite chooses whether workers are appropriate for the task.

## Evidence standard for every pull

Before a row above can be marked complete in this document, record:

1. exact files changed;
2. focused RED → GREEN test evidence and relevant regression results;
3. source/freshness/provenance impact;
4. deployment status (including explicitly **not deployed** when applicable);
5. browser/mobile verification when UI changes;
6. Bee final-gate verdict.
7. For any `daily_shortlist.py` change, also record `curl :8000` live probe vs source diff (stale-runtime check) and resource-gate result.

## Historical deployment evidence — 2026-09-12 (superseded by 2026-09-13 closeout)

- Previously deployed shadow/UI slices remain historical evidence only: the shared-drawer OHLCV containment and DOM-mapping changes were deployed and browser-verified on 2026-09-12, with no `/mvp` semantic, API, database, ingestion, alert, or broker change. They do not prove the current backend hardening source is served.
- Owner decision (2026-09-12): the Daily Trend Map is permanently production-served public read-only. `GET /trend-map` and same-origin `GET /api/trend-map` require no authentication. Its canonical envelope is `status=PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`; it has no setup, recommendation, alert, order, broker, BUY, or other action semantics, and this decision does not change `/mvp`'s separate owner-only/private signal policy.
- Historical hardening source and deployment read-back (2026-09-12; superseded by the production closeout above): bounded publisher, artifact/failure-sidecar validation, EOD hook, and fail-closed SQL guard were deployed. Public shadow API returned HTTP 200 with 237 rows, `229 AVAILABLE / 5 INVALID_DATA / 3 NO_DATA`, `FRESH`, and the historical artifact identity is preserved below for audit only. It is not the current pointer.
- Read-only shadow review surface: the route does not change `/mvp`, setup candidates, classifier semantics, schema, alerts, broker paths, or BUY/action paths.
- The surface uses a backend-local SELECT-only adapter (with the research replay adapter retained for host compatibility), current `price_data` Daily as-of, and the canonical `marginable_long` universe. Every declared symbol remains visible; row `status` is `AVAILABLE` only for valid classifier output and `DATA_BLOCKED` otherwise, while `data_quality_status` preserves `NO_DATA`, `INVALID_DATA`, `INSUFFICIENT_HISTORY`, `AVAILABLE`, or `DATA_BLOCKED` reason visibility.
- Publication (not the HTTP request) resolves the current as-of and uses one read-only `SELECT`/`WITH` batch query for all symbols (`symbol=ANY(%s)`, `market='TH'`, `date <= as_of`, ordered by symbol/date). The publisher validates the complete `marginable_long` universe, declared/evaluated/returned/blocked counts, policy, quote envelope/source/basis, and provenance before writing an immutable versioned JSON artifact and atomically replacing `backend/shadow-read-model/current.json`. Version identities include the quote representation revision, policy hash, Daily as-of, universe hash, content hash, and measurement hash; each HTTP read recomputes the latter two from persisted artifact content/measurement metadata, and cannot accept a mismatch. The revision prevents a quote-column representation change from colliding with an older artifact.
- Classification uses at most the most recent 400 valid Daily bars, fails closed below 30 valid bars, and derives `prior_10d_low` from the prior ten selected Daily bars excluding the current bar. Policy, as-of, adapter, table, timeframe, and query provenance are returned.
- Publisher retrieval is bounded at `retrieval_cap=430` rows per symbol using deterministic newest-first partitioning. The read-only batch SELECT also returns per-symbol `invalid_count` metadata from the filtered Daily source (`date <= as_of`) using the exact `_valid` missing/nonfinite/OHLC-geometry rules; it transfers no unbounded history and makes no full-history claim. Every cap hit records `cap_reached=true`, `cap=430`, `quality_scan`, `quality_established`, `invalid_count`, and `full_history_claim=false`. A cap-hit row may be `AVAILABLE` only when quality is established and `invalid_count=0`; selected or aggregate invalid rows remain visible as `INVALID_DATA`, and unavailable quality fails closed as `DATA_BLOCKED`. Rows not hitting the cap retain the max-400/min-30/prior-10 rules. The immutable artifact persists numeric `db_read_ms`, `classify_ms`, `serialize_write_ms`, and `total_ms` under `timing` with `measurement_scope=pre_immutable_write`; these are publisher preparation measurements, while HTTP `read_path.latency_ms` measures pointer/artifact validation. The version identity includes content and measurement fingerprints, so changed measurement metadata receives a new immutable version rather than colliding with an existing file.
- The default API path reads and validates only `current.json` plus its referenced immutable artifact; it never classifies symbols or queries `price_data`. Missing, corrupt, mismatched, or unavailable pointer/artifact state returns visible `DATA_BLOCKED`/`NOT_VERIFIED` with zero rows and no request-time fallback. The envelope preserves cache metadata and exposes artifact id/path, publication time, as-of, policy hash, source, and read-only provenance. `build_shadow_report(..., source="publisher")` is reserved for the bounded publisher/tests path.
- Every HTTP read validates the current pointer and immutable artifact; no process-local cache is authoritative. The response exposes read-path latency and pointer/artifact validation metadata plus deterministic freshness (`published_at`, `age_seconds`, configurable `SIGNALIX_SHADOW_STALE_AFTER_SECONDS`). Missing, corrupt, unknown, or stale artifacts are `DATA_BLOCKED`/`NOT_VERIFIED` with zero rows; the prior immutable artifact is not changed.
- The review dashboard is a permanent public read-only shadow surface with a lane-grouped table and click-to-open the shared `/mvp` drawer implementation from `frontend/shared-drawer.js` (no duplicate drawer/chart renderer), native Search, exact machine-lane filter, broad-state filter, and Reload. No authentication is required. Status and data-quality values remain drawer evidence but are not visible table columns or controls. Lane headings show the exact machine lane and visible-row count. At 390px the table is contained in a bounded horizontal-scroll wrapper so the page itself does not overflow. The shared drawer loads the existing same-origin `GET /api/chart-db/{symbol}?timeframe=1D` read-only chart contract and reports loading, error, empty, source/timeframe/as-of/latest-time, and provenance states alongside the shadow evidence. This remains separate from `/mvp`'s owner-only/private signal policy and carries no action/order semantics.
- The shadow table quote columns are source projections: `Price`, `Change`, and `% Change` come from each row's persisted canonical `quote` envelope. `price` is the latest completed Daily close; `change_amount` and `change_pct` compare it with the previous completed Daily close and carry `change_basis=previous_daily_close` (or explicit `NOT_VERIFIED`/null fields when unavailable). Quote provenance remains `price_data` / `1D` / non-provisional. The browser only renders these artifact values and passes the complete row to the shared drawer; it does not calculate financial values.
- The existing successful EOD updater calls the bounded publisher only after the Daily update path succeeds and only when `--scan` is enabled; intraday-only runs do not publish. Publication errors leave the previous pointer untouched. The hardening hook is deployed and covered by source tests; next scheduled EOD freshness evidence remains ongoing, and no post-commit EOD run is claimed here.
- EOD publication failures emit a structured `SHADOW_TREND_MAP_PUBLISH_FAILURE` event containing error type/message, failure count, and pointer-preserved status. The ingestion/update path remains successful unless its pre-existing contract fails; the shadow failure is observable and non-fatal.
- Historical status superseded by the 2026-09-13 production-served read-only closeout above: source implementation, focused tests, deployed/public artifact read-back, `/mvp` preservation, and named browser journeys were verified; the Trend Map is non-actionable and no production decision/action path changed.
- Historical closeout release references remain preserved for audit only. The current release and artifact identity are recorded in the fresh promotion evidence above.
- Worktree note: generated `backend/shadow-read-model/` artifacts are intentionally tracked runtime inputs in commit `f18e48f`, not untracked research artifacts. Untracked `research/`, `docs/current/`, and `docs/agents/` QA/session notes remain preserved owner/research artifacts outside that commit and must not be cleaned, reset, or treated as deployment evidence. The unused `map_daily_trend` compatibility alias remains preserved because removing it would require editing outside this bounded file scope; no caller or test currently uses it.
