"""MVP-only HTTP API dispatch for the Signalix dashboard server.

This module owns only /api/* projection routes. It is read-only: snapshot
projection and chart DB access never run a scan or mutate PostgreSQL.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.parse import parse_qs, urlsplit

from mvp_snapshot import load_mvp_artifact

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_MVP_SNAPSHOT_PATH = os.getenv("MVP_SNAPSHOT_PATH", os.path.join(_BACKEND_DIR, "mvp_snapshot.json"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def load_payload() -> dict:
    """Load the canonical MVP artifact; no legacy fallback is allowed."""
    if not os.path.exists(_MVP_SNAPSHOT_PATH):
        raise FileNotFoundError("mvp_snapshot.json not found")
    return load_mvp_artifact(_MVP_SNAPSHOT_PATH)


def load_snapshot() -> list[dict]:
    """Compatibility helper returning only MVP items."""
    return load_payload()["items"]


def json_response(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(body)


def _not_found(handler, symbol):
    json_response(handler, {"error": "symbol not found", "symbol": symbol}, status=404)


def handle_mvp_api(path, handler) -> bool:
    """Handle MVP /api routes. Return False only for unknown API paths."""
    parsed = urlsplit(path)
    route = parsed.path
    qs = parse_qs(parsed.query or "")
    try:
        payload = load_payload()
        items = payload["items"]
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        json_response(handler, {"error": "snapshot unavailable", "detail": str(exc)[:200]}, status=503)
        return True
    try:
        import mvp_api
    except ImportError as exc:
        json_response(handler, {"error": "mvp_api module unavailable", "detail": str(exc)[:200]}, status=503)
        return True

    if route in ("/api/daily-shortlist", "/api/daily-shortlist/"):
        json_response(handler, mvp_api.project_shortlist_response(items, snapshot_meta=payload)); return True
    if route in ("/api/explorer", "/api/explorer/"):
        result = mvp_api.project_explorer_response(
            items,
            page=int(qs.get("page", ["1"])[0]),
            page_size=int(qs.get("page_size", ["20"])[0]),
            search=qs.get("search", [None])[0],
            stage=qs.get("stage", [None])[0],
            snapshot_meta=payload,
        )
        json_response(handler, result); return True
    if route.startswith("/api/symbol/"):
        symbol = route[len("/api/symbol/"):].strip().rstrip("/")
        if not symbol:
            json_response(handler, {"error": "symbol required"}, status=400); return True
        result = mvp_api.project_symbol_detail(items, symbol)
        if result is None: _not_found(handler, symbol)
        else: json_response(handler, result)
        return True
    if route.startswith("/api/chart-db/"):
        symbol = route[len("/api/chart-db/"):].strip().rstrip("/")
        if not symbol:
            json_response(handler, {"error": "symbol required"}, status=400); return True
        import mvp_chart_db
        timeframe = (qs.get("timeframe", ["1D"])[0] or "1D").upper()
        try:
            result = mvp_chart_db.project_chart_db_response(symbol, timeframe=timeframe)
        except ValueError as exc:
            json_response(handler, {"error": str(exc)}, status=400); return True
        if result is None: _not_found(handler, symbol)
        else: json_response(handler, result)
        return True
    if route.startswith("/api/chart/"):
        symbol = route[len("/api/chart/"):].strip().rstrip("/")
        if not symbol:
            json_response(handler, {"error": "symbol required"}, status=400); return True
        import mvp_chart
        result = mvp_chart.project_chart_response(items, symbol)
        if not result or not (result.get("candles") or []):
            import mvp_chart_db
            timeframe = (qs.get("timeframe", ["1D"])[0] or "1D").upper()
            try:
                result = mvp_chart_db.project_chart_db_response(symbol, timeframe=timeframe) or result
            except ValueError as exc:
                json_response(handler, {"error": str(exc)}, status=400); return True
        if result is None: _not_found(handler, symbol)
        else: json_response(handler, result)
        return True
    return False
