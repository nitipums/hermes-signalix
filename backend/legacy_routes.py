"""Legacy static route mapping for the compatibility dashboard server."""
from __future__ import annotations

import os


def legacy_file_for_path(path: str, legacy_dir: str) -> str | None:
    """Map only legacy routes to files; MVP routes are deliberately excluded."""
    names = {
        "/dashboard": "dashboard.html",
        "/dashboard/": "dashboard.html",
        "/dashboard.html": "dashboard.html",
        "/portal": "portal.html",
        "/portal/": "portal.html",
        "/portal.html": "portal.html",
        "/portfolio": "portfolio.html",
        "/portfolio/": "portfolio.html",
        "/portfolio.html": "portfolio.html",
    }
    filename = names.get(path)
    return os.path.join(legacy_dir, filename) if filename else None


def serve_file(handler, filepath: str, content_type: str = "text/html") -> None:
    """Serve a legacy file without changing the MVP static directory."""
    if not os.path.isfile(filepath):
        handler.send_response(404)
        handler.send_header("Content-Type", "text/plain")
        handler.end_headers()
        handler.wfile.write(b"Not Found")
        return
    with open(filepath, "rb") as f:
        body = f.read()
    handler.send_response(200)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(body)
