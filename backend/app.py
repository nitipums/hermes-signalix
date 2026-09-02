"""
Signalix backend - Phase 1 (webhook) + Phase 2 (DB-backed screening).

Phase 1: webhook ingestion + storage + Redis pub/sub (backbone).
Phase 2: deterministic screening (Minervini Trend Template / VCP / RS /
         Position Sizing) read from PostgreSQL, published over the SAME
         Redis channel that bots/dashboard consume.
LLM summarization is Phase 3 (LLM only summarizes, never computes).
"""
import os
import json
import uuid
import hmac
import hashlib
import datetime as dt
import re

import psycopg2
import psycopg2.extras
import redis
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form, Header

from provenance_contract import compute_freshness, FRESH, STALE, UNKNOWN
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
import uvicorn

# ---------- Config ----------
PG_DSN = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "user": os.getenv("POSTGRES_USER", "signalix"),
    "password": os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
    "dbname": os.getenv("POSTGRES_DB", "signalix"),
}
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_CHANNEL = os.getenv("REDIS_CHANNEL", "signals")

app = FastAPI(title="Signalix Backend", version="0.1.0")
# The dashboard snapshot is intentionally complete (718 cards), but is roughly
# 6.6 MB uncompressed.  Compress responses at the HTTP boundary; this preserves
# the exact JSON contract while avoiding slow repeated transfers.
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
# Dashboard is served on port 3001; chart fetches go to this API on port 8000.
# Explicit origins keep browser access working without opening credentialed CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://91.98.72.120:3001",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["X-Portfolio-Token", "X-Authenticated-User", "X-Idempotency-Key"],
)

# ---------- Connections (lazy) ----------
_pg = None
_rd = None

def get_pg():
    global _pg
    if _pg is None or _pg.closed:
        _pg = psycopg2.connect(**PG_DSN)
        _pg.autocommit = True
    return _pg

def get_rd():
    global _rd
    if _rd is None:
        _rd = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _rd

# ---------- Schema ----------
def schema_application_mode():
    """Return the explicit startup DDL policy (safe default: no DDL)."""
    mode = os.getenv("SIGNALIX_SCHEMA_MODE", "validate").strip().lower()
    if mode not in {"validate", "apply"}:
        raise RuntimeError("SIGNALIX_SCHEMA_MODE must be 'validate' or 'apply'")
    return mode


def init_db():
    pg = get_pg()
    cur = pg.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS signals (
        id UUID PRIMARY KEY,
        symbol TEXT NOT NULL,
        source TEXT,
        payload JSONB NOT NULL,
        signal_hash TEXT UNIQUE,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS raw_events (
        id SERIAL PRIMARY KEY,
        event_type TEXT,
        body JSONB,
        received_at TIMESTAMPTZ DEFAULT NOW()
    );
    """)
    cur.close()
    # Daily full-scan history is deliberately separate from intraday tables.
    from scan_history import init_daily_scan_history_schema
    init_daily_scan_history_schema(pg)

@app.on_event("startup")
def startup():
    if schema_application_mode() != "apply":
        print("  ! schema DDL skipped (SIGNALIX_SCHEMA_MODE=validate)")
        return
    init_db()
    try:
        from deferred_runtime import init_deferred_schemas
        init_deferred_schemas(get_pg)
    except Exception as e:
        print(f"  ! deferred schema init failed: {repr(e)[:120]}")

# ---------- Helpers ----------
def dedupe_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]

# ---------- Routes ----------
@app.get("/health")
def health():
    try:
        get_pg().cursor().execute("SELECT 1")
        get_rd().ping()
        return {"status": "ok", "db": "up", "redis": "up"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "degraded", "error": str(e)})


@app.get("/health/readiness")
def readiness():
    """Fast DB/Redis readiness probe; never touches the dashboard snapshot."""
    try:
        get_pg().cursor().execute("SELECT 1")
        get_rd().ping()
        return {"status": "ok", "db": "up", "redis": "up"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "degraded", "error": str(e)})


@app.get("/api/risk-stop-target/{symbol}")
def risk_stop_target(symbol: str, contract: str = "daily"):
    """Deprecated compatibility alias for the canonical /risk-plan endpoint.

    Keep one deterministic RST contract: legacy callers are delegated to
    ``risk_plan`` rather than maintaining a second calculation path.
    """
    return risk_plan(symbol=symbol, contract=contract)


def load_snapshot_items() -> list[dict]:
    """Load serialized items from the latest snapshot for RST calculation."""
    snap_path = os.path.join(os.path.dirname(__file__), "dashboard_snapshot.json")
    if not os.path.exists(snap_path):
        return []
    try:
        with open(snap_path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


# ---------- User layer (multi-tenant routing) ----------
from users import upsert_user, set_watch, _normalize_symbols  # noqa: E402


@app.post("/register")
def register_user(chat_id: str, tier: str = "free"):
    """Public signup creates free subscribers only; tier changes are admin-only."""
    from users import public_registration_tier, public_register_user
    public_tier = public_registration_tier(tier)
    if public_tier is None:
        raise HTTPException(status_code=403, detail="tier provisioning is admin-only")
    uid = public_register_user(chat_id)
    return {"status": "ok", "user_id": uid, "chat_id": chat_id, "tier": public_tier}


@app.post("/watch")
def watch(chat_id: str, symbols: str = ""):
    """Set a user's watchlist. Comma-separated tickers, or empty = receive ALL.

    Free tier is capped (see users.TIER_LIMITS); returns 400 if exceeded.
    """
    raw_syms = [s for s in symbols.split(",") if s.strip()] if symbols else []
    syms = _normalize_symbols(raw_syms)
    ok, msg = set_watch(chat_id, syms)
    if not ok:
        return JSONResponse(status_code=400, content={"status": "rejected", "reason": msg})
    return {"status": "ok", "chat_id": chat_id,
            "mode": "all" if not syms else "watchlist", "symbols": syms}


@app.get("/me")
def me(chat_id: str):
    """Return a user's current state (tier, watchlist, caps) for the frontend."""
    from users import get_user_state
    state = get_user_state(chat_id)
    # alerts sent today (live Redis counter)
    try:
        import redis as _redis
        rd = _redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"),
                                   decode_responses=True)
        import datetime as _dt
        day = _dt.datetime.utcnow().strftime("%Y-%m-%d")
        key = f"alerts:{chat_id}:{day}"
        state["alerts_today"] = int(rd.get(key) or 0)
    except Exception:
        pass
    return state


@app.get("/tiers")
def tiers():
    """Public tier table for the pricing/plan page."""
    from users import TIER_LIMITS, TIER_ALERT_CAP
    return {
        "tiers": {
            t: {"watchlist": (TIER_LIMITS[t] if TIER_LIMITS[t] is not None else "unlimited"),
                "alerts_per_day": (TIER_ALERT_CAP[t] if TIER_ALERT_CAP[t] is not None else "unlimited")}
            for t in TIER_LIMITS
        }
    }


# Deferred Portfolio/owner routes are isolated from the MVP app core.
from portfolio_routes import create_portfolio_router
app.include_router(create_portfolio_router(get_pg))
from lifecycle_routes import create_lifecycle_router
app.include_router(create_lifecycle_router(get_pg))


@app.post("/webhook")
async def receive_webhook(request: Request):
    """Accept TradingView / analysis webhook payloads, store + publish.

    If WEBHOOK_SECRET is set, the caller must supply it via the
    `X-Webhook-Secret` header OR a `?secret=` query param, else 401.
    """
    if WEBHOOK_SECRET:
        provided = request.headers.get("X-Webhook-Secret") or request.query_params.get("secret", "")
        if not provided or not hmac.compare_digest(provided, WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="invalid or missing webhook secret")
    try:
        body = await request.json()
    except Exception:
        # Some webhooks send form-encoded; fall back to raw text
        raw = (await request.body()).decode("utf-8", "ignore")
        body = {"raw": raw}

    source = request.headers.get("X-Source", "unknown")
    sig_hash = dedupe_hash(body)

    pg = get_pg()
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # log raw event
    cur.execute("INSERT INTO raw_events(event_type, body) VALUES (%s, %s)", ("webhook", json.dumps(body, default=str)))

    # dedupe
    cur.execute("SELECT id FROM signals WHERE signal_hash = %s", (sig_hash,))
    if cur.fetchone():
        cur.close()
        return {"status": "duplicate", "hash": sig_hash}

    symbol = (body.get("symbol") or body.get("ticker") or "UNKNOWN").upper()
    sig_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO signals(id, symbol, source, payload, signal_hash) VALUES (%s,%s,%s,%s,%s)",
        (sig_id, symbol, source, json.dumps(body, default=str), sig_hash),
    )
    cur.close()

    # publish to Redis for downstream consumers (bot, dashboard)
    envelope = {
        "id": sig_id,
        "symbol": symbol,
        "source": source,
        "payload": body,
        "received_at": dt.datetime.utcnow().isoformat() + "Z",
    }
    try:
        get_rd().publish(REDIS_CHANNEL, json.dumps(envelope, default=str))
    except Exception as e:
        # not fatal — stored already
        print("redis publish failed:", e)

    return {"status": "stored", "id": sig_id, "symbol": symbol}

@app.get("/signals")
def list_signals(limit: int = 50):
    pg = get_pg()
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, symbol, source, payload, created_at FROM signals ORDER BY created_at DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close()
    return {"count": len(rows), "signals": [dict(r) for r in rows]}


@app.get("/symbols/excluded")
def list_excluded_symbols():
    """Return delisted / inactive symbols (marked after the 60m backfill proved
    Settrade has no data for them). These are excluded from the scan and the
    primary dashboard but inspectable here for record-keeping."""
    from screening import excluded_symbols
    pg = get_pg()
    try:
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT symbol, instrument_type, status, reason, marked_at "
            "FROM symbol_master WHERE status <> 'active' ORDER BY status, symbol")
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        return {"count": len(rows), "excluded": rows}
    finally:
        pg.close()


@app.get("/instruments")
def list_instruments(limit: int = 200):
    """Return bounded authoritative active-ORD identity/taxonomy records."""
    from instruments import instrument_master, instrument_quality_summary, profile_taxonomy, validate_instrument_record
    limit = max(1, min(int(limit), 1000))
    pg = get_pg()
    try:
        records = instrument_master(pg)[:limit]
        profiles = profile_taxonomy(pg, [r["symbol"] for r in records])
        for record in records:
            record["quality"] = validate_instrument_record(record)
            record["profile"] = profiles.get(record["symbol"], {
                "symbol": record["symbol"], "missing": True,
                "source": None,
            })
        return {
            "count": len(records), "limit": limit, "source": "symbol_master",
            "quality": instrument_quality_summary(records),
            "instruments": records,
        }
    finally:
        pg.close()


@app.get("/instruments/{symbol}")
def get_instrument(symbol: str):
    """Return one authoritative identity plus honest profile provenance."""
    from instruments import instrument_identity, profile_taxonomy
    pg = get_pg()
    try:
        identity = instrument_identity(pg, symbol)
        if identity is None:
            raise HTTPException(status_code=404, detail="instrument identity not found")
        profile = profile_taxonomy(pg, [symbol]).get(symbol)
        return {"instrument": identity, "profile": profile}
    finally:
        pg.close()


# ---------- Phase 3 delivery (shared with the real-time consumer) ----------
from screening import analyze_symbol_db, analyze_symbol_db_ranked, scan_universe, group_scan_results, load_symbol_intraday  # noqa: E402
from provenance_contract import screen_price_provenance  # noqa: E402
from scan_history import persist_daily_scan_snapshot, active_breakout_events, persist_breakout_lifecycle, breakout_event_lifecycle, reconcile_intraday_events_at_eod  # noqa: E402
# All senders + formatters live in delivery.py so the batch scan (here) and the
# standalone Redis consumer format + push identically.
from delivery import push_telegram, DASHBOARD_PUBLIC_URL  # noqa: E402

# Webhook shared-secret gate. When set, /webhook requires it (header
# X-Webhook-Secret or ?secret=). Leave empty to accept any POST — NOT
# recommended while port 8000 is exposed publicly.
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


def build_and_push_summary(cands, near, scan_time, scanned, run_id=None):
    """Build the dashboard HTML, then push a summary + link to Telegram."""
    # build dashboard (runs build_dashboard.build in-process)
    try:
        import build_dashboard
        info = build_dashboard.build(scanned=scanned, run_id=run_id)
        vcp_n = info["vcp"]
    except Exception as e:
        print(f"  ! dashboard build failed: {repr(e)[:120]}")
        vcp_n = sum(1 for c in cands if c.get("vcp", {}).get("is_vcp"))
    url = DASHBOARD_PUBLIC_URL.rstrip("/") + "/mvp" if DASHBOARD_PUBLIC_URL else ""
    top = sorted(cands, key=lambda c: c["trend_template"]["rs_rating"], reverse=True)[:8]
    lines = [f"📊 *Signalix Scan* — {scan_time[:19].replace('T',' ')} UTC",
             f"✅ ผ่าน Trend Template 8/8: *{len(cands)}* หุ้น  |  🔺 VCP: *{vcp_n}*  |  Near-miss 6/8: {len(near)}",
             "",
             "*Top RS (ใกล้ buy-zone Fib 0.5/0.618):*"]
    for c in top:
        tt = c["trend_template"]
        vcp = " 🔺VCP" if c.get("vcp", {}).get("is_vcp") else ""
        bz = c.get("buy_zone") or {}
        buys = ""
        if bz.get("buy_zones"):
            buys = " | buy-zone " + "/".join(f"{k}={v}" for k, v in bz.get("buy_zones", {}).items())
        lines.append(f"  • {c['symbol']}  RS {tt['rs_rating']:.0f}  ปิด {c['close']}{vcp}{buys}")
    if url:
        lines.append("")
        lines.append(f"📈 Dashboard: {url}")
    else:
        lines.append("")
        lines.append("⚠️ ตั้ง DASHBOARD_PUBLIC_URL ใน .env เพื่อแนบลิงก์")
    push_telegram("\n".join(lines))
    return url

def _write_scan_json(cands, near, groups=None):
    """Write scan_results.json (read by build_dashboard.py) atomically."""
    path = os.path.join(os.path.dirname(__file__), "scan_results.json")
    payload = {
        "scan_time": dt.datetime.now(dt.timezone.utc).isoformat(),
        "full_trend_template": cands,
        "near_miss_6of8": near,
        "groups": groups or {},
    }
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    os.replace(tmp, path)
    print(f"  scan_results.json written: {len(cands)} full, {len(near)} near-miss")


def _publish_screen(result: dict, min_conditions: int):
    """Persist + publish a screening result on the same Redis channel."""
    pg = get_pg()
    cur = pg.cursor()
    sig_hash = dedupe_hash({"type": "screen", "symbol": result["symbol"],
                            "scan_time": result["scan_time"]})
    cur.execute(
        "INSERT INTO signals(id, symbol, source, payload, signal_hash) "
        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (signal_hash) DO NOTHING",
        (str(uuid.uuid4()), result["symbol"], "screen",
         json.dumps(result, default=str), sig_hash),
    )
    cur.close()
    envelope = {"type": "screen", "symbol": result["symbol"],
                "min_conditions": min_conditions, "result": result,
                "published_at": dt.datetime.utcnow().isoformat() + "Z"}
    try:
        get_rd().publish(REDIS_CHANNEL, json.dumps(envelope, default=str))
    except Exception as e:
        print("redis publish failed:", e)
    return sig_hash


@app.get("/screen/{symbol}")
def screen_symbol(symbol: str):
    """Run the Minervini pipeline for a single symbol from the DB archive.

    Uses the SAME rank-based universe RS as /scan so TT/RS is consistent.
    Returns the enriched daily_state (stage + 2-layer actionable setup state).
    """
    try:
        result = analyze_symbol_db_ranked(symbol.upper())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"screen failed: {e}")
    if result is None:
        raise HTTPException(status_code=404,
                            detail=f"{symbol} not found or insufficient history")
    # /screen is Daily/EOD analysis only.  Its fresh scan_time must never be
    # interpreted as a current quote timestamp; current price belongs to /chart.
    result.update(screen_price_provenance(
        last_date=result.get("last_date"),
        scan_time=result.get("scan_time"),
    ))
    result["daily_eod"] = {
        "source": "price_data",
        "as_of": result.get("last_date"),
        "close": result.get("close"),
    }
    # Keep Daily analytics immutable, but expose the latest stored intraday
    # quote separately.  A fresh scan must not make an older EOD close look
    # like the current market price.
    quote_cur = get_pg().cursor()
    quote_cur.execute(
        """SELECT ts, open, high, low, close, volume
           FROM intraday_price_data
           WHERE symbol=%s AND interval='60m'
           ORDER BY ts DESC LIMIT 1""",
        (symbol.upper(),),
    )
    quote_row = quote_cur.fetchone()
    quote_cur.close()
    if quote_row:
        quote_ts, quote_open, quote_high, quote_low, quote_close, quote_volume = quote_row
        quote_iso = quote_ts.isoformat()
        quote_freshness = compute_freshness(quote_ts)
        result.update({
            "quote_source": "intraday_price_data",
            "quote_provider": "settrade_intraday_60m",
            "quote_timestamp": quote_iso,
            "quote_is_provisional": True,
            "freshness_verdict": quote_freshness,
            "current_quote": {
                "price": float(quote_close),
                "timestamp": quote_iso,
                "open": float(quote_open),
                "high": float(quote_high),
                "low": float(quote_low),
                "volume": float(quote_volume or 0),
                "source": "intraday_price_data",
                "provider": "settrade_intraday_60m",
                "is_provisional": True,
                "freshness": quote_freshness,
            },
        })
    _publish_screen(result, result["trend_template"]["conditions_met"])
    # Two-layer actionable setup state (quality gate + proximity timing).
    # Mirrors group_scan_results' daily_state attachment for a single symbol.
    from daily_setup_state import classify_daily_state
    from setup_state import compute_setup_state
    from scan_history import active_breakout_events
    pg = get_pg()
    events = active_breakout_events(pg)
    state = classify_daily_state(result, events.get(symbol.upper(), {}))
    _setup = compute_setup_state(state["stage"], result)
    state["setup_quality"] = _setup["quality"]
    state["setup_proximity"] = _setup["proximity"]
    result["daily_state"] = state
    return result


@app.get("/risk-plan/{symbol}")
def risk_plan(
    symbol: str,
    contract: str = "daily",
    account_size: float | None = None,
    risk_percent: float | None = None,
    planned_entry: float | None = None,
    planned_stop: float | None = None,
):
    """On-demand Risk / Stop / Target Assistant.

    Returns deterministic Fib 1.272/1.618 targets, system stop, planned stop,
    and position sizing. User inputs are session-local only — never persisted.

    Contracts:
      daily    — derives swing anchors from analyze_symbol_db_ranked (DB archive)
      intraday — derives swing anchors from stored 60m candles

    All calculations are read-only and deterministic. NOT_VERIFIED is returned
    when anchors are stale/invalid — never fabricated numbers.
    """
    import risk_stop_target as rst

    symbol = symbol.upper().strip()
    contract = contract.lower().strip()

    if contract not in ("daily", "intraday"):
        raise HTTPException(
            status_code=400,
            detail=f"contract must be 'daily' or 'intraday', got '{contract}'",
        )

    user_inputs = {}
    if account_size is not None and account_size > 0:
        user_inputs["account_size"] = account_size
    if risk_percent is not None and 0 < risk_percent <= 100:
        user_inputs["risk_percent"] = risk_percent
    if planned_entry is not None:
        user_inputs["planned_entry"] = planned_entry
    if planned_stop is not None:
        user_inputs["planned_stop"] = planned_stop

    if contract == "daily":
        # Pre-baked: risk anchors are deterministic and computed at build time.
        # Only user-input sizing is computed at request time.
        try:
            cache = _load_dashboard_cache()
        except HTTPException:
            raise HTTPException(status_code=503, detail="dashboard cache unavailable")
        snapshot_items = {item["symbol"]: item for item in cache.get("items", [])}
        snapshot_item = snapshot_items.get(symbol)
        if snapshot_item is None:
            raise HTTPException(
                status_code=404,
                detail=f"{symbol} not found or insufficient history",
            )
        # Reconstruct the base RST result from pre-baked fields
        base = {
            "symbol": symbol,
            "contract": "daily",
            "trigger": snapshot_item.get("rst_trigger"),
            "system_stop": snapshot_item.get("rst_system_stop"),
            "pivot_low": snapshot_item.get("rst_pivot_low"),
            "swing_low": snapshot_item.get("rst_swing_low"),
            "swing_high": snapshot_item.get("rst_swing_high"),
            "planned_entry": snapshot_item.get("rst_planned_entry"),
            "planned_stop": snapshot_item.get("rst_planned_stop"),
            "fib_1272": snapshot_item.get("rst_fib_1272"),
            "fib_1618": snapshot_item.get("rst_fib_1618"),
            "freshness": snapshot_item.get("date") or snapshot_item.get("daily_eod_freshness", {}).get("as_of"),
            "sizing": {"risk_budget": None, "risk_per_share": None,
                       "shares": None, "status": "NOT_VERIFIED"},
            "warnings": snapshot_item.get("rst_warnings", []),
            "status": snapshot_item.get("rst_status", "NOT_VERIFIED"),
        }
        # Apply user inputs for sizing only
        base["planned_entry"] = (user_inputs.get("planned_entry")
                                  if user_inputs.get("planned_entry") is not None
                                  else snapshot_item.get("rst_trigger"))
        base["planned_stop"] = (user_inputs.get("planned_stop")
                                 if user_inputs.get("planned_stop") is not None
                                 else snapshot_item.get("rst_system_stop"))
        if user_inputs:
            sizing = rst.compute_position_size(
                user_inputs.get("account_size"),
                user_inputs.get("risk_percent"),
                base["planned_entry"],
                base["planned_stop"],
            )
            base["sizing"] = sizing
            # Recompute warnings with user override
            base["warnings"] = rst._compute_warnings(base["planned_stop"], base["system_stop"])
            base["status"] = "OK" if not base["warnings"] else "OK_WITH_WARNINGS"
        return base

    # intraday contract
    pg = get_pg()
    try:
        df = load_symbol_intraday(symbol, pg=pg, interval="60m", lookback=400)
    finally:
        pg.close()
    return rst.compute_risk_stop_target("intraday", symbol, intraday_df=df, user_inputs=user_inputs or None)


def dashboard_overview_payload(scan_path):
    """Read the persisted Daily scan envelope for the progressive dashboard."""
    with open(scan_path) as handle:
        scan = json.load(handle)
    return scan


def us_watchlist_overview_payload(scan_path):
    """Return the curated US payload without joining chart/history/profile data.

    The US scan file is the single source of truth for its own provenance:
    it carries scan_time at the envelope and per-row.  We surface scan_time
    as root-level data_fetched_at (max of per-row scan_time) so the US page
    has the same provenance contract shape as the TH dashboard snapshot.

    Freshness is computed via the centralized P0 contract (provenance_contract)
    using the same INTRADAY_STALE_HOURS threshold as the TH dashboard — the US
    page never hardcodes "unknown" for a fetch timestamp it actually received.
    """
    with open(scan_path) as handle:
        payload = json.load(handle)
    cards = payload.get("results", [])
    # data_fetched_at: the most recent per-symbol scan_time from the US file.
    # Falls back to the envelope scan_time if per-row timestamps are missing.
    row_times = [row.get("scan_time") for row in cards if row.get("scan_time")]
    data_fetched_at = max(row_times) if row_times else payload.get("scan_time")
    freshness_status = compute_freshness(data_fetched_at)
    return {"universe": payload.get("universe"), "market": "US",
            "benchmark": payload.get("benchmark_symbol"), "source": payload.get("source"),
            "scan_time": payload.get("scan_time"),
            "data_fetched_at": data_fetched_at,
            "data_freshness_source": payload.get("source"),
            "data_freshness_status": freshness_status,
            "cards": [{"symbol": row["symbol"], "close": row.get("close")}
                      for row in cards]}


def _load_dashboard_cache() -> dict:
    """Load the persisted dashboard artifact without DB joins or rescanning."""
    cache_path = os.path.join(os.path.dirname(__file__), "dashboard_snapshot.json")
    try:
        with open(cache_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=f"dashboard cache unavailable: {exc}")
    if not isinstance(payload.get("items"), list):
        raise HTTPException(status_code=503, detail="dashboard cache has no items list")
    return payload


@app.get("/dashboard/overview")
def dashboard_overview():
    """Small dashboard metadata response for fast initial page load."""
    payload = _load_dashboard_cache()
    coverage = {}
    coverage_path = os.path.join(os.path.dirname(__file__), "coverage_report.json")
    try:
        with open(coverage_path, encoding="utf-8") as handle:
            report = json.load(handle)
        coverage = {
            "architecture_declared_universe_count": report.get("architecture_declared_universe_count"),
            "database": report.get("database", {}),
            "scan_count": report.get("scan", {}).get("count"),
            "dashboard_count": report.get("dashboard", {}).get("count"),
            "legacy_taxonomy_count": report.get("legacy_taxonomy", {}).get("count"),
            "scan_not_in_dashboard_count": len(report.get("lineage", {}).get("scan_not_in_dashboard", [])),
        }
    except (OSError, json.JSONDecodeError):
        # coverage_report.json is a generated/optional artifact. Keep the API
        # contract usable from the dashboard snapshot instead of returning a
        # shape that forces clients/tests to special-case missing keys.
        coverage = {
            "status": "coverage_report_unavailable",
            "dashboard_count": len(payload.get("items", [])),
            "scan_count": len(payload.get("items", [])),
            "legacy_taxonomy_count": None,
            "scan_not_in_dashboard_count": 0,
        }
    items = payload["items"]
    return {
        "scan_time": payload.get("scan_time"),
        "build_timestamp": payload.get("build_timestamp"),
        "market": payload.get("market", "TH"),
        "refresh": payload.get("refresh"),
        "count": len(items),
        "stage_meta": payload.get("stage_meta", {}),
        "stage_counts": payload.get("stage_counts", {}),
        "projection_version": payload.get("projection_version"),
        "coverage": coverage,
    }


# --- Compact card fields for lightweight first paint ---
# These are the ONLY fields the overview needs to render before detail/chart loads.
# Any field not listed here is "unknown" until the detail view requests it.
COMPACT_CARD_FIELDS = (
    "symbol", "close", "date", "stage", "phase", "phase_label",
    "group", "action", "actionReason", "breakoutLevel", "stop", "cut",
    "priceSource", "priceLabel", "stale", "intradaySource", "intradayStale",
    "intent", "status", "tone", "volume", "tradeValue",
    "layer2_group", "intradayFreshness", "dataFreshness",
)


def _compact_card(item: dict, market: str = "unknown") -> dict:
    """Project a full card to the compact overview contract.

    Missing enrichment fields become explicit 'unknown' so the UI never
    misinterprets absence as a negative signal.  ``market`` is authoritative
    at the payload root (same universe for all cards), so it is injected
    explicitly rather than guessed per item.
    """
    out = {}
    for f in COMPACT_CARD_FIELDS:
        out[f] = item.get(f)
        if out[f] is None:
            out[f] = "unknown"
    # market: one canonical market per response; never guess from item absence
    out["market"] = item.get("market", market)
    # scan_time and data_fetched_at come from root, not per-card
    return out


def _load_dashboard_cache() -> dict:
    """Load the persisted dashboard artifact without DB joins or rescanning."""
    cache_path = os.path.join(os.path.dirname(__file__), "dashboard_snapshot.json")
    try:
        with open(cache_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=f"dashboard cache unavailable: {exc}")
    if not isinstance(payload.get("items"), list):
        raise HTTPException(status_code=503, detail="dashboard cache has no items list")
    return payload


@app.get("/dashboard/cards")
def dashboard_cards(stage: str | None = None, l2: str | None = None,
                    page: int = 1, page_size: int = 50):
    """Return bounded card pages from the persisted dashboard artifact.

    This endpoint is deliberately read-only and uses the same serialized card
    contract as the existing snapshot endpoint.  Filters are applied before
    pagination so the UI can request one Stage/L2 subgroup at a time.
    """
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if page_size < 1 or page_size > 200:
        raise HTTPException(status_code=400, detail="page_size must be between 1 and 200")
    valid_stages = {"S1_basing", "S2_uptrend", "S3_distributing", "S4_down"}
    valid_l2 = {"up_leg", "pullback", "tight_base", "down_leg", "bounce"}
    if stage and stage not in valid_stages:
        raise HTTPException(status_code=400, detail=f"unsupported stage: {stage}")
    if l2 and l2 not in valid_l2:
        raise HTTPException(status_code=400, detail=f"unsupported l2: {l2}")
    payload = _load_dashboard_cache()
    items = [item for item in payload["items"]
             if (not stage or item.get("stage") == stage)
             and (not l2 or item.get("layer2_group") == l2)]
    start = (page - 1) * page_size
    cards = items[start:start + page_size]
    return {
        "scan_time": payload.get("scan_time"),
        "stage": stage,
        "l2": l2,
        "page": page,
        "page_size": page_size,
        "total": len(items),
        "cards": cards,
    }


@app.get("/dashboard/cards/compact")
def dashboard_cards_compact(stage: str | None = None, l2: str | None = None,
                            page: int = 1, page_size: int = 50):
    """Return lightweight compact cards for first paint.

    Returns ONLY the core fields needed for overview rendering.  Enrichment
    (history, profile, MA/EMA, ATH, risk/R, breakoutEvidence, etc.) is
    explicitly 'unknown' until the detail view loads via /dashboard/cards.

    Mobile resilience: if the refresh call fails, the previously cached
    compact cards remain visible — the UI never clears the grid on error.
    """
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if page_size < 1 or page_size > 200:
        raise HTTPException(status_code=400, detail="page_size must be between 1 and 200")
    valid_stages = {"S1_basing", "S2_uptrend", "S3_distributing", "S4_down"}
    valid_l2 = {"up_leg", "pullback", "tight_base", "down_leg", "bounce"}
    if stage and stage not in valid_stages:
        raise HTTPException(status_code=400, detail=f"unsupported stage: {stage}")
    if l2 and l2 not in valid_l2:
        raise HTTPException(status_code=400, detail=f"unsupported l2: {l2}")
    payload = _load_dashboard_cache()
    items = [item for item in payload["items"]
             if (not stage or item.get("stage") == stage)
             and (not l2 or item.get("layer2_group") == l2)]
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]
    market = payload.get("market", "TH")
    dashboard_meta = payload.get("dashboard_meta", {})
    compact = [_compact_card(item, market=market) for item in page_items]
    return {
        "scan_time": payload.get("scan_time"),
        "build_timestamp": payload.get("build_timestamp"),
        "data_fetched_at": payload.get("data_fetched_at") or dashboard_meta.get("data_fetched_at"),
        "data_freshness_source": payload.get("data_freshness_source") or dashboard_meta.get("data_freshness_source"),
        "data_freshness_status": payload.get("data_freshness_status") or dashboard_meta.get("data_freshness_status"),
        "data_intraday_status": payload.get("data_intraday_status"),
        "data_global_status": payload.get("data_global_status"),
        "market_session": payload.get("market_session") or dashboard_meta.get("market_session"),
        "last_valid_session": payload.get("last_valid_session") or (dashboard_meta.get("market_session") or {}).get("last_valid_session"),
        "data_freshness_age_hours": payload.get("data_freshness_age_hours"),
        "dashboard_meta": dashboard_meta,
        "market": payload.get("market", "TH"),
        "stage": stage,
        "l2": l2,
        "page": page,
        "page_size": page_size,
        "total": len(items),
        "cards": compact,
    }


def _active_intraday_events(items):
    """Collect non-null intradayEventEvidence fields from serialized cards.

    Returns a list of symbol-keyed evidence dicts for cards carrying an active
    emerging/confirmed intraday breakout event. Each entry exposes the source
    (intraday_run_id), freshness (intraday_candle_at/stale), and baseline
    (daily_close/daily_date) lineage required by the P0 reconciliation contract.
    """
    out = []
    for item in items:
        evidence = item.get("intradayEventEvidence")
        if evidence:
            out.append({
                "symbol": item.get("symbol"),
                "confidence": evidence.get("confidence"),
                "origin": evidence.get("origin"),
                "trigger_price": evidence.get("trigger_price"),
                "failure_level": evidence.get("failure_level"),
                "first_seen": evidence.get("first_seen"),
                "first_candle_ts": evidence.get("first_candle_ts"),
                "interval": evidence.get("interval"),
                "intraday_run_id": evidence.get("intraday_run_id"),
                "resolved_daily_event_id": evidence.get("resolved_daily_event_id"),
                "reconciled_at": evidence.get("reconciled_at"),
                "baseline_close": evidence.get("baseline_close"),
                "baseline_date": evidence.get("baseline_date"),
                "intraday_close": evidence.get("intraday_close"),
                "intraday_candle_at": evidence.get("intraday_candle_at"),
                "stale": evidence.get("stale"),
            })
    return out


@app.get("/dashboard/shortlist")
def dashboard_shortlist():
    """Compact, cached Daily Shortlist — read-only, no scan/DB/chart/history.

    Loads the persisted dashboard_snapshot.json artifact (via
    ``_load_dashboard_cache``), projects each serialized card through
    ``daily_shortlist.project_shortlist``, and returns only eligible READY /
    PRE-READY candidates plus exact root freshness / market_session / policy /
    total fields.

    Never rescans, never queries the database, never fetches charts/history,
    and never mutates snapshot data.  A missing or corrupt cache yields HTTP 503.
    """
    payload = _load_dashboard_cache()
    from daily_shortlist import project_shortlist, POLICY_VERSION
    candidates = project_shortlist(payload.get("items", []))
    dashboard_meta = payload.get("dashboard_meta", {})
    return {
        "scan_time": payload.get("scan_time"),
        "data_fetched_at": payload.get("data_fetched_at") or dashboard_meta.get("data_fetched_at"),
        "data_freshness_source": payload.get("data_freshness_source") or dashboard_meta.get("data_freshness_source"),
        "data_freshness_status": payload.get("data_freshness_status") or dashboard_meta.get("data_freshness_status"),
        "market_session": payload.get("market_session") or dashboard_meta.get("market_session"),
        "policy_version": POLICY_VERSION,
        "total": len(candidates),
        "candidates": candidates,
    }


@app.get("/dashboard/shortlist/compact")
def dashboard_shortlist_compact(page: int = 1, page_size: int = 20,
                                publication_state: str | None = None):
    """Read-only, paginated compact shortlist for Explorer on-demand loading.

    Returns a bounded page of shortlist candidates projected through the same
    compact contract as /dashboard/shortlist, but paginated so the Explorer
    never embeds the full universe on first paint.  Never rescans, never
    queries the database, never fetches charts/history.  A missing or corrupt
    cache yields HTTP 503.

    ``publication_state`` may filter to READY or PRE_READY only.
    """
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="page_size must be between 1 and 100")
    valid_states = {"READY", "PRE_READY", None}
    if publication_state and publication_state not in {"READY", "PRE_READY"}:
        raise HTTPException(status_code=400, detail=f"unsupported publication_state: {publication_state}")
    payload = _load_dashboard_cache()
    from daily_shortlist import (
        project_shortlist, project_shortlist_lanes, POLICY_VERSION,
        LANE_POLICY_VERSION,
    )
    candidates = project_shortlist(payload.get("items", []))
    if publication_state:
        candidates = [c for c in candidates if c["publication_state"] == publication_state]
    start = (page - 1) * page_size
    page_items = candidates[start:start + page_size]
    dashboard_meta = payload.get("dashboard_meta", {})

    # Lane projection (Task C): canonical three-lane contract. Extended names
    # are visible in LEADERSHIP_EXTENDED only; never READY. When filtering to
    # READY/PRE_READY, the extended lane is intentionally empty.
    lanes = project_shortlist_lanes(payload.get("items", []))
    if publication_state == "READY":
        lanes["PREPARE"] = []
        lanes["LEADERSHIP_EXTENDED"] = []
    elif publication_state == "PRE_READY":
        lanes["REVIEW_NOW"] = []
        lanes["LEADERSHIP_EXTENDED"] = []
    else:
        # No filter: paginate per lane with the same page window.
        for lane in lanes:
            lanes[lane] = lanes[lane][start:start + page_size]
    return {
        "scan_time": payload.get("scan_time"),
        "data_fetched_at": payload.get("data_fetched_at") or dashboard_meta.get("data_fetched_at"),
        "data_freshness_source": payload.get("data_freshness_source") or dashboard_meta.get("data_freshness_source"),
        "data_freshness_status": payload.get("data_freshness_status") or dashboard_meta.get("data_freshness_status"),
        "market_session": payload.get("market_session") or dashboard_meta.get("market_session"),
        "policy_version": POLICY_VERSION,

        "lane_policy_version": LANE_POLICY_VERSION,
        "publication_state": publication_state,
        "page": page,
        "page_size": page_size,
        "total": len(candidates),
        "count": len(page_items),
        "candidates": page_items,

        "lanes": lanes,
    }


@app.get("/dashboard/snapshot")
def dashboard_snapshot():
    """Retired legacy contract; the MVP uses /api/vcp-finder instead."""
    raise HTTPException(status_code=410, detail="legacy dashboard snapshot retired; use /api/vcp-finder")


@app.get("/watchlists/us-ai-buildout")
def us_ai_buildout_watchlist():
    """Small, file-backed US theme snapshot; deliberately avoids Thai dashboard queries."""
    path = os.path.join(os.path.dirname(__file__), "us_ai_buildout_scan.json")
    try:
        payload = us_watchlist_overview_payload(path)
        # The dedicated US page needs its compact technical card fields, but no
        # chart/profile/history joins; those remain lazy requests.
        with open(path) as handle:
            raw = json.load(handle)
        payload["cards"] = [{
            "symbol": row["symbol"], "close": row.get("close"), "last_date": row.get("last_date"),
            "tt": row.get("trend_template", {}).get("conditions_met"),
            "rs": row.get("trend_template", {}).get("rs_rating"),
            "rsi": row.get("trade_readiness", {}).get("rsi_daily"),
            "status": row.get("trade_readiness", {}).get("status"),
            "trigger": row.get("trade_readiness", {}).get("breakout_level_20d"),
            "stop": row.get("suggested_stop"), "vcp": row.get("vcp", {}).get("is_vcp"), "market": "US",
        } for row in raw.get("results", [])]
        return payload
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="US AI Buildout scan has not run")


@app.get("/intraday/transitions")
def intraday_transitions(limit: int = 30):
    """Recent deterministic intraday action-state transitions; no LLM or live fetch."""
    from intraday_evaluator import recent_transitions
    return {"transitions": recent_transitions(limit)}


@app.post("/intraday/evaluate")
def intraday_evaluate(mode: str, interval: str):
    """Re-evaluate stored intraday prices against Daily reference levels."""
    from intraday_evaluator import evaluate
    try:
        return evaluate(mode, interval)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/intraday/events")
def intraday_events(confidence: str | None = None):
    """Active intraday emerging/confirmed events (append-only, lower confidence).

    Each event carries the resolved_daily_event_id lineage when the EOD scan
    has confirmed it; the Daily baseline remains the official final class.
    """
    from scan_history import get_active_intraday_events
    pg = get_pg()
    try:
        return {"events": get_active_intraday_events(pg, confidence=confidence)}
    finally:
        pg.close()


def fetch_chart_rows(cur, symbol, timeframe, limit, market="TH"):
    """Return stored bars, rolling the latest 60m price into Day/Week/Month.

    The current-session Daily candle is provisional. Week and Month are derived
    strictly by aggregating those stored Daily bars—no additional market fetch.
    """
    if timeframe == "60M":
        if market.upper() != "TH":
            return [], "60-minute data is not configured for this market"
        cur.execute("""SELECT ts, open, high, low, close, volume,
                              (ROW_NUMBER() OVER (ORDER BY ts DESC) = 1) AS provisional
                       FROM intraday_price_data WHERE symbol=%s AND interval='60m'
                       ORDER BY ts DESC LIMIT %s""", (symbol, limit))
        return cur.fetchall(), "60-minute (latest candle may be in progress)"
    daily_limit = limit if timeframe == "1D" else min(limit * (25 if timeframe == "1M" else 5), 1500)
    cur.execute("""SELECT date::timestamp, open, high, low, close, volume, false AS provisional
                   FROM price_data WHERE market=%s AND symbol=%s ORDER BY date DESC LIMIT %s""",
                (market.upper(), symbol, daily_limit))
    daily = cur.fetchall()
    cur.execute("""SELECT ts, open, high, low, close, volume FROM intraday_price_data
                   WHERE symbol=%s AND interval='60m' AND (ts AT TIME ZONE 'Asia/Bangkok')::date = (NOW() AT TIME ZONE 'Asia/Bangkok')::date
                   ORDER BY ts ASC""", (symbol,))
    intra = cur.fetchall()
    if intra:
        stamp = intra[-1][0]
        today = stamp.astimezone(dt.timezone(dt.timedelta(hours=7))).date()
        # The stored Daily row for today may be stale or official. Replace it
        # for chart display with the latest current-session 60m aggregate; this
        # does not alter price_data or any Daily decision provenance.
        provisional = (dt.datetime.combine(today, dt.time()), intra[0][1], max(r[2] for r in intra),
                       min(r[3] for r in intra), intra[-1][4], sum(float(r[5] or 0) for r in intra), True)
        daily = [row for row in daily if row[0].date() != today]
        daily.append(provisional)
    has_provisional = bool(intra)
    daily.sort(key=lambda r: r[0], reverse=True)
    if timeframe == "1D":
        label = ("Daily EOD + provisional current session (60m as-is)"
                 if has_provisional else "Daily EOD (no current-session 60m data)")
        return daily[:limit], label
    # Aggregate Daily OHLCV into a higher period.  The first daily open and
    # latest daily close are retained; high/low/volume span the period.
    periods = {}
    for stamp, open_, high, low, close, volume, provisional in reversed(daily):
        day = stamp.date()
        key = day - dt.timedelta(days=day.weekday()) if timeframe == "1W" else day.replace(day=1)
        if key not in periods:
            periods[key] = [dt.datetime.combine(key, dt.time()), open_, high, low, close, float(volume or 0), bool(provisional)]
        else:
            p = periods[key]
            p[2] = max(p[2], high)
            p[3] = min(p[3], low)
            p[4] = close
            p[5] += float(volume or 0)
            p[6] = p[6] or bool(provisional)
    rows = list(reversed(sorted(periods.values(), key=lambda r: r[0])))[:limit]
    if timeframe == "1W":
        label = ("Weekly + provisional current session (60m as-is)"
                 if has_provisional else "Weekly Daily EOD (no current-session 60m data)")
    else:
        label = ("Monthly + provisional current session (60m as-is)"
                 if has_provisional else "Monthly Daily EOD (no current-session 60m data)")
    return rows, label


@app.get("/chart/{symbol}")
def chart_data(symbol: str, timeframe: str = "1D", limit: int = 180, market: str = "TH"):
    """Return stored market-scoped chart data; US currently exposes Daily only."""
    symbol = symbol.upper().strip()
    market = market.upper().strip()
    if market not in {"TH", "US"}:
        raise HTTPException(status_code=400, detail="market must be TH or US")
    timeframe = timeframe.upper().strip()
    if not symbol.isalnum() or len(symbol) > 16:
        raise HTTPException(status_code=400, detail="invalid symbol")
    aliases = {"D": "1D", "DAILY": "1D", "W": "1W", "WEEKLY": "1W", "M": "1M", "MONTHLY": "1M", "1H": "60M", "60M": "60M"}
    timeframe = aliases.get(timeframe, timeframe)
    if timeframe not in {"1M", "1W", "1D", "60M"}:
        raise HTTPException(status_code=400, detail="timeframe must be 1M, 1W, 1D, or 60m")
    limit = max(20, min(limit, 500))
    pg = get_pg(); cur = pg.cursor()
    rows, label = fetch_chart_rows(cur, symbol, timeframe, limit, market=market)
    cur.close()
    if not rows:
        raise HTTPException(status_code=404, detail=f"no stored {label} chart data")
    bars = [{"time": str(stamp), "open": float(open_), "high": float(high), "low": float(low),
             "close": float(close), "volume": float(volume or 0), "provisional": bool(provisional)}
            for stamp, open_, high, low, close, volume, provisional in reversed(rows)]
    return {"symbol": symbol, "timeframe": timeframe, "label": label,
            "latest_time": bars[-1]["time"], "provisional": bars[-1]["provisional"],
            "provenance": {
                "source": "price_data + intraday_price_data" if has_provisional else "price_data",
                "intraday_current_session": has_provisional,
                "daily_decision_source": "price_data EOD",
                "note": ("current-session 60m aggregate is provisional/as-is; not official EOD"
                         if has_provisional else "no current-session 60m data; Daily EOD bars shown"),
            }, "bars": bars}


@app.post("/scan")
def run_scan(
    min_conditions: int = 8,
    limit: int = 0,
    push: bool = True,
    retry_of_run_id: str | None = None,
):
    """Scan the active universe; publish every candidate to Redis.

    min_conditions: bar for a candidate (Minervini wants 8/8; lower = watchlist).
    limit: 0 = all candidates.
    push: if True, also push a Telegram summary with the dashboard link.
    Dashboard HTML is rebuilt on every scan, even when push=false.
    retry_of_run_id: explicit UUID of the persisted parent run for a retry.
    """
    try:
        # Evaluate every active ORD with sufficient history. Each one is placed
        # in a visible group, including falling and consolidating names.
        scanned, near = scan_universe(min_conditions=0, limit=limit or None)
        pg = get_pg()
        try:
            events = active_breakout_events(pg)
        finally:
            pg.close()
        groups = group_scan_results(scanned, events=events)
        for row in scanned:
            if row["symbol"] in events:
                row["active_breakout_event"] = events[row["symbol"]]
        # The canonical Daily as-of must come from the official price_data
        # boundary, never from a benchmark/current-session row in scan output.
        eod_pg = get_pg()
        try:
            eod_cur = eod_pg.cursor()
            eod_cur.execute("SELECT MAX(date) FROM price_data WHERE market='TH'")
            eod_row = eod_cur.fetchone()
            eod_cur.close()
        finally:
            eod_pg.close()
        official_eod_date = eod_row[0].isoformat() if eod_row and eod_row[0] else None
        latest_market_dates = [official_eod_date] if official_eod_date else []
        pg = get_pg()
        try:
            snapshot = persist_daily_scan_snapshot(
                pg,
                scanned,
                scan_date=dt.date.fromisoformat(latest_market_dates[-1]) if latest_market_dates else None,
                scanner_version="signalix/daily-state-v2",
                source_lineage={
                    "source": "price_data",
                    "freshness": "daily_eod_archive",
                    "market_benchmark": "SET",
                    "evaluated_market_dates": latest_market_dates,
                },
                retry_of_run_id=retry_of_run_id,
            )
        finally:
            pg.close()

        # Persist market regime for this scan run (Contract v0.2.0 §3)
        run_id = snapshot["run_id"]
        pg = get_pg()
        try:
            # The regime is already attached to each symbol in scanned by scan_universe
            # Extract from the first symbol that has it
            regime_data = None
            for row in scanned:
                if row.get("market_regime"):
                    regime_data = row["market_regime"]
                    break
            if regime_data:
                from scan_history import persist_market_regime
                persist_market_regime(
                    pg,
                    run_id=run_id,
                    regime_state=regime_data.get("regime_state", "NORMAL"),
                    atr_pct_20d=regime_data.get("inputs", {}).get("atr_pct_20d"),
                    median_spread_bps=regime_data.get("inputs", {}).get("median_spread_bps"),
                    liquidity_event_flag=regime_data.get("inputs", {}).get("liquidity_event_flag"),
                    breadth_pct_above_ma50=regime_data.get("inputs", {}).get("breadth_pct_above_ma50"),
                    benchmark_at_or_above_ma50=regime_data.get("inputs", {}).get("benchmark_at_or_above_ma50"),
                    liquidity_event_reason_codes=regime_data.get("liquidity_event_reason_codes", []),
                    reason_codes=regime_data.get("reason_codes", []),
                    policy_version=regime_data.get("policy_version", "regime-v0.2.0"),
                    data_timestamp_utc=regime_data.get("data_timestamp_utc"),
                )
        finally:
            pg.close()

        pg = get_pg()
        try:
            lifecycle = persist_breakout_lifecycle(pg, scanned, snapshot["run_id"], "signalix/daily-state-v2")
        finally:
            pg.close()
        
        # EOD reconciliation: promote intraday emerging events to Daily events
        pg = get_pg()
        try:
            reconciliation = reconcile_intraday_events_at_eod(
                pg, snapshot["run_id"], "signalix/daily-state-v2",
                symbols=[row["symbol"] for row in scanned]
            )
            print(f"Intraday event reconciliation: {reconciliation}")
        finally:
            pg.close()
        
        # Only actionable states publish signals; structure/no-long stay dashboard-only.
        cands = groups.get("breakout_new", []) + groups.get("uptrend_pullback", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"scan failed: {e}")
    for c in cands:
        _publish_screen(c, min_conditions)
    # Persist all 7/8 scan rows plus their display groups for the dashboard.
    _write_scan_json(scanned, near, groups)
    url = None
    if push:
        from datetime import datetime as _dt
        url = build_and_push_summary(cands, near, _dt.utcnow().isoformat(), scanned, run_id=snapshot["run_id"])
    else:
        try:
            import build_dashboard
            build_dashboard.build(scanned=scanned, run_id=snapshot["run_id"])
        except Exception as e:
            print(f"  ! dashboard build failed: {repr(e)[:120]}")
    return {"status": "scanned", "min_conditions": min_conditions,
            "candidates": len(cands), "near_miss": len(near),
            "symbols": [c["symbol"] for c in cands],
            "dashboard_url": url}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
