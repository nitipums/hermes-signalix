"""Signalix Phase 2 — DB-backed screening engine.

Reads price_data from PostgreSQL (the SET EOD archive ingested by ingest.py),
NOT yfinance. The market benchmark for RS Rating is the 'SET' index symbol,
which lives in the same price_data table.

Deterministic computation only — NO LLM here. Reuses the pure-math functions
from scanner.py (trend_template / detect_vcp / compute_rs_rating /
position_sizing) so the calculation is identical whether the data came from
yfinance or the local archive.

Used by:
  - app.py  /scan endpoint (publishes candidates to Redis + stores in DB)
  - scripts / cron for a daily universe scan
"""
import os
import warnings
import datetime as dt

warnings.filterwarnings("ignore")

import psycopg2
import psycopg2.extras
import pandas as pd
import numpy as np

# Pure deterministic math lives in signal_core; scanner.py remains transitional legacy.
from signal_core import (
    compute_rs_rating,
    compute_rs_percentile,
    detect_vcp,
    trend_template,
    position_sizing,
    buy_zone,
    trade_readiness,
    MIN_DAYS,
    VCP_PERIOD,
    RS_THRESHOLD,
    RS_LOOKBACK,
)
from daily_setup_state import classify_daily_state
from stage_classifier import classify_stage
from setup_state import compute_setup_state
from ranking import compute_symbol_ranking, RANKING_WEIGHTS

CONDITION_LABELS = {
    "c1_price_above_150ma": "Price above MA150",
    "c2_150ma_above_200ma": "MA150 above MA200",
    "c3_200ma_uptrend": "MA200 trending upward",
    "c4_50ma_above_150ma": "MA50 above MA150",
    "c5_price_above_50ma": "Price above MA50",
    "c6_25pct_above_52wlow": "Price at least 25% above the 52-week low",
    "c7_within_25pct_52whigh": "Price within 25% of the 52-week high",
    "c8_rs_above_threshold": f"RS percentile at or above {RS_THRESHOLD}",
}

PG_DSN = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "user": os.getenv("POSTGRES_USER", "signalix"),
    "password": os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
    "dbname": os.getenv("POSTGRES_DB", "signalix"),
}
# Market benchmark symbol held in price_data (the SET index itself).
MARKET_SYMBOL = os.getenv("MARKET_SYMBOL", "SET")
# For the scan we only care about names that are currently tradeable-ish:
# latest row within this many days of the newest date in the DB.
MAX_STALE_DAYS = int(os.getenv("MAX_STALE_DAYS", "10"))
SCAN_LOOKBACK = int(os.getenv("SIGNALIX_SCAN_LOOKBACK", "360"))
MIN_TODAY_TRADE_VALUE = 15_000_000.0
MIN_SCAN_PRICE = 0.60


def scan_exclusion_reason(df, min_price=MIN_SCAN_PRICE,
                          min_today_trade_value=MIN_TODAY_TRADE_VALUE):
    """Return a policy-driven pre-scan exclusion reason, or None.

    Thresholds are explicit market policy, rather than an accidental inheritance
    of Thailand's price/currency rules by a different market.
    """
    if df is None or len(df) < 2:
        return "insufficient_history"
    close = float(df["Close"].iloc[-1])
    volume = float(df["Volume"].iloc[-1] or 0)
    if min_price is not None and close < float(min_price):
        return "price_below_minimum"
    if (min_today_trade_value is not None and
            close * volume < float(min_today_trade_value)):
        return "low_today_trade_value"
    return None


def get_pg():
    return psycopg2.connect(**PG_DSN)


# Symbol master: delisted / inactive names are marked (after the 60m backfill
# proved Settrade has no data for them) and MUST be excluded from the scan and
# the primary dashboard. They remain inspectable on a separate "delisted" page.
# Returns a set of symbols whose status != 'active'.
def excluded_symbols(pg=None, market="TH"):
    own = pg is None
    if own:
        pg = get_pg()
    try:
        cur = pg.cursor()
        cur.execute("SELECT to_regclass('public.symbol_master')")
        if not cur.fetchone()[0]:
            return set()
        # Seed the master from the ORD universe if it exists but is empty, so the
        # gate never wrongly excludes everything before a backfill run.
        cur.execute("SELECT COUNT(*) FROM symbol_master")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO symbol_master(symbol, instrument_type, status) "
                "SELECT DISTINCT symbol, instrument_type, 'active' FROM price_data "
                "WHERE market=%s AND instrument_type='ORD' ON CONFLICT (symbol) DO NOTHING",
                (market.upper(),),
            )
            pg.commit()
        cur.execute("SELECT symbol FROM symbol_master WHERE status <> 'active'")
        out = {r[0] for r in cur.fetchall()}
        cur.close()
        return out
    finally:
        if own:
            pg.close()


def _rows_to_df(rows):
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    return df


def load_symbol(symbol, pg=None, lookback=None, market="TH", as_of_date=None):
    """Return a market-scoped OHLCV DataFrame (Date-indexed), or None."""
    own = pg is None
    if own:
        pg = get_pg()
    try:
        cur = pg.cursor()
        if lookback:
            if as_of_date is not None:
                cur.execute(
                    "SELECT date, open, high, low, close, volume FROM price_data "
                    "WHERE market=%s AND symbol=%s AND date<=%s ORDER BY date DESC LIMIT %s",
                    (market.upper(), symbol, as_of_date, int(lookback)),
                )
            else:
                cur.execute(
                    "SELECT date, open, high, low, close, volume FROM price_data "
                    "WHERE market=%s AND symbol=%s ORDER BY date DESC LIMIT %s",
                    (market.upper(), symbol, int(lookback)),
                )
            rows = cur.fetchall()
            rows.reverse()
        else:
            suffix = " AND date<=%s" if as_of_date is not None else ""
            params = (market.upper(), symbol, as_of_date) if as_of_date is not None else (market.upper(), symbol)
            cur.execute("SELECT date, open, high, low, close, volume FROM price_data "
                        "WHERE market=%s AND symbol=%s" + suffix + " ORDER BY date ASC", params)
            rows = cur.fetchall()
        cur.close()
    finally:
        if own:
            pg.close()
    return _rows_to_df(rows)


def load_symbol_intraday(symbol, pg=None, interval="60m", lookback=400, market="TH"):
    """Return an interval-scoped OHLCV DataFrame (timestamp-indexed), or None.

    This loader is reserved for explicitly intraday paths. It must not be used
    as a fallback for Daily/stage calculations.
    """
    own = pg is None
    if own:
        pg = get_pg()
    try:
        cur = pg.cursor()
        cur.execute(
            "SELECT ts, open, high, low, close, volume FROM intraday_price_data "
            "WHERE symbol=%s AND interval=%s ORDER BY ts DESC LIMIT %s",
            (symbol, interval, int(lookback)),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        if own:
            pg.close()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    return df


def load_market(pg=None, lookback=400, market="TH", benchmark_symbol=None, as_of_date=None):
    """Return a market's benchmark series for relative-strength computation."""
    return load_symbol(benchmark_symbol or MARKET_SYMBOL, pg=pg, lookback=lookback,
                       market=market, as_of_date=as_of_date)


def _active_symbols(pg, min_history=MIN_DAYS, instrument_types=("ORD",), market="TH"):
    """Active market-scoped instruments with sufficient history and a recent bar."""
    cur = pg.cursor()
    cur.execute("SELECT MAX(date) FROM price_data WHERE market=%s", (market.upper(),))
    max_date = cur.fetchone()[0]
    cur.close()
    if max_date is None:
        return []
    cutoff = max_date - dt.timedelta(days=MAX_STALE_DAYS)
    cur = pg.cursor()
    cur.execute(
        "SELECT symbol, COUNT(*) AS n, MAX(date) AS last_date "
        "FROM price_data WHERE market=%s AND instrument_type = ANY(%s) GROUP BY symbol "
        "HAVING COUNT(*) >= %s AND MAX(date) >= %s "
        "ORDER BY symbol",
        (market.upper(), list(instrument_types), min_history, cutoff),
    )
    rows = cur.fetchall()
    cur.close()
    return [r[0] for r in rows]


def _active_scan_symbols(pg, min_history=0, instrument_types=("ORD",),
                         market="TH", min_price=None,
                         min_today_trade_value=None):
    """Return ALL active ORD symbols present in the database (no staleness or
    price/volume/bar-count pre-filter).

    Owner's architecture rule: Layer-1 (stage scan) runs on the FULL universe.
    Only instrument TYPE is filtered (ORD). Stale names are still scanned and
    flagged stale downstream — never hidden by a pre-filter.

    Excluded (delisted/inactive) symbols from symbol_master are dropped: they
    have no live Settrade data so scanning them is wasted work and they must
    not appear in the primary dashboard.
    """
    excluded = excluded_symbols(pg, market=market)
    cur = pg.cursor()
    # symbol_master is the authoritative universe.  Keep the price_data query
    # only as a compatibility fallback for databases predating the master;
    # missing price rows must remain visible to scan_universe as insufficient
    # Daily evidence rather than disappearing from coverage.
    cur.execute("SELECT to_regclass('public.symbol_master')")
    master_exists = bool(cur.fetchone()[0])
    if master_exists:
        cur.execute("""\
            SELECT symbol
            FROM symbol_master
            WHERE instrument_type = ANY(%s)
              AND (status IS NULL OR status = 'active')
            ORDER BY symbol
        """, (list(instrument_types),))
    else:
        cur.execute("""\
            SELECT symbol
            FROM price_data
            WHERE market = %s AND instrument_type = ANY(%s)
            GROUP BY symbol
            ORDER BY symbol
        """, (market.upper(), list(instrument_types),))
    rows = cur.fetchall()
    cur.close()
    return [r[0] for r in rows if r[0] not in excluded]


def _universe_rs_ranks(pg, market_series, symbols):
    """Return the authoritative rank-based RS rating for each symbol."""
    if market_series is None or len(market_series) < RS_LOOKBACK:
        return {sym: 0.0 for sym in symbols}
    m_ret = (market_series["Close"].iloc[-1] /
             market_series["Close"].iloc[-RS_LOOKBACK] - 1)
    rel_returns = {}
    for sym in symbols:
        df = load_symbol(sym, pg=pg, lookback=SCAN_LOOKBACK)
        if df is None or len(df) < MIN_DAYS:
            continue
        c = df["Close"]
        rel_returns[sym] = c.iloc[-1] / c.iloc[-RS_LOOKBACK] - 1 - m_ret
    if not rel_returns:
        return {}
    ranks = pd.Series(rel_returns).rank(pct=True) * 100
    return {sym: float(value) for sym, value in ranks.items()}


def ranked_rs_for_symbol(symbol, pg=None, market_series=None):
    """Return rank-based RS percentile for one symbol using the active universe.

    RS percentile needs peer context. This helper makes `/screen/{symbol}`
    consistent with `/scan`: compute 1y relative returns for the active universe,
    rank them 0-100, then return this symbol's percentile.
    """
    own = pg is None
    if own:
        pg = get_pg()
    try:
        if market_series is None:
            market_series = load_market(pg=pg, lookback=400)
        if market_series is None or len(market_series) < RS_LOOKBACK:
            return None
        m_ret = market_series["Close"].iloc[-1] / market_series["Close"].iloc[-RS_LOOKBACK] - 1
        rel_returns = {}
        for sym in _active_symbols(pg):
            df = load_symbol(sym, pg=pg, lookback=SCAN_LOOKBACK)
            if df is None or len(df) < MIN_DAYS:
                continue
            c = df["Close"]
            rel_returns[sym] = c.iloc[-1] / c.iloc[-RS_LOOKBACK] - 1 - m_ret
        if symbol not in rel_returns:
            return None
        ranks = pd.Series(rel_returns).rank(pct=True) * 100
        return float(ranks.get(symbol))
    finally:
        if own:
            pg.close()


def analyze_symbol_db_ranked(symbol, pg=None):
    """Single-symbol analysis with the same rank-based RS semantics as /scan."""
    own = pg is None
    if own:
        pg = get_pg()
    try:
        market_series = load_market(pg=pg, lookback=400)
        rs = ranked_rs_for_symbol(symbol, pg=pg, market_series=market_series)
        return analyze_symbol_db(symbol, pg=pg, market_series=market_series, rs_rating=rs)
    finally:
        if own:
            pg.close()


def insufficient_history_row(symbol, df, rs_rating=0.0):
    """Keep a symbol visible without inventing technical signals.

    Full ORD scans must not drop an active symbol merely because its daily
    history is shorter than the MA200/52-week calculation window. The row is
    explicit non-signal state; downstream UI can show INSUFFICIENT HISTORY.
    """
    close = float(df["Close"].iloc[-1]) if df is not None and len(df) else None
    previous = float(df["Close"].iloc[-2]) if df is not None and len(df) > 1 else None
    change = ((close / previous - 1) * 100) if close is not None and previous else None
    volume = float(df["Volume"].iloc[-1] or 0) if df is not None and len(df) else 0.0
    last_date = df.index[-1].strftime("%Y-%m-%d") if df is not None and len(df) else None
    return {
        "symbol": symbol, "analysis_status": "INSUFFICIENT_HISTORY",
        "close": close, "change": change, "volume": volume,
        "trade_value": (close * volume) if close is not None else None,
        "last_date": last_date, "trend_source": "daily",
        "trend_template": {"pass": False, "conditions_met": 0,
                            "reason": "insufficient history", "conditions": {},
                            "ma": {}, "rs_rating": float(rs_rating or 0.0)},
        "vcp": {"is_vcp": False, "contractions": [], "latest_contraction_pct": 0.0},
        "buy_zone": {"50": None, "62": None},
        "trade_readiness": {"status": "INSUFFICIENT_HISTORY",
                             "readiness_status": "INSUFFICIENT_HISTORY",
                             "reason": "Not enough daily bars for MA200/52-week analysis.",
                             "buy_zones_90d": {}, "near_buy_zone": False},
        "position_sizing": {}, "suggested_stop": None,
        "daily_state": {
            "stage": "S1_basing", "phase": "insufficient_history",
            "primary_state": "base_forming",
            "stage_label": "Stage 1 · Basing", "phase_label": "Insufficient history",
            "setup_quality": {"pass": False, "reasons": ["insufficient_history"]},
            "setup_proximity": {"state": None, "pivot": None, "distance_pct": None, "zone": None},
            "trend_source": "daily", "data_freshness": "unknown",
        },
    }


def analysis_error_row(symbol, reason_code="analysis_exception"):
    """Keep a failed Daily analysis visible without inventing evidence.

    This is an observation of unavailable/invalid analysis, not a market
    signal.  In particular, all price and indicator fields remain unknown.
    """
    return {
        "symbol": symbol,
        "analysis_status": "NOT_VERIFIED",
        "reason_codes": [reason_code],
        "reason": "Daily analysis failed; no actionable state was produced.",
        "close": None,
        "change": None,
        "volume": 0.0,
        "trade_value": None,
        "last_date": None,
        "trend_source": "daily",
        "trend_template": {
            "pass": False, "conditions_met": 0,
            "reason": reason_code, "conditions": {},
            "ma": {}, "rs_rating": 0.0,
        },
        "vcp": {"is_vcp": False, "contractions": [], "latest_contraction_pct": 0.0},
        "buy_zone": {"50": None, "62": None},
        "trade_readiness": {
            "status": "NOT_VERIFIED",
            "readiness_status": "NOT_VERIFIED",
            "reason": "Daily analysis failed; no actionable state was produced.",
            "buy_zones_90d": {}, "near_buy_zone": False,
        },
        "position_sizing": {},
        "suggested_stop": None,
        "daily_state": {
            "stage": "S1_basing", "phase": "not_verified",
            "primary_state": "not_verified",
            "stage_label": "Stage 1 · Basing", "phase_label": "Not verified",
            "setup_quality": {"pass": False, "reasons": [reason_code]},
            "setup_proximity": {"state": None, "pivot": None,
                                 "distance_pct": None, "zone": None},
            "trend_source": "daily", "data_freshness": "unknown",
        },
    }


def analyze_symbol_db(symbol, pg=None, market_series=None, rel_return=None, rs_rating=None, df=None):
    """Full Minervini pipeline for one symbol, reading from PostgreSQL.

    market_series: optional pre-loaded SET Close series (reused across the
    universe scan to avoid re-querying for every symbol).
    rel_return: optional precomputed relative return (stock_1y_ret - market_1y_ret).
    rs_rating: optional precomputed percentile RS (used in the universe scan
    where all symbols are processed together so ranks span the whole cohort).
    df: optional pre-loaded OHLCV DataFrame. When supplied, the DB is NOT
    queried again for this symbol (the universe scan already fetched it in
    pass 1), eliminating a duplicate per-symbol SELECT.
    """
    own = pg is None
    if own:
        pg = get_pg()
    try:
        if df is None:
            df = load_symbol(symbol, pg=pg, lookback=SCAN_LOOKBACK)
        if df is None:
            return None
        if len(df) < MIN_DAYS:
            return insufficient_history_row(symbol, df, rs_rating=rs_rating)
        if market_series is None:
            market_series = load_market(pg=pg, lookback=400)
        if rs_rating is None:
            # Single-symbol screening must use the same cohort percentile as
            # /scan; the old stock-vs-SET linear score made endpoints disagree.
            ranks = _universe_rs_ranks(pg, market_series, _active_symbols(pg))
            rs = ranks.get(symbol, 0.0)
        else:
            rs = float(rs_rating)
    finally:
        if own:
            pg.close()

    tt = trend_template(df, rs)
    tt["rs_threshold"] = RS_THRESHOLD
    tt["failed_conditions"] = [
        {"key": key, "label": CONDITION_LABELS.get(key, key)}
        for key, passed in tt.get("conditions", {}).items() if not passed
    ]
    vcp = detect_vcp(df["High"], df["Low"], period=VCP_PERIOD)
    bz = buy_zone(df)
    readiness = trade_readiness(df, tt, bz)
    # Tighter of the structural low or -7% hard stop: higher stop price.
    suggested_stop = readiness["stop_loss"]
    ps = position_sizing(df["Close"].iloc[-1], suggested_stop)
    latest_close = float(df["Close"].iloc[-1])
    previous_close = float(df["Close"].iloc[-2]) if len(df) > 1 else None
    analysis_metrics = {
        "ma20": float(df["Close"].rolling(20).mean().iloc[-1]),
        "ma50": tt.get("ma", {}).get("ma50"),
        "ma150": tt.get("ma", {}).get("ma150"),
        "ma200": tt.get("ma", {}).get("ma200"),
        "max_20d": float(df["High"].tail(20).max()),
        "min_20d": float(df["Low"].tail(20).min()),
        "max_52w": tt.get("ma", {}).get("hi_52"),
        "min_52w": tt.get("ma", {}).get("lo_52"),
        "rsi14": readiness.get("rsi_daily"),
        "volume_ratio_50": readiness.get("volume_ratio_50"),
        "trade_value": latest_close * float(df["Volume"].iloc[-1] or 0),
        "volume": float(df["Volume"].iloc[-1] or 0),
        "daily_change_pct": ((latest_close / previous_close - 1) * 100
                              if previous_close else None),
    }
    return {
        "symbol": symbol,
        "last_date": df.index[-1].strftime("%Y-%m-%d"),
        "close": round(float(df["Close"].iloc[-1]), 2),
        "analysis_metrics": analysis_metrics,
        "trend_template": tt,
        "vcp": vcp,
        "buy_zone": bz,
        "trade_readiness": readiness,
        "position_sizing": ps,
        "suggested_stop": round(float(suggested_stop), 2),
        "scan_time": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


# v2 state contract: single canonical stage-first classifier (Stage 1-4 +
# phase) replaces the legacy action-first grouping below. Kept as ONE function.
def group_scan_results(results, events=None):
    """Classify each eligible symbol into one Daily trade-story state."""
    groups = {key: [] for key in (
        "breakout_new", "uptrend_pullback", "waiting_breakout", "base", "down_or_broken", "benchmark",
    )}
    events = events or {}
    for row in results:
        trend = row["trend_template"]
        readiness = row.get("trade_readiness", {})
        close = float(row.get("close") or 0)
        fibs = [float(value) for value in (readiness.get("buy_zones_90d") or {}).values()
                if value is not None]
        near_pullback = readiness.get("near_buy_zone") or any(
            close > 0 and abs(close - level) / close <= 0.04 for level in fibs
        )
        vcp = (row.get("vcp") or {}).get("is_vcp", False)
        evidence = {
            "close": close,
            "ma50": (trend.get("ma") or {}).get("ma50"),
            "ma150": (trend.get("ma") or {}).get("ma150"),
            "ma200": (trend.get("ma") or {}).get("ma200"),
            "above_ma50": readiness.get("above_ma50"),
            "above_ma150": readiness.get("above_ma150"),
            "above_ma200": readiness.get("above_ma200"),
            "ma50_slope_20d_pct": readiness.get("ma50_slope_20d_pct"),
            "ma150_slope_20d_pct": readiness.get("ma150_slope_20d_pct"),
            "ma200_slope_20d_pct": readiness.get("ma200_slope_20d_pct"),
            "macd": readiness.get("macd"),
            "rolling_trigger": readiness.get("breakout_level_20d"),
            "volume_ratio_50": readiness.get("volume_ratio_50"),
            "rsi_daily": readiness.get("rsi_daily"),
            "trend_template_conditions": trend.get("conditions_met"),
            "rs_rating": trend.get("rs_rating"),
            "rs_threshold": trend.get("rs_threshold"),
            "range_20d_pct": readiness.get("range_20d_pct"),
            "near_pullback_reference": near_pullback,
            "vcp": vcp,
            "buy_zones_90d": readiness.get("buy_zones_90d"),
            "swing_high_90d": readiness.get("swing_high_90d"),
            "readiness_status": readiness.get("status"),
            "last_date": row.get("last_date"),
            "latest_scan_date": max((x.get("last_date") for x in results if x.get("last_date")), default=row.get("last_date")),
            "trend_source": row.get("trend_source", "daily"),
        }
        # Single canonical classifier: Stage 1-4 (Minervini) + phase.
        state = classify_stage(evidence, events.get(row["symbol"]))
        if row.get("analysis_status") == "INSUFFICIENT_HISTORY":
            state["phase"] = "insufficient_history"
            state["phase_label"] = "Insufficient history"
            state["primary_state"] = "base_forming"
            state["setup_quality"] = {"pass": False, "reasons": ["insufficient_history"]}
            state["setup_proximity"] = {"state": None, "pivot": None, "distance_pct": None, "zone": None}
        elif row.get("analysis_status") == "NOT_VERIFIED":
            state["phase"] = "not_verified"
            state["phase_label"] = "Not verified"
            state["primary_state"] = "not_verified"
            state["setup_quality"] = {"pass": False, "reasons": row.get("reason_codes", ["analysis_exception"])}
            state["setup_proximity"] = {"state": None, "pivot": None, "distance_pct": None, "zone": None}
        # Two-layer actionable setup state (quality gate + proximity timing).
        # Attached at source so every serialization path (build/snapshot) inherits it.
        # Insufficient-history rows already have an explicit fail/null contract;
        # never let the generic classifier overwrite it.
        if row.get("analysis_status") not in ("INSUFFICIENT_HISTORY", "NOT_VERIFIED"):
            _setup = compute_setup_state(state["stage"], evidence)
            state["setup_quality"] = _setup["quality"]
            state["setup_proximity"] = _setup["proximity"]
        if row.get("last_date") and evidence.get("latest_scan_date") and row["last_date"] != evidence["latest_scan_date"]:
            state["data_freshness"] = "stale"
        # New-listing flag: trend derived from 60m intraday, not daily history.
        if evidence.get("trend_source") == "intraday_60m":
            state["trend_source"] = "intraday_60m"
            state["is_new_listing"] = True
        stage = state["stage"]
        phase = state["phase"]
        # One level-one dashboard group derived from (stage, phase).
        if stage == "S2_uptrend" and phase in ("breakout_new", "breakout_extended"):
            key = "breakout_new"
        elif stage == "S2_uptrend" and phase == "uptrend_pullback":
            key = "uptrend_pullback"
        elif stage == "S2_uptrend" and phase == "waiting_breakout":
            key = "waiting_breakout"
        elif stage == "S1_basing":
            key = "base"
        elif stage in ("S3_distributing", "S4_down") or phase in ("broken", "declining"):
            key = "down_or_broken"
        else:
            key = "waiting_breakout"
        row["daily_state"] = state
        row["scan_group"] = key
        row["group_reason"] = f"{state['stage_label']} · {state['phase_label']}"
        
        # Compute ranking (Contract v0.2.0 §5)
        regime_state = None
        if row.get("market_regime"):
            regime_state = row["market_regime"].get("regime_state")
        compute_symbol_ranking(row, regime_state)
        
        groups[key].append(row)
    for values in groups.values():
        # Sort by ranking total_score (descending), fallback to RS rating
        values.sort(key=lambda row: (
            row.get("ranking", {}).get("total_score") is not None,
            row.get("ranking", {}).get("total_score") or 0.0,
            row.get("trend_template", {}).get("rs_rating", 0.0)
        ), reverse=True)
    return groups


def annotate_all_time_highs(pg, results, market="TH"):
    """Attach ATH levels from a persisted cache; scan only today's highs."""
    if not results:
        return
    symbols = [r["symbol"] for r in results]
    cur = pg.cursor()
    cur.execute("""SELECT symbol,all_time_high,prior_all_time_high,latest_high,last_seen_date
                   FROM daily_symbol_ath_cache
                   WHERE market=%s AND symbol=ANY(%s)""", (market.upper(), symbols))
    cached = {sym: (float(all_high), float(prior) if prior is not None else None,
                    float(latest) if latest is not None else None, last_date)
              for sym, all_high, prior, latest, last_date in cur.fetchall()}
    missing = [sym for sym in symbols if sym not in cached]
    if missing:
        # One-time initialization for symbols never seen by the cache.
        cur.execute("""
            WITH latest AS (
              SELECT symbol, MAX(date) AS last_date FROM price_data
              WHERE market=%s AND symbol=ANY(%s) GROUP BY symbol
            )
            SELECT p.symbol, MAX(p.high),
                   MAX(p.high) FILTER (WHERE p.date < l.last_date),
                   MAX(p.high) FILTER (WHERE p.date = l.last_date), l.last_date
            FROM price_data p JOIN latest l ON p.symbol=l.symbol AND p.market=%s
            GROUP BY p.symbol,l.last_date
        """, (market.upper(), missing, market.upper()))
        for sym, all_high, prior, latest, last_date in cur.fetchall():
            cached[sym] = (float(all_high), float(prior) if prior is not None else None,
                           float(latest) if latest is not None else None, last_date)
            cur.execute("""INSERT INTO daily_symbol_ath_cache
                           (market,symbol,all_time_high,prior_all_time_high,latest_high,last_seen_date)
                           VALUES (%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (market,symbol) DO NOTHING""",
                        (market.upper(), sym, all_high, prior, latest, last_date))
    cur.execute("""SELECT DISTINCT ON (symbol) symbol,date,high
                   FROM price_data WHERE market=%s AND symbol=ANY(%s)
                   ORDER BY symbol,date DESC""", (market.upper(), symbols))
    latest_rows = {sym: (last_date, float(high)) for sym, last_date, high in cur.fetchall()}
    ath = {}
    for sym in symbols:
        old = cached.get(sym)
        today = latest_rows.get(sym)
        if not old or not today:
            continue
        all_high, prior, _latest, _old_date = old
        today_date, today_high = today
        if today_high > all_high:
            cur.execute("""UPDATE daily_symbol_ath_cache
                           SET prior_all_time_high=all_time_high,
                               all_time_high=%s, latest_high=%s,
                               last_seen_date=%s, updated_at=NOW()
                           WHERE market=%s AND symbol=%s""",
                        (today_high, today_high, today_date, market.upper(), sym))
            prior = all_high
            all_high = today_high
        ath[sym] = (all_high, prior, today_high)
    pg.commit()
    cur.close()
    for r in results:
        all_high, prior, latest = ath.get(r["symbol"], (None, None, None))
        r["all_time_high"] = round(all_high, 2) if all_high is not None else None
        r["prior_all_time_high"] = round(prior, 2) if prior is not None else None
        r["ath_distance_pct"] = (round((r["close"] / all_high - 1) * 100, 2)
                                 if all_high else None)
        r["ath_breakout_close"] = bool(prior is not None and r["close"] >= prior)
        r["ath_tested_today"] = bool(prior is not None and latest is not None and latest >= prior)


def scan_universe(min_conditions=8, limit=None, pg=None, market="TH",
                  benchmark_symbol=None, symbols=None, min_price=MIN_SCAN_PRICE,
                  min_today_trade_value=None, as_of_date=None, annotate_ath=True):
    """Run the identical deterministic scanner over an explicit market universe.

    ``market`` scopes storage; ``benchmark_symbol`` supplies the RS comparator;
    ``symbols`` turns a broad market scan into a curated watchlist scan.  The
    Minervini/VCP/Fib mathematics is unchanged across both modes.
    """
    own = pg is None
    if own:
        pg = get_pg()
    try:
        market = market.upper()
        benchmark_symbol = benchmark_symbol or (MARKET_SYMBOL if market == "TH" else None)
        if not benchmark_symbol:
            raise ValueError("benchmark_symbol is required for a non-TH market")
        excluded = excluded_symbols(pg, market=market)
        market_series = load_market(pg=pg, lookback=400, market=market,
                                    benchmark_symbol=benchmark_symbol, as_of_date=as_of_date)
        symbol_list = (list(symbols) if symbols is not None else
                       _active_scan_symbols(pg, instrument_types=("ORD",), market=market))
        symbol_list = [s for s in symbol_list if s not in excluded]
        closes, rel_returns, trend_sources = {}, {}, {}
        insufficient_daily = {}
        daily_load_errors = {}
        m_ret = (market_series["Close"].iloc[-1] / market_series["Close"].iloc[-RS_LOOKBACK] - 1
                 if market_series is not None and len(market_series) >= RS_LOOKBACK else 0.0)
        for sym in symbol_list:
            try:
                df = load_symbol(sym, pg=pg, lookback=SCAN_LOOKBACK, market=market,
                                 as_of_date=as_of_date)
            except Exception:
                # Preserve coverage even when the Daily loader fails for one
                # symbol. No fallback timeframe is permitted here.
                daily_load_errors[sym] = "daily_load_exception"
                continue
            if df is None or len(df) < MIN_DAYS:
                # Daily/stage metrics must never be calculated from 60m bars.
                # Keep the symbol visible as an explicit fail-closed observation.
                insufficient_daily[sym] = df
                continue
            trend_source = "daily"
            c = df["Close"]
            rel_returns[sym] = c.iloc[-1] / c.iloc[-RS_LOOKBACK] - 1 - m_ret
            closes[sym] = df
            trend_sources[sym] = trend_source
        ranks = pd.Series(rel_returns).rank(pct=True) * 100
        results, all_results = [], []
        for sym in symbol_list:
            df = closes.get(sym)
            try:
                if sym in insufficient_daily:
                    row = insufficient_history_row(sym, insufficient_daily[sym])
                elif sym in daily_load_errors:
                    row = analysis_error_row(sym, daily_load_errors[sym])
                else:
                    row = analyze_symbol_db(sym, pg=pg, market_series=market_series,
                                            rs_rating=ranks.get(sym, 0.0), df=df)
            except Exception:
                row = analysis_error_row(sym)
            if row is None:
                row = analysis_error_row(sym, "analysis_unavailable")
            row["market"] = market
            row["benchmark_symbol"] = benchmark_symbol
            row["trend_source"] = trend_sources.get(sym, "daily")
            all_results.append(row)
            if row["trend_template"]["conditions_met"] >= min_conditions:
                results.append(row)
        if annotate_ath:
            annotate_all_time_highs(pg, all_results, market=market)
    finally:
        if own:
            pg.close()
    results.sort(key=lambda row: (row["trend_template"]["conditions_met"],
                                   row["trend_template"]["rs_rating"]), reverse=True)
    near_miss = [row for row in all_results if row["trend_template"]["conditions_met"] == 6]
    near_miss.sort(key=lambda row: row["trend_template"]["rs_rating"], reverse=True)
    return results, near_miss


def load_evaluated_ord_rows(pg=None, *, market="TH", symbols=None,
                            as_of_date=None, annotate_ath=False):
    """Return every evaluated Thai ORD row, including fail-closed rows.

    This bounded adapter reuses the existing full-universe scanner with a
    permissive condition threshold.  It intentionally applies no VCP filter;
    callers may project rows into the setup-candidate contract afterwards.
    """
    rows, _near_miss = scan_universe(
        min_conditions=-1,
        pg=pg,
        market=market,
        symbols=symbols,
        as_of_date=as_of_date,
        annotate_ath=annotate_ath,
    )
    return rows


# Keep the adapter discoverable under the universe terminology used by the
# setup-candidate pipeline.
evaluate_ord_universe = load_evaluated_ord_rows


if __name__ == "__main__":
    import json

    cands, near = scan_universe(min_conditions=8)
    payload = {
        "scan_time": dt.datetime.now(dt.timezone.utc).isoformat(),
        "full_trend_template": cands,
        "near_miss_6of8": near,
    }
    out_path = os.path.join(os.path.dirname(__file__), "scan_results.json")
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"Full Trend Template (8/8) candidates: {len(cands)}")
    for r in cands[:25]:
        tt = r["trend_template"]
        print(f"  {r['symbol']:10s} {r['close']:>9.2f}  RS={tt['rs_rating']:5.1f}  "
              f"TT={tt['conditions_met']}/8  VCP={r['vcp']['is_vcp']}  "
              f"stop={r['suggested_stop']}")
    print(f"\nResults written to {out_path}")


# --- Layer 2: short-term MINOR-TREND (structural) grouping on 60m bars (no scoring) ---
# Replaces the old oscillator read (RSI/MACD). Classifies the *structure* of the
# short-term swing, not momentum extremes. Five groups (Q14):
#   up_leg     - higher highs + higher lows (minor uptrend)
#   pullback   - dip inside an uptrend (higher lows but short-term slope down)
#   tight_base - narrow sideways consolidation
#   down_leg   - lower highs + lower lows (minor downtrend)
#   bounce     - short rebound inside a downtrend (lower lows but slope turning up)
def _ma_slope(close, n=20):
    if len(close) < n + 5:
        return 0.0
    ma = close.rolling(n).mean()
    now = float(ma.iloc[-1])
    prev = float(ma.iloc[-5])
    return (now - prev) / now if now else 0.0

def _swing_points(close, window=2):
    """Return list of (idx, price, kind) pivots; kind in {'H','L'}."""
    n = len(close)
    pivots = []
    if n < 2 * window + 1:
        return pivots
    for i in range(window, n - window):
        price = float(close.iloc[i])
        seg = [float(close.iloc[j]) for j in range(i - window, i + window + 1) if j != i]
        if all(price > s for s in seg):
            pivots.append((i, price, 'H'))
        elif all(price < s for s in seg):
            pivots.append((i, price, 'L'))
    return pivots

def compute_layer2(symbol, df_60m):
    """Classify the minor (short-term) trend STRUCTURE on 60m bars — the L2 axis
    is a *structural* minor-trend read, NOT a momentum/oscillator read (Q9b).

    Five groups (Q14):
      up_leg     - uptrend, minor leg also advancing (HH/HL)
      pullback   - uptrend, minor leg dipping but higher-low structure intact
      tight_base - narrow consolidation (negligible recent range)
      down_leg   - downtrend, minor leg also declining (LH/LL)
      bounce     - downtrend, minor leg lifting but lower-high structure intact

    Structure (swing highs/lows) decides pullback vs up_leg and bounce vs
    down_leg; a short dip that still holds higher lows is a pullback, not a
    trend break. Never returns None: missing/short 60m data falls back to
    tight_base so every symbol is classified (Q18).
    """
    default = {"signals": {"structure": "flat", "swing": "none", "long_slope": 0.0, "short_slope": 0.0}, "group": "tight_base"}
    if df_60m is None or len(df_60m) < 30:
        return default
    close = df_60m["Close"].astype(float)
    long_slope = _ma_slope(close, 50)
    short_slope = _ma_slope(close, 10)
    pivots = _swing_points(close, window=2)
    recent = close.iloc[-20:]
    amp = (float(recent.max()) - float(recent.min())) / float(recent.mean()) if len(recent) else 0.0
    signals = {"structure": "mixed", "long_slope": round(long_slope, 4), "short_slope": round(short_slope, 4)}
    if len(pivots) < 3:
        # Not enough swing structure: fall back to primary-trend slope.
        if amp < 0.015:
            group = "tight_base"
        elif long_slope > 0:
            group = "up_leg"
        elif long_slope < 0:
            group = "down_leg"
        else:
            group = "tight_base"
        signals["structure"] = group
        return {"signals": signals, "group": group}
    last = pivots[-4:]
    highs = [p[1] for p in last if p[2] == 'H']
    lows = [p[1] for p in last if p[2] == 'L']
    hh = len(highs) >= 2 and highs[-1] > highs[0]
    hl = len(lows) >= 2 and lows[-1] > lows[0]
    lh = len(highs) >= 2 and highs[-1] < highs[0]
    ll = len(lows) >= 2 and lows[-1] < lows[0]
    swing_label = "HH/HL" if (hh and hl) else "LH/LL" if (lh and ll) else "mixed"
    signals["swing"] = swing_label
    if amp < 0.015:
        group = "tight_base"
    elif hl and not ll:
        group = "pullback"           # higher lows intact -> dip in uptrend
    elif ll and not hl:
        group = "bounce"            # lower highs intact -> rebound in downtrend
    elif hh and hl:
        group = "up_leg"
    elif lh and ll:
        group = "down_leg"
    elif long_slope > 0:
        group = "up_leg"
    elif long_slope < 0:
        group = "down_leg"
    else:
        group = "tight_base"
    signals["structure"] = group
    return {"signals": signals, "group": group}


def compute_layer2_momentum(symbol, df_60m):
    """MACD(12,26,9) + RSI(14) on 60m close. Returns signals + group."""
    default = {"signals": {"macd": "cross", "rsi": 50.0}, "group": "neutral"}
    if df_60m is None or len(df_60m) < 30:
        return default
    close = df_60m["Close"].astype(float)
    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line
    macd_now = float(macd_line.iloc[-1])
    signal_now = float(signal_line.iloc[-1])
    hist_now = float(hist.iloc[-1])
    hist_prev = float(hist.iloc[-2]) if len(hist) > 1 else 0.0
    if macd_now > signal_now and macd_now > 0:
        macd_state = "bullish"
    elif macd_now < signal_now and macd_now < 0:
        macd_state = "bearish"
    else:
        macd_state = "cross"
    # RSI(14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi_series = 100 - (100 / (1 + rs))
    rsi_now = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else 50.0
    # Group
    if rsi_now >= 70:
        group = "overbought"
    elif rsi_now <= 30:
        group = "oversold"
    elif macd_state == "bullish" and 50 <= rsi_now < 70:
        group = "strong"
    elif macd_state == "bullish":
        group = "up"
    elif macd_state == "bearish":
        group = "down"
    else:
        group = "neutral"
    return {
        "signals": {"macd": macd_state, "rsi": round(rsi_now, 2)},
        "group": group
    }


def compute_layer3_qualifier(symbol, df_daily, df_60m, snapshot):
    """Breakout quality 0-3 from volume/52wk/ATH. snapshot must have avgDailyValue20, high52, athHigh, close, volume."""
    flags = {"vol": False, "wk52": False, "ath": False}
    if not snapshot:
        return {"score": 0, "flags": flags}
    avg_val = snapshot.get("avgDailyValue20") or 0
    high52 = snapshot.get("high52")
    ath = snapshot.get("athHigh")
    close = snapshot.get("close")
    vol = snapshot.get("volume") or 0
    # Volume flag: today's trade value >= 2 * avgDailyValue20
    if avg_val > 0 and vol * close >= 2 * avg_val:
        flags["vol"] = True
    # 52wk flag: close > 52wk high
    if high52 is not None and close is not None and close > high52:
        flags["wk52"] = True
    # ATH flag: close > all-time high
    if ath is not None and close is not None and close > ath:
        flags["ath"] = True
    score = sum(flags.values())
    return {"score": score, "flags": flags}


def universe_layer2(pg, symbols):
    """Classify every symbol on both the structural and momentum axes.

    Missing/short 60m data is handled by the compute helpers, while an
    individual symbol failure gets a complete, schema-safe default.
    """
    structural_default = {
        "signals": {
            "structure": "flat",
            "long_slope": 0.0,
            "short_slope": 0.0,
            "swing": "error",
        },
        "group": "tight_base",
    }
    momentum_default = {
        "signals": {"macd": "cross", "rsi": 50.0},
        "group": "neutral",
    }
    out = {}
    for sym in symbols:
        try:
            df = load_symbol_intraday(sym, pg=pg, interval="60m", lookback=400)
            out[sym] = {
                "structural": compute_layer2(sym, df),
                "momentum": compute_layer2_momentum(sym, df),
            }
        except Exception:
            out[sym] = {
                "structural": structural_default.copy(),
                "momentum": momentum_default.copy(),
            }
    return out


def universe_layer3(pg, symbols):
    """Batch the daily breakout-quality qualifier for *symbols*.

    Daily bars come from ``load_symbol`` and intraday bars from the existing
    60m loader.  Snapshot data is read from the daily scan history tables;
    there is intentionally no dependency on a ``latest_snapshots`` table.
    """
    default = {"score": 0, "flags": {"vol": False, "wk52": False, "ath": False}}
    out = {}
    for sym in symbols:
        try:
            df_daily = load_symbol(sym, pg=pg, lookback=250)
            df_60m = load_symbol_intraday(sym, pg=pg, interval="60m", lookback=400)
            cur = pg.cursor()
            try:
                cur.execute("""
                    SELECT s.close, s.volume, s.max_52w, s.trade_value,
                           s.volume_ratio_50, s.metrics,
                           a.all_time_high
                    FROM daily_analysis_snapshots AS s
                    LEFT JOIN daily_symbol_ath_cache AS a
                      ON a.market = s.market AND a.symbol = s.symbol
                    WHERE s.market = 'TH' AND s.symbol = %s
                    ORDER BY s.analysis_date DESC, s.created_at DESC
                    LIMIT 1
                """, (sym,))
                row = cur.fetchone()
            finally:
                cur.close()

            snapshot = {}
            if row:
                close, volume, high52, trade_value, volume_ratio, metrics, ath = row
                metrics = metrics or {}
                if isinstance(metrics, str):
                    import json
                    metrics = json.loads(metrics)
                avg_value = next(
                    (metrics.get(key) for key in (
                        "avgDailyValue20", "avg_daily_value_20",
                        "avgTradeValue20", "avg_trade_value_20",
                    ) if metrics.get(key) is not None),
                    None,
                )
                if avg_value is None and trade_value is not None and volume_ratio:
                    avg_value = float(trade_value) / float(volume_ratio)
                snapshot = {
                    "avgDailyValue20": avg_value,
                    "high52": high52,
                    "athHigh": ath,
                    "close": close,
                    "volume": volume,
                }
            out[sym] = compute_layer3_qualifier(sym, df_daily, df_60m, snapshot)
        except Exception:
            out[sym] = {
                "score": default["score"],
                "flags": default["flags"].copy(),
            }
    return out

def load_index_membership(pg):
    cur = pg.cursor()
    # Prefer the normalized, historical table when present.  Keep the old
    # table as a compatibility fallback for deployments before migration 006.
    cur.execute("SELECT to_regclass('public.index_memberships')")
    if cur.fetchone()[0]:
        cur.execute("""SELECT DISTINCT symbol
                       FROM index_memberships
                       WHERE index_name = 'SET50'
                         AND effective_from <= CURRENT_DATE
                         AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)""")
        rows = {r[0] for r in cur.fetchall()}
        cur.close()
        return rows
    cur.execute("SELECT to_regclass('public.index_membership')")
    if not cur.fetchone()[0]:
        cur.close(); return set()
    cur.execute("SELECT symbol FROM index_membership WHERE is_set50 = TRUE")
    rows = {r[0] for r in cur.fetchall()}
    cur.close()
    return rows
