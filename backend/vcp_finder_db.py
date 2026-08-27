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


def load_latest_vcp_run(pg, *, market="TH", state=None, symbol=None, limit=None, actionable=False, focused=False, review=False):
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
