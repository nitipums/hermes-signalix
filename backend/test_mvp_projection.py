"""P1-02 contract: canonical MVP projection boundary."""


def test_projection_exposes_mvp_contract_without_legacy_root_shape():
    import mvp_projection
    result = mvp_projection.project_legacy_snapshot({
        "scan_time": "2026-08-24T16:10:43+00:00",
        "data_freshness_status": "market_closed",
        "items": [{"symbol": "PTT", "dailyEodDecision": {"source": "Daily EOD", "as_of": "2026-08-24"}}],
    })
    assert result["contract_version"] == "signalix.mvp.v1"
    assert result["items"][0]["symbol"] == "PTT"
    assert result["freshness"]["status"] == "market_closed"
    assert "dashboard_meta" not in result


def test_legacy_projection_is_explicitly_audit_only_for_one_day():
    import mvp_projection

    result = mvp_projection.project_legacy_snapshot({"items": []})

    assert result["audit_only"] is True
    assert result["deprecation"] == mvp_projection.COMPATIBILITY_DEPRECATION
    assert result["deprecation"]["boundary"] == "one_day"


def test_mvp_uses_canonical_provenance_resolver():
    import mvp_api
    import provenance_contract
    assert mvp_api.resolve_decision_state is provenance_contract.resolve_decision_state


def test_projection_fails_closed_when_items_missing():
    import mvp_projection
    try:
        mvp_projection.project_legacy_snapshot({"scan_time": "x"})
    except ValueError as exc:
        assert "items" in str(exc)
    else:
        raise AssertionError("missing items must fail closed")
