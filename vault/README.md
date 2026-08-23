# Signalix — Project Vault

> **STATUS: REVIEW_REQUIRED** · This overview still contains older 2026-08-12 status claims. Reconcile against `Documentation-Governance.md`, `Architecture.md`, `Deployment.md`, and `Execution-Pipeline.md` before treating the table below as current.

AI Trading-Agent SaaS for Thai SET retail traders. Trend-Following engine
(Mark Minervini / VCP) that auto-screens the market, scores setups, and pushes
real-time alerts to **Telegram**.

> Owner: Nitipum.s (collaborates with Arm). This vault is the canonical
> knowledge base — keep it in sync after every structural change.

## Status (updated 2026-08-23)

| Layer | State | Notes |
|-------|-------|-------|
| Data ingestion (EOD) | ✅ Done | local/drive/settrade/yfinance, idempotent, FULL ORD |
| Scanner (TT/VCP/RS/Position sizing) | ✅ Done | deterministic, pandas + Postgres |
| Dashboard (web) | ✅ Done | dark-theme HTML, charts, port 3001 |
| Backend API | ✅ Done | FastAPI, ports 8000/3001 |
| Realtime delivery | ✅ Done | Redis `signals` → `signalix_delivery` → Telegram |
| Webhook auth | ✅ Done | `WEBHOOK_SECRET` + hmac |
| **LINE** | ❌ Dropped | user decision; `notify-api.line.me` DNS-blocked on VPS |
| LLM summarization (Phase 3) | ✅ Done | Nous `upstage/solar-pro4:free`, Thai "why now" note |
| Multi-tenant user routing + tier quota | ✅ Done | `users.py` + `TIER_LIMITS` enforced 2026-08-12 |
| Portal frontend (self-service SPA) | ✅ Done | portal.html ↔ backend APIs; watchlist sync |
| Subscription / payment billing | ⬜ Gap | tier field exists; no payment/subscription frontend |
| Full SaaS login frontend | ⬜ Gap | no login UI; owner-only deep links |

> Older claim that User/Auth/Subscription and Frontend were pure gaps reflected the 2026-08-12 state. Multi-tier routing, enforcement, and a self-service portal shipped shortly after; only the login/ billing UI remains.


## Quick links
- [[Architecture]] — data flow + container map
- [[Components]] — every module explained
- [[Deployment]] — docker-compose, systemd, env vars
- [[Phases]] — roadmap + open gaps
- [[Execution-Pipeline]] — canonical active product/data sequence and acceptance evidence

## Invariants (do NOT violate)
1. **Deterministic calcs in code; LLM only summarizes.** Never let the LLM
   compute Trend Template / RS / position size.
2. **Edit `.env` or `backend/*.py`?** Reload with
   `docker compose up -d --force-recreate delivery backend`
   (`restart` does NOT re-read env or pick up code changes).
3. **Reuse the Hermes Telegram bot** — do not provision a new one.
4. **Docker network only.** Never run the delivery consumer on the host.
