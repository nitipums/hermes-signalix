import gzip
import json
from pathlib import Path
import subprocess
import sys

from active_transport import ActiveTransportHandler, ACTIVE_ROUTE_TABLE
import trend_map
from active_transport import retired_route_payload


class Handler:
    _accepts_gzip = ActiveTransportHandler._accepts_gzip

    def __init__(self, accept_encoding=""):
        self.headers = []
        self.status = None
        self.request_version = "HTTP/1.1"
        self.headers_in = {"Accept-Encoding": accept_encoding}
        self.wfile = self
        self.ended = False

    def header_value(self, name):
        return self.headers_in.get(name, "")

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers.append((name, value))

    def end_headers(self):
        self.ended = True

    def write(self, body):
        self.body = body


def header(handler, name):
    return next(value for key, value in handler.headers if key.lower() == name.lower())


def test_trend_map_transport_gzip_negotiation_and_cache_headers():
    payload = b'{"status":"PRODUCTION_READ_ONLY","rows":[]}'
    compressed = Handler("br, gzip")
    ActiveTransportHandler.send_bytes(compressed, payload, content_type="application/json; charset=utf-8")

    assert compressed.status == 200
    assert gzip.decompress(compressed.body) == payload
    assert header(compressed, "Content-Encoding") == "gzip"
    assert header(compressed, "Content-Length") == str(len(compressed.body))
    assert header(compressed, "Vary") == "Accept-Encoding"
    assert header(compressed, "Cache-Control") == "no-store"

    identity = Handler("gzip;q=0")
    ActiveTransportHandler.send_bytes(identity, payload, content_type="application/json; charset=utf-8")

    assert identity.body == payload
    assert all(key.lower() != "content-encoding" for key, _ in identity.headers)
    assert header(identity, "Content-Length") == str(len(payload))
    assert header(identity, "Vary") == "Accept-Encoding"
    assert header(identity, "Cache-Control") == "no-store"


def test_accepts_gzip_explicit_quality_overrides_wildcard_and_rejects_invalid_values():
    assert Handler("gzip")._accepts_gzip()
    assert Handler("gzip;q=1")._accepts_gzip()
    assert Handler("*;q=1")._accepts_gzip()
    assert not Handler("*;q=1, gzip;q=0")._accepts_gzip()
    assert not Handler("*;q=1, gzip;q=2")._accepts_gzip()
    assert not Handler("*;q=1, gzip;q=inf")._accepts_gzip()
    assert not Handler("*;q=1, gzip;q=malformed")._accepts_gzip()
    assert not Handler("*;q=1, gzip;q")._accepts_gzip()


def test_trend_map_route_uses_send_bytes_seam(monkeypatch):
    payload = {
        "status": "PRODUCTION_READ_ONLY",
        "research_only": False,
        "actionability": "NONE",
        "rows": [],
    }

    class RouteHandler:
        def send_bytes(self, body, *, content_type, status=200, cache_control="no-store"):
            self.body = body
            self.status = status
            self.content_type = content_type
            self.cache_control = cache_control
            self.content_length = len(body)

    monkeypatch.setattr(trend_map, "build_trend_map_report", lambda: payload)
    handler = RouteHandler()

    assert trend_map.handle_trend_map_api("/api/trend-map", handler)
    assert handler.status == 200
    assert handler.content_type == "application/json; charset=utf-8"
    assert handler.cache_control == "no-store"
    assert handler.content_length == len(handler.body)
    assert json.loads(handler.body) == payload


def test_retired_route_payload_is_small_historical_non_actionable_response():
    assert retired_route_payload("/mvp") == {
        "status": "retired",
        "historical": True,
        "actionability": "NONE",
        "message": "This historical Signalix setup surface is retired; use the current read-only Trend Map.",
        "replacement": "/trend-map",
        "route": "/mvp",
    }


class _TransportProbe(ActiveTransportHandler):
    def __init__(self, path):
        self.path = path
        self.request_version = "HTTP/1.1"
        self.headers = {"Accept-Encoding": ""}
        self.status = None
        self.response_headers = []
        self.body = b""
        self.wfile = self

    def header_value(self, name):
        return self.headers.get(name, "")

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.response_headers.append((name, value))

    def write(self, body):
        self.body = body

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        if not getattr(self, "_cache_control_sent", False):
            self.send_header("Cache-Control", "no-store")

    def send_error(self, status, message=None):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.body = (message or "error").encode("utf-8")


def request(path):
    probe = _TransportProbe(path)
    ActiveTransportHandler.do_GET(probe)
    return {
        "status": probe.status,
        "headers": dict(probe.response_headers),
        "body": probe.body,
    }


def test_transport_has_explicit_active_allowlist_and_rejects_fallthrough(monkeypatch):
    def active_api(path, handler):
        handler.send_bytes(b"{}", content_type="application/json; charset=utf-8")
        return True

    monkeypatch.setattr("active_transport.handle_trend_map_api", active_api)
    monkeypatch.setattr("active_transport.handle_market_breadth_api", active_api)
    assert set(ACTIVE_ROUTE_TABLE) == {
        "/trend-map", "/api/trend-map", "/market-breadth", "/api/market-breadth"
    }
    for path in ("/trend-map", "/market-breadth", "/api/trend-map", "/api/market-breadth"):
        response = request(path)
        assert response["status"] == 200
        assert response["headers"]["Cache-Control"] == "no-store"
    for path in ("/unknown", "/frontend/app.js", "/request_cache.js", "/api/unknown"):
        response = request(path)
        assert response["status"] == 404
        assert response["headers"]["Cache-Control"] == "no-store"


def test_active_entrypoint_import_does_not_load_historical_dispatchers():
    code = (
        "import json,sys; import active_transport; "
        "print(json.dumps(sorted(set(sys.modules) & "
        "{'mvp_routes','mvp_api','vcp_finder','actionable_signal_policy',"
        "'shadow_signal_replay','chart_wave_evidence'})))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent,
    )
    assert json.loads(result.stdout) == []


def test_active_chart_request_does_not_load_historical_decision_modules():
    code = """
import json, sys
import active_chart_routes, chart_read_model
chart_read_model.read_current = lambda symbol, timeframe: {
    'symbol': symbol, 'timeframe': timeframe,
    'candles': [{'date': '2026-09-19', 'close': 10}],
    'provenance': {'source': 'test'},
}
class Handler:
    def send_bytes(self, body, **kwargs):
        self.body = body
active_chart_routes.handle_active_chart_api(
    '/api/chart-db/AAA?timeframe=1D&view=chart', Handler())
print(json.dumps(sorted(set(sys.modules) & {
    'mvp_routes', 'mvp_api', 'vcp_finder', 'actionable_signal_policy',
    'shadow_signal_replay', 'chart_wave_evidence'})))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent,
    )
    assert json.loads(result.stdout) == []


def test_active_static_assets_are_served_with_content_and_unknown_assets_404():
    expected_markers = {
        "/styles.css": b".trend-route",
        "/canonical-client.js": b"fetchAllCandidates",
        "/shared-drawer.js": b"openSharedDrawer",
    }
    for path, marker in expected_markers.items():
        response = request(path)
        assert response["status"] == 200
        assert response["body"]
        assert marker in response["body"]
        assert response["headers"]["Content-Type"].startswith(
            "text/"
        ) or response["headers"]["Content-Type"].startswith(
            "application/javascript"
        )
    assert request("/not-an-active-asset.js")["status"] == 404


def test_root_and_index_aliases_redirect_with_query_and_no_store():
    for path in ("/", "/index", "/index.html"):
        response = request(path + "?from=test")
        assert response["status"] == 302
        assert response["headers"]["Location"] == "/trend-map?from=test"
        assert response["headers"]["Cache-Control"] == "no-store"


def test_retired_routes_are_explicitly_unavailable():
    assert request("/mvp")["status"] == 410
    assert request("/api/setup-candidates")["status"] == 410
    assert request("/wave-context")["status"] == 404
    assert request("/dashboard.html")["status"] == 404
    assert request("/api/vcp-finder")["status"] == 404
    assert request("/api/shadow-buy-signals")["status"] == 404
    assert request("/api/team/setup-candidates")["status"] == 404


def test_active_api_callers_use_retained_explicit_chart_and_trend_route_shapes(monkeypatch):
    calls = []

    def trend_route(path, handler):
        calls.append(("trend", path))
        handler.send_bytes(b"{}", content_type="application/json; charset=utf-8")
        return True

    def mvp(path, handler):
        calls.append(("chart", path))
        handler.send_bytes(b"{}", content_type="application/json; charset=utf-8")
        return True

    monkeypatch.setattr("active_transport.handle_trend_route_api", trend_route)
    monkeypatch.setattr("active_transport.handle_active_chart_api", mvp)
    for path in (
        "/api/trend-map/aAa/route?window=260",
        "/api/trend-map/AA-BB/route?window=260",
        "/api/trend-map/AA.BB/route?window=260",
        "/api/trend-map/AA_BB/route?window=260",
        "/api/chart-db/AAA?timeframe=1D",
    ):
        response = request(path)
        assert response["status"] == 200
    assert calls == [
        ("trend", "/api/trend-map/aAa/route?window=260"),
        ("trend", "/api/trend-map/AA-BB/route?window=260"),
        ("trend", "/api/trend-map/AA.BB/route?window=260"),
        ("trend", "/api/trend-map/AA_BB/route?window=260"),
        ("chart", "/api/chart-db/AAA?timeframe=1D"),
    ]
    assert request("/api/chart/AAA")["status"] == 404


def test_market_breadth_query_is_preserved_at_transport_boundary(monkeypatch):
    calls = []

    def market_breadth(path, handler):
        calls.append(path)
        handler.send_bytes(b"{}", content_type="application/json; charset=utf-8")
        return True

    monkeypatch.setattr("active_transport.handle_market_breadth_api", market_breadth)
    assert request("/api/market-breadth?range=20D")["status"] == 200
    assert calls == ["/api/market-breadth?range=20D"]


def test_malformed_retained_api_symbol_shapes_are_deterministic_404(monkeypatch):
    def unexpected_handler(path, handler):
        raise AssertionError(f"dispatcher must reject {path!r}")

    monkeypatch.setattr("active_transport.handle_trend_route_api", unexpected_handler)
    monkeypatch.setattr("active_transport.handle_active_chart_api", unexpected_handler)
    for path in (
        "/api/trend-map/AA A/route",
        "/api/trend-map/AA%2FBB/route",
        "/api/trend-map/AA!%40/route",
        "/api/trend-map/AA/extra/route",
        "/api/symbol/AA A",
        "/api/symbol/AA%2FBB",
        "/api/symbol/AA!%40",
        "/api/symbol/AA/extra",
        "/api/chart-db/.AABB",
        "/api/chart-db/AA!BB",
        "/api/chart-db/AA/extra",
    ):
        assert request(path)["status"] == 404


def test_dispatcher_false_fallthrough_is_a_deterministic_404(monkeypatch):
    monkeypatch.setattr("active_transport.handle_trend_route_api", lambda path, handler: False)
    monkeypatch.setattr("active_transport.handle_active_chart_api", lambda path, handler: False)
    assert request("/api/trend-map/AAA/route")["status"] == 404
    assert request("/api/symbol/AAA")["status"] == 404
