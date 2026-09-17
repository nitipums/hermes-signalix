"""HTTP seam for the symbol-scoped Trend Route read model."""
from __future__ import annotations

import json
import re
from urllib.parse import unquote, urlsplit

import trend_route_publisher as publisher


def route_envelope(symbol: str, route: dict, *, universe: dict | None = None) -> dict:
    status = route.get("status", "NOT_VERIFIED")
    return {"status": "PRODUCTION_READ_ONLY", "research_only": False, "actionability": "NONE",
            "verification_status": "VERIFIED" if status in {"FULL", "PARTIAL"} else "NOT_VERIFIED",
            "symbol": symbol, "universe": universe or {"scope": "marginable_long", "mode": "fixed_current_universe",
                                              "membership": "published_current_universe"},
            "route": {key: route.get(key) for key in ("status", "reason_codes", "policy_version", "coverage",
                                                        "segments", "transitions", "duration_summaries", "provenance")},
            "provenance": {"source": "trend_route_read_model", "timeframe": "1D", "query_mode": "READ_MODEL",
                           "no_lookahead": True}}


def _published_symbols(universe: dict | None, routes: dict) -> set[str]:
    """Prefer explicit universe membership; route keys are the read-model fallback."""
    if isinstance(universe, dict):
        for key in ("symbols", "members", "universe_symbols"):
            values = universe.get(key)
            if isinstance(values, (list, tuple, set)):
                return {str(value).strip().upper() for value in values if str(value).strip()}
    return {str(value).strip().upper() for value in routes}


def handle_trend_route_api(path: str, handler, *, reader=None) -> bool:
    parsed = urlsplit(path).path
    prefix = "/api/trend-map/"
    suffix = "/route"
    if not (parsed.startswith(prefix) and parsed.endswith(suffix)):
        return False
    symbol = unquote(parsed[len(prefix):-len(suffix)]).strip().upper()
    if not symbol or not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]*", symbol):
        payload = {"status": "PRODUCTION_READ_ONLY", "research_only": False, "actionability": "NONE",
                   "verification_status": "NOT_VERIFIED", "symbol": symbol,
                   "error": "MALFORMED_SYMBOL", "reason_codes": ["MALFORMED_SYMBOL"]}
        status = 404
        _send(handler, payload, status)
        return True
    try:
        if reader is None:
            model = publisher.read_current_route()
            if model.get("verification_status") != "VERIFIED":
                payload = route_envelope(symbol, {"status": "NOT_VERIFIED", "reason_codes": ["READ_MODEL_UNAVAILABLE"]})
                _send(handler, payload, 503)
                return True
            universe = model.get("universe") if isinstance(model.get("universe"), dict) else None
            routes = model.get("routes") if isinstance(model.get("routes"), dict) else {}
            published_symbols = _published_symbols(universe, routes)
            if symbol not in published_symbols or symbol not in routes:
                payload = {"status": "PRODUCTION_READ_ONLY", "research_only": False, "actionability": "NONE",
                           "verification_status": "NOT_VERIFIED", "symbol": symbol,
                           "error": "SYMBOL_NOT_PUBLISHED", "reason_codes": ["SYMBOL_NOT_PUBLISHED"],
                           "universe": universe or {"scope": "marginable_long", "mode": "fixed_current_universe",
                                                       "membership": "published_current_universe"}}
                _send(handler, payload, 404)
                return True
            payload = route_envelope(symbol, routes[symbol], universe=universe)
        else:
            route = reader(symbol)
            if not isinstance(route, dict) or route.get("status") == "NOT_VERIFIED" and "SYMBOL_NOT_PUBLISHED" in route.get("reason_codes", []):
                payload = {"status": "PRODUCTION_READ_ONLY", "research_only": False, "actionability": "NONE",
                           "verification_status": "NOT_VERIFIED", "symbol": symbol,
                           "error": "SYMBOL_NOT_PUBLISHED", "reason_codes": ["SYMBOL_NOT_PUBLISHED"]}
                _send(handler, payload, 404)
                return True
            payload = route_envelope(symbol, route)
    except Exception:
        payload = route_envelope(symbol, {"status": "NOT_VERIFIED", "reason_codes": ["READ_MODEL_UNAVAILABLE"]})
        payload["verification_status"] = "NOT_VERIFIED"
        _send(handler, payload, 503)
        return True
    _send(handler, payload, 200)
    return True


def _send(handler, payload: dict, status: int) -> None:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    if hasattr(handler, "send_bytes"):
        handler.send_bytes(body, content_type="application/json; charset=utf-8", status=status)
    else:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
