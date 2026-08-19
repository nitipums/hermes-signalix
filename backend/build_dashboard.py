"""Signalix professional screening workspace (English-only, no chart images)."""
import html
import json
import os
from datetime import datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import psycopg2
from reconciled_projection import PRIMARY_GROUPS, PRIMARY_META, apply_projection, snapshot_payload
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
        "status": "unknown",
        "intraday_status": "unknown_stale",
        "global_status": "unknown",
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
        intraday_status = "fresh" if age_hours < INTRADAY_STALE_HOURS else "stale"
        global_status = "fresh" if intraday_status == "fresh" else "stale"
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


def snapshots(pg, symbols):
    if not symbols:
        return {}
    cur = pg.cursor()
    cur.execute("""SELECT q.symbol,q.date,q.close,q.volume,q.rn,cp.sector,cp.industry,
                          cp.market_cap,cp.free_float_pct,cp.foreign_limit_pct
                   FROM (
                     SELECT symbol,date,close,volume,
                            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                     FROM price_data
                     WHERE market='TH' AND symbol=ANY(%s)
                   ) q
                   LEFT JOIN company_profiles cp ON q.symbol = cp.symbol
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
        value = out.setdefault(symbol, {})
        if rn == 1:
            value.update({"date": str(date), "close": float(close), "volume": float(volume or 0),
                          "turnover": float(close) * float(volume or 0),
                          "daily_date": str(date), "daily_close": float(close),
                          "daily_turnover": float(close) * float(volume or 0),
                          "sector": sector, "industry": industry,
                          "market_cap": market_cap, "free_float_pct": free_float_pct,
                          "foreign_limit_pct": foreign_limit_pct})
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
    # Non-price identity metadata is cached asynchronously. It is intentionally
    # not a price/decision input and may be absent while the cache is filling.
    cur = pg.cursor()
    cur.execute("""SELECT symbol,company_name,sector,industry,business_summary,source,fetched_at,
                          market_cap,free_float_pct,foreign_limit_pct
                   FROM company_profiles WHERE symbol=ANY(%s)""", (symbols,))
    for symbol, name, sector, industry, summary, source, fetched_at, market_cap, free_float_pct, foreign_limit_pct in cur.fetchall():
        out.setdefault(symbol, {}).update({"companyName": name, "sector": sector, "industry": industry,
            "businessSummary": summary, "profileSource": source, "profileFetchedAt": str(fetched_at),
            "market_cap": market_cap, "free_float_pct": free_float_pct,
            "foreign_limit_pct": foreign_limit_pct})
    cur.close()
    # Overlay the newest stored intraday close when available. This is a DB-only
    # freshness choice: it never implies streaming/real-time market data.
    cur = pg.cursor()
    cur.execute("""SELECT DISTINCT ON (symbol) symbol, interval, ts, close, volume
        FROM intraday_price_data
        WHERE symbol=ANY(%s) AND interval = '60m'
        ORDER BY symbol, ts DESC""", (symbols,))
    for symbol, interval, ts, close, volume in cur.fetchall():
        value = out.setdefault(symbol, {})
        value.update({"close": float(close), "date": str(ts), "price_source": interval,
                      "volume": float(volume or 0), "turnover": float(close) * float(volume or 0),
                      "previous_close": value.get("daily_previous_close"), "change": None})
    cur.close()
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
        flags.append({"code": "extended", "label": "EXTENDED", "note": "Extended from trigger or RSI; do not chase."})
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


def serialize(group, row, snapshot, intraday_state=None, layer2=None, set50=None,
              layer3=None, sector=None, industry=None, market_cap=None,
              free_float_pct=None, foreign_limit_pct=None):
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
    # Two-layer actionable setup state (quality gate + proximity timing).
    setup_q = daily_state.get("setup_quality") or {}
    setup_p = daily_state.get("setup_proximity") or {}
    radar_state = setup_p.get("state")
    radar = bool(setup_q.get("pass") and radar_state in ("near_trigger", "action"))
    radar_badge = ("READY" if radar_state == "action"
                   else "WATCH" if radar_state == "near_trigger" else None)
    lifecycle = {
        "state": phase or "unclassified",
        "stage": stage or "none",
        "fresh_opportunity": phase == "breakout_new",
        "extended": phase == "breakout_extended",
        "label": f"{(STAGE_LABELS.get(stage, stage))} · {(PHASE_LABELS.get(phase, phase))}",
    }
    daily_as_of = snapshot.get("daily_date") or snapshot.get("date")
    intraday_source = snapshot.get("price_source")
    # Stage-first canonical projection (Minervini S1-S4 + phase). The persisted
    # daily_state carries {stage, phase, ...}; legacy primary_state is gone.
    canonical = dict(row.get("daily_state") or {})
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
                          "breakout_extended": "extended_breakout"}.get(phase, "none"))
    canonical.setdefault("action",
                         {"breakout_new": "VALIDATE_FRESH",
                          "breakout_extended": "DO_NOT_CHASE",
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
    return {
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
        "intradayAvailable": bool(intraday_source),
        "intradayFreshness": {"status": "stale" if intraday_stale else ("fresh" if intraday_source else "unavailable"),
                              "source": intraday_source, "candle_at": snapshot.get("date") if intraday_source else None,
                              "age": _card_age if intraday_source else None},
        "daily_eod_freshness": {"status": "latest_available" if daily_as_of else "unavailable",
                                "source": "price_data", "as_of": daily_as_of},
        "dailyEodDecision": {"source": "Daily EOD", "as_of": daily_as_of,
                             "close": number(snapshot.get("daily_close")),
                             "turnover": number(snapshot.get("daily_turnover"), 0)},
        "decision_source": "Daily EOD",
        "decision_source_as_of": daily_as_of,
        "staleNote": ("A newer intraday quote exists but is stale; Daily EOD shown for decisions."
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
    }


def dashboard_sort_key(item):
    """Stage-first; within stage, actionable proximity first; rs last tiebreak."""
    stage_order = {"S2_uptrend": 0, "S1_basing": 1, "S3_distributing": 2, "S4_down": 3}
    proximity_order = {"action": 0, "near_trigger": 1, "forming": 2, "extended": 3}
    proximity = (item.get("setup_proximity") or {}).get("state")
    rs = item.get("rs") or 0
    return (stage_order.get(item.get("stage"), 99),
            proximity_order.get(proximity, 5),
            -rs)


def build(scanned=None):
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
    # Enrich all cards with one batched DB read. This is not a per-symbol
    # connection/query fan-out: snapshots() performs set-based lateral queries
    # for the complete universe, so EOD keeps the technical fields visible.
    pg = get_pg()
    try:
        latest = snapshots(pg, [row["symbol"] for row in rows])
        last_valid_session = max((row.get("last_date") for row in rows if row.get("last_date")), default=None)
        freshness = dashboard_freshness(pg, last_valid_session=last_valid_session)
        from screening import excluded_symbols, universe_layer2, universe_layer3, load_index_membership
        symbols = [row["symbol"] for row in rows]
        excluded = excluded_symbols(pg, market="TH")
        layer2_map = universe_layer2(pg, symbols)
        layer3_map = universe_layer3(pg, symbols)
        set50_set = load_index_membership(pg)
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
    with open(SNAPSHOT_JSON, "w") as file:
        json.dump({"scan_time": scan_time, "market": "TH",
                   "refresh": "progressive_cards", "items": items,
                   "stage_meta": stage_meta, "stage_counts": stage_counts}, file,
                  separators=(",", ":"))
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
    page = (template
            .replace("__ITEMS__", json.dumps(items, separators=(",", ":")))
            .replace("__STAGE_META__", json.dumps(stage_meta, separators=(",", ":"))))
    with open(OUT_HTML, "w") as file:
        file.write(page)
    return {"securities": len(items), "groups": counts, "out": OUT_HTML}

if __name__ == "__main__":
    print(build())
