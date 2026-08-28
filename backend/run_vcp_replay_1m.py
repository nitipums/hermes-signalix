"""Append-only one-month point-in-time VCP 60m replay.

Uses only stored 60m bars with ts <= each daily as_of timestamp. This is an
analysis artifact, isolated from live VCP runs and Daily state.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg2
import psycopg2.extras

from instruments import active_ord_symbols
from vcp_finder import POLICY_VERSION, find_vcp_60m
from vcp_finder_db import _classify_types, load_daily_metrics, load_daily_trend_context

TYPE_POLICY_VERSION = "signalix/vcp-types-v2-early-entry"
TARGET_R_MULTIPLE = 3.0

DDL = """
CREATE TABLE IF NOT EXISTS vcp_finder_60m_replay_runs (
  replay_id TEXT PRIMARY KEY,
  window_start TIMESTAMPTZ NOT NULL,
  window_end TIMESTAMPTZ NOT NULL,
  as_of TIMESTAMPTZ NOT NULL,
  policy_version TEXT NOT NULL,
  eligible_count INTEGER NOT NULL,
  evaluated_count INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS vcp_finder_60m_replay_results (
  replay_id TEXT NOT NULL REFERENCES vcp_finder_60m_replay_runs(replay_id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  state TEXT NOT NULL,
  actionable BOOLEAN NOT NULL,
  result JSONB NOT NULL,
  PRIMARY KEY (replay_id, symbol)
);
CREATE INDEX IF NOT EXISTS vcp_replay_results_symbol_idx
  ON vcp_finder_60m_replay_results(symbol, replay_id);
"""


def pg_args():
    import os
    return dict(host=os.getenv("POSTGRES_HOST", "postgres"), port=5432,
                user=os.getenv("POSTGRES_USER", "signalix"),
                password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
                dbname=os.getenv("POSTGRES_DB", "signalix"))


def trade_plan(result, *, rr_multiple=TARGET_R_MULTIPLE):
    """Build a point-in-time plan; no future bars are read here."""
    vcp_type = result.get("vcp_type") or {}
    base_type = vcp_type.get("base_type")
    if base_type not in {"low_cheat_vcp", "standard_vcp"}:
        return None
    price = result.get("price") or {}
    entry = price.get("last_close") if base_type == "low_cheat_vcp" else (result.get("breakout") or {}).get("required_close")
    stop = price.get("invalidation")
    if entry is None or stop is None or float(entry) <= float(stop):
        return None
    risk = float(entry) - float(stop)
    return {
        "base_type": base_type,
        "entry_profile": vcp_type.get("entry_profile"),
        "entry": float(entry),
        "stop": float(stop),
        "target": float(entry) + float(rr_multiple) * risk,
        "rr_multiple": float(rr_multiple),
    }


def build_replay_result(symbol, rows, *, as_of, replay_id,
                        daily_context=None, daily_metrics=None,
                        rr_multiple=TARGET_R_MULTIPLE):
    """Build one point-in-time replay result with the same Daily inputs as live."""
    result = find_vcp_60m(
        pd.DataFrame(rows), as_of=as_of,
        daily_context=daily_context or {},
    )
    result["symbol"] = symbol
    result.setdefault("data", {})["daily_metrics"] = daily_metrics or {}
    result = _classify_types(result, ath_context={}, listing_context=None)
    result.setdefault("provenance", {})["replay_id"] = replay_id
    result["provenance"]["replay_as_of"] = as_of.isoformat()
    result["replay_trade_plan"] = trade_plan(result, rr_multiple=rr_multiple)
    return result


def evaluate_trade(plan, future_rows):
    """Evaluate only bars strictly after detection, conservatively."""
    if not plan:
        return None
    entry, stop, target = plan["entry"], plan["stop"], plan["target"]
    base_type = plan.get("base_type")
    pre_entry_bars = 0
    entry_ts = "detection"
    observed_rows = list(future_rows)
    if base_type == "standard_vcp":
        activation_idx = next(
            (i for i, row in enumerate(observed_rows) if float(row["high"]) >= entry),
            None,
        )
        if activation_idx is None:
            return {
                "outcome": "entry_not_activated",
                "entry_activated": False,
                "entry_ts": None,
                "pre_entry_bars": len(observed_rows),
                "bars_observed": 0,
                "mfe_r": None,
                "mae_r": None,
            }
        pre_entry_bars = activation_idx
        entry_ts = observed_rows[activation_idx].get("ts")
        observed_rows = observed_rows[activation_idx:]
    highs = [float(row["high"]) for row in observed_rows]
    lows = [float(row["low"]) for row in observed_rows]
    if not highs:
        outcome = "insufficient_future_data"
    else:
        hit_stop = any(low <= stop for low in lows)
        hit_target = any(high >= target for high in highs)
        if hit_stop and hit_target:
            stop_idx = next(i for i, low in enumerate(lows) if low <= stop)
            target_idx = next(i for i, high in enumerate(highs) if high >= target)
            outcome = "ambiguous_same_bar" if stop_idx == target_idx else ("stop_hit" if stop_idx < target_idx else "target_hit")
        elif hit_stop:
            outcome = "stop_hit"
        elif hit_target:
            outcome = "target_hit"
        else:
            outcome = "open_at_replay_end"
    risk = entry - stop
    return {
        "outcome": outcome,
        "entry_activated": True,
        "entry_ts": entry_ts,
        "pre_entry_bars": pre_entry_bars,
        "bars_observed": len(observed_rows),
        "mfe_r": max(((high - entry) / risk for high in highs), default=None),
        "mae_r": min(((low - entry) / risk for low in lows), default=None),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--end", default=None, help="UTC ISO timestamp; defaults to now")
    ap.add_argument("--cadence", choices=("daily", "60m"), default="daily")
    ap.add_argument("--trading-days", type=int, default=None)
    ap.add_argument("--rr", type=float, default=TARGET_R_MULTIPLE)
    args = ap.parse_args()
    end = datetime.fromisoformat(args.end) if args.end else datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = end - timedelta(days=args.days)
    pg = psycopg2.connect(**pg_args())
    try:
        cur = pg.cursor()
        cur.execute(DDL)
        pg.commit()
        symbols = sorted(set(active_ord_symbols(pg)))
        cur.execute(
            """SELECT symbol, ts, open, high, low, close, volume
               FROM intraday_price_data
               WHERE symbol=ANY(%s) AND interval='60m'
                 AND ts <= %s AND ts >= %s
               ORDER BY symbol, ts""",
            (symbols, end, start - timedelta(days=45)),
        )
        grouped = defaultdict(list)
        for row in cur.fetchall():
            grouped[row[0]].append({"ts": row[1], "open": row[2], "high": row[3], "low": row[4], "close": row[5], "volume": row[6]})
        cur.execute("SELECT DISTINCT (ts AT TIME ZONE 'Asia/Bangkok')::date FROM intraday_price_data WHERE interval='60m' AND ts >= %s AND ts <= %s ORDER BY 1", (start, end))
        dates = [r[0] for r in cur.fetchall()]
        if args.trading_days:
            selected_dates = set(dates[-max(1, args.trading_days):])
            selected_ts = [r["ts"] for rows in grouped.values() for r in rows if r["ts"].astimezone(ZoneInfo("Asia/Bangkok")).date() in selected_dates]
            if selected_ts:
                start = min(selected_ts)
        snapshots = []
        if args.cadence == "60m":
            snapshots = sorted({r["ts"] for rows in grouped.values() for r in rows if start <= r["ts"] <= end})
        else:
            for day in dates:
                day_end = datetime.combine(day, datetime.max.time(), tzinfo=timezone.utc)
                ts_values = [r["ts"] for rows in grouped.values() for r in rows if r["ts"] <= day_end]
                if ts_values:
                    snapshots.append(max(ts_values))
            snapshots = sorted(set(snapshots))
        summary = {"window_start": start.isoformat(), "window_end": end.isoformat(), "snapshots": len(snapshots), "runs": [], "coverage": {}}
        previous = {}
        first_events = {}
        outcome_counts = defaultdict(int)
        for idx, as_of in enumerate(snapshots, 1):
            replay_id = f"vcp-replay-1m-{args.cadence}-{as_of.strftime('%Y%m%dT%H%M%SZ')}-{idx:03d}"
            results = []
            daily_contexts = load_daily_trend_context(pg, symbols, as_of=as_of)
            daily_metrics = load_daily_metrics(pg, symbols, as_of=as_of)
            for symbol in symbols:
                rows = [r for r in grouped.get(symbol, []) if r["ts"] <= as_of][-400:]
                result = build_replay_result(
                    symbol, rows, as_of=as_of, replay_id=replay_id,
                    daily_context=daily_contexts.get(symbol),
                    daily_metrics=daily_metrics.get(symbol),
                    rr_multiple=args.rr,
                )
                result["provenance"]["replay_id"] = replay_id
                result["provenance"]["replay_window_start"] = start.isoformat()
                result["provenance"]["replay_as_of"] = as_of.isoformat()
                plan = result["replay_trade_plan"]
                if plan and (symbol, plan["base_type"]) not in first_events:
                    future = [r for r in grouped.get(symbol, []) if r["ts"] > as_of and r["ts"] <= end]
                    evaluation = evaluate_trade(plan, future)
                    event = {"symbol": symbol, "detected_at": as_of.isoformat(), **plan, **(evaluation or {})}
                    first_events[(symbol, plan["base_type"])] = event
                    outcome_counts[(plan["base_type"], event.get("outcome"))] += 1
                results.append(result)
            cur.execute("INSERT INTO vcp_finder_60m_replay_runs (replay_id,window_start,window_end,as_of,policy_version,eligible_count,evaluated_count) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (replay_id) DO NOTHING", (replay_id, start, end, as_of, POLICY_VERSION, len(symbols), len(results)))
            psycopg2.extras.execute_values(cur, "INSERT INTO vcp_finder_60m_replay_results (replay_id,symbol,state,actionable,result) VALUES %s ON CONFLICT (replay_id,symbol) DO NOTHING", [(replay_id, r["symbol"], r["state"], bool(r["actionable"]), json.dumps(r, default=str)) for r in results])
            pg.commit()
            states = defaultdict(int)
            transitions = []
            current = {}
            for r in results:
                states[r["state"]] += 1
                current[r["symbol"]] = r["state"]
                if r["symbol"] in previous and previous[r["symbol"]] != r["state"]:
                    transitions.append({"symbol": r["symbol"], "from": previous[r["symbol"]], "to": r["state"]})
            summary["runs"].append({"replay_id": replay_id, "as_of": as_of.isoformat(), "states": dict(states), "transitions": transitions})
            previous = current
        summary["coverage"] = {"eligible": len(symbols), "symbols_with_rows": sum(bool(grouped.get(s)) for s in symbols), "symbols_with_80_at_end": sum(len([r for r in grouped.get(s, []) if r["ts"] <= end]) >= 80 for s in symbols)}
        summary["type_policy_version"] = TYPE_POLICY_VERSION
        summary["target_rr"] = args.rr
        summary["first_events"] = list(first_events.values())
        summary["outcomes"] = {f"{kind}:{outcome}": count for (kind, outcome), count in outcome_counts.items()}
        print(json.dumps(summary, default=str))
    finally:
        pg.close()


if __name__ == "__main__":
    main()
