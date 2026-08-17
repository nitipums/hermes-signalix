"""
Signalix — User layer (multi-tenant routing).

Minimal, extensible schema for a subscription SaaS:
  * users           — one row per subscriber, keyed by Telegram chat id
  * user_watchlists — per-user symbol watchlist; NULL/empty = receive ALL signals

The delivery consumer (delivery.py) loads the active routing map from here and
fans each signal out to every user who watches that symbol (or watches "all").

Deterministic screening stays in screening.py; this module ONLY stores routing
preferences and never computes trade logic.
"""
import os
import psycopg2
import psycopg2.extras

PG = dict(
    host=os.getenv("POSTGRES_HOST", "postgres"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    user=os.getenv("POSTGRES_USER", "signalix"),
    password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
    dbname=os.getenv("POSTGRES_DB", "signalix"),
)


def get_pg():
    return psycopg2.connect(**PG)


def init_user_schema():
    """Create user-layer tables if missing. Idempotent."""
    pg = get_pg()
    cur = pg.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              SERIAL PRIMARY KEY,
            telegram_chat_id TEXT UNIQUE NOT NULL,
            tier            TEXT NOT NULL DEFAULT 'free',
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS user_watchlists (
            user_id     INT REFERENCES users(id) ON DELETE CASCADE,
            symbol     TEXT NOT NULL,
            added_at   TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, symbol)
        );
    """)
    pg.commit()
    cur.close()


def upsert_user(chat_id: str, tier: str = "free") -> int:
    pg = get_pg()
    cur = pg.cursor()
    cur.execute(
        """INSERT INTO users(telegram_chat_id, tier) VALUES (%s, %s)
           ON CONFLICT (telegram_chat_id) DO UPDATE SET tier = EXCLUDED.tier
           RETURNING id""",
        (str(chat_id), tier),
    )
    uid = cur.fetchone()[0]
    pg.commit()
    cur.close()
    return uid


def public_register_user(chat_id: str) -> int:
    """Get-or-create a public free account without downgrading an existing tier."""
    return _ensure_user(chat_id)


def _ensure_user(chat_id: str) -> int:
    """Get-or-create a user WITHOUT touching the tier (used by set_watch)."""
    pg = get_pg()
    cur = pg.cursor()
    cur.execute(
        "INSERT INTO users(telegram_chat_id) VALUES (%s) "
        "ON CONFLICT (telegram_chat_id) DO UPDATE SET telegram_chat_id=EXCLUDED.telegram_chat_id "
        "RETURNING id",
        (str(chat_id),),
    )
    uid = cur.fetchone()[0]
    pg.commit()
    cur.close()
    return uid


# Subscription tiers.
#  * Watchlist size: empty (watch ALL) always allowed; explicit list capped for free.
#  * Alert frequency: max alerts pushed per user per UTC day (None = unlimited).
TIER_LIMITS = {"free": 5, "paid": None, "owner": None}
TIER_ALERT_CAP = {"free": 10, "paid": 200, "owner": None}
WATCH_ALL_ALWAYS_ALLOWED = True


def alert_cap_for(tier: str):
    return TIER_ALERT_CAP.get(tier, TIER_ALERT_CAP["free"])


def public_registration_tier(requested: str = "free") -> str | None:
    """Public signup may create free users only; tier elevation is admin-only."""
    return "free" if (requested or "free").lower() == "free" else None


def get_user_state(chat_id: str) -> dict:
    """Return {tier, watch_mode, symbols, watchlist_cap, alert_cap, alerts_today}."""
    pg = get_pg(); cur = pg.cursor()
    cur.execute("SELECT id, tier FROM users WHERE telegram_chat_id=%s", (str(chat_id),))
    row = cur.fetchone()
    if not row:
        return {"exists": False, "tier": "free", "watch_mode": "none",
                "symbols": [], "watchlist_cap": TIER_LIMITS["free"],
                "alert_cap": TIER_ALERT_CAP["free"], "alerts_today": 0}
    uid, tier = row
    cur.execute("SELECT symbol FROM user_watchlists WHERE user_id=%s ORDER BY symbol", (uid,))
    syms = [r[0] for r in cur.fetchall()]
    cur.close()
    return {"exists": True, "tier": tier,
            "watch_mode": "all" if not syms else "watchlist",
            "symbols": syms, "watchlist_cap": TIER_LIMITS.get(tier),
            "alert_cap": TIER_ALERT_CAP.get(tier), "alerts_today": 0}


def _normalize_symbols(symbols) -> list[str]:
    """Uppercase, remove blanks, and deduplicate while preserving input order."""
    return list(dict.fromkeys(s.upper().strip() for s in (symbols or []) if s and s.strip()))


def _unknown_symbols(symbols: list[str]) -> list[str]:
    """Only permit active Thai ORD symbols present in the authoritative price store."""
    if not symbols:
        return []
    pg = get_pg(); cur = pg.cursor()
    cur.execute(
        "SELECT DISTINCT symbol FROM price_data "
        "WHERE instrument_type='ORD' AND symbol = ANY(%s)",
        (symbols,),
    )
    known = {row[0].upper() for row in cur.fetchall()}
    cur.close()
    return [symbol for symbol in symbols if symbol not in known]


def set_watch(chat_id: str, symbols):
    """Replace a user's watchlist with validated, deduplicated ORD tickers.

    `symbols` = list of tickers, or empty/None = watch ALL (always allowed).
    Validation happens *before* creating a user: an invalid request must never
    accidentally create an empty watch-all account.
    """
    syms = _normalize_symbols(symbols)
    if syms:
        unknown = _unknown_symbols(syms)
        if unknown:
            return False, "Unknown or unavailable SET ORD ticker(s): " + ", ".join(unknown)

    uid = _ensure_user(chat_id)
    if not syms:  # explicit watch ALL
        pg = get_pg(); cur = pg.cursor()
        cur.execute("DELETE FROM user_watchlists WHERE user_id=%s", (uid,))
        pg.commit(); cur.close()
        return True, "watch_all"

    # Explicit watchlist -> enforce cap AFTER deduplication.
    tier = _tier_of(uid)
    limit = TIER_LIMITS.get(tier)
    if limit is not None and len(syms) > limit:
        return False, f"tier '{tier}' allows at most {limit} unique symbols (got {len(syms)}). Upgrade to watch more."
    pg = get_pg(); cur = pg.cursor()
    cur.execute("DELETE FROM user_watchlists WHERE user_id=%s", (uid,))
    psycopg2.extras.execute_values(cur,
        "INSERT INTO user_watchlists(user_id, symbol) VALUES %s", [(uid, s) for s in syms])
    pg.commit(); cur.close()
    return True, f"watchlist:{len(syms)}"


def _tier_of(uid: int) -> str:
    pg = get_pg(); cur = pg.cursor()
    cur.execute("SELECT tier FROM users WHERE id=%s", (uid,))
    row = cur.fetchone(); cur.close()
    return row[0] if row else "free"


def get_routing_map():
    """Return {symbol_upper: [chat_id,...], '*': [chat_id,...]} for users watching ALL."""
    pg = get_pg()
    cur = pg.cursor()
    cur.execute("SELECT id, telegram_chat_id FROM users")
    uid_to_chat = {r[0]: r[1] for r in cur.fetchall()}
    routing = {}          # symbol -> [chat_id]
    watch_all = []        # chat_ids that receive everything
    cur.execute("SELECT user_id, symbol FROM user_watchlists")
    for uid, sym in cur.fetchall():
        chat = uid_to_chat.get(uid)
        if chat:
            routing.setdefault(sym.upper(), []).append(chat)
    cur.execute("SELECT u.telegram_chat_id FROM users u "
                "LEFT JOIN user_watchlists w ON w.user_id=u.id "
                "GROUP BY u.id, u.telegram_chat_id HAVING count(w.symbol)=0")
    watch_all = [r[0] for r in cur.fetchall()]
    cur.close()
    return routing, watch_all


if __name__ == "__main__":
    init_user_schema()
    print("user schema ready")
    r, a = get_routing_map()
    print(f"routing symbols={len(r)} watch_all={len(a)}")
