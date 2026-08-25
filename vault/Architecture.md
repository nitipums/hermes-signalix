# Architecture

> **STATUS: CURRENT** · `CANONICAL_FOR: current system architecture and runtime data flow`. Verify implementation/runtime when dates conflict.

## Data flow
```
            ┌─────────────────── EOD INGESTION ───────────────────┐
   Thai EOD │  update_data.py  (local zip → drive → Settrade → yf) │
   zip /    │  incremental, idempotent (ON CONFLICT DO NOTHING)    │
   Drive /  │  yfinance: NO 15% price-gap skip (2026-08-20)        │
   Settrade └───────────────┬──────────────────────────────────────┘
                    ▼
                    PostgreSQL  price_data / intraday_price_data / company_profiles
                        │  (SET index = benchmark for RS)
                        ▼
   ┌───────────────── SCREENING (deterministic) ─────────────────┐
   │  screening.py  scan_universe() → group_scan_results()        │
   │  Trend Template 8/8 · VCP · RS Rating · Buy Zone · Stop      │
   └───────────────┬───────────────────────────┬──────────────────┘
                   │ publish (screen envelope)  │ write scan_results.json
                   ▼                            ▼
              Redis channel              build_dashboard.py
                 'signals'                    │
                   │ subscribe                ▼
   ┌─────────── DELIVERY (signalix_delivery) ─┐   dashboard_server.py
   │  delivery_consumer.py → push_telegram()  │   (static, :3001)
   │  (app.py /scan also pushes batch summary)│
   └───────────────────┬──────────────────────┘
                        ▼
                  Telegram chat (7295704669)
```

## Containers (docker-compose)
| Service | Image | Port | Role |
|---------|-------|------|------|
| `signalix_postgres` | postgres:16-alpine | 5432 | price archive |
| `signalix_redis` | redis:7-alpine | 6379 | pub/sub bus |
| `signalix_backend` | builds `./backend` | 8000 | FastAPI API |
| `signalix_dashboard` | builds `./backend` | 3001 | MVP-only dashboard server (`mvp_server.py`), same bind-mounted `./backend`; legacy routes return 404 |
| `signalix_delivery` | builds `./backend` | — | Redis consumer → Telegram |

Backend and delivery share the **same image** (redis + requests preinstalled).
Delivery runs `python -u delivery_consumer.py` (the `-u` avoids block-buffered
logs in the non-TTY container).

## Webhook contract
`POST /webhook` (backend, :8000)
- Requires header `X-Webhook-Secret: <WEBHOOK_SECRET>` (or `?secret=`) → 401 else.
- Body: `{"symbol","source","price", ...}` → stored (dedup by hash) + published.

## Key files
- `backend/app.py` — FastAPI routes (`/webhook`, `/scan`, `/screen/{sym}`, `/chart/{sym}`, `/health`)
- `backend/delivery.py` — `push_telegram()` + envelope formatting (shared by batch + consumer)
- `backend/delivery_consumer.py` — Redis subscriber entrypoint
- `backend/screening.py` — DB-backed Minervini engine
- `backend/update_data.py` — Daily ingestion plus full active-ORD intraday 60m ingestion; `intraday_feed_status` tracks per-symbol Settrade 60m availability without changing Daily eligibility
- `backend/intraday_evaluator.py` / `run_intraday_evaluation.py` — 60m action overlay and transition persistence
- Intraday E2E contract: fetch → `intraday_price_data` upsert (active feed only) → evaluator → `build_dashboard.build()` from existing Daily scan → `dashboard_snapshot.json`/`dashboard.html` → served `:3001`
- `backend/refresh_company_profiles.py` — non-price cached company context; restrict future refreshes to active ORD universe
- `backend/build_dashboard.py` — legacy dashboard artifact builder; not the MVP entrypoint
- `backend/mvp_server.py` / `mvp_routes.py` — owner-only MVP static server and fail-closed `/api/*` dispatcher
- `backend/mvp_snapshot.py` — canonical `signalix.mvp.v1` artifact loader/sanitizer
- `backend/mvp_api.py` — Daily Shortlist, watch-only mover/caution lanes, Explorer projection
- `backend/mvp_chart_db.py` — SELECT-only `1D`/`1W`/`60M`/`1M` OHLCV + indicators
- `backend/app.py` — FastAPI routes, chart aggregation (`60m`, `1D`, `1W`, `1M`)
- `docker-compose.yml` — 4 services

## Current MVP surface contract — 2026-08-25

The served owner-only MVP is intentionally separate from the legacy dashboard:

```text
/mvp
  ├─ Daily Shortlist       READY / PRE_READY only
  ├─ Rising Movers         WATCH ONLY; never actionable
  ├─ Caution               DO NOT CHASE; never actionable
  └─ All Stocks Explorer   full-ORD research, immediate Stage/Search filters
```

Daily Shortlist hard gates are unchanged. `Rising Movers` uses explicit Daily
price/volume evidence for S1/S2 context; `Caution` exposes strong moves in
S3/S4/topping/extended structures. Neither lane receives shortlist rank,
trigger permission, or READY styling.

Chart contract is `GET /api/chart-db/{symbol}?timeframe=1D|1W|60M|1M`:
`1D` reads Daily bars, `1W`/`1M` aggregate Daily bars, and `60M` reads stored
intraday 60m bars. Chart controls and indicator legends are below the plot so
they cannot obscure candles, volume, MA, or RSI panes.

Freshness display keeps ownership explicit: `Daily EOD` timestamp is the
official decision provenance, while `60m updated` comes from the latest
completed `intraday_ingestion_runs.fetch_completed_at`. Intraday refresh must
never overwrite the Daily decision timestamp.

See [[Components]] for detail, [[Deployment]] for ops.

## Current intraday E2E reliability contract (2026-08-21)

The active 60m path is:

```text
Settrade full active ORD fetch (excluding feed-status cooldown symbols)
→ intraday_price_data upsert
→ intraday_feed_status update (retry/unavailable/available)
→ intraday evaluator
→ dashboard rebuild from existing Daily scan
→ dashboard_snapshot.json + dashboard.html
→ separate dashboard server :3001
```

Per-symbol intraday feed failure must not remove a symbol from Daily/EOD. When a
60m feed is unavailable, the dashboard explicitly shows `60m unavailable · Daily
EOD` and uses Daily EOD as the decision source. `COLOR` is the separate
instrument-master exception: it remains excluded until official Settrade master
sync reactivates it.

It deliberately does not run a Daily scan. Daily membership/classification remains EOD-owned. A run may be `partial_success` when Settrade returns empty data for a bounded symbol tail; that is tolerated by the watchdog when data/evaluator freshness is healthy. Dashboard freshness must be proven at the served browser surface, not only by DB or HTTP 200.

The next product direction is documented in [[Product-Strategy-Market-to-Action]]. Signalix is evolving toward a shared **Market View to Action Engine** with separate DR Follow, TFEX Trigger, Fund Plan, Stock Alert, and private Investment Copilot experiences. The strategy includes sourced fundamental context, immutable recommendation/outcome logging, and an isolated paper/pilot portfolio before live execution.
