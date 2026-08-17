# Signalix — Project Vault

AI Trading-Agent SaaS for Thai SET retail traders. Trend-Following engine
(Mark Minervini / VCP) that auto-screens the market, scores setups, and pushes
real-time alerts to **Telegram**.

> Owner: Nitipum.s (collaborates with Arm). This vault is the canonical
> knowledge base — keep it in sync after every structural change.

## Status (updated 2026-08-12)
| Layer | State | Notes |
|-------|-------|-------|
| Data ingestion (EOD) | ✅ Done | local/drive/settrade/yfinance, idempotent |
| Scanner (TT/VCP/RS/Position sizing) | ✅ Done | deterministic, pandas + Postgres |
| Dashboard (web) | ✅ Done | dark-theme HTML, charts, port 3001 |
| Backend API | ✅ Done | FastAPI, ports 8000/3001 |
| Realtime delivery | ✅ Done | Redis `signals` → `signalix_delivery` → Telegram |
| Webhook auth | ✅ Done | `WEBHOOK_SECRET` + hmac |
| **LINE** | ❌ Dropped | user decision; `notify-api.line.me` DNS-blocked on VPS |
| LLM summarization (Phase 3) | ✅ Done | Nous portal `upstage/solar-pro4:free`, token from Hermes runtime |
| User / Auth / Subscription | ⬜ Gap | needed for true SaaS |
| Frontend app | ⬜ Gap | dashboard is read-only HTML |

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
