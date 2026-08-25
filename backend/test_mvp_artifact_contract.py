"""P1-05 deep: artifact lineage and mismatch gates."""

import json

import pytest


def test_mvp_snapshot_validation_rejects_run_mismatch():
    from mvp_snapshot import build_mvp_snapshot, validate_mvp_snapshot
    payload = build_mvp_snapshot([{"symbol": "PTT"}], run_id="run-new", scan_time="now", freshness={})
    validate_mvp_snapshot(payload, expected_run_id="run-new", expected_item_count=1)
    with pytest.raises(ValueError, match="run_id"):
        validate_mvp_snapshot(payload, expected_run_id="run-old", expected_item_count=1)


def test_mvp_snapshot_validation_rejects_count_mismatch():
    from mvp_snapshot import build_mvp_snapshot, validate_mvp_snapshot
    payload = build_mvp_snapshot([{"symbol": "PTT"}], run_id="run-1", scan_time="now", freshness={})
    with pytest.raises(ValueError, match="item count"):
        validate_mvp_snapshot(payload, expected_run_id="run-1", expected_item_count=904)


def test_snapshot_removes_legacy_projection_labels():
    from mvp_snapshot import build_mvp_snapshot, load_mvp_artifact

    payload = build_mvp_snapshot([{
        "symbol": "ZIGA",
        "stage": "S3_distributing",
        "phase": "topping",
        "evidence_summary": "old date",
        "old_group_mapping": {"group": "breakout_new"},
        "lifecycle_badge": "fresh_breakout",
    }], run_id="run-1", scan_time="now", freshness={})
    item = payload["items"][0]
    assert all(key not in item for key in ("evidence_summary", "old_group_mapping", "lifecycle_badge"))


def test_loaded_artifact_sanitizes_legacy_labels(tmp_path):
    from mvp_snapshot import load_mvp_artifact

    path = tmp_path / "mvp_snapshot.json"
    path.write_text(json.dumps({
        "contract_version": "signalix.mvp.v1",
        "items": [{"symbol": "ZIGA", "stage": "S3_distributing", "old_group_mapping": {"group": "breakout_new"}}],
    }), encoding="utf-8")
    item = load_mvp_artifact(path)["items"][0]
    assert "old_group_mapping" not in item


def test_artifact_manifest_records_lineage_and_hashes(tmp_path):
    from artifact_writer import write_artifact_manifest
    snapshot = tmp_path / "mvp_snapshot.json"
    html = tmp_path / "dashboard.html"
    snapshot.write_text(json.dumps({"contract_version": "signalix.mvp.v1"}), encoding="utf-8")
    html.write_text("<html></html>", encoding="utf-8")
    manifest = write_artifact_manifest(tmp_path / "manifest.json", "run-1", snapshot, html)
    assert manifest["run_id"] == "run-1"
    assert manifest["files"]["mvp_snapshot.json"]["sha256"]
    assert manifest["files"]["dashboard.html"]["bytes"] > 0
