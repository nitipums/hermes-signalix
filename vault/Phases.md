# Phases & Open Gaps

> **STATUS: CURRENT** · `CANONICAL_FOR: roadmap phase boundaries`. Individual task state belongs to the active work system, not this note.

## Phase status
- **Phase 1 — Webhook ingestion + storage + Redis pub/sub** ✅
- **Phase 2 — Deterministic screening (TT/VCP/RS/Position sizing)** ✅
- **Phase 3 — LLM summarization** ✅ (2026-08-12)
- **Phase 4 — Bot delivery** ✅ (Telegram; LINE dropped)
- **User layer (multi-tenant routing)** ✅ (2026-08-12)

## User layer (DONE 2026-08-12)
Multi-tenant routing so Signalix can serve many subscribers, not one hardcoded chat.
- `backend/users.py` — tables `users` (telegram_chat_id unique, tier) +
  `user_watchlists` (user_id, symbol). Empty watchlist = receive ALL signals.
- API: `POST /register?chat_id=&tier=` , `POST /watch?chat_id=&symbols=` (csv,
  empty = all). Schema auto-created at backend startup.
- `delivery.py` `deliver()` loads a 30s-cached routing map and fans each alert out
  to every chat watching that symbol (or watching all). Falls back to the legacy
  single `TG_CHAT_ID` only when NO user matches.
- Tier field enforced: `users.TIER_LIMITS = {free:5, paid:None, owner:None}`.
  Explicit watchlists over the free cap are rejected (HTTP 400) at `/watch`;
  watch-ALL is always allowed. set_watch uses `_ensure_user()` (no tier reset)
  so editing a watchlist never downgrades a paid user.
- Owner chat `7295704669` is registered as tier `owner`, watch-all.
- **Alert frequency cap** (per-tier, per-UTC-day) enforced in `delivery.deliver()`:
  `TIER_ALERT_CAP = {free:10, paid:200, owner:None}`. A Redis counter
  `alerts:{chat_id}:{YYYY-MM-DD}` increments per push; over-cap alerts are skipped
  (logged). Counter TTL 2 days.
- **Frontend glue (2026-08-12; retired route updated 2026-08-28)**: portal ↔ MVP now connected. Alerts carry an `/mvp` deep-link and a `/portal`
  manage link. `build_dashboard.py` injects JS that, when loaded with `?chat=ID`,
  fetches `/me` and syncs the watchlist from the backend (instead of localStorage
  only) — so portal selections appear in the MVP Watchlist tab.

## Phase 3 — LLM summarization (DONE)
LLM summarizes ONLY — never computes Trend Template / RS / position size. The
deterministic `screening.py` result is passed verbatim; the LLM appends a short
Thai "why now" note.

**Implementation (`backend/llm.py`):**
- Endpoint: Nous portal OpenAI-compatible → `https://inference-api.nousresearch.com/v1`
- Model: **`upstage/solar-pro4:free`** (free, Thai-capable, non-reasoning so
  content is never swallowed by CoT). `tencent/hy3:free` also exists on Nous but
  is reasoning-only → its `content` gets truncated by the thinking budget, so
  avoid it for alert text.
- Auth: **Nous OAuth token read at runtime** from
  `/root/.hermes/shared/nous_auth.json` (mounted read-only into the delivery
  container at `/app/nous_auth.json`). The token is cached in-memory 5 min. It is
  **NOT** copied into Signalix `.env` (privacy + expiry safety).
- Env overrides: `SIGNALIX_LLM_MODEL`, `SIGNALIX_LLM_BASE_URL`, `NOUS_AUTH_JSON`.
- Wiring: `delivery.py` `format_signal()` calls `summarize_signal(result)` and
  appends the note after the deterministic block. Safe no-op if LLM unavailable
  (returns '' → alert still sends without the note).
- Alerts are sent as **plain text** (no `parse_mode`) — a stray `*` from either
  the deterministic block or the LLM made Telegram's Markdown parser 400.

## 2026-08-13 — Intraday dashboard / chart handoff

See [[2026-08-13-Intraday-Dashboard-Handoff]] for the full verified technical handoff.

**Delivered:** unified active 60m overlay, current/open-candle upserts, provisional 1D/1W/1M charts, 15m removal, liquidity filter, same-time cumulative volume surge, Top Gainers, native chart volume pane, detail-company context cache, full-archive-versus-52W ATH semantics, mobile detail improvements, and visible 15-second snapshot polling/retry state.

**P0 continuation:** verify systemd calendar parser/cadence, build an active-ORD-only company/instrument master pipeline, add provenance/tests/mobile visual test coverage, and do not restart the stopped 7,147-symbol Yahoo metadata backfill. `company_profiles` currently has a partial cache only; it is non-decision context.

**Intraday E2E reliability (DONE 2026-08-21):** intraday-only fetch now rebuilds dashboard artifacts from the existing Daily scan after DB upsert/evaluation; watchdog tolerates expected partial-success and uses cadence-aware freshness thresholds; a temporary morning monitor checks and self-heals served dashboard freshness. See `2026-08-21-Intraday-E2E-Reliability-Incident.md`.

**Ploy-ready continuation:** use the Market View to Action roadmap below after P0 integrity work. Product discovery is already curated in [[Product-Strategy-Market-to-Action]]; begin with domain contracts and immutable recommendation/outcome persistence, not broad new UI.

## Open gaps vs SaaS goal
| Gap | Why it matters |
|-----|----------------|
| User management / auth | Multi-tenant SaaS needs accounts |
| Subscription / payment | Monetization layer absent |
| Multi-user signal routing | Today: one hardcoded Telegram chat |
| Webhook idempotency/retry/dedup | `signals` table dedupes by hash; redis consume is at-most-once (no ack replay) |
| Frontend app | Dashboard is read-only HTML; no login/UI |

## Proposed next roadmap — Market View to Action

See [[Product-Strategy-Market-to-Action]] for the curated plan agreed with Arm.

- **Phase 0:** product/domain contracts, instrument master, underlying mapping, recommendation/decision/paper/outcome schemas.
- **Phase 1:** Alert Builder, basic mapping, immutable recommendation log, outcome tracking, DR Follow proposal-only flow, fundamental snapshot foundation.
- **Phase 2:** isolated paper/pilot portfolio with deterministic paper execution and auto-management.
- **Phase 3:** US/HK/index/DR expansion, TFEX Trigger, Fund Plan, broader fundamental coverage.
- **Phase 4:** controlled real execution only after pilot evidence, reconciliation, idempotency, risk bounds, and kill switch.

Detailed feature scope and tomorrow's concrete starting artifacts are in [[Product-Strategy-Market-to-Action]], under **Detailed feature plan** and **Tomorrow's implementation starting point**. Do not restart product discovery; use that checklist as the handoff.

Industry/group analysis is part of the foundation backlog: official taxonomy first, then group breadth/dispersion/leader ranking/rotation history, with behavioral clusters later.

## Decisions log
- **2026-08-12** Dropped LINE (user decision; VPS DNS blocks `notify-api.line.me`).
- **2026-08-12** Moved delivery consumer into docker (`signalix_delivery`) — host run fails.
- **2026-08-12** Added `WEBHOOK_SECRET` + hmac auth to `/webhook`.
- **2026-08-12** Phase 3 LLM live via Nous portal, model `upstage/solar-pro4:free`;
  Nous token mounted RO from Hermes auth file (not copied to .env).
- **2026-08-12** Alerts switched to plain text (Markdown parse → Telegram 400).
- **Data source order** (Nitipum.s): native EOD zip > Settrade > Drive > yfinance.
