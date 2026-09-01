import json
from decimal import Decimal

import numpy as np

from setup_candidate_contract import (
    _setup_evidence_markers,
    build_peer_context,
    build_setup_candidate,
    project_setup_candidate_list,
)
from trade_setup_engine import build_trade_setup


def sample_inputs():
    return {
        "symbol": "ABC",
        "as_of": "2026-08-30",
        "data_status": {"sufficient": True, "freshness": "fresh", "source": "daily_eod+60m"},
        "trend": {"state": "uptrend", "rise_20d_pct": 18.4, "relative_strength": 91},
        "wave": {"state": "WAVE_2_NEAR_COMPLETION", "confidence": "PARTIAL", "evidence": {}},
        "setup": {"state": "EARLY_WAVE_3", "status": "PRE_TRIGGER", "trigger": 12.5},
        "context": build_peer_context("ABC", {"sector": "Tech", "industry": "Components"}),
        "bonus_evidence": {"vcp": {"present": False}},
        "provenance": {"policy_version": "setup-candidates-v1", "daily_source": "eod"},
    }


def test_candidate_contract_keeps_layers_separate():
    item = build_setup_candidate(**sample_inputs())
    assert set(("symbol", "as_of", "data_status", "trend", "wave", "setup",
                "context", "bonus_evidence", "decision_lane", "provenance")) == set(item)
    assert item["wave"]["timeframe"] == "daily"
    assert item["setup"]["timeframe"] == "60m"
    assert item["decision_lane"] == "DAILY_CANDIDATE"
    assert "decision" not in item
    json.dumps(item)


def test_60m_marker_timestamp_uses_chart_datetime_form():
    markers = _setup_evidence_markers(
        {"trigger": 12.5, "trigger_timestamp": "2026-01-02 11:00:00"},
        {}, {},
    )
    assert markers[0]["timestamp"] == "2026-01-02T11:00:00"


def test_candidate_preserves_timeframe_mismatches_and_blocks_them():
    inputs = sample_inputs()
    inputs["wave"] = {"timeframe": "60m", "state": "WAVE_2_NEAR_COMPLETION"}
    inputs["setup"] = {"timeframe": "15m", "status": "PRE_TRIGGER"}
    item = build_setup_candidate(**inputs)
    assert item["wave"]["timeframe"] == "60m"
    assert item["setup"]["timeframe"] == "15m"
    assert item["decision_lane"] == "DATA_BLOCKED"


def test_missing_timeframes_are_defaulted_by_contract_construction():
    inputs = sample_inputs()
    inputs["wave"].pop("timeframe", None)
    inputs["setup"].pop("timeframe", None)
    item = build_setup_candidate(**inputs)
    assert item["wave"]["timeframe"] == "daily"
    assert item["setup"]["timeframe"] == "60m"


def test_non_unknown_wave_always_has_three_evidence_arrays():
    inputs = sample_inputs()
    inputs["wave"] = {"state": "WAVE_1_ADVANCE", "confidence": "MEDIUM"}

    wave = build_setup_candidate(**inputs)["wave"]

    assert wave["primary_state"] == "WAVE_1_ADVANCE"
    assert wave["supporting_evidence"] == []
    assert wave["contradicting_evidence"] == []
    assert wave["missing_evidence"] == []


def test_peer_context_derives_breadth_breakouts_and_leadership():
    context = build_peer_context("ABC", {
        "sector": "Technology", "industry": "Components",
        "peers": [
            {"symbol": "AAA", "state": "uptrend", "is_52w_high_breakout": True},
            {"symbol": "BBB", "state": "uptrend", "is_52w_high_breakout": False},
            {"symbol": "CCC", "state": "downtrend", "is_52w_high_breakout": True},
        ],
        "sector_leadership": "LEADER",
        "relative_strength_vs_sector": 7.2,
    })
    assert context["sector"] == "Technology"
    assert context["industry"] == "Components"
    assert context["peer_trend_breadth"] == "2/3"
    assert context["peer_breakout_count"] == 2
    assert context["sector_leader_or_laggard"] == "LEADER"


def test_missing_peer_context_is_explicit_and_non_gating():
    inputs = sample_inputs()
    inputs["context"] = build_peer_context("ABC")
    item = build_setup_candidate(**inputs)
    assert item["context"]["peer_data_status"] == "UNKNOWN"
    assert item["context"]["peer_trend_breadth"] is None
    assert item["context"]["peer_symbols"] == []
    assert item["decision_lane"] == "DAILY_CANDIDATE"


def test_decision_mapping_fails_closed_and_keeps_vcp_as_bonus():
    blocked = sample_inputs()
    blocked["data_status"] = {"sufficient": False, "freshness": "unknown"}
    assert build_setup_candidate(**blocked)["decision_lane"] == "DATA_BLOCKED"

    waiting = sample_inputs()
    waiting["setup"] = {"timeframe": "60m", "state": "EARLY_WAVE_3", "status": "FORMING"}
    assert build_setup_candidate(**waiting)["decision_lane"] == "DAILY_CANDIDATE"

    avoided = sample_inputs()
    avoided["setup"] = {"timeframe": "60m", "state": "EARLY_WAVE_3", "status": "INVALIDATED"}
    assert build_setup_candidate(**avoided)["decision_lane"] == "AVOID"

    non_vcp = sample_inputs()
    non_vcp["bonus_evidence"] = {"vcp": {"present": False}}
    assert build_setup_candidate(**non_vcp)["decision_lane"] == "DAILY_CANDIDATE"


def test_lane_plan_requires_ordered_target_1_and_never_uses_target_2_only():
    base = sample_inputs()
    base["wave"] = {"state": "WAVE_2_NEAR_COMPLETION", "confidence": "HIGH", "evidence": {}}
    base["setup"] = {
        "timeframe": "60m", "status": "PRE_TRIGGER", "trigger": 12.5,
        "invalidation": 10.0, "rr": {"to_target_1": 3.0},
        "targets": [{"name": "target_1", "price": 20.0},
                    {"name": "target_2", "price": 25.0}],
        "target_1": 20.0,
    }
    assert build_setup_candidate(**base)["decision_lane"] == "REVIEW_NOW"

    for targets, target_1 in (
        ([{"name": "target_2", "price": 25.0}], None),
        ([{"name": "target_2", "price": 25.0}], 20.0),
        ([{"name": "target_1", "price": "not-a-price"}], "not-a-price"),
        ([{"name": "target_2", "price": 25.0}, {"name": "target_1", "price": 20.0}], 20.0),
    ):
        blocked_plan = dict(base["setup"], targets=targets, target_1=target_1)
        result = build_setup_candidate(**dict(base, setup=blocked_plan))
        assert result["decision_lane"] == "DAILY_CANDIDATE"


def test_legacy_scalar_targets_remain_compatible_without_downgrading_mixed_targets():
    base = sample_inputs()
    base["wave"] = {"state": "WAVE_2_NEAR_COMPLETION", "confidence": "HIGH", "evidence": {}}
    legacy_setup = {
        "timeframe": "60m", "status": "PRE_TRIGGER", "trigger": 100,
        "invalidation": 90, "targets": [120], "rr": {"to_target_1": 2.0},
    }
    assert build_setup_candidate(**dict(base, setup=legacy_setup))["decision_lane"] == "REVIEW_NOW"

    mixed_setup = dict(legacy_setup, targets=[120, {"name": "target_2", "price": 130}])
    assert build_setup_candidate(**dict(base, setup=mixed_setup))["decision_lane"] == "DAILY_CANDIDATE"


def test_explicit_failed_structure_and_risk_statuses_avoid():
    for status in ("FAILED", "BROKEN", "DO_NOT_CHASE", "FAILED_STRUCTURE"):
        inputs = sample_inputs()
        inputs["setup"] = {"status": status}
        assert build_setup_candidate(**inputs)["decision_lane"] == "AVOID"
    inputs = sample_inputs()
    inputs["setup"] = {"status": "FORMING", "risk_status": "RISK_FAILED"}
    assert build_setup_candidate(**inputs)["decision_lane"] == "AVOID"


def test_failed_setup_status_token_variants_avoid():
    for status in ("DO-NOT-CHASE", "FAILED STRUCTURE"):
        inputs = sample_inputs()
        inputs["setup"] = {"status": status}
        assert build_setup_candidate(**inputs)["decision_lane"] == "AVOID"


def test_blocked_data_precedes_failed_statuses():
    inputs = sample_inputs()
    inputs["data_status"] = {"sufficient": False, "freshness": "stale"}
    inputs["setup"] = {"status": "DO_NOT_CHASE"}
    assert build_setup_candidate(**inputs)["decision_lane"] == "DATA_BLOCKED"


def test_reason_codes_project_no_setup_and_invalid_risk_without_text_matching():
    no_setup = sample_inputs()
    no_setup["setup"] = {"status": "FORMING", "reason_code": "NO_SETUP_DETECTED",
                         "reason": "localized display text"}
    assert build_setup_candidate(**no_setup)["decision_lane"] == "DAILY_CANDIDATE"

    invalid_risk = sample_inputs()
    invalid_risk["setup"] = {"status": "INVALIDATED", "risk_status": "INVALID",
                              "reason_code": "RISK_INVALID", "reason": "display only"}
    assert build_setup_candidate(**invalid_risk)["decision_lane"] == "AVOID"

    blocked = sample_inputs()
    blocked["data_status"] = {"sufficient": False, "freshness": "unknown",
                              "reason_code": "NO_60M_DATA"}
    blocked["setup"] = {"status": "FORMING", "reason_code": "NO_SETUP_DETECTED"}
    assert build_setup_candidate(**blocked)["decision_lane"] == "DATA_BLOCKED"


def test_direct_engine_data_reason_is_serialized_under_data_status_only():
    inputs = sample_inputs()
    inputs["data_status"] = {"sufficient": False, "freshness": "unknown"}
    inputs["setup"] = build_trade_setup(
        {"timeframe": "daily", "state": "UNKNOWN"}, None
    )

    item = build_setup_candidate(**inputs)

    assert item["data_status"]["reason_code"] == "NO_60M_DATA"
    assert item["data_status"]["reason_codes"] == ["NO_60M_DATA"]
    assert "data_reason_code" not in item["setup"]


def test_recursive_json_conversion_returns_plain_primitives_or_null():
    inputs = sample_inputs()
    inputs["trend"] = {
        "nested": [np.int64(4), np.float32(2.5), Decimal("3.25"), np.nan],
    }
    item = build_setup_candidate(**inputs)
    nested = item["trend"]["nested"]
    assert nested == [4, 2.5, 3.25, None]
    assert [type(value) for value in nested] == [int, float, float, type(None)]
    json.dumps(item)


def test_list_projection_preserves_unknown_and_non_vcp_rows():
    first = build_setup_candidate(**sample_inputs())
    second = dict(first, symbol="XYZ", decision_lane="DATA_BLOCKED")
    projected = project_setup_candidate_list([first, second])
    assert projected["count"] == 2
    assert [row["symbol"] for row in projected["items"]] == ["ABC", "XYZ"]
    json.dumps(projected)


def test_screening_adapter_does_not_apply_vcp_filter(monkeypatch):
    import screening

    captured = {}

    def fake_scan_universe(**kwargs):
        captured.update(kwargs)
        return ([{"symbol": "AAA", "vcp": {"is_vcp": False}},
                 {"symbol": "BBB", "analysis_status": "INSUFFICIENT_HISTORY",
                  "trend_template": {"conditions_met": 0}},
                 {"symbol": "CCC", "vcp": {"is_vcp": True}}], [])

    monkeypatch.setattr(screening, "scan_universe", fake_scan_universe)
    rows = screening.load_evaluated_ord_rows(object(), market="TH")
    assert [row["symbol"] for row in rows] == ["AAA", "BBB", "CCC"]
    assert captured["min_conditions"] == -1
    assert captured["market"] == "TH"
    assert captured["annotate_ath"] is False


def test_universe_manifest_uses_authoritative_active_ord_and_explicit_audit_mode():
    import mvp_api
    from marginable import load_marginable_data

    eligible = sorted(
        symbol for symbol, record in load_marginable_data()["by_symbol"].items()
        if record.get("instrument_type") == "ORD" and record.get("can_buy") is True
    )
    assert len(eligible) == 237
    excluded = [f"NOT_MARGINABLE_{i:03d}" for i in range(694)]
    active = eligible + excluded

    symbols, manifest = mvp_api.resolve_universe(
        object(), "marginable_long", active_symbols=active
    )
    assert symbols == eligible
    assert manifest["base_active_ord_count"] == 931
    assert manifest["eligible_count"] == 237
    assert manifest["excluded_count"] == 694
    assert not set(excluded).intersection(symbols)

    audit_symbols, audit_manifest = mvp_api.resolve_universe(
        object(), "active_ord", active_symbols=active
    )
    assert audit_symbols == sorted(active)
    assert audit_manifest["audit_only"] is True
    assert audit_manifest["eligible_count"] == 931
    import pytest
    with pytest.raises(ValueError, match="unknown universe"):
        mvp_api.resolve_universe(object(), "all", active_symbols=active)
