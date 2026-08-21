# Architecture

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
| `signalix_dashboard` | builds `./backend` | 3001 | Separate static dashboard server, same bind-mounted `./backend` |
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
- `backend/update_data.py` — Daily ingestion plus full active-ORD intraday 60m ingestion
- `backend/intraday_evaluator.py` / `run_intraday_evaluation.py` — 60m action overlay and transition persistence
- Intraday E2E contract: fetch → `intraday_price_data` → evaluator → `build_dashboard.build()` from existing Daily scan → `dashboard_snapshot.json`/`dashboard.html` → served `:3001`
- `backend/refresh_company_profiles.py` — non-price cached company context; restrict future refreshes to active ORD universe
- `backend/build_dashboard.py` — dashboard HTML shell + dynamic snapshot presentation
- `backend/app.py` — FastAPI routes, chart aggregation (`60m`, `1D`, `1W`, `1M`)
- `docker-compose.yml` — 4 services

See [[Components]] for detail, [[Deployment]] for ops.

## Current intraday E2E reliability contract (2026-08-21)

The active 60m path is:

```text
Settrade full active ORD fetch
→ intraday_price_data upsert
→ intraday evaluator
→ dashboard rebuild from existing Daily scan
→ dashboard_snapshot.json + dashboard.html
→ separate dashboard server :3001
```

It deliberately does not run a Daily scan. Daily membership/classification remains EOD-owned. A run may be `partial_success` when Settrade returns empty data for a bounded symbol tail; that is tolerated by the watchdog when data/evaluator freshness is healthy. Dashboard freshness must be proven at the served browser surface, not only by DB or HTTP 200.

The next product direction is documented in [[Product-Strategy-Market-to-Action]]. Signalix is evolving toward a shared **Market View to Action Engine** with separate DR Follow, TFEX Trigger, Fund Plan, Stock Alert, and private Investment Copilot experiences. The strategy includes sourced fundamental context, immutable recommendation/outcome logging, and an isolated paper/pilot portfolio before live execution.
