"""Standalone legacy compatibility server.

This entrypoint serves only legacy dashboard/portal/portfolio assets. The public
:3001 dispatcher keeps compatibility routes during migration; this process can
be promoted behind a proxy after route-parity review.
"""
from __future__ import annotations

import http.server
import os
import socketserver
from urllib.parse import urlsplit

from legacy_routes import legacy_file_for_path, serve_file

PORT = int(os.getenv("LEGACY_PORT", "3002"))
LEGACY_DIR = os.getenv("LEGACY_DIR", os.path.dirname(os.path.abspath(__file__)))


class LegacyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=LEGACY_DIR, **kwargs)

    def do_GET(self):
        path = urlsplit(self.path).path
        target = legacy_file_for_path(path, LEGACY_DIR)
        if target:
            return serve_file(self, target)
        if path in ("/", "/index", "/index.html"):
            return serve_file(self, os.path.join(LEGACY_DIR, "dashboard.html"))
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Legacy route only")

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), LegacyHandler) as httpd:
        httpd.daemon_threads = True
        print(f"Serving legacy dashboard on 0.0.0.0:{PORT}")
        httpd.serve_forever()
