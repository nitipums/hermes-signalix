# Signalix Handoff — 2026-08-13

> Curated end-of-session handoff for Bee, Ploy, and future implementers. It records what is deployed, what was verified, known limits, and the next safe work order. No secrets are stored here.

## Executive outcome

Signalix changed from a mixed 15m/60m dashboard into a **60m-first intraday action overlay** on top of the Daily EOD scanner.

```text
Daily EOD data → structural screening / TT / RS / RSI / VCP / reference levels
Stored 60m data → current-price action overlay + current provisional chart candles
Dashboard → static first paint + dynamic /dashboard/snapshot polling
```

The system must not claim live streaming. It displays the latest stored 60m data with explicit source/freshness provenance.

## User decisions that are now product contracts

1. **No 15m active architecture.** Active fetch/evaluation/chart UI/history-fill modes are 60m-only. Existing historic 15m DB rows are legacy data, not a current product path.
2. **60m current/open candle must be included and refreshed.** Intraday upsert updates `open/high/low/close/volume` on conflict, rather than preserving first-seen values.
3. **Intraday cadence is every 10 minutes within SET continuous sessions.** Service has a Bangkok session guard: `10:15–12:30` and `14:45–16:30`, Mon–Fri, with a holiday `ExecCondition`.
4. **Daily EOD owns structure; intraday owns action overlay only.** Do not recompute Minervini structure from 60m candles or merge incomplete intraday values into Daily indicators.
5. **Chart semantics follow TradingView’s current-candle concept.** Daily, Weekly, and Monthly use stored data and show a provisional current candle until the relevant period closes. They do not make a fresh upstream fetch.
6. **Default dashboard market-quality rule:** hide names whose 20-Daily-session average traded value is below **THB 10M/day**. The user may opt into viewing all values.
7. **Volume surge must compare same-time cumulative volume**, not simply last-bar volume. To badge a surge: liquid name (20D value >= THB 10M), current cumulative volume >= 5M shares, and >= 5x prior-session cumulative volume through the same Bangkok cutoff.
8. **English UI and ORD-first scope.** No horizontal-scroll dependent UI; mobile cards/detail are primary.

## Current implementation

### Data + scheduling

| Component | Responsibility | Current behavior |
|---|---|---|
| `backend/update_data.py` | ingestion / intraday storage | Active groups, 60m only; normal fetch uses short lookback `--intraday-limit 8`; `intraday_price_data` uses conflict update for open candle |
| `backend/intraday_evaluator.py` | action overlay | Reads latest stored 60m versus Daily reference levels; persists state transitions |
| `backend/run_intraday_evaluation.py` | evaluator CLI | Restricted to `--mode active|act_prepare|monitor`, `--interval 60m` |
| `/etc/systemd/system/signalix-intraday.service` | deterministic runner | Settrade 60m active shortlist fetch then evaluator; no Hermes/LLM call |
| `/etc/systemd/system/signalix-intraday.timer` | frequent wakeup | Enabled and active; service has exact-session guard |
| `backend/fill_intraday_history.py` | one-shot repair | 60m-only missing-history utility; must not be repurposed as normal timer work |

### Important timer verification status

At handoff the timer is enabled/active and has recently triggered. Systemd reported the next trigger as `2026-08-13 07:00 UTC` and last trigger `05:50 UTC`; newest stored 60m timestamp was `2026-08-13 12:00 Asia/Bangkok`.

**Verified in continuation:** `systemd-analyze calendar --iterations=24` expands this expression to 10-minute occurrences (`07:00, 07:10, ... 09:50 UTC`, then afternoon block), so the cadence is correct. The service still wakes at block boundaries outside the continuous session and skips those safely via the exact Bangkok session guard. Keep the parser check in deployment runbooks.

### Chart API

`GET /chart/{symbol}?timeframe=1M|1W|1D|60m&limit=N`

- `60m`: stored 60m bars; latest bar can be in progress.
- `1D`: Daily EOD bars plus a provisional current-day bar derived from today’s stored 60m bars.
- `1W`: aggregate Daily bars plus current provisional daily material into the current week.
- `1M`: aggregate Daily bars plus current provisional daily material into the current month.
- `15m`: intentionally rejected (HTTP 400).
- Returned bars include `volume` and `provisional`; responses include `label`, `latest_time`, and `provisional`.

### Dashboard API and UI

`GET /dashboard/snapshot` dynamically serializes cards from `scan_results.json`, DB snapshots, cached company metadata, and intraday overlay state. `GET /intraday/transitions` supplies state transition events.

The served dashboard is `http://91.98.72.120:3001/dashboard.html`.

Implemented UI:

- card basics: volume, trade value, cash + percent change
- top gainers (default liquid-only) and low-value toggle
- same-time cumulative `VOLUME SURGE` badge with materiality guards
- timeframes: `1M`, `1W`, `1D`, `60m`; no 15m button
- native canvas chart: candles plus a separate aligned volume pane; only Entry/Support/Risk/Resistance overlays to avoid the dense-Fibonacci failure mode shown in TradingView references
- detail header: ticker, cached company name, sector, industry, short business description, and sticky close/header behavior
- detail basic info placed before action/reference metrics: volume, trade value, change, 52W high/low, ATH high/low, MACD
- MA block: MA10/20/50/200 together, with deterministic bullish/bearish/mixed stacking interpretation
- `Why this?` is checklist/bullet-oriented: TT/RS floor, RSI/volume ratio, turnover/VCP, and unresolved conditions
- visible dynamic refresh status: `Live snapshot · updated HH:MM` on success; `Snapshot retrying · retry N` on failure

Dashboard refresh behavior is now 15 seconds on success. Requests use `cache: no-store`, 12-second abort timeout, and bounded retry backoff `5s → 10s → 20s → max 60s`.

## Company profile / taxonomy work

### What was discovered

The Settrade Open API v2 `get_quote_symbol()` quote contract provides price, volume, change, PE/PBV/yield/EPS and market state, but **does not provide** company name, sector, industry, or business description. Do not assume quote endpoint has taxonomy.

### Current fallback implementation

- New table: `company_profiles(symbol, company_name, sector, industry, business_summary, source, fetched_at)`.
- New utility: `backend/refresh_company_profiles.py`.
- Current source is Yahoo Finance metadata, kept as a **non-price cached context layer** only. It is not a source of signal, valuation decision, execution, or price truth.
- Dashboard treats profile fields as optional, shows `pending` if absent, and exposes source/fetched timestamp in snapshot data.
- Verified examples: SIS and TFG have name/sector/industry/description available.
- Business description is deliberately capped to 320 characters at UI serialization.

### Critical incomplete work / blocker

A naive full backfill selected **7,147 historical symbols** from `price_data`, including expired/legacy/non-ORD records, leading to many invalid Yahoo requests. It was stopped after 438 requests; `company_profiles` held 142 profiles at handoff.

**Implemented in continuation:** automatic no-argument refresh now selects only `price_data.instrument_type='ORD'` symbols missing profiles, never the historical DR/legacy universe. Failures are recorded in `company_profile_refresh_failures` with error text, attempt count, and exponential retry date. `--retry-failed` explicitly opts into due failures. The current cache remains partial: 142 profiles and 1,135 active-ORD symbols missing at this checkpoint. Do not restart a 7k-symbol yfinance run.

**Product foundation:** replace the Yahoo taxonomy fallback with an authoritative SET instrument master/taxonomy once a valid licensed/official source is identified. That master should own official Thai/English company names, sector, industry, listing/instrument status, and `ORD` eligibility. This is also the prerequisite for trustworthy group/industry analysis in [[Product-Strategy-Market-to-Action]].

## ATH / history truth

- 52-week high/low uses the latest 252 Daily sessions.
- ATH high/low now reads full `price_data` history, separate from the 252-day metrics.
- Example verified at handoff:
  ```text
  SIS: 52W 27.50 / 18.30; full stored-history ATH 48.75 / 2.00
  ```
- “ATH” currently means **all-time high/low in the local stored archive**, not a guarantee of exchange-all-time history. The DB coverage differs by instrument; UI or docs should eventually show history-start / coverage provenance.

## Verification performed

At final deployment:

- Backend was force-recreated (required after Python changes); PostgreSQL and Redis passed container health before backend start.
- `/health` returned `{"status":"ok","db":"up","redis":"up"}`.
- `/dashboard/snapshot` returned new company, liquidity, surge, ATH/52W, MA, MACD fields.
- `SIS` snapshot had verified cached profile data and different 52W vs ATH ranges.
- `/chart/SIS?timeframe=1D&limit=180`: 180 bars, all with nonzero volume, latest current-day provisional candle.
- `/chart/SIS?timeframe=60m&limit=30`: stored 60m data with volume.
- Served dashboard returned HTTP 200; extracted JavaScript passed `node --check`.
- Added `backend/test_signalix_contracts.py`; live contract test passed for health, 866-item snapshot, all four chart timeframes with volume/provisional fields, explicit 15m HTTP 400 rejection, and served UI markers.
- Unit tests passed: 6 tests covering action grouping, liquidity gating, and 60m snapshot freshness contract.
- Browser automation itself remained unreliable on this VPS due to Chrome temporary-directory startup failure. Served HTML/API/JS contracts were verified; a real mobile visual regression test remains desirable.

## Deployment / operations rules

- Project: `/root/signalix`; backend: `/root/signalix/backend`.
- PostgreSQL runs locally; no public Redis/Postgres exposure should be added.
- After Python or environment edits run:
  ```bash
  cd /root/signalix
  docker compose up -d --force-recreate backend
  ```
  Build first only if dependency requirements changed.
- Use systemd for deterministic market polling. Hermes cron is watchdog/reporting only, not the market-data runner.
- Keep credentials out of notes, logs, commits, and user-facing responses.
- There is no Git repository in the current Signalix working tree; audit changed files by explicit paths/backups until version control is established.

## Files changed in this session

- `backend/update_data.py`
- `backend/intraday_evaluator.py`
- `backend/run_intraday_evaluation.py`
- `backend/fill_intraday_history.py`
- `backend/app.py`
- `backend/build_dashboard.py`
- `backend/refresh_company_profiles.py` (new)
- `backend/signalix-intraday.service`
- `backend/signalix-intraday.timer`
- deployed `/etc/systemd/system/signalix-intraday.{service,timer}`

## Prioritized continuation pipeline

### P0 — data integrity and reliability

1. **Instrument master / company profile pipeline.** The refresh is now active-ORD-only with failure backoff; next add authoritative SET taxonomy, profile status/refresh metrics, and a low-frequency scheduled runner. Evaluate official SET taxonomy before treating Yahoo metadata as a durable source.
2. **Browser/mobile visual test path.** Fix the VPS Chromium temporary-directory failure or use a remote/browser test runner. Exercise detail happy path, chart error/404 path, filter toggle, and refresh-failure state.
3. **Add profile/history provenance.** Surface/retain `profile source + fetched_at`; define local-history coverage metadata so ATH is not overclaimed.
3. **Extend API and unit tests.** Existing live contract + unit tests cover core snapshot/chart/15m/action/freshness paths; add direct provisional aggregation, same-time volume calculation, MA interpretation, profile-absent fallback, and snapshot failure-state tests.

### P1 — screening product quality

1. Build official taxonomy-led **sector/industry breadth**, leadership, participation, dispersion, and rotation views; do not infer groups solely from Yahoo labels.
2. Make volume surge thresholds configurable/versioned, then backtest the signal against subsequent returns/volume outcomes. Current rule is a product heuristic, not a validated alpha claim.
3. Persist richer intraday snapshot/transition diagnostics and surface whether a quote is stale versus current-session data.
4. Decide whether to add chart MA overlays. Current detail displays MA values and alignment, while native chart stays uncluttered; any overlay needs clear colors/legend and mobile readability.

### P2 — Market View to Action foundation (Ploy product work can continue here)

Follow [[Product-Strategy-Market-to-Action]] without reopening product discovery:

1. Domain contracts: instrument master, underlying mapping, market view, recommendation, decision event, paper portfolio, outcome.
2. Persist immutable recommendation/decision/outcome events **before** building broad UI flows.
3. Alert Builder slice with clear evidence/provenance.
4. DR Follow remains proposal-only; validate mapping/conversion/FX/liquidity/premium before action.
5. Fundamental Snapshot: source-dated, separate from technical/risk logic.
6. Paper/pilot portfolio and outcome evaluation before any real execution. No LLM executable orders; no live auto-trading.

## Collaboration guide

- **Bee/lite:** final architecture, implementation quality gate, live verification, ops, and user-facing delivery.
- **Ploy:** product semantics, user flows, prioritization, copy and Market View to Action proposal curation. Use this note and [[Product-Strategy-Market-to-Action]] as current technical/product context.
- **Mali/Nida:** test mobile journey and failure/error states; record actionable feedback in [[Product-Feedback]].
- **Khim:** mechanical implementation only with a specific brief; no production-deploy claim without Bee verification.

## Next-session quick start

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/dashboard/snapshot > /tmp/snapshot.json
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3001/dashboard.html
systemctl status signalix-intraday.timer --no-pager
systemctl show signalix-intraday.timer -p NextElapseUSecRealtime -p LastTriggerUSec
```

Then read this note, [[Architecture]], [[Deployment]], [[Decisions]], [[Phases]], and [[Product-Strategy-Market-to-Action]] before editing.
