import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probe_shortlist.sh"


def _payload():
    results = [
        {"symbol": "AAA", "state": "READY"},
        {"symbol": "BBB", "state": "READY"},
        {"symbol": "CCC", "state": "READY"},
        {"symbol": "DDD", "state": "STALE"},
    ]
    return {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "run_id": "vcp-test-run",
        "as_of": "2026-08-28T11:13:05+00:00",
        "universe": {"eligible": 4, "evaluated": 4, "returned": 4},
        "coverage": {"feed_unavailable": 1, "no_data": 0},
        "results": results,
        "daily_watchlist": {
            "counts": {"ACTION_REVIEW": 0, "NEAR_TRIGGER": 0, "BREAKOUT_WATCH": 1},
            "action_review": [],
            "near_trigger": [],
            "breakout_watch": [{"symbol": "AAA"}],
        },
    }


def _serve(retired_dashboard_status=404):
    payload = _payload()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health/readiness":
                body = json.dumps({"status": "ok", "db": "ok", "redis": "ok"}).encode()
                status, content_type = 200, "application/json"
            elif self.path.startswith("/api/vcp-finder?"):
                body_payload = payload
                if "daily_watchlist=true" in self.path:
                    body_payload = {**payload, "results": [], "daily_watchlist": payload["daily_watchlist"]}
                body = json.dumps(body_payload).encode()
                status, content_type = 200, "application/json"
            elif self.path == "/mvp":
                body = b"<!doctype html><title>Signalix VCP Finder</title>"
                status, content_type = 200, "text/html"
            elif self.path == "/dashboard.html":
                body = b"retired"
                status, content_type = retired_dashboard_status, "text/plain"
            elif self.path == "/api/symbol/___SIGNALIX_PROBE_MISSING___":
                body = json.dumps({"error": "symbol not found"}).encode()
                status, content_type = 404, "application/json"
            else:
                body = b"not found"
                status, content_type = 404, "text/plain"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _run_probe(tmp_path, server):
    host = f"http://127.0.0.1:{server.server_port}"
    env = os.environ.copy()
    env["SIGNALIX_BACKEND_URL"] = host
    env["SIGNALIX_DASHBOARD_URL"] = host
    return subprocess.run(
        [str(SCRIPT), str(tmp_path)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_probe_uses_canonical_vcp_contract_and_writes_nonempty_artifacts(tmp_path):
    server = _serve()
    try:
        result = _run_probe(tmp_path, server)
    finally:
        server.shutdown()
        server.server_close()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "READY count: 3" in result.stdout
    assert "evaluated: 4" in result.stdout
    for name in ("readiness.json", "daily_vcp.json", "vcp.json", "mvp.html", "missing_symbol.json", "probe_report.json"):
        artifact = tmp_path / name
        assert artifact.is_file()
        assert artifact.stat().st_size > 0
    report = json.loads((tmp_path / "probe_report.json").read_text())
    assert report["run_id"] == "vcp-test-run"
    assert report["universe"] == {"eligible": 4, "evaluated": 4, "returned": 4}
    assert report["state_counts"]["READY"] == 3


def test_probe_fails_if_retired_dashboard_is_served(tmp_path):
    server = _serve(retired_dashboard_status=200)
    try:
        result = _run_probe(tmp_path, server)
    finally:
        server.shutdown()
        server.server_close()

    assert result.returncode != 0
    assert "dashboard.html must return 404" in (result.stdout + result.stderr)
