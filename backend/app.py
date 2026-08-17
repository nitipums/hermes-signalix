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
    allow_headers=["X-Portfolio-Token"],
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
        from users import init_user_schema
        init_user_schema()
        from portfolio import init_portfolio_schema
        init_portfolio_schema(get_pg())
    except Exception as e:
        print(f"  ! schema init failed: {repr(e)[:120]}")

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


# ---------- Investment Co-pilot MVP (owner-only) ----------
def _portfolio_owner(chat_id: str, owner_token: str) -> int:
    expected = os.getenv("PORTFOLIO_OWNER_TOKEN", "")
    # The bearer token is bound to the configured beta owner; never let callers
    # select a portfolio merely by supplying a different chat_id.
    bound_owner_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    from portfolio import require_owner_identity
    if not require_owner_identity(owner_token, expected, str(chat_id), bound_owner_chat_id):
        raise HTTPException(status_code=403, detail="portfolio access denied")
    pg = get_pg(); cur = pg.cursor()
    cur.execute("SELECT id, tier FROM users WHERE telegram_chat_id=%s", (bound_owner_chat_id,))
    row = cur.fetchone(); cur.close()
    if not row or row[1] != "owner":
        raise HTTPException(status_code=403, detail="portfolio owner account required")
    return row[0]


@app.post("/portfolio/documents")
async def portfolio_document(
    chat_id: str = Form(...), broker: str = Form(...), account_alias: str = Form(...),
    pdf: UploadFile = File(...), pdf_password: str = Form(""),
    x_portfolio_token: str = Header(default=""),
):
    """Owner-only PDF intake. Password is used in memory only and never persisted."""
    user_id = _portfolio_owner(chat_id, x_portfolio_token)
    if broker not in {"innovestx_derivatives", "krungsri_equity"}:
        raise HTTPException(status_code=400, detail="unsupported broker parser")
    if not account_alias or len(account_alias) > 64 or not re.fullmatch(r"[a-z0-9_-]+", account_alias):
        raise HTTPException(status_code=400, detail="invalid account alias")
    if not (pdf.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF required")
    data = await pdf.read()
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="empty or oversized PDF")
    from portfolio import document_hash, parse_document, persist_parsed
    try:
        parsed = parse_document(data, broker, account_alias, pdf_password or None)
        result = persist_parsed(get_pg(), user_id, parsed, document_hash(data))
        return {**result, "broker": parsed["broker"], "account_alias": account_alias,
                "trade_date": parsed["trade_date"]}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/portfolio/snapshots")
async def portfolio_snapshot(request: Request, chat_id: str, x_portfolio_token: str = Header(default="")):
    """Owner-only manual/screenshot holding snapshot intake.

    Screenshots are observation snapshots, not ledger transactions; the payload
    must already be reviewed by the owner/assistant before import.
    """
    user_id = _portfolio_owner(chat_id, x_portfolio_token)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="snapshot payload required")
    for key in ("broker", "account_alias", "account_type", "as_of", "holdings"):
        if key not in payload:
            raise HTTPException(status_code=400, detail=f"missing {key}")
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", payload["account_alias"]):
        raise HTTPException(status_code=400, detail="invalid account alias")
    if not isinstance(payload.get("holdings"), list) or len(payload["holdings"]) > 200:
        raise HTTPException(status_code=400, detail="invalid holdings list")
    from portfolio import persist_manual_snapshot
    try:
        return persist_manual_snapshot(user_id, payload)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/portfolio/me")
def portfolio_me(chat_id: str, x_portfolio_token: str = Header(default="")):
    """Owner-only safe summary; no raw account numbers or source documents are returned."""
    user_id = _portfolio_owner(chat_id, x_portfolio_token)
    from portfolio import portfolio_summary
    return portfolio_summary(user_id)


@app.get("/portfolio/health")
def portfolio_health_route(chat_id: str, x_portfolio_token: str = Header(default="")):
    """Owner-only Monitor/Inspect account-health contract for the cockpit."""
    user_id = _portfolio_owner(chat_id, x_portfolio_token)
    from portfolio import portfolio_health
    return portfolio_health(user_id)


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


# ---------- Phase 3 delivery (shared with the real-time consumer) ----------
from screening import analyze_symbol_db, analyze_symbol_db_ranked, scan_universe, group_scan_results  # noqa: E402
from scan_history import persist_daily_scan_snapshot, active_breakout_events, persist_breakout_lifecycle  # noqa: E402
# All senders + formatters live in delivery.py so the batch scan (here) and the
# standalone Redis consumer format + push identically.
from delivery import push_telegram, DASHBOARD_PUBLIC_URL  # noqa: E402

# Webhook shared-secret gate. When set, /webhook requires it (header
# X-Webhook-Secret or ?secret=). Leave empty to accept any POST — NOT
# recommended while port 8000 is exposed publicly.
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


def build_and_push_summary(cands, near, scan_time):
    """Build the dashboard HTML, then push a summary + link to Telegram."""
    # build dashboard (runs build_dashboard.build in-process)
    try:
        import build_dashboard
        info = build_dashboard.build()
        vcp_n = info["vcp"]
    except Exception as e:
        print(f"  ! dashboard build failed: {repr(e)[:120]}")
        vcp_n = sum(1 for c in cands if c.get("vcp", {}).get("is_vcp"))
    url = DASHBOARD_PUBLIC_URL.rstrip("/") + "/dashboard.html" if DASHBOARD_PUBLIC_URL else ""
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
    """
    try:
        result = analyze_symbol_db_ranked(symbol.upper())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"screen failed: {e}")
    if result is None:
        raise HTTPException(status_code=404,
                            detail=f"{symbol} not found or insufficient history")
    _publish_screen(result, result["trend_template"]["conditions_met"])
    return result


def dashboard_overview_payload(scan_path):
    """Read the persisted Daily scan envelope for the progressive dashboard."""
    with open(scan_path) as handle:
        scan = json.load(handle)
    return scan


def us_watchlist_overview_payload(scan_path):
    """Return the curated US payload without joining chart/history/profile data."""
    with open(scan_path) as handle:
        payload = json.load(handle)
    return {"universe": payload.get("universe"), "market": "US",
            "benchmark": payload.get("benchmark_symbol"), "source": payload.get("source"),
            "cards": [{"symbol": row["symbol"], "close": row.get("close")}
                      for row in payload.get("results", [])]}


@app.get("/dashboard/snapshot")
def dashboard_snapshot():
    """Progressive refresh: return the complete persisted scan card contract.

    The browser swaps these cards in without rebuilding the static asset.  The
    DB work is set-based (same path as build_dashboard), and no Daily state or
    scan membership is changed here.
    """
    try:
        import build_dashboard
        from reconciled_projection import apply_projection, snapshot_payload
        scan_path = os.path.join(os.path.dirname(__file__), "scan_results.json")
        scan = dashboard_overview_payload(scan_path)
        last_valid_session = max((row.get("last_date") for values in scan.get("groups", {}).values()
                                  for row in values if row.get("last_date")), default=None)
        try:
            freshness_pg = build_dashboard.get_pg()
            try:
                freshness = build_dashboard.dashboard_freshness(freshness_pg, last_valid_session=last_valid_session)
            finally:
                freshness_pg.close()
        finally:
            pass
        cache_path = os.path.join(os.path.dirname(__file__), "dashboard_snapshot.json")
        try:
            with open(cache_path) as handle:
                payload = json.load(handle)
            if payload.get("scan_time") != scan.get("scan_time"):
                raise ValueError("snapshot cache is not for latest scan")
            payload["items"] = apply_projection(payload.get("items", []))
            payload.update(snapshot_payload(payload["items"], scan.get("scan_time")))
        except (OSError, ValueError, json.JSONDecodeError):
            # Safe fallback for a scan generated before the cache artifact was
            # introduced; normal deploys/builds never take this slow path.
            pg_fallback = get_pg()
            try:
                fallback_items = build_dashboard.snapshot_items(pg_fallback, scan)
            finally:
                pg_fallback.close()
            payload = {"scan_time": scan.get("scan_time"), "market": "TH",
                       "refresh": "progressive_cards", "items": fallback_items}
            payload.update(snapshot_payload(payload["items"], scan.get("scan_time")))
        return {**payload,
                "data_fetched_at": freshness["data_fetched_at"],
                "data_freshness_source": freshness["source"],
                "data_freshness_status": freshness["status"],
                "data_intraday_status": freshness.get("intraday_status"),
                "data_global_status": freshness.get("global_status"),
                "market_session": freshness.get("market_session"),
                "last_valid_session": (freshness.get("market_session") or {}).get("last_valid_session"),
                "data_freshness_age_hours": freshness.get("age_hours")}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"dashboard snapshot unavailable: {exc}")


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


def fetch_chart_rows(cur, symbol, timeframe, limit, market="TH"):
    """Return stored bars, rolling the latest 60m price into Day/Week/Month.

    The current-session Daily candle is provisional. Week and Month are derived
    strictly by aggregating those stored Daily bars—no additional market fetch.
    """
    if timeframe == "60M":
        if market.upper() != "TH":
            return [], "60-minute data is not configured for this market"
        cur.execute("""SELECT ts, open, high, low, close, volume, false AS provisional
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
        # Avoid duplicate EOD/provisional day: EOD is authoritative when already present.
        if not daily or daily[0][0].date() != today:
            provisional = (dt.datetime.combine(today, dt.time()), intra[0][1], max(r[2] for r in intra),
                           min(r[3] for r in intra), intra[-1][4], sum(float(r[5] or 0) for r in intra), True)
            daily.append(provisional)
    daily.sort(key=lambda r: r[0], reverse=True)
    if timeframe == "1D":
        return daily[:limit], "Daily EOD + current session (in progress)"
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
    label = "Weekly + current week (in progress)" if timeframe == "1W" else "Monthly + current month (in progress)"
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
            "latest_time": bars[-1]["time"], "provisional": bars[-1]["provisional"], "bars": bars}


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
        # Persist the complete deterministic evaluator output before filtering
        # delivery candidates. This captures monitor/risk names too.
        latest_market_dates = sorted({row.get("last_date") for row in scanned if row.get("last_date")})
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
        pg = get_pg()
        try:
            lifecycle = persist_breakout_lifecycle(pg, scanned, snapshot["run_id"], "signalix/daily-state-v2")
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
        url = build_and_push_summary(cands, near, _dt.utcnow().isoformat())
    else:
        try:
            import build_dashboard
            build_dashboard.build(scanned=scanned)
        except Exception as e:
            print(f"  ! dashboard build failed: {repr(e)[:120]}")
    return {"status": "scanned", "min_conditions": min_conditions,
            "candidates": len(cands), "near_miss": len(near),
            "symbols": [c["symbol"] for c in cands],
            "dashboard_url": url}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
