"""MVP Chart DB Adapter — read-only PostgreSQL price_data query layer.

Fills the chart overlay contract with real DB candles and computed
indicators (MA20/50/200, MACD, RSI) when the database is available.
Never writes, never mutates.

  GET /api/chart-db/{symbol} → {symbol, candles, ma20, ma50, ma200,
                                 macd, rsi, source, as_of, latest_time, provenance}

All fields are null (None) when no authoritative data exists.
NOT_VERIFIED when computed values are unavailable due to insufficient data.

Uses PostgreSQL env vars:
  POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB

Separate from mvp_chart.py (snapshot-only adapter) — this is the DB-backed
adapter that fills the candles gap without modifying the existing contract.
"""

from __future__ import annotations

import os
import datetime as dt
from typing import Any, Optional
from threading import Lock

from canonical_chart_read import ChartReadResult, read_chart_result
from chart_wave_evidence import (build_legacy_chart_wave_evidence,
                                 canonical_chart_wave_evidence)


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
                    1, 4,
                    host=host,
                    port=int(os.getenv("POSTGRES_PORT", "5432")),
                    user=os.getenv("POSTGRES_USER", "signalix"),
                    password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
                    dbname=os.getenv("POSTGRES_DB", "signalix"),
                )
    return _POOL


def _get_db_connection() -> Optional[Any]:
    """Borrow a connection from a small process-local pool."""
    pool = _get_db_pool()
    return pool.getconn() if pool is not None else None


def _release_db_connection(pg: Any, *, close: bool = False) -> None:
    pool = _POOL
    if pool is None or pg is None:
        return
    if close:
        pool.putconn(pg, close=True)
    else:
        pool.putconn(pg)


# ── Queries (SELECT only, never write) ─────────────────────────────────

def _fetch_candles(cur: Any, symbol: str, market: str = "TH", limit: int = 250,
                   timeframe: str = "1D") -> list[dict]:
    """Fetch/aggregate OHLCV candles for the explicit MVP timeframe."""
    return read_chart_result(cur, symbol, timeframe, limit, market=market).candles


def _fetch_candles_with_metadata(cur: Any, symbol: str, market: str = "TH", limit: int = 250,
                                 timeframe: str = "1D") -> tuple[list[dict], dict]:
    """Fetch candles and preserve the latest stored intraday source timestamp."""
    result: ChartReadResult = read_chart_result(cur, symbol, timeframe, limit, market=market)
    return result.candles, {"latest_time": result.latest_time, "as_of": result.as_of,
                            "provisional": result.provisional}


def _chart_timestamp(value: Any, timeframe: str = "1D") -> str | None:
    """Serialize Daily dates and 60m datetimes in the same ISO form as markers."""
    if value is None:
        return None
    raw = value.isoformat() if hasattr(value, "isoformat") else str(value)
    raw = raw.strip()
    if not raw:
        return None
    if str(timeframe).upper() != "60M":
        return raw[:10] if len(raw) >= 10 else raw
    if len(raw) > 10 and raw[10] == " ":
        raw = raw[:10] + "T" + raw[11:]
    return raw



# ── Indicator computations (deterministic, no DB) ──────────────────────

def _compute_sma(values: list[float], period: int) -> list[Optional[float]]:
    """Simple Moving Average. Returns None-padded list same length as input."""
    n = len(values)
    result: list[Optional[float]] = [None] * n
    if n < period:
        return result
    window_sum = sum(values[:period])
    result[period - 1] = round(window_sum / period, 4)
    for i in range(period, n):
        window_sum += values[i] - values[i - period]
        result[i] = round(window_sum / period, 4)
    return result


def _compute_ema(values: list[float], period: int) -> list[Optional[float]]:
    """Exponential Moving Average. Returns None-padded list same length as input."""
    n = len(values)
    result: list[Optional[float]] = [None] * n
    if n < period:
        return result
    multiplier = 2.0 / (period + 1)
    # Seed EMA with SMA of first 'period' values
    seed = sum(values[:period]) / period
    result[period - 1] = round(seed, 4)
    for i in range(period, n):
        prev = result[i - 1]  # type: ignore[assignment] — always float here
        assert prev is not None, "EMA invariant: prev must be set at index >= period-1"
        result[i] = round(
            (values[i] - prev) * multiplier + prev, 4
        )
    return result


def _compute_macd(closes: list[float]) -> dict:
    """Compute MACD(12,26,9) — returns {macd_line, signal_line, histogram}.

    All arrays are None-padded same length as closes.
    """
    n = len(closes)
    ema12 = _compute_ema(closes, 12)
    ema26 = _compute_ema(closes, 26)

    macd_line: list[Optional[float]] = [None] * n
    signal_line: list[Optional[float]] = [None] * n
    histogram: list[Optional[float]] = [None] * n

    for i in range(25, n):  # ema26 ready at index 25
        e12 = ema12[i]
        e26 = ema26[i]
        if e12 is not None and e26 is not None:
            macd_line[i] = round(e12 - e26, 4)

    # Signal = EMA9 of macd_line (from index 25 onward)
    macd_vals: list[float] = [v for v in macd_line[25:] if v is not None]
    if len(macd_vals) >= 9:
        ema9 = _compute_ema(macd_vals, 9)
        for j, val in enumerate(ema9):
            if val is not None:
                idx = 25 + j
                signal_line[idx] = val
                ml = macd_line[idx]
                if ml is not None:
                    histogram[idx] = round(ml - val, 4)

    return {
        "macd_line": macd_line,
        "signal_line": signal_line,
        "histogram": histogram,
    }


def _compute_rsi(closes: list[float], period: int = 14) -> list[Optional[float]]:
    """Compute RSI using Wilder's smoothing. Returns None-padded list."""
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n < period + 1:
        return result

    # Calculate price changes
    changes: list[float] = [closes[i] - closes[i - 1] for i in range(1, n)]

    # First RSI value: simple average of gains/losses over first 'period' changes
    gain_sum = sum(max(c, 0.0) for c in changes[:period])
    loss_sum = sum(max(-c, 0.0) for c in changes[:period])
    avg_gain = gain_sum / period
    avg_loss = loss_sum / period

    if avg_loss == 0.0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = round(100.0 - (100.0 / (1.0 + rs)), 4)

    # Wilder's smoothing for subsequent values
    for i in range(period + 1, n):
        change = changes[i - 1]  # changes is 0-indexed, offset by 1
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0.0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = round(100.0 - (100.0 / (1.0 + rs)), 4)

    return result


# ── Public API ─────────────────────────────────────────────────────────

def _chart_source(timeframe: str) -> str:
    """Return the authoritative storage relation for a chart timeframe."""
    return "intraday_price_data" if str(timeframe).upper() == "60M" else "price_data"


def project_chart_db_response(symbol: str, timeframe: str = "1D", *, canonical_item: dict | None = None) -> Optional[dict]:
    """Build the GET /api/chart-db/{symbol}?timeframe=... response.

    Supported timeframes: 1D, 1W, 60M, 1M. All queries are SELECT-only.
    """
    timeframe = (timeframe or "1D").upper()
    if timeframe not in {"1D", "1W", "60M", "1M"}:
        raise ValueError("timeframe must be 1D, 1W, 60M, or 1M")
    chart_source = _chart_source(timeframe)
    pg = _get_db_connection()
    if pg is None:
        return {
            "symbol": symbol.upper(),
            "candles": None,
            "ma20": None,
            "ma50": None,
            "ma200": None,
            "macd": None,
            "rsi": None,
            "wave_evidence": {"timeframe": timeframe.lower(), "markers": [],
                              "mapping": {"daily": "not_available", "60m": "not_available"}},
            "source": None,
            "as_of": None,
            "latest_time": None,
            "provenance": {
                "source": None,
                "as_of": None,
                "note": "NOT_VERIFIED: Database not configured (POSTGRES_HOST not set).",
            },
        }

    try:
        cur = pg.cursor()
        candles, chart_metadata = _fetch_candles_with_metadata(cur, symbol, timeframe=timeframe)
        cur.close()
    except Exception as e:
        # Fail-graceful: return NOT_VERIFIED
        # psycopg2 connections are transactional; return a clean connection
        # to the pool so a failed query cannot poison the next chart request.
        try:
            pg.rollback()
        except Exception:
            pass
        return {
            "symbol": symbol.upper(),
            "candles": None,
            "ma20": None,
            "ma50": None,
            "ma200": None,
            "macd": None,
            "rsi": None,
            "wave_evidence": {"timeframe": timeframe.lower(), "markers": [],
                              "mapping": {"daily": "not_available", "60m": "not_available"}},
            "source": None,
            "as_of": None,
            "latest_time": None,
            "provenance": {
                "source": chart_source,
                "as_of": None,
                "note": f"NOT_VERIFIED: DB query failed — {str(e)[:200]}",
            },
        }
    finally:
        try:
            _release_db_connection(pg)
        except Exception:
            pass

    if not candles:
        if timeframe == "60M":
            return {
                "symbol": symbol.upper(),
                "timeframe": timeframe,
                "candles": [],
                "ma20": None,
                "ma50": None,
                "ma200": None,
                "macd": None,
                "rsi": None,
                "wave_evidence": {"timeframe": "60m", "markers": [],
                                  "mapping": {"daily": "not_projected", "60m": "setup_only"},
                                  "missing": ["daily_markers_not_projected"]},
                "source": None,
                "as_of": None,
                "latest_time": None,
                "availability": "unavailable",
                "provenance": {
                    "source": None,
                    "as_of": None,
                    "note": "60m unavailable · Daily EOD remains the decision source.",
                },
            }
        return None  # Daily/aggregated symbol not found

    closes: list[float] = [c["close"] for c in candles if c["close"] is not None]
    as_of: Optional[str] = candles[-1]["date"] if candles else None
    latest_time = (
        chart_metadata.get("latest_time")
        or _chart_timestamp(chart_metadata.get("latest_intraday_time"), "60M")
        or _chart_timestamp(chart_metadata.get("latest_confirmed_time"), "1D")
        or as_of
    )

    # Build NOT_VERIFIED notes
    notes: list[str] = []
    if len(closes) < 20:
        notes.append("MA20 NOT_VERIFIED: insufficient data (< 20 candles)")
    if len(closes) < 50:
        notes.append("MA50 NOT_VERIFIED: insufficient data (< 50 candles)")
    if len(closes) < 200:
        notes.append("MA200 NOT_VERIFIED: insufficient data (< 200 candles)")
    if len(closes) < 35:
        notes.append("MACD NOT_VERIFIED: insufficient data (< 35 candles)")
    if len(closes) < 15:
        notes.append("RSI NOT_VERIFIED: insufficient data (< 15 candles)")

    # Compute indicators if enough data
    ma20 = _compute_sma(closes, 20) if len(closes) >= 20 else ([None] * len(closes))
    ma50 = _compute_sma(closes, 50) if len(closes) >= 50 else ([None] * len(closes))
    ma200 = _compute_sma(closes, 200) if len(closes) >= 200 else ([None] * len(closes))
    macd = _compute_macd(closes) if len(closes) >= 35 else None
    rsi = _compute_rsi(closes, 14) if len(closes) >= 15 else None

    provisional_note = ("Current session is represented by provisional 60m aggregation; "
                        "Daily EOD decision data is unchanged. "
                        if any(c.get("provisional") for c in candles) else "")
    note = (provisional_note + (", ".join(notes) if notes else
            f"Computed from {chart_source} (SELECT only). All indicators available."))

    wave_evidence = (canonical_chart_wave_evidence(canonical_item)
                     if timeframe == "1D" else None)
    if wave_evidence is None:
        wave_evidence = build_legacy_chart_wave_evidence(candles, timeframe, as_of)
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "candles": candles,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "macd": macd,
        "rsi": rsi,
        "wave_evidence": wave_evidence,
        "source": chart_source,
        "as_of": as_of,
        "latest_time": latest_time,
        "provenance": {
            "source": chart_source,
            "as_of": as_of,
            "note": note,
        },
    }
