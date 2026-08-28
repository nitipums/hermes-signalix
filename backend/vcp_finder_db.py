"""DB adapter and isolated persistence for VCP Finder 60m."""
from __future__ import annotations

import json
from datetime import datetime, timezone
import psycopg2.extras

from instruments import active_ord_symbols
from vcp_finder import POLICY_VERSION, VCP60Config, find_vcp_60m, new_run_id


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS vcp_finder_60m_runs (
  run_id TEXT PRIMARY KEY,
  market TEXT NOT NULL,
  interval TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  as_of TIMESTAMPTZ NOT NULL,
  eligible_count INTEGER NOT NULL,
  evaluated_count INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ingestion_run_id TEXT,
  ingestion_status TEXT,
  fetch_completed_at TIMESTAMPTZ
);
ALTER TABLE vcp_finder_60m_runs ADD COLUMN IF NOT EXISTS ingestion_run_id TEXT;
ALTER TABLE vcp_finder_60m_runs ADD COLUMN IF NOT EXISTS ingestion_status TEXT;
ALTER TABLE vcp_finder_60m_runs ADD COLUMN IF NOT EXISTS fetch_completed_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS vcp_finder_60m_results (
  run_id TEXT NOT NULL REFERENCES vcp_finder_60m_runs(run_id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  state TEXT NOT NULL,
  actionable BOOLEAN NOT NULL,
  result JSONB NOT NULL,
  PRIMARY KEY (run_id, symbol)
);
CREATE INDEX IF NOT EXISTS vcp_finder_60m_results_state_idx
  ON vcp_finder_60m_results(state, run_id);
"""


# Low-Cheat is an early-entry profile, not a looser VCP quality gate.
LOW_CHEAT_MAX_BASE_DEPTH_PCT = 15.0
LOW_CHEAT_MAX_FINAL_CONTRACTION_PCT = 8.0
LOW_CHEAT_MIN_DISTANCE_TO_PIVOT_PCT = -2.0
LOW_CHEAT_MAX_DISTANCE_TO_PIVOT_PCT = 1.0
LOW_CHEAT_MAX_RISK_PCT = 8.0
LOW_CHEAT_MAX_RISK_ATR = 2.5
LOW_CHEAT_STATES = frozenset({"READY", "NEAR_TRIGGER"})


def init_vcp_schema(pg):
    cur = pg.cursor()
    cur.execute(TABLE_DDL)
    pg.commit()
    cur.close()


def load_vcp_60m_rows(pg, symbols, lookback=400, as_of=None):
    if not symbols:
        return {}
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = """SELECT symbol, ts, open, high, low, close, volume
           FROM intraday_price_data
           WHERE symbol=ANY(%s) AND interval='60m'"""
    params = [symbols]
    if as_of is not None:
        query += " AND ts <= %s"
        params.append(as_of)
    query += " ORDER BY symbol, ts DESC"
    cur.execute(query, tuple(params))
    grouped = {s: [] for s in symbols}
    for row in cur.fetchall():
        if len(grouped[row["symbol"]]) < int(lookback):
            grouped[row["symbol"]].append(dict(row))
    cur.close()
    for symbol in grouped:
        grouped[symbol].reverse()
    return grouped


def load_daily_trend_context(pg, symbols, as_of=None, lookback=80):
    if not symbols:
        return {}
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = """SELECT symbol, date, close FROM (
                 SELECT symbol, date, close,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                 FROM price_data
                 WHERE market='TH' AND instrument_type='ORD' AND symbol=ANY(%s)
               ) x WHERE rn <= %s"""
    params = [symbols, int(lookback)]
    if as_of is not None:
        query = query.replace("WHERE market='TH'", "WHERE market='TH' AND date <= %s")
        params = [as_of.date() if hasattr(as_of, "date") else as_of, symbols, int(lookback)]
    cur.execute(query, tuple(params))
    grouped = {s: [] for s in symbols}
    for row in cur.fetchall(): grouped[row["symbol"]].append(float(row["close"]))
    cur.close()
    contexts = {}
    for symbol, values in grouped.items():
        values.reverse()
        if len(values) < 40:
            contexts[symbol] = {"trend_pass": False, "status": "insufficient_history", "bars": len(values)}
            continue
        recent = sum(values[-20:]) / 20
        prior = sum(values[-40:-20]) / 20
        ret = (values[-1] / values[-21] - 1) * 100 if values[-21] else 0
        contexts[symbol] = {"trend_pass": bool(values[-1] > recent and recent >= prior and ret > 0), "return_20d_pct": ret, "status": "available", "bars": len(values)}
    return contexts


def load_daily_metrics(pg, symbols, as_of=None, lookback=20):
    if not symbols:
        return {}
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = """SELECT symbol, date, close, volume FROM (
                 SELECT symbol, date, close, volume,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                 FROM price_data
                 WHERE market='TH' AND instrument_type='ORD' AND symbol=ANY(%s)
               ) x WHERE rn <= %s"""
    params = [symbols, int(lookback)]
    if as_of is not None:
        query = query.replace("WHERE market='TH'", "WHERE market='TH' AND date <= %s")
        params = [as_of.date() if hasattr(as_of, "date") else as_of, symbols, int(lookback)]
    cur.execute(query, tuple(params))
    grouped = {s: [] for s in symbols}
    for row in cur.fetchall(): grouped[row["symbol"]].append((float(row["close"]), float(row["volume"])))
    cur.close()
    return {s: {"avg_trade_value_20": sum(c * v for c, v in vals) / len(vals) if vals else None, "latest_daily_close": vals[-1][0] if vals else None, "bars": len(vals)} for s, vals in grouped.items()}


def _presentation_fields(result):
    state = result.get("state")
    evidence = result.get("evidence") or {}
    if state == "FORMING":
        if evidence.get("prior_trend_pass") and evidence.get("price_contraction_pass") and evidence.get("base_pass"):
            forming_group, forming_rank = "maturing", 0
        elif evidence.get("prior_trend_pass") and (evidence.get("price_contraction_pass") or evidence.get("base_pass")):
            forming_group, forming_rank = "early", 1
        else:
            forming_group, forming_rank = "needs_work", 2
    else:
        forming_group, forming_rank = None, 9
    state_rank = {"BREAKOUT_WATCH": 0, "CONFIRMED": 1, "NEAR_TRIGGER": 2, "READY": 3, "EXTENDED": 5, "FAILED": 7, "STALE": 8, "NOT_VERIFIED": 9, "FORMING": 4}.get(state, 10)
    result["forming_group"] = forming_group
    result["state_rank"] = state_rank
    result["forming_rank"] = forming_rank
    result["review_rank"] = state_rank * 10 + forming_rank
    result["data"]["latest_closed_bar"] = result["data"].get("last_bar_ts")
    return result


def _result_sort_key(result):
    price = result.get("price") or {}
    pattern = result.get("pattern") or {}
    volume = result.get("volume") or {}
    distance = price.get("distance_to_pivot_pct")
    if result.get("state") in {"READY", "NEAR_TRIGGER", "BREAKOUT_WATCH"}:
        distance_key = abs(float(distance)) if distance is not None else 999999.0
    else:
        distance_key = 0.0
    latest = (result.get("data") or {}).get("latest_closed_bar") or ""
    contraction = pattern.get("latest_contraction_pct")
    breakout = volume.get("breakout_volume_ratio")
    return (result.get("state_rank", 9), result.get("forming_rank", 9), -int(bool((result.get("data") or {}).get("freshness") == "fresh")), distance_key, float(contraction) if contraction is not None else 999999.0, -(float(breakout) if breakout is not None else 0.0), -len(latest), result.get("symbol", ""))


def load_observed_ath(pg, symbols, as_of=None):
    if not symbols:
        return {}
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = "SELECT symbol, MAX(high) AS ath FROM price_data WHERE market='TH' AND (instrument_type='ORD' OR instrument_type IS NULL) AND symbol=ANY(%s)"
    params = [symbols]
    if as_of is not None:
        query += " AND date <= %s"
        params.append(as_of.date() if hasattr(as_of, "date") else as_of)
    query += " GROUP BY symbol"
    cur.execute(query, tuple(params))
    rows = {r["symbol"]: {"observed_ath_all_time": float(r["ath"]) if r["ath"] is not None else None, "source": "price_data", "as_of": str(as_of) if as_of else None} for r in cur.fetchall()}
    cur.close()
    return rows


def _classify_types(result, *, ath_context=None, listing_context=None):
    ath_context = ath_context or {}
    listing_context = listing_context or {}
    state = result.get("state")
    price = result.get("price") or {}
    pattern = result.get("pattern") or {}
    evidence = result.get("evidence") or {}
    close = price.get("last_close")
    pivot = price.get("pivot_high")
    base_depth = pattern.get("base_depth_pct")
    latest_contraction = pattern.get("latest_contraction_pct")
    distance = price.get("distance_to_pivot_pct")
    ath = ath_context.get("observed_ath_all_time")
    ath_distance = ((close / ath) - 1) * 100 if close is not None and ath else None
    pivots = pattern.get("pivots") or []
    sequence_valid = len(pivots) >= 5 and [p.get("kind") for p in pivots[-5:]] == ["high", "low", "high", "low", "high"]
    evidence_valid = all(bool(evidence.get(key)) for key in (
        "prior_trend_pass", "price_contraction_pass", "base_pass", "leg_volume_pass"
    ))
    base_valid = base_depth is not None and 0 < float(base_depth) <= 35
    contraction_valid = latest_contraction is not None and 0 < float(latest_contraction) <= 12
    invalidation = price.get("invalidation")
    risk_pct = ((float(close) - float(invalidation)) / float(close) * 100
                if close is not None and invalidation is not None and float(close) > 0 else None)
    atr = price.get("atr14")
    risk_atr = ((float(close) - float(invalidation)) / float(atr)
                if close is not None and invalidation is not None and atr is not None and float(atr) > 0 else None)
    usable_risk = bool(
        risk_pct is not None and 0 < risk_pct <= LOW_CHEAT_MAX_RISK_PCT
        and risk_atr is not None and 0 < risk_atr <= LOW_CHEAT_MAX_RISK_ATR
    )
    valid_vcp_morphology = bool(sequence_valid and evidence_valid and base_valid and contraction_valid)
    low_cheat = bool(
        valid_vcp_morphology
        and state in LOW_CHEAT_STATES
        and float(base_depth) <= LOW_CHEAT_MAX_BASE_DEPTH_PCT
        and float(latest_contraction) <= LOW_CHEAT_MAX_FINAL_CONTRACTION_PCT
        and distance is not None
        and LOW_CHEAT_MIN_DISTANCE_TO_PIVOT_PCT <= float(distance) <= LOW_CHEAT_MAX_DISTANCE_TO_PIVOT_PCT
        and usable_risk
    )
    base_type = "low_cheat_vcp" if low_cheat else ("standard_vcp" if valid_vcp_morphology else None)
    break_ath = bool(ath and close is not None and close >= ath * 1.005)
    listing_date = listing_context.get("listing_date")
    new_stock = bool(listing_date and listing_context.get("age_calendar_days") is not None and listing_context["age_calendar_days"] <= 120)
    overlays = []
    if break_ath: overlays.append("break_ath")
    if new_stock: overlays.append("new_stock")
    types = ([base_type] if base_type else []) + overlays
    result["vcp_type"] = {
        "base_type": base_type,
        "overlays": overlays,
        "types": types,
        "primary_type": "break_ath" if break_ath else ("new_stock" if new_stock else base_type),
        "entry_profile": "early_entry" if low_cheat else ("standard_entry" if base_type == "standard_vcp" else None),
        "type_evidence": {
            "observed_ath_all_time": ath,
            "ath_distance_pct": ath_distance,
            "break_ath_price_pass": break_ath,
            "listing_date": listing_date,
            "new_stock_age_calendar_days": listing_context.get("age_calendar_days"),
            "low_cheat_base_depth_pct": base_depth,
            "low_cheat_latest_contraction_pct": latest_contraction,
            "low_cheat_distance_to_pivot_pct": distance,
            "valid_vcp_morphology": valid_vcp_morphology,
            "valid_pivot_sequence": sequence_valid,
            "healthy_trend_60m": bool(evidence.get("prior_trend_pass")),
            "risk_to_invalidation_pct": risk_pct,
            "risk_to_invalidation_atr": risk_atr,
            "tight_risk_pass": usable_risk,
        },
        "type_policy_version": "signalix/vcp-types-v2-early-entry",
    }
    return result


def find_vcp_universe_60m(pg, *, market="TH", symbols=None, as_of=None, config=None,
                          ingestion_run_id=None, ingestion_status=None, fetch_completed_at=None):
    cfg = config or VCP60Config()
    if market.upper() != "TH":
        raise ValueError("vcp_finder_60m currently supports market=TH only")
    eligible = sorted(set(symbols or active_ord_symbols(pg)))
    observed_as_of = as_of or datetime.now(timezone.utc)
    rows = load_vcp_60m_rows(pg, eligible, as_of=observed_as_of)
    daily_context = load_daily_trend_context(pg, eligible, as_of=observed_as_of)
    daily_metrics = load_daily_metrics(pg, eligible, as_of=observed_as_of)
    ath_context = load_observed_ath(pg, eligible, as_of=observed_as_of)
    feed_status = {}
    if eligible:
        cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """SELECT symbol,status,reason,retry_at,last_success_at
               FROM intraday_feed_status
               WHERE feed='settrade_intraday_60m' AND symbol=ANY(%s)""",
            (eligible,),
        )
        feed_status = {r["symbol"]: dict(r) for r in cur.fetchall()}
        cur.close()
    run_id = new_run_id()
    results = []
    for symbol in eligible:
        result = find_vcp_60m(rows.get(symbol), as_of=observed_as_of, config=cfg, daily_context=daily_context.get(symbol))
        result["symbol"] = symbol
        result["data"]["feed_status"] = feed_status.get(symbol, {}).get("status", "unknown")
        result["data"]["feed_reason"] = feed_status.get(symbol, {}).get("reason")
        result["data"]["feed_retry_at"] = str(feed_status.get(symbol, {}).get("retry_at")) if feed_status.get(symbol, {}).get("retry_at") else None
        result["data"]["feed_last_success_at"] = str(feed_status.get(symbol, {}).get("last_success_at")) if feed_status.get(symbol, {}).get("last_success_at") else None
        result["data"]["daily_metrics"] = daily_metrics.get(symbol, {})
        result = _classify_types(result, ath_context=ath_context.get(symbol), listing_context=None)
        result["provenance"]["run_id"] = run_id
        result["provenance"]["market"] = market.upper()
        result["provenance"]["ingestion_run_id"] = ingestion_run_id
        result["provenance"]["ingestion_status"] = ingestion_status
        result["provenance"]["fetch_completed_at"] = str(fetch_completed_at) if fetch_completed_at else None
        results.append(_presentation_fields(result))
    results.sort(key=_result_sort_key)
    coverage = {"returned": len(results), "feed_unavailable": sum(1 for r in results if (r.get("data") or {}).get("feed_status") == "unavailable"), "no_data": sum(1 for r in results if (r.get("data") or {}).get("bar_count", 0) == 0)}
    return {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "finder": "vcp_finder_60m",
        "interval": cfg.interval,
        "market": market.upper(),
        "run_id": run_id,
        "policy_version": POLICY_VERSION,
        "as_of": observed_as_of.isoformat(),
        "ingestion_run_id": ingestion_run_id,
        "ingestion_status": ingestion_status,
        "fetch_completed_at": str(fetch_completed_at) if fetch_completed_at else None,
        "universe": {
            "eligible": len(eligible),
            "evaluated": len(results),
            "returned": len(results),
        },
        "coverage": coverage,
        "results": results,
    }


def load_latest_vcp_run(pg, *, market="TH", daily_watchlist=False, state=None, symbol=None, limit=None, actionable=False, focused=False, review=False):
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT run_id, market, interval, policy_version, as_of,
                  eligible_count, evaluated_count, ingestion_run_id,
                  ingestion_status, fetch_completed_at
           FROM vcp_finder_60m_runs
           WHERE market=%s ORDER BY created_at DESC LIMIT 1""",
        (market.upper(),),
    )
    run = cur.fetchone()
    if not run:
        cur.close()
        return None
    if daily_watchlist:
        # The watchlist projection must see the full run and apply its own
        # fail-closed caps. Ignore caller state/limit/symbol filters.
        state = symbol = limit = None
        actionable = focused = review = False
    clauses = ["run_id=%s"]
    params = [run["run_id"]]
    if state:
        clauses.append("state=%s")
        params.append(state.upper())
    elif actionable:
        clauses.append("state IN ('READY','NEAR_TRIGGER','CONFIRMED')")
    elif review:
        clauses.append("(state IN ('READY','NEAR_TRIGGER','CONFIRMED','BREAKOUT_WATCH') OR result->>'reviewable' = 'true' OR (state='FORMING' AND symbol IN (SELECT o.symbol FROM daily_scan_observations o JOIN daily_scan_runs d ON d.id=o.run_id WHERE d.id=(SELECT id FROM daily_scan_runs WHERE scanner_version='signalix/daily-state-v2' ORDER BY scan_date DESC,run_timestamp DESC LIMIT 1) AND o.classification='waiting_breakout')) OR (state NOT IN ('FAILED','STALE','NOT_VERIFIED') AND (result->'price'->>'distance_to_pivot_pct')::double precision BETWEEN -2 AND 5 AND symbol IN (SELECT symbol FROM company_profiles WHERE industry ILIKE 'Insurance%%')))" )
    elif focused:
        clauses.append("(state IN ('READY','NEAR_TRIGGER','CONFIRMED','BREAKOUT_WATCH') OR (state='FORMING' AND result->>'forming_group'='maturing'))")
    if symbol:
        clauses.append("symbol=%s")
        params.append(symbol.upper())
    query = "SELECT result FROM vcp_finder_60m_results WHERE " + " AND ".join(clauses) + " ORDER BY symbol"
    if limit is not None:
        query += " LIMIT %s"
        params.append(max(1, min(int(limit), 5000)))
    cur.execute(query, params)
    results = [r["result"] for r in cur.fetchall()]
    symbols = [r.get("symbol") for r in results if r.get("symbol")]
    daily_watch = set()
    if symbols:
        cur.execute("SELECT o.symbol FROM daily_scan_observations o JOIN daily_scan_runs d ON d.id=o.run_id WHERE d.id=(SELECT id FROM daily_scan_runs WHERE scanner_version='signalix/daily-state-v2' ORDER BY scan_date DESC,run_timestamp DESC LIMIT 1) AND o.classification='waiting_breakout' AND o.symbol=ANY(%s)", (symbols,))
        daily_watch = {r["symbol"] for r in cur.fetchall()}
    insurance_symbols = set()
    if symbols:
        cur.execute("SELECT symbol FROM company_profiles WHERE symbol=ANY(%s) AND industry ILIKE 'Insurance%%'", (symbols,))
        insurance_symbols = {r["symbol"] for r in cur.fetchall()}
    event_context = {}
    if symbols:
        cur.execute("SELECT DISTINCT ON (x.symbol) x.symbol,r.as_of,x.result FROM vcp_finder_60m_results x JOIN vcp_finder_60m_runs r ON r.run_id=x.run_id WHERE x.symbol=ANY(%s) AND x.state='BREAKOUT_WATCH' AND r.as_of < %s ORDER BY x.symbol,r.as_of DESC", (symbols, run["as_of"]))
        event_context = {r["symbol"]: {"state": "BREAKOUT_WATCH", "as_of": r["as_of"].isoformat() if hasattr(r["as_of"], "isoformat") else str(r["as_of"]), "price": (r["result"].get("price") or {}).get("last_close"), "pivot": (r["result"].get("price") or {}).get("pivot_high"), "volume_ratio": (r["result"].get("volume") or {}).get("breakout_volume_ratio")} for r in cur.fetchall()}
    for result in results:
        result["daily_context_watch"] = result.get("symbol") in daily_watch
        result["insurance_context_watch"] = result.get("symbol") in insurance_symbols and result.get("state") not in {"FAILED", "STALE", "NOT_VERIFIED"} and -2 <= float((result.get("price") or {}).get("distance_to_pivot_pct")) <= 5 if (result.get("price") or {}).get("distance_to_pivot_pct") is not None else False
        result["last_watch_event"] = event_context.get(result.get("symbol"))
        dist = (result.get("price") or {}).get("distance_to_pivot_pct")
        result["late_watch"] = bool(result.get("last_watch_event") and dist is not None and float(dist) > 3 and result.get("state") not in {"BREAKOUT_WATCH","CONFIRMED"})
    cur.execute("SELECT COUNT(*) FILTER (WHERE result->'data'->>'feed_status' = 'unavailable') AS feed_unavailable, COUNT(*) FILTER (WHERE COALESCE((result->'data'->>'bar_count')::int, 0) = 0) AS no_data FROM vcp_finder_60m_results WHERE run_id=%s", (run["run_id"],))
    coverage_row = cur.fetchone()
    cur.close()
    from marginable import lookup
    for result in results:
        record = lookup(result.get("symbol"))
        result["marginable"] = {
            "is_marginable": bool(record),
            "margin_rate_pct": record.get("margin_rate_pct") if record else None,
            "source": "Krungsri Credit Balance" if record else None,
        }
        result["margin_rate_pct"] = record.get("margin_rate_pct") if record else None
    results.sort(key=_result_sort_key)
    return {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "finder": "vcp_finder_60m",
        "interval": run["interval"],
        "market": run["market"],
        "run_id": run["run_id"],
        "policy_version": run["policy_version"],
        "as_of": run["as_of"].isoformat() if hasattr(run["as_of"], "isoformat") else str(run["as_of"]),
        "ingestion_run_id": run["ingestion_run_id"],
        "ingestion_status": run["ingestion_status"],
        "fetch_completed_at": run["fetch_completed_at"].isoformat() if hasattr(run["fetch_completed_at"], "isoformat") else (str(run["fetch_completed_at"]) if run["fetch_completed_at"] else None),
        "universe": {"eligible": run["eligible_count"], "evaluated": run["evaluated_count"], "returned": len(results)},
        "coverage": {"feed_unavailable": coverage_row["feed_unavailable"] or 0, "no_data": coverage_row["no_data"] or 0},
        "results": results,
        "daily_watchlist": project_daily_vcp_watchlist(results) if daily_watchlist else None,
    }


# ---------------------------------------------------------------------------
# Daily VCP Watchlist projection — fail-closed, quality-gated, capped lanes.
# ---------------------------------------------------------------------------

DAILY_VCP_WATCHLIST_VERSION = "signalix/daily-vcp-watchlist-v1"
DAILY_VCP_MIN_LIQUIDITY = 10_000_000
DAILY_VCP_CAP_ACTION_REVIEW = 10
DAILY_VCP_CAP_NEAR_TRIGGER = 10
DAILY_VCP_CAP_BREAKOUT_WATCH = 5


def _dv_to_float(value, default=None):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dv_quality_pass(result):
    """Canonical VCP structural quality: all base evidence must pass."""
    ev = result.get("evidence") or {}
    return bool(
        ev.get("prior_trend_pass")
        and ev.get("price_contraction_pass")
        and ev.get("base_pass")
        and ev.get("leg_volume_pass")
    )


def _dv_daily_context_pass(result):
    return bool((result.get("trend") or {}).get("daily_context_pass"))


def _dv_fresh(result):
    if result.get("state") in {"STALE", "FAILED", "NOT_VERIFIED"}:
        return False
    data = result.get("data") or {}
    if data.get("freshness") != "fresh":
        return False
    if data.get("feed_status") == "unavailable":
        return False
    return True


def _dv_liquid(result):
    metrics = (result.get("data") or {}).get("daily_metrics") or {}
    val = _dv_to_float(metrics.get("avg_trade_value_20"), 0)
    return val >= DAILY_VCP_MIN_LIQUIDITY


def _dv_action_review_coherent(result):
    """Close/trigger evidence is coherent for the ACTION_REVIEW lane.

    CONFIRMED must have a closed-bar close at/above the pivot with volume.
    READY is a valid pre-breakout setup: it must hold above invalidation and
    must not contradict the trigger (close below pivot is expected).
    """
    state = result.get("state")
    price = result.get("price") or {}
    breakout = result.get("breakout") or {}
    close = _dv_to_float(price.get("last_close"))
    pivot = _dv_to_float(breakout.get("pivot_level") or price.get("pivot_high"))
    invalidation = _dv_to_float(price.get("invalidation"))
    if close is None or pivot is None or pivot <= 0:
        return False
    if invalidation is not None and close < invalidation:
        return False
    if state == "CONFIRMED":
        return bool(breakout.get("close_confirmed")) and close >= pivot
    if state == "READY":
        # Pre-breakout: close below pivot is expected; above pivot would be
        # CONFIRMED. Anything at/above invalidation is coherent.
        return True
    return False


def _dv_risk_reward_score(result):
    price = result.get("price") or {}
    close = _dv_to_float(price.get("last_close"))
    stop = _dv_to_float(price.get("invalidation"))
    pivot = _dv_to_float(price.get("pivot_high") or (result.get("breakout") or {}).get("pivot_level"))
    if not close or not stop or stop >= close or not pivot:
        return 0.0
    risk = close - stop
    if risk <= 0:
        return 0.0
    reward = abs(pivot - close)
    rr = reward / risk
    return round(min(1.0, max(0.0, (rr - 1.0) / 8.0 + 0.25)), 4)


def _dv_liquidity_score(result):
    metrics = (result.get("data") or {}).get("daily_metrics") or {}
    val = _dv_to_float(metrics.get("avg_trade_value_20"), 0)
    if val <= 0:
        return 0.0
    return round(min(1.0, val / (DAILY_VCP_MIN_LIQUIDITY * 2)), 4)


def _dv_rank_score(result):
    """Quality/proximity/context/risk-reward/liquidity/recency composite."""
    ev = result.get("evidence") or {}
    structure = sum([
        bool(ev.get("prior_trend_pass")),
        bool(ev.get("price_contraction_pass")),
        bool(ev.get("base_pass")),
        bool(ev.get("leg_volume_pass")),
    ]) / 4.0
    state = result.get("state")
    readiness = {
        "CONFIRMED": 1.0,
        "READY": 0.9,
        "NEAR_TRIGGER": 0.7,
        "BREAKOUT_WATCH": 0.4,
    }.get(state, 0.0)
    rr = _dv_risk_reward_score(result)
    liq = _dv_liquidity_score(result)
    context = 1.0 if _dv_daily_context_pass(result) else 0.0
    data = result.get("data") or {}
    recency = 1.0 if data.get("freshness_session_age", 1) == 0 else 0.5
    return round(
        0.35 * structure
        + 0.25 * readiness
        + 0.15 * rr
        + 0.10 * liq
        + 0.10 * context
        + 0.05 * recency,
        4,
    )


def _dv_lane(result):
    """Return canonical Daily VCP lane or None (fail-closed)."""
    state = result.get("state")
    if state in {"EXTENDED", "FAILED", "STALE", "NOT_VERIFIED", "FORMING"}:
        return None
    if not _dv_fresh(result) or not _dv_liquid(result):
        return None
    if result.get("late_watch") is True:
        return None
    quality = _dv_quality_pass(result)
    if state in {"READY", "CONFIRMED"}:
        if not quality or not _dv_daily_context_pass(result):
            return None
        if not _dv_action_review_coherent(result):
            return None
        return "ACTION_REVIEW"
    if state == "NEAR_TRIGGER":
        if not quality or not _dv_daily_context_pass(result):
            return None
        return "NEAR_TRIGGER"
    if state == "BREAKOUT_WATCH":
        if not _dv_daily_context_pass(result):
            return None
        return "BREAKOUT_WATCH"
    return None


def _dv_sort_key(result):
    return (
        -(_dv_rank_score(result)),
        -(_dv_liquidity_score(result)),
        str(result.get("symbol") or ""),
    )


def project_daily_vcp_watchlist(results):
    """Fail-closed Daily VCP Watchlist projection with deterministic caps.

    Lanes:
      - ACTION_REVIEW: READY/CONFIRMED with quality pass + coherent close/trigger.
      - NEAR_TRIGGER: NEAR_TRIGGER with quality pass.
      - BREAKOUT_WATCH: intrabar watch-only, never actionable.

    Hard caps: ACTION_REVIEW <= 10, NEAR_TRIGGER <= 10, BREAKOUT_WATCH <= 5.
    Cross-lane duplicate symbols are removed, keeping the highest-priority lane.
    """
    raw_lanes = {"ACTION_REVIEW": [], "NEAR_TRIGGER": [], "BREAKOUT_WATCH": []}
    caps = {
        "ACTION_REVIEW": DAILY_VCP_CAP_ACTION_REVIEW,
        "NEAR_TRIGGER": DAILY_VCP_CAP_NEAR_TRIGGER,
        "BREAKOUT_WATCH": DAILY_VCP_CAP_BREAKOUT_WATCH,
    }
    for r in results or []:
        lane = _dv_lane(r)
        if lane:
            raw_lanes[lane].append(r)
    for lane, items in raw_lanes.items():
        items.sort(key=_dv_sort_key)
        raw_lanes[lane] = items[:caps[lane]]
    seen = set()
    lanes = {}
    counts = {}
    for lane in ("ACTION_REVIEW", "NEAR_TRIGGER", "BREAKOUT_WATCH"):
        filtered = []
        for r in raw_lanes[lane]:
            sym = str(r.get("symbol", "")).upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            filtered.append(r)
        lanes[lane] = filtered
        counts[lane] = len(filtered)
    return {
        "policy_version": DAILY_VCP_WATCHLIST_VERSION,
        "caps": caps,
        "counts": counts,
        "action_review": lanes["ACTION_REVIEW"],
        "near_trigger": lanes["NEAR_TRIGGER"],
        "breakout_watch": lanes["BREAKOUT_WATCH"],
    }


def persist_vcp_run(pg, payload):
    init_vcp_schema(pg)
    cur = pg.cursor()
    cur.execute(
        """INSERT INTO vcp_finder_60m_runs
           (run_id, market, interval, policy_version, as_of, eligible_count, evaluated_count,
            ingestion_run_id, ingestion_status, fetch_completed_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (payload["run_id"], payload["market"], payload["interval"], payload["policy_version"],
         payload["as_of"], payload["universe"]["eligible"], payload["universe"]["evaluated"],
         payload.get("ingestion_run_id"), payload.get("ingestion_status"), payload.get("fetch_completed_at")),
    )
    rows = [(payload["run_id"], r["symbol"], r["state"], bool(r["actionable"]), json.dumps(r, default=str)) for r in payload["results"]]
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO vcp_finder_60m_results(run_id,symbol,state,actionable,result) VALUES %s",
        rows,
    )
    pg.commit()
    cur.close()
    return payload["run_id"]
