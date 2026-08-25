"""Signalix dashboard compatibility entrypoint.

Route ownership is split:
- ``mvp_routes`` owns /api/* projection routes.
- ``legacy_routes`` owns /dashboard.html, /portal, and /portfolio files.
- this module owns only HTTP server lifecycle and route dispatch.
"""
from __future__ import annotations

import os
import http.server
import socketserver
from urllib.parse import urlsplit

from legacy_routes import legacy_file_for_path, serve_file
from mvp_routes import handle_mvp_api

PORT = int(os.getenv("DASHBOARD_PORT", "3001"))
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DIR = os.getenv("FRONTEND_DIR", os.path.join(_BACKEND_DIR, "frontend"))
LEGACY_DIR = os.getenv("LEGACY_DIR", _BACKEND_DIR)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        suffix = ("?" + parsed.query) if parsed.query else ""

        if path.startswith("/api/"):
            if handle_mvp_api(self.path, self):
                return
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        legacy_file = legacy_file_for_path(path, LEGACY_DIR)
        if legacy_file:
            return serve_file(self, legacy_file)

        if path in ("/mvp", "/mvp/"):
            self.path = "/index.html" + suffix
        elif path in ("/", "/index", "/index.html"):
            self.path = "/index.html" + suffix
        return super().do_GET()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


if __name__ == "__main__":
    os.chdir(DIR)
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.daemon_threads = True
        print(f"Serving dashboard on 0.0.0.0:{PORT}")
        httpd.serve_forever()
