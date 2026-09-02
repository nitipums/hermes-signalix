# Components

> **STATUS: CURRENT** · `CANONICAL_FOR: current component responsibilities and hard rules`.
> **Reconciled:** 2026-09-02 · Elliott/Trend/Trade-Setup is primary; VCP modules are compatibility/audit; canonical chart-read seam extracted with public contract preserved.

Every backend module, what it does, and its hard rules.

## `update_data.py` — EOD ingestion
Incremental, idempotent SET EOD updater. Fetches only trade days **strictly
after** `MAX(date)` and inserts with `ON CONFLICT DO NOTHING` → safe to re-run.

**Source priority** (`--source` to force):
1. `local` — CSV drop dirs (`/root/signalix/uploads`, seed dir). Owner pushes via `upload_server.py`. Most reliable.
2. `drive` — re-list Google Drive archive folder via `gdown`, pull newer files.
3. `settrade` — Settrade Open API v2 (`settrade-v2`), preferred automated source.
4. `yfinance` — fallback only; no 15% price-gap skip is applied, per owner directive.

> Per Nitipum.s rule: native Thai EOD zip is AUTHORITATIVE; Settrade preferred
> automated; Drive = owner backup; yfinance = last resort only.

Triggers a scan + dashboard rebuild after loading (when not `--dry-run`).

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

## `build_dashboard.py` — compatibility snapshot builder
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

## MVP owner-only surface — current
`mvp_server.py` serves `/mvp` from the bind-mounted release tree. `mvp_routes.py`
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

## `mvp_server.py` — MVP static server (separate dashboard service)
Serves `/mvp` on :3001 from the bind-mounted `/root/signalix/backend/frontend`
directory. The former `/dashboard.html` route returns 404. Runtime container is
`signalix_dashboard`; it is separate from the FastAPI `signalix_backend` service.
Verify served source and API freshness against the
latest `intraday_ingestion_runs.fetch_completed_at`, not only HTTP 200.

## `app.py` — FastAPI backend
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

## `portal.html` — User self-service frontend
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

## `classify_check.py` — ingest guard
Dry-run keep/cut rule before re-ingesting: CUT if ticker ends with -O/-F/-M/-P
or starts with ! or $.

## `set_market_day_guard.py` — holiday guard
Exits non-zero on SET market holidays so systemd `ExecCondition` skips jobs.

## `ingest.py` / `ingest_demo.py` — seed loaders
Parse `set-history_EOD_*.csv` into `price_data`. `ingest_demo.py` is the first
stage of the demo pipeline.

## `upload_server.py` — owner CSV drop
HTTP receiver so the owner can push EOD CSV files into the drop dirs.
