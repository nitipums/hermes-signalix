# Components

> **STATUS: CURRENT** · `CANONICAL_FOR: current component responsibilities and hard rules`.
> **Reconciled:** 2026-09-19 · Daily Trend Mapping and Market Breadth are the active public read-only surfaces. `/mvp` and setup components are `HISTORICAL / SUPERSEDED / DROPPED`; the former shadow naming is retired for active modules.

Every current backend component, its responsibility, and its hard rules. Legacy
components below are retained only as explicitly labelled audit/history.

## Current active-only boundary — 2026-09-20

The [active-only contract freeze](../docs/current/2026-09-20-active-only-contract-freeze.md)
owns the component boundary; the [pointer/artifact inventory](../docs/current/2026-09-20-pointer-artifact-inventory.md)
records evidence without merging verdicts.

## Daily Trend Mapping — current delivery surface

The Trend Mapping surface is the current delivery target. Its publisher builds
an immutable, versioned Daily read model; the Trend Map API reads and validates
only the current pointer/artifact; the dashboard renders the public read-only
research table and reuses the shared chart drawer. It preserves Daily
as-of, Daily-first quote provenance, data-quality states, and fail-closed
behavior. It has no setup, BUY, alert, order, broker, or auto-trading meaning.

Current route pair:

```text
GET /api/trend-map
GET /trend-map
```

### Read-model rule

Public Trend Map request paths consume validated compact artifacts rather than
querying raw market history. The drawer chart prebuild contract covers `1D`,
`60M`, `1W`, and `1M`: EOD publication owns `1D/1W/1M`, intraday commit owns
`60M`, and the request path selects a symbol/timeframe entry. Only the current
pointer and validated artifact are used for the normal path; explicit,
provenance-labelled DB fallback is permitted only when the artifact is
unavailable or stale. No request-time scan, rescan, indicator rebuild, or
PostgreSQL history query is permitted for a valid artifact.

## Market Breadth — current delivery surface

Market Breadth is the active aggregate companion surface at
`/market-breadth` and `/api/market-breadth`. Its deterministic publisher and
validated current pointer provide read-only breadth evidence. It has no setup,
signal, alert, order, broker, or auto-trading meaning.

## HISTORICAL / SUPERSEDED / DROPPED — private paper/shadow signal components

Pure deterministic projection over canonical setup-candidate evidence. Its
Phase 1 market-only seam emits `BUY_NOW`, `BUY_ON_TRIGGER`, `WAIT`, `AVOID`, or
`DATA_BLOCKED` without portfolio input. Evidence score is explicitly not a
calibrated probability. The module never writes, publishes, sizes, alerts, or
submits an order. Position-aware states remain isolated for later work.

`shadow_signal_replay.py` rebuilds canonical candidates at each completed
session boundary in the trailing seven calendar days, projects `BUY_NOW`, and
deduplicates repeated observations of the same unchanged setup plan while
preserving first/latest timestamps. `mvp_routes.py` exposes it through the
token-free `GET /api/shadow-buy-signals?days=7`; `/mvp` renders the
shadow result without changing the canonical setup API.

## `update_data.py` — shared EOD ingestion dependency
Incremental, idempotent SET EOD updater. Fetches only trade days **strictly
after** `MAX(date)` and inserts with `ON CONFLICT DO NOTHING` → safe to re-run.

**Source priority** (`--source` to force):
1. `local` — CSV drop dirs (`/root/signalix/uploads`, seed dir). Owner pushes via `upload_server.py`. Most reliable.
2. `drive` — re-list Google Drive archive folder via `gdown`, pull newer files.
3. `settrade` — Settrade Open API v2 (`settrade-v2`), preferred automated source.
4. `yfinance` — fallback only; no 15% price-gap skip is applied, per owner directive.

> Per Nitipum.s rule: native Thai EOD zip is AUTHORITATIVE; Settrade preferred
> automated; Drive = owner backup; yfinance = last resort only.

Triggers the historical compatibility scan/dashboard rebuild after loading (when
not `--dry-run`); this is not current Trend Map or Market Breadth routing.

## `screening.py` — DB-backed Minervini engine (Phase 2)
Reads `price_data` from Postgres (NOT yfinance). Benchmark for RS Rating = the
`SET` index symbol in the same table. Core API:
- `analyze_symbol_db_ranked(symbol)` — single-symbol pipeline
- `scan_universe(min_conditions, limit)` — full market
- `group_scan_results(scanned)` — bins into entry_now / ath_breakout / breakout_extended / monitor / risk

Computes: Trend Template 8/8, VCP contractions, RS Rating, Buy Zone (Fib 0.5/0.618), Stop, Trade Readiness. **Deterministic — no LLM.**

## `instruments.py` — instrument authority
Returns bounded active-ORD identity/taxonomy records from `symbol_master` and
profile provenance with SET factsheet priority, Yahoo fallback, and honest
unknown/absent states. Public API: `GET /instruments?limit=` and
`GET /instruments/{symbol}`.

## `fetch_fundamentals_subagent.py` — SET factsheet refresh
Bounded, resumable active-ORD factsheet scraper. It persists JSONL progress and
upserts only factsheet fields that are missing, preserving stronger existing
profile evidence. The `signalix-factsheet-refresh.timer` runs 20 symbols per
weekday cycle; the scraper is not a signal/price source.

## `scanner.py` — legacy/standalone scanner
Original pandas scanner (pre-DB rewrite). Kept for reference; `screening.py` is
the live engine. Imports `scan_universe` must stay at module top in `app.py`.

## HISTORICAL / SUPERSEDED — `build_dashboard.py` compatibility snapshot builder
Builds compatibility snapshots/manifest data for the pipeline. The former
public `dashboard.html` artifact and route are retired; the owner-facing UI is
served from `/mvp` and charts are fetched through the MVP API.

Intraday-only runs refresh the MVP snapshot from the existing Daily scan after 60m
upsert/evaluation; they do not rerun Daily classification. The active feed is
filtered by `intraday_feed_status`: after three consecutive Settrade empty/fail
responses a symbol is `unavailable` for a 24-hour cooldown. This filter is
intraday-only; Daily/EOD membership and historical data remain intact. Cards
Cards show `60m unavailable · Daily EOD` and keep `decision_source=Daily EOD`
rather than relabelling an old Daily value as 60m.

## HISTORICAL / SUPERSEDED / DROPPED — retained MVP owner-only trial surface
`mvp_server.py` serves the retained trial `/mvp` from the bind-mounted release tree. `mvp_routes.py`
owns the fail-closed `/api/*` boundary and never falls back to legacy snapshots.
`mvp_api.py` retains the builder and compatibility projections. `canonical_setup_projection.py` owns the deep read-only canonical projection interface: exact-envelope validation, deterministic ordering, presentation filters, pagination, six-lane counts, freshness/provenance metadata, and diagnostics. `mvp_api.py` re-exports the canonical function for compatibility with existing callers. T1–T9 source contracts and release promotion are complete; public 390px failure→Retry→recovery browser acceptance is verified, with evaluator auto-caller separate. Legacy VCP/Stage labels are compatibility/audit only.
Explorer Stage/Search filters reload immediately; there is no Apply step.

`canonical_freshness_lineage.py` owns the read-only intraday sidecar merge and timestamp comparison. The route retains a thin compatibility wrapper so existing tests/callers remain stable; it does not acquire/query PostgreSQL. Daily/read-model identity remains unchanged while intraday run metadata is overlaid only when the sidecar is valid and newer.
`canonical_chart_read.py` owns the shared SELECT-only chart row retrieval and
aggregation rules. `chart_rows.py` is a compatibility adapter for that seam;
`mvp_chart_db.py` and `app.py` retain their existing public imports. The chart
layer serves real timeframe contracts: `1D` Daily with a current-session
provisional 60m replacement when available, `1W`/`1M` aggregate those Day bars,
and `60M` stored intraday bars. The frontend renders candlestick OHLC, volume,
MA, and RSI; timeframe/layer controls and indicator values sit below the chart
plot. `as_of` is the chart period key; `latest_time` identifies the actual
latest stored candle. Runtime promotion and public Day/Week verification
completed 2026-09-02; request-time metadata caching and explicit audit-run
universe identity remain bounded follow-up work.

The `/mvp` drawer plots deterministic, source-linked Daily Wave markers only
on `1D`, using the API's exact timestamp and price. It never derives missing
positions, never projects Daily Wave markers onto `60m`, and keeps 60m setup
levels separate. These non-LLM evidence annotations support chart review; they
are not trade instructions.

The same canonical Wave producer exposes `wave.deep_pullback_evidence` as a
source-generated, non-actionable Daily shadow envelope for rejected raw W3
candidates in the `0.60 < retracement <= 0.786` band. Cards and the drawer may
display its exact API ratio and anchors separately from Primary Daily Wave;
the frontend does not derive them. It cannot change publication, decision
lanes, setup/risk math, or chart markers.

### `/mvp` visible diagnostics — current UI decision, 2026-09-12

Owner feedback intentionally removes chart status/timeframe/source diagnostic
prose and the drawer's Wave Evidence/Evidence Details sections from the visible
review surface. Deterministic API fields, source-linked chart markers, and
provenance remain available for audit; this does not remove the underlying
contract or data.

## HISTORICAL / SUPERSEDED — `mvp_server.py` MVP static server
Serves `/mvp` on :3001 from the bind-mounted `/root/signalix/backend/frontend`
directory. The former `/dashboard.html` route returns 404. Runtime container is
`signalix_dashboard`; it is separate from the FastAPI `signalix_backend` service.
Verify served source and API freshness against the
latest `intraday_ingestion_runs.fetch_completed_at`, not only HTTP 200.

## HISTORICAL / COMPATIBILITY — legacy FastAPI, delivery, and portal components

The route/component inventory below is retained for audit and compatibility.
Current public routing is owned by the Trend Map and Market Breadth surfaces
above; these legacy `/scan`, `/screen`, signal-delivery, portal, and MVP paths
are not current product routing.

## `app.py` — legacy FastAPI backend
Routes:
- `GET /health` — db+redis ping
- `POST /webhook` — store + publish (auth-gated, see [[Architecture]])
- `GET /signals` — list stored signals
- `GET /screen/{symbol}` — run pipeline for one symbol, publish
- `GET /chart/{symbol}?timeframe=` — backend bounded OHLCV (`1W/1D/60M/1M`); MVP uses the separate `/api/chart-db/{symbol}` contract, and 15m is retired
- `POST /scan` — scan universe, publish candidates, rebuild dashboard, push summary

Imports `push_telegram` + `DASHBOARD_PUBLIC_URL` from `delivery.py`.

## `delivery.py` — push + formatting (shared)
`push_telegram(text)`, `format_signal(envelope)` (Thai alert), `deliver(envelope)`,
`run_consumer()`. Used by BOTH `app.py` (batch summary) and `delivery_consumer.py`
(realtime). **Telegram-only** as of 2026-08-12 (LINE removed). Plain-text sends
(Markdown parse caused Telegram 400).

## `llm.py` — Phase 3 LLM summarization
`summarize_signal(result)` calls the Nous portal (`inference-api.nousresearch.com/v1`,
model `upstage/solar-pro4:free`) and returns a short Thai note. Reads the Nous
OAuth token at runtime from `/root/.hermes/shared/nous_auth.json` (mounted RO into
the container); never copied to Signalix `.env`. Safe no-op (returns '') if the LLM
is unavailable. The LLM NEVER computes numbers — only summarizes.

## HISTORICAL / SUPERSEDED — `portal.html` User self-service frontend
Dark-theme, Thai, mobile-first single-page app. Lets a user register by Telegram
chat id, view/edit their watchlist, see live quota bars (watchlist size + alerts
today vs tier cap), and view the tier table. Served at `:3001/portal` by
`dashboard_server.py` (do_GET rewrites /portal -> /portal.html). Calls backend
API on `:8000` (`/me`, `/watch`, `/tiers`). Pure static HTML+JS, no build step.
No payment flow (payment deferred by user).
DB helpers for subscribers: `init_user_schema()`, `upsert_user(chat_id, tier)`,
`set_watch(chat_id, symbols)` (empty list = watch ALL), `get_routing_map()` →
`({symbol:[chat_id]}, [watch_all_chats])`. Routing is cached 30s in the consumer.
**Quota:** `TIER_LIMITS={free:5, paid:None, owner:None}` — explicit watchlists over
the free cap are rejected (HTTP 400) at `/watch`; watch-ALL always allowed.
`_ensure_user()` (no tier reset) is used by set_watch so editing a watchlist never
downgrades a paid user.

## `delivery_consumer.py` — Redis subscriber
Entrypoint for the `signalix_delivery` container. Subscribes `signals`, calls
`deliver()` forever. Blocks; systemd-like restart via compose `restart: always`.

## Retired ingest guard

`classify_check.py` was removed during the 2026-09-19 repository cleanup. Its
old dry-run ticker filtering rule is historical evidence only; no current
Trend Mapping runtime path invokes it.

## `set_market_day_guard.py` — holiday guard
Exits non-zero on SET market holidays so systemd `ExecCondition` skips jobs.

## `ingest.py` / `ingest_demo.py` — seed loaders
Parse `set-history_EOD_*.csv` into `price_data`. `ingest_demo.py` is the first
stage of the demo pipeline.

## `upload_server.py` — owner CSV drop
HTTP receiver so the owner can push EOD CSV files into the drop dirs.

## `market_breadth_artifact.py` — immutable MB-2 read path

Owns the separate Market Breadth artifact schema, content hash, immutable
version publication, pointer validation, range projection, and
`GET /api/market-breadth` dispatcher seam. Publication prebuilds explicit
`current`, `history_20`, `history_60`, `history_260`, and bounded `history_all`
fields. The public v2 representation contains aggregate `new_high_low` values
plus quality/reason fields; MB-1 builder details remain available in the
retained source/audit artifact. The read path selects one validated prebuilt
field and caches only a pointer/content-addressed artifact, invalidating it
when the pointer or file identity changes. Its publisher accepts an injected
MB-1 build or read-only source/build; this artifact module owns the schema,
hash, pointer, and validated read path, not an injected MB-1 source itself. It never uses
`marginable_long`, Trend Map, a database rebuild, ingestion, or a request-time
scan. Missing, corrupt, mismatched, stale, empty, undersized, or invalid
artifacts fail closed with a visible `DATA_BLOCKED` response; invalid ranges
return an explicit client error. Section 02 publishes content-addressed
`directions` for `history_20`, `history_60`, `history_260`, and `history_all`;
the API returns the selected direction while `current` remains the latest
single session. Direction is deterministic A/D-line evidence only: it uses
the first and last valid `ad_line`, valid `net_advances` steps, and explicit
AVAILABLE/PARTIAL/DATA_BLOCKED quality without thresholds, ratios, or trade
meaning. Artifacts without the direction envelope fail closed. Source and
fixture-backed contract tests are complete. Wave 1 served/runtime and browser
verification is complete; the production artifact read-back is `929` declared
active ORD, `841` observed, `88` blocked, `quality=PARTIAL`, and
`freshness=AVAILABLE`. PARTIAL preserves the declared denominator while
excluding invalid price rows from category counts.

## `market_breadth_publisher.py` — bounded MB-4A replay publisher

Owns the injected read-only source seam and production SELECT-only Postgres
adapter for active-ORD Market Breadth replay. It preserves universe/session
snapshot identity, 520-session pre-roll versus 260-session publication,
official-first lineage, Main Trend v6 observation evidence, and SET benchmark
quality before delegating to `market_breadth_artifact.py`. Observation
projection retains only OHLCV/source lineage, compact Main Trend decision
metadata, and MA50/MA200 participation; full technical series are symbol-local
scratch data released before the next symbol. The CLI requires an explicit
`--read-only` acknowledgement and accepts bounded `since`, `until`, and `as_of`
controls. It has no request-time rebuild or scheduler/deployment side effect;
live source/runtime verification is complete for the Wave 1 read-back. Artifact universe
metadata keeps the compatibility `observed_count` historical union separate
from point-in-time `current_observed_count`, `current_blocked_count`, and
`current_declared_count`; the public coverage header uses the current fields.

## `market_breadth_template.html` — aggregate MB-3 review page

Serves the separate `/market-breadth` aggregate evidence page. It reads only
`/api/market-breadth`, renders current metrics plus 20/60/260/all history,
preserves null/reason/quality states, and keeps the page explicitly
read-only/non-actionable. The hero metadata separates point-in-time `Quality`
from data `Freshness`; it has no symbol drawer, setup lane, alert, order,
broker, or auto-trading control. Isolated desktop/390px success, range-switch,
and empty-artifact Retry checks, and the Wave 1 public deployment are verified.

The first beginner-facing slice renders `Daily Market Participation` as an
aggregate active-ORD advancing/declining/unchanged bar with visible partial
coverage, plus a separate SET Index context strip. The SET benchmark is
display-only context and does not create a second breadth universe; SET50 is
not part of this feature slice.

MB-UI-2 extends the beginner-first presentation for cumulative participation,
Main Trend distribution, MA50/MA200 participation, new highs/lows, and
up/down volume. These are display-only explanations over deterministic API
values; they do not alter breadth calculations, create action states, or add
SET50 semantics. Live browser/runtime promotion is verified for Wave 1; the
feature remains read-only and non-actionable.

MB-UI-4 applies the approved High-Fashion Monochrome visual direction:
black/white editorial typography, one lime accent, hairline rules, oversized
masthead, and full-width visual figures. It removes the legacy dark dashboard
palette/card-grid treatment while preserving compact SET context, aggregate
active-ORD evidence, deterministic API/data semantics, and non-actionable
boundaries.

MB-UI-5 adds the shared semantic trend palette: acid lime for Up/Main 2,
vermilion for Down/Main 4, amber for Pullback/Main 3, slate for Base/Main 1
and neutral, and cobalt for SET Index reference. The same tokens are reused
across participation, Main Trend, high/low, volume, and benchmark visuals.

MB-UI-6 moves system/data status and expandable details below the primary
readings while retaining local as-of/quality/coverage qualifiers. It merges
Daily Market Participation into one count/share visual and uses beginner-facing
neutral vocabulary for Main Trend composition, moving-average coverage, rolling
new highs/lows, and up/down volume shares. Section 02 direction/baseline remains
an API contract decision and is intentionally unchanged in this slice.
