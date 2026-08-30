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
from marginable import eligible_symbols, lookup as marginable_lookup, metadata as marginable_metadata
from vcp_decision_policy import project_vcp_decision_shadow
from vcp_finder import POLICY_VERSION, find_vcp_60m
from vcp_finder_db import _classify_types, load_daily_metrics, load_daily_trend_context

TYPE_POLICY_VERSION = "signalix/vcp-types-v2-early-entry"
TARGET_R_MULTIPLE = 3.0
LOCAL_TZ = ZoneInfo("Asia/Bangkok")
DEFAULT_MAX_SNAPSHOTS = 2_000
DEFAULT_MAX_DIAGNOSTIC_ITEMS = 500

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
ALTER TABLE vcp_finder_60m_replay_runs
  ADD COLUMN IF NOT EXISTS universe_filter TEXT,
  ADD COLUMN IF NOT EXISTS base_active_ord_count INTEGER,
  ADD COLUMN IF NOT EXISTS excluded_count INTEGER,
  ADD COLUMN IF NOT EXISTS margin_schema_version TEXT,
  ADD COLUMN IF NOT EXISTS margin_source_document TEXT,
  ADD COLUMN IF NOT EXISTS margin_effective_date DATE,
  ADD COLUMN IF NOT EXISTS cadence TEXT,
  ADD COLUMN IF NOT EXISTS snapshots_per_day INTEGER;
"""


def make_replay_id(prefix, cadence, as_of, index, *, universe="active_ord",
                   snapshots_per_day=1):
    """Build an idempotency key, retaining the original default id format."""
    timestamp = as_of.strftime('%Y%m%dT%H%M%SZ')
    if universe == "active_ord" and snapshots_per_day == 1:
        return f"{prefix}-{cadence}-{timestamp}-{index:03d}"
    return (f"{prefix}-{universe}-spd{snapshots_per_day}-{cadence}-"
            f"{timestamp}-{index:03d}")


def pending_replay_points(prefix, cadence, snapshots, existing_ids, *,
                          universe="active_ord", snapshots_per_day=1):
    pending = []
    for index, as_of in enumerate(snapshots, 1):
        replay_id = make_replay_id(
            prefix, cadence, as_of, index, universe=universe,
            snapshots_per_day=snapshots_per_day,
        )
        if replay_id not in existing_ids:
            pending.append((index, as_of, replay_id))
    return pending


def _utc_timestamp(value):
    """Normalize a queried timestamp without changing its instant."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def resolve_replay_universe(pg, universe):
    """Resolve the selected symbols and auditable manifest for a replay."""
    active_symbols = sorted(set(active_ord_symbols(pg)))
    if universe == "marginable_long":
        return eligible_symbols(active_symbols)
    margin_meta = marginable_metadata()
    return active_symbols, {
        "universe_filter": "active_ord",
        "base_active_ord_count": len(active_symbols),
        "eligible_count": len(active_symbols),
        "excluded_count": 0,
        "excluded_reason": None,
        "schema_version": "signalix.marginable.v1",
        "source_document": margin_meta.get("source_document"),
        "effective_date": margin_meta.get("effective_date"),
    }


def load_replay_rows(cur, symbols, *, end, query_start):
    """Load only the selected universe's stored 60m rows."""
    cur.execute(
        """SELECT symbol, ts, open, high, low, close, volume
           FROM intraday_price_data
           WHERE symbol=ANY(%s) AND interval='60m'
             AND ts <= %s AND ts >= %s
           ORDER BY symbol, ts""",
        (symbols, end, query_start - timedelta(days=45)),
    )
    grouped = defaultdict(list)
    for row in cur.fetchall():
        grouped[row[0]].append({
            "ts": row[1], "open": row[2], "high": row[3], "low": row[4],
            "close": row[5], "volume": row[6],
        })
    return grouped


def insert_replay_run(cur, *, replay_id, window_start, window_end, as_of,
                      eligible_count, evaluated_count, universe_manifest,
                      cadence, snapshots_per_day):
    """Persist one immutable replay-run manifest without rewriting old rows."""
    cur.execute(
        """INSERT INTO vcp_finder_60m_replay_runs
        (replay_id,window_start,window_end,as_of,policy_version,
         eligible_count,evaluated_count,universe_filter,
         base_active_ord_count,excluded_count,margin_schema_version,
         margin_source_document,margin_effective_date,cadence,
         snapshots_per_day)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (replay_id) DO NOTHING""",
        (replay_id, window_start, window_end, as_of, POLICY_VERSION,
         eligible_count, evaluated_count, universe_manifest["universe_filter"],
         universe_manifest.get("base_active_ord_count"),
         universe_manifest.get("excluded_count"),
         universe_manifest.get("schema_version"),
         universe_manifest.get("source_document"),
         universe_manifest.get("effective_date"), cadence, snapshots_per_day),
    )


def select_replay_snapshots(timestamps, *, end, cadence="daily",
                            trading_days=None, window_start=None,
                            max_snapshots=DEFAULT_MAX_SNAPSHOTS,
                            snapshots_per_day=1):
    """Select deterministic snapshots using Asia/Bangkok trading dates."""
    if cadence not in {"daily", "60m"}:
        raise ValueError(f"unsupported replay cadence: {cadence}")
    if snapshots_per_day not in {1, 2}:
        raise ValueError("snapshots_per_day must be 1 or 2")
    if cadence == "60m" and snapshots_per_day != 1:
        raise ValueError("snapshots_per_day=2 is only supported for daily cadence")
    if max_snapshots < 1:
        raise ValueError("max_snapshots must be positive")
    if trading_days is not None and trading_days < 1:
        raise ValueError("trading_days must be positive")
    end_utc = _utc_timestamp(end)
    start_utc = _utc_timestamp(window_start) if window_start is not None else None
    values = sorted({
        _utc_timestamp(value) for value in timestamps
        if _utc_timestamp(value) <= end_utc
        and (start_utc is None or _utc_timestamp(value) >= start_utc)
    })
    by_date = defaultdict(list)
    for value in values:
        by_date[value.astimezone(LOCAL_TZ).date()].append(value)
    available_dates = sorted(by_date)
    if trading_days is not None:
        if len(available_dates) < trading_days:
            raise ValueError(
                f"requested {trading_days} trading dates, but queried data "
                f"represents only {len(available_dates)} completed dates"
            )
        selected_dates = available_dates[-trading_days:]
    else:
        selected_dates = available_dates
    if cadence == "daily":
        if snapshots_per_day == 1:
            snapshots = [max(by_date[day]) for day in selected_dates]
        else:
            snapshots = []
            for day in selected_dates:
                cutoff_points = []
                for hour, minute in ((12, 30), (16, 45)):
                    cutoff = datetime.combine(day, datetime.min.time(), LOCAL_TZ).replace(
                        hour=hour, minute=minute).astimezone(timezone.utc)
                    available = [value for value in by_date[day] if value <= cutoff]
                    if not available:
                        raise ValueError(
                            f"no snapshot at or before {hour:02d}:{minute:02d} BKK "
                            f"for selected date {day}"
                        )
                    cutoff_points.append(max(available))
                snapshots.extend(cutoff_points)
    else:
        snapshots = [value for day in selected_dates for value in by_date[day]]
    snapshots = sorted(set(snapshots))
    if len(snapshots) > max_snapshots:
        raise ValueError(
            f"selected {len(snapshots)} {cadence} snapshots, exceeding "
            f"max_snapshots={max_snapshots}"
        )
    if not snapshots:
        raise ValueError("queried data represents no replay snapshots")
    return {
        "snapshots": snapshots,
        "selected_dates": selected_dates,
        "window_start": snapshots[0],
        "window_end": snapshots[-1],
    }


def point_in_time_rows(rows, as_of):
    """Return only bars available at the snapshot instant (no look-ahead)."""
    as_of_utc = _utc_timestamp(as_of)
    return [row for row in rows if _utc_timestamp(row["ts"]) <= as_of_utc]


def daily_context_boundary(as_of, *, cadence="daily"):
    """Return the Daily date boundary permitted for a replay snapshot.

    A midday observation cannot see that session's Daily EOD row.  The
    official EOD snapshot is the one exception: at the Bangkok 16:45
    boundary the completed same-day Daily row is available.
    """
    instant = _utc_timestamp(as_of).astimezone(LOCAL_TZ)
    # Both daily two-point and 60m replay snapshots are blind to the same-day
    # Daily close until the explicit Bangkok EOD boundary.  In particular,
    # cadence must not make a 60m EOD snapshot permanently stale.
    if instant.time() >= datetime.min.replace(hour=16, minute=45).time():
        return instant.date()
    return instant.date() - timedelta(days=1)


def load_replay_daily_context(pg, symbols, as_of, *, cadence="daily"):
    """Load Daily evidence at the replay-safe boundary for this snapshot."""
    boundary = daily_context_boundary(as_of, cadence=cadence)
    return (
        load_daily_trend_context(pg, symbols, as_of=boundary),
        load_daily_metrics(pg, symbols, as_of=boundary),
        boundary,
    )


def append_bounded_diagnostic(items, item, limit):
    """Keep diagnostics bounded while callers retain exact aggregate counts."""
    if len(items) < limit:
        items.append(item)


def validate_replay_results(results, eligible_count, replay_id):
    """Enforce complete active-ORD coverage before any snapshot insert."""
    if len(results) != eligible_count:
        raise RuntimeError(
            f"replay {replay_id} evaluated {len(results)} of "
            f"{eligible_count} selected eligible symbols"
        )
    if any("decision_shadow_v2" not in result for result in results):
        raise RuntimeError(f"replay {replay_id} missing decision_shadow_v2")


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


def sequence_v2_trade_plan(result, *, rr_multiple=TARGET_R_MULTIPLE):
    """Build standard breakout plan from latest-sequence shadow only."""
    shadow = result.get("sequence_policy_shadow_v2") or {}
    if not shadow.get("standard_entry_eligible"):
        return None
    entry = (shadow.get("breakout") or {}).get("required_close")
    stop = (shadow.get("price") or {}).get("invalidation")
    if entry is None or stop is None or float(entry) <= float(stop):
        return None
    risk = float(entry) - float(stop)
    return {
        "base_type": "standard_vcp",
        "entry_profile": "standard_entry",
        "entry": float(entry),
        "stop": float(stop),
        "target": float(entry) + float(rr_multiple) * risk,
        "rr_multiple": float(rr_multiple),
        "sequence_policy_version": "signalix/vcp-sequence-policy-shadow-v2",
    }


def build_replay_result(symbol, rows, *, as_of, replay_id,
                        daily_context=None, daily_metrics=None,
                        daily_context_as_of=None,
                        marginable_record=None,
                        rr_multiple=TARGET_R_MULTIPLE):
    """Build one point-in-time replay result with the same Daily inputs as live."""
    if daily_context_as_of is None:
        daily_context_as_of = daily_context_boundary(as_of)
    result = find_vcp_60m(
        pd.DataFrame(rows), as_of=as_of,
        daily_context=daily_context or {},
        include_sequence_policy_shadow=True,
    )
    result["symbol"] = symbol
    result.setdefault("data", {})["daily_metrics"] = daily_metrics or {}
    result["marginable"] = {
        "is_marginable": bool(marginable_record),
        "margin_rate_pct": marginable_record.get("margin_rate_pct") if marginable_record else None,
    }
    result = _classify_types(result, ath_context={}, listing_context=None)
    result.setdefault("provenance", {})["replay_id"] = replay_id
    result["provenance"]["replay_as_of"] = as_of.isoformat()
    result["provenance"]["daily_context_as_of"] = (
        daily_context_as_of.isoformat()
        if hasattr(daily_context_as_of, "isoformat") else daily_context_as_of
    )
    result["replay_trade_plan"] = trade_plan(result, rr_multiple=rr_multiple)
    result["sequence_v2_trade_plan"] = sequence_v2_trade_plan(
        result, rr_multiple=rr_multiple)
    result["decision_shadow_v2"] = project_vcp_decision_shadow(result)
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


def attach_replay_evaluation(result, plan, future_rows):
    evaluation = evaluate_trade(plan, future_rows)
    result["replay_evaluation"] = evaluation
    return evaluation


def attach_sequence_v2_evaluation(result, future_rows):
    plan = result.get("sequence_v2_trade_plan")
    if not plan:
        result["sequence_v2_replay_evaluation"] = None
        return None
    evaluation = evaluate_trade(plan, future_rows)
    result["sequence_v2_replay_evaluation"] = evaluation
    return evaluation


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--end", default=None, help="UTC ISO timestamp; defaults to now")
    ap.add_argument("--cadence", choices=("daily", "60m"), default="daily")
    ap.add_argument("--snapshots-per-day", type=int, choices=(1, 2), default=1)
    ap.add_argument("--universe", choices=("active_ord", "marginable_long"), default="active_ord")
    ap.add_argument("--trading-days", type=int, default=None)
    ap.add_argument("--max-snapshots", type=int, default=DEFAULT_MAX_SNAPSHOTS)
    ap.add_argument("--max-diagnostic-items", type=int, default=DEFAULT_MAX_DIAGNOSTIC_ITEMS)
    ap.add_argument("--rr", type=float, default=TARGET_R_MULTIPLE)
    ap.add_argument("--id-prefix", default="vcp-replay-1m")
    args = ap.parse_args()
    end = datetime.fromisoformat(args.end) if args.end else datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    query_start = end - timedelta(days=args.days)
    if args.max_diagnostic_items < 1:
        ap.error("--max-diagnostic-items must be positive")
    pg = psycopg2.connect(**pg_args())
    try:
        cur = pg.cursor()
        cur.execute(DDL)
        pg.commit()
        symbols, universe_manifest = resolve_replay_universe(pg, args.universe)
        marginable_records = {symbol: marginable_lookup(symbol) for symbol in symbols}
        grouped = load_replay_rows(
            cur, symbols, end=end, query_start=query_start,
        )
        selection = select_replay_snapshots(
            [r["ts"] for rows in grouped.values() for r in rows],
            end=end, cadence=args.cadence, trading_days=args.trading_days,
            window_start=query_start, max_snapshots=args.max_snapshots,
            snapshots_per_day=args.snapshots_per_day,
        )
        snapshots = selection["snapshots"]
        start, replay_end = selection["window_start"], selection["window_end"]
        cur.execute(
            "SELECT replay_id FROM vcp_finder_60m_replay_runs WHERE replay_id LIKE %s",
            (args.id_prefix + "-%",),
        )
        existing_ids = {row[0] for row in cur.fetchall()}
        pending_points = pending_replay_points(
            args.id_prefix, args.cadence, snapshots, existing_ids,
            universe=args.universe, snapshots_per_day=args.snapshots_per_day,
        )
        summary = {
            "window_start": start.isoformat(), "window_end": replay_end.isoformat(),
            "snapshots": len(snapshots), "snapshots_existing": len(snapshots) - len(pending_points),
            "snapshots_pending": len(pending_points), "runs": [], "coverage": {},
            "universe": {**universe_manifest, "cadence": args.cadence,
                         "snapshots_per_day": args.snapshots_per_day},
        }
        previous = {}
        first_events = []
        first_event_keys = set()
        first_sequence_v2_events = []
        first_sequence_event_symbols = set()
        outcome_counts = defaultdict(int)
        sequence_v2_outcome_counts = defaultdict(int)
        for idx, as_of, replay_id in pending_points:
            results = []
            daily_contexts, daily_metrics, daily_as_of = load_replay_daily_context(
                pg, symbols, as_of, cadence=args.cadence)
            for symbol in symbols:
                rows = point_in_time_rows(grouped.get(symbol, []), as_of)[-400:]
                result = build_replay_result(
                    symbol, rows, as_of=as_of, replay_id=replay_id,
                    daily_context=daily_contexts.get(symbol),
                    daily_metrics=daily_metrics.get(symbol),
                    daily_context_as_of=daily_as_of,
                    marginable_record=marginable_records.get(symbol),
                    rr_multiple=args.rr,
                )
                result["provenance"]["replay_id"] = replay_id
                result["provenance"]["replay_window_start"] = start.isoformat()
                result["provenance"]["replay_as_of"] = as_of.isoformat()
                result["provenance"]["replay_manifest"] = {
                    **universe_manifest, "cadence": args.cadence,
                    "snapshots_per_day": args.snapshots_per_day,
                }
                plan = result["replay_trade_plan"]
                if plan and (symbol, plan["base_type"]) not in first_event_keys:
                    future = [r for r in grouped.get(symbol, []) if r["ts"] > as_of and r["ts"] <= replay_end]
                    evaluation = attach_replay_evaluation(result, plan, future)
                    event = {"symbol": symbol, "detected_at": as_of.isoformat(), **plan, **(evaluation or {})}
                    first_event_keys.add((symbol, plan["base_type"]))
                    append_bounded_diagnostic(first_events, event, args.max_diagnostic_items)
                    outcome_counts[(plan["base_type"], event.get("outcome"))] += 1
                sequence_plan = result["sequence_v2_trade_plan"]
                if sequence_plan and symbol not in first_sequence_event_symbols:
                    future = [r for r in grouped.get(symbol, []) if r["ts"] > as_of and r["ts"] <= replay_end]
                    evaluation = attach_sequence_v2_evaluation(result, future)
                    event = {
                        "symbol": symbol, "detected_at": as_of.isoformat(),
                        **sequence_plan, **(evaluation or {}),
                    }
                    first_sequence_event_symbols.add(symbol)
                    append_bounded_diagnostic(first_sequence_v2_events, event, args.max_diagnostic_items)
                    sequence_v2_outcome_counts[event.get("outcome")] += 1
                results.append(result)
            validate_replay_results(results, len(symbols), replay_id)
            insert_replay_run(
                cur, replay_id=replay_id, window_start=start,
                window_end=replay_end, as_of=as_of,
                eligible_count=len(symbols), evaluated_count=len(results),
                universe_manifest=universe_manifest, cadence=args.cadence,
                snapshots_per_day=args.snapshots_per_day,
            )
            psycopg2.extras.execute_values(cur, "INSERT INTO vcp_finder_60m_replay_results (replay_id,symbol,state,actionable,result) VALUES %s ON CONFLICT (replay_id,symbol) DO NOTHING", [(replay_id, r["symbol"], r["state"], bool(r["actionable"]), json.dumps(r, default=str)) for r in results])
            pg.commit()
            states = defaultdict(int)
            transitions = []
            transition_count = 0
            current = {}
            for r in results:
                states[r["state"]] += 1
                current[r["symbol"]] = r["state"]
                if r["symbol"] in previous and previous[r["symbol"]] != r["state"]:
                    transition_count += 1
                    append_bounded_diagnostic(transitions, {"symbol": r["symbol"], "from": previous[r["symbol"]], "to": r["state"]}, args.max_diagnostic_items)
            append_bounded_diagnostic(summary["runs"], {"replay_id": replay_id, "as_of": as_of.isoformat(), "states": dict(states), "transitions": transitions, "transition_count": transition_count}, args.max_diagnostic_items)
            previous = current
        summary["runs_omitted"] = max(0, len(pending_points) - len(summary["runs"]))
        summary["coverage"] = {"eligible": len(symbols), "symbols_with_rows": sum(bool(grouped.get(s)) for s in symbols), "symbols_with_80_at_end": sum(len([r for r in grouped.get(s, []) if r["ts"] <= replay_end]) >= 80 for s in symbols)}
        summary["type_policy_version"] = TYPE_POLICY_VERSION
        summary["target_rr"] = args.rr
        summary["first_events"] = first_events
        summary["first_events_omitted"] = max(0, len(first_event_keys) - len(first_events))
        summary["outcomes"] = {f"{kind}:{outcome}": count for (kind, outcome), count in outcome_counts.items()}
        summary["sequence_v2_first_events"] = first_sequence_v2_events
        summary["sequence_v2_first_events_omitted"] = max(0, len(first_sequence_event_symbols) - len(first_sequence_v2_events))
        summary["sequence_v2_outcomes"] = dict(sequence_v2_outcome_counts)
        print(json.dumps(summary, default=str))
    finally:
        pg.close()


if __name__ == "__main__":
    main()
