"""P1-02 deep: canonical MVP snapshot contract."""


def test_build_mvp_snapshot_has_stable_root_contract():
    from mvp_snapshot import build_mvp_snapshot
    result = build_mvp_snapshot(
        [{"symbol": "PTT", "dailyEodDecision": {"source": "Daily EOD", "as_of": "2026-08-24"}}],
        run_id="run-123",
        scan_time="2026-08-24T16:10:43+00:00",
        freshness={"status": "market_closed", "source": "price_data", "as_of": "2026-08-24"},
        decision_state="official_daily",
    )
    assert result["contract_version"] == "signalix.mvp.v1"
    assert result["run_id"] == "run-123"
    assert result["decision_state"] == "official_daily"
    assert result["items"][0]["symbol"] == "PTT"
    assert "dashboard_meta" not in result


def test_load_mvp_artifact_validates_contract(tmp_path):
    import json
    from mvp_snapshot import load_mvp_artifact
    path = tmp_path / "mvp_snapshot.json"
    path.write_text(json.dumps({"contract_version": "signalix.mvp.v1", "items": []}), encoding="utf-8")
    assert load_mvp_artifact(path)["contract_version"] == "signalix.mvp.v1"


def test_build_mvp_snapshot_rejects_non_list_items():
    from mvp_snapshot import build_mvp_snapshot
    try:
        build_mvp_snapshot({}, run_id=None, scan_time=None, freshness={})
    except ValueError as exc:
        assert "items" in str(exc)
    else:
        raise AssertionError("non-list MVP items must fail closed")


def test_daily_freshness_uses_scan_run_source():
    from mvp_snapshot import daily_freshness_from_run
    result = daily_freshness_from_run(
        run_timestamp="2026-08-24T16:10:43+00:00",
        scan_date="2026-08-24",
        source_lineage={"source": "price_data", "freshness": "daily_eod_archive"},
        market_session={"status": "market_closed", "last_valid_session": "2026-08-24"},
    )
    assert result == {
        "status": "market_closed",
        "source": "price_data",
        "as_of": "2026-08-24",
        "data_fetched_at": "2026-08-24T16:10:43+00:00",
    }
