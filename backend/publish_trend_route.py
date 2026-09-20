"""Build and publish the immutable Daily Trend Route read model.

This is the refresh-time seam for Trend Route.  It owns the only raw Daily
database read: one SELECT-only connection resolves the current fixed
``marginable_long`` universe, chooses one market-wide completed cutoff, and
loads one bounded history batch.  HTTP readers consume the resulting artifact
through :mod:`trend_route_publisher` and never call this module.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time
from typing import Any, Mapping, cast

from daily_history import DailyHistoryAdapter
from main_trend_mapping import POLICY_VERSION as MAIN_TREND_POLICY_VERSION
from main_trend_mapping import classify_main_trend
from trend_map import RETRIEVAL_CAP
from technical_indicators import POLICY_VERSION as INDICATOR_POLICY_VERSION
from technical_indicators import build_technical_indicators
from trend_route import MAX_SESSIONS, ROUTE_POLICY_VERSION, build_route
from trend_route_publisher import publish_route_read_model

UNIVERSE = "marginable_long"
PUBLISHER_VERSION = "trend-route-publisher-v1"
NO_ACTION = {"actionability": "NONE", "signals": [], "orders": [], "alerts": []}


def _date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _finite(value: Any) -> bool:
    try:
        return not isinstance(value, bool) and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _valid(row: Mapping[str, Any]) -> bool:
    if _date(row.get("date")) is None or not all(_finite(row.get(key)) for key in ("open", "high", "low", "close", "volume")):
        return False
    high, low = float(row["high"]), float(row["low"])
    return high >= max(float(row["open"]), float(row["close"])) and low <= min(float(row["open"]), float(row["close"])) and low <= high


def _snapshot(row_prefix: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Classify only the prefix ending at this snapshot's completed Daily row."""
    if not row_prefix:
        return None
    candles = [{key: row[key] for key in ("open", "high", "low", "close", "volume")} for row in row_prefix]
    indicators = build_technical_indicators(candles, "1D")
    for key in ("open", "high", "low", "close", "volume"):
        indicators["series"][key] = [row[key] for row in row_prefix]
    as_of = _date(row_prefix[-1]["date"])
    indicators["as_of"] = as_of.isoformat() if as_of else None
    classified = classify_main_trend(indicators)
    return {"date": as_of.isoformat(), "main_trend": classified["main_trend"],
            "policy_version": MAIN_TREND_POLICY_VERSION, "source": "published_daily_main_trend"}


def _row_stats(rows: Any, cutoff: Any) -> tuple[list[Mapping[str, Any]], dict[str, int]]:
    """Filter, de-duplicate, and order valid completed rows through cutoff."""
    cutoff_date = _date(cutoff)
    if cutoff_date is None:
        return [], {"rows_loaded": 0, "rows_used": 0, "future_rows_excluded": 0, "invalid_rows": 0}
    by_date: dict[dt.date, Mapping[str, Any]] = {}
    future = invalid = 0
    for row in rows or []:
        if not isinstance(row, Mapping):
            invalid += 1
            continue
        row_date = _date(row.get("date"))
        if row_date is None:
            invalid += 1
            continue
        if row_date > cutoff_date:
            future += 1
            continue
        if not _valid(row):
            invalid += 1
            continue
        by_date[row_date] = row
    ordered = [by_date[key] for key in sorted(by_date)]
    return ordered, {"rows_loaded": len(rows or []), "rows_used": len(ordered),
                     "future_rows_excluded": int(future), "invalid_rows": invalid}


def classify_history_reference(rows: Any, cutoff: Any, *, max_sessions: int = MAX_SESSIONS) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Slow, prefix-recompute reference path used to prove equivalence."""
    ordered, stats = _row_stats(rows, cutoff)
    snapshots = []
    for index in range(len(ordered)):
        point = _snapshot(ordered[:index + 1])
        if point is not None:
            snapshots.append(point)
    return snapshots, stats


def _indicator_snapshot(indicators: Mapping[str, Any], rows: list[Mapping[str, Any]], index: int) -> dict[str, Any]:
    """Make the exact classifier input for ``rows[index]`` from aligned arrays."""
    # The unchanged classifier only reads close[-1], each MA[-1], and each
    # MA[-21].  A 21-value tail is therefore the smallest exact point-in-time
    # view, and avoids copying unrelated indicator arrays at every snapshot.
    start = max(0, index - 20)
    ma_arrays = indicators.get("series", {}).get("ma", {})
    series = {"close": [rows[index]["close"]],
              "ma": {str(period): list(ma_arrays.get(str(period), [])[start:index + 1])
                     for period in (5, 10, 20, 50, 100, 200)}}
    point = {"timeframe": indicators.get("timeframe", "1D"), "series": series}
    point["latest"] = {
        "close": rows[index]["close"],
        "ma": {period: values[-1] if values else None for period, values in series["ma"].items()},
    }
    as_of = _date(rows[index]["date"])
    point["as_of"] = as_of.isoformat() if as_of else None
    return point


def classify_history(rows: Any, cutoff: Any, *, max_sessions: int = MAX_SESSIONS) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return point-in-time Main Trend snapshots without future rows.

    Indicator arrays are computed once and remain aligned to the ordered valid
    rows.  Each classifier invocation receives only the prefix ending at its
    own completed Daily row, preserving the reference path's warmup semantics.
    """
    ordered, stats = _row_stats(rows, cutoff)
    if not ordered:
        return [], stats
    candles = [{key: row[key] for key in ("open", "high", "low", "close", "volume")} for row in ordered]
    indicators = build_technical_indicators(candles, "1D")
    snapshots = []
    for index in range(len(ordered)):
        classified = classify_main_trend(_indicator_snapshot(indicators, ordered, index))
        as_of = _date(ordered[index]["date"])
        snapshots.append({"date": as_of.isoformat(), "main_trend": classified["main_trend"],
                          "policy_version": MAIN_TREND_POLICY_VERSION, "source": "published_daily_main_trend"})
    return snapshots, stats


def benchmark_classification(symbol_counts: tuple[int, ...] = (1, 10, 237), *, sessions: int = MAX_SESSIONS) -> list[dict[str, Any]]:
    """Time the optimized classifier on deterministic fake Daily histories."""
    rows = [{"date": (dt.date(2020, 1, 1) + dt.timedelta(days=index)).isoformat(),
             "open": 100.0 + index, "high": 101.0 + index, "low": 99.0 + index,
             "close": 100.5 + index, "volume": 1000.0 + index}
            for index in range(sessions)]
    results = []
    for count in symbol_counts:
        started = time.perf_counter()
        for _ in range(count):
            classify_history(rows, rows[-1]["date"], max_sessions=sessions)
        results.append({"symbols": count, "sessions": sessions,
                        "elapsed_seconds": time.perf_counter() - started})
    return results


def _cutoff(adapter: Any, conn: Any) -> Any:
    resolver = getattr(adapter, "latest_completed_daily_cutoff", None)
    if callable(resolver):
        value = resolver(conn)
        if value is not None:
            return value
    rows, _ = adapter._exec_select(conn, """
        SELECT MAX(day) FROM (
            SELECT MAX(date) AS day FROM price_data WHERE market='TH'
            UNION ALL
            SELECT MAX(session_date) AS day FROM derived_daily_price_data
            WHERE is_official=FALSE AND source='settrade' AND source_timeframe='60m'
              AND source_bar_count=8
              AND derivation_method='settrade_60m_complete_bangkok_session_ohlcv_v1'
              AND source_completion_cutoff >= ((session_date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')
              AND source_completion_cutoff <= NOW()
        ) completed_daily
    """)
    return rows[0][0] if rows and rows[0] and rows[0][0] is not None else None


def build_publication(*, adapter: Any | None = None, conn: Any | None = None,
                      cutoff: Any = None, max_sessions: int = MAX_SESSIONS) -> dict[str, Any]:
    if adapter is None:
        from trend_map import BackendDailyAdapter

        adapter = BackendDailyAdapter()
    history_adapter = cast(DailyHistoryAdapter, adapter)
    owns_conn = conn is None
    conn = conn or adapter._get_conn()
    try:
        symbols, manifest = adapter.resolve_universe(conn, UNIVERSE)
        symbols = sorted({str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()})
        if not symbols:
            raise RuntimeError("resolved marginable_long universe is empty")
        cutoff = cutoff if cutoff is not None else _cutoff(adapter, conn)
        cutoff_date = _date(cutoff)
        if cutoff_date is None:
            raise RuntimeError("no completed Daily cutoff available")
        loaded = history_adapter.load_daily_pit_batch(conn, symbols, cutoff_date)
        expected_sessions = sorted({row_date for symbol in symbols
                                    for row in ((loaded.get(symbol, ([], None, {}))[0]
                                                if isinstance(loaded.get(symbol, ([], None, {})), (tuple, list))
                                                else loaded.get(symbol, [])) or [])
                                    if isinstance(row, Mapping) and _valid(row)
                                    for row_date in [_date(row.get("date"))]
                                    if row_date is not None and row_date <= cutoff_date})
        routes = {}
        coverage = {}
        for symbol in symbols:
            value = loaded.get(symbol, ([], None, {}))
            rows = value[0] if isinstance(value, (tuple, list)) else value
            snapshots, stats = classify_history(rows, cutoff_date, max_sessions=max_sessions)
            route = build_route(snapshots, symbol=symbol, cutoff=cutoff_date, max_sessions=max_sessions,
                                expected_sessions=expected_sessions)
            route["coverage"].update(stats)
            routes[symbol] = route
            coverage[symbol] = stats
        policy = {"route": ROUTE_POLICY_VERSION, "main_trend_classifier": MAIN_TREND_POLICY_VERSION,
                  "indicators": INDICATOR_POLICY_VERSION, "publisher": PUBLISHER_VERSION,
                  "retrieval_cap": RETRIEVAL_CAP, "max_sessions": max_sessions}
        universe = {**dict(manifest or {}), "scope": UNIVERSE, "symbols": symbols,
                    "resolved_count": len(symbols), "readback_count": len(symbols),
                    "resolution": "BackendDailyAdapter.resolve_universe"}
        metadata = {"cutoff": cutoff_date.isoformat(), "policy": {**policy, "hash": _json_hash(policy)},
                    "coverage": {"resolved_count": len(symbols), "routes": len(routes),
                                 "full_routes": sum(route["status"] == "FULL" for route in routes.values()),
                                 "partial_routes": sum(route["status"] == "PARTIAL" for route in routes.values()),
                                 "not_verified_routes": sum(route["status"] == "NOT_VERIFIED" for route in routes.values()),
                                 "expected_sessions": len(expected_sessions), "no_lookahead": True},
                    "source": {"adapter": type(adapter).__name__, "tables": ["price_data", "derived_daily_price_data"],
                               "timeframe": "1D", "query_mode": "SELECT_ONLY", "provenance": "completed_daily_ohlcv"},
                    "no_action": NO_ACTION, "publisher": PUBLISHER_VERSION}
        return {"routes": routes, "universe": universe, "metadata": metadata}
    finally:
        if owns_conn:
            conn.close()


def _json_hash(value: Any) -> str:
    return __import__("hashlib").sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def publish_trend_route(*, adapter: Any | None = None, conn: Any | None = None,
                        cutoff: Any = None, root: str | None = None,
                        published_at: Any = None, max_sessions: int = MAX_SESSIONS) -> dict[str, Any]:
    built = build_publication(adapter=adapter, conn=conn, cutoff=cutoff, max_sessions=max_sessions)
    result = publish_route_read_model(built["routes"], root=root, published_at=published_at,
                                      universe=built["universe"], metadata=built["metadata"])
    return {**result, "cutoff": built["metadata"]["cutoff"], "coverage": built["metadata"]["coverage"],
            "universe": built["universe"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the SELECT-only Daily Trend Route artifact")
    parser.add_argument("--root", help="artifact root; defaults to SIGNALIX_TREND_ROUTE_ROOT")
    parser.add_argument("--cutoff", help="optional completed Daily cutoff YYYY-MM-DD")
    parser.add_argument("--benchmark", action="store_true", help="run the deterministic 1/10/237-symbol classifier benchmark")
    args = parser.parse_args()
    if args.benchmark:
        print(json.dumps(benchmark_classification(), sort_keys=True))
        return 0
    print(json.dumps(publish_trend_route(root=args.root, cutoff=args.cutoff), sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
