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
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
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


def find_vcp_universe_60m(pg, *, market="TH", symbols=None, as_of=None, config=None):
    cfg = config or VCP60Config()
    if market.upper() != "TH":
        raise ValueError("vcp_finder_60m currently supports market=TH only")
    eligible = sorted(set(symbols or active_ord_symbols(pg)))
    observed_as_of = as_of or datetime.now(timezone.utc)
    rows = load_vcp_60m_rows(pg, eligible, as_of=observed_as_of)
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
        result = find_vcp_60m(rows.get(symbol), as_of=observed_as_of, config=cfg)
        result["symbol"] = symbol
        result["data"]["feed_status"] = feed_status.get(symbol, {}).get("status", "unknown")
        result["data"]["feed_reason"] = feed_status.get(symbol, {}).get("reason")
        result["data"]["feed_retry_at"] = str(feed_status.get(symbol, {}).get("retry_at")) if feed_status.get(symbol, {}).get("retry_at") else None
        result["data"]["feed_last_success_at"] = str(feed_status.get(symbol, {}).get("last_success_at")) if feed_status.get(symbol, {}).get("last_success_at") else None
        result["provenance"]["run_id"] = run_id
        result["provenance"]["market"] = market.upper()
        results.append(result)
    results.sort(key=lambda x: x["symbol"])
    return {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "finder": "vcp_finder_60m",
        "interval": cfg.interval,
        "market": market.upper(),
        "run_id": run_id,
        "policy_version": POLICY_VERSION,
        "as_of": observed_as_of.isoformat(),
        "universe": {
            "eligible": len(eligible),
            "evaluated": len(results),
            "returned": len(results),
        },
        "results": results,
    }


def load_latest_vcp_run(pg, *, market="TH", state=None, symbol=None, limit=None, actionable=False):
    cur = pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT run_id, market, interval, policy_version, as_of,
                  eligible_count, evaluated_count
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
    if symbol:
        clauses.append("symbol=%s")
        params.append(symbol.upper())
    query = "SELECT result FROM vcp_finder_60m_results WHERE " + " AND ".join(clauses) + " ORDER BY symbol"
    if limit is not None:
        query += " LIMIT %s"
        params.append(max(1, min(int(limit), 5000)))
    cur.execute(query, params)
    results = [r["result"] for r in cur.fetchall()]
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
    return {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "finder": "vcp_finder_60m",
        "interval": run["interval"],
        "market": run["market"],
        "run_id": run["run_id"],
        "policy_version": run["policy_version"],
        "as_of": run["as_of"].isoformat() if hasattr(run["as_of"], "isoformat") else str(run["as_of"]),
        "universe": {"eligible": run["eligible_count"], "evaluated": run["evaluated_count"], "returned": len(results)},
        "results": results,
    }


def persist_vcp_run(pg, payload):
    init_vcp_schema(pg)
    cur = pg.cursor()
    cur.execute(
        """INSERT INTO vcp_finder_60m_runs
           (run_id, market, interval, policy_version, as_of, eligible_count, evaluated_count)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (payload["run_id"], payload["market"], payload["interval"], payload["policy_version"],
         payload["as_of"], payload["universe"]["eligible"], payload["universe"]["evaluated"]),
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
