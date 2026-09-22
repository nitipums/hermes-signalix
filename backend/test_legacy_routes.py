from fastapi import HTTPException

from app import dashboard_snapshot
import json

import mvp_routes


def test_legacy_dashboard_snapshot_is_explicitly_retired():
    try:
        dashboard_snapshot()
    except HTTPException as exc:
        assert exc.status_code == 410
        assert "retired" in str(exc.detail)
    else:
        raise AssertionError("legacy dashboard snapshot unexpectedly remained live")


def test_setup_candidates_is_explicitly_retired_without_fallback(monkeypatch):
    def fail_snapshot():
        raise AssertionError("canonical route called the legacy snapshot")

    monkeypatch.setattr(mvp_routes, "load_payload", fail_snapshot)
    handler = type("Handler", (), {
        "wfile": None,
        "send_response": lambda self, status: setattr(self, "status", status),
        "send_header": lambda self, *args: None,
        "end_headers": lambda self: None,
    })()
    body = bytearray()
    handler.wfile = type("Writer", (), {"write": lambda self, data: body.extend(data)})()
    assert mvp_routes.handle_mvp_api("/api/setup-candidates", handler)
    assert handler.status == 410
    payload = json.loads(body)
    assert payload["status"] == "retired"
    assert payload["historical"] is True
    assert payload["route"] == "/api/setup-candidates"


def test_chart_compatibility_response_is_explicitly_audit_only(monkeypatch):
    monkeypatch.setattr(mvp_routes, "load_payload", lambda: {"items": []})
    monkeypatch.setattr(
        "mvp_chart.project_chart_response",
        lambda items, symbol: {"symbol": symbol, "candles": [{"close": 1}]},
    )
    handler = type("Handler", (), {
        "wfile": None,
        "send_response": lambda self, status: setattr(self, "status", status),
        "send_header": lambda self, *args: None,
        "end_headers": lambda self: None,
    })()
    body = bytearray()
    handler.wfile = type("Writer", (), {"write": lambda self, data: body.extend(data)})()

    assert mvp_routes.handle_mvp_api("/api/chart/AUDIT", handler)
    payload = json.loads(body)
    assert payload["audit_only"] is True
    assert payload["deprecation"] == mvp_routes.LEGACY_ROUTE_DEPRECATION
