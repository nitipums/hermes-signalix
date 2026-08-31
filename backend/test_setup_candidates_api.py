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


def test_route_serves_canonical_snapshot_without_legacy_db_fallback(monkeypatch):
    monkeypatch.setattr(mvp_routes, "load_payload", lambda: {
        "items": [candidate()], "scan_time": "2026-08-30",
        "freshness": {"status": "fresh"},
    })
    monkeypatch.setattr(
        mvp_routes, "_vcp_pg",
        lambda: (_ for _ in ()).throw(AssertionError("canonical snapshot must not fallback")),
    )
    handler = Handler()
    assert mvp_routes.handle_mvp_api("/api/setup-candidates", handler)
    assert handler.status == 200
    assert json.loads(handler.body)["items"][0]["decision_lane"] == "REVIEW_NOW"


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

    daily = pd.DataFrame({"Open": [1.0] * 25, "High": [1.1] * 25,
                          "Low": [0.9] * 25, "Close": list(range(1, 26)),
                          "Volume": [10] * 25},
                         index=pd.date_range("2026-07-01", periods=25))
    calls = []
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


def test_wrong_intraday_interval_is_blocked(monkeypatch):
    import mvp_api
    import pandas as pd
    daily = pd.DataFrame({"Close": [float(i) for i in range(25)]},
                         index=pd.date_range("2026-08-01", periods=25))
    intraday = pd.DataFrame({"Close": [1.0, 1.1, 1.2]},
                            index=pd.date_range("2026-08-31", periods=3, freq="15min"))
    intraday.attrs["timeframe"] = "15m"
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
    assert rows[0]["decision_lane"] == "DATA_BLOCKED"


def test_prior_completed_session_is_current_before_eod_cutoff(monkeypatch):
    import datetime as dt
    import mvp_api
    import pandas as pd
    import screening

    daily = pd.DataFrame({
        "Open": [10.0] * 25, "High": [11.0] * 25,
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
    monkeypatch.setattr(mvp_api, "classify_wave_candidate", lambda *a, **k: {
        "state": "WAVE_1_ADVANCE", "confidence": "MEDIUM", "evidence": {}})
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
        "Open": [10.0] * 25, "High": [11.0] * 25,
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
    monkeypatch.setattr(mvp_api, "classify_wave_candidate", lambda *a, **k: {
        "state": "WAVE_1_ADVANCE", "confidence": "MEDIUM", "evidence": {}})
    monkeypatch.setattr(mvp_api, "build_trade_setup", lambda *a, **k: {
        "timeframe": "60m", "status": "READY"})

    rows, _ = mvp_api.build_setup_candidates_from_data(object())
    item = rows[0]
    assert item["data_status"]["intraday_60m_freshness"] == "stale"
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
