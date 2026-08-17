"""
Signalix — Delivery layer (Phase 3 real-time push).

One shared module used by BOTH:
  * app.py          -> build_and_push_summary() pushes the batch scan to Telegram
  * delivery_consumer.py -> a standalone process that SUBSCRIBES to the Redis
                            `signals` channel and pushes every realtime webhook /
                            screen envelope to Telegram.

Everything is env-gated: if a token is missing the push is a silent no-op, so
the code is safe to deploy before credentials are pasted in.

Webhook -> channel wiring
-------------------------
  /webhook  publishes a generic envelope  {id,symbol,source,payload,...}
  /scan     publishes a "screen" envelope  {type:"screen",result:{...}}
  The consumer formats both into a readable Thai alert and fans out to Telegram.
"""
import os
import json
import datetime as dt

import redis
import requests

# ---------- config (env-gated) ----------
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DASHBOARD_PUBLIC_URL = os.getenv("DASHBOARD_PUBLIC_URL", "").rstrip("/")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_CHANNEL = os.getenv("REDIS_CHANNEL", "signals")

# Phase 3 LLM summarization (Nous portal). Reads its token from the Hermes auth
# file at call time — see backend/llm.py. Safe no-op if unavailable.
from llm import summarize_signal  # noqa: E402

# Multi-tenant routing (user layer). Imported lazily-safe: if users.py is missing
# the consumer falls back to the single hardcoded TG_CHAT_ID.
try:
    from users import get_routing_map, alert_cap_for as users_alert_cap
except Exception:
    get_routing_map = None
    users_alert_cap = lambda t: None

import threading
_ROUTING_CACHE = {"map": ({}, []), "at": 0}
_ROUTING_TTL = 30  # seconds — reload routing at most every 30s


def _routing():
    """Cached {symbol:[chats], '*':[chats]} so we don't hit DB per message."""
    now = __import__("time").time()
    if now - _ROUTING_CACHE["at"] > _ROUTING_TTL or get_routing_map is None:
        try:
            _ROUTING_CACHE["map"] = get_routing_map() if get_routing_map else ({}, [])
            _ROUTING_CACHE["at"] = now
        except Exception as e:
            print(f"  ! routing load failed: {repr(e)[:100]}")
    return _ROUTING_CACHE["map"]


_TIER_CACHE = {"map": {}, "at": 0}


def _tier_for_chats(rd, chats) -> dict:
    """Return {chat_id: tier} for the given chats, cached 60s (DB-backed)."""
    import time as _t
    now = _t.time()
    if now - _TIER_CACHE["at"] > 60:
        try:
            pg = __import__("psycopg2").connect(
                host=os.getenv("POSTGRES_HOST", "postgres"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
                user=os.getenv("POSTGRES_USER", "signalix"),
                password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
                dbname=os.getenv("POSTGRES_DB", "signalix"),
            )
            cur = pg.cursor()
            cur.execute("SELECT telegram_chat_id, tier FROM users")
            _TIER_CACHE["map"] = {r[0]: r[1] for r in cur.fetchall()}
            cur.close(); pg.close()
            _TIER_CACHE["at"] = now
        except Exception as e:
            print(f"  ! tier map load failed: {repr(e)[:100]}")
    return {c: _TIER_CACHE["map"].get(c, "free") for c in chats}


# ---------- low-level senders ----------
def push_telegram(text: str, chat_id: str = None) -> bool:
    """Send a message to a Telegram chat. Defaults to TG_CHAT_ID (single-tenant
    fallback). No-op if the token or target chat is missing.

    Sent as plain text (no parse_mode): the alert mixes deterministic fields and
    an LLM summary, and any stray '*'/'_' from either side would make Telegram's
    Markdown parser 400. Plain text is mobile-friendly and never breaks.
    """
    target = chat_id or TG_CHAT_ID
    if not TG_TOKEN or not target:
        print("  ! Telegram not configured (token / target chat missing) — skip push")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": target, "text": text,
                  "disable_web_page_preview": False},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"  ! Telegram send failed: HTTP {r.status_code} {r.text[:120]}")
            return False
        return True
    except Exception as e:  # network / timeout
        print(f"  ! Telegram error: {repr(e)[:120]}")
        return False


# ---------- formatting ----------
def _fmt_screen(result: dict) -> str:
    """Pretty Thai alert for a Minervini screen envelope."""
    sym = result.get("symbol", "?")
    last = result.get("last_date", "")
    close = result.get("close", "")
    tt = result.get("trend_template", {}) or {}
    vcp = result.get("vcp", {}) or {}
    bz = result.get("buy_zone", {}) or {}
    tr = result.get("trade_readiness", {}) or {}

    met = tt.get("conditions_met", 0)
    rs = tt.get("rs_rating")
    is_vcp = vcp.get("is_vcp")
    vcp_pct = vcp.get("latest_contraction_pct")
    buys = bz.get("buy_zones") or {}
    stop = bz.get("stop_loss")
    readiness = tr.get("status", "-")

    lines = [f"🚀 *Signalix Alert — {sym}*",
             f"📅 {last}   💰 ปิด {close}"]
    lines.append("")
    lines.append(f"✅ Trend Template: *{met}/8* {'✅' if tt.get('pass') else '⚠️'}")
    if rs is not None:
        lines.append(f"⭐ RS Rating: *{rs}*")
    lines.append(f"🔺 VCP: {'Yes (' + str(vcp_pct) + '%)' if is_vcp else 'No'}")
    if buys:
        lines.append("🎯 Buy Zone: " + " / ".join(f"{k}={v}" for k, v in buys.items()))
    if stop is not None:
        lines.append(f"🛡 Stop: {stop}")
    lines.append(f"📊 Trade Readiness: {readiness}")
    if DASHBOARD_PUBLIC_URL:
        lines.append("")
        lines.append(f"🔗 Dashboard: {DASHBOARD_PUBLIC_URL}/dashboard.html#{sym}")
        lines.append(f"⚙️ จัดการ Watchlist: {DASHBOARD_PUBLIC_URL}/portal")
    return "\n".join(lines)


def _fmt_generic(envelope: dict) -> str:
    """Fallback for arbitrary webhook payloads."""
    sym = envelope.get("symbol", "?")
    src = envelope.get("source", "unknown")
    payload = envelope.get("payload", envelope)
    if isinstance(payload, dict):
        summary = "  " + " | ".join(f"{k}={v}" for k, v in list(payload.items())[:8])
    else:
        summary = str(payload)[:400]
    return (f"📡 *Signalix Webhook — {sym}* (src: {src})\n{summary}")


def format_signal(envelope: dict) -> str:
    """Turn a Redis envelope into a human-readable alert (Thai).

    Deterministic fields come from code; if the LLM is configured it appends a
    short Thai 'why now' note (never recomputes numbers).
    """
    etype = envelope.get("type")
    if etype == "screen" and isinstance(envelope.get("result"), dict):
        base = _fmt_screen(envelope["result"])
        note = summarize_signal(envelope["result"])
        return base + ("\n\n💡 " + note if note else "")
    return _fmt_generic(envelope)


def _alert_count_key(chat_id: str) -> str:
    """Redis key for a user's per-UTC-day alert counter."""
    import datetime as _dt
    day = _dt.datetime.utcnow().strftime("%Y-%m-%d")
    return f"alerts:{chat_id}:{day}"


def _incr_alert_count(rd, chat_id: str, cap) -> bool:
    """Increment the daily counter; return True if still within cap (or cap is None)."""
    if cap is None:
        return True
    key = _alert_count_key(chat_id)
    try:
        n = rd.incr(key)
        if n == 1:
            rd.expire(key, 86400 * 2)
        if n > cap:
            # roll back the over-cap increment so the counter stays meaningful
            rd.decr(key)
            return False
        return True
    except Exception:
        # redis hiccup -> don't block delivery
        return True


def deliver(envelope: dict) -> None:
    """Format + fan out to every subscribed Telegram chat, enforcing the tier
    alert-cap (max alerts per user per UTC day).

    Routing:
      * users with an empty watchlist receive ALL signals
      * users watching the signal's symbol receive it
      * if no user matches, fall back to the hardcoded TG_CHAT_ID (legacy mode)
    """
    text = format_signal(envelope)
    sym = (envelope.get("symbol")
           or (envelope.get("result") or {}).get("symbol")
           or "").upper()
    routing, watch_all = _routing()
    targets = set(watch_all)
    targets.update(routing.get(sym, []))
    if not targets:
        # legacy single-chat fallback — no per-user cap applies
        push_telegram(text)
        return
    rd = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    # map chat -> tier (from routing cache helper)
    tier_of = _tier_for_chats(rd, targets)
    for chat in targets:
        cap = users_alert_cap(tier_of.get(chat, "free"))
        if not _incr_alert_count(rd, chat, cap):
            print(f"  ! alert cap reached for {chat} (tier {tier_of.get(chat)}) — skip")
            continue
        push_telegram(text, chat_id=chat)


# ---------- consumer ----------
def run_consumer(channel: str = REDIS_CHANNEL) -> None:
    """Subscribe to Redis and push every envelope to Telegram.

    Blocks forever. Run as a standalone process (delivery_consumer.py).
    """
    rd = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    pubsub = rd.pubsub()
    pubsub.subscribe(channel)
    print(f"[delivery] subscribed to Redis channel '{channel}' — push to Telegram")
    for msg in pubsub.listen():
        if msg.get("type") != "message":
            continue
        try:
            envelope = json.loads(msg["data"])
        except Exception as e:
            print(f"  ! bad envelope on channel: {repr(e)[:120]}")
            continue
        try:
            deliver(envelope)
        except Exception as e:
            print(f"  ! deliver failed: {repr(e)[:160]}")


if __name__ == "__main__":
    run_consumer()
