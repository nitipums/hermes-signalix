"""MVP Chart Data Adapter — deterministic read-only chart data seam.

Converts dashboard_snapshot.json serialized cards into chart overlay data:

  GET /api/chart/{symbol} → {symbol, candles, ma20, ma50, ma200, macd, rsi,
                               trigger, stop, target, provenance}

Uses existing snapshot fields only. Never queries DB, never rescans,
never fabricates indicators.

All fields are null when no authoritative data exists in the snapshot.
"""

from __future__ import annotations

from typing import Any


def _number(value, default=None):
    """Safe float coercion; returns default on None/non-numeric."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_trigger(item: dict) -> str | None:
    """Trigger label from snapshot evidence only."""
    t = item.get("trigger")
    if t and str(t).strip():
        return str(t).strip()
    bev = item.get("breakoutEvidence") or {}
    if bev.get("trigger"):
        return f"Break above {bev['trigger']}"
    return None


def _resolve_stop(item: dict) -> float | None:
    """Stop/invalidation level from snapshot."""
    return _number(item.get("stop") or item.get("riskStop") or item.get("invalidation"))


def _resolve_target(item: dict) -> float | None:
    """Price target from fib extensions or explicit target."""
    return (
        _number(item.get("target"))
        or _number(item.get("t161"))
        or _number(item.get("t127"))
    )


def _find_item_by_symbol(items: list[dict], symbol: str) -> dict | None:
    """Case-insensitive symbol lookup."""
    upper = symbol.upper().strip()
    for item in items:
        if str(item.get("symbol", "")).upper() == upper:
            return item
    return None


def project_chart_response(items: list[dict], symbol: str) -> dict | None:
    """Build the GET /api/chart/{symbol} drawer chart data response.

    Returns chart overlay data from snapshot fields.  All indicator values
    are sourced from the serialized card — no time-series calculations,
    no DB queries, no fabrication.

    Fields:
        symbol      — the symbol (string)
        candles     — OHLCV time series; null when unavailable (NOT_VERIFIED)
        ma20        — 20-period simple moving average (float or null)
        ma50        — 50-period simple moving average (float or null)
        ma200       — 200-period simple moving average (float or null)
        macd        — MACD line value (float or null)
        rsi         — 14-period RSI (float or null)
        trigger     — trigger price label (string or null)
        stop        — stop/invalidation level (float or null)
        target      — price target (float or null)
        close       — latest close price (float or null)
        provenance  — {source, as_of, note}
    """
    item = _find_item_by_symbol(items, symbol)
    if item is None:
        return None

    as_of = (
        (item.get("daily_eod_freshness") or {}).get("as_of")
        or item.get("date")
    )

    return {
        "symbol": item.get("symbol"),
        # NOT_VERIFIED: No OHLCV time series in dashboard_snapshot.json.
        # The snapshot stores point-in-time card data, not historical bars.
        # candle data would require a DB query to price_data — outside
        # the scope of read-only snapshot adapters.
        "candles": None,
        "ma20": _number(item.get("ma20Value")),
        "ma50": _number(item.get("ma50Value")),
        "ma200": _number(item.get("ma200Value")),
        "macd": _number(item.get("macd")),
        "rsi": _number(item.get("rsi")),
        "trigger": _resolve_trigger(item),
        "stop": _resolve_stop(item),
        "target": _resolve_target(item),
        "close": _number(item.get("close")),
        "provenance": {
            "source": "dashboard_snapshot",
            "as_of": as_of,
            "note": (
                "Point-in-time snapshot. "
                "MA/MACD/RSI are last computed values from the scan pipeline. "
                "No OHLCV time series (candles) available in snapshot — "
                "NOT_VERIFIED."
            ),
        },
    }