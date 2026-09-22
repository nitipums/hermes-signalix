"""Bounded adapter for the current Trend Map drawer chart/detail requests.

This seam deliberately owns only the two read-only request shapes used by the
active drawer.  The older chart and setup projections remain in mvp_routes for
audit compatibility.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping


APPROVED_TIMEFRAMES = frozenset(("1D", "60M", "1W", "1M"))


class InvalidActiveChartRequest(ValueError):
    """The active drawer supplied a timeframe outside its explicit contract."""


_FORBIDDEN_SEMANTIC_TOKENS = frozenset({
    "action", "actionable", "buy", "decision", "elliott", "invalidation",
    "lane", "order", "risk", "rr", "sell", "setup", "signal", "target",
    "trigger", "vcp", "wave",
})
_PRESERVED_BOUNDARY_KEYS = frozenset({"actionability", "research_only", "status"})


def _key_tokens(key: Any) -> set[str]:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key)).lower()
    return {part for part in re.split(r"[^a-z0-9]+", normalized) if part}


def _is_forbidden_semantic_key(key: Any) -> bool:
    if str(key).lower() in _PRESERVED_BOUNDARY_KEYS:
        return False
    return bool(_key_tokens(key) & _FORBIDDEN_SEMANTIC_TOKENS)


def _strip_semantics(value: Any) -> Any:
    """Remove historical setup semantics at every depth of an active payload."""
    if isinstance(value, Mapping):
        return {
            key: _strip_semantics(child)
            for key, child in value.items()
            if not _is_forbidden_semantic_key(key)
        }
    if isinstance(value, list):
        return [_strip_semantics(child) for child in value]
    return value


def _unavailable_chart(symbol: str, timeframe: str, *, note: str) -> dict:
    return {
        "status": "NOT_VERIFIED",
        "availability": "unavailable",
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": [],
        "indicators": None,
        "provenance": {
            "source": None,
            "as_of": None,
            "chart_read_model": "DB_FALLBACK",
            "availability": "NOT_VERIFIED",
            "note": f"NOT_VERIFIED: {note}",
        },
    }


def _timeframe(value: Any) -> str:
    timeframe = str(value or "1D").strip().upper()
    if timeframe not in APPROVED_TIMEFRAMES:
        raise InvalidActiveChartRequest("invalid_timeframe")
    return timeframe


def chart_response(
    symbol: str,
    timeframe: Any,
    *,
    read_prebuilt: Callable[..., Mapping[str, Any] | None],
    load_canonical_item: Callable[[str], dict | None],
    project_db: Callable[..., dict | None],
    compact: Callable[[dict | None], dict | None],
) -> tuple[int, dict]:
    """Read one active drawer chart, preferring the validated artifact."""
    normalized_symbol = str(symbol).strip().upper()
    normalized_timeframe = _timeframe(timeframe)
    try:
        prebuilt = read_prebuilt(normalized_symbol, timeframe=normalized_timeframe)
    except Exception:
        prebuilt = None
    if _usable_prebuilt(prebuilt, normalized_symbol, normalized_timeframe):
        result = _strip_semantics(prebuilt)
        provenance = dict(result.get("provenance") or {})
        provenance["chart_read_model"] = "PREBUILT"
        result["provenance"] = provenance
        return 200, result

    canonical_item = None
    try:
        canonical_item = load_canonical_item(normalized_symbol)
        result = project_db(normalized_symbol, timeframe=normalized_timeframe,
                            canonical_item=canonical_item)
    except ValueError:
        return 400, {"error": "invalid_request"}
    except Exception:
        result = _unavailable_chart(normalized_symbol, normalized_timeframe,
                                    note="chart data unavailable")
    if result is None:
        if canonical_item is None:
            return 404, {"error": "symbol not found", "symbol": normalized_symbol}
        result = _unavailable_chart(normalized_symbol, normalized_timeframe,
                                    note="chart data unavailable")
    result = compact(result)
    if not isinstance(result, Mapping) or not result.get("candles"):
        result = _unavailable_chart(normalized_symbol, normalized_timeframe,
                                    note="no usable candles")
    result = _strip_semantics(result)
    provenance = dict(result.get("provenance") or {})
    provenance["chart_read_model"] = "DB_FALLBACK"
    result["provenance"] = provenance
    return 200, result


def _usable_prebuilt(payload: Any, symbol: str, timeframe: str) -> bool:
    return (
        isinstance(payload, Mapping)
        and str(payload.get("symbol", "")).upper() == symbol
        and payload.get("timeframe") == timeframe
        and isinstance(payload.get("candles"), list)
        and bool(payload.get("candles"))
    )


def symbol_detail_response(
    symbol: str,
    *,
    load_model: Callable[[], dict],
    validate_model: Callable[[dict], dict],
    snapshot_meta: Callable[[dict], dict],
    overlay_intraday: Callable[[dict], dict],
) -> tuple[int, dict]:
    """Project only current identity, market facts, and provenance."""
    normalized_symbol = str(symbol).strip()
    if not normalized_symbol:
        return 400, {"error": "symbol required"}
    try:
        model = validate_model(load_model())
        payload = overlay_intraday(snapshot_meta(model))
        item = next((candidate for candidate in model["items"]
                     if str(candidate.get("symbol", "")).upper()
                     == normalized_symbol.upper()), None)
    except Exception:
        return 503, {"error": "setup_candidates_unavailable"}
    if item is None:
        return 404, {"error": "symbol not found", "symbol": normalized_symbol}
    allowed = {
        "symbol", "name", "company_name", "companyName", "sector", "industry",
        "description", "businessSummary", "market_cap", "marketCap", "close",
        "change_pct", "changePct", "changeAmount", "change_amount", "tradeValue",
        "turnover", "volume", "high52", "low52", "athHigh", "ath_low", "athLow",
        "index_membership", "margin_pct", "marginPct", "margin_rate_pct",
        "margin_marker", "margin_can_buy", "margin_can_add_collateral",
        "margin_can_short", "marginable", "daily_metrics", "quote", "provenance",
        "as_of", "date", "dataFreshness", "daily_eod_freshness",
        "intraday_freshness", "freshness", "latest_completed_60m",
    }
    result = {key: _strip_semantics(value) for key, value in item.items()
              if key in allowed and not _is_forbidden_semantic_key(key)}
    if "provenance" not in result:
        result["provenance"] = {}
    result["provenance"] = _strip_semantics(result["provenance"])
    return 200, result


def is_active_route(route: str, query: Mapping[str, list[str]]) -> bool:
    """Return whether a path is one of the current drawer requests."""
    if route.startswith("/api/symbol/"):
        return (query.get("view", [""])[0] or "").lower() == "detail"
    return route.startswith("/api/chart-db/") and (
        (query.get("view", [""])[0] or "").lower() == "chart"
    )
