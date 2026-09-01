# Signalix — Project Vault

> **STATUS: CURRENT** · Reconciled 2026-09-01.
> Runtime scope: T1–T9 Elliott/Trend/Trade-Setup release promotion. Served `/mvp` and `/api/setup-candidates` are verified for the public 390px failure→Retry→recovery journey; evaluator auto-caller remains separate.

AI Trading-Agent SaaS for Thai SET retail traders. Trend-Following engine
(Mark Minervini / VCP) that auto-screens the market and supports dashboard-based
watchlist/explorer review. Alert delivery is currently paused.

> Owner: Nitipum.s (collaborates with Arm). This vault is the canonical
> knowledge base — keep it in sync after every structural change.

## Status (updated 2026-08-25)

| Layer | State | Notes |
|-------|-------|-------|
| Data ingestion (EOD) | ✅ Done | local/drive/settrade/yfinance, idempotent, FULL ORD |
| Scanner (TT/VCP/RS/Position sizing) | ✅ Done | deterministic, pandas + Postgres |
| Dashboard (web) | 🟡 Partial acceptance | owner-only `/mvp`, port 3001; canonical `/api/setup-candidates`; 390px failure→Retry→recovery PASS, broader acceptance/evaluator decision separate |
| Backend API | ✅ Done | FastAPI, ports 8000/3001 |
| Realtime delivery | ⏸ Paused | Docker `delivery` is gated under Compose profile `alerts`; source/routing retained |
| Webhook auth | ✅ Done | `WEBHOOK_SECRET` + hmac |
| **LINE** | ❌ Dropped | user decision; `notify-api.line.me` DNS-blocked on VPS |
| LLM summarization (Phase 3) | ✅ Implemented, paused with alert delivery | Retained for future alert reactivation; no current alert push |
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
2. **MVP release source** is `/root/signalix`; `signalix_backend` and `signalix_dashboard`
   bind-mount its `backend/` directory. After dashboard Python/UI edits, reload
   with `docker restart signalix_dashboard`, then verify served API/browser evidence.
3. **Reuse the Hermes Telegram bot** — do not provision a new one.
4. **Docker network only.** Never run the delivery consumer on the host.
