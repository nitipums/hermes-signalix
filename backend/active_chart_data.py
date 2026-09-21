"""Neutral SELECT-only chart fallback for the active Trend Map drawer.

This module owns only OHLCV retrieval, deterministic technical indicators,
and the compact chart projection used when a validated chart artifact cannot
be read.  Historical setup, Wave, VCP, signal, and MVP adapters do not belong
on this import path.
"""
from __future__ import annotations

import os
from threading import Lock
from typing import Any, Mapping

from canonical_chart_read import DEFAULT_CHART_CANDLE_LIMIT, read_chart_result
from technical_indicators import MA_PERIODS, build_technical_indicators


APPROVED_TIMEFRAMES = frozenset(("1D", "60M", "1W", "1M"))
_CHART_VIEW_CANDLE_LIMIT = 120
_POOL = None
_POOL_LOCK = Lock()


def _get_db_pool():
    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                from psycopg2.pool import ThreadedConnectionPool

                host = os.getenv("POSTGRES_HOST")
                if not host:
                    return None
                _POOL = ThreadedConnectionPool(
                    1,
                    4,
                    host=host,
                    port=int(os.getenv("POSTGRES_PORT", "5432")),
                    user=os.getenv("POSTGRES_USER", "signalix"),
                    password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
                    dbname=os.getenv("POSTGRES_DB", "signalix"),
                )
    return _POOL


def _get_db_connection():
    pool = _get_db_pool()
    return pool.getconn() if pool is not None else None


def _release_db_connection(connection: Any, *, close: bool = False) -> None:
    pool = _POOL
    if pool is None or connection is None:
        return
    pool.putconn(connection, close=close)


def _source_for(timeframe: str) -> str:
    return "intraday_price_data" if timeframe == "60M" else "price_data"


def _unavailable_projection(
    symbol: str,
    timeframe: str,
    *,
    source: str | None,
    note: str,
    candles: list[dict] | None = None,
) -> dict:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": candles,
        "indicators": build_technical_indicators([], timeframe),
        "source": source,
        "as_of": None,
        "latest_time": None,
        "availability": "unavailable",
        "provenance": {"source": source, "as_of": None, "note": note},
    }


def compact_active_chart_data(
    payload: Mapping[str, Any] | None,
    *,
    limit: int = _CHART_VIEW_CANDLE_LIMIT,
) -> dict | None:
    """Return only the bounded series consumed by the active chart renderer."""
    if payload is None:
        return None
    compact = dict(payload)
    candles = compact.get("candles")
    if isinstance(candles, list):
        start = max(0, len(candles) - limit)
        compact["candles"] = [
            dict(candle) if isinstance(candle, Mapping) else candle
            for candle in candles[start:]
        ]
    else:
        start = 0

    indicators = compact.get("indicators")
    if isinstance(indicators, Mapping):
        indicators = dict(indicators)
        compact["indicators"] = indicators
    series = indicators.get("series") if isinstance(indicators, Mapping) else None
    if isinstance(series, Mapping):
        compact_series = {}
        ma = series.get("ma")
        if isinstance(ma, Mapping):
            compact_series["ma"] = {
                period: values[start:]
                for period, values in ma.items()
                if isinstance(values, list)
            }
        macd = series.get("macd")
        if isinstance(macd, Mapping):
            compact_series["macd"] = {
                name: values[start:]
                for name in ("line", "signal", "histogram")
                if isinstance((values := macd.get(name)), list)
            }
        rsi = series.get("rsi")
        if isinstance(rsi, list):
            compact_series["rsi"] = rsi[start:]
        indicators["series"] = compact_series

    provenance = dict(compact.get("provenance") or {})
    provenance["representation"] = "chart_view"
    provenance["representation_authoritative"] = False
    compact["provenance"] = provenance
    return compact


def project_active_chart_data(
    symbol: str,
    timeframe: str = "1D",
    *,
    connection: Any | None = None,
) -> dict | None:
    """Build one neutral OHLCV/indicator fallback using SELECT-only reads."""
    normalized_symbol = str(symbol).strip().upper()
    normalized_timeframe = str(timeframe or "1D").strip().upper()
    if normalized_timeframe not in APPROVED_TIMEFRAMES:
        raise ValueError("timeframe must be 1D, 1W, 60M, or 1M")

    source = _source_for(normalized_timeframe)
    owns_connection = connection is None
    database = connection if connection is not None else _get_db_connection()
    if database is None:
        return _unavailable_projection(
            normalized_symbol,
            normalized_timeframe,
            source=None,
            note="NOT_VERIFIED: Database not configured (POSTGRES_HOST not set).",
        )

    try:
        cursor = database.cursor()
        chart = read_chart_result(
            cursor,
            normalized_symbol,
            normalized_timeframe,
            DEFAULT_CHART_CANDLE_LIMIT,
        )
        cursor.close()
    except Exception as error:
        try:
            database.rollback()
        except Exception:
            pass
        return _unavailable_projection(
            normalized_symbol,
            normalized_timeframe,
            source=source,
            note=f"NOT_VERIFIED: DB query failed — {str(error)[:200]}",
        )
    finally:
        if owns_connection:
            try:
                _release_db_connection(database)
            except Exception:
                pass

    candles = chart.candles
    if not candles:
        if normalized_timeframe == "60M":
            return _unavailable_projection(
                normalized_symbol,
                normalized_timeframe,
                source=None,
                candles=[],
                note="60m unavailable · Daily EOD remains the decision source.",
            )
        return None

    indicators = build_technical_indicators(candles, normalized_timeframe)
    closes = [candle["close"] for candle in candles if candle.get("close") is not None]
    input_available = indicators["availability"]["input"]["status"] == "AVAILABLE"
    notes = []
    if not input_available:
        notes.append("Indicators NOT_VERIFIED: missing or non-finite High/Low/Close input")
    for period in MA_PERIODS:
        if len(closes) < period:
            notes.append(f"MA{period} NOT_VERIFIED: insufficient data (< {period} candles)")
    unavailable_windows = [
        period
        for period, summary in indicators["latest"]["window_summary"].items()
        if summary["availability"]["status"] != "AVAILABLE"
    ]
    if unavailable_windows:
        notes.append("OHLCV windows NOT_VERIFIED: " + ",".join(unavailable_windows))
    if len(closes) < 34:
        notes.append("MACD signal NOT_VERIFIED: insufficient data (< 34 candles)")
    if len(closes) < 15:
        notes.append("RSI NOT_VERIFIED: insufficient data (< 15 candles)")
    if len(closes) < 14:
        notes.append("ATR NOT_VERIFIED: insufficient data (< 14 candles)")

    source = chart.source or source
    provisional_note = (
        "Current session is represented by provisional 60m aggregation; "
        "Daily EOD decision data is unchanged. "
        if chart.provisional
        else ""
    )
    note = provisional_note + (
        ", ".join(notes)
        if notes
        else f"Computed from {source} (SELECT only). All indicators available."
    )
    return {
        "symbol": normalized_symbol,
        "timeframe": normalized_timeframe,
        "candles": candles,
        "indicators": indicators,
        "source": source,
        "as_of": chart.as_of,
        "latest_time": chart.latest_time,
        "provenance": {
            "source": source,
            "as_of": chart.as_of,
            "indicator_policy_version": indicators["policy_version"],
            "note": note,
        },
    }
