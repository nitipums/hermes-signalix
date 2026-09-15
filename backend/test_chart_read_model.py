import datetime as dt
import json

import chart_read_model as crm
import mvp_routes
import pytest
import update_data


def _payload(symbol="AAA", timeframe="1D"):
    return {
        "symbol": symbol, "timeframe": timeframe, "candles": [{"date": "2026-09-14", "close": 10}],
        "indicators": {"series": {}, "latest": {"window_summary": {}}},
        "provenance": {"source": "intraday_price_data" if timeframe == "60M" else "price_data",
                       "as_of": "2026-09-14"},
    }


def test_publish_and_readback_is_compact_and_content_addressed(tmp_path, monkeypatch):
    monkeypatch.setattr("mvp_chart_db.project_chart_db_response", lambda symbol, timeframe, connection, canonical_item: _payload(symbol, timeframe))
    generated = dt.datetime.now(dt.timezone.utc)
    result = crm.publish(object(), ["BBB", "AAA"], root=tmp_path, generated_at=generated)
    assert result["timeframe"] == "1D"
    assert crm.read_current("AAA", root=tmp_path)["symbol"] == "AAA"
    pointer = json.loads((tmp_path / "current-1D.json").read_text())
    artifact = json.loads((tmp_path / pointer["artifact_path"]).read_text())
    assert artifact["schema_version"] == crm.SCHEMA_VERSION
    assert artifact["query_mode"] == "SELECT_ONLY"
    assert artifact["provenance"]["source"] == "price_data+derived_daily_price_data"
    assert artifact["as_of"] == "2026-09-14"
    assert "raw_history" not in artifact


def test_chart_projection_keeps_renderer_series_and_removes_unused_aligned_series():
    from mvp_chart_db import compact_chart_db_response

    candles = [{"date": f"2026-09-{index + 1:02d}", "close": index}
               for index in range(3)]
    aligned = lambda value: [f"{value}-{index}" for index in range(3)]
    payload = {
        "symbol": "AAA",
        "timeframe": "1D",
        "candles": candles,
        "indicators": {
            "policy_version": "technical-indicators-v2",
            "timeframe": "1D",
            "alignment": "candle_index",
            "availability": {"input": {"status": "AVAILABLE"}},
            "provenance": {"no_lookahead": True},
            "series": {
                "ma": {period: aligned(f"ma-{period}") for period in ("5", "10", "20", "50", "100", "200")},
                "macd": {name: aligned(f"macd-{name}") for name in ("line", "signal", "histogram")},
                "rsi": aligned("rsi"),
                "atr": aligned("atr"),
                "high": aligned("high"),
                "low": aligned("low"),
                "rolling_high": {"20": aligned("rolling-high")},
                "rolling_low": {"20": aligned("rolling-low")},
                "window_summary": [{"close": 1}] * 3,
            },
            "latest": {"window_summary": {"20": {"close": 2}}, "rsi": 2},
        },
        "availability": {"status": "available"},
        "source": "price_data",
        "as_of": "2026-09-03",
        "latest_time": "2026-09-03",
        "wave_evidence": {"markers": []},
        "provenance": {"source": "price_data", "as_of": "2026-09-03"},
    }

    compact = compact_chart_db_response(payload, limit=2)
    assert compact["candles"] == candles[-2:]
    assert set(compact["indicators"]["series"]) == {"ma", "macd", "rsi"}
    assert set(compact["indicators"]["series"]["ma"]) == {"5", "10", "20", "50", "100", "200"}
    assert set(compact["indicators"]["series"]["macd"]) == {"line", "signal", "histogram"}
    assert compact["indicators"]["series"]["rsi"] == aligned("rsi")[-2:]
    assert compact["indicators"]["latest"] == payload["indicators"]["latest"]
    assert compact["indicators"]["policy_version"] == "technical-indicators-v2"
    assert compact["availability"] == payload["availability"]
    assert compact["wave_evidence"] == payload["wave_evidence"]
    assert compact["source"] == payload["source"]
    assert compact["as_of"] == payload["as_of"]
    assert compact["timeframe"] == payload["timeframe"]


def test_60m_selection_and_stale_artifact_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("mvp_chart_db.project_chart_db_response", lambda symbol, timeframe, connection, canonical_item: _payload(symbol, timeframe))
    crm.publish(object(), ["AAA"], "60M", root=tmp_path,
                generated_at=dt.datetime.now(dt.timezone.utc))
    assert crm.read_current("AAA", "60M", root=tmp_path)["timeframe"] == "60M"
    assert crm.read_current("AAA", "1D", root=tmp_path) is None
    pointer = json.loads((tmp_path / "current-60M.json").read_text())
    artifact_path = tmp_path / pointer["artifact_path"]
    artifact = json.loads(artifact_path.read_text())
    artifact["generated_at"] = "2026-09-14T00:00:00+00:00"
    artifact_path.write_text(json.dumps(artifact))
    assert crm.read_current("AAA", "60M", root=tmp_path,
                            now=dt.datetime(2026, 9, 15, tzinfo=dt.timezone.utc)) is None


@pytest.mark.parametrize("timeframe,source", [
    ("1D", "price_data+derived_daily_price_data"), ("60M", "intraday_price_data"),
    ("1W", "price_data+derived_daily_price_data"), ("1M", "price_data+derived_daily_price_data"),
])
def test_all_drawer_timeframes_publish_with_explicit_source(tmp_path, monkeypatch, timeframe, source):
    monkeypatch.setattr("mvp_chart_db.project_chart_db_response",
                        lambda symbol, timeframe, connection, canonical_item: _payload(symbol, timeframe))
    crm.publish(object(), ["AAA"], timeframe, root=tmp_path,
                generated_at=dt.datetime.now(dt.timezone.utc))
    pointer = json.loads((tmp_path / f"current-{timeframe}.json").read_text())
    artifact = json.loads((tmp_path / pointer["artifact_path"]).read_text())
    assert artifact["provenance"] == {"source": source, "timeframe": timeframe}
    assert artifact["freshness"]["max_age_seconds"] == crm.FRESHNESS_SECONDS[timeframe]
    assert crm.read_current("AAA", timeframe, root=tmp_path)["timeframe"] == timeframe


def test_missing_entry_returns_none_for_explicit_db_fallback():
    assert crm.read_current("MISSING", "1D", root="/does/not/exist") is None


def test_pointer_identity_and_raw_history_invalidate_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr("mvp_chart_db.project_chart_db_response", lambda *args, **kwargs: _payload())
    crm.publish(object(), ["AAA"], root=tmp_path,
                generated_at=dt.datetime.now(dt.timezone.utc))
    pointer_path = tmp_path / "current-1D.json"
    pointer = json.loads(pointer_path.read_text())
    artifact_path = tmp_path / pointer["artifact_path"]
    artifact = json.loads(artifact_path.read_text())

    artifact["raw_history"] = [{"close": 1}]
    artifact_path.write_text(json.dumps(artifact))
    assert crm.read_current("AAA", root=tmp_path) is None

    artifact.pop("raw_history")
    artifact_path.write_text(json.dumps(artifact))
    pointer["generated_at"] = "2026-09-14T00:00:00+00:00"
    pointer_path.write_text(json.dumps(pointer))
    assert crm.read_current("AAA", root=tmp_path) is None


@pytest.mark.parametrize("timeframe", ["1D", "60M", "1W", "1M"])
def test_chart_route_reads_valid_artifact_without_database(tmp_path, monkeypatch, timeframe):
    generated = dt.datetime.now(dt.timezone.utc)
    monkeypatch.setattr("mvp_chart_db.project_chart_db_response",
                        lambda symbol, timeframe, connection, canonical_item: _payload(symbol, timeframe))
    crm.publish(object(), ["AAA"], timeframe=timeframe, root=tmp_path, generated_at=generated)
    monkeypatch.setenv("SIGNALIX_CHART_READ_MODEL_ROOT", str(tmp_path))
    def fail_db(*args, **kwargs):
        raise AssertionError("database chart path was used")
    monkeypatch.setattr("mvp_chart_db.project_chart_db_response", fail_db)

    class Handler:
        def __init__(self):
            self.wfile = self
        def send_response(self, status): self.status = status
        def send_header(self, key, value): pass
        def end_headers(self): pass
        def write(self, body): self.body = body

    handler = Handler()
    assert mvp_routes.handle_mvp_api(f"/api/chart-db/AAA?timeframe={timeframe}&view=chart", handler)
    assert json.loads(handler.body)["symbol"] == "AAA"


def test_chart_route_db_fallback_is_compact_and_explicitly_labelled(monkeypatch):
    payload = _payload()
    payload["indicators"]["series"] = {
        "ma": {"5": [1, 2]},
        "macd": {"line": [1, 2], "signal": [1, 2], "histogram": [1, 2]},
        "rsi": [1, 2], "atr": [1, 2], "high": [1, 2],
    }
    monkeypatch.setattr("chart_read_model.read_current", lambda *args, **kwargs: None)
    monkeypatch.setattr("mvp_chart_db.project_chart_db_response",
                        lambda *args, **kwargs: payload)
    monkeypatch.setattr(mvp_routes, "load_payload", lambda: {"items": []})

    class Handler:
        def __init__(self):
            self.wfile = self
        def send_response(self, status): self.status = status
        def send_header(self, key, value): pass
        def end_headers(self): pass
        def write(self, body): self.body = body

    handler = Handler()
    assert mvp_routes.handle_mvp_api("/api/chart-db/AAA?timeframe=1D&view=chart", handler)
    response = json.loads(handler.body)
    assert response["provenance"]["chart_read_model"] == "DB_FALLBACK"
    assert set(response["indicators"]["series"]) == {"ma", "macd", "rsi"}


def test_eod_publication_calls_all_aggregates_and_is_nonfatal(monkeypatch):
    calls = []

    class Connection:
        def close(self):
            calls.append("close")

    monkeypatch.setattr(update_data, "get_pg", lambda: Connection())
    monkeypatch.setattr(update_data, "publish_chart_read_model_after_commit",
                        lambda pg, timeframe: calls.append(timeframe))
    update_data.publish_eod_chart_read_models_after_commit()
    assert calls == ["1D", "1W", "1M", "close"]


def test_chart_publication_failure_preserves_pointer_and_does_not_raise(monkeypatch, capsys):
    class Connection:
        def close(self):
            pass

    monkeypatch.setattr(update_data, "get_pg", lambda: Connection())
    monkeypatch.setattr(update_data, "publish_chart_read_model_after_commit",
                        lambda pg, timeframe: (_ for _ in ()).throw(ValueError("bad chart")))
    update_data.publish_eod_chart_read_models_after_commit()
    captured = capsys.readouterr()
    events = [json.loads(line.split(" ", 1)[1]) for line in
              (captured.out + captured.err).splitlines()]
    assert [event["timeframe"] for event in events] == ["1D", "1W", "1M"]
    assert all(event["event"] == "chart_read_model_publish_failure"
               and event["pointer_preserved"] is True for event in events)
