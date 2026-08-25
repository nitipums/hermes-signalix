"""Signalix professional screening workspace (English-only, no chart images)."""
import html
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote
from zoneinfo import ZoneInfo

import psycopg2
from reconciled_projection import PRIMARY_GROUPS, PRIMARY_META, apply_projection, snapshot_payload
from artifact_writer import atomic_write_json, atomic_write_text, write_artifact_manifest
from mvp_snapshot import build_mvp_snapshot, daily_freshness_from_run
from stage_classifier import STAGE_LABELS, PHASE_LABELS

try:
    from set_market_day_guard import SET_CLOSED_DATES
except ImportError:  # pragma: no cover - allows isolated module import
    SET_CLOSED_DATES = {}

PG_DSN = {"host": os.getenv("POSTGRES_HOST", "127.0.0.1"), "port": os.getenv("POSTGRES_PORT", "5432"),
          "user": os.getenv("POSTGRES_USER", "signalix"), "password": os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
          "dbname": os.getenv("POSTGRES_DB", "signalix")}
MARKET_SESSION_TIMEZONE = "Asia/Bangkok"
MARKET_SESSION_SOURCE = "set_market_day_guard"
HERE = os.path.dirname(os.path.abspath(__file__))
SCAN_JSON = os.path.join(HERE, "scan_results.json")
OUT_HTML = os.path.join(HERE, "dashboard.html")
SNAPSHOT_JSON = os.path.join(HERE, "dashboard_snapshot.json")
GROUPS = (
    ("breakout_new", "เบรกใหม่", "opportunity", "positive", "Daily breakout cycle ยังทำงานอยู่; ดู stage และรอ 1H confirmation"),
    ("uptrend_pullback", "ย่อในขาขึ้น", "opportunity", "positive", "ย่อเข้าสู่ Fib/MA support ใน trend ที่ยังไม่เสีย; รอแรงรับยืนยัน"),
    ("waiting_breakout", "รอเบรก", "prepare", "accent", "trend หรือฐานยังไม่หลุด; รอ trigger/volume ยืนยัน"),
    ("base", "สร้างฐาน", "monitor", "neutral", "กำลังสะสมตัว; รอ trigger ชัดเจน"),
    ("down_or_broken", "ขาลง / หลุด", "risk", "danger", "โครงสร้างอ่อนหรือหลุด; ไม่เปิด long ใหม่"),
)
GROUP_BY_KEY = {g[0]: g for g in GROUPS}


def _json_default(value):
    """Serialize DB-native numeric/time values without leaking Decimal to JSON."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def get_pg():
    return psycopg2.connect(**PG_DSN)


def market_session_status(now=None, last_valid_session=None):
    """Return deterministic SET session state for freshness interpretation.

    Wall-clock age is still reported for the 60m candle, but a closed/holiday
    session must not turn the absence of a new fetch into a global alarm.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(ZoneInfo(MARKET_SESSION_TIMEZONE))
    date = local.date().isoformat()
    base = {"timezone": MARKET_SESSION_TIMEZONE, "source": MARKET_SESSION_SOURCE,
            "date": date, "last_valid_session": last_valid_session}
    if local.weekday() >= 5:
        return {**base, "status": "market_closed", "is_open": False, "reason": "weekend"}
    if date in SET_CLOSED_DATES:
        return {**base, "status": "market_closed", "is_open": False,
                "reason": "holiday", "holiday": SET_CLOSED_DATES[date]}
    minutes = local.hour * 60 + local.minute
    is_open = (10 * 60 + 15 <= minutes < 12 * 60 + 30 or
               14 * 60 + 45 <= minutes < 16 * 60 + 30)
    return {**base, "status": "open_session" if is_open else "market_closed",
            "is_open": is_open, "reason": "open" if is_open else "outside_session"}


def dashboard_freshness(pg, now=None, last_valid_session=None):
    """Separate intraday candle age from global fetch freshness/session state."""
    unknown = {
        "data_fetched_at": None,
        "display": "Unknown / Stale",
        "source": "unknown",
        "status": UNKNOWN,
        "intraday_status": "unknown_stale",
        "global_status": UNKNOWN,
        "market_session": market_session_status(now, last_valid_session),
        "age_hours": None,
    }
    cur = pg.cursor()
    try:
        cur.execute("SELECT to_regclass('public.data_fetch_status')")
        if not cur.fetchone()[0]:
            return unknown
        cur.execute("""SELECT data_fetched_at, source FROM data_fetch_status
                       WHERE dataset='dashboard_intraday'""")
        row = cur.fetchone()
        if not row or not row[0]:
            return unknown
        fetched_at = row[0]
        if isinstance(fetched_at, str):
            fetched_at = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        fetched_at = fetched_at.astimezone(timezone.utc)
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (now.astimezone(timezone.utc) - fetched_at).total_seconds() / 3600.0)
        market = market_session_status(now, last_valid_session)
        intraday_status = FRESH if age_hours < _CONTRACT_STALE_HOURS else STALE
        global_status = FRESH if intraday_status == FRESH else STALE
        # Closed sessions intentionally suppress a global freshness alarm;
        # candle age remains independently visible and auditable.
        if market["status"] == "market_closed":
            global_status = "market_closed"
        return {
            "data_fetched_at": fetched_at.isoformat(),
            "display": fetched_at.astimezone(ZoneInfo("Asia/Bangkok")).strftime(
                "%d %b %Y %H:%M ICT (Bangkok)"
            ),
            "source": str(row[1] or "unknown"),
            "status": global_status,
            "intraday_status": intraday_status,
            "global_status": global_status,
            "market_session": market,
            "age_hours": round(age_hours, 3),
        }
    except (TypeError, ValueError, IndexError):
        return unknown
    finally:
        cur.close()


def fetch_market_regime(pg):
    """Fetch latest market regime from daily_market_regime table.

    Returns dict with regime_state, inputs, reason_codes, policy_version, timestamps.
    """
    cur = pg.cursor()
    try:
        # Join with daily_scan_runs to get the latest canonical run
        cur.execute("""
            SELECT mr.regime_state, mr.atr_pct_20d, mr.median_spread_bps,
                   mr.liquidity_event_flag, mr.breadth_pct_above_ma50,
                   mr.benchmark_at_or_above_ma50, mr.liquidity_event_reason_codes,
                   mr.reason_codes, mr.policy_version, mr.data_timestamp_utc,
                   mr.computed_at_utc, mr.run_id
            FROM daily_market_regime mr
            JOIN daily_scan_runs dr ON dr.id = mr.run_id
            JOIN daily_scan_run_selection_audit sa ON sa.run_id = dr.id
            WHERE sa.selection_status = 'selected'
            ORDER BY mr.data_timestamp_utc DESC NULLS LAST
            LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return {
                "regime_state": "NORMAL",
                "inputs": {
                    "atr_pct_20d": None,
                    "median_spread_bps": None,
                    "liquidity_event_flag": None,
                    "breadth_pct_above_ma50": None,
                    "benchmark_at_or_above_ma50": None,
                },
                "reason_codes": ["NO_REGIME_DATA"],
                "policy_version": "regime-v0.2.0",
                "data_timestamp_utc": None,
                "computed_at_utc": None,
                "run_id": None,
            }
        return {
            "regime_state": row[0],
            "inputs": {
                "atr_pct_20d": row[1],
                "median_spread_bps": row[2],
                "liquidity_event_flag": row[3],
                "breadth_pct_above_ma50": row[4],
                "benchmark_at_or_above_ma50": row[5],
            },
            "liquidity_event_reason_codes": row[6] or [],
            "reason_codes": row[7] or [],
            "policy_version": row[8],
            "data_timestamp_utc": row[9],
            "computed_at_utc": row[10],
            "run_id": str(row[11]) if row[11] else None,
        }
    except Exception as e:
        # If table doesn't exist or query fails, return default
        return {
            "regime_state": "NORMAL",
            "inputs": {
                "atr_pct_20d": None,
                "median_spread_bps": None,
                "liquidity_event_flag": None,
                "breadth_pct_above_ma50": None,
                "benchmark_at_or_above_ma50": None,
            },
            "reason_codes": [f"REGIME_FETCH_ERROR: {type(e).__name__}"],
            "policy_version": "regime-v0.2.0",
            "data_timestamp_utc": None,
            "computed_at_utc": None,
            "run_id": None,
        }
    finally:
        cur.close()


def _regime_badge_class(regime_state: str) -> str:
    """CSS class for regime badge styling."""
    return {
        "HIGH_VOLATILITY": "regime-high-vol",
        "LIQUIDITY_EVENT": "regime-liquidity-event",
        "LOW_SPREAD": "regime-low-spread",
        "NORMAL": "regime-normal",
    }.get(regime_state, "regime-normal")


def _regime_label(regime_state: str) -> str:
    """English label for regime badge (launch-ready requirement)."""
    return {
        "HIGH_VOLATILITY": "High Volatility",
        "LIQUIDITY_EVENT": "Liquidity Event",
        "LOW_SPREAD": "Low Spread",
        "NORMAL": "Normal",
    }.get(regime_state, "Normal")


def snapshots(pg, symbols):
    if not symbols:
        return {}
    cur = pg.cursor()
    # P0-2 instrument authority: join through symbol_master so the canonical
    # venue/asset_class/currency/timezone/session taxonomy is available, and
    # prefer the SET factsheet taxonomy source over the Yahoo fallback for
    # sector/industry. company_profiles is non-decision enrichment data only.
    cur.execute("""SELECT q.symbol,q.date,q.close,q.volume,q.rn,
                          cp.sector,cp.industry,cp.market_cap,
                          cp.free_float_pct,cp.foreign_limit_pct,cp.company_name,
                          cp.source AS profile_source,cp.fetched_at AS profile_fetched_at,
                          sm.venue,sm.asset_class,sm.currency,sm.timezone,sm.session,sm.source AS inst_source
                   FROM (
                     SELECT symbol,date,close,volume,
                            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                     FROM price_data
                     WHERE market='TH' AND symbol=ANY(%s)
                   ) q
                   LEFT JOIN symbol_master sm
                     ON sm.symbol=q.symbol AND sm.instrument_type='ORD'
                   LEFT JOIN company_profiles cp ON cp.symbol = q.symbol
                   WHERE q.rn <= 2
                   ORDER BY q.symbol,q.rn""", (symbols,))
    out = {}
    for row in cur.fetchall():
        symbol, date, close, volume, rn = row[:5]
        sector = row[5] if len(row) > 5 else None
        industry = row[6] if len(row) > 6 else None
        market_cap = row[7] if len(row) > 7 else None
        free_float_pct = row[8] if len(row) > 8 else None
        foreign_limit_pct = row[9] if len(row) > 9 else None
        company_name = row[10] if len(row) > 10 else None
        profile_source = row[11] if len(row) > 11 else None
        profile_fetched_at = row[12] if len(row) > 12 else None
        venue = row[13] if len(row) > 13 else None
        asset_class = row[14] if len(row) > 14 else None
        currency = row[15] if len(row) > 15 else None
        timezone = row[16] if len(row) > 16 else None
        session = row[17] if len(row) > 17 else None
        inst_source = row[18] if len(row) > 18 else None
        value = out.setdefault(symbol, {})
        if rn == 1:
            value.update({"date": str(date), "close": float(close), "volume": float(volume or 0),
                          "turnover": float(close) * float(volume or 0),
                          "daily_date": str(date), "daily_close": float(close),
                          "daily_turnover": float(close) * float(volume or 0),
                          "sector": sector, "industry": industry,
                          "market_cap": market_cap, "free_float_pct": free_float_pct,
                          "foreign_limit_pct": foreign_limit_pct,
                          "companyName": company_name,
                          "profileSource": profile_source,
                          "profileFetchedAt": str(profile_fetched_at) if profile_fetched_at else None,
                          # P0-2 instrument authority taxonomy from symbol_master.
                          # Provenance: inst_source (settrade_stock_master) beats
                          # the Yahoo fallback for venue/currency/timezone/session.
                          "venue": venue, "asset_class": asset_class,
                          "currency": currency, "timezone": timezone,
                          "session": session, "instrument_source": inst_source})
        else:
            value["previous_close"] = float(close)
            value["daily_previous_close"] = float(close)
    cur.close()
    # Daily-derived technical/context metrics. They remain EOD indicators even
    # when a newer stored 60m quote is shown as the card price.
    cur = pg.cursor()
    cur.execute("""SELECT symbol,date,close,high,low,volume FROM (
          SELECT symbol,date,close,high,low,volume,
                 ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
          FROM price_data
          WHERE market='TH' AND symbol=ANY(%s)
        ) q WHERE rn <= 252 ORDER BY symbol,date""", (symbols,))
    history = {}
    for symbol, date, close, high, low, volume in cur.fetchall():
        history.setdefault(symbol, []).append((date, float(close), float(high), float(low), float(volume or 0)))
    cur.close()
    for symbol, bars in history.items():
        value = out.setdefault(symbol, {})
        # Keep the raw OHLC series so the dashboard can draw a price chart.
        value["history"] = [[str(d), round(float(c), 4), round(float(h), 4),
                              round(float(l), 4), round(float(v or 0), 2)] for d, c, h, l, v in bars]
        closes = [b[1] for b in bars]
        def sma(n): return round(sum(closes[-n:]) / n, 2) if len(closes) >= n else None
        def ema(n):
            if not closes: return None
            alpha, x = 2 / (n + 1), closes[0]
            for price in closes[1:]: x = price * alpha + x * (1 - alpha)
            return x
        e12, e26 = ema(12), ema(26)
        macd = round(e12 - e26, 3) if e12 is not None and e26 is not None else None
        value.update({
            "ma10": sma(10), "ma20": sma(20), "ma50": sma(50), "ma200": sma(200),
            "high52": round(max(b[2] for b in bars[-252:]), 2) if bars else None,
            "low52": round(min(b[3] for b in bars[-252:]), 2) if bars else None,
            "athHigh": round(max(b[2] for b in bars), 2) if bars else None,
            "athLow": round(min(b[3] for b in bars), 2) if bars else None,
            "macd": macd,
            # Liquidity is a rolling Daily EOD measure—not the possibly partial
            # current-session value shown on the card.
            "avgDailyValue20": round(sum(b[1] * b[4] for b in bars[-20:]) / min(len(bars), 20), 2) if bars else None,
        })
    # Actual historical ATH range across the stored database. This is separate
    # from the 252-session window above, which intentionally powers 52W/MAs.
    cur = pg.cursor()
    cur.execute("""SELECT symbol, MAX(high), MIN(low) FROM price_data
                   WHERE market='TH' AND symbol=ANY(%s) GROUP BY symbol""", (symbols,))
    for symbol, high, low in cur.fetchall():
        out.setdefault(symbol, {}).update({"athHigh": round(float(high), 2) if high is not None else None,
                                            "athLow": round(float(low), 2) if low is not None else None})
    cur.close()
    # Non-price identity metadata is cached asynchronously (non-decision data).
    # The first snapshot query already joined sector/industry/profile_source,
    # but company_profiles may still hold a longer business_summary and the
    # legacy Yahoo rows. Merge only when the first query found nothing, so the
    # authoritative SET-sourced taxonomy (sector/industry) is never overwritten
    # by a stale Yahoo fallback value.
    cur = pg.cursor()
    cur.execute("""SELECT symbol, company_name, sector, industry,
                          business_summary, source, fetched_at
                   FROM company_profiles WHERE symbol=ANY(%s)""", (symbols,))
    for symbol, name, sector, industry, summary, source, fetched_at in cur.fetchall():
        val = out.setdefault(symbol, {})
        # Prefer existing values (already authoritative via the symbol_master
        # join); only fill what was genuinely absent. This keeps Yahoo from
        # clobbering SET-sourced taxonomy.
        if val.get("companyName") is None and name is not None:
            val["companyName"] = name; val["profileSource"] = source
            val["profileFetchedAt"] = str(fetched_at)
        if val.get("sector") is None and sector is not None:
            val["sector"] = sector
            if not val.get("profileSource"):
                val["profileSource"] = source; val["profileFetchedAt"] = str(fetched_at)
        if val.get("industry") is None and industry is not None:
            val["industry"] = industry
            if not val.get("profileSource"):
                val["profileSource"] = source; val["profileFetchedAt"] = str(fetched_at)
        if val.get("businessSummary") is None and summary is not None:
            val["businessSummary"] = summary
            if not val.get("profileSource"):
                val["profileSource"] = source; val["profileFetchedAt"] = str(fetched_at)
    cur.close()
    # Overlay the newest stored intraday close when available. This is a DB-only
    # freshness choice: it never implies streaming/real-time market data.
    cur = pg.cursor()
    cur.execute("""SELECT DISTINCT ON (ip.symbol) ip.symbol, ip.interval, ip.ts, ip.close, ip.volume
        FROM intraday_price_data ip
        LEFT JOIN intraday_feed_status fs
          ON fs.symbol=ip.symbol AND fs.feed='settrade_intraday_60m'
        WHERE ip.symbol=ANY(%s) AND ip.interval = '60m'
          AND (fs.status IS NULL OR fs.status <> 'unavailable' OR fs.retry_at <= now())
        ORDER BY ip.symbol, ip.ts DESC""", (symbols,))
    for symbol, interval, ts, close, volume in cur.fetchall():
        value = out.setdefault(symbol, {})
        value.update({"close": float(close), "date": str(ts), "price_source": interval,
                      "volume": float(volume or 0), "turnover": float(close) * float(volume or 0),
                      "previous_close": value.get("daily_previous_close"), "change": None})
    try:
        cur.execute("""SELECT symbol,status,reason,consecutive_failures,last_failure_at,retry_at
            FROM intraday_feed_status WHERE symbol=ANY(%s) AND feed='settrade_intraday_60m'""", (symbols,))
        for symbol, status, reason, failures, last_failure, retry_at in cur.fetchall():
            out.setdefault(symbol, {}).update({
                "intraday_feed_status": status,
                "intraday_feed_reason": reason,
                "intraday_feed_failures": int(failures or 0),
                "intraday_feed_retry_at": str(retry_at) if retry_at else None,
            })
        cur.close()
    except Exception:
        # Backward-compatible with isolated/unit DBs created before the
        # feed-status table; production creates it before intraday runs.
        pass
    # Same-time cumulative-volume comparison. For every symbol use the latest
    # local BKK intraday timestamp today and total its bars up to that time;
    # compare against the most recent prior trading day at the same cutoff.
    cur = pg.cursor()
    cur.execute("""WITH scoped AS (
        SELECT symbol, (ts AT TIME ZONE 'Asia/Bangkok')::date AS d,
               (ts AT TIME ZONE 'Asia/Bangkok')::time AS t, volume
        FROM intraday_price_data
        WHERE symbol=ANY(%s) AND interval='60m'
          AND ts >= NOW() - INTERVAL '10 days'
    ), latest AS (
        SELECT symbol, max(d) AS today FROM scoped GROUP BY symbol
    ), cutoff AS (
        SELECT s.symbol,l.today,max(s.t) AS cutoff
        FROM scoped s JOIN latest l USING(symbol) WHERE s.d=l.today GROUP BY s.symbol,l.today
    ), prior AS (
        SELECT s.symbol,max(s.d) AS prior_day FROM scoped s JOIN cutoff c USING(symbol)
        WHERE s.d<c.today GROUP BY s.symbol
    ) SELECT c.symbol,c.today,c.cutoff,
             COALESCE((SELECT sum(s.volume) FROM scoped s WHERE s.symbol=c.symbol AND s.d=c.today AND s.t<=c.cutoff),0) AS today_volume,
             p.prior_day,
             COALESCE((SELECT sum(q.volume) FROM scoped q WHERE q.symbol=c.symbol AND q.d=p.prior_day AND q.t<=c.cutoff),0) AS prior_volume
      FROM cutoff c
      LEFT JOIN prior p ON p.symbol=c.symbol""", (symbols,))
    for symbol, today, cutoff, today_volume, prior_day, prior_volume in cur.fetchall():
        ratio = (float(today_volume) / float(prior_volume)) if prior_volume and prior_volume > 0 else None
        out.setdefault(symbol, {}).update({"sameTimeVolume": float(today_volume or 0),
            "sameTimePriorVolume": float(prior_volume or 0), "sameTimeVolumeRatio": round(ratio, 2) if ratio else None,
            "sameTimeCutoff": str(cutoff), "sameTimePriorDay": str(prior_day) if prior_day else None})
    cur.close()
    for value in out.values():
        if value.get("change") is not None:
            continue
        prev, close = value.get("previous_close"), value.get("close")
        # Daily change is only meaningful for a Daily EOD price.
        if value.get("price_source") is None:
            value["change"] = ((close / prev - 1) * 100) if prev else None
            value["change_amount"] = (close - prev) if prev else None
        else:
            value["change"] = ((close / prev - 1) * 100) if prev else None
            value["change_amount"] = (close - prev) if prev else None
        dprev, dclose = value.get("daily_previous_close"), value.get("daily_close")
        value["daily_change"] = ((dclose / dprev - 1) * 100) if dprev and dclose else None
    return out


# --- Signalix decision / freshness / data-quality layer (presentation only) ---
# These helpers NEVER mutate the deterministic scanner output. They interpret
# existing fields into an actionable, auditable presentation layer. Rules are
# deliberately conservative: prefer WAIT over READY, and never claim live data.

# Active intraday contract is 60m and the UI must make a quote older than one
# hour visibly stale.  Daily EOD remains the decision source when stale.
INTRADAY_STALE_HOURS = 1
MIN_DAILY_TURNOVER_THB = 5_000_000
BREAKOUT_VOLUME_REQUIREMENT = 1.20

# Canonical freshness statuses — single source of truth from provenance_contract.
from provenance_contract import (
    INTRADAY_STALE_HOURS as _CONTRACT_STALE_HOURS,
    FRESH, STALE, AGING, UNKNOWN,
)


def _price_band(close):
    try:
        c = float(close)
    except (TypeError, ValueError):
        return None
    if c < 2.0:
        return "low"
    if c <= 10.0:
        return "mid"
    return "high"


def _passes_value(avg_daily_value):
    try:
        v = float(avg_daily_value)
    except (TypeError, ValueError):
        return False
    return v >= 5_000_000


def number(value, digits=2):
    """JSON-safe numeric value, or None. Keeps chart levels numeric."""
    try:
        return None if value is None else round(float(value), digits)
    except (TypeError, ValueError):
        return None


def fmt_number(value, digits=2):
    value = number(value, digits)
    return "—" if value is None else f"{value:.{digits}f}"


def breakout_evidence(readiness, snapshot):
    """Serialize explicit breakout trigger/volume evidence for cards and detail."""
    trigger = readiness.get("breakout_level_20d")
    close = snapshot.get("close")
    ratio = readiness.get("volume_ratio_50")
    try:
        close_n, trigger_n = float(close), float(trigger)
    except (TypeError, ValueError):
        close_n = trigger_n = None
    try:
        ratio_n = float(ratio) if ratio is not None else None
    except (TypeError, ValueError):
        ratio_n = None
    close_ok = close_n is not None and trigger_n is not None and close_n >= trigger_n
    volume_ok = ratio_n is not None and ratio_n >= BREAKOUT_VOLUME_REQUIREMENT
    triggered = close_ok and volume_ok
    return {
        "status": "TRIGGERED" if triggered else "NOT TRIGGERED",
        "close": number(close_n), "trigger": number(trigger_n),
        "close_vs_trigger": "at_or_above" if close_ok else "below",
        "volume_ratio": number(ratio_n), "volume_requirement": BREAKOUT_VOLUME_REQUIREMENT,
        "volume_pass": volume_ok,
        "reason": "Daily close and volume requirement met" if triggered else
                  f"Close {fmt_number(close_n)} vs trigger {fmt_number(trigger_n)}; volume {fmt_number(ratio_n)}× vs required {BREAKOUT_VOLUME_REQUIREMENT:.2f}×",
    }


def pullback_reference_status(row, snapshot):
    """Make pullback support comparison explicit; presentation-only."""
    state = row.get("daily_state") or {}
    reference = state.get("reference_level")
    if reference is None:
        reference = (row.get("trade_readiness") or {}).get("buy_zones_90d", {}).get("62")
    current = snapshot.get("close")
    try:
        current_n, reference_n = float(current), float(reference)
    except (TypeError, ValueError):
        current_n = reference_n = None
    holding = current_n is not None and reference_n is not None and current_n >= reference_n
    return {
        "status": "PULLBACK HOLDING REFERENCE" if holding else "UNDER REFERENCE",
        "current": number(current_n), "reference": number(reference_n),
        "comparison": "above_or_at" if holding else "below",
    }


def intraday_event_evidence(snapshot, intraday_event=None):
    """Serialize intraday emerging-event evidence for the detail/UI layer.

    Daily is the official state; this is provenance only. Exposes the
    source/freshness/baseline lineage required by the P0 contract: when an
    intraday emerging event exists, the card carries its confidence lifecycle
    (emerging/confirmed/expired/invalidated/not_confirmed) and, when reconciled,
    the resolved Daily baseline event it maps to.
    """
    if not intraday_event:
        return None
    confidence = intraday_event.get("confidence")
    if confidence not in ("emerging", "confirmed"):
        return None
    evidence = {
        "confidence": confidence,
        "origin": intraday_event.get("origin"),
        "trigger_price": number(intraday_event.get("trigger_price")),
        "failure_level": number(intraday_event.get("failure_level")),
        "first_seen": intraday_event.get("first_seen"),
        "first_candle_ts": intraday_event.get("first_candle_ts"),
        "interval": intraday_event.get("interval"),
        "intraday_run_id": intraday_event.get("intraday_run_id"),
        "resolved_daily_event_id": intraday_event.get("resolved_daily_event_id"),
        "reconciled_at": intraday_event.get("reconciled_at"),
    }
    # Baseline evidence: the Daily close that anchors the trigger level
    if snapshot:
        evidence["baseline_close"] = number(snapshot.get("daily_close"))
        evidence["baseline_date"] = snapshot.get("daily_date")
    else:
        evidence["baseline_close"] = None
        evidence["baseline_date"] = None
    # Freshness evidence: latest observation join from get_active_intraday_events
    fresh = intraday_event.get("freshness") or {}
    evidence["intraday_close"] = number(fresh.get("close"))
    evidence["intraday_candle_at"] = fresh.get("candle_ts")
    evidence["stale"] = bool(fresh.get("stale"))
    evidence["freshness_status"] = fresh.get("status", "unknown")
    return evidence


def determine_action(group, readiness, snapshot, zones, phase=None):
    """Conservative next action—not a permission to trade.

    Phase (canonical) drives the action; group is a fallback only.
    """
    phase = phase or readiness.get("_phase")
    rsi = readiness.get("rsi_daily")
    near = bool(readiness.get("near_buy_zone"))
    stop = readiness.get("stop_loss") or readiness.get("suggested_stop")
    cut = readiness.get("cut_level")
    close = snapshot.get("close")
    entry50, entry62 = zones.get("50"), zones.get("62")
    invalid = stop or cut

    if close is not None and invalid is not None:
        try:
            if float(close) <= float(invalid):
                return "INVALIDATED", "Price is at or below invalidation; remove this setup from the active plan."
        except (TypeError, ValueError):
            pass

    # --- Phase-driven (canonical) ---
    if phase in ("breakout_new",):
        return "VALIDATE FRESH BREAKOUT", "Fresh breakout; validate live price/liquidity before entry — not an entry signal."
    if phase == "breakout_extended":
        return "DO NOT CHASE", "Breakout extended from trigger or RSI; wait for a new base or controlled retest."
    if phase == "uptrend_pullback":
        return "HOLD IF SUPPORT DEFENDS", "In an uptrend pullback; require support defense and a higher low."
    if phase == "waiting_breakout":
        return "SET BREAKOUT ALERT", "Wait for a Daily close above the 20-day trigger with volume >= 1.2x."
    if phase == "base_tight":
        return "WATCH BASE", "Tight base / VCP; wait for a clean launch breakout."
    if phase in ("base_early",):
        return "WAIT", "Base forming; no qualified structure yet."
    if phase == "topping":
        return "AVOID CHASING", "Stage 3 distribution; protect gains, no new longs."
    if phase in ("declining", "broken"):
        return "NO LONG SETUP", "Stage 4 / broken structure; no qualified long until repair."

    # --- Group fallback (keeps current behaviour for rollups) ---
    if group == "avoid":
        return "AVOID NEW LONG", "Trend quality is weak. Reconsider only after the failed conditions improve."
    if rsi is not None and rsi >= 70 and group in {"uptrend_pullback", "waiting_breakout", "base"}:
        return "AVOID CHASING", f"RSI {rsi:.0f} is stretched; wait for a calm pullback or base."
    return "WAIT", "Wait for a defined setup and confirmation."


def quality_action_gate(action, group, flags):
    """Hard presentation gate: weak evidence can never be READY/VALIDATE.

    The deterministic Daily scan/group is preserved.  This only prevents the
    action layer from overstating a setup when quality/liquidity evidence is
    below the validation floor.
    """
    codes = {flag.get("code") for flag in flags}
    blockers = codes & {"weak_quality", "low_rs", "low_liquidity", "low_volume"}
    if not blockers:
        return action, None
    if action in {"READY TO VALIDATE", "VALIDATE FRESH BREAKOUT", "VALIDATE", "CHECK LIQUIDITY"}:
        if "low_liquidity" in blockers or "low_volume" in blockers:
            return "CHECK QUALITY", "Technical setup remains in the scan, but Daily liquidity/volume is below the hard validation floor."
        return "WAIT", "Technical setup remains in the scan, but Trend Template/RS quality is below the hard validation floor."
    if group == "uptrend_pullback" and blockers & {"low_liquidity", "low_volume", "low_rs", "weak_quality"}:
        return "MONITOR ONLY", "Uptrend pullback is retained for monitoring, not READY, until Daily quality and liquidity pass."
    return action, None


def quality_flags(group, row, snapshot):
    """Presentation-only warnings; never changes the persisted Daily state."""
    state = row.get("daily_state") or {}
    readiness = row.get("trade_readiness") or {}
    trend = row.get("trend_template") or {}
    phase = state.get("phase")
    stage = state.get("stage")
    flags = []
    if phase == "breakout_new":
        flags.append({"code": "fresh", "label": "FRESH", "note": "Fresh Daily breakout; wait for hold/retest confirmation."})
    if phase == "breakout_extended":
        # label avoids the legacy proximity term EXTENDED (v0.2.0 isolation);
        # the code field stays machine-canonical.
        flags.append({"code": "extended", "label": "LATE STAGE",
                      "note": "Extended from trigger or RSI; do not chase."})
    met = trend.get("conditions_met")
    if met is not None and met < 8:
        flags.append({"code": "weak_quality", "label": "WEAK QUALITY", "note": f"Trend Template {met}/8; not a fully qualified trend."})
    rs = trend.get("rs_rating")
    threshold = trend.get("rs_threshold", 50)
    if rs is not None and threshold is not None and float(rs) < float(threshold):
        flags.append({"code": "low_rs", "label": "LOW RS", "note": f"RS {float(rs):.0f} is below the Daily floor {float(threshold):.0f}."})
    turnover = snapshot.get("daily_turnover", snapshot.get("turnover"))
    ratio = readiness.get("volume_ratio_50")
    if turnover is not None and float(turnover) < MIN_DAILY_TURNOVER_THB:
        flags.append({"code": "low_liquidity", "label": "LOW LIQUIDITY", "note": f"Daily EOD turnover ฿{float(turnover):,.0f} is below ฿{MIN_DAILY_TURNOVER_THB:,.0f}."})
    if ratio is not None and float(ratio) < 0.5:
        flags.append({"code": "low_volume", "label": "LOW VOLUME", "note": f"Daily volume is {float(ratio):.2f}× the 50-day average."})
    return flags


def snapshot_items(pg, scan):
    """Build the same complete progressive payload used by the static dashboard."""
    source_groups = scan.get("groups", {})
    rows = [r for values in source_groups.values() for r in values]
    symbols = [row["symbol"] for row in rows]
    latest = snapshots(pg, symbols)
    from screening import load_index_membership, universe_layer2, universe_layer3
    layer2_map = universe_layer2(pg, symbols)
    layer3_map = universe_layer3(pg, symbols)
    set50_set = load_index_membership(pg)
    items = [serialize(
        key, row, latest.get(row["symbol"], {}), None,
        layer2_map.get(row["symbol"]), set50_set,
        layer3=layer3_map.get(row["symbol"]),
        sector=latest.get(row["symbol"], {}).get("sector"),
        industry=latest.get(row["symbol"], {}).get("industry"),
        market_cap=latest.get(row["symbol"], {}).get("market_cap"),
        free_float_pct=latest.get(row["symbol"], {}).get("free_float_pct"),
        foreign_limit_pct=latest.get(row["symbol"], {}).get("foreign_limit_pct"),
    ) for key, values in source_groups.items() for row in values]
    items = apply_projection(items)
    items.sort(key=dashboard_sort_key)
    return items


def freshness_info(snapshot):
    """Return human-readable BKK provenance for the card/detail UI."""
    source = snapshot.get("price_source") or "Daily EOD"
    ts = snapshot.get("date")
    if source == "Daily EOD":
        return ("Daily EOD", as_date(ts) or "Unavailable", "EOD", False)
    full_ts = str(ts) if ts else "Unavailable"
    is_stale = False
    age = ""
    try:
        from datetime import timezone
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")) if ts else None
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff_h = (now - dt).total_seconds() / 3600.0
            is_stale = diff_h > INTRADAY_STALE_HOURS
            bkk = dt.astimezone(ZoneInfo("Asia/Bangkok"))
            full_ts = bkk.strftime("%d %b %Y %H:%M ICT (Bangkok)")
            if diff_h < 1:
                mins = max(1, round(diff_h * 60))
                age = f"updated {mins} min ago"
            elif diff_h < 24:
                age = f"updated {round(diff_h)}h ago"
            else:
                age = f"updated {round(diff_h / 24)}d ago"
    except (ValueError, TypeError):
        age = ""
    label = f"{source} stored"
    return (label, full_ts, age, is_stale)


def ath_quality_flag(row, snapshot):
    """ATH distance is NOT used for ranking/decision. Flag potential corporate-action
    discontinuity so the UI can warn without claiming adjusted history is correct."""
    ath = row.get("all_time_high")
    close = snapshot.get("close") or row.get("close")
    try:
        ath = float(ath) if ath is not None else None
        close = float(close) if close is not None else None
    except (TypeError, ValueError):
        return None
    if not ath or not close or ath <= 0 or close <= 0:
        return None
    ratio = ath / close
    # A price more than ~5x its ATH strongly suggests unadjusted historical ATH
    # (corporate actions: splits/rights). Heuristic, not a claim of correctness.
    if ratio >= 5:
        return {"level": "warn", "note": "Historical ATH looks disconnected from the current price (possible unadjusted corporate action). Not used as a signal."}
    return None


def risk_metrics(snapshot, readiness, zones):
    """Deterministic risk-to-stop % and target R-multiples. Safe None/zero handling."""
    close = snapshot.get("close")
    stop = readiness.get("stop_loss") or readiness.get("suggested_stop")
    targets = readiness.get("targets") or {}
    out = {"riskStop": None, "riskStopPct": None, "t127": None, "t161": None, "r127": None, "r161": None}
    if close is None or stop is None:
        return out
    try:
        close = float(close); stop = float(stop)
    except (TypeError, ValueError):
        return out
    if close <= 0 or stop <= 0:
        return out
    risk = close - stop
    if risk > 0:
        out["riskStopPct"] = round(risk / close * 100, 1)
    out["riskStop"] = round(stop, 2)
    for key, tkey in (("127", "t127"), ("161", "t161")):
        t = targets.get(key)
        if t is not None:
            try:
                t = float(t)
            except (TypeError, ValueError):
                continue
            out[tkey] = round(t, 2)
            if risk > 0:
                out["r" + key] = round((t - close) / risk, 1)
    return out


def as_date(value):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except (TypeError, ValueError):
        return "Unavailable"


def plan(group, readiness, trend, snapshot, phase=None):
    phase = phase or readiness.get("_phase")
    zones = readiness.get("buy_zones_90d", {})
    stop = readiness.get("stop_loss") or readiness.get("suggested_stop")
    # --- Phase-driven (canonical) ---
    if phase in ("breakout_new", "breakout_extended"):
        return "20-day trigger", number(readiness.get("breakout_level_20d")), "Invalidation", number(stop)
    if phase == "uptrend_pullback":
        return "Reference entry", f"{number(zones.get('50')) or '—'}–{number(zones.get('62')) or '—'}", "Invalidation", number(stop)
    if phase == "waiting_breakout":
        return "20-day trigger", number(readiness.get("breakout_level_20d")), "Invalidation", number(stop)
    if phase in ("base_early", "base_tight"):
        return "Structure", "Base building", "RS", number(trend.get("rs_rating"), 0)
    if phase in ("topping", "declining", "broken"):
        return "สถานะ", "ยังไม่เล่น", "เงื่อนไข", "รอให้โครงสร้างดีขึ้น"
    # --- Group fallback ---
    if group == "base":
        return "Structure", "Base building", "RS", number(trend.get("rs_rating"), 0)
    if group == "down_or_broken":
        return "Trend Template", f"{trend.get('conditions_met', 0)}/8", "RS required", f"≥ {number(trend.get('rs_threshold'), 0)}"
    return "Setup status", "Awaiting confirmation", "RS", number(trend.get("rs_rating"), 0)


# --- Task 3: explicit shortlist evidence helpers (serialize raw fields) ---
def _shortlist_trigger(phase, group) -> str | None:
    """Explainable Daily Shortlist trigger label (entry confirmation).

    Mirrors daily_shortlist._trigger so the serialized card carries an explicit
    trigger raw field.  Only the Daily EOD decision layer is considered.
    """
    if phase == "breakout_new":
        return "Daily close >= breakout trigger with quality pass"
    if phase == "uptrend_pullback":
        return "Pullback holding support reference"
    if phase == "breakout_retest":
        return "Breakout retest at reference"
    if group == "waiting_breakout":
        return "Near trigger/pivot; confirm with close + volume"
    return None


def _shortlist_invalidation(stop_price) -> str | None:
    """Explainable Daily Shortlist invalidation / system-stop boundary.

    Mirrors daily_shortlist._invalidation so the serialized card carries an
    explicit invalidation raw field.
    """
    if stop_price is not None:
        try:
            return f"Close <= risk stop {float(stop_price):.2f}"
        except (TypeError, ValueError):
            return None
    return None


def serialize(group, row, snapshot, intraday_state=None, layer2=None, set50=None,
              layer3=None, sector=None, industry=None, market_cap=None,
              free_float_pct=None, foreign_limit_pct=None,
              intraday_event=None):
    readiness, trend = row.get("trade_readiness", {}), row.get("trend_template", {})
    intraday_state = intraday_state or {}
    l2 = layer2 or {}
    l3 = layer3 or {}
    s50 = set50 or set()
    # A stored overlay belongs only to the Daily base state that created it.
    # Never let yesterday's base-group override a newly rebuilt Daily scan.
    if intraday_state.get("base_group") != group:
        intraday_state = {}
    effective_group = intraday_state.get("effective_group") or group
    zones = readiness.get("buy_zones_90d", {})
    source_label, _card_timestamp, _card_age, stale = freshness_info(snapshot)
    # Scanner decisions are Daily EOD. A stale stored intraday quote remains
    # visible for provenance, but must never upgrade/downgrade the action.
    decision_snapshot = snapshot
    if stale and snapshot.get("daily_close") is not None:
        decision_snapshot = {**snapshot, "close": snapshot["daily_close"],
                             "date": snapshot.get("daily_date"),
                             "turnover": snapshot.get("daily_turnover"),
                             "change": snapshot.get("daily_change")}
        source_label = "Daily EOD"
    phase = (row.get("daily_state") or {}).get("phase")
    a_label, a_value, b_label, b_value = plan(effective_group, readiness, trend, decision_snapshot, phase=phase)
    action, action_reason = determine_action(effective_group, readiness, decision_snapshot, zones, phase=phase)
    if readiness.get("status") == "INSUFFICIENT_HISTORY":
        action = "INSUFFICIENT HISTORY"
        action_reason = readiness.get("reason") or "Not enough history for technical analysis."
    flags = quality_flags(group, row, snapshot)
    if any(f["code"] == "extended" for f in flags):
        action, action_reason = "DO NOT CHASE", "Breakout is extended; wait for a new base or controlled retest."
    elif any(f["code"] == "fresh" for f in flags) and effective_group == "breakout_new":
        action, action_reason = "VALIDATE FRESH BREAKOUT", "Fresh Daily breakout; do not treat the scan label as an entry."
    gated_action, gated_reason = quality_action_gate(action, group, flags)
    if gated_reason:
        action, action_reason = gated_action, gated_reason
    daily_state = row.get("daily_state") or {}
    stage = daily_state.get("stage")
    phase = daily_state.get("phase")
    # Retest Watch mapping reconciliation (t_c5694a25): scan files produced by
    # the pre-t_3ae98ae4 classifier persist primary_state="breakout_retest"
    # while phase stayed "breakout_new". primary_state is the canonical P0
    # decision state, so when the two disagree on the retest label we trust the
    # deterministic primary_state and promote phase — never the reverse. This
    # does NOT broaden legacy labels: it only fires on the exact canonical
    # primary_state value and keeps every other phase untouched.
    if (daily_state.get("primary_state") == "breakout_retest"
            and phase != "breakout_retest" and stage == "S2_uptrend"):
        phase = "breakout_retest"
        daily_state = {**daily_state, "phase": phase,
                       "phase_label": "Breakout retest"}
    # Two-layer actionable setup state (quality gate + proximity timing).
    setup_q = daily_state.get("setup_quality") or {}
    setup_p = daily_state.get("setup_proximity") or {}
    radar_state = setup_p.get("state")
    radar = bool(setup_q.get("pass") and radar_state in ("near_trigger", "action"))
    # P1 Action Queue Redesign (t_69ff91c2): canonical 7-queue projection.
    # Deterministic; derived from stage/phase/quality/proximity + active event.
    from action_queue import (assign_action_queue, queue_label,
                              LEGACY_PROXIMITY_ALIASES,
                              DATA_BLOCK_INSUFFICIENT, DATA_BLOCK_STALE)
    _queue = assign_action_queue(
        stage=stage, phase=phase,
        quality_pass=bool(setup_q.get("pass")),
        proximity_state=radar_state,
        intraday_event=intraday_event,
    )
    # Insufficient-history rows are never actionable and carry an explicit
    # data-block reason instead of a silent risk verdict.
    _data_block = None
    _daily_fresh = ((row.get("daily_state") or {}).get("data_freshness") or "fresh")
    if readiness.get("status") == "INSUFFICIENT_HISTORY":
        _queue = "monitor_only"
        _data_block = DATA_BLOCK_INSUFFICIENT
    elif stale or _daily_fresh == "stale":
        _data_block = DATA_BLOCK_STALE
    # Canonical v0.2.0: READY/WATCH-style proximity badges are legacy display
    # terms. They survive ONLY under explicit legacy_alias for migration/audit.
    legacy_alias = {"proximity_state": LEGACY_PROXIMITY_ALIASES.get(radar_state)} \
        if radar_state else {}
    radar_badge = None
    lifecycle = {
        "state": phase or "unclassified",
        "stage": stage or "none",
        "fresh_opportunity": phase == "breakout_new",
        "extended": phase == "breakout_extended",
        "label": f"{(STAGE_LABELS.get(stage, stage))} · {(PHASE_LABELS.get(phase, phase))}",
    }
    daily_as_of = snapshot.get("daily_date") or snapshot.get("date")
    feed_status = snapshot.get("intraday_feed_status")
    feed_unavailable = feed_status == "unavailable"
    intraday_source = None if feed_unavailable else snapshot.get("price_source")
    # Stage-first canonical projection (Minervini S1-S4 + phase). The persisted
    # daily_state carries {stage, phase, ...}; legacy primary_state is gone.
    canonical = dict(daily_state)  # already carries the retest reconciliation
    phase = canonical.get("phase")
    stage = canonical.get("stage")
    _fresh = phase == "breakout_new"
    _ext = phase == "breakout_extended"
    _broken = phase in ("broken", "declining") or stage in ("S3_distributing", "S4_down")
    canonical.setdefault("trendState",
                         "trend_pass" if stage == "S2_uptrend"
                         else "trend_partial" if stage == "S1_basing"
                         else "trend_failed")
    canonical.setdefault("setupState",
                         {"uptrend_pullback": "pullback_holding",
                          "waiting_breakout": "pre_breakout",
                          "breakout_new": "pre_breakout",
                          "base_early": "base_forming",
                          "base_tight": "base_forming"}.get(phase, "pre_breakout"))
    canonical.setdefault("lifecycleState",
                         {"breakout_new": "fresh_breakout",
                          "breakout_extended": "extended_breakout",
                          "breakout_retest": "retest"}.get(phase, "none"))
    canonical.setdefault("action",
                         {"breakout_new": "VALIDATE_FRESH",
                          "breakout_extended": "DO_NOT_CHASE",
                          "breakout_retest": "WAIT_FOR_RETEST",
                          "uptrend_pullback": "HOLD_IF_SUPPORT_DEFENDS",
                          "declining": "NO_LONG_SETUP",
                          "broken": "NO_LONG_SETUP"}.get(phase, "WAIT"))
    canonical.setdefault("eligibility",
                         "eligible" if phase in ("breakout_new", "uptrend_pullback") else "not_eligible")
    canonical.setdefault("dataFreshness", "fresh")
    primary_state = phase  # kept for downstream readability where still referenced
    canonical_action = canonical.get("action") or "WAIT"
    if _broken:
        action, action_reason = "AVOID BROKEN SETUP", "Broken or declining structure; no new long until it repairs."
    elif phase == "declining" or group == "down_or_broken":
        action, action_reason = "NO LONG SETUP", "No qualified long setup is currently persisted; wait for a new structure."
    intraday_stale = bool(stale and intraday_source)
    if intraday_state.get("action"):
        action, action_reason = intraday_state["action"], intraday_state.get("action_reason") or action_reason
        action, gated_reason = quality_action_gate(action, group, flags)
        if gated_reason:
            action_reason = gated_reason
    quality_flag = ath_quality_flag(row, decision_snapshot)
    risk = risk_metrics(decision_snapshot, readiness, zones)
    breakout = (breakout_evidence(readiness, decision_snapshot)
                if group in {"waiting_breakout", "breakout_new"} or phase in {"waiting_breakout", "breakout_new", "breakout_extended"}
                else None)
    pullback = pullback_reference_status(row, decision_snapshot) if phase == "uptrend_pullback" or group == "uptrend_pullback" else None
    result = {
        "symbol": row["symbol"], "group": effective_group, "baseGroup": group,
        "intent": GROUP_BY_KEY.get(effective_group, GROUP_BY_KEY["down_or_broken"])[2], "status": GROUP_BY_KEY.get(effective_group, GROUP_BY_KEY["down_or_broken"])[1],
                    "tone": GROUP_BY_KEY.get(effective_group, GROUP_BY_KEY["down_or_broken"])[3],
        "intradayChanged": effective_group != group,
        "intradayEvaluatedAt": str(intraday_state.get("evaluated_at") or ""),
        "close": decision_snapshot.get("close", row.get("close")), "change": decision_snapshot.get("change"),
        "changeAmount": number(decision_snapshot.get("change_amount")), "changePct": decision_snapshot.get("change"), "volume": number(decision_snapshot.get("volume"), 0),
        "tradeValue": number(decision_snapshot.get("turnover"), 0),
        "avgDailyValue20": number(snapshot.get("avgDailyValue20"), 0),
        # Compact first-paint cards deliberately skip historical fan-out.  Unknown
        # liquidity must remain visible—not be misclassified as illiquid and
        # removed by the default filter. The detail view supplies the real 20D value.
        "lowValue": snapshot.get("avgDailyValue20") is not None and snapshot["avgDailyValue20"] < 10_000_000,
        "volumeSurgeRatio": number(snapshot.get("sameTimeVolumeRatio"), 2),
        # Avoid a 5x badge caused only by a tiny prior-session denominator.
        # A surge is actionable only for liquid names with meaningful cumulative flow.
        "volumeSurge": bool((snapshot.get("avgDailyValue20") or 0) >= 10_000_000 and
                            (snapshot.get("sameTimeVolume") or 0) >= 5_000_000 and
                            (snapshot.get("sameTimeVolumeRatio") or 0) >= 5),
        "sameTimeVolume": number(snapshot.get("sameTimeVolume"), 0),
        "sameTimePriorVolume": number(snapshot.get("sameTimePriorVolume"), 0),
        "sameTimeCutoff": snapshot.get("sameTimeCutoff"),
        "date": decision_snapshot.get("date") or row.get("last_date"),
        "priceSource": "Daily EOD" if stale else snapshot.get("price_source") or "Daily EOD", "priceLabel": source_label,
        "stale": stale,
        "intraday_stale": intraday_stale,
        "intradaySource": intraday_source,
        "intradayLatestTime": snapshot.get("date") if intraday_source else None,
        "intradayAge": _card_age if intraday_source else None,
        "intradayStale": intraday_stale if intraday_source else None,
        "intradayFeedStatus": feed_status,
        "intradayFeedReason": snapshot.get("intraday_feed_reason"),
        "intradayFeedFailures": snapshot.get("intraday_feed_failures", 0),
        "intradayFeedRetryAt": snapshot.get("intraday_feed_retry_at"),
        "intradayAvailable": bool(intraday_source) and not feed_unavailable,
        "intradayFreshness": {"status": "unavailable" if feed_unavailable else ("stale" if intraday_stale else ("fresh" if intraday_source else "unavailable")),
                              "source": intraday_source, "candle_at": snapshot.get("date") if intraday_source else None,
                              "age": _card_age if intraday_source else None},
        "freshness_badge": "stale" if stale else ("fresh" if daily_as_of or intraday_source else "unknown"),
        "daily_eod_freshness": {"status": "latest_available" if daily_as_of else "unavailable",
                                "source": "price_data", "as_of": daily_as_of},
        "dailyEodDecision": {"source": "Daily EOD", "as_of": daily_as_of,
                             "close": number(snapshot.get("daily_close")),
                             "turnover": number(snapshot.get("daily_turnover"), 0)},
        "decision_source": "Daily EOD",
        "decision_source_as_of": daily_as_of,
        "staleNote": ("60m intraday feed unavailable; Daily EOD shown for decisions."
                      if feed_unavailable else "A newer intraday quote exists but is stale; Daily EOD shown for decisions."
                      if stale else ""),
        "action": action, "actionReason": action_reason, "canonicalAction": canonical_action,
        "trendState": canonical.get("trendState"), "setupState": canonical.get("setupState"),
        "lifecycleState": canonical.get("lifecycleState"), "eligibility": canonical.get("eligibility"),
        "dataFreshness": canonical.get("dataFreshness") or ("stale" if stale else "fresh"),
        "eventFailureLevel": number(canonical.get("failure_level")) if canonical.get("lifecycleState") in {"fresh_breakout", "extended_breakout", "retest", "confirmed_failure"} else None,
        "structuralCut90d": number(readiness.get("cut_level")),
        "riskStop": risk.get("riskStop"), "athFlag": quality_flag,
        "lifecycle": lifecycle,
        "breakoutEvidence": breakout,
        "intradayEventEvidence": intraday_event_evidence(snapshot, intraday_event),
        "pullbackReference": pullback,
        "qualityFlags": flags, "qualityWarning": "; ".join(f["label"] for f in flags),
        "dailyState": canonical,
        # --- Stage-first top-level fields (Minervini S1-S4 + phase) ---
        # These are the PRIMARY axis of the dashboard; the legacy 5-group label
        # is retained only as a presentation tag (i.group), not the organizer.
        "stage": stage or "S1_basing",
        "stage_label": STAGE_LABELS.get(stage, stage) or STAGE_LABELS["S1_basing"],
        "phase": phase or "base_early",
        "phase_label": PHASE_LABELS.get(phase, phase) or PHASE_LABELS["base_early"],
        "stage_phase": f"{(STAGE_LABELS.get(stage, stage))} · {(PHASE_LABELS.get(phase, phase))}",
        "quality": (row.get("daily_state") or {}).get("quality") or {},
        "setup_quality": setup_q,
        "setup_proximity": setup_p,
        "radar": radar,
        "action_queue": _queue,
        "action_queue_label": queue_label(_queue),
        "data_block": _data_block,
        "legacy_alias": legacy_alias or None,
        "radarBadge": radar_badge,
        "liquidity": {"source": "Daily EOD", "turnover": number(snapshot.get("daily_turnover", snapshot.get("turnover")), 0),
                      "volumeRatio50": number(readiness.get("volume_ratio_50")),
                      "thresholdTurnover": MIN_DAILY_TURNOVER_THB},
        "orderBook": {"available": False, "status": "unavailable",
                       "note": "No order-book source is connected; OHLCV is not Level 2."},
        "rs": number(trend.get("rs_rating"), 0), "rsi": number(readiness.get("rsi_daily"), 1),
        "tt": trend.get("conditions_met"), "rsThreshold": trend.get("rs_threshold"),
        "failedConditions": [c.get("label", c.get("key", "")) for c in trend.get("failed_conditions", [])],
        "companyName": snapshot.get("companyName"), "sector": snapshot.get("sector"), "industry": snapshot.get("industry"),
        "businessSummary": (snapshot.get("businessSummary") or "")[:320] or None, "profileSource": snapshot.get("profileSource"),
        "profileFetchedAt": snapshot.get("profileFetchedAt"),
        # P0-2 instrument authority taxonomy (symbol_master). These are the
        # canonical SET/mai ordinary-share descriptors used for venue routing,
        # currency conversion, session/freshness and audit provenance.
        "venue": snapshot.get("venue"), "assetClass": snapshot.get("asset_class"),
        "currency": snapshot.get("currency"), "timezone": snapshot.get("timezone"),
        "marketSession": snapshot.get("session"), "instrumentSource": snapshot.get("instrument_source"),
        "ma50": readiness.get("above_ma50"), "ma10Value": number(snapshot.get("ma10")),
        "ma20Value": number(snapshot.get("ma20")), "ma50Value": number(snapshot.get("ma50")),
        "ma200Value": number(snapshot.get("ma200")), "macd": number(snapshot.get("macd"), 3),
        "high52": number(snapshot.get("high52")), "low52": number(snapshot.get("low52")),
        "athHigh": number(snapshot.get("athHigh")), "athLow": number(snapshot.get("athLow")),
        "entry50": number(zones.get("50")), "entry62": number(zones.get("62")),
        "stop": number(readiness.get("stop_loss") or readiness.get("suggested_stop")),
        "cut": number(readiness.get("cut_level")), "ath": number(row.get("all_time_high")),
        "volumeRatio": number(readiness.get("volume_ratio_50")),
        "volumeRatio50": number(readiness.get("volume_ratio_50")), "turnover": number(decision_snapshot.get("turnover"), 0),
        "breakout": bool(readiness.get("breakout_20d")), "breakoutLevel": number(readiness.get("breakout_level_20d")),
        "nearEntry": bool(readiness.get("near_buy_zone")), "vcp": bool(row.get("vcp", {}).get("is_vcp")),
        "primaryLabel": a_label, "primaryValue": a_value, "secondaryLabel": b_label, "secondaryValue": b_value,
        **risk,
        "tvUrl": "https://www.tradingview.com/chart/?symbol=SET%3A" + quote(row["symbol"], safe=""),
        # --- Layer 2 (short-term momentum grouping, 60m) + Independence filter ---
        "layer1_stage": stage or "S1_basing",
        "layer2_signals": l2.get("signals", {}),
        "layer2_group": l2.get("group"),
        "layer2_structural": {
            "signals": (l2.get("structural") or {}).get("signals", {}),
            "group": (l2.get("structural") or {}).get("group"),
        },
        "layer2_momentum": {
            "signals": (l2.get("momentum") or {}).get("signals", {}),
            "group": (l2.get("momentum") or {}).get("group"),
        },
        "independence": {
            "is_set50": row["symbol"] in s50,
            "avgTradeValue20": number(snapshot.get("avgDailyValue20"), 0),
            "priceBand": _price_band(snapshot.get("close")),
            "passesValueFilter": _passes_value(snapshot.get("avgDailyValue20")),
            "sector": sector,
            "industry": industry,
            "market_cap": market_cap,
            "free_float_pct": free_float_pct,
            "foreign_limit_pct": foreign_limit_pct,
        },
        "layer3_qualifier": l3,
        # Retain the plural legacy key for existing dashboard consumers.
        "layer3_qualifiers": l3,
        # Ranking (Contract v0.2.0 §5)
        "ranking": row.get("ranking"),
        # --- Task 3: explicit raw shortlist evidence fields (where absent) ---
        # These expose the Daily EOD provenance and entry/invalidation evidence
        # as top-level raw fields so the Daily Shortlist API can consume them
        # directly from the serialized card without re-deriving them.
        "daily_as_of": daily_as_of,
        "daily_source": snapshot.get("price_source") or "Daily EOD",
        "trigger": _shortlist_trigger(phase, effective_group),
        "invalidation": _shortlist_invalidation(risk.get("riskStop") or readiness.get("stop_loss") or readiness.get("suggested_stop")),
        "lifecycle_state": lifecycle.get("state") or phase or "unclassified",
    }
    # --- P1 Risk/Stop/Target Assistant: pre-baked deterministic RST fields ---
    # Risk anchors (trigger, system_stop, pivots, fibs) are deterministic from
    # Daily EOD data — they do NOT change between data pulls. Embedding them at
    # build time avoids per-request DB scans; only user-input sizing is computed
    # at request time. Intraday 60m contract is still on-demand (candles change).
    try:
        from risk_stop_target import compute_risk_stop_target
        _rst = compute_risk_stop_target("daily", row["symbol"], item=row)
        result.update({
            "rst_contract": "daily",
            "rst_trigger": _rst.get("trigger"),
            "rst_system_stop": _rst.get("system_stop"),
            "rst_pivot_low": _rst.get("pivot_low"),
            "rst_swing_low": _rst.get("swing_low"),
            "rst_swing_high": _rst.get("swing_high"),
            "rst_planned_entry": _rst.get("planned_entry"),
            "rst_planned_stop": _rst.get("planned_stop"),
            "rst_fib_1272": _rst.get("fib_1272"),
            "rst_fib_1618": _rst.get("fib_1618"),
            "rst_risk_per_share": None,
            "rst_position_size": None,
            "rst_risk_budget": None,
            "rst_account_size": None,
            "rst_risk_percent": None,
            "rst_warnings": _rst.get("warnings", []),
            "rst_status": _rst.get("status"),
        })
    except Exception:
        pass
    return result


def dashboard_sort_key(item):
    """Stage-first; within stage, actionable proximity first; rs last tiebreak."""
    stage_order = {"S2_uptrend": 0, "S1_basing": 1, "S3_distributing": 2, "S4_down": 3}
    proximity_order = {"action": 0, "near_trigger": 1, "forming": 2, "extended": 3}
    proximity = (item.get("setup_proximity") or {}).get("state")
    rs = item.get("rs") or 0
    return (stage_order.get(item.get("stage"), 99),
            proximity_order.get(proximity, 5),
            -rs)


def build(scanned=None, run_id=None):
    """Build the stage-first dashboard.

    If ``scanned`` (list of row dicts) is provided it is used directly — this is
    the path the /scan endpoint uses so the dashboard always reflects the exact
    universe just scanned (no stale-file round-trip). Otherwise we fall back to
    reading scan_results.json for standalone rebuilds.
    """
    if scanned is None:
        with open(SCAN_JSON) as file:
            scan = json.load(file)
        source_groups = scan.get("groups", {})
        rows = [r for values in source_groups.values() for r in values]
    else:
        # Re-derive the same group structure the scanner produced, so serialize
        # (which expects a `scan_group` key) stays happy.
        from screening import group_scan_results
        grouped = group_scan_results(scanned, events={})
        source_groups = grouped
        rows = [r for values in source_groups.values() for r in values]
    
    # Ensure ranking is computed for all rows (Contract v0.2.0 §5)
    # This is needed for standalone rebuilds where group_scan_results wasn't called
    if scanned is None:
        from screening import compute_symbol_ranking
        # fetch_market_regime is module-level; keep the import-free fix so
        # build(scanned=...) cannot create a function-local shadow.
        pg = get_pg()
        try:
            market_regime = fetch_market_regime(pg)
            regime_state = market_regime.get("regime_state") if market_regime else None
            for row in rows:
                compute_symbol_ranking(row, regime_state)
        finally:
            pg.close()
    else:
        # When scanned is provided, group_scan_results was already called
        pass
    # Enrich all cards with one batched DB read. This is not a per-symbol
    # connection/query fan-out: snapshots() performs set-based lateral queries
    # for the complete universe, so EOD keeps the technical fields visible.
    pg = get_pg()
    try:
        latest = snapshots(pg, [row["symbol"] for row in rows])
        last_valid_session = max((row.get("last_date") for row in rows if row.get("last_date")), default=None)
        freshness = dashboard_freshness(pg, last_valid_session=last_valid_session)
        cur = pg.cursor()
        cur.execute("""SELECT fetch_completed_at FROM intraday_ingestion_runs
                       WHERE status IN ('full_success','partial_success')
                       ORDER BY fetch_completed_at DESC NULLS LAST LIMIT 1""")
        intraday_row = cur.fetchone()
        intraday_scan_time = intraday_row[0].isoformat() if intraday_row and intraday_row[0] else None
        cur.close()
        from screening import excluded_symbols, universe_layer2, universe_layer3, load_index_membership
        symbols = [row["symbol"] for row in rows]
        excluded = excluded_symbols(pg, market="TH")
        layer2_map = universe_layer2(pg, symbols)
        layer3_map = universe_layer3(pg, symbols)
        set50_set = load_index_membership(pg)
        # P0: intraday emerging events are append-only; fetch active ones
        # (emerging/confirmed) so serialize can expose source/freshness/baseline
        # evidence on each card. Daily remains the official decision source.
        active_events = {}
        try:
            from scan_history import get_active_intraday_events
            active_events = get_active_intraday_events(pg)
        except Exception:
            pass
        # Retest Watch provenance (t_c5694a25): the retest hard gate requires a
        # persisted event with its original trigger price. Daily canonical
        # breakout events are that provenance source (the same immutable events
        # the scanner classified against); intraday emerging events stay a
        # separate append-only lane and never qualify for retest_watch.
        daily_events = {}
        try:
            from scan_history import active_breakout_events
            daily_events = active_breakout_events(pg)
        except Exception:
            pass
    finally:
        pg.close()
    overlays = {}
    items = [serialize(
        key, row, latest.get(row["symbol"], {}), overlays.get(row["symbol"]),
        layer2_map.get(row["symbol"]), set50_set,
        layer3=layer3_map.get(row["symbol"]),
        sector=latest.get(row["symbol"], {}).get("sector"),
        industry=latest.get(row["symbol"], {}).get("industry"),
        market_cap=latest.get(row["symbol"], {}).get("market_cap"),
        free_float_pct=latest.get(row["symbol"], {}).get("free_float_pct"),
        foreign_limit_pct=latest.get(row["symbol"], {}).get("foreign_limit_pct"),
        intraday_event=active_events.get(row["symbol"])
        or daily_events.get(row["symbol"]),
    ) for key, values in source_groups.items() for row in values
      if row["symbol"] not in excluded]
    items = apply_projection(items)
    items.sort(key=dashboard_sort_key)
    # Stage-first axis (Minervini S1-S4): the PRIMARY organizer for the UI.
    stage_order = ["S2_uptrend", "S1_basing", "S3_distributing", "S4_down"]
    stage_counts = {s: sum(1 for item in items if item.get("stage") == s) for s in stage_order}
    stage_meta = {
        s: {"title": STAGE_LABELS.get(s, s), "count": stage_counts[s],
            "tone": {"S2_uptrend": "positive", "S1_basing": "neutral",
                     "S3_distributing": "warning", "S4_down": "danger"}[s]}
        for s in stage_order
    }
    # The progressive API serves this exact set-based build artifact.  Keeping
    # it on disk avoids making every browser refresh repeat 718-symbol joins.
    # Derive scan_time from the scanned rows (no dependency on a stale file).
    scan_time = (scanned[0].get("scan_time") if scanned and isinstance(scanned[0], dict) and scanned[0].get("scan_time")
                 else datetime.now(timezone.utc).isoformat())
    build_timestamp = datetime.now(timezone.utc).isoformat()
    # P0: expose intraday emerging-event reconciliation state in the snapshot
    # metadata so the UI can surface source/freshness/baseline evidence. Daily
    # remains the official state; these are append-only provenance rows.
    event_counts = {"emerging": 0, "confirmed": 0}
    try:
        from scan_history import get_active_intraday_events
        for ev in active_events.values():
            event_counts[ev.get("confidence", "emerging")] = event_counts.get(
                ev.get("confidence", "emerging"), 0) + 1
    except Exception:
        pass
    
    # Fetch market regime (Contract v0.2.0 §3)
    # Priority: 1) from scanned data (when called from app.py), 2) from DB
    market_regime = None
    if scanned:
        for row in scanned:
            if row.get("market_regime"):
                market_regime = row["market_regime"]
                break
    if not market_regime:
        pg_regime = get_pg()
        try:
            market_regime = fetch_market_regime(pg_regime)
        finally:
            pg_regime.close()

    # Freshness computation
    from provenance_contract import compute_freshness
    _root_data_fetched = freshness.get("data_fetched_at")
    _root_freshness_status = compute_freshness(_root_data_fetched)

    snapshot_doc = {"scan_time": scan_time, "market": "TH",
                    "build_timestamp": build_timestamp,
                    "data_fetched_at": _root_data_fetched,
                    "data_freshness_source": freshness.get("source"),
                    "data_freshness_status": _root_freshness_status,
                    "data_global_status": _root_freshness_status,
                    "data_freshness_age_hours": freshness.get("age_hours"),
                    "market_session": freshness.get("market_session", {}),
                    "last_valid_session": (freshness.get("market_session") or {}).get("last_valid_session"),
                    "dashboard_meta": {"build_timestamp": build_timestamp,
                                       "data_fetched_at": freshness.get("data_fetched_at"),
                                       "data_freshness_source": freshness.get("source"),
                                       "intraday_scan_time": intraday_scan_time,
                                       "data_freshness_status": freshness.get("status"),
                                       "market_session": freshness.get("market_session", {}),
                                       "last_valid_session": (freshness.get("market_session") or {}).get("last_valid_session"),
                                       "intraday_event_counts": event_counts},
                    "market_regime": market_regime,
                    "refresh": "progressive_cards", "items": items,
                    "stage_meta": stage_meta, "stage_counts": stage_counts}
    atomic_write_json(SNAPSHOT_JSON, snapshot_doc)
    from provenance_contract import resolve_decision_state
    mvp_freshness = {
        "status": freshness.get("status") or _root_freshness_status,
        "source": freshness.get("source"),
        "as_of": (freshness.get("market_session") or {}).get("last_valid_session"),
        "data_fetched_at": _root_data_fetched,
    }
    if run_id:
        pg_daily = get_pg()
        try:
            cur_daily = pg_daily.cursor()
            cur_daily.execute("SELECT run_timestamp, scan_date, source_lineage FROM daily_scan_runs WHERE id=%s", (run_id,))
            daily_run = cur_daily.fetchone()
            cur_daily.close()
            if daily_run:
                mvp_freshness = daily_freshness_from_run(
                    daily_run[0], daily_run[1], daily_run[2], freshness.get("market_session")
                )
        finally:
            pg_daily.close()
    mvp_doc = build_mvp_snapshot(
        items,
        run_id=run_id,
        scan_time=scan_time,
        freshness=mvp_freshness,
        decision_state=resolve_decision_state(
            freshness.get("market_session"),
            (freshness.get("market_session") or {}).get("last_valid_session"),
        ),
    )
    atomic_write_json(os.path.join(HERE, "mvp_snapshot.json"), mvp_doc)
    counts = {key: sum(1 for item in items if item["primary_group"] == key) for key, *_ in PRIMARY_GROUPS}
    meta = {key: {"title": v["label"], "action": v["action"], "intent": "presentation", "tone": "neutral", "description": v["action"], "count": counts[key]}
            for key, v in PRIMARY_META.items()}
    # Header remains the Daily screening freshness; cards may separately show a
    # newer stored intraday close.
    as_of = max((row.get("last_date") for row in rows if row.get("last_date")), default=None)
    opportunity = counts['fresh']
    prepare = counts['extended'] + counts['pre_break']
    monitor = counts['base'] + counts['pullback_holding'] + counts['pullback_under_reference']
    risk = counts['no_long_setup'] + counts['failed_setup_no_event']
    breadth = round((opportunity + prepare) / max(len(items), 1) * 100)
    health = "Constructive" if breadth >= 45 else "Neutral" if breadth >= 30 else "Defensive"
    health_tone = "positive" if health == "Constructive" else "warning" if health == "Neutral" else "danger"
    # Market page: actionable breadth detail built from the same serialized items.
    vcp_ready = sum(1 for i in items if i["vcp"] and i["group"] in ("ready_validate", "pullback_watch", "retest_watch"))
    invalidated = sum(1 for i in items if i["action"] == "INVALIDATED")
    leaders = sorted((i for i in items if i["group"] in ("ready_validate", "retest_watch", "pullback_watch", "breakout_watch")),
                     key=lambda i: (i["rs"] or 0), reverse=True)[:5]
    leader_rows = "".join(
        '<div class="leader-row" data-open="' + html.escape(i["symbol"]) + '">'
        '<b>' + html.escape(i["symbol"]) + '</b>'
        '<span>' + html.escape(i["status"]) + '</span>'
        '<span>RS ' + str(number(i["rs"], 0)) + '</span>'
        '<span class="' + ("gain" if (i["change"] or 0) >= 0 else "loss") + '">'
        + (f'{i["change"]:+.2f}%' if i["change"] is not None else "—") + '</span></div>'
        for i in leaders)
    # Stage-first dashboard: rendered from dashboard_template.html (kept separate
    # for maintainability). Placeholders are replaced with JSON; the template's
    # own <script> builds stage sections client-side.
    template_path = os.path.join(HERE, "dashboard_template.html")
    with open(template_path, encoding="utf-8") as tf:
        template = tf.read()
    # First-paint artifact: embed only the compact Daily Shortlist candidates
    # (READY + PRE_READY) as __ITEMS__, NOT the full ~900-item universe.
    # The Explorer/Radar/Market pages lazy-load bounded pages from
    # /dashboard/cards/compact instead, keeping the initial HTML slim.
    from daily_shortlist import project_shortlist as _project_shortlist
    shortlist_items = _project_shortlist(items)
    page = (template
            .replace("__ITEMS__", json.dumps(shortlist_items, separators=(",", ":"), default=_json_default))
            .replace("__STAGE_META__", json.dumps(stage_meta, separators=(",", ":"), default=_json_default))
            .replace("__DASHBOARD_META__", json.dumps({"build_timestamp": build_timestamp,
                                                        "data_fetched_at": freshness.get("data_fetched_at"),
                                                        "intraday_scan_time": intraday_scan_time,
                                                        "data_freshness_status": freshness.get("status"),
                                                        "data_freshness_source": freshness.get("source"),
                                                        "market_session": freshness.get("market_session", {}),
                                                        "market_regime": market_regime}, separators=(",", ":"), default=_json_default)))
    atomic_write_text(OUT_HTML, page)
    write_artifact_manifest(os.path.join(HERE, "artifact_manifest.json"), run_id, os.path.join(HERE, "mvp_snapshot.json"), OUT_HTML)
    return {"securities": len(items), "shortlist": len(shortlist_items),
            "groups": counts, "out": OUT_HTML}

if __name__ == "__main__":
    print(build())
