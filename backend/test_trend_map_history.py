import json
from datetime import date, timedelta

import pytest

import shadow_trend_map
from trend_map_history import (MAX_SNAPSHOT_SESSIONS, SnapshotSelectionError,
                               TrendMapEodSnapshotStore)


def artifact(date, value=None):
    value = value if value is not None else date
    return {
        "schema_version": "daily-trend-map-shadow-read-model-v2",
        "artifact_id": f"artifact-{value}",
        "identity": {"as_of": date, "content_hash": f"content-{value}",
                      "universe_hash": "universe-1"},
        "as_of": date,
        "rows": [{"symbol": "AAA", "status": "AVAILABLE"}],
        "universe": {"scope": "marginable_long", "declared_symbols": ["AAA"],
                     "declared_count": 1, "symbol_hash": "universe-1"},
        "status": "PRODUCTION_READ_ONLY", "research_only": False,
        "actionability": "NONE", "verification_status": "VERIFIED",
        "quality": {"status": "verified"},
        "provenance": {"source": "price_data"},
    }


def publish(store, date, value=None):
    item = artifact(date, value)
    return store.publish(item, artifact_path=f"versions/{item['artifact_id']}.json",
                         is_current=date == "2026-09-18")


def test_history_retains_exactly_latest_3_sessions_and_handles_fewer_or_more(tmp_path):
    store = TrendMapEodSnapshotStore(tmp_path)
    first = date(2026, 1, 1)
    for day in range(2):
        publish(store, str(first + timedelta(days=day)))
    assert len(store.read_index()["sessions"]) == 2
    for day in range(2, 8):
        publish(store, str(first + timedelta(days=day)))
    sessions = store.read_index()["sessions"]
    assert len(sessions) == MAX_SNAPSHOT_SESSIONS == 3
    assert [item["as_of"] for item in sessions] == [
        "2026-01-08", "2026-01-07", "2026-01-06"]


def test_publish_is_immutable_and_index_update_is_atomic(tmp_path):
    store = TrendMapEodSnapshotStore(tmp_path)
    publish(store, "2026-09-18")
    original = (tmp_path / "versions/artifact-2026-09-18.json").read_bytes()
    changed = artifact("2026-09-18")
    changed["rows"][0]["status"] = "DATA_BLOCKED"
    with pytest.raises(ValueError, match="immutable"):
        store.publish(changed,
                      artifact_path="versions/artifact-2026-09-18.json",
                      is_current=True)
    assert (tmp_path / "versions/artifact-2026-09-18.json").read_bytes() == original


def test_exact_selection_and_fail_closed_reasons(tmp_path):
    store = TrendMapEodSnapshotStore(tmp_path)
    publish(store, "2026-09-17")
    assert store.select("2026-09-17")["snapshot"]["as_of"] == "2026-09-17"
    for date, reason in (("2026-09-16", "snapshot_not_found"),
                         ("not-a-date", "invalid_snapshot_date")):
        with pytest.raises(SnapshotSelectionError, match=reason):
            store.select(date)


@pytest.mark.parametrize("mutation, reason", [
    (lambda root: (root / "versions/artifact-2026-09-17.json").write_text("bad"), "corrupt"),
    (lambda root: _mismatch(root), "mismatch"),
    (lambda root: _stale(root), "stale"),
])
def test_invalid_selected_entry_never_falls_back_to_current(tmp_path, mutation, reason):
    store = TrendMapEodSnapshotStore(tmp_path)
    publish(store, "2026-09-18")
    publish(store, "2026-09-17")
    mutation(tmp_path)
    with pytest.raises(SnapshotSelectionError, match=reason):
        store.select("2026-09-17")


def _mismatch(root):
    index = json.loads((root / "snapshots.json").read_text())
    index["sessions"][-1]["artifact_id"] = "wrong"
    (root / "snapshots.json").write_text(json.dumps(index))


def _stale(root):
    index = json.loads((root / "snapshots.json").read_text())
    index["sessions"][-1]["artifact_path"] = "versions/missing.json"
    (root / "snapshots.json").write_text(json.dumps(index))


def test_historical_metadata_preserves_universe_and_no_history_callback(tmp_path):
    store = TrendMapEodSnapshotStore(tmp_path)
    item = artifact("2026-09-17")
    item["universe"]["declared_symbols"] = ["AAA", "BBB"]
    item["universe"]["declared_count"] = 2
    store.publish(item, artifact_path="versions/artifact-2026-09-17.json")
    selected = store.select("2026-09-17")["snapshot"]
    assert selected["kind"] == "historical"
    assert selected["universe"] == item["universe"]
    assert selected["row_count"] == 1


def test_api_selector_is_explicit_and_does_not_use_current_fallback(monkeypatch):
    calls = []

    class Handler:
        def send_bytes(self, body, **kwargs):
            self.payload = json.loads(body)

    def selected(**kwargs):
        calls.append(kwargs)
        return {"status": "PRODUCTION_READ_ONLY", "research_only": False,
                "actionability": "NONE", "rows": [], "snapshot": {"kind": "historical"}}

    monkeypatch.setattr(shadow_trend_map, "build_shadow_report", selected)
    handler = Handler()
    assert shadow_trend_map.handle_shadow_trend_map_api(
        "/api/trend-map?snapshot_date=2026-09-17", handler)
    assert calls == [{"snapshot_date": "2026-09-17"}]
    assert handler.payload["snapshot"]["kind"] == "historical"
