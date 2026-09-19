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


def _canonical_item():
    return {
        "symbol": "ZIGA", "as_of": "2026-08-30",
        "data_status": {"sufficient": True}, "trend": {"state": "uptrend"},
        "wave": {"timeframe": "daily", "state": "WAVE_2_FORMING"},
        "setup": {"timeframe": "60m", "status": "FORMING"},
        "context": {}, "bonus_evidence": {}, "decision": "WAIT",
        "provenance": {"policy_version": "setup-candidates-v1"},
    }


def test_canonical_setup_candidate_is_primary_and_vcp_is_nested():
    from mvp_snapshot import build_mvp_snapshot

    item = _canonical_item()
    item.update({
        "group": "fresh", "status": "FRESH BREAKOUT", "action": "BUY",
        "primary_group": "fresh", "action_queue": "fresh_breakout",
        "primary_state": "fresh_breakout", "primaryState": "fresh_breakout",
        "evidence_summary": "legacy summary", "old_group_mapping": {"group": "fresh"},
        "vcp": {"is_vcp": True, "quality": "PASS"},
        "evidence": {"contraction": {"raw": True}},
    })
    primary = build_mvp_snapshot([item], run_id="run-1", scan_time="now", freshness={})["items"][0]

    assert primary["decision"] == "WAIT"
    assert all(key not in primary for key in ("group", "status", "action", "primary_group", "action_queue", "primary_state", "primaryState"))
    assert primary["bonus_evidence"]["vcp"]["is_vcp"] is True
    assert primary["bonus_evidence"]["vcp"]["raw_evidence"] == {"contraction": {"raw": True}}
    assert primary["audit"]["legacy_projection"]["action"] == "BUY"
    assert primary["audit"]["legacy_projection"]["evidence_summary"] == "legacy summary"
    assert primary["audit"]["legacy_projection"]["old_group_mapping"] == {"group": "fresh"}
    assert primary["audit"]["raw_item"]["evidence"]["contraction"]["raw"] is True


def test_canonical_artifact_load_preserves_raw_item_for_audit(tmp_path):
    from mvp_snapshot import load_mvp_artifact

    item = _canonical_item()
    item.update({"action": "BUY", "vcp": {"is_vcp": False}, "raw_observation": {"x": 1}})
    path = tmp_path / "mvp_snapshot.json"
    path.write_text(json.dumps({"contract_version": "signalix.mvp.v1", "items": [item]}), encoding="utf-8")

    loaded = load_mvp_artifact(path)["items"][0]
    assert loaded["audit"]["raw_item"]["raw_observation"] == {"x": 1}
    assert loaded["bonus_evidence"]["vcp"] == {"is_vcp": False}


def test_conflicting_top_level_vcp_is_preserved_in_audit(tmp_path):
    from mvp_snapshot import load_mvp_artifact

    item = _canonical_item()
    item.update({"vcp": {"is_vcp": True}, "bonus_evidence": {"vcp": {"is_vcp": False}}})
    path = tmp_path / "mvp_snapshot.json"
    path.write_text(json.dumps({"contract_version": "signalix.mvp.v1", "items": [item]}), encoding="utf-8")

    loaded = load_mvp_artifact(path)["items"][0]
    assert loaded["bonus_evidence"]["vcp"] == {"is_vcp": False}
    assert loaded["audit"]["legacy_vcp"] == {"is_vcp": True}


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
