"""Read-only bounded Market Breadth v2 replay and publisher (MB-4A).

The source boundary is intentionally injectable.  The production adapter uses
one read-only PostgreSQL transaction and SELECT-only SQL; tests can provide a
small source object without a database.  Nothing in this module is used by a
request handler: requests consume the immutable artifact made here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from instruments import active_ord_symbols
from main_trend_mapping import POLICY_VERSION as MAIN_TREND_POLICY_VERSION
from main_trend_mapping import classify_main_trend
from market_breadth import build_market_breadth, select_official_first_daily
from market_breadth_artifact import publish_market_breadth_artifact
from technical_indicators import build_technical_indicators

CONTEXT_SESSIONS = 520
EMITTED_SESSIONS = 260
DERIVED_METHOD = "settrade_60m_complete_bangkok_session_ohlcv_v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _as_date(value: Any) -> str:
    return str(value)[:10]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _valid_derived(row: Mapping[str, Any]) -> bool:
    """The existing explicit derived-Daily eligibility policy."""
    return (row.get("source") == "derived_daily_price_data"
            and row.get("is_official", False) is False
            and row.get("source_origin", row.get("origin", "settrade")) == "settrade"
            and row.get("source_timeframe") == "60m"
            and row.get("source_bar_count") == 8
            and row.get("derivation_method") == DERIVED_METHOD)


def _indicator_observations(rows: Iterable[Mapping[str, Any]], symbols: Iterable[str],
                            dates: list[str]) -> list[dict[str, Any]]:
    """Attach point-in-time Main Trend v6 evidence without lookahead."""
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for raw in rows:
        symbol = str(raw["symbol"]).upper()
        grouped[symbol].append(raw)
    requested_dates = set(dates)
    output: list[dict[str, Any]] = []
    for symbol in sorted({str(item).upper() for item in symbols}):
        frame = sorted(grouped.get(symbol, []),
                       key=lambda item: _as_date(item.get("session_date", item.get("date"))))
        candles = [{key: row.get(key) for key in ("open", "high", "low", "close", "volume")}
                   for row in frame]
        indicators = build_technical_indicators(candles, "1D") if candles else None
        full_series = indicators.get("series", {}) if indicators is not None else {}
        ma_series = full_series.get("ma", {}) if isinstance(full_series, Mapping) else {}
        for index, row in enumerate(frame):
            session_date = _as_date(row.get("session_date", row.get("date")))
            if session_date not in requested_dates:
                continue
            enriched = dict(row)
            # The classifier only needs the current MA values and the point
            # exactly 20 completed bars earlier. Keep a 21-value window so
            # its existing no-lookahead slope implementation is unchanged.
            window_start = max(0, index - 20)
            window_ma = {
                str(period): list(values[window_start:index + 1])
                for period in (5, 10, 20, 50, 100, 200)
                for values in [ma_series.get(str(period), ma_series.get(period, []))]
                if isinstance(values, (list, tuple))
            }
            latest_ma = {period: values[-1] if values else None
                         for period, values in window_ma.items()}
            prefix = {"timeframe": "1D", "as_of": session_date,
                      "latest": {"close": row.get("close")},
                      "series": {"ma": window_ma}}
            prefix["latest"]["ma"] = latest_ma
            evidence = classify_main_trend(prefix)
            enriched["session_date"] = session_date
            enriched["main_trend_evidence"] = {
                key: evidence.get(key)
                for key in ("main_trend", "main_trend_display", "evidence_quality",
                            "used_periods", "slope_window", "as_of", "source_timeframe",
                            "policy_version", "reason", "missing_periods",
                            "missing_slope_periods", "ambiguity_reasons", "actionability")
            }
            ma = evidence.get("moving_averages", {})
            for period in (50, 200):
                enriched[f"ma{period}"] = ma.get(str(period))
                close = _number(row.get("close")); average = _number(ma.get(str(period)))
                enriched[f"above_ma{period}"] = (close > average) if close is not None and average is not None else None
            output.append(enriched)
        # ``candles`` and the full technical series are symbol-local scratch
        # data; no reference to either is retained in an observation.
        del indicators, candles, full_series, ma_series
    return output


class PostgresMarketBreadthSource:
    """Production source.  Every query is SELECT-only and the connection is read-only."""

    def __init__(self, conn):
        self.conn = conn
        try:
            conn.set_session(readonly=True, autocommit=True)
        except Exception:
            pass

    def _select(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple]:
        statement = sql.lstrip().upper()
        if not (statement.startswith("SELECT") or statement.startswith("WITH")) or ";" in sql.rstrip():
            raise RuntimeError("market breadth source only permits SELECT/WITH")
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            cur.close()

    def resolve_universe(self) -> dict[str, Any]:
        symbols = sorted({str(symbol).upper() for symbol in active_ord_symbols(self.conn)})
        return {"name": "active_ord", "symbols": symbols, "count": len(symbols),
                "symbol_hash": _hash(symbols), "source": "symbol_master"}

    def completed_sessions(self, *, until: str | None = None, as_of: str | None = None,
                           limit: int = CONTEXT_SESSIONS) -> list[str]:
        cutoff = as_of or until
        params: tuple[Any, ...] = (cutoff,) if cutoff else ()
        where = " AND date <= %s" if cutoff else ""
        derived_where = " AND session_date <= %s" if cutoff else ""
        rows = self._select(f"""
            SELECT day FROM (
              SELECT DISTINCT date AS day FROM price_data
              WHERE market='TH' {where}
              UNION
              SELECT DISTINCT session_date AS day FROM derived_daily_price_data
              WHERE is_official=FALSE AND source='settrade'
                AND source_timeframe='60m' AND source_bar_count=8
                AND derivation_method=%s
                AND source_completion_cutoff >= ((session_date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')
                AND source_completion_cutoff <= NOW() {derived_where}
            ) dates ORDER BY day DESC LIMIT %s
        """, ((cutoff,) if cutoff else ()) + (DERIVED_METHOD,) + ((cutoff,) if cutoff else ()) + (limit,))
        return sorted(_as_date(row[0]) for row in rows)

    def load_daily(self, symbols: list[str], *, since: str, until: str) -> list[dict[str, Any]]:
        rows = self._select("""
            WITH official AS (
              SELECT symbol, date AS session_date, open, high, low, close, volume,
                     'price_data' AS source, NULL::text AS source_timeframe,
                     NULL::text AS derivation_method, NULL::text AS source_run_id,
                     NULL::timestamptz AS source_first_ts, NULL::timestamptz AS source_last_ts,
                     NULL::timestamptz AS source_completion_cutoff, NULL::integer AS source_bar_count
              FROM price_data WHERE market='TH' AND symbol=ANY(%s) AND date BETWEEN %s AND %s
            ), derived AS (
              SELECT symbol, session_date, open, high, low, close, volume,
                     'derived_daily_price_data' AS source, source_timeframe,
                     derivation_method, source_run_id, source_first_ts, source_last_ts,
                     source_completion_cutoff, source_bar_count
              FROM derived_daily_price_data
              WHERE symbol=ANY(%s) AND session_date BETWEEN %s AND %s
                AND is_official=FALSE AND source='settrade' AND source_timeframe='60m'
                AND source_bar_count=8 AND derivation_method=%s
                AND source_completion_cutoff >= ((session_date + TIME '17:00') AT TIME ZONE 'Asia/Bangkok')
                AND source_completion_cutoff <= NOW()
                AND NOT EXISTS (SELECT 1 FROM official o WHERE o.symbol=derived_daily_price_data.symbol AND o.session_date=derived_daily_price_data.session_date)
            ) SELECT * FROM official UNION ALL SELECT * FROM derived
              ORDER BY symbol, session_date
        """, (symbols, since, until, symbols, since, until, DERIVED_METHOD))
        keys = ("symbol", "session_date", "open", "high", "low", "close", "volume", "source",
                "source_timeframe", "derivation_method", "source_run_id", "source_first_ts",
                "source_last_ts", "source_completion_cutoff", "source_bar_count")
        return [dict(zip(keys, row)) for row in rows]

    def benchmark(self, *, as_of: str) -> dict[str, Any]:
        rows = self._select("""SELECT date, close FROM price_data
                              WHERE symbol='SET' AND market='TH' AND date <= %s
                              ORDER BY date DESC LIMIT 21""", (as_of,))
        if not rows:
            return {"symbol": "SET", "source": "price_data", "timeframe": "1D",
                    "close": None, "change_1d_pct": None, "change_20d_pct": None,
                    "as_of": None, "quality": {"status": "DATA_BLOCKED", "reason": "benchmark_missing"}}
        close = _number(rows[0][1]); prior1 = _number(rows[1][1]) if len(rows) > 1 else None
        prior20 = _number(rows[20][1]) if len(rows) > 20 else None
        pct = lambda prior: round((close - prior) / prior * 100, 4) if close is not None and prior not in (None, 0) else None
        quality = "AVAILABLE" if close is not None else "DATA_BLOCKED"
        return {"symbol": "SET", "source": "price_data", "timeframe": "1D", "close": close,
                "change_1d_pct": pct(prior1), "change_20d_pct": pct(prior20),
                "as_of": _as_date(rows[0][0]), "quality": {"status": quality, "reason": "valid_inputs_available" if quality == "AVAILABLE" else "benchmark_close_invalid"}}


def publish_market_breadth_replay(*, source: Any, root: str | Path, conn: Any = None,
                                  since: str | None = None, until: str | None = None,
                                  as_of: str | None = None, run_id: str | None = None) -> dict[str, Any]:
    """Build and publish one bounded replay; no request-time DB work is involved."""
    if source is None:
        if conn is None:
            raise ValueError("read-only source or connection is required")
        source = PostgresMarketBreadthSource(conn)
    universe = source.resolve_universe()
    symbols = list(universe["symbols"])
    context_dates = list(source.completed_sessions(until=until, as_of=as_of, limit=CONTEXT_SESSIONS))
    if since is not None:
        context_dates = [session for session in context_dates if session >= _as_date(since)]
    if len(context_dates) < EMITTED_SESSIONS:
        raise RuntimeError("fewer than 260 completed market sessions")
    context_dates = sorted(context_dates)[-CONTEXT_SESSIONS:]
    # An explicit cutoff is a bound, not permission to invent a session.  The
    # artifact always names the latest completed session actually resolved.
    resolved_as_of = context_dates[-1]
    report_dates = context_dates[-EMITTED_SESSIONS:]
    rows = source.load_daily(symbols, since=since or context_dates[0], until=resolved_as_of)
    official = (row for row in rows if row.get("source") == "price_data")
    derived = (row for row in rows if _valid_derived(row))
    selected = select_official_first_daily(official, derived, universe=symbols, as_of=resolved_as_of)
    observations = _indicator_observations(selected, symbols, context_dates)
    build = build_market_breadth(observations, universe_snapshot={**universe, "count": len(symbols), "completed_session_dates": context_dates},
                                  completed_session_dates=context_dates, report_session_dates=report_dates)
    current_rows = [row for row in selected if _as_date(row.get("session_date")) == resolved_as_of]
    observed = {str(row["symbol"]).upper() for row in current_rows}
    # Coverage is point-in-time: only selected rows at the resolved as-of are
    # observed. Do not fill a missing current row from the historical union.
    current_declared_count = len(symbols)
    current_observed_count = len(observed)
    current_blocked_count = max(current_declared_count - current_observed_count, 0)
    build["universe"].update({
        "current_declared_count": current_declared_count,
        "current_observed_count": current_observed_count,
        "current_blocked_count": current_blocked_count,
    })
    invalid = sum(any(_number(row.get(key)) is None for key in ("open", "high", "low", "close", "volume")) for row in current_rows)
    lineage = {
        "selected_rows": len(selected),
        "sources": sorted({str(row.get("source")) for row in selected}),
        "source_run_ids": sorted({str(row["source_run_id"]) for row in selected if row.get("source_run_id")}),
        "completion_cutoffs": sorted({str(row["source_completion_cutoff"]) for row in selected if row.get("source_completion_cutoff")}),
    }
    metadata = {
        "counts": {"official": sum(row.get("source") == "price_data" for row in current_rows),
                    "derived": sum(row.get("source") == "derived_daily_price_data" for row in current_rows),
                    "blocked": max(len(symbols) - len(observed), 0), "invalid": invalid},
        "source": "market-breadth-mb4a-read-only-replay", "run_id": run_id or _hash({"as_of": resolved_as_of, "universe": universe["symbol_hash"]})[:16],
        "source_identity": {"tables": ["symbol_master", "price_data", "derived_daily_price_data"], "universe_hash": universe["symbol_hash"], "as_of": resolved_as_of},
        "run_identity": {"as_of": resolved_as_of, "context_sessions": len(context_dates), "report_sessions": len(report_dates)},
        "provenance": {"source": "price_data+derived_daily_price_data", "timeframe": "1D", "query_mode": "SELECT_ONLY", "fallback_policy": "official_price_data_first_then_derived_60m", "main_trend_policy": MAIN_TREND_POLICY_VERSION, "context_sessions": CONTEXT_SESSIONS, "report_sessions": EMITTED_SESSIONS, "lineage": lineage},
        "freshness": {"status": "AVAILABLE", "as_of": resolved_as_of, "reason": "completed_market_session"},
        "benchmark": source.benchmark(as_of=resolved_as_of),
    }
    result = publish_market_breadth_artifact(build, root=root, metadata=metadata)
    return {**result, "as_of": resolved_as_of, "context_sessions": len(context_dates), "report_sessions": len(report_dates),
            "active_count": len(symbols), "observed_count": len(observed), "blocked_count": metadata["counts"]["blocked"],
            "source_rows": len(rows), "quality": build["quality"], "read_only": True}


def publish_market_breadth_from_postgres(*, root: str | Path, conn: Any = None, **controls: Any) -> dict[str, Any]:
    """Explicit production convenience seam; the caller owns/ closes ``conn``."""
    return publish_market_breadth_replay(source=None, root=root, conn=conn, **controls)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish read-only Market Breadth v2")
    parser.add_argument("--read-only", action="store_true", required=True,
                        help="required safety acknowledgement; this command never writes Postgres")
    parser.add_argument("--root", required=True, help="artifact root")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--as-of")
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    if not args.read_only:
        parser.error("--read-only is required")
    import psycopg2
    from mvp_routes import _setup_candidates_pg_dsn
    conn = psycopg2.connect(**_setup_candidates_pg_dsn())
    try:
        result = publish_market_breadth_from_postgres(
            root=args.root, conn=conn, since=args.since, until=args.until,
            as_of=args.as_of, run_id=args.run_id)
        print(json.dumps(result, sort_keys=True, default=str))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a bounded CLI
    raise SystemExit(main())
