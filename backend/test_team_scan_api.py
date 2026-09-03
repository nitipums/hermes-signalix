import json
from datetime import date, datetime, timezone

import mvp_routes
import pytest
from team_facts_api import build_response, _facts


class Handler:
    def __init__(self, headers=None):
        self.headers = headers or {}; self.status = None; self.body = b""; self.wfile = self
    def send_response(self, status): self.status = status
    def send_header(self, *_): pass
    def end_headers(self): pass
    def write(self, body): self.body += body


def model(symbols=("AAA",)):
    item_keys = ("as_of", "ath_high", "ath_low", "bonus_evidence", "context",
                 "daily_metrics", "data_status", "decision_lane", "high52",
                 "low52", "index_membership", "index_membership_evidence",
                 "provenance", "quote", "setup", "symbol", "trend", "wave")
    return {"items": [{key: (s if key == "symbol" else None) for key in item_keys} for s in symbols],
            "universe": "marginable_long", "base_active_ord_count": 237,
            "eligible_count": 237, "excluded_count": 0, "freshness": {"status": "fresh"},
            "source_version": "run-1", "published_at": "2026-09-03T00:00:00Z"}


def bars(n=260, close=100, volume=100):
    return [(date(2025, 1, 1), close, close + 1, close - 1, close, volume)] * n


def intra():
    return [(datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc), 100, 101, 99, 100, 100)]


def fresh_bars(close=100, volume=100):
    rows = bars(260, close, volume)
    rows[-2] = (date(2026, 9, 1), close - 1, close, close - 2, close - 1, volume)
    rows[-1] = (date(2026, 9, 2), close, close + 1, close - 1, close, volume)
    return rows


def response(h): return json.loads(h.body)


def test_auth_header_only(monkeypatch):
    monkeypatch.setenv("TEAM_SCAN_API_KEY", "secret")
    for path, headers in (("/api/team/setup-candidates", {}),
                          ("/api/team/setup-candidates?key=secret", {}),
                          ("/api/team/setup-candidates", {"X-Signalix-Team-Key": "wrong"})):
        h = Handler(headers); mvp_routes.handle_mvp_api(path, h)
        assert h.status == 401


def test_history_route_auth_validation_unknown_symbol_and_facts_only(monkeypatch):
    monkeypatch.setenv("TEAM_SCAN_API_KEY", "secret")
    monkeypatch.setattr("read_model_publisher.load_current_read_model", lambda: model())
    monkeypatch.setattr("team_facts_api.load_history", lambda pg, symbol, timeframe, limit: (
        [(date(2026, 9, 2), 100, 101, 99, 100, 100)] if timeframe == "1D" else
        [(datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc), 100, 101, 99, 100, 100)]
    ))
    monkeypatch.setattr(mvp_routes, "_acquire_setup_candidates_pg", lambda: (object(), lambda: None))
    unauthenticated = Handler()
    mvp_routes.handle_mvp_api("/api/team/setup-candidates/AAA/history", unauthenticated)
    assert unauthenticated.status == 401
    unknown = Handler({"X-Signalix-Team-Key": "secret"})
    mvp_routes.handle_mvp_api("/api/team/setup-candidates/MISSING/history", unknown)
    assert unknown.status == 404
    for suffix in ("?timeframe=5m", "?limit=0", "?limit=401"):
        invalid = Handler({"X-Signalix-Team-Key": "secret"})
        mvp_routes.handle_mvp_api("/api/team/setup-candidates/AAA/history" + suffix, invalid)
        assert invalid.status == 400
    detail = Handler({"X-Signalix-Team-Key": "secret"})
    mvp_routes.handle_mvp_api("/api/team/setup-candidates/AAA/history?timeframe=1D&limit=1", detail)
    payload = response(detail)
    assert detail.status == 200
    assert payload["history"] == {"source": "price_data", "timeframe": "1D",
                                   "completed_60m_filter": None}
    assert payload["candles"]["daily"][0]["source"] == "price_data"
    assert "completed_60m" not in payload["candles"]
    assert "setup" not in json.dumps(payload).lower()

    detail_60m = Handler({"X-Signalix-Team-Key": "secret"})
    mvp_routes.handle_mvp_api("/api/team/setup-candidates/AAA/history?timeframe=60m&limit=1", detail_60m)
    payload_60m = response(detail_60m)
    assert payload_60m["history"]["source"] == "intraday_price_data"
    assert payload_60m["history"]["timeframe"] == "60m"
    assert payload_60m["candles"]["completed_60m"][0]["source"] == "intraday_price_data"


def test_route_is_facts_only_and_read_only(monkeypatch):
    monkeypatch.setenv("TEAM_SCAN_API_KEY", "secret")
    monkeypatch.setattr("read_model_publisher.load_current_read_model", lambda: model())
    monkeypatch.setattr("team_facts_api.load_ohlcv", lambda pg, symbols: ({"AAA": bars()}, {"AAA": intra()}))
    monkeypatch.setattr(mvp_routes, "_acquire_setup_candidates_pg", lambda: (object(), lambda: None))
    h = Handler({"X-Signalix-Team-Key": "secret"})
    mvp_routes.handle_mvp_api("/api/team/setup-candidates", h)
    payload = response(h)
    assert h.status == 200 and payload["api_version"] == "team-facts-v1"
    assert set(payload["views"]) == {"momentum", "near_high", "pullback"}
    forbidden = {"state", "setup", "lane", "trigger", "trade_stop", "target", "rr", "wave", "primary_state", "buy", "order"}
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                assert key.lower() not in forbidden
                yield from walk(child)
        elif isinstance(value, list):
            for child in value: yield from walk(child)
    list(walk(payload))
    assert payload["run"]["eligible_count"] == 237
    assert all(isinstance(view["items"], list) for view in payload["views"].values())


def test_exact_view_thresholds_and_missing_data_are_fail_closed():
    out = build_response(model(), {"AAA": bars(260, 100, 100)}, {"AAA": intra()})
    assert all(view["count"] == 0 for view in out["views"].values())
    assert out["views"]["momentum"]["exclusion_reasons"]
    missing = build_response(model(), {"AAA": []}, {"AAA": []})
    assert all(view["count"] == 0 for view in missing["views"].values())
    assert missing["views"]["momentum"]["exclusion_reasons"]["daily_close"] == 1


def test_published_item_shape_uses_canonical_universe_membership_for_identity():
    out = build_response(model(), {"AAA": fresh_bars()}, {"AAA": intra()})
    assert out["views"]["momentum"]["items"][0]["identity"] == {
        "symbol": "AAA", "market": "TH", "instrument_type": "ORD",
        "can_buy": True, "universe": "marginable_long",
    }


def test_noncanonical_universe_and_disagreeing_explicit_can_buy_fail_closed():
    unknown = model()
    unknown["universe"] = "active_ord"
    with pytest.raises(ValueError, match="canonical marginable_long"):
        build_response(unknown, {}, {})

    disagreeing = model()
    disagreeing["items"][0]["can_buy"] = False
    with pytest.raises(ValueError, match="disagrees"):
        build_response(disagreeing, {}, {})


def test_root_stale_metadata_does_not_globally_exclude_valid_symbols():
    stale_model = model(("AAA", "MISSING", "STALE"))
    stale_model["freshness"] = {"status": "stale", "daily_unavailable_count": 3}
    out = build_response(
        stale_model,
        {"AAA": fresh_bars(), "STALE": fresh_bars()},
        {"AAA": intra(), "STALE": [(datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc), 100, 101, 99, 100, 100)]},
        now=datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc),
    )
    assert out["run"]["freshness"]["status"] == "partial"
    assert out["run"]["freshness"]["daily"] == {"status": "partial", "missing_symbols": ["MISSING"]}
    assert out["run"]["freshness"]["intraday"] == {"status": "partial", "missing_symbols": ["MISSING"]}
    assert out["run"]["freshness"]["missing_symbols"]["reasons"]["MISSING"] == [
        "daily_baseline_missing", "intraday_missing"]
    assert all(view["count"] == 1 for view in out["views"].values())
    assert all(view["exclusion_reasons"] == {"daily_close": 1, "60m_stale": 1}
               for view in out["views"].values())


def test_current_timestamp_uses_latest_completed_intraday_bar():
    daily = fresh_bars()
    completed = (datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc), 100, 101, 99, 100, 100)
    out = build_response(
        model(), {"AAA": daily}, {"AAA": [completed]},
        now=datetime(2026, 9, 3, 10, 15, tzinfo=timezone.utc),
    )
    item = out["views"]["momentum"]["items"][0]
    assert item["current"]["timestamp"] == "2026-09-03T09:00:00+00:00"
    assert item["current"]["timeframe"] == "60m"
    assert item["current"]["completed_bar"] is True
    assert item["provenance"]["daily"]["latest"] == "2026-09-02"
    assert item["provenance"]["intraday"]["latest_completed"] == "2026-09-03T09:00:00+00:00"


def test_incomplete_intraday_row_cannot_satisfy_completed_intraday_requirement():
    out = build_response(
        model(), {"AAA": fresh_bars()},
        {"AAA": [(datetime(2026, 9, 3, 10, 1, tzinfo=timezone.utc), 100, 101, 99, 100, 100)]},
        now=datetime(2026, 9, 3, 10, 15, tzinfo=timezone.utc),
    )
    assert all(view["count"] == 0 for view in out["views"].values())
    assert all(view["exclusion_reasons"] == {"completed_intraday": 1} for view in out["views"].values())


def test_qualifying_boundary_items_contain_facts_and_indicators_only():
    daily = bars(260, 100, 100)
    daily[-2] = (date(2026, 9, 1), 99, 100, 98, 99, 100)
    daily[-1] = (date(2026, 9, 2), 100, 101, 99, 100, 100)
    out = build_response(model(), {"AAA": daily}, {"AAA": intra()})
    assert all(out["views"][name]["count"] == 1 for name in out["views"])
    item = out["views"]["near_high"]["items"][0]
    assert item["current"]["latest_price"] == 100
    assert item["current"]["timeframe"] == "60m"
    assert item["indicators"]["high_52w"] == 101
    assert "daily" not in item["candles"]
    assert item["candles"]["latest_completed_60m"]["source"] == "intraday_price_data"


def test_timeframe_source_separation_and_deterministic_unique_order():
    out = build_response(model(("ZZZ", "AAA", "AAA")), {"AAA": bars()}, {"AAA": intra()})
    for view in out["views"].values():
        symbols = [item["identity"]["symbol"] for item in view["items"]]
        assert symbols == sorted(set(symbols))
        for item in view["items"]:
            assert "daily" not in item["candles"]
            assert item["candles"]["latest_completed_60m"]["timeframe"] == "60m"


def test_volume_ratio_uses_current_daily_volume_over_previous_20_completed_volumes():
    rows = [(date(2026, 1, day), 100, 101, 99, 100, volume)
            for day, volume in enumerate(range(10, 31), start=1)]
    identity = {"symbol": "AAA", "market": "TH", "instrument_type": "ORD",
                "can_buy": True, "universe": "marginable_long"}
    fact = _facts(identity, rows, [])
    assert fact["indicators"]["volume_ratio_20"] == pytest.approx(30 / 19.5)


def test_volume_ratio_boundary_and_insufficient_history():
    identity = {"symbol": "AAA", "market": "TH", "instrument_type": "ORD",
                "can_buy": True, "universe": "marginable_long"}
    prior = [(date(2026, 1, day), 100, 101, 99, 100, 10) for day in range(1, 21)]
    exact = prior + [(date(2026, 2, 1), 100, 101, 99, 100, 20)]
    assert _facts(identity, exact, []) ["indicators"]["volume_ratio_20"] == pytest.approx(2)
    assert _facts(identity, exact[:-1], []) ["indicators"]["volume_ratio_20"] is None


def test_as_of_is_latest_completed_intraday_across_list_and_history():
    now = datetime(2026, 9, 3, 10, 15, tzinfo=timezone.utc)
    daily = fresh_bars()
    intraday = [(datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc), 100, 101, 99, 100, 100)]
    listed = build_response(model(), {"AAA": daily}, {"AAA": intraday}, now=now)
    detail = __import__("team_facts_api").build_history_response(
        model(), "AAA", daily, intraday, timeframe="60m", limit=1, now=now)
    assert listed["run"]["as_of"] == "2026-09-03T09:00:00+00:00"
    assert listed["timezone"] == "Asia/Bangkok"
    assert detail["run"]["as_of"] == listed["run"]["as_of"]
    assert listed["views"]["momentum"]["items"][0]["provenance"]["daily"]["latest"] == "2026-09-02"


def test_freshness_components_keep_partial_missing_symbols_visible():
    out = build_response(model(("AAA", "COM7")), {"AAA": fresh_bars()}, {"AAA": intra()})
    freshness = out["run"]["freshness"]
    assert freshness["daily"]["status"] == "partial"
    assert freshness["intraday"]["status"] == "partial"
    assert freshness["missing_symbols"]["symbols"] == ["COM7"]
    assert freshness["missing_symbols"]["reasons"]["COM7"] == [
        "daily_baseline_missing", "intraday_missing"]


def test_history_indicators_use_daily_contract_fields_and_history():
    rows = fresh_bars()
    identity = {"symbol": "AAA", "market": "TH", "instrument_type": "ORD",
                "can_buy": True, "universe": "marginable_long"}
    indicators = _facts(identity, rows, [])["indicators"]
    assert {"SMA5", "SMA20", "SMA50", "SMA200", "RSI14", "volume_average",
            "volume_ratio", "high20", "high52w", "previous252high"} <= set(indicators)
    assert indicators["SMA5"] == indicators["sma5"]
    assert indicators["high52w"] == indicators["high_52w"]


def test_daily_source_date_is_not_synthesized_from_intraday():
    out = build_response(model(), {"AAA": fresh_bars()}, {"AAA": intra()},
                         now=datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc))
    item = out["views"]["momentum"]["items"][0]
    assert item["provenance"]["daily"] == {
        "source": "price_data", "timeframe": "1D", "latest": "2026-09-02"}
    assert item["candles"]["latest_completed_60m"]["source"] == "intraday_price_data"


def test_missing_daily_baseline_is_data_incomplete_and_not_ranked():
    intraday = {"COM7": intra()}
    out = build_response(model(("COM7",)), {}, intraday,
                         now=datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc))
    assert all(view["count"] == 0 for view in out["views"].values())
    assert out["views"]["momentum"]["exclusion_reasons"] == {"daily_close": 1}
    fact = __import__("team_facts_api")._facts(
        {"symbol": "COM7", "market": "TH", "instrument_type": "ORD",
         "can_buy": True, "universe": "marginable_long"}, [], intraday["COM7"])
    assert fact["data_status"]["status"] == "DATA_INCOMPLETE"
    assert fact["current"]["change_pct"] is None
    assert fact["indicators"]["high52w"] is None
