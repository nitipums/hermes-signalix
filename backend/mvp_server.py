"""MVP dashboard server.

Serves the owner-only Classic Review app at /mvp and the presentation-only
Wave Context app at /wave-context. The former dashboard.html surface is
retired and deliberately returns 404. This entrypoint has no dependency on
legacy_routes, legacy_server, portal.html, portfolio.html, or legacy snapshots.
"""
from __future__ import annotations

import http.server
import os
import socketserver
from urllib.parse import urlsplit

from mvp_routes import handle_mvp_api
from shadow_trend_map import handle_shadow_trend_map_api

PORT = int(os.getenv("DASHBOARD_PORT", "3001"))
HOST = os.getenv("DASHBOARD_BIND_HOST", "127.0.0.1")
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DIR = os.getenv("FRONTEND_DIR", os.path.join(_BACKEND_DIR, "frontend"))



class MVPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Use the runtime FRONTEND_DIR so tests can point the server at a fixture
        # directory without mutating global module state.
        super().__init__(*args, directory=os.getenv("FRONTEND_DIR", DIR), **kwargs)


    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        suffix = ("?" + parsed.query) if parsed.query else ""
        if path == "/trend-map-shadow":
            template_path = os.path.join(_BACKEND_DIR, "shadow_trend_map_template.html")
            try:
                with open(template_path, "rb") as template:
                    body = template.read()
            except OSError:
                self.send_error(404, "shadow trend-map template unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/api/"):
            if path == "/api/trend-map-shadow" and handle_shadow_trend_map_api(self.path, self):
                return
            if handle_mvp_api(self.path, self):
                return
            self.send_error(404, "MVP API route not found")
            return
        if path == "/dashboard.html":
            self.send_error(404, "dashboard.html retired; use /mvp")
            return
        if path in ("/mvp", "/mvp/"):
            self.path = "/index.html" + suffix
        elif path in ("/wave-context", "/wave-context/"):
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
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    os.chdir(DIR)
    with socketserver.ThreadingTCPServer((HOST, PORT), MVPHandler) as httpd:
        httpd.daemon_threads = True
        print(f"Serving MVP dashboard on {HOST}:{PORT}")
        httpd.serve_forever()
