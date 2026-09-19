import json
from datetime import date, timedelta

import pytest

import market_breadth_artifact as artifact_module
from market_breadth import build_market_breadth
from market_breadth_artifact import (
    ARTIFACT_VERSION,
    handle_market_breadth_api,
    load_market_breadth_artifact,
    market_breadth_response,
    publish_market_breadth_artifact,
)


def observation(date, close):
    return {"symbol": "AAA", "session_date": date, "open": close,
            "high": close, "low": close, "close": close, "volume": 100,
            "above_ma50": True, "above_ma200": True,
            "main_trend_evidence": {"main_trend": 2, "evidence_quality": "FULL"}}


def fixture_build(count=260):
    rows = []
    for index in range(count):
        rows.append(observation(str(date(2026, 1, 1) + timedelta(days=index)), 100 + index))
    return build_market_breadth(rows, universe_snapshot={"name": "active_ord", "symbols": ["AAA"], "count": 1})


def publish_fixture(tmp_path, count=260, **metadata):
    return publish_market_breadth_artifact(
        fixture_build(count), root=tmp_path,
        metadata={"counts": {"official": 1, "derived": 0, "blocked": 0, "invalid": 0},
                  "source": "fixture", "run_id": "run-mb2", **metadata},
    )


def test_publish_and_route_serialize_current_history_and_all_ranges(tmp_path):
    publish_fixture(tmp_path)
    artifact = load_market_breadth_artifact(tmp_path)
    assert set((key for key in artifact if key.startswith("history_"))) == {
        "history_20", "history_60", "history_260", "history_all"}
    assert {key: artifact["prebuilt_ranges"][key]["count"] for key in artifact["prebuilt_ranges"]} == {
        "current": 1, "history_20": 20, "history_60": 60,
        "history_260": 260, "history_all": 260}
    for value, expected in ((None, 20), ("20", 20), ("60", 60), ("260", 260), ("all", 260)):
        path = "/api/market-breadth" if value is None else f"/api/market-breadth?range={value}"
        payload, status = market_breadth_response(path, loader=lambda: load_market_breadth_artifact(tmp_path))
        assert status == 200
        assert len(payload["history"]) == expected
        assert payload["history"] == sorted(payload["history"], key=lambda item: item["session_date"])
        assert payload["history"][-1] == payload["current"]
        assert payload["status"] == "PRODUCTION_READ_ONLY"
        assert payload["research_only"] is False
        assert payload["actionability"] == "NONE"
        assert payload["direction"] == artifact["directions"][f"history_{value or '20'}"]
        assert payload["content_identity"]["artifact_version"] == ARTIFACT_VERSION


def test_direction_is_published_and_selected_with_the_requested_range(tmp_path):
    publish_fixture(tmp_path)
    artifact = load_market_breadth_artifact(tmp_path)
    assert set(artifact["directions"]) == {"history_20", "history_60", "history_260", "history_all"}
    for value in ("20", "60", "260", "all"):
        payload, status = market_breadth_response(
            f"/api/market-breadth?range={value}",
            loader=lambda: load_market_breadth_artifact(tmp_path),
        )
        assert status == 200
        assert payload["direction"] == artifact["directions"][f"history_{value}"]
        assert payload["direction"]["endpoint"]["session_date"] == payload["history"][-1]["session_date"]


def test_api_selects_published_slice_without_request_time_projection(tmp_path, monkeypatch):
    publish_fixture(tmp_path)
    loaded = load_market_breadth_artifact(tmp_path)

    def projection_must_not_run(session):
        raise AssertionError("request path projected a raw session")

    monkeypatch.setattr(artifact_module, "_public_session", projection_must_not_run)
    payload, status = artifact_module.market_breadth_response(
        "/api/market-breadth?range=60", loader=lambda: loaded)
    assert status == 200
    assert payload["history"] is loaded["history_60"]
    assert payload["content_identity"]["range"] == "history_60"


def test_api_does_not_rescan_validated_artifact_on_each_request(tmp_path, monkeypatch):
    publish_fixture(tmp_path)
    loaded = load_market_breadth_artifact(tmp_path)
    monkeypatch.setattr(artifact_module, "_validate", lambda value, **kwargs: (_ for _ in ()).throw(
        AssertionError("request path rescanned artifact")))
    payload, status = artifact_module.market_breadth_response(
        "/api/market-breadth?range=20", loader=lambda: loaded)
    assert status == 200 and len(payload["history"]) == 20


def test_public_projection_has_aggregate_only_new_high_low_and_bounded_size(tmp_path):
    publish_fixture(tmp_path, 260)
    payload, status = market_breadth_response("/api/market-breadth?range=260",
                                              loader=lambda: load_market_breadth_artifact(tmp_path))
    assert status == 200
    for session in payload["history"]:
        details = session["new_high_low"]
        assert set(details) == {"aggregate", "quality", "reason"}
        assert "AAA" not in details
        assert "by_symbol" not in details
    assert payload["current"]["new_high_low"]["aggregate"]["20"]["new_high_count"] == 1
    assert payload["current"]["new_high_low"]["aggregate"]["20"]["new_high_percentage"] == 100.0
    assert payload["current"]["moving_average_breadth"]["above_ma50"]["percentage"] == 100.0
    assert payload["current"]["volume"]["up_percentage"] == 100.0
    assert payload["current"]["main_trend"]["totals"]["2"]["percentage"] == 100.0
    assert len(json.dumps(payload, separators=(",", ":"))) < 1_000_000


def test_old_version_pointer_fails_closed(tmp_path):
    published = publish_fixture(tmp_path, 20)
    pointer = tmp_path / "current.json"
    pointer.write_text(json.dumps({"artifact_version": "signalix.market-breadth.artifact.v1",
                                   "path": published["path"].split("/")[-1],
                                   "content_hash": published["content_hash"]}))
    with pytest.raises(ValueError):
        load_market_breadth_artifact(tmp_path)


def test_old_current_artifact_without_directions_fails_closed(tmp_path):
    publish_fixture(tmp_path)
    pointer = json.loads((tmp_path / "current.json").read_text())
    path = tmp_path / "versions" / pointer["path"]
    data = json.loads(path.read_text())
    data.pop("directions")
    path.write_text(json.dumps(data, separators=(",", ":"), sort_keys=True))
    with pytest.raises(ValueError):
        load_market_breadth_artifact(tmp_path)


def test_pointer_change_invalidates_in_process_cache(tmp_path):
    first = publish_fixture(tmp_path, 20, run_id="first")
    assert load_market_breadth_artifact(tmp_path)["run_id"] == "first"
    second = publish_fixture(tmp_path, 20, run_id="second")
    assert second["content_hash"] != first["content_hash"]
    assert load_market_breadth_artifact(tmp_path)["run_id"] == "second"


def test_null_metric_has_reason_and_counts_are_preserved(tmp_path):
    build = fixture_build(20)
    build["sessions"][build["as_of"]]["ad_ratio"] = {"value": None, "status": "NO_DECLINERS"}
    publish_market_breadth_artifact(build, root=tmp_path, metadata={
        "counts": {"official": 10, "derived": 2, "blocked": 3, "invalid": 4},
        "source": "fixture", "run_id": "run-1"})
    payload, status = market_breadth_response("/api/market-breadth", loader=lambda: load_market_breadth_artifact(tmp_path))
    assert status == 200
    assert payload["current"]["ad_ratio"]["reason_code"] == "no_decliners"
    assert payload["counts"] == {"official": 10, "derived": 2, "blocked": 3, "invalid": 4}
    assert payload["official_count"] == 10 and payload["invalid_count"] == 4


def test_optional_set_benchmark_is_preserved_through_artifact_and_api(tmp_path):
    benchmark = {"symbol": "SET", "source": "price_data", "timeframe": "1D",
                 "close": 1400.25, "change_1d_pct": 0.5, "change_20d_pct": -1.25,
                 "as_of": "2026-09-11", "quality": {"status": "AVAILABLE", "reason": "valid_inputs_available"}}
    publish_fixture(tmp_path, benchmark=benchmark)
    artifact = load_market_breadth_artifact(tmp_path)
    payload, status = market_breadth_response("/api/market-breadth", loader=lambda: artifact)
    assert status == 200 and payload["benchmark"] == benchmark
    assert all("SET50" not in json.dumps(value) for value in (artifact, payload))


def test_optional_blocked_benchmark_preserves_null_values_and_quality(tmp_path):
    benchmark = {"symbol": "SET", "source": "price_data", "timeframe": "1D",
                 "close": None, "change_1d_pct": None, "change_20d_pct": None,
                 "as_of": None, "quality": {"status": "DATA_BLOCKED", "reason": "benchmark_missing"}}
    publish_fixture(tmp_path, benchmark=benchmark)
    payload, status = market_breadth_response("/api/market-breadth", loader=lambda: load_market_breadth_artifact(tmp_path))
    assert status == 200 and payload["benchmark"] == benchmark


@pytest.mark.parametrize("path", ["/api/market-breadth?range=10", "/api/market-breadth?range=", "/api/market-breadth?range=bad"])
def test_invalid_range_fails_closed(path):
    payload, status = market_breadth_response(path, loader=lambda: (_ for _ in ()).throw(AssertionError("loader called")))
    assert status == 400 and payload["reason"] == "invalid_range"


@pytest.mark.parametrize("tamper", ["pointer", "pointer_missing", "pointer_corrupt", "content", "missing", "empty", "stale"])
def test_pointer_content_and_unusable_artifact_fail_closed(tmp_path, tamper):
    published = publish_fixture(tmp_path)
    pointer = tmp_path / "current.json"
    artifact = tmp_path / "versions" / published["path"]
    if tamper == "pointer":
        pointer.write_text(json.dumps({"artifact_version": ARTIFACT_VERSION, "path": published["path"], "content_hash": "0" * 64}))
    elif tamper == "pointer_missing":
        pointer.unlink()
    elif tamper == "pointer_corrupt":
        pointer.write_text("not-json")
    elif tamper == "content":
        artifact.write_bytes(artifact.read_bytes() + b" ")
    elif tamper == "missing":
        artifact.unlink()
    elif tamper == "empty":
        artifact.write_text("{}")
    else:
        data = json.loads(artifact.read_text())
        data["quality"] = {"status": "STALE"}
        artifact.write_text(json.dumps(data, separators=(",", ":"), sort_keys=True))
    payload, status = market_breadth_response("/api/market-breadth", loader=lambda: load_market_breadth_artifact(tmp_path))
    assert status == 503 and payload["status"] == "DATA_BLOCKED"


def test_handler_uses_actual_json_serialization_seam(tmp_path):
    publish_fixture(tmp_path, 20)

    class Handler:
        def __init__(self):
            self.body = bytearray()
            self.wfile = self
        def send_response(self, status): self.status = status
        def send_header(self, key, value): pass
        def end_headers(self): pass
        def write(self, body): self.body.extend(body)

    handler = Handler()
    assert handle_market_breadth_api("/api/market-breadth?range=20", handler,
                                     loader=lambda: load_market_breadth_artifact(tmp_path))
    assert handler.status == 200
    assert len(json.loads(bytes(handler.body))["history"]) == 20
