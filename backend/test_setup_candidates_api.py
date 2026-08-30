import json

import mvp_routes
from mvp_api import project_setup_candidates_response


class Handler:
    def __init__(self):
        self.status = None
        self.body = b""
        self.wfile = self

    def send_response(self, status): self.status = status
    def send_header(self, *_): pass
    def end_headers(self): pass
    def write(self, body): self.body += body


def candidate(symbol="ABC", *, decision="REVIEW", sector="Technology"):
    return {
        "symbol": symbol, "as_of": "2026-08-30", "data_status": {"sufficient": True, "freshness": "fresh"},
        "trend": {"state": "uptrend", "relative_strength": 91},
        "wave": {"timeframe": "daily", "state": "EARLY_WAVE_3", "evidence": {}},
        "setup": {"timeframe": "60m", "state": "EARLY_WAVE_3", "status": "READY", "rr": {"to_target_1": 3}},
        "context": {"sector": sector}, "bonus_evidence": {"vcp": {"present": False}},
        "decision": decision, "provenance": {"policy_version": "setup-candidates-v1"},
    }


def test_setup_candidates_route_returns_canonical_items(monkeypatch):
    monkeypatch.setattr(mvp_routes, "load_payload", lambda: {"items": [candidate()], "scan_time": "2026-08-30", "freshness": {"status": "fresh"}})
    handler = Handler()
    assert mvp_routes.handle_mvp_api("/api/setup-candidates", handler)
    assert handler.status == 200
    payload = json.loads(handler.body)
    assert payload["items"][0]["trend"]
    assert payload["items"][0]["wave"]
    assert payload["items"][0]["setup"]
    assert payload["evaluated_count"] == 1


def test_setup_candidates_blocks_insufficient_data_and_keeps_non_vcp_row():
    row = candidate("NO_VCP", decision="DATA_BLOCKED")
    row["data_status"] = {"sufficient": False, "freshness": "unknown"}
    row["bonus_evidence"] = {"vcp": {"present": False}}
    result = project_setup_candidates_response([row])
    assert result["items"][0]["decision"] == "DATA_BLOCKED"
    assert result["items"][0]["bonus_evidence"]["vcp"]["present"] is False
    assert result["evaluated_count"] == 1


def test_setup_candidate_filters_are_presentation_only():
    result = project_setup_candidates_response([candidate(), candidate("XYZ", sector="Energy")], sector="Energy")
    assert [item["symbol"] for item in result["items"]] == ["XYZ"]
    assert result["evaluated_count"] == 2
