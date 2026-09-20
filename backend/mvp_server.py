"""Signalix Daily Trend Map server.

Serves the canonical public read-only Trend Map at /trend-map and the
presentation-only Wave Context app at /wave-context. Retired setup/MVP routes
remain compatibility history and are not the active product surface.
"""
from __future__ import annotations

import gzip
import http.server
import math
import os
import socketserver
from urllib.parse import urlsplit

from mvp_routes import handle_mvp_api, retired_route_payload
from trend_map import handle_trend_map_api
from trend_route_api import handle_trend_route_api
from market_breadth_artifact import handle_market_breadth_api

PORT = int(os.getenv("DASHBOARD_PORT", "3001"))
HOST = os.getenv("DASHBOARD_BIND_HOST", "127.0.0.1")
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DIR = os.getenv("FRONTEND_DIR", os.path.join(_BACKEND_DIR, "frontend"))



class MVPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Use the runtime FRONTEND_DIR so tests can point the server at a fixture
        # directory without mutating global module state.
        super().__init__(*args, directory=os.getenv("FRONTEND_DIR", DIR), **kwargs)

    def _accepts_gzip(self):
        headers = getattr(self, "headers", None)
        if headers is not None and hasattr(headers, "get"):
            value = headers.get("Accept-Encoding", "") or ""
        else:
            value = self.header_value("Accept-Encoding") or ""
        wildcard_quality = None
        gzip_quality = None
        for item in value.lower().split(","):
            encoding, _, parameters = item.strip().partition(";")
            if encoding not in ("gzip", "*"):
                continue
            quality = 1.0
            for parameter in parameters.split(";"):
                name, separator, raw_value = parameter.strip().partition("=")
                if name.strip() == "q":
                    if not separator:
                        quality = 0.0
                    else:
                        try:
                            quality = float(raw_value.strip())
                        except ValueError:
                            quality = 0.0
                    if not 0.0 <= quality <= 1.0 or not math.isfinite(quality):
                        quality = 0.0
            if encoding == "gzip":
                gzip_quality = quality
            else:
                wildcard_quality = quality
        if gzip_quality is not None:
            return gzip_quality > 0
        return wildcard_quality is not None and wildcard_quality > 0

    def send_bytes(self, body, *, content_type, status=200, cache_control="no-store"):
        """Send a complete response with HTTP/1.0-compatible byte framing."""
        encoded = gzip.compress(body, mtime=0) if self._accepts_gzip() else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Vary", "Accept-Encoding")
        if encoded is not body:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Cache-Control", cache_control)
        self._cache_control_sent = True
        self.end_headers()
        self.wfile.write(encoded)


    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        suffix = ("?" + parsed.query) if parsed.query else ""
        if path == "/trend-map":
            template_path = os.path.join(_BACKEND_DIR, "trend_map_template.html")
            try:
                with open(template_path, "rb") as template:
                    body = template.read()
            except OSError:
                self.send_error(404, "Trend Map template unavailable")
                return
            self.send_bytes(body, content_type="text/html; charset=utf-8")
            return
        if path == "/market-breadth":
            template_path = os.path.join(_BACKEND_DIR, "market_breadth_template.html")
            try:
                with open(template_path, "rb") as template:
                    body = template.read()
            except OSError:
                self.send_error(404, "market breadth template unavailable")
                return
            self.send_bytes(body, content_type="text/html; charset=utf-8")
            return
        if path.startswith("/api/"):
            if path in ("/api/setup-candidates", "/api/setup-candidates/"):
                body = __import__("json").dumps(
                    retired_route_payload("/api/setup-candidates"), ensure_ascii=False
                ).encode("utf-8")
                self.send_bytes(body, content_type="application/json; charset=utf-8", status=410)
                return
            if handle_trend_route_api(self.path, self):
                return
            if path == "/api/market-breadth" and handle_market_breadth_api(self.path, self):
                return
            if path == "/api/trend-map" and handle_trend_map_api(self.path, self):
                return
            if handle_mvp_api(self.path, self):
                return
            self.send_error(404, "MVP API route not found")
            return
        if path == "/dashboard.html":
            self.send_error(404, "dashboard.html retired; use /trend-map")
            return
        if path in ("/mvp", "/mvp/"):
            body = __import__("json").dumps(
                retired_route_payload("/mvp"), ensure_ascii=False
            ).encode("utf-8")
            self.send_bytes(body, content_type="application/json; charset=utf-8", status=410)
            return
        if path in ("/wave-context", "/wave-context/"):
            self.path = "/wave-context.html" + suffix
        elif path in ("/", "/index", "/index.html"):
            self.path = "/index.html" + suffix
        else:
            # No compatibility route is exposed by the MVP server.
            if path in ("/portal", "/portfolio"):
                self.send_error(404, "legacy route unavailable")
                return
        return super().do_GET()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        if not getattr(self, "_cache_control_sent", False):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    os.chdir(DIR)
    try:
        from chart_read_model import warm_current
        for timeframe in ("1D", "60M", "1W", "1M"):
            warm_current(timeframe)
    except Exception:
        pass
    with socketserver.ThreadingTCPServer((HOST, PORT), MVPHandler) as httpd:
        httpd.daemon_threads = True
        print(f"Serving MVP dashboard on {HOST}:{PORT}")
        httpd.serve_forever()
