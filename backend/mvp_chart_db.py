"""MVP Chart DB Adapter — read-only PostgreSQL price_data query layer.

Fills the chart overlay contract with real DB candles and computed
indicators (MA20/50/200, MACD, RSI) when the database is available.
Never writes, never mutates.

  GET /api/chart-db/{symbol} → {symbol, candles, ma20, ma50, ma200,
                                 macd, rsi, source, as_of, provenance}

All fields are null (None) when no authoritative data exists.
NOT_VERIFIED when computed values are unavailable due to insufficient data.

Uses PostgreSQL env vars:
  POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB

Separate from mvp_chart.py (snapshot-only adapter) — this is the DB-backed
adapter that fills the candles gap without modifying the existing contract.
"""

from __future__ import annotations

import os
from typing import Any, Optional
from threading import Lock


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

def _fetch_candles(cur: Any, symbol: str, market: str = "TH", limit: int = 250) -> list[dict]:
    """Fetch daily OHLCV candles from price_data, newest first → reversed.

    Returns list of dicts: {date, open, high, low, close, volume}
    in chronological order (oldest first).
    """
    cur.execute(
        """
        SELECT date, open, high, low, close, volume
        FROM price_data
        WHERE market = %s AND UPPER(symbol) = UPPER(%s) AND instrument_type = 'ORD'
        ORDER BY date DESC
        LIMIT %s
        """,
        (market, symbol, limit),
    )
    rows = cur.fetchall()
    candles: list[dict] = []
    for row in rows:
        candles.append({
            "date": str(row[0]),
            "open": float(row[1]) if row[1] is not None else None,
            "high": float(row[2]) if row[2] is not None else None,
            "low": float(row[3]) if row[3] is not None else None,
            "close": float(row[4]) if row[4] is not None else None,
            "volume": float(row[5]) if row[5] is not None else None,
        })
    # Reverse to chronological order (oldest first)
    candles.reverse()
    return candles


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

def project_chart_db_response(symbol: str) -> Optional[dict]:
    """Build the GET /api/chart-db/{symbol} response from price_data.

    Returns:
        {
          "symbol": str,
          "candles": [...OHLCV dicts] | None,
          "ma20": [float|None, ...] | None,
          "ma50": [float|None, ...] | None,
          "ma200": [float|None, ...] | None,
          "macd": {...} | None,
          "rsi": [float|None, ...] | None,
          "source": "price_data" | None,
          "as_of": "YYYY-MM-DD" | None,
          "provenance": {"source": ..., "as_of": ..., "note": ...}
        }

    Returns None when symbol is not found in price_data.
    Returns partial (NOT_VERIFIED) when DB unavailable or query fails.
    """
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
            "source": None,
            "as_of": None,
            "provenance": {
                "source": None,
                "as_of": None,
                "note": "NOT_VERIFIED: Database not configured (POSTGRES_HOST not set).",
            },
        }

    try:
        cur = pg.cursor()
        candles = _fetch_candles(cur, symbol)
        cur.close()
    except Exception as e:
        # Fail-graceful: return NOT_VERIFIED
        return {
            "symbol": symbol.upper(),
            "candles": None,
            "ma20": None,
            "ma50": None,
            "ma200": None,
            "macd": None,
            "rsi": None,
            "source": None,
            "as_of": None,
            "provenance": {
                "source": "price_data",
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
        return None  # symbol not found

    closes: list[float] = [c["close"] for c in candles if c["close"] is not None]
    as_of: Optional[str] = candles[-1]["date"] if candles else None

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

    note = (", ".join(notes) if notes else
            "Computed from price_data (SELECT only). All indicators available.")

    return {
        "symbol": symbol.upper(),
        "candles": candles,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "macd": macd,
        "rsi": rsi,
        "source": "price_data",
        "as_of": as_of,
        "provenance": {
            "source": "price_data",
            "as_of": as_of,
            "note": note,
        },
    }