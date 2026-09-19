import json
from pathlib import Path

import pytest

import shadow_read_model_publisher as publisher
import shadow_trend_map as trend_map
import update_data


def bars(count=75):
    return [{"date": f"2026-01-{(i % 28) + 1:02d}", "open": 99 + i,
             "high": 101 + i, "low": 98 + i, "close": 100 + i, "volume": 1000}
            for i in range(count)]


class Adapter:
    def resolve_universe(self, conn, value):
        return ["AAA", "BBB", "CCC"], {"universe_filter": value, "eligible_count": 3}

    def _exec_select(self, conn, sql, params=None):
        return [("2026-09-11",)], ["max_date"]

    def load_daily_pit_batch(self, conn, symbols, as_of):
        return {"AAA": (bars(75), as_of), "BBB": ([], None), "CCC": (bars(2), as_of)}


def publish(tmp_path):
    return publisher.publish_shadow_read_model(
        adapter=Adapter(), conn=object(), as_of="2026-09-11", root=tmp_path,
        published_at="2026-09-12T01:00:00+00:00")


def test_publisher_writes_version_pointer_and_full_counts(tmp_path):
    result = publish(tmp_path)
    assert result["counts"] == {"declared": 3, "evaluated": 3, "returned": 3, "blocked": 2}
    pointer = json.loads((tmp_path / "current.json").read_text())
    artifact = json.loads((tmp_path / pointer["artifact_path"]).read_text())
    assert pointer["artifact_id"] == artifact["artifact_id"]
    assert artifact["identity"]["as_of"] == "2026-09-11"
    assert artifact["status"] == trend_map.PRODUCTION_READ_ONLY
    assert artifact["research_only"] is False
    assert artifact["actionability"] == "NONE"
    assert artifact["identity"]["policy_hash"] == artifact["policy"]["hash"]
    assert artifact["universe"]["scope"] == "marginable_long"
    assert artifact["provenance"]["query_mode"] == "SELECT_ONLY"
    assert len(artifact["rows"]) == 3
    quote = next(row for row in artifact["rows"] if row["symbol"] == "AAA")["quote"]
    assert quote["price"] == 174
    assert quote["change_amount"] == 1
    assert quote["change_pct"] == pytest.approx(100 / 173)
    assert quote["change_basis"] == "previous_daily_close"
    assert quote["provenance"]["source"] == "price_data"
    assert quote["provenance"]["timeframe"] == "1D"
    assert next(row for row in artifact["rows"] if row["symbol"] == "BBB")["quote"]["availability"] == "NOT_VERIFIED"
    assert artifact["identity"]["representation_revision"] == trend_map.REPRESENTATION_REVISION
    assert pointer["representation_revision"] == trend_map.REPRESENTATION_REVISION
    for key in ("db_read_ms", "classify_ms", "serialize_write_ms", "total_ms"):
        assert isinstance(artifact["timing"][key], (int, float))
        assert artifact["timing"][key] >= 0
    assert artifact["timing"]["measurement_scope"] == "pre_immutable_write"


def test_quote_representation_revision_avoids_legacy_identity_collision(tmp_path):
    publish(tmp_path)
    current_pointer = json.loads((tmp_path / "current.json").read_text())
    current_artifact_path = tmp_path / current_pointer["artifact_path"]
    current_artifact = json.loads(current_artifact_path.read_text())

    legacy_artifact = dict(current_artifact)
    legacy_artifact["schema_version"] = "daily-trend-map-shadow-read-model-v1"
    legacy_artifact["artifact_id"] = (
        f"shadow-trend-map-{legacy_artifact['as_of']}-"
        f"{legacy_artifact['identity']['policy_hash'][:16]}-"
        f"{legacy_artifact['identity']['universe_hash'][:16]}"
    )
    legacy_artifact["identity"] = dict(legacy_artifact["identity"])
    legacy_artifact["identity"].pop("representation_revision")
    legacy_artifact["policy"] = dict(legacy_artifact["policy"])
    legacy_artifact["policy"].pop("representation_revision")
    for row in legacy_artifact["rows"]:
        row.pop("quote")
    legacy_path = tmp_path / "versions" / f"{legacy_artifact['artifact_id']}.json"
    legacy_path.write_bytes(publisher._json_bytes(legacy_artifact))
    legacy_bytes = legacy_path.read_bytes()

    result = publish(tmp_path)
    assert result["artifact_id"] != legacy_artifact["artifact_id"]
    assert legacy_path.read_bytes() == legacy_bytes
    assert len(list((tmp_path / "versions").glob("*.json"))) == 3
    new_artifact = json.loads((tmp_path / result["artifact_path"]).read_text())
    assert new_artifact["identity"]["representation_revision"] == trend_map.REPRESENTATION_REVISION
    assert all("quote" in row for row in new_artifact["rows"])


def test_publisher_rejects_invalid_quote_envelope_and_basis(tmp_path):
    original = trend_map.build_shadow_report

    def invalid_report(**kwargs):
        report = original(adapter=Adapter(), conn=object(), as_of="2026-09-11", source="publisher")
        report["rows"][0]["quote"]["provenance"]["timeframe"] = "60m"
        report["rows"][0]["quote"]["change_basis"] = "intraday_close"
        return report

    import pytest
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(trend_map, "build_shadow_report", invalid_report)
    try:
        with pytest.raises(ValueError, match="quote"):
            publisher.publish_shadow_read_model(root=tmp_path)
    finally:
        monkeypatch.undo()
    assert not (tmp_path / "current.json").exists()


@pytest.mark.parametrize("field,value", [
    ("status", "READ_ONLY_SHADOW"),
    ("research_only", True),
    ("actionability", "BUY_NOW"),
])
def test_publisher_rejects_legacy_or_actionable_report_semantics(tmp_path, monkeypatch, field, value):
    original = trend_map.build_shadow_report

    def invalid_report(**kwargs):
        report = original(adapter=Adapter(), conn=object(), as_of="2026-09-11", source="publisher")
        report[field] = value
        return report

    monkeypatch.setattr(trend_map, "build_shadow_report", invalid_report)
    with pytest.raises((ValueError, RuntimeError), match="(policy|fully verified)"):
        publisher.publish_shadow_read_model(root=tmp_path)


def test_publisher_rejects_cap_hit_positive_classification(tmp_path, monkeypatch):
    original = trend_map.build_shadow_report

    def unsafe_report(**kwargs):
        report = original(adapter=Adapter(), conn=object(), as_of="2026-09-11", source="publisher")
        row = report["rows"][0]
        row["retrieval_cap_reached"] = True
        row["cap_reached"] = True
        row["status"] = "AVAILABLE"
        row["data_quality_status"] = "AVAILABLE"
        row["quality_established"] = False
        return report

    monkeypatch.setattr(trend_map, "build_shadow_report", unsafe_report)
    with pytest.raises(ValueError, match="cap-hit"):
        publisher.publish_shadow_read_model(root=tmp_path)
    assert not (tmp_path / "current.json").exists()


def test_publisher_allows_cap_hit_available_only_with_established_zero_invalid_quality(tmp_path, monkeypatch):
    original = trend_map.build_shadow_report

    def safe_report(**kwargs):
        report = original(adapter=Adapter(), conn=object(), as_of="2026-09-11", source="publisher")
        row = report["rows"][0]
        row.update({"retrieval_cap_reached": True, "cap_reached": True, "status": "AVAILABLE",
                    "data_quality_status": "AVAILABLE", "quality_established": True,
                    "invalid_count": 0, "full_history_claim": False})
        return report

    monkeypatch.setattr(trend_map, "build_shadow_report", safe_report)
    result = publisher.publish_shadow_read_model(root=tmp_path)
    assert result["counts"]["blocked"] == 2


def test_existing_version_cannot_be_overwritten_with_different_content(tmp_path):
    publish(tmp_path)
    original_paths = list((tmp_path / "versions").glob("*.json"))
    original = original_paths[0].read_bytes()
    changed = Adapter()
    changed.load_daily_pit_batch = lambda conn, symbols, as_of: {"AAA": (bars(76), as_of), "BBB": ([], None), "CCC": (bars(2), as_of)}
    result = publisher.publish_shadow_read_model(adapter=changed, conn=object(), as_of="2026-09-11", root=tmp_path, published_at="2026-09-12T02:00:00+00:00")
    assert result["artifact_id"] != json.loads(original_paths[0].read_text())["artifact_id"]
    assert original_paths[0].read_bytes() == original


def test_repeated_publish_with_new_measurement_does_not_collide(tmp_path):
    first = publish(tmp_path)
    second = publisher.publish_shadow_read_model(adapter=Adapter(), conn=object(), as_of="2026-09-11", root=tmp_path,
                                                  published_at="2026-09-12T02:00:00+00:00")
    assert first["artifact_id"] != second["artifact_id"]
    assert Path(first["artifact_path"]).read_bytes() != Path(second["artifact_path"]).read_bytes()
    assert publisher.read_current_shadow_report(tmp_path)["timing"] == second["timing"]


def test_pointer_readback_missing_corrupt_and_mismatched_are_blocked(tmp_path):
    missing = publisher.read_current_shadow_report(tmp_path)
    assert missing["status"] == "DATA_BLOCKED" and missing["rows"] == []
    publish(tmp_path)
    loaded = publisher.read_current_shadow_report(tmp_path)
    assert loaded["artifact"]["id"] == loaded["artifact_id"]
    (tmp_path / "current.json").write_text("not json")
    assert publisher.read_current_shadow_report(tmp_path)["verification_status"] == "NOT_VERIFIED"
    publish(tmp_path)
    pointer = json.loads((tmp_path / "current.json").read_text())
    pointer["policy_hash"] = "stale"
    (tmp_path / "current.json").write_text(json.dumps(pointer))
    blocked = publisher.read_current_shadow_report(tmp_path)
    assert blocked["status"] == "DATA_BLOCKED" and blocked["rows"] == []


def test_pointer_readback_rejects_persisted_content_and_measurement_tampering(tmp_path):
    publish(tmp_path)
    pointer = json.loads((tmp_path / "current.json").read_text())
    artifact_path = tmp_path / pointer["artifact_path"]
    artifact = json.loads(artifact_path.read_text())
    artifact["rows"][0]["quote"]["price"] += 1
    artifact_path.write_bytes(publisher._json_bytes(artifact))
    blocked = publisher.read_current_shadow_report(tmp_path)
    assert blocked["status"] == "DATA_BLOCKED"
    assert blocked["verification_status"] == "NOT_VERIFIED"
    assert blocked["rows"] == []

    publish(tmp_path)
    pointer = json.loads((tmp_path / "current.json").read_text())
    artifact_path = tmp_path / pointer["artifact_path"]
    artifact = json.loads(artifact_path.read_text())
    artifact["timing"]["total_ms"] += 1
    artifact_path.write_bytes(publisher._json_bytes(artifact))
    blocked = publisher.read_current_shadow_report(tmp_path)
    assert blocked["status"] == "DATA_BLOCKED"
    assert blocked["verification_status"] == "NOT_VERIFIED"
    assert blocked["rows"] == []


def test_pointer_change_is_observed_without_process_restart(tmp_path):
    first = publish(tmp_path)
    first_read = publisher.read_current_shadow_report(tmp_path)
    second = publisher.publish_shadow_read_model(adapter=Adapter(), conn=object(), as_of="2026-09-12", root=tmp_path,
                                                  published_at="2026-09-12T02:00:00+00:00")
    second_read = publisher.read_current_shadow_report(tmp_path)
    assert first["artifact_id"] != second["artifact_id"]
    assert first_read["artifact_id"] != second_read["artifact_id"]
    assert second_read["as_of"] == "2026-09-12"
    assert all(isinstance(second_read["timing"][key], (int, float))
               for key in ("db_read_ms", "classify_ms", "serialize_write_ms", "total_ms"))
    assert second_read["read_path"]["latency_ms"] >= 0


def test_stale_artifact_is_not_verified_and_returns_no_rows(tmp_path, monkeypatch):
    publish(tmp_path)
    monkeypatch.setenv("SIGNALIX_SHADOW_STALE_AFTER_SECONDS", "0")
    stale = publisher.read_current_shadow_report(tmp_path)
    assert stale["status"] == "DATA_BLOCKED"
    assert stale["verification_status"] == "NOT_VERIFIED"
    assert stale["rows"] == []
    assert stale["freshness"]["status"] == "STALE"


def test_publisher_reports_timing_metrics(tmp_path):
    result = publish(tmp_path)
    assert set(("db_read_ms", "classify_ms", "serialize_write_ms", "total_ms")) <= set(result["timing"])
    assert result["timing"]["total_ms"] >= 0
    loaded = publisher.read_current_shadow_report(tmp_path)
    assert loaded["timing"] == result["timing"]
    assert loaded["read_path"]["latency_ms"] >= 0


def test_api_default_path_never_invokes_classifier_or_history(monkeypatch, tmp_path):
    publish(tmp_path)
    monkeypatch.setenv("SIGNALIX_SHADOW_READ_MODEL_ROOT", str(tmp_path))
    monkeypatch.setattr(trend_map, "classify_daily_trend", lambda *_: (_ for _ in ()).throw(AssertionError("classifier called")))
    monkeypatch.setattr(trend_map.BackendDailyAdapter, "load_daily_pit_batch", lambda *args: (_ for _ in ()).throw(AssertionError("history queried")))
    result = trend_map.build_shadow_report()
    assert result["artifact"]["id"]
    assert result["counts"] == {"declared": 3, "evaluated": 3, "returned": 3, "blocked": 2}


def test_publisher_rejects_unverified_or_incomplete_build(tmp_path, monkeypatch):
    monkeypatch.setattr(trend_map, "build_shadow_report", lambda **kwargs: {"status": "DATA_BLOCKED", "verification_status": "NOT_VERIFIED"})
    try:
        publisher.publish_shadow_read_model(root=tmp_path)
    except RuntimeError as error:
        assert "fully verified" in str(error)
    else:
        raise AssertionError("unverified report was published")
    assert not (tmp_path / "current.json").exists()


def test_eod_hook_publishes_only_on_successful_scan_path(monkeypatch):
    calls = []
    monkeypatch.setattr(update_data, "publish_canonical_read_model", lambda: calls.append("canonical"))
    monkeypatch.setattr(update_data, "json", json)
    monkeypatch.setitem(__import__("sys").modules, "shadow_read_model_publisher", type("Publisher", (), {
        "publish_shadow_read_model": staticmethod(lambda: calls.append("shadow") or {"artifact_id": "v1"}),
    }))

    class Args:
        scan = True
        dry_run = False
    assert update_data._finish_successful_run(Args()) == 0
    assert calls == ["canonical", "shadow"]

    calls.clear()
    Args.scan = False
    assert update_data._finish_successful_run(Args()) == 0
    assert calls == []


def test_eod_shadow_publish_failure_is_structured_and_nonfatal(monkeypatch, capsys):
    monkeypatch.setattr(update_data, "publish_canonical_read_model", lambda: None)
    monkeypatch.setitem(__import__("sys").modules, "shadow_read_model_publisher", type("Publisher", (), {
        "publish_shadow_read_model": staticmethod(lambda: (_ for _ in ()).throw(ValueError("bad artifact"))),
    }))
    update_data.SHADOW_TREND_MAP_PUBLISH_FAILURES = 0
    class Args:
        scan = True
        dry_run = False
    assert update_data._finish_successful_run(Args()) == 0
    assert update_data.SHADOW_TREND_MAP_PUBLISH_FAILURES == 1
    event = json.loads(capsys.readouterr().out.split(" ", 1)[1])
    assert event["event"] == "shadow_trend_map_publish_failure"
    assert event["error_type"] == "ValueError"
    assert event["pointer_preserved"] is False
    assert event["pointer_verification"] == "NOT_VERIFIED"


def test_publish_failure_sidecar_is_bounded_and_read_only(tmp_path):
    metadata = publisher.record_publish_failure(tmp_path, ValueError("bad artifact"), 2, True, "VERIFIED")
    assert metadata["pointer_preserved"] is True
    loaded = publisher.read_current_shadow_report(tmp_path)
    assert loaded["last_failure"]["failure_count"] == 2
    assert loaded["last_failure"]["message"] == "bad artifact"
