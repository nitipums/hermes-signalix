"""Market-wide, point-in-time Trend Route replay seams."""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping

from main_trend_mapping import classify_main_trend
from trend_route import MAX_SESSIONS, build_route, normalize_snapshot


def _date(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _observed_sessions(history_by_symbol: Mapping[str, Any], cutoff: dt.date) -> list[dt.date]:
    dates = set()
    for snapshots in (history_by_symbol or {}).values():
        for raw in snapshots or []:
            normalized = normalize_snapshot(raw) if isinstance(raw, Mapping) else None
            if normalized and _date(normalized["date"]) <= cutoff:
                dates.add(_date(normalized["date"]))
    return sorted(date for date in dates if date is not None)


def replay_symbol(symbol: str, snapshots: Any, cutoff: Any, *, max_sessions: int = MAX_SESSIONS,
                  expected_sessions: list[dt.date] | None = None) -> dict[str, Any]:
    """Replay one symbol using a cutoff shared by the caller's market run."""
    cutoff_date = _date(cutoff)
    if cutoff_date is None:
        return {"symbol": symbol, "status": "NOT_VERIFIED", "reason_codes": ["INVALID_CUTOFF"],
                "coverage": {"no_lookahead": True}, "route": build_route([], symbol=symbol)}
    bounded = []
    future = 0
    for raw in (snapshots or []):
        normalized = normalize_snapshot(raw, symbol=symbol) if isinstance(raw, Mapping) else None
        if normalized is None:
            continue
        if _date(normalized["date"]) <= cutoff_date:
            bounded.append(normalized)
        else:
            future += 1
    route = build_route(bounded, symbol=symbol, cutoff=cutoff_date, max_sessions=max_sessions,
                        expected_sessions=expected_sessions)
    route["coverage"]["future_rows_excluded"] = future
    route["coverage"]["cutoff"] = cutoff_date.isoformat()
    if future and route["status"] == "FULL":
        route["status"] = "PARTIAL"
        route["reason_codes"] = ["FUTURE_ROWS_EXCLUDED"]
    return route


def replay_market(history_by_symbol: Mapping[str, Any], cutoff: Any, *, max_sessions: int = MAX_SESSIONS,
                  expected_sessions: list[Any] | None = None) -> dict[str, Any]:
    """Replay every symbol at one cutoff; no symbol receives a later cutoff."""
    cutoff_date = _date(cutoff)
    if cutoff_date is None:
        return {"status": "NOT_VERIFIED", "reason_codes": ["INVALID_CUTOFF"], "cutoff": cutoff,
                "symbols": {}, "coverage": {"no_lookahead": True}}
    expected = sorted({_date(value) for value in (expected_sessions or _observed_sessions(history_by_symbol, cutoff_date)) if _date(value) is not None})
    symbols = {}
    for symbol in sorted(history_by_symbol or {}):
        symbols[str(symbol)] = replay_symbol(str(symbol), history_by_symbol[symbol], cutoff_date,
                                             max_sessions=max_sessions, expected_sessions=expected)
    statuses = {value["status"] for value in symbols.values()}
    status = "FULL" if symbols and statuses == {"FULL"} else "PARTIAL" if symbols else "NOT_VERIFIED"
    return {"status": status, "cutoff": cutoff_date.isoformat(), "max_sessions": max_sessions,
            "symbols": symbols, "coverage": {"symbols": len(symbols), "expected_sessions": len(expected), "no_lookahead": True,
                                               "cutoff": cutoff_date.isoformat(), "reason_codes": [] if status == "FULL" else ["SYMBOL_PARTIAL"]}}


def classify_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Use the canonical classifier when a replay fixture supplies indicators."""
    indicators = snapshot.get("indicators")
    if indicators is None:
        return {"main_trend": snapshot.get("main_trend"), "source": "canonical_snapshot"}
    return classify_main_trend(indicators)


replay = replay_market
replay_market_cutoff = replay_market
