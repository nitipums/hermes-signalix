import json

import mvp_routes


class Handler:
    def __init__(self):
        self.status = None
        self.headers = []
        self.body = b""
        self.wfile = self

    def send_response(self, status): self.status = status
    def send_header(self, key, value): self.headers.append((key, value))
    def end_headers(self): pass
    def write(self, body): self.body += body


def test_vcp_route_rejects_non_60m_without_db():
    h = Handler()
    assert mvp_routes.handle_mvp_api("/api/vcp-finder?interval=1D", h) is True
    assert h.status == 400
    assert json.loads(h.body)["error"]


def test_vcp_route_evaluates_then_filters(monkeypatch):
    payload = {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "results": [{"symbol": "AAA", "state": "READY"}, {"symbol": "BBB", "state": "FORMING"}],
        "universe": {"eligible": 2, "evaluated": 2, "returned": 2},
    }
    class Conn:
        def close(self): pass
    monkeypatch.setattr(mvp_routes, "_vcp_pg", lambda: Conn())
    def latest(pg, market, state, symbol, limit, actionable):
        filtered = [r for r in payload["results"] if (not state or r["state"] == state) and (not actionable or r["state"] in {"READY", "NEAR_TRIGGER", "CONFIRMED"})]
        return {**payload, "results": filtered}
    monkeypatch.setattr("vcp_finder_db.load_latest_vcp_run", latest)
    h = Handler()
    assert mvp_routes.handle_mvp_api("/api/vcp-finder?state=READY", h) is True
    assert h.status == 200
    assert [x["symbol"] for x in json.loads(h.body)["results"]] == ["AAA"]
