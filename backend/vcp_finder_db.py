"""DB adapter and isolated persistence for VCP Finder 60m."""
from __future__ import annotations

import json
from datetime import datetime, timezone
import psycopg2.extras

from instruments import active_ord_symbols
from marginable import eligible_symbols, metadata as marginable_metadata
from mvp_api import _resolve_rr
from unified_vcp_decision import project_unified_vcp_decision
from vcp_decision_policy import (
    CANDIDATE_POLICY,
    POLICY_VERSION as DECISION_SHADOW_POLICY_VERSION,
    PROJECTION_MARKER,
    project_vcp_decision_shadow,
)
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
VCP_INGESTION_STATUSES = frozenset({"full_success", "partial_success"})
SERVING_UNIVERSES = frozenset({"marginable_long", "active_ord"})


def resolve_serving_universe(pg, *, universe="marginable_long"):
    """Resolve the explicit live serving universe and auditable manifest."""
    if universe not in SERVING_UNIVERSES:
        raise ValueError(f"unknown universe: {universe}")
    active = sorted(set(active_ord_symbols(pg)))
    if universe == "marginable_long":
        selected, manifest = eligible_symbols(active, universe)
        margin = marginable_metadata()
        manifest["source"] = margin.get("source")
        return selected, manifest
    margin = marginable_metadata()
    return active, {
        "universe_filter": "active_ord",
        "base_active_ord_count": len(active),
        "eligible_count": len(active),
        "excluded_count": 0,
        "excluded_reason": None,
        "schema_version": margin["schema_version"] if "schema_version" in margin else "signalix.marginable.v1",
        "source": margin.get("source"),
        "source_document": margin.get("source_document"),
        "effective_date": margin.get("effective_date"),
    }


def validate_vcp_run_provenance(*, ingestion_run_id, ingestion_status,
                                fetch_completed_at):
    """Return a diagnostic for incomplete VCP lineage, or None when valid."""
    if not isinstance(ingestion_run_id, str) or not ingestion_run_id.strip():
        return "missing_ingestion_run_id"
    if ingestion_status not in VCP_INGESTION_STATUSES:
        return "invalid_ingestion_status"
    if fetch_completed_at is None or not str(fetch_completed_at).strip():
        return "missing_fetch_completed_at"
    try:
        completed = datetime.fromisoformat(str(fetch_completed_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "invalid_fetch_completed_at"
    if completed.tzinfo is None or completed.utcoffset() is None:
        return "invalid_fetch_completed_at"
    return None


def _canonical_rr_from_daily_payload(payload):
    """Project the persisted Daily producer fields through the MVP rr rule."""
    readiness = payload.get("trade_readiness") or {}
    targets = readiness.get("targets") or {}
    item = dict(payload)
    item["riskStop"] = item.get("riskStop") or readiness.get("stop_loss")
    item["t161"] = item.get("t161") or targets.get("161")
    item["t127"] = item.get("t127") or targets.get("127")
    return _resolve_rr(item)


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


def _daily_context_from_rows(rows):
    ordered = sorted(rows or [], key=lambda row: row["date"])
    values = [float(row["close"]) for row in ordered]
    as_of = str(ordered[-1]["date"]) if ordered else None
    if len(values) < 40:
        return {
            "trend_pass": False,
            "status": "insufficient_history",
            "bars": len(values),
            "as_of": as_of,
        }
    recent = sum(values[-20:]) / 20
    prior = sum(values[-40:-20]) / 20
    ret = (values[-1] / values[-21] - 1) * 100 if values[-21] else 0.0
    return {
        "trend_pass": bool(values[-1] > recent and recent >= prior and ret > 0),
        "return_20d_pct": ret,
        "recent_avg_20": recent,
        "prior_avg_20": prior,
        "status": "available",
        "bars": len(values),
        "as_of": as_of,
    }


def _daily_metrics_from_rows(rows):
    ordered = sorted(rows or [], key=lambda row: row["date"])[-20:]
    if not ordered:
        return {
            "avg_trade_value_20": None,
            "latest_daily_close": None,
            "bars": 0,
            "as_of": None,
        }
    values = [(float(row["close"]), float(row["volume"])) for row in ordered]
    return {
        "avg_trade_value_20": sum(close * volume for close, volume in values) / len(values),
        "latest_daily_close": values[-1][0],
        "bars": len(values),
        "as_of": str(ordered[-1]["date"]),
    }


def load_daily_trend_context(pg, symbols, as_of=None, lookback=80):
    if not symbols:
        return {}
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = """SELECT symbol, date, close FROM (
                 SELECT symbol, date, close,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                 FROM price_data
                 WHERE market='TH' AND instrument_type='ORD' AND symbol=ANY(%s)
               ) x WHERE rn <= %s ORDER BY symbol, date ASC"""
    params = [symbols, int(lookback)]
    if as_of is not None:
        query = query.replace("WHERE market='TH'", "WHERE market='TH' AND date <= %s")
        params = [as_of.date() if hasattr(as_of, "date") else as_of, symbols, int(lookback)]
    cur.execute(query, tuple(params))
    grouped = {s: [] for s in symbols}
    for row in cur.fetchall():
        grouped[row["symbol"]].append(dict(row))
    cur.close()
    return {symbol: _daily_context_from_rows(rows) for symbol, rows in grouped.items()}


def load_daily_metrics(pg, symbols, as_of=None, lookback=20):
    if not symbols:
        return {}
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = """SELECT symbol, date, close, volume FROM (
                 SELECT symbol, date, close, volume,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                 FROM price_data
                 WHERE market='TH' AND instrument_type='ORD' AND symbol=ANY(%s)
               ) x WHERE rn <= %s ORDER BY symbol, date ASC"""
    params = [symbols, int(lookback)]
    if as_of is not None:
        query = query.replace("WHERE market='TH'", "WHERE market='TH' AND date <= %s")
        params = [as_of.date() if hasattr(as_of, "date") else as_of, symbols, int(lookback)]
    cur.execute(query, tuple(params))
    grouped = {s: [] for s in symbols}
    for row in cur.fetchall():
        grouped[row["symbol"]].append(dict(row))
    cur.close()
    return {symbol: _daily_metrics_from_rows(rows) for symbol, rows in grouped.items()}


def load_52_week_context(pg, symbols, as_of=None, lookback=252):
    """Load point-in-time daily high/low context for presentation only."""
    if not symbols:
        return {}
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Bound the work per requested symbol.  The window-function form makes
    # PostgreSQL rank all matching price_data rows before retaining 252 rows;
    # the lateral lookup can use the symbol/date index and stop at lookback.
    query = """SELECT x.symbol, MAX(x.high) AS high52, MIN(x.low) AS low52, COUNT(*) AS bars
               FROM unnest(%s::text[]) AS requested(symbol)
               CROSS JOIN LATERAL (
                 SELECT p.symbol, p.high, p.low
                 FROM price_data p
                 WHERE p.market='TH' AND p.instrument_type='ORD'
                   AND UPPER(p.symbol) = UPPER(requested.symbol)"""
    params = [symbols]
    if as_of is not None:
        query += " AND p.date <= %s"
        params.append(as_of.date() if hasattr(as_of, "date") else as_of)
    query += """ ORDER BY p.date DESC
                 LIMIT %s
               ) x
               GROUP BY x.symbol"""
    params.append(int(lookback))
    cur.execute(query, tuple(params))
    rows = {
        row["symbol"]: {
            "high52": float(row["high52"]) if row["high52"] is not None else None,
            "low52": float(row["low52"]) if row["low52"] is not None else None,
            "bars": int(row["bars"] or 0),
            "source": "price_data",
            "as_of": str(as_of) if as_of else None,
        }
        for row in cur.fetchall()
    }
    cur.close()
    return rows


def _attach_unified_decision(result):
    """Attach the additive decision projection using result-local Daily context."""
    daily_context = (result.get("trend") or {}).get("daily_context") or {}
    result["decision"] = project_unified_vcp_decision(result, daily_context)
    return result


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
    result["data"]["latest_closed_bar"] = result["data"].get("latest_closed_bar")
    return _attach_unified_decision(result)


def _apply_52_week_presentation(result, context):
    """Attach as-of high/low proximity without changing lifecycle state."""
    context = context or {}
    price = result.setdefault("price", {})
    result["high52"] = context.get("high52", result.get("high52"))
    result["low52"] = context.get("low52", result.get("low52"))
    price["high52"] = result["high52"]
    price["low52"] = result["low52"]
    close = price.get("last_close")
    high52 = result["high52"]
    proximity = ((float(close) / high52) - 1) * 100 if close is not None and high52 else None
    price["distance_to_52w_high_pct"] = proximity
    if proximity is not None and -5 <= proximity <= 0:
        vcp_type = result.setdefault("vcp_type", {"overlays": [], "types": []})
        vcp_type.setdefault("overlays", [])
        vcp_type.setdefault("types", [])
        if "near_52w_high" not in vcp_type["overlays"]:
            vcp_type["overlays"].append("near_52w_high")
        if "near_52w_high" not in vcp_type["types"]:
            vcp_type["types"].append("near_52w_high")
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
    high52_distance = (result.get("price") or {}).get("distance_to_52w_high_pct")
    high52_key = abs(float(high52_distance)) if high52_distance is not None else 999999.0
    return (result.get("state_rank", 9), result.get("forming_rank", 9), -int(bool((result.get("data") or {}).get("freshness") == "fresh")), high52_key, distance_key, float(contraction) if contraction is not None else 999999.0, -(float(breakout) if breakout is not None else 0.0), -len(latest), result.get("symbol", ""))


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
    high52_context = load_52_week_context(pg, eligible, as_of=observed_as_of)
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
        symbol_feed_status = feed_status.get(symbol, {}).get("status")
        result = find_vcp_60m(
            rows.get(symbol), as_of=observed_as_of, config=cfg,
            daily_context=daily_context.get(symbol), feed_status=symbol_feed_status,
            ingestion_status=ingestion_status,
        )
        result["symbol"] = symbol
        result["data"]["feed_status"] = symbol_feed_status or "unknown"
        result["data"]["feed_reason"] = feed_status.get(symbol, {}).get("reason")
        result["data"]["feed_retry_at"] = str(feed_status.get(symbol, {}).get("retry_at")) if feed_status.get(symbol, {}).get("retry_at") else None
        result["data"]["feed_last_success_at"] = str(feed_status.get(symbol, {}).get("last_success_at")) if feed_status.get(symbol, {}).get("last_success_at") else None
        result["data"]["daily_metrics"] = daily_metrics.get(symbol, {})
        result = _classify_types(result, ath_context=ath_context.get(symbol), listing_context=None)
        _apply_52_week_presentation(result, high52_context.get(symbol))
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


def _presentation_symbols_for_run(results, *, daily_watchlist):
    """Return symbols that need presentation enrichment for this response."""
    if not daily_watchlist:
        return [r.get("symbol") for r in results if r.get("symbol")]
    eligible_states = daily_watchlist_query_states()
    return [
        r.get("symbol")
        for r in results
        if r.get("symbol") and r.get("state") in eligible_states
    ]


def _attach_decision_shadow_v2(result):
    """Add the pure v2 serving projection while retaining the v1 evidence."""
    out = dict(result)
    if "policy_version" in out:
        out["source_policy_version"] = out["policy_version"]
    shadow = project_vcp_decision_shadow(out)
    out["decision_shadow_v2"] = shadow
    out["decision_policy_version"] = DECISION_SHADOW_POLICY_VERSION
    out["decision_lane"] = shadow["decision_lane"]
    out["lane"] = shadow["decision_lane"]
    out["actionability"] = shadow["actionability"]
    return out


def load_latest_vcp_run(pg, *, market="TH", daily_watchlist=False, state=None, symbol=None, limit=None, actionable=False, focused=False, review=False, universe="marginable_long"):
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT run_id, market, interval, policy_version, as_of,
                  eligible_count, evaluated_count, ingestion_run_id,
                  ingestion_status, fetch_completed_at
           FROM vcp_finder_60m_runs
           WHERE market=%s
             AND ingestion_run_id IS NOT NULL
             AND ingestion_status = 'full_success'
             AND fetch_completed_at IS NOT NULL
           ORDER BY created_at DESC LIMIT 1""",
        (market.upper(),),
    )
    run = cur.fetchone()
    if not run:
        cur.close()
        return None
    selected_symbols, universe_manifest = resolve_serving_universe(pg, universe=universe)
    if daily_watchlist:
        # The watchlist projection must see the full run and apply its own
        # fail-closed caps. Ignore caller state/limit/symbol filters.
        state = symbol = limit = None
        actionable = focused = review = False
    # Count coverage against the unfiltered live result set. The run manifest
    # describes the producer's input, not the rows actually available to this
    # serving request; never substitute it for observed serving coverage.
    cur.execute(
        "SELECT symbol FROM vcp_finder_60m_results WHERE run_id=%s AND symbol=ANY(%s)",
        (run["run_id"], selected_symbols),
    )
    run_symbols = {row["symbol"] for row in cur.fetchall()}
    missing_from_run = sorted(set(selected_symbols) - run_symbols)
    clauses = ["run_id=%s", "symbol=ANY(%s)"]
    params = [run["run_id"], selected_symbols]
    # Daily projection must inspect the full completed run so it can report
    # machine-readable rejection coverage. _dv_lane remains fail-closed.
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
    presentation_symbols = _presentation_symbols_for_run(results, daily_watchlist=daily_watchlist)
    high52_context = load_52_week_context(pg, presentation_symbols, as_of=run["as_of"])
    for result in results:
        _apply_52_week_presentation(result, high52_context.get(result.get("symbol")))
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
    # VCP rows are the drawer's authoritative context. Resolve membership at
    # the run's as-of date from the normalized historical index table rather
    # than fetching retired Daily symbol detail in the browser.
    if symbols:
        cur.execute(
            """SELECT symbol, index_name FROM index_memberships
               WHERE symbol=ANY(%s) AND effective_from <= %s
                 AND (effective_to IS NULL OR effective_to >= %s)
               ORDER BY symbol, index_name""",
            (symbols, run["as_of"].date() if hasattr(run["as_of"], "date") else run["as_of"],
             run["as_of"].date() if hasattr(run["as_of"], "date") else run["as_of"]),
        )
        memberships = {}
        for row in cur.fetchall():
            memberships.setdefault(row["symbol"], []).append(row["index_name"])
        for result in results:
            result["index_membership"] = memberships.get(result.get("symbol"), [])
        # The VCP producer has no R/R field.  Enrich only a missing row value
        # from the same canonical Daily projection used by the drawer.  This
        # is metadata enrichment: VCP price/trigger/invalidation stay intact.
        cur.execute(
            """SELECT DISTINCT ON (o.symbol) o.symbol, o.raw_payload
               FROM daily_scan_observations o
               JOIN daily_scan_runs d ON d.id = o.run_id
               WHERE o.symbol=ANY(%s) AND d.run_timestamp <= %s
               ORDER BY o.symbol, d.scan_date DESC, d.run_timestamp DESC""",
            (symbols, run["as_of"]),
        )
        canonical_rr = {}
        for row in cur.fetchall():
            rr = _canonical_rr_from_daily_payload(row.get("raw_payload") or {})
            if rr is not None:
                canonical_rr[row["symbol"]] = rr
        for result in results:
            if result.get("rr") is None and result.get("symbol") in canonical_rr:
                result["rr"] = canonical_rr[result["symbol"]]
    cur.execute("SELECT COUNT(*) FILTER (WHERE result->'data'->>'feed_status' = 'unavailable') AS feed_unavailable, COUNT(*) FILTER (WHERE COALESCE((result->'data'->>'bar_count')::int, 0) = 0) AS no_data FROM vcp_finder_60m_results WHERE run_id=%s AND symbol=ANY(%s)", (run["run_id"], selected_symbols))
    coverage_row = cur.fetchone()
    cur.close()
    from marginable import lookup
    for index, result in enumerate(results):
        result = dict(result)
        record = lookup(result.get("symbol"))
        if record:
            margin_meta = marginable_metadata()
            result["marginable"] = {
                "is_marginable": True,
                "instrument_type": record.get("instrument_type"),
                "margin_rate_pct": record.get("margin_rate_pct"),
                "marker": record.get("marker"),
                "can_buy": record.get("can_buy"),
                "can_add_collateral": record.get("can_add_collateral"),
                "can_short": record.get("can_short"),
                "schema_version": margin_meta.get("schema_version"),
                "source_document": margin_meta.get("source_document"),
                "effective_date": margin_meta.get("effective_date"),
                "source": margin_meta.get("source"),
            }
            # Preserve established v1 aliases for consumers that still read
            # them; their values remain sourced from the margin record.
            result["margin_rate_pct"] = record.get("margin_rate_pct")
            result["margin_marker"] = record.get("marker")
            result["margin_can_buy"] = record.get("can_buy")
            result["margin_can_add_collateral"] = record.get("can_add_collateral")
            result["margin_can_short"] = record.get("can_short")
        else:
            # Do not attach document/date/source metadata to a symbol for
            # which no margin record exists.
            result["marginable"] = {"is_marginable": False}
            result["margin_rate_pct"] = None
        _attach_unified_decision(result)
        # The shadow must see the final margin permissions. Re-project after
        # enrichment; the helper remains pure and raw v1 fields are retained.
        results[index] = _attach_decision_shadow_v2(result)
    results.sort(key=_result_sort_key)
    daily_projection = project_daily_vcp_watchlist(results) if daily_watchlist else None
    return {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "finder": "vcp_finder_60m",
        "interval": run["interval"],
        "market": run["market"],
        "run_id": run["run_id"],
        # v1 is the producer/raw morphology policy. v2 is an explicit serving
        # projection and must not replace the source contract field.
        "policy_version": run["policy_version"],
        "source_policy_version": run["policy_version"],
        "as_of": run["as_of"].isoformat() if hasattr(run["as_of"], "isoformat") else str(run["as_of"]),
        "ingestion_run_id": run["ingestion_run_id"],
        "ingestion_status": run["ingestion_status"],
        "fetch_completed_at": run["fetch_completed_at"].isoformat() if hasattr(run["fetch_completed_at"], "isoformat") else (str(run["fetch_completed_at"]) if run["fetch_completed_at"] else None),
        "universe_filter": universe_manifest["universe_filter"],
        "base_active_ord_count": universe_manifest["base_active_ord_count"],
        "eligible_count": universe_manifest["eligible_count"],
        "excluded_count": universe_manifest["excluded_count"],
        "margin_schema_version": universe_manifest.get("schema_version"),
        "margin_source": universe_manifest.get("source"),
        "margin_source_document": universe_manifest.get("source_document"),
        "margin_effective_date": universe_manifest.get("effective_date"),
        "decision_policy_version": DECISION_SHADOW_POLICY_VERSION,
        "universe": {
            "eligible": universe_manifest["eligible_count"],
            "evaluated": len(results),
            "returned": len(results),
            "missing_from_run": len(missing_from_run),
            "missing_symbols": missing_from_run,
        },
        "coverage": {"feed_unavailable": coverage_row["feed_unavailable"] or 0, "no_data": coverage_row["no_data"] or 0},
        # The Daily VCP Watchlist only needs capped lanes. Keep full-universe
        # counts in metadata, but never ship the 931-row audit payload here.
        "results": [] if daily_watchlist else results,
        "daily_watchlist": daily_projection,
    }


# ---------------------------------------------------------------------------
# Daily VCP Watchlist projection — fail-closed, quality-gated, capped lanes.
# ---------------------------------------------------------------------------

DAILY_VCP_WATCHLIST_VERSION = "signalix/daily-vcp-watchlist-v1"
DAILY_VCP_PROJECTION_MARKER = PROJECTION_MARKER
DAILY_VCP_CANDIDATE_POLICY = CANDIDATE_POLICY
DAILY_VCP_MIN_LIQUIDITY = 10_000_000
DAILY_VCP_CAP_ACTION_REVIEW = 10
DAILY_VCP_CAP_NEAR_TRIGGER = 10
DAILY_VCP_CAP_BREAKOUT_WATCH = 5
DAILY_VCP_CAP_STRUCTURE_WATCH = 10
DAILY_VCP_CAP_EVENT_WATCH = None


def daily_watchlist_query_states():
    """States that can enter one of the capped Daily VCP lanes."""
    return {"READY", "NEAR_TRIGGER", "CONFIRMED", "BREAKOUT_WATCH"}


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


def _dv_structure_pass(result):
    ev = result.get("evidence") or {}
    return bool(ev.get("prior_trend_pass") and ev.get("price_contraction_pass") and ev.get("base_pass"))


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


def _dv_invalidation_coherent(result):
    price = result.get("price") or {}
    close = _dv_to_float(price.get("last_close"))
    invalidation = _dv_to_float(price.get("invalidation"))
    return close is not None and close > 0 and invalidation is not None and 0 < invalidation < close


def _dv_event_watch(result):
    """Return true only for an explicit v2/live EVENT_WATCH classification."""
    shadow = result.get("decision_shadow_v2") or {}
    return shadow.get("decision_lane") == "EVENT_WATCH" or result.get("decision_lane") == "EVENT_WATCH"


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
    if _dv_event_watch(result):
        if _dv_fresh(result) and _dv_liquid(result) and result.get("late_watch") is not True:
            return "EVENT_WATCH"
        return None
    state = result.get("state")
    if state in {"EXTENDED", "FAILED", "STALE", "NOT_VERIFIED", "FORMING"}:
        return None
    if not _dv_fresh(result) or not _dv_liquid(result):
        return None
    if result.get("late_watch") is True:
        return None
    quality = _dv_quality_pass(result)
    if state in {"READY", "CONFIRMED"}:
        if quality and _dv_daily_context_pass(result) and _dv_action_review_coherent(result):
            return "ACTION_REVIEW"
        if _dv_structure_pass(result) and _dv_invalidation_coherent(result):
            return "STRUCTURE_WATCH"
        return None
    if state == "NEAR_TRIGGER":
        if quality and _dv_daily_context_pass(result):
            return "NEAR_TRIGGER"
        if _dv_structure_pass(result) and _dv_invalidation_coherent(result):
            return "STRUCTURE_WATCH"
        return None
    if state == "BREAKOUT_WATCH":
        if not _dv_daily_context_pass(result):
            return None
        return "BREAKOUT_WATCH"
    return None


def _dv_rejection_reason(result):
    """Return one deterministic reason for a row omitted from the watchlist."""
    if _dv_lane(result) is not None:
        return None
    state = result.get("state")
    if state in {"EXTENDED", "FORMING"}:
        return "state_not_watchlist_eligible"
    if state in {"FAILED", "STALE", "NOT_VERIFIED"}:
        return "state_invalid_or_unverified"
    if not _dv_fresh(result):
        return "freshness_or_feed_gate"
    if not _dv_liquid(result):
        return "liquidity_below_minimum"
    if result.get("late_watch") is True:
        return "late_watch"
    if state in {"READY", "CONFIRMED"}:
        if not _dv_quality_pass(result):
            return "structural_quality_gate"
        if not _dv_daily_context_pass(result):
            return "daily_context_gate"
        if not _dv_action_review_coherent(result):
            return "close_trigger_coherence_gate"
    elif state == "NEAR_TRIGGER":
        if not _dv_quality_pass(result):
            return "structural_quality_gate"
        if not _dv_daily_context_pass(result):
            return "daily_context_gate"
    elif state == "BREAKOUT_WATCH":
        if not _dv_daily_context_pass(result):
            return "daily_context_gate"
    else:
        return "state_not_watchlist_eligible"
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
      - STRUCTURE_WATCH: structurally valid but volume/context evidence pending.
      - EVENT_WATCH: explicit v2 event evidence, including FORMING rows, always
        watch-only and never actionable.

    Hard caps: ACTION_REVIEW <= 10, NEAR_TRIGGER <= 10, BREAKOUT_WATCH <= 5,
    STRUCTURE_WATCH <= 10. EVENT_WATCH is intentionally uncapped so the
    full explicit event-evidence lane remains visible as WATCH_ONLY.
    Cross-lane duplicate symbols are removed, keeping the highest-priority lane.
    """
    raw_lanes = {
        "ACTION_REVIEW": [], "NEAR_TRIGGER": [], "BREAKOUT_WATCH": [],
        "STRUCTURE_WATCH": [], "EVENT_WATCH": [],
    }
    caps = {
        "ACTION_REVIEW": DAILY_VCP_CAP_ACTION_REVIEW,
        "NEAR_TRIGGER": DAILY_VCP_CAP_NEAR_TRIGGER,
        "BREAKOUT_WATCH": DAILY_VCP_CAP_BREAKOUT_WATCH,
        "STRUCTURE_WATCH": DAILY_VCP_CAP_STRUCTURE_WATCH,
        "EVENT_WATCH": DAILY_VCP_CAP_EVENT_WATCH,
    }
    for r in results or []:
        lane = _dv_lane(r)
        if lane:
            raw_lanes[lane].append(r)
    candidate_counts = {lane: len(items) for lane, items in raw_lanes.items()}
    capped_counts = {}
    for lane, items in raw_lanes.items():
        items.sort(key=_dv_sort_key)
        cap = caps[lane]
        raw_lanes[lane] = items if cap is None else items[:cap]
        capped_counts[lane] = candidate_counts[lane] - len(raw_lanes[lane])
    seen = set()
    lanes = {}
    counts = {}
    duplicate_count = 0
    for lane in ("ACTION_REVIEW", "NEAR_TRIGGER", "BREAKOUT_WATCH", "STRUCTURE_WATCH", "EVENT_WATCH"):
        filtered = []
        for r in raw_lanes[lane]:
            sym = str(r.get("symbol", "")).upper()
            if not sym or sym in seen:
                duplicate_count += 1
                continue
            seen.add(sym)
            filtered.append(r)
        lanes[lane] = filtered
        counts[lane] = len(filtered)
    rejection_counts = {}
    for result in results or []:
        reason = _dv_rejection_reason(result)
        if reason:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
    accepted = sum(counts.values())
    return {
        "policy_version": DAILY_VCP_WATCHLIST_VERSION,
        "projection_marker": DAILY_VCP_PROJECTION_MARKER,
        "candidate_policy": DAILY_VCP_CANDIDATE_POLICY,
        "caps": caps,
        "counts": counts,
        "coverage": {
            "input": len(results or []),
            "accepted": accepted,
            "rejected": sum(rejection_counts.values()),
            "rejection_counts": rejection_counts,
            "candidate_counts": candidate_counts,
            "cap_dropped": sum(capped_counts.values()),
            "duplicate_dropped": duplicate_count,
        },
        "action_review": lanes["ACTION_REVIEW"],
        "near_trigger": lanes["NEAR_TRIGGER"],
        "breakout_watch": lanes["BREAKOUT_WATCH"],
        "structure_watch": lanes["STRUCTURE_WATCH"],
        "event_watch": lanes["EVENT_WATCH"],
    }


def persist_vcp_run(pg, payload):
    provenance_error = validate_vcp_run_provenance(
        ingestion_run_id=payload.get("ingestion_run_id"),
        ingestion_status=payload.get("ingestion_status"),
        fetch_completed_at=payload.get("fetch_completed_at"),
    )
    if provenance_error:
        raise ValueError("cannot persist VCP run with incomplete provenance: " + provenance_error)
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
