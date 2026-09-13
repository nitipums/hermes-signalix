import gzip
import json

from mvp_server import MVPHandler
import shadow_trend_map


class Handler:
    _accepts_gzip = MVPHandler._accepts_gzip

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
    MVPHandler.send_bytes(compressed, payload, content_type="application/json; charset=utf-8")

    assert compressed.status == 200
    assert gzip.decompress(compressed.body) == payload
    assert header(compressed, "Content-Encoding") == "gzip"
    assert header(compressed, "Content-Length") == str(len(compressed.body))
    assert header(compressed, "Vary") == "Accept-Encoding"
    assert header(compressed, "Cache-Control") == "no-store"

    identity = Handler("gzip;q=0")
    MVPHandler.send_bytes(identity, payload, content_type="application/json; charset=utf-8")

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


def test_shadow_trend_map_route_uses_send_bytes_seam(monkeypatch):
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

    monkeypatch.setattr(shadow_trend_map, "build_shadow_report", lambda: payload)
    handler = RouteHandler()

    assert shadow_trend_map.handle_shadow_trend_map_api("/api/trend-map-shadow", handler)
    assert handler.status == 200
    assert handler.content_type == "application/json; charset=utf-8"
    assert handler.cache_control == "no-store"
    assert handler.content_length == len(handler.body)
    assert json.loads(handler.body) == payload
