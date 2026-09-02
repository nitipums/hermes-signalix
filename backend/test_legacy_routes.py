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


def test_vcp_route_response_is_explicitly_audit_only(monkeypatch):
    class Conn:
        def close(self): pass

    monkeypatch.setattr(mvp_routes, "_vcp_pg", lambda: Conn())
    monkeypatch.setattr(
        "vcp_finder_db.load_latest_vcp_run",
        lambda *args, **kwargs: {"results": [{"symbol": "AUDIT"}]},
    )
    handler = type("Handler", (), {
        "wfile": None,
        "send_response": lambda self, status: setattr(self, "status", status),
        "send_header": lambda self, *args: None,
        "end_headers": lambda self: None,
    })()
    body = bytearray()
    handler.wfile = type("Writer", (), {"write": lambda self, data: body.extend(data)})()
    assert mvp_routes.handle_mvp_api("/api/vcp-finder", handler)
    payload = json.loads(body)
    assert payload["audit_only"] is True
    assert payload["deprecation"] == mvp_routes.VCP_AUDIT_DEPRECATION


def test_setup_candidates_never_falls_back_to_legacy_snapshot(monkeypatch):
    def fail_snapshot():
        raise AssertionError("canonical route called the legacy snapshot")

    monkeypatch.setattr(mvp_routes, "load_payload", fail_snapshot)
    monkeypatch.setattr("read_model_publisher.load_current_read_model", lambda: {
        "items": [], "universe": "marginable_long", "eligible_count": 0,
        "excluded_count": 0, "freshness": {"status": "fresh"},
        "provenance": {"as_of": None, "source_versions": {},
                        "policy_version": "setup-candidates-v1"},
        "source_version": "test-version", "published_at": "t1",
    })
    monkeypatch.setattr(
        "mvp_api.build_setup_candidates_from_data",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("canonical route called the builder")),
    )
    mvp_routes.clear_setup_candidates_cache()
    handler = type("Handler", (), {
        "wfile": None,
        "send_response": lambda self, status: setattr(self, "status", status),
        "send_header": lambda self, *args: None,
        "end_headers": lambda self: None,
    })()
    body = bytearray()
    handler.wfile = type("Writer", (), {"write": lambda self, data: body.extend(data)})()
    assert mvp_routes.handle_mvp_api("/api/setup-candidates", handler)
    assert handler.status == 200
    assert json.loads(body)["evaluated_count"] == 0
    mvp_routes.clear_setup_candidates_cache()


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
