import json
import threading
import time

import pytest

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


def candidate(symbol="ABC", *, decision_lane="REVIEW_NOW", sector="Technology"):
    return {
        "symbol": symbol, "as_of": "2026-08-30", "data_status": {"sufficient": True, "freshness": "fresh"},
        "trend": {"state": "uptrend", "relative_strength": 91},
        "wave": {"timeframe": "daily", "state": "EARLY_WAVE_3",
                  "primary_state": "EARLY_WAVE_3", "evidence": {}},
        "setup": {"timeframe": "60m", "state": "EARLY_WAVE_3", "status": "PRE_TRIGGER",
                  "trigger": 12, "invalidation": 10, "targets": [16], "rr": {"to_target_1": 3}},
        "context": {"sector": sector}, "bonus_evidence": {"vcp": {"present": False}},
        "decision_lane": decision_lane, "provenance": {
            "policy_version": "setup-candidates-v1", "source": "test",
            "as_of": "2026-08-30", "freshness": "fresh",
        },
    }


def test_setup_candidates_route_returns_canonical_items(monkeypatch):
    class PG:
        def close(self): pass
    monkeypatch.setattr(mvp_routes, "load_payload", lambda: {"items": [{"stage": "legacy"}]})
    monkeypatch.setattr(mvp_routes, "_vcp_pg", PG)
    monkeypatch.setattr("mvp_api.build_setup_candidates_from_data",
                        lambda pg, market="TH": ([candidate()], {
                            "scan_time": "2026-08-30", "freshness": {"status": "fresh"}}))
    handler = Handler()
    assert mvp_routes.handle_mvp_api("/api/setup-candidates", handler)
    assert handler.status == 200
    payload = json.loads(handler.body)
    assert payload["items"][0]["trend"]
    assert payload["items"][0]["wave"]
    assert payload["items"][0]["wave"]["state"] == "EARLY_WAVE_3"
    assert payload["items"][0]["setup"]
    assert payload["evaluated_count"] == 1


def test_route_never_uses_snapshot_as_canonical_source(monkeypatch):
    monkeypatch.setattr(mvp_routes, "load_payload", lambda: {
        "items": [candidate()], "scan_time": "2026-08-30",
        "freshness": {"status": "fresh"},
    })
    class PG:
        def close(self): pass
    monkeypatch.setattr(mvp_routes, "_vcp_pg", PG)
    monkeypatch.setattr(mvp_routes, "_setup_candidates_source_version", lambda pg: ("v1",))
    monkeypatch.setattr("mvp_api.build_setup_candidates_from_data",
                        lambda pg, market="TH": ([candidate("DATABASE")], {
                            "scan_time": "2026-08-30", "freshness": {"status": "fresh"}}))
    mvp_routes.clear_setup_candidates_cache()
    handler = Handler()
    assert mvp_routes.handle_mvp_api("/api/setup-candidates", handler)
    assert handler.status == 200
    assert json.loads(handler.body)["items"][0]["symbol"] == "DATABASE"
    mvp_routes.clear_setup_candidates_cache()


def test_setup_candidates_blocks_insufficient_data_and_keeps_non_vcp_row():
    row = candidate("NO_VCP", decision_lane="DATA_BLOCKED")
    row["data_status"] = {"sufficient": False, "freshness": "unknown"}
    row["bonus_evidence"] = {"vcp": {"present": False}}
    result = project_setup_candidates_response([row])
    assert result["items"][0]["decision_lane"] == "DATA_BLOCKED"
    assert result["items"][0]["bonus_evidence"]["vcp"]["present"] is False
    assert result["evaluated_count"] == 1


def test_setup_candidate_filters_are_presentation_only():
    result = project_setup_candidates_response([candidate(), candidate("XYZ", sector="Energy")], sector="Energy")
    assert [item["symbol"] for item in result["items"]] == ["XYZ"]
    assert result["evaluated_count"] == 2


def test_setup_candidates_default_page_is_compact_and_preserves_full_metadata():
    rows = [candidate(f"S{i:03d}", decision_lane="WAIT" if i % 2 else "REVIEW_NOW")
            for i in range(237)]
    for row in rows:
        row["wave"]["supporting_evidence"] = ["x" * 1000] * 10
        row["wave"]["contradicting_evidence"] = ["y" * 1000] * 10
    result = project_setup_candidates_response(rows, snapshot_meta={"eligible_count": 237})
    assert result["page_size"] == 50
    assert result["returned_count"] == 50
    assert result["evaluated_count"] == result["eligible_count"] == 237
    assert result["total_items"] == 237
    assert result["total_pages"] == 5
    assert sum(result["counts"].values()) == 237
    assert result["items"][0]["wave"]["supporting_evidence"]
    assert result["items"][0]["wave"]["contradicting_evidence"]
    assert "evidence" not in result["items"][0]["wave"]


def test_setup_candidates_page_count_is_page_return_count_not_universe_count():
    rows = [candidate(f"S{i:03d}") for i in range(237)]

    result = project_setup_candidates_response(
        rows, page=1, page_size=100,
        snapshot_meta={"eligible_count": 237, "universe_filter": "marginable_long"},
    )

    assert len(result["items"]) == 100
    assert result["returned_count"] == 100
    assert result["evaluated_count"] == 237
    assert result["eligible_count"] == 237
    assert result["total_items"] == 237
    assert result["total_pages"] == 3
    assert result["diagnostic"]["returned_count"] == 100


def test_missing_benchmark_history_leaves_relative_strength_unknown(monkeypatch):
    import mvp_api

    assert mvp_api._relative_strength_ranks(
        {"AAA": object()}, None
    ) == {}

    # Legacy fallback zeroes are not an observed percentile either.
    assert mvp_api._number(0.0) == 0.0


def test_setup_candidates_diagnostic_covers_all_evaluated_rows_not_page():
    daily_missing = candidate("DAILY_MISSING")
    daily_missing["data_status"] = {
        "sufficient": False, "daily_available": False, "daily_final_session_available": False,
        "freshness": "unknown", "reason_code": "NO_DAILY_DATA",
    }
    daily_missing["decision_lane"] = "DATA_BLOCKED"
    intraday_missing = candidate("INTRADAY_MISSING")
    intraday_missing["data_status"] = {
        "sufficient": False, "daily_available": True, "daily_final_session_available": True,
        "intraday_60m_available": False, "intraday_60m_freshness": "unknown", "freshness": "unknown",
        "reason_code": "NO_60M_DATA",
    }
    intraday_missing["decision_lane"] = "DATA_BLOCKED"
    stale = candidate("STALE")
    stale["data_status"] = {"sufficient": False, "freshness": "stale", "daily_available": True,
                             "daily_final_session_available": True, "intraday_60m_available": True,
                             "intraday_60m_freshness": "stale", "reason_code": "STALE_60M_DATA"}
    stale["decision_lane"] = "DATA_BLOCKED"
    no_setup = candidate("NO_SETUP")
    no_setup["setup"] = {"timeframe": "60m", "status": "FORMING",
                          "reason_code": "NO_SETUP_DETECTED", "trigger": None,
                          "invalidation": None, "targets": [], "rr": {"to_target_1": None}}
    no_setup["decision_lane"] = "DAILY_CANDIDATE"
    bad_risk = candidate("BAD_RISK")
    bad_risk["setup"] = {**bad_risk["setup"], "status": "INVALIDATED",
                          "risk_status": "INVALID", "reason_code": "RISK_INVALID",
                          "reason": "display text without classification tokens"}
    bad_risk["decision_lane"] = "AVOID"

    result = project_setup_candidates_response(
        [daily_missing, intraday_missing, stale, no_setup, bad_risk], page=1, page_size=2,
        snapshot_meta={"scan_time": "2026-08-30", "universe_filter": "marginable_long",
                       "eligible_count": 5},
    )
    diagnostic = result["diagnostic"]
    assert diagnostic["as_of"] == "2026-08-30"
    assert diagnostic["universe"] == "marginable_long"
    assert diagnostic["evaluated_count"] == 5
    assert diagnostic["returned_count"] == 2
    assert diagnostic["decision_lane_totals"]["DATA_BLOCKED"] == 3
    assert diagnostic["daily_unavailable"] == {"count": 1, "symbols": ["DAILY_MISSING"]}
    assert diagnostic["intraday_60m_unavailable"] == {"count": 1, "symbols": ["INTRADAY_MISSING"]}
    assert diagnostic["stale_invalid_evidence"] == {"count": 1, "symbols": ["STALE"]}
    assert diagnostic["no_setup_detected"] == {"count": 1, "symbols": ["NO_SETUP"]}
    assert diagnostic["invalid_risk_fib"] == {"count": 1, "symbols": ["BAD_RISK"]}


def test_legacy_snapshot_is_not_disguised_as_canonical():
    import pytest
    with pytest.raises(ValueError, match="canonical"):
        from mvp_api import _setup_candidate_from_snapshot
        _setup_candidate_from_snapshot({"symbol": "LEGACY", "stage": "S2_uptrend"})


def test_canonical_snapshot_rejects_competing_legacy_decision_alias():
    import pytest
    from mvp_api import _setup_candidate_from_snapshot

    row = candidate()
    row["decision"] = "BUY"
    with pytest.raises(ValueError, match="legacy decision"):
        _setup_candidate_from_snapshot(row)


def test_canonical_projection_does_not_call_snapshot_compatibility_adapter(monkeypatch):
    import mvp_api

    monkeypatch.setattr(
        mvp_api, "_setup_candidate_from_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("canonical projection used snapshot compatibility adapter")
        ),
    )
    result = mvp_api.project_setup_candidates_response([candidate("DIRECT")])
    assert result["items"][0]["symbol"] == "DIRECT"


def test_canonical_snapshot_rejects_positive_lane_for_blocked_data():
    import pytest
    from mvp_api import _setup_candidate_from_snapshot

    row = candidate()
    row["data_status"] = {"sufficient": False, "freshness": "stale"}
    with pytest.raises(ValueError, match="fail-closed"):
        _setup_candidate_from_snapshot(row)


def test_canonical_snapshot_requires_exact_envelope_and_complete_provenance():
    import pytest
    from mvp_api import _setup_candidate_from_snapshot

    extra = candidate()
    extra["lane"] = "REVIEW"
    with pytest.raises(ValueError, match="exact canonical envelope"):
        _setup_candidate_from_snapshot(extra)

    incomplete = candidate()
    incomplete["provenance"] = {"policy_version": "setup-candidates-v1"}
    with pytest.raises(ValueError, match="provenance"):
        _setup_candidate_from_snapshot(incomplete)


def test_data_source_calls_completed_engines_and_preserves_missing_60m(monkeypatch):
    import mvp_api
    import screening
    import instruments
    import pandas as pd

    closes = [10.0 + i / 10 for i in range(25)]
    daily = pd.DataFrame({"Open": closes, "High": [value + 0.1 for value in closes],
                          "Low": [value - 0.1 for value in closes], "Close": closes,
                          "Volume": [10] * 25},
                         index=pd.date_range("2026-07-01", periods=25))
    calls = []
    monkeypatch.setattr(mvp_api, "expected_market_date", lambda: daily.index[-1].date())
    monkeypatch.setattr(instruments, "active_ord_symbols", lambda pg: ["AAA"])
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
    original_wave = mvp_api.build_wave_contract
    original_setup = mvp_api.build_trade_setup
    monkeypatch.setattr(mvp_api, "build_wave_contract", lambda df, evidence: (calls.append("wave") or original_wave(df, evidence)))
    monkeypatch.setattr(mvp_api, "build_trade_setup", lambda wave, intra: (calls.append("setup") or original_setup(wave, intra)))

    rows, meta = mvp_api.build_setup_candidates_from_data(object())
    assert calls == ["wave", "setup"]
    item = rows[0]
    assert item["trend"]["rise_20d_pct"] is not None
    assert set(("near_52w_high", "is_52w_high_breakout", "is_ath_breakout")) <= item["trend"].keys()
    assert item["wave"]["timeframe"] == "daily"
    assert item["setup"]["timeframe"] == "60m"
    assert item["setup"]["status"] == "DATA_BLOCKED"
    assert item["data_status"]["reason_code"] == "NO_60M_DATA"
    assert item["decision_lane"] == "DATA_BLOCKED"
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
    assert first is not second
    assert first["cache_status"] == "cold"
    assert second["cache_status"] == "warm"
    assert first["scan_time"] == second["scan_time"] == "2026-08-30"
    assert first["build_observability"]["cache_status"] == "cold"
    assert second["build_observability"]["cache_status"] == "warm"
    assert len(calls) == 1
    mvp_routes.clear_setup_candidates_cache()


def test_setup_candidate_cold_and_warm_latency_budget_is_deterministic(monkeypatch):
    monkeypatch.setattr(mvp_routes, "_setup_candidates_source_version", lambda pg: ("stable",))

    def builder(pg, market="TH"):
        time.sleep(0.05)
        return [candidate("TIMED")], {"scan_time": "2026-08-30"}

    mvp_routes.clear_setup_candidates_cache()
    started = time.monotonic()
    mvp_routes._load_setup_candidates_cached(builder, object())
    cold_seconds = time.monotonic() - started
    started = time.monotonic()
    mvp_routes._load_setup_candidates_cached(builder, object())
    warm_seconds = time.monotonic() - started
    assert cold_seconds < 3.0
    assert warm_seconds < 0.5
    assert warm_seconds < cold_seconds
    mvp_routes.clear_setup_candidates_cache()


def test_setup_candidate_cache_expires_immediately_after_ingestion(monkeypatch):
    versions = iter([("daily-1", "intra-1"), ("daily-1", "intra-1"),
                     ("daily-1", "intra-2")])
    monkeypatch.setattr(mvp_routes, "_setup_candidates_source_version", lambda pg: next(versions))
    calls = []

    def builder(pg, market="TH"):
        calls.append(1)
        return [candidate("VERSIONED")], {"scan_time": "2026-08-30"}

    mvp_routes.clear_setup_candidates_cache()
    cold = mvp_routes._load_setup_candidates_cached(builder, object())
    warm = mvp_routes._load_setup_candidates_cached(builder, object())
    refreshed = mvp_routes._load_setup_candidates_cached(builder, object())
    assert cold is not warm
    assert cold["cache_status"] == "cold"
    assert warm["cache_status"] == "warm"
    assert refreshed is not warm
    assert len(calls) == 2
    mvp_routes.clear_setup_candidates_cache()


def test_build_exposes_stage_timing_and_bounded_bulk_query_count(monkeypatch):
    import mvp_api
    import screening
    monkeypatch.setattr(mvp_api, "resolve_universe", lambda pg, universe: ([], {
        "universe_filter": "marginable_long", "eligible_count": 0}))
    monkeypatch.setattr(mvp_api.instruments, "profile_taxonomy", lambda *a, **k: {})
    monkeypatch.setattr(screening, "load_market", lambda *a, **k: None)
    rows, meta = mvp_api.build_setup_candidates_from_data(object())
    assert rows == []
    observed = meta["build_observability"]
    assert observed["duration_ms"] >= 0
    assert set(observed["stages_ms"]) == {"source_context", "ohlcv_load", "candidate_evaluation"}
    assert observed["ohlcv_query_count"] == 0


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
    assert sorted(result["cache_status"] for result in results) == [
        "cold", "single_flight", "single_flight"
    ]
    for result in results:
        assert result["scan_time"] == "2026-08-30"
        assert result["build_observability"]["duration_ms"] >= 0
        assert result["build_observability"]["request_duration_ms"] >= 0
    assert all(
        result["build_observability"].get("single_flight_wait_ms", 0) > 0
        for result in results if result["cache_status"] == "single_flight"
    )
    mvp_routes.clear_setup_candidates_cache()


def test_setup_candidate_response_keeps_page_totals_lanes_and_observability_consistent():
    rows = [candidate(f"S{i:03d}", decision_lane=("REVIEW_NOW" if i < 2 else "WAIT"))
            for i in range(3)]
    meta = {
        "scan_time": "2026-08-30", "freshness": {"status": "fresh"},
        "universe_filter": "marginable_long", "cache_status": "single_flight",
        "build_observability": {
            "duration_ms": 12.5, "stages_ms": {"source_context": 1.0,
            "ohlcv_load": 2.0, "candidate_evaluation": 3.0}, "ohlcv_query_count": 4,
            "cache_status": "single_flight", "request_duration_ms": 14.0,
            "single_flight_wait_ms": 10.0,
        },
    }
    result = project_setup_candidates_response(rows, snapshot_meta=meta, page=2, page_size=2)
    assert result["page"] == 2 and result["page_size"] == 2
    assert result["returned_count"] == 1
    assert result["total_items"] == result["evaluated_count"] == 3
    assert result["total_pages"] == 2
    assert result["counts"]["REVIEW_NOW"] == 2 and result["counts"]["WAIT"] == 1
    assert result["cache_status"] == "single_flight"
    assert result["build_observability"]["ohlcv_query_count"] == 4
    assert result["build_observability"]["request_duration_ms"] == 14.0


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


def test_missing_final_daily_session_is_blocked(monkeypatch):
    import mvp_api
    import pandas as pd
    daily = pd.DataFrame({"Close": [float(i) for i in range(25)]},
                         index=pd.date_range("2026-08-01", periods=25))
    monkeypatch.setattr(mvp_api, "expected_market_date", lambda: pd.Timestamp("2026-08-31").date())
    monkeypatch.setattr(mvp_api.instruments, "active_ord_symbols", lambda pg: ["AAA"])
    monkeypatch.setattr(mvp_api.instruments, "profile_taxonomy", lambda *a, **k: {})
    monkeypatch.setattr(mvp_api, "eligible_symbols", lambda active: (["AAA"], {
        "universe_filter": "marginable_long", "schema_version": "test",
        "source_document": "test", "effective_date": "2026-08-25",
        "base_active_ord_count": 1, "eligible_count": 1, "excluded_count": 0}))
    monkeypatch.setattr(mvp_api, "_load_daily_for_symbol", lambda *a, **k: daily)
    monkeypatch.setattr(mvp_api, "_load_intraday_for_symbol", lambda *a, **k: None)
    import screening
    monkeypatch.setattr(screening, "load_market", lambda *a, **k: None)
    monkeypatch.setattr(screening, "_universe_rs_ranks", lambda *a, **k: {})
    rows, _ = mvp_api.build_setup_candidates_from_data(object())
    assert rows[0]["decision_lane"] == "DATA_BLOCKED"
    assert rows[0]["wave"]["primary_state"] == "UNKNOWN"


def test_builder_missing_daily_is_explicitly_blocked(monkeypatch):
    import mvp_api
    import screening
    monkeypatch.setattr(mvp_api, "expected_market_date", lambda: __import__("datetime").date(2026, 8, 31))
    monkeypatch.setattr(mvp_api.instruments, "active_ord_symbols", lambda pg: ["AAA"])
    monkeypatch.setattr(mvp_api.instruments, "profile_taxonomy", lambda *a, **k: {})
    monkeypatch.setattr(mvp_api, "eligible_symbols", lambda active: (["AAA"], {
        "universe_filter": "marginable_long", "eligible_count": 1}))
    monkeypatch.setattr(screening, "load_market", lambda *a, **k: None)
    monkeypatch.setattr(screening, "_universe_rs_ranks", lambda *a, **k: {})
    monkeypatch.setattr(mvp_api, "_load_daily_for_symbol", lambda *a, **k: None)
    monkeypatch.setattr(mvp_api, "_load_intraday_for_symbol", lambda *a, **k: None)

    rows, _ = mvp_api.build_setup_candidates_from_data(object())

    assert rows[0]["data_status"]["reason_codes"] == ["NO_DAILY_DATA", "NO_60M_DATA"]
    assert rows[0]["decision_lane"] == "DATA_BLOCKED"


def test_builder_malformed_unsorted_daily_fails_closed(monkeypatch):
    import mvp_api
    import screening
    import pandas as pd
    dates = pd.to_datetime(["2026-08-30", "2026-08-29", "2026-08-31"])
    daily = pd.DataFrame({"Open": [10.0, 11.0, 12.0], "High": [11.0, 12.0, 13.0],
                          "Low": [9.0, 10.0, 11.0], "Close": [10.5, 11.5, 12.5],
                          "Volume": [100, 100, 100]}, index=dates)
    monkeypatch.setattr(mvp_api, "expected_market_date", lambda: dates[-1].date())
    monkeypatch.setattr(mvp_api.instruments, "active_ord_symbols", lambda pg: ["AAA"])
    monkeypatch.setattr(mvp_api.instruments, "profile_taxonomy", lambda *a, **k: {})
    monkeypatch.setattr(mvp_api, "eligible_symbols", lambda active: (["AAA"], {
        "universe_filter": "marginable_long", "eligible_count": 1}))
    monkeypatch.setattr(screening, "load_market", lambda *a, **k: None)
    monkeypatch.setattr(screening, "_universe_rs_ranks", lambda *a, **k: {})
    monkeypatch.setattr(mvp_api, "_load_daily_for_symbol", lambda *a, **k: daily)
    monkeypatch.setattr(mvp_api, "_load_intraday_for_symbol", lambda *a, **k: None)

    rows, _ = mvp_api.build_setup_candidates_from_data(object())

    assert rows[0]["data_status"]["reason_code"] == "INVALID_DAILY_OHLCV"
    assert rows[0]["data_status"]["reason_codes"] == ["INVALID_DAILY_OHLCV", "NO_60M_DATA"]
    assert rows[0]["decision_lane"] == "DATA_BLOCKED"


def test_builder_diagnostic_keeps_simultaneous_daily_and_60m_missing_observable(monkeypatch):
    import mvp_api
    import screening
    monkeypatch.setattr(mvp_api, "expected_market_date", lambda: __import__("datetime").date(2026, 8, 31))
    monkeypatch.setattr(mvp_api.instruments, "active_ord_symbols", lambda pg: ["AAA"])
    monkeypatch.setattr(mvp_api.instruments, "profile_taxonomy", lambda *a, **k: {})
    monkeypatch.setattr(mvp_api, "eligible_symbols", lambda active: (["AAA"], {
        "universe_filter": "marginable_long", "eligible_count": 1}))
    monkeypatch.setattr(screening, "load_market", lambda *a, **k: None)
    monkeypatch.setattr(screening, "_universe_rs_ranks", lambda *a, **k: {})
    monkeypatch.setattr(mvp_api, "_load_daily_for_symbol", lambda *a, **k: None)
    monkeypatch.setattr(mvp_api, "_load_intraday_for_symbol", lambda *a, **k: None)

    rows, _ = mvp_api.build_setup_candidates_from_data(object())
    diagnostic = mvp_api.build_setup_candidate_diagnostic(
        rows, as_of=None, universe="marginable_long", returned_count=1
    )

    assert diagnostic["daily_unavailable"] == {"count": 1, "symbols": ["AAA"]}
    assert diagnostic["intraday_60m_unavailable"] == {"count": 1, "symbols": ["AAA"]}


@pytest.mark.parametrize("timeframe", [None, "15m"])
def test_wrong_or_untagged_intraday_interval_is_blocked(monkeypatch, timeframe):
    import mvp_api
    import pandas as pd
    closes = [10.0 + i / 10 for i in range(25)]
    daily = pd.DataFrame({"Open": closes, "High": [value + 0.1 for value in closes],
                          "Low": [value - 0.1 for value in closes], "Close": closes,
                          "Volume": [100] * 25},
                         index=pd.date_range("2026-08-01", periods=25))
    intraday = pd.DataFrame({"Close": [1.0, 1.1, 1.2]},
                            index=pd.date_range("2026-08-31", periods=3, freq="15min"))
    if timeframe is not None:
        intraday.attrs["timeframe"] = timeframe
    monkeypatch.setattr(mvp_api, "expected_market_date", lambda: daily.index[-1].date())
    monkeypatch.setattr(mvp_api.instruments, "active_ord_symbols", lambda pg: ["AAA"])
    monkeypatch.setattr(mvp_api.instruments, "profile_taxonomy", lambda *a, **k: {})
    monkeypatch.setattr(mvp_api, "eligible_symbols", lambda active: (["AAA"], {
        "universe_filter": "marginable_long", "schema_version": "test",
        "source_document": "test", "effective_date": "2026-08-25",
        "base_active_ord_count": 1, "eligible_count": 1, "excluded_count": 0}))
    monkeypatch.setattr(mvp_api, "_load_daily_for_symbol", lambda *a, **k: daily)
    monkeypatch.setattr(mvp_api, "_load_intraday_for_symbol", lambda *a, **k: intraday)
    import screening
    monkeypatch.setattr(screening, "load_market", lambda *a, **k: None)
    monkeypatch.setattr(screening, "_universe_rs_ranks", lambda *a, **k: {})
    rows, _ = mvp_api.build_setup_candidates_from_data(object())
    assert rows[0]["setup"]["status"] == "DATA_BLOCKED"
    assert rows[0]["data_status"]["reason_code"] == "INVALID_60M_OHLCV"
    assert rows[0]["decision_lane"] == "DATA_BLOCKED"


def test_loader_preserves_explicit_intraday_timeframe_and_accepts_60m(monkeypatch):
    import mvp_api
    import pandas as pd

    def load(*args, **kwargs):
        frame = pd.DataFrame({"Close": [1.0, 1.1, 1.2]},
                             index=pd.date_range("2026-08-31", periods=3, freq="60min"))
        frame.attrs["timeframe"] = "60m"
        return frame

    class Screening:
        load_symbol_intraday = staticmethod(load)

    frame = mvp_api._load_intraday_for_symbol(Screening, "AAA", object(), "TH")
    assert frame.attrs["timeframe"] == "60m"
    available, current, freshness, _ = mvp_api._intraday_60m_status(
        frame, frame.index[-1].to_pydatetime().replace(tzinfo=None)
    )
    assert available is True
    assert current is True
    assert freshness == "fresh"


def test_intraday_loader_stamps_requested_timeframe_and_last_timestamp():
    import pandas as pd
    import screening

    timestamps = pd.to_datetime(["2026-08-31 11:00", "2026-08-31 10:00"])

    class Cursor:
        def execute(self, *_args): pass
        def fetchall(self):
            return [
                (timestamps[0], 10.0, 10.5, 9.9, 10.3, 1000),
                (timestamps[1], 9.8, 10.2, 9.7, 10.0, 900),
            ]
        def close(self): pass

    class PG:
        def cursor(self): return Cursor()

    frame = screening.load_symbol_intraday(
        "AAA", pg=PG(), interval="60m", lookback=400,
    )

    assert frame.attrs["timeframe"] == "60m"
    assert frame.attrs["as_of"] == frame.index[-1]


def test_prior_completed_session_is_current_before_eod_cutoff(monkeypatch):
    import datetime as dt
    import mvp_api
    import pandas as pd
    import screening

    daily = pd.DataFrame({
        "Open": [10.0] * 25, "High": [11.0 + i / 10 for i in range(25)],
        "Low": [9.0] * 25, "Close": [10.0 + i / 10 for i in range(25)],
        "Volume": [1000] * 25,
    }, index=pd.bdate_range(end="2026-08-28", periods=25))
    intraday = pd.DataFrame({
        "Open": [10.0] * 3, "High": [10.5] * 3, "Low": [9.8] * 3,
        "Close": [10.1, 10.2, 10.3], "Volume": [100] * 3,
    }, index=pd.date_range("2026-08-31 14:00", periods=3, freq="60min"))
    intraday.attrs["timeframe"] = "60m"

    monkeypatch.setattr(mvp_api, "expected_market_date", lambda: dt.date(2026, 8, 28), raising=False)
    monkeypatch.setattr(mvp_api, "_expected_intraday_interval_start",
                        lambda: dt.datetime(2026, 8, 31, 14, 0), raising=False)
    monkeypatch.setattr(mvp_api.instruments, "active_ord_symbols", lambda pg: ["AAA"])
    monkeypatch.setattr(mvp_api.instruments, "profile_taxonomy", lambda *a, **k: {})
    monkeypatch.setattr(mvp_api, "eligible_symbols", lambda active: (["AAA"], {
        "universe_filter": "marginable_long", "schema_version": "test",
        "source_document": "test", "effective_date": "2026-08-25",
        "base_active_ord_count": 1, "eligible_count": 1, "excluded_count": 0}))
    monkeypatch.setattr(mvp_api, "_load_daily_for_symbol", lambda *a, **k: daily)
    monkeypatch.setattr(mvp_api, "_load_intraday_for_symbol", lambda *a, **k: intraday)
    monkeypatch.setattr(screening, "load_market", lambda *a, **k: None)
    monkeypatch.setattr(screening, "_universe_rs_ranks", lambda *a, **k: {})
    monkeypatch.setattr(mvp_api, "compute_trend_strength", lambda *a, **k: {"state": "uptrend"})
    monkeypatch.setattr(mvp_api, "build_wave_contract", lambda *a, **k: {
        "primary_state": "WAVE_1_ADVANCE", "alternative_state": "WAVE_2_FORMING",
        "confidence": "MEDIUM", "supporting_evidence": [],
        "contradicting_evidence": [], "missing_evidence": [], "evidence": {}})
    monkeypatch.setattr(mvp_api, "build_trade_setup", lambda *a, **k: {
        "timeframe": "60m", "status": "FORMING"})

    rows, _ = mvp_api.build_setup_candidates_from_data(object())
    item = rows[0]
    assert item["data_status"]["daily_final_session_available"] is True
    assert item["decision_lane"] == "DAILY_CANDIDATE"
    assert item["provenance"]["freshness"] == "fresh"
    assert item["provenance"]["source"] == "price_data+intraday_price_data"
    assert item["provenance"]["as_of"].startswith("2026-08-28")


def test_stale_60m_session_fails_closed(monkeypatch):
    import datetime as dt
    import mvp_api
    import pandas as pd
    import screening

    daily = pd.DataFrame({
        "Open": [10.0] * 25, "High": [11.0 + i / 10 for i in range(25)],
        "Low": [9.0] * 25, "Close": [10.0 + i / 10 for i in range(25)],
        "Volume": [1000] * 25,
    }, index=pd.bdate_range(end="2026-08-28", periods=25))
    stale_intraday = pd.DataFrame({
        "Open": [10.0] * 3, "High": [10.5] * 3, "Low": [9.8] * 3,
        "Close": [10.1, 10.2, 10.3], "Volume": [100] * 3,
    }, index=pd.date_range("2026-08-31 12:00", periods=3, freq="60min"))
    stale_intraday.attrs["timeframe"] = "60m"

    monkeypatch.setattr(mvp_api, "expected_market_date", lambda: dt.date(2026, 8, 28))
    monkeypatch.setattr(mvp_api, "_expected_intraday_interval_start",
                        lambda: dt.datetime(2026, 8, 31, 16, 0), raising=False)
    monkeypatch.setattr(mvp_api.instruments, "active_ord_symbols", lambda pg: ["AAA"])
    monkeypatch.setattr(mvp_api.instruments, "profile_taxonomy", lambda *a, **k: {})
    monkeypatch.setattr(mvp_api, "eligible_symbols", lambda active: (["AAA"], {
        "universe_filter": "marginable_long", "schema_version": "test",
        "source_document": "test", "effective_date": "2026-08-25",
        "base_active_ord_count": 1, "eligible_count": 1, "excluded_count": 0}))
    monkeypatch.setattr(mvp_api, "_load_daily_for_symbol", lambda *a, **k: daily)
    monkeypatch.setattr(mvp_api, "_load_intraday_for_symbol", lambda *a, **k: stale_intraday)
    monkeypatch.setattr(screening, "load_market", lambda *a, **k: None)
    monkeypatch.setattr(screening, "_universe_rs_ranks", lambda *a, **k: {})
    monkeypatch.setattr(mvp_api, "compute_trend_strength", lambda *a, **k: {"state": "uptrend"})
    monkeypatch.setattr(mvp_api, "build_wave_contract", lambda *a, **k: {
        "primary_state": "WAVE_1_ADVANCE", "alternative_state": "WAVE_2_FORMING",
        "confidence": "MEDIUM", "supporting_evidence": [],
        "contradicting_evidence": [], "missing_evidence": [], "evidence": {}})
    monkeypatch.setattr(mvp_api, "build_trade_setup", lambda *a, **k: {
        "timeframe": "60m", "status": "READY"})

    rows, _ = mvp_api.build_setup_candidates_from_data(object())
    item = rows[0]
    assert item["data_status"]["intraday_60m_freshness"] == "stale"
    assert item["data_status"]["reason_code"] == "STALE_60M_DATA"
    assert item["setup"]["status"] == "DATA_BLOCKED"
    assert item["decision_lane"] == "DATA_BLOCKED"


def test_expected_intraday_session_respects_opening_weekend_and_set_holiday():
    import datetime as dt
    from zoneinfo import ZoneInfo
    from mvp_api import _expected_intraday_interval_start, _expected_intraday_session_date

    utc = dt.timezone.utc
    assert _expected_intraday_session_date(
        dt.datetime(2026, 8, 31, 2, 0, tzinfo=utc)
    ) == dt.date(2026, 8, 28)  # Monday 09:00 ICT: no current-session bar yet.
    assert _expected_intraday_session_date(
        dt.datetime(2026, 8, 31, 3, 15, tzinfo=utc)
    ) == dt.date(2026, 8, 31)  # Monday 10:15 ICT.
    assert _expected_intraday_session_date(
        dt.datetime(2026, 8, 29, 8, 0, tzinfo=utc)
    ) == dt.date(2026, 8, 28)  # Saturday.
    assert _expected_intraday_session_date(
        dt.datetime(2026, 8, 12, 8, 0, tzinfo=utc)
    ) == dt.date(2026, 8, 11)  # Known SET holiday.
    assert _expected_intraday_interval_start(
        dt.datetime(2026, 8, 31, 3, 15, tzinfo=utc)
    ) == dt.datetime(2026, 8, 28, 16, 0, tzinfo=ZoneInfo("Asia/Bangkok"))


def test_untagged_intraday_dataframe_is_not_assumed_to_be_60m():
    import datetime as dt
    import pandas as pd
    from mvp_api import _intraday_60m_status

    frame = pd.DataFrame({"Close": [1.0, 1.1, 1.2]},
                         index=pd.date_range("2026-08-31 14:00", periods=3, freq="60min"))
    available, current, freshness, as_of = _intraday_60m_status(
        frame, dt.datetime(2026, 8, 31, 14, 0)
    )
    assert (available, current, freshness, as_of) == (False, False, "unknown", None)
