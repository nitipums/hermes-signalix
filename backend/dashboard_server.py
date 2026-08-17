"""Minimal static file server for the Signalix dashboard.

Serves /app/dashboard.html (and any other static asset in the backend dir)
on port 3001. Run as a sidecar so the dashboard is always available alongside
the FastAPI backend on port 8000.
"""
import os
import http.server
import socketserver
from urllib.parse import urlsplit

PORT = int(os.getenv("DASHBOARD_PORT", "3001"))
DIR = "/app"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def do_GET(self):
        # serve friendly routes for the public Signalix portal and the private
        # owner-only Investment Co-pilot cockpit. Strip the query string first
        # so cache-busting URLs such as /portfolio?v=2 still resolve.
        parsed = urlsplit(self.path)
        path = parsed.path
        suffix = ("?" + parsed.query) if parsed.query else ""
        if path in ("/portal", "/portal/", "/portal.html"):
            self.path = "/portal.html" + suffix
        elif path in ("/portfolio", "/portfolio/", "/portfolio.html"):
            self.path = "/portfolio.html" + suffix
        return super().do_GET()

    def end_headers(self):
        # allow clicking the dashboard link from Telegram/Bots
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


if __name__ == "__main__":
    os.chdir(DIR)
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.daemon_threads = True
        print(f"Serving dashboard on 0.0.0.0:{PORT}")
        httpd.serve_forever()
