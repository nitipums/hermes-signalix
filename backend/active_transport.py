"""Canonical HTTP transport for Signalix's active read-only product."""
from __future__ import annotations

import gzip
import http.server
import json
import math
import mimetypes
import os
import re
import socketserver
from urllib.parse import urlsplit

from active_chart_routes import handle_active_chart_api
from market_breadth_artifact import handle_market_breadth_api
from trend_map import handle_trend_map_api
from trend_route_api import handle_trend_route_api

PORT = int(os.getenv("DASHBOARD_PORT", "3001"))
HOST = os.getenv("DASHBOARD_BIND_HOST", "127.0.0.1")
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DIR = os.getenv("FRONTEND_DIR", os.path.join(_BACKEND_DIR, "frontend"))

ACTIVE_ROUTE_TABLE = {
    "/trend-map": "page",
    "/api/trend-map": "api",
    "/market-breadth": "page",
    "/api/market-breadth": "api",
}
_ACTIVE_STATIC_ASSETS = {
    "/styles.css": "styles.css",
    "/canonical-client.js": "canonical-client.js",
    "/shared-drawer.js": "shared-drawer.js",
}
_SYMBOL_SEGMENT = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_ACTIVE_CHART_API = re.compile(rf"^/api/chart-db/{_SYMBOL_SEGMENT}/?$")
_ACTIVE_TREND_ROUTE_API = re.compile(
    rf"^/api/trend-map/{_SYMBOL_SEGMENT}/route$"
)
_RETIRED = {
    "status": "retired",
    "historical": True,
    "actionability": "NONE",
    "message": "This historical Signalix setup surface is retired; use the current read-only Trend Map.",
    "replacement": "/trend-map",
}


def retired_route_payload(route: str) -> dict:
    return {**_RETIRED, "route": route}


class ActiveTransportHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.getenv("FRONTEND_DIR", DIR), **kwargs)

    def _accepts_gzip(self):
        headers = getattr(self, "headers", None)
        value = (headers.get("Accept-Encoding", "") if headers is not None and hasattr(headers, "get")
                 else self.header_value("Accept-Encoding")) or ""
        wildcard_quality = gzip_quality = None
        for item in value.lower().split(","):
            encoding, _, parameters = item.strip().partition(";")
            if encoding not in ("gzip", "*"):
                continue
            quality = 1.0
            for parameter in parameters.split(";"):
                name, separator, raw_value = parameter.strip().partition("=")
                if name.strip() == "q":
                    try:
                        quality = float(raw_value.strip()) if separator else 0.0
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

    def redirect(self, location, status=302):
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self._cache_control_sent = True
        self.end_headers()

    def _serve_file(self, path, content_type):
        try:
            with open(path, "rb") as source:
                body = source.read()
        except OSError:
            self.send_error(404, "Active resource unavailable")
            return
        self.send_bytes(body, content_type=content_type)

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        suffix = ("?" + parsed.query) if parsed.query else ""
        if path == "/trend-map":
            self._serve_file(os.path.join(_BACKEND_DIR, "trend_map_template.html"),
                             "text/html; charset=utf-8")
            return
        if path == "/market-breadth":
            self._serve_file(os.path.join(_BACKEND_DIR, "market_breadth_template.html"),
                             "text/html; charset=utf-8")
            return
        if path in _ACTIVE_STATIC_ASSETS:
            asset_path = os.path.join(DIR, _ACTIVE_STATIC_ASSETS[path])
            mime = mimetypes.guess_type(asset_path)[0] or "application/octet-stream"
            self._serve_file(asset_path, f"{mime}; charset=utf-8")
            return
        if path.startswith("/api/"):
            if path in ("/api/setup-candidates", "/api/setup-candidates/"):
                self.send_bytes(json.dumps(retired_route_payload("/api/setup-candidates"), ensure_ascii=False).encode(),
                                content_type="application/json; charset=utf-8", status=410)
                return
            if _ACTIVE_TREND_ROUTE_API.fullmatch(path) and handle_trend_route_api(self.path, self):
                return
            if path == "/api/market-breadth" and handle_market_breadth_api(self.path, self):
                return
            if path == "/api/trend-map" and handle_trend_map_api(self.path, self):
                return
            if _ACTIVE_CHART_API.fullmatch(path) and handle_active_chart_api(self.path, self):
                return
            self.send_error(404, "API route not found")
            return
        if path in ("/mvp", "/mvp/"):
            self.send_bytes(json.dumps(retired_route_payload("/mvp"), ensure_ascii=False).encode(),
                            content_type="application/json; charset=utf-8", status=410)
            return
        if path in ("/", "/index", "/index.html"):
            self.redirect("/trend-map" + suffix)
            return
        self.send_error(404, "Route not found")

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        if not getattr(self, "_cache_control_sent", False):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    os.chdir(DIR)
    try:
        from chart_read_model import warm_current
        for timeframe in ("1D", "60M", "1W", "1M"):
            warm_current(timeframe)
    except Exception:
        pass
    with socketserver.ThreadingTCPServer((HOST, PORT), ActiveTransportHandler) as httpd:
        httpd.daemon_threads = True
        print(f"Serving active Signalix transport on {HOST}:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
