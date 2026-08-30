import json
import threading
import time

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


def test_legacy_snapshot_is_not_disguised_as_canonical():
    import pytest
    with pytest.raises(ValueError, match="canonical"):
        from mvp_api import _setup_candidate_from_snapshot
        _setup_candidate_from_snapshot({"symbol": "LEGACY", "stage": "S2_uptrend"})


def test_data_source_calls_completed_engines_and_preserves_missing_60m(monkeypatch):
    import mvp_api
    import screening
    import instruments
    import pandas as pd

    daily = pd.DataFrame({"Open": [1.0] * 25, "High": [1.1] * 25,
                          "Low": [0.9] * 25, "Close": list(range(1, 26)),
                          "Volume": [10] * 25},
                         index=pd.date_range("2026-07-01", periods=25))
    calls = []
    monkeypatch.setattr(screening, "_active_scan_symbols", lambda *a, **k: ["AAA"])
    monkeypatch.setattr(mvp_api, "eligible_symbols", lambda active: (["AAA"], {
        "universe_filter": "marginable_long", "schema_version": "signalix.marginable.v1",
        "source_document": "test", "effective_date": "2026-08-25",
        "base_active_ord_count": 1, "eligible_count": 1, "excluded_count": 0,
    }))
    monkeypatch.setattr(instruments, "profile_taxonomy", lambda *a, **k: {
        "AAA": {"sector": "Technology", "industry": "Components"}})
    monkeypatch.setattr(screening, "load_market", lambda *a, **k: None)
    monkeypatch.setattr(screening, "_universe_rs_ranks", lambda *a, **k: {"AAA": 91})
    monkeypatch.setattr(screening, "load_symbol", lambda *a, **k: daily)
    monkeypatch.setattr(screening, "load_symbol_intraday", lambda *a, **k: None)
    original_wave = mvp_api.classify_wave_candidate
    original_setup = mvp_api.build_trade_setup
    monkeypatch.setattr(mvp_api, "classify_wave_candidate", lambda df, evidence: (calls.append("wave") or original_wave(df, evidence)))
    monkeypatch.setattr(mvp_api, "build_trade_setup", lambda wave, intra: (calls.append("setup") or original_setup(wave, intra)))

    rows, meta = mvp_api.build_setup_candidates_from_data(object())
    assert calls == ["wave", "setup"]
    item = rows[0]
    assert item["trend"]["rise_20d_pct"] is not None
    assert set(("near_52w_high", "is_52w_high_breakout", "is_ath_breakout")) <= item["trend"].keys()
    assert item["wave"]["timeframe"] == "daily"
    assert item["setup"]["timeframe"] == "60m"
    assert item["setup"]["status"] == "DATA_BLOCKED"
    assert item["context"]["sector"] == "Technology"
    assert "peer_symbols" in item["context"]
    assert item["bonus_evidence"]["vcp"]["source"] == "legacy_audit_only"
    assert meta["source"] == "price_data+intraday_price_data"


def test_setup_candidate_data_build_is_cached(monkeypatch):
    import mvp_routes
    calls = []

    def builder(pg, market="TH"):
        calls.append((pg, market))
        return [candidate("CACHED")], {"scan_time": "2026-08-30", "freshness": {"status": "fresh"}}

    mvp_routes.clear_setup_candidates_cache()
    pg = object()
    first = mvp_routes._load_setup_candidates_cached(builder, pg)
    second = mvp_routes._load_setup_candidates_cached(builder, pg)
    assert first is second
    assert len(calls) == 1
    mvp_routes.clear_setup_candidates_cache()


def test_setup_candidate_concurrent_build_is_single_flight():
    import mvp_routes
    calls = []
    barrier = threading.Barrier(3)

    def builder(pg, market="TH"):
        calls.append(1)
        time.sleep(0.05)
        return [candidate("SINGLE")], {"scan_time": "2026-08-30", "freshness": {"status": "fresh"}}

    mvp_routes.clear_setup_candidates_cache()
    results = []
    threads = [threading.Thread(target=lambda: (barrier.wait(), results.append(
        mvp_routes._load_setup_candidates_cached(builder, object())
    ))) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(calls) == 1
    assert len(results) == 3
    mvp_routes.clear_setup_candidates_cache()


def test_route_uses_data_source_when_snapshot_is_legacy(monkeypatch):
    row = candidate("REAL_SOURCE")
    calls = []
    class PG:
        def close(self):
            pass
    monkeypatch.setattr(mvp_routes, "load_payload", lambda: {"items": [{"symbol": "OLD", "stage": "S2_uptrend"}]})
    monkeypatch.setattr(mvp_routes, "_vcp_pg", PG)
    monkeypatch.setattr(mvp_routes, "json_response", lambda handler, data, status=200: calls.append((status, data)))
    monkeypatch.setattr("mvp_api.build_setup_candidates_from_data", lambda pg, market="TH": ([row], {"scan_time": "2026-08-30", "freshness": {}}))
    handler = Handler()
    assert mvp_routes.handle_mvp_api("/api/setup-candidates", handler)
    assert calls[0][0] == 200
    assert calls[0][1]["items"][0]["symbol"] == "REAL_SOURCE"
