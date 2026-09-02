import json
from pathlib import Path

import pytest

from read_model_publisher import (build_read_model, load_current_read_model,
                                  publish_builder_result, publish_read_model,
                                  DEFAULT_ROOT)


def test_default_root_is_shared_backend_read_model_path():
    assert DEFAULT_ROOT == Path(__file__).resolve().parent / "read-model"


def _item(symbol, lane="WAIT"):
    return {
        "symbol": symbol, "as_of": "2026-09-01T00:00:00", "data_status": {"sufficient": True, "freshness": "fresh"},
        "trend": {}, "wave": {"primary_state": "UNKNOWN", "confidence": "LOW"},
        "setup": {"status": "FORMING"}, "context": {}, "bonus_evidence": {}, "decision_lane": lane,
        "provenance": {"policy_version": "setup-candidates-v1", "source": "price_data+intraday_price_data", "as_of": "2026-09-01", "freshness": "fresh"},
    }


def _build(count=237):
    items = [_item(f"S{n:03d}") for n in range(count)]
    return items, {"universe_filter": "marginable_long", "eligible_count": 237, "excluded_count": 694,
                   "scan_time": "2026-09-01", "freshness": {"status": "fresh"}}


VERSIONS = {"daily": {"run_id": "daily-1", "as_of": "2026-09-01"},
            "intraday": {"run_id": "60m-1", "as_of": "2026-09-02T09:00:00+00:00"}}


def test_build_preserves_complete_coverage_lanes_and_provenance():
    items, metadata = _build()
    items[0]["decision_lane"] = "REVIEW_NOW"
    model = build_read_model(items, metadata, source_versions=VERSIONS, published_at="2026-09-02T02:00:00+00:00")
    assert model["count"] == model["evaluated_count"] == 237
    assert sum(model["counts"].values()) == 237
    assert set(model["counts"]) == {"REVIEW_NOW", "SETUP_FORMING", "DAILY_CANDIDATE", "WAIT", "AVOID", "DATA_BLOCKED"}
    assert model["provenance"]["source_versions"] == VERSIONS
    assert model["excluded_count"] == 694


def test_partial_build_rejected_before_existing_pointer_changes(tmp_path):
    items, metadata = _build()
    model = build_read_model(items, metadata, source_versions=VERSIONS, published_at="t1")
    publish_read_model(model, tmp_path)
    before = (tmp_path / "current.json").read_text()
    with pytest.raises(ValueError, match="exactly 237"):
        partial, partial_meta = _build(236)
        publish_read_model(build_read_model(partial, partial_meta, source_versions={**VERSIONS, "daily": {"run_id": "daily-2"}}, published_at="t2"), tmp_path)
    assert (tmp_path / "current.json").read_text() == before


def test_failed_builder_does_not_publish(tmp_path):
    items, metadata = _build()
    publish_read_model(build_read_model(items, metadata, source_versions=VERSIONS, published_at="t1"), tmp_path)
    before = (tmp_path / "current.json").read_text()
    def failed_builder():
        raise RuntimeError("refresh failed")
    with pytest.raises(RuntimeError, match="refresh failed"):
        publish_builder_result(failed_builder, root=tmp_path, source_versions=VERSIONS, published_at="t2")
    assert (tmp_path / "current.json").read_text() == before


def test_publish_is_deterministic_and_pointer_selects_complete_version(tmp_path):
    items, metadata = _build()
    reversed_items = list(reversed(items))
    model = build_read_model(reversed_items, metadata, source_versions=VERSIONS, published_at="t1")
    result = publish_read_model(model, tmp_path)
    pointer = json.loads((tmp_path / "current.json").read_text())
    stored = json.loads((tmp_path / "versions" / pointer["path"]).read_text())
    assert result["source_version"] == stored["source_version"]
    assert [item["symbol"] for item in stored["items"]] == [item["symbol"] for item in model["items"]]


def test_load_current_read_model_rejects_missing_or_malformed_pointer(tmp_path):
    with pytest.raises((FileNotFoundError, json.JSONDecodeError)):
        load_current_read_model(tmp_path)
    (tmp_path / "current.json").write_text(json.dumps({"path": "../escape.json"}), encoding="utf-8")
    with pytest.raises(ValueError, match="pointer"):
        load_current_read_model(tmp_path)


def test_load_current_read_model_preserves_stale_and_in_flight_metadata(tmp_path):
    items, metadata = _build()
    metadata["freshness"] = {"status": "stale", "in_flight": True, "reason": "refresh_running"}
    model = build_read_model(items, metadata, source_versions=VERSIONS, published_at="t1")
    publish_read_model(model, tmp_path)
    loaded = load_current_read_model(tmp_path)
    assert loaded["freshness"] == metadata["freshness"]
    assert loaded["provenance"]["source_versions"] == VERSIONS
