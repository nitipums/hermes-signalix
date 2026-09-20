import json

import active_chart_adapter as adapter
import mvp_routes
import pytest


def payload(symbol="AAA", timeframe="1D", candles=None):
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": [{"date": "2026-09-19", "close": 10}] if candles is None else candles,
        "provenance": {"source": "price_data"},
    }


def semantic_payload(symbol="AAA", timeframe="1D", candles=None):
    result = payload(symbol, timeframe, candles)
    result.update({
        "wave_evidence": {"markers": [{"wave": "WAVE_2"}]},
        "setup": {"status": "TRIGGERED", "nested": {"vcp": {"score": 9}}},
        "decision_lane": "REVIEW_NOW",
        "action": "BUY_NOW",
        "decision": {"state": "READY"},
        "research_only": False,
        "status": "PRODUCTION_READ_ONLY",
        "actionability": "NONE",
        "nested": {"wave_state": "EARLY_WAVE_3", "safe": "kept"},
    })
    return result


def test_active_timeframes_are_explicit_and_invalid_requests_fail_closed():
    assert adapter.APPROVED_TIMEFRAMES == {"1D", "60M", "1W", "1M"}
    with pytest.raises(adapter.InvalidActiveChartRequest):
        adapter.chart_response(
            "AAA", "5M", read_prebuilt=lambda *args, **kwargs: None,
            load_canonical_item=lambda symbol: None,
            project_db=lambda *args, **kwargs: None,
            compact=lambda value: value,
        )


def test_prebuilt_chart_is_preferred_and_labelled():
    calls = []
    status, result = adapter.chart_response(
        "aaa", "1D",
        read_prebuilt=lambda *args, **kwargs: payload("AAA"),
        load_canonical_item=lambda symbol: calls.append("item"),
        project_db=lambda *args, **kwargs: calls.append("db"),
        compact=lambda value: value,
    )
    assert status == 200
    assert result["provenance"]["chart_read_model"] == "PREBUILT"
    assert calls == []


def test_active_prebuilt_chart_strips_nested_historical_semantics():
    status, result = adapter.chart_response(
        "AAA", "1D", read_prebuilt=lambda *args, **kwargs: semantic_payload(),
        load_canonical_item=lambda symbol: pytest.fail("DB item lookup must not run"),
        project_db=lambda *args, **kwargs: pytest.fail("DB fallback must not run"),
        compact=lambda value: value,
    )
    assert status == 200
    assert result["candles"]
    assert result["nested"] == {"safe": "kept"}
    assert result["status"] == "PRODUCTION_READ_ONLY"
    assert result["actionability"] == "NONE"
    assert result["research_only"] is False
    assert all(key not in result for key in
               ("wave_evidence", "setup", "decision_lane", "action", "decision"))
    assert "chart_read_model" not in result.get("deprecation", {})


def test_active_db_fallback_strips_semantics_and_keeps_chart_facts():
    status, result = adapter.chart_response(
        "AAA", "1W", read_prebuilt=lambda *args, **kwargs: None,
        load_canonical_item=lambda symbol: {"symbol": symbol},
        project_db=lambda *args, **kwargs: semantic_payload("AAA", "1W"),
        compact=lambda value: value,
    )
    assert status == 200
    assert result["symbol"] == "AAA"
    assert result["timeframe"] == "1W"
    assert result["candles"]
    assert result["provenance"]["chart_read_model"] == "DB_FALLBACK"
    assert all(key not in result for key in
               ("wave_evidence", "setup", "decision_lane", "action", "decision"))


def test_invalid_prebuilt_falls_back_to_explicit_db_and_is_labelled():
    status, result = adapter.chart_response(
        "AAA", "1W",
        read_prebuilt=lambda *args, **kwargs: payload("AAA", "1W", candles=[]),
        load_canonical_item=lambda symbol: {"symbol": symbol},
        project_db=lambda *args, **kwargs: payload("AAA", "1W"),
        compact=lambda value: value,
    )
    assert status == 200
    assert result["provenance"]["chart_read_model"] == "DB_FALLBACK"


def test_db_unavailability_is_not_verified():
    status, result = adapter.chart_response(
        "AAA", "60M",
        read_prebuilt=lambda *args, **kwargs: None,
        load_canonical_item=lambda symbol: None,
        project_db=lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("offline")),
        compact=lambda value: value,
    )
    assert status == 200
    assert result["provenance"]["chart_read_model"] == "DB_FALLBACK"
    assert result["provenance"]["note"].startswith("NOT_VERIFIED")


@pytest.mark.parametrize("db_result", [None, {"symbol": "AAA", "timeframe": "1D", "candles": []}])
def test_known_symbol_empty_db_chart_is_explicitly_unavailable(db_result):
    status, result = adapter.chart_response(
        "AAA", "1D", read_prebuilt=lambda *args, **kwargs: None,
        load_canonical_item=lambda symbol: {"symbol": symbol},
        project_db=lambda *args, **kwargs: db_result,
        compact=lambda value: value,
    )
    assert status == 200
    assert result["status"] == "NOT_VERIFIED"
    assert result["availability"] == "unavailable"
    assert result["candles"] == []
    assert result["provenance"]["chart_read_model"] == "DB_FALLBACK"


def test_unknown_symbol_keeps_distinguishable_404():
    status, result = adapter.chart_response(
        "MISSING", "1D", read_prebuilt=lambda *args, **kwargs: None,
        load_canonical_item=lambda symbol: None,
        project_db=lambda *args, **kwargs: None,
        compact=lambda value: value,
    )
    assert status == 404
    assert result == {"error": "symbol not found", "symbol": "MISSING"}


def test_symbol_detail_is_facts_only_and_does_not_delegate_historical_projection():
    item = {
        "symbol": "AAA", "name": "Alpha", "close": 10, "sector": "Tech",
        "quote": {"price": 10, "action": "BUY_NOW"},
        "provenance": {"source": "trend-map", "wave": "WAVE_1"},
        "wave": {"state": "WAVE_1_ADVANCE"},
        "setup": {"status": "TRIGGERED"},
        "bonus_evidence": {"vcp": {"present": True}},
        "decision_lane": "REVIEW_NOW", "action": "BUY_NOW",
    }
    status, result = adapter.symbol_detail_response(
        "aaa", load_model=lambda: {"items": [item]},
        validate_model=lambda model: model,
        snapshot_meta=lambda model: {},
        overlay_intraday=lambda payload: payload,
    )
    assert status == 200
    assert result["symbol"] == "AAA"
    assert result["close"] == 10
    assert result["quote"] == {"price": 10}
    assert result["provenance"] == {"source": "trend-map"}
    assert all(key not in result for key in
               ("wave", "setup", "bonus_evidence", "decision_lane", "action"))


class _Handler:
    def __init__(self):
        self.wfile = self

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        pass

    def end_headers(self):
        pass

    def write(self, body):
        self.body = body


def test_active_dispatch_preserves_query_timeframe_and_has_no_legacy_markers(monkeypatch):
    monkeypatch.setattr("chart_read_model.read_current",
                        lambda symbol, timeframe: semantic_payload(symbol, timeframe))
    handler = _Handler()
    assert mvp_routes.handle_mvp_api(
        "/api/chart-db/AAA?timeframe=60M&view=chart", handler
    )
    result = json.loads(handler.body)
    assert handler.status == 200
    assert result["timeframe"] == "60M"
    assert result["provenance"]["chart_read_model"] == "PREBUILT"
    assert "audit_only" not in result
    assert "deprecation" not in result
    assert "wave_evidence" not in result


def test_active_dispatch_returns_unavailable_state_for_known_empty_fallback(monkeypatch):
    monkeypatch.setattr("chart_read_model.read_current", lambda *args, **kwargs: None)
    monkeypatch.setattr(mvp_routes, "_load_active_chart_item",
                        lambda symbol: {"symbol": symbol})
    monkeypatch.setattr("mvp_chart_db.project_chart_db_response",
                        lambda *args, **kwargs: None)
    handler = _Handler()
    assert mvp_routes.handle_mvp_api(
        "/api/chart-db/AAA?timeframe=1D&view=chart", handler
    )
    result = json.loads(handler.body)
    assert handler.status == 200
    assert result["status"] == "NOT_VERIFIED"
    assert result["availability"] == "unavailable"
    assert result["provenance"]["chart_read_model"] == "DB_FALLBACK"
    assert "audit_only" not in result
    assert "deprecation" not in result


def test_active_detail_dispatch_is_facts_only_without_legacy_markers(monkeypatch):
    item = {
        "symbol": "AAA", "name": "Alpha", "close": 10,
        "wave": {"state": "WAVE_1_ADVANCE"},
        "setup": {"status": "TRIGGERED"},
        "vcp": {"score": 99}, "decision_lane": "REVIEW_NOW",
        "provenance": {"source": "trend-map"},
    }
    model = {
        "universe": "marginable_long", "base_active_ord_count": 1,
        "eligible_count": 1, "excluded_count": 0, "items": [item],
    }
    monkeypatch.setattr("read_model_publisher.load_current_read_model",
                        lambda: model)
    monkeypatch.setattr(mvp_routes, "_overlay_latest_intraday_metadata",
                        lambda payload: payload)
    handler = _Handler()
    assert mvp_routes.handle_mvp_api("/api/symbol/AAA?view=detail", handler)
    result = json.loads(handler.body)
    assert handler.status == 200
    assert result["symbol"] == "AAA"
    assert result["close"] == 10
    assert "wave" not in result
    assert "setup" not in result
    assert "vcp" not in result
    assert "decision_lane" not in result
    assert "audit_only" not in result
    assert "deprecation" not in result


def test_active_route_shapes_exclude_setup_and_vcp_routes():
    assert adapter.is_active_route("/api/chart-db/AAA", {"view": ["chart"]})
    assert adapter.is_active_route("/api/symbol/AAA", {"view": ["detail"]})
    assert not adapter.is_active_route("/api/symbol/AAA", {})
    assert not adapter.is_active_route("/api/symbol/AAA", {"view": [""]})
    assert not adapter.is_active_route("/api/setup-candidates", {})
    assert not adapter.is_active_route("/api/vcp-finder", {})
