import json
import datetime as dt

from daily_history import DailyHistoryAdapter
import trend_route
import trend_route_api
import trend_route_publisher as publisher
import publish_trend_route
from trend_route_replay import replay_market

from pathlib import Path


def indicator_rows(count=260):
    return [{"date": (dt.date(2025, 1, 1) + dt.timedelta(days=index)).isoformat(),
             "open": 100.0 + index * 0.1, "high": 101.0 + index * 0.1,
             "low": 99.0 + index * 0.1, "close": 100.5 + index * 0.1,
             "volume": 1000 + index} for index in range(count)]


def observations():
    return [{"date": "2026-01-05", "main_trend": 1},
            {"date": "2026-01-06", "main_trend": 1},
            {"date": "2026-01-07", "main_trend": 2},
            {"date": "2026-01-12", "main_trend": 2}]


def test_route_maps_numeric_main_trend_and_marks_gap_partial():
    route = trend_route.build_route(observations(), symbol="AAA", cutoff="2026-01-12",
                                    expected_sessions=["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"])
    assert [segment["label"] for segment in route["segments"]] == ["BASING", "UP", "UP"]
    assert route["status"] == "PARTIAL"
    assert "MISSING_SESSION_GAP" in route["reason_codes"]
    assert route["coverage"]["no_lookahead"] is True
    assert all("close" not in observation for observation in route["observations"])
    assert route["current_segment"] == route["segments"][-1]["id"]
    assert route["segments"][-1]["current"] is True
    assert route["segments"][-1]["main_trend"] == 2
    assert route["segments"][-1]["quality"] == "VERIFIED"
    assert route["segments"][-1]["provenance"]["timeframe"] == "1D"
    assert route["segments"][-1]["date"] == "2026-01-12"
    assert route["segments"][-1]["session_count"] == 1


def test_weekend_or_holiday_span_does_not_split_without_expected_market_session():
    route = trend_route.build_route(observations(), symbol="AAA", cutoff="2026-01-12",
                                    expected_sessions=["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-12"])
    assert route["status"] == "FULL"
    assert route["coverage"]["gap_count"] == 0


def test_true_missing_market_session_splits_route():
    route = trend_route.build_route([{"date": "2026-01-05", "main_trend": 1},
                                    {"date": "2026-01-07", "main_trend": 1}], symbol="AAA",
                                    cutoff="2026-01-07",
                                    expected_sessions=["2026-01-05", "2026-01-06", "2026-01-07"])
    assert route["status"] == "PARTIAL"
    assert route["coverage"]["gap_count"] == 1
    assert route["coverage"]["missing_expected_sessions"] == 1


def test_symbol_missing_expected_session_is_partial_while_market_calendar_is_shared():
    result = replay_market({"AAA": [{"date": "2026-01-05", "main_trend": 1}, {"date": "2026-01-07", "main_trend": 1}],
                            "BBB": [{"date": "2026-01-05", "main_trend": 1}, {"date": "2026-01-06", "main_trend": 1},
                                     {"date": "2026-01-07", "main_trend": 1}]}, "2026-01-07")
    assert result["coverage"]["expected_sessions"] == 3
    assert result["symbols"]["AAA"]["status"] == "PARTIAL"
    assert result["symbols"]["BBB"]["status"] == "FULL"


def test_route_does_not_mark_segment_current_when_cutoff_has_no_usable_observation():
    route = trend_route.build_route(observations(), symbol="AAA", cutoff="2026-01-13")
    assert route["current_segment"] is None
    assert all(segment["current"] is False for segment in route["segments"])


def test_replay_uses_one_cutoff_and_excludes_future_observation():
    result = replay_market({"AAA": observations() + [{"date": "2026-02-01", "main_trend": 4}]}, "2026-01-12")
    assert result["cutoff"] == "2026-01-12"
    assert result["symbols"]["AAA"]["coverage"]["future_rows_excluded"] == 1
    assert all(item["date"] <= "2026-01-12" for item in result["symbols"]["AAA"]["observations"])


def test_route_publisher_is_deterministic_and_fail_closed(tmp_path):
    route = trend_route.build_route(observations(), symbol="AAA")
    first = publisher.publish_route_read_model({"AAA": route}, root=tmp_path,
        published_at="2026-02-01T00:00:00+00:00", universe={"symbols": ["AAA"], "scope": "fixed"})
    first_pointer = json.loads((tmp_path / "current.json").read_text())
    second = publisher.publish_route_read_model({"AAA": route}, root=tmp_path,
        published_at="2026-02-02T00:00:00+00:00", universe={"symbols": ["AAA"], "scope": "fixed"})
    second_pointer = json.loads((tmp_path / "current.json").read_text())
    assert first["artifact_id"] == second["artifact_id"]
    assert first_pointer["content_hash"] == second_pointer["content_hash"]
    assert first_pointer["published_at"] != second_pointer["published_at"]
    assert len(list((tmp_path / "versions").glob("*.json"))) == 1
    loaded = publisher.read_symbol_route("AAA", root=tmp_path)
    assert loaded["segments"] == route["segments"]
    pointer = json.loads((tmp_path / "current.json").read_text())
    pointer["content_hash"] = "corrupt"
    (tmp_path / "current.json").write_text(json.dumps(pointer))
    assert publisher.read_current_route(tmp_path)["verification_status"] == "NOT_VERIFIED"


def test_route_api_is_compact_read_only_envelope():
    class Handler:
        status = None
        def send_bytes(self, body, **kwargs):
            self.body = body
            self.status = kwargs.get("status")

    handler = Handler()
    assert trend_route_api.handle_trend_route_api("/api/trend-map/AAA/route", handler,
        reader=lambda symbol: trend_route.build_route(observations(), symbol=symbol))
    payload = json.loads(handler.body)
    assert payload["status"] == "PRODUCTION_READ_ONLY"
    assert payload["actionability"] == "NONE"
    assert "ohlcv" not in json.dumps(payload).lower()
    assert handler.status == 200


def test_route_api_rejects_unknown_and_malformed_symbols():
    class Handler:
        def send_bytes(self, body, **kwargs):
            self.body = body
            self.status = kwargs["status"]

    def reader(symbol):
        return trend_route.build_route(observations(), symbol=symbol) if symbol == "AAA" else {
            "status": "NOT_VERIFIED", "reason_codes": ["SYMBOL_NOT_PUBLISHED"]
        }

    unknown = Handler()
    assert trend_route_api.handle_trend_route_api("/api/trend-map/ZZZ/route", unknown, reader=reader)
    assert unknown.status == 404
    assert json.loads(unknown.body)["error"] == "SYMBOL_NOT_PUBLISHED"

    malformed = Handler()
    assert trend_route_api.handle_trend_route_api("/api/trend-map/not%20a%20symbol/route", malformed, reader=reader)
    assert malformed.status == 404
    assert json.loads(malformed.body)["error"] == "MALFORMED_SYMBOL"


def test_route_api_uses_published_read_model_universe(monkeypatch):
    class Handler:
        def send_bytes(self, body, **kwargs):
            self.body = body
            self.status = kwargs["status"]

    route = trend_route.build_route(observations(), symbol="AAA")
    monkeypatch.setattr(trend_route_api.publisher, "read_current_route", lambda: {
        "verification_status": "VERIFIED", "universe": {"symbols": ["AAA"]},
        "routes": {"AAA": route}
    })
    handler = Handler()
    assert trend_route_api.handle_trend_route_api("/api/trend-map/ZZZ/route", handler)
    assert handler.status == 404
    assert json.loads(handler.body)["error"] == "SYMBOL_NOT_PUBLISHED"


def test_publisher_replays_one_cutoff_and_publishes_resolved_bounded_universe(tmp_path, monkeypatch):
    class SelectOnlyFake:
        def __init__(self):
            self.resolve_calls = 0
            self.batch_calls = []
            self.symbols = [f"S{index:03d}" for index in range(237)]

        def resolve_universe(self, conn, universe):
            assert conn == "select-only"
            assert universe == "marginable_long"
            self.resolve_calls += 1
            return self.symbols, {"eligible_count": len(self.symbols), "base_active_ord_count": 931,
                                  "excluded_count": 694, "universe_filter": universe}

        def load_daily_pit_batch(self, conn, symbols, cutoff):
            assert conn == "select-only"
            self.batch_calls.append((list(symbols), cutoff))
            rows = []
            for offset in range(35):
                rows.append({"date": f"2026-01-{offset + 1:02d}", "open": 10 + offset,
                             "high": 11 + offset, "low": 9 + offset, "close": 10.5 + offset,
                             "volume": 1000})
            rows.append({"date": "2026-02-01", "open": 999, "high": 1000, "low": 998,
                         "close": 999, "volume": 1000})
            return {symbol: ([row for row in rows if not (symbol == "S000" and row["date"] == "2026-01-15")],
                             "2026-01-35", {"quality_established": True, "invalid_count": 0})
                    for symbol in symbols}

    calls = 0
    original = publish_trend_route.build_technical_indicators

    def counted(candles, timeframe):
        nonlocal calls
        calls += 1
        return original(candles, timeframe)

    monkeypatch.setattr(publish_trend_route, "build_technical_indicators", counted)
    fake = SelectOnlyFake()
    result = publish_trend_route.publish_trend_route(adapter=fake, conn="select-only",
                                                      cutoff="2026-01-31", root=tmp_path,
                                                      published_at="2026-02-02T00:00:00+00:00")
    assert fake.resolve_calls == 1
    assert len(fake.batch_calls) == 1
    assert fake.batch_calls[0][1].isoformat() == "2026-01-31"
    assert result["universe"]["resolved_count"] == 237
    assert result["coverage"]["resolved_count"] == 237
    assert calls == 237
    artifact = publisher.read_current_route(tmp_path)
    assert artifact["verification_status"] == "VERIFIED"
    assert artifact["cutoff"] == "2026-01-31"
    assert artifact["universe"]["readback_count"] == 237
    assert artifact["metadata"]["no_action"]["actionability"] == "NONE"
    assert len(artifact["routes"]) == 237
    assert artifact["routes"]["S000"]["status"] == "PARTIAL"
    assert artifact["routes"]["S000"]["coverage"]["missing_expected_sessions"] == 1
    assert sum(route["status"] == "FULL" for route in artifact["routes"].values()) == 236
    assert all(all(point["date"] <= "2026-01-31" for point in route["observations"])
               for route in artifact["routes"].values())


def test_publisher_consumes_named_daily_history_interface_without_concrete_adapter():
    class InMemoryDailyHistory:
        def resolve_universe(self, conn, universe):
            return ["AAA"], {"universe_filter": universe}

        def load_daily_pit(self, conn, symbol, as_of):
            return indicator_rows(35), as_of

        def load_daily_pit_batch(self, conn, symbols, as_of):
            return {symbol: self.load_daily_pit(conn, symbol, as_of) for symbol in symbols}

    adapter = InMemoryDailyHistory()
    assert isinstance(adapter, DailyHistoryAdapter)
    assert not hasattr(publish_trend_route, "BackendDailyAdapter")
    result = publish_trend_route.build_publication(adapter=adapter, conn=object(), cutoff="2026-02-01")

    assert result["universe"]["symbols"] == ["AAA"]
    assert result["routes"]["AAA"]["coverage"]["no_lookahead"] is True


def test_optimized_history_builds_indicators_once_per_symbol(monkeypatch):
    rows = indicator_rows()
    calls = 0
    original = publish_trend_route.build_technical_indicators

    def counted(candles, timeframe):
        nonlocal calls
        calls += 1
        return original(candles, timeframe)

    monkeypatch.setattr(publish_trend_route, "build_technical_indicators", counted)
    snapshots, stats = publish_trend_route.classify_history(rows, rows[-1]["date"])
    assert calls == 1
    assert len(snapshots) == 260
    assert stats["rows_used"] == 260


def test_optimized_history_matches_slow_reference_and_has_no_lookahead():
    rows = indicator_rows()
    cutoff = rows[219]["date"]
    reference, reference_stats = publish_trend_route.classify_history_reference(rows, cutoff)
    optimized, optimized_stats = publish_trend_route.classify_history(rows, cutoff)
    assert optimized == reference
    assert optimized_stats == reference_stats
    assert all(point["date"] <= cutoff for point in optimized)

    future_changed = list(rows)
    future_changed[-1] = {**future_changed[-1], "close": 1_000_000.0, "high": 1_000_001.0}
    changed, changed_stats = publish_trend_route.classify_history(future_changed, cutoff)
    assert changed == optimized
    assert changed_stats["future_rows_excluded"] == 40


def test_history_coverage_counts_missing_and_invalid_rows_explicitly():
    rows = indicator_rows(3) + [{"date": "not-a-date", "close": 1},
                                {"date": "2026-12-01", "open": 1, "high": 2,
                                 "low": 0, "close": 1, "volume": 1}]
    snapshots, stats = publish_trend_route.classify_history(rows, "2025-01-03")
    assert len(snapshots) == 3
    assert stats == {"rows_loaded": 5, "rows_used": 3,
                     "future_rows_excluded": 1, "invalid_rows": 1}


def test_route_keeps_canonical_260_session_bound():
    snapshots, _ = publish_trend_route.classify_history(indicator_rows(300), "2025-10-27")
    route = trend_route.build_route(snapshots, symbol="AAA", cutoff="2025-10-27")
    assert route["coverage"]["max_sessions"] == trend_route.MAX_SESSIONS == 260
    assert len(route["observations"]) == 260


def test_drawer_renderer_uses_route_field_paths_and_mobile_containment_contract():
    source = (Path(__file__).parent / "frontend" / "shared-drawer.js").read_text()
    css = (Path(__file__).parent / "frontend" / "styles.css").read_text()
    for marker in ("/api/trend-map/", "payload.segments", "segment.sessions", "segment.current", "Main Trend ", "segment.quality", "segment.provenance", "drawer-route-graph", "data-current"):
        assert marker in source
    assert "min-width:0" in css and "max-width: 520px" in css
