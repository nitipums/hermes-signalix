import json
import threading
import time
from pathlib import Path

import pytest

from read_model_publisher import (build_read_model, load_current_read_model,
                                  load_intraday_metadata, publish_builder_result,
                                  publish_intraday_metadata, publish_read_model,
                                  DEFAULT_ROOT, UniverseIdentity)


def test_default_root_is_shared_backend_read_model_path():
    assert DEFAULT_ROOT == Path(__file__).resolve().parent / "read-model"


def test_intraday_metadata_sidecar_is_atomic_and_round_trips_product_identity(tmp_path):
    metadata = publish_intraday_metadata({
        "run_id": "run-1", "status": "full_success",
        "fetch_completed_at": "2026-09-02T09:00:00+00:00",
        "universe": "marginable_long", "published_at": "pub-1",
    }, tmp_path)
    assert metadata["path"].endswith("intraday-latest.json")
    assert load_intraday_metadata(tmp_path) == {
        "schema_version": "signalix.intraday-metadata.v1", "run_id": "run-1",
        "status": "full_success", "fetch_completed_at": "2026-09-02T09:00:00+00:00",
        "universe": "marginable_long", "published_at": "pub-1",
    }


def test_intraday_metadata_sidecar_rejects_audit_or_legacy_identity(tmp_path):
    with pytest.raises(ValueError, match="only marginable_long"):
        publish_intraday_metadata({"run_id": "audit", "status": "full_success",
                                   "fetch_completed_at": "t", "universe": "active_ord"}, tmp_path)
    (tmp_path / "intraday-latest.json").write_text(
        json.dumps({"run_id": "legacy", "status": "full_success",
                    "fetch_completed_at": "t", "universe": None}), encoding="utf-8")
    assert load_intraday_metadata(tmp_path) is None


def _item(symbol, lane="WAIT"):
    return {
        "symbol": symbol, "as_of": "2026-09-01T00:00:00", "data_status": {"sufficient": True, "freshness": "fresh"},
        "trend": {}, "wave": {"primary_state": "UNKNOWN", "confidence": "LOW"},
        "setup": {"status": "FORMING"}, "context": {}, "bonus_evidence": {}, "decision_lane": lane,
        "provenance": {"policy_version": "setup-candidates-v1", "source": "price_data+intraday_price_data", "as_of": "2026-09-01", "freshness": "fresh"},
    }


def _build(count=237):
    items = [_item(f"S{n:03d}") for n in range(count)]
    return items, {"universe_filter": "marginable_long", "base_active_ord_count": count + 694,
                   "eligible_count": count, "excluded_count": 694,
                   "scan_time": "2026-09-01", "freshness": {"status": "fresh"}}


def test_build_rejects_missing_canonical_universe_identity():
    items, metadata = _build()
    for field in ("base_active_ord_count", "eligible_count", "excluded_count"):
        incomplete = {key: value for key, value in metadata.items() if key != field}
        with pytest.raises(ValueError, match="required"):
            build_read_model(items, incomplete, source_versions=VERSIONS, published_at="t1")


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


def test_explicit_small_universe_scope_validates_without_runtime_count_constant(tmp_path):
    items, metadata = _build(3)
    metadata.update({
        "base_active_ord_count": 5,
        "excluded_count": 2,
        "schema_version": "test-universe-v1",
        "source_document": "test-manifest.json",
        "effective_date": "2026-09-02",
    })
    model = build_read_model(items, metadata, source_versions=VERSIONS, published_at="t1")
    assert model["universe"] == "marginable_long"
    assert model["count"] == model["evaluated_count"] == model["eligible_count"] == 3
    assert model["base_active_ord_count"] == 5
    assert model["universe_metadata"] == {
        "schema_version": "test-universe-v1",
        "source_document": "test-manifest.json",
        "effective_date": "2026-09-02",
    }
    publish_read_model(model, tmp_path)
    loaded = load_current_read_model(tmp_path)
    assert loaded["evaluated_count"] == 3


def test_universe_identity_is_immutable_and_scope_count_mismatch_fails_closed():
    scope = UniverseIdentity("marginable_long", 2, 2, 3, 1, "v1", "source", "2026-09-02")
    with pytest.raises((AttributeError, TypeError)):
        scope.evaluated_count = 3
    items, metadata = _build(2)
    metadata["eligible_count"] = 3
    metadata["base_active_ord_count"] = 697
    with pytest.raises(ValueError, match="exactly 3"):
        build_read_model(items, metadata, source_versions=VERSIONS, published_at="t1")


def test_active_ord_read_model_is_rejected_at_canonical_publication_seam():
    items, metadata = _build(2)
    metadata["universe_filter"] = "active_ord"
    with pytest.raises(ValueError, match="marginable_long"):
        build_read_model(items, metadata, source_versions=VERSIONS, published_at="t1")


def test_read_model_preserves_canonical_daily_metadata_through_validation(tmp_path):
    items, metadata = _build()
    items[0].update({
        "high52": 72, "low52": 41, "ath_high": 89, "ath_low": 12,
        "index_membership": ["SET50"],
        "index_membership_evidence": {"source": "set-index"},
    })

    model = build_read_model(items, metadata, source_versions=VERSIONS, published_at="t1")
    publish_read_model(model, tmp_path)
    loaded = load_current_read_model(tmp_path)

    item = next(row for row in loaded["items"] if row["symbol"] == "S000")
    assert item["high52"] == 72
    assert item["low52"] == 41
    assert item["ath_high"] == 89
    assert item["ath_low"] == 12
    assert item["index_membership"] == ["SET50"]
    assert item["index_membership_evidence"] == {"source": "set-index"}


def test_partial_build_rejected_before_existing_pointer_changes(tmp_path):
    items, metadata = _build()
    model = build_read_model(items, metadata, source_versions=VERSIONS, published_at="t1")
    publish_read_model(model, tmp_path)
    before = (tmp_path / "current.json").read_text()
    with pytest.raises(ValueError, match="exactly 237"):
        partial, partial_meta = _build(236)
        partial_meta["eligible_count"] = 237
        partial_meta["base_active_ord_count"] = 931
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


def test_repeated_loads_cache_validated_model_and_prevent_mutation(tmp_path, monkeypatch):
    items, metadata = _build()
    publish_read_model(build_read_model(items, metadata, source_versions=VERSIONS, published_at="t1"), tmp_path)
    import read_model_publisher as publisher
    calls = {"validate": 0, "version_read": 0}
    original_validate = publisher._validate_build
    original_read_text = Path.read_text

    def counted_validate(*args, **kwargs):
        calls["validate"] += 1
        return original_validate(*args, **kwargs)

    def counted_read_text(path, *args, **kwargs):
        if path.name != "current.json":
            calls["version_read"] += 1
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(publisher, "_validate_build", counted_validate)
    monkeypatch.setattr(Path, "read_text", counted_read_text)
    first = load_current_read_model(tmp_path)
    second = load_current_read_model(tmp_path)
    assert first is second
    assert calls == {"validate": 1, "version_read": 1}
    with pytest.raises(TypeError):
        first["items"][0] = {}
    with pytest.raises(TypeError):
        first["items"][0]["symbol"] = "MUTATED"


def test_pointer_change_invalidates_cached_model(tmp_path):
    items, metadata = _build()
    first_model = build_read_model(items, metadata, source_versions=VERSIONS, published_at="t1")
    publish_read_model(first_model, tmp_path)
    first = load_current_read_model(tmp_path)
    changed_versions = {**VERSIONS, "intraday": {"run_id": "60m-2", "as_of": VERSIONS["intraday"]["as_of"]}}
    second_model = build_read_model(items, metadata, source_versions=changed_versions, published_at="t2")
    publish_read_model(second_model, tmp_path)
    second = load_current_read_model(tmp_path)
    assert second is not first
    assert second["source_version"] != first["source_version"]
    assert load_current_read_model(tmp_path) is second


def test_cached_model_does_not_mask_malformed_or_missing_pointer(tmp_path):
    items, metadata = _build()
    publish_read_model(build_read_model(items, metadata, source_versions=VERSIONS, published_at="t1"), tmp_path)
    load_current_read_model(tmp_path)
    pointer_path = tmp_path / "current.json"
    pointer_path.unlink()
    with pytest.raises(FileNotFoundError):
        load_current_read_model(tmp_path)
    pointer_path.write_text(json.dumps({"contract_version": "wrong"}), encoding="utf-8")
    with pytest.raises(ValueError, match="pointer"):
        load_current_read_model(tmp_path)


def test_concurrent_cache_misses_coalesce_to_one_validation(tmp_path, monkeypatch):
    items, metadata = _build()
    publish_read_model(build_read_model(items, metadata, source_versions=VERSIONS, published_at="t1"), tmp_path)
    import read_model_publisher as publisher
    calls = 0
    original_validate = publisher._validate_build

    def counted_validate(*args, **kwargs):
        nonlocal calls
        calls += 1
        time.sleep(0.02)
        return original_validate(*args, **kwargs)

    monkeypatch.setattr(publisher, "_validate_build", counted_validate)
    barrier = threading.Barrier(4)
    results = []

    def read():
        barrier.wait()
        results.append(load_current_read_model(tmp_path))

    threads = [threading.Thread(target=read) for _ in range(3)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert calls == 1
    assert len(results) == 3
    assert all(result is results[0] for result in results)
