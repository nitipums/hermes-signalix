"""HTTP route seam for the chart request made by the active Trend Map drawer.

This module intentionally exposes no setup, MVP, VCP, signal, or symbol-detail
dispatcher.  Historical chart enrichment remains behind its historical caller.
"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from active_chart_adapter import InvalidActiveChartRequest, chart_response


def _load_active_trend_item(symbol: str) -> dict | None:
    """Resolve symbol membership from the active Trend Map artifact only."""
    try:
        from trend_map_read_model_publisher import read_current_trend_map_report
        report = read_current_trend_map_report()
        return next(
            (row for row in report.get("rows", [])
             if str(row.get("symbol", "")).upper() == str(symbol).upper()),
            None,
        )
    except Exception:
        return None


def _send_json(handler, payload: dict, *, status: int) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    if hasattr(handler, "send_bytes"):
        handler.send_bytes(
            body, content_type="application/json; charset=utf-8", status=status
        )
        return
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def handle_active_chart_api(path: str, handler) -> bool:
    """Handle only ``/api/chart-db/{symbol}?view=chart``."""
    parsed = urlsplit(path)
    route = parsed.path
    prefix = "/api/chart-db/"
    if not route.startswith(prefix):
        return False
    query = parse_qs(parsed.query or "")
    if (query.get("view", [""])[0] or "").lower() != "chart":
        return False
    symbol = route[len(prefix):].strip().rstrip("/")
    if not symbol:
        _send_json(handler, {"error": "symbol required"}, status=400)
        return True
    try:
        from chart_read_model import read_current
        from mvp_chart_db import compact_chart_db_response, project_chart_db_response

        status, payload = chart_response(
            symbol,
            query.get("timeframe", ["1D"])[0],
            read_prebuilt=read_current,
            load_canonical_item=_load_active_trend_item,
            project_db=lambda requested_symbol, **kwargs: project_chart_db_response(
                requested_symbol, include_historical_evidence=False, **kwargs
            ),
            compact=compact_chart_db_response,
        )
    except InvalidActiveChartRequest:
        status, payload = 400, {
            "error": "invalid_request", "reason": "invalid_timeframe"
        }
    _send_json(handler, payload, status=status)
    return True
