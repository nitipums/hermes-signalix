import json
from decimal import Decimal

import numpy as np

from setup_candidate_contract import (
    build_peer_context,
    build_setup_candidate,
    project_setup_candidate_list,
)


def sample_inputs():
    return {
        "symbol": "ABC",
        "as_of": "2026-08-30",
        "data_status": {"sufficient": True, "freshness": "fresh", "source": "daily_eod+60m"},
        "trend": {"state": "uptrend", "rise_20d_pct": 18.4, "relative_strength": 91},
        "wave": {"state": "WAVE_2_NEAR_COMPLETION", "confidence": "PARTIAL", "evidence": {}},
        "setup": {"state": "EARLY_WAVE_3", "status": "READY", "trigger": 12.5},
        "context": build_peer_context("ABC", {"sector": "Tech", "industry": "Components"}),
        "bonus_evidence": {"vcp": {"present": False}},
        "provenance": {"policy_version": "setup-candidates-v1", "daily_source": "eod"},
    }


def test_candidate_contract_keeps_layers_separate():
    item = build_setup_candidate(**sample_inputs())
    assert set(("symbol", "as_of", "data_status", "trend", "wave", "setup",
                "context", "bonus_evidence", "decision", "provenance")) == set(item)
    assert item["wave"]["timeframe"] == "daily"
    assert item["setup"]["timeframe"] == "60m"
    assert item["decision"] == "REVIEW"
    json.dumps(item)


def test_candidate_preserves_timeframe_mismatches_and_blocks_them():
    inputs = sample_inputs()
    inputs["wave"] = {"timeframe": "60m", "state": "WAVE_2_NEAR_COMPLETION"}
    inputs["setup"] = {"timeframe": "15m", "status": "READY"}
    item = build_setup_candidate(**inputs)
    assert item["wave"]["timeframe"] == "60m"
    assert item["setup"]["timeframe"] == "15m"
    assert item["decision"] == "DATA_BLOCKED"


def test_missing_timeframes_are_defaulted_by_contract_construction():
    inputs = sample_inputs()
    inputs["wave"].pop("timeframe", None)
    inputs["setup"].pop("timeframe", None)
    item = build_setup_candidate(**inputs)
    assert item["wave"]["timeframe"] == "daily"
    assert item["setup"]["timeframe"] == "60m"


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
    assert item["decision"] == "REVIEW"


def test_decision_mapping_fails_closed_and_keeps_vcp_as_bonus():
    blocked = sample_inputs()
    blocked["data_status"] = {"sufficient": False, "freshness": "unknown"}
    assert build_setup_candidate(**blocked)["decision"] == "DATA_BLOCKED"

    waiting = sample_inputs()
    waiting["setup"] = {"timeframe": "60m", "state": "EARLY_WAVE_3", "status": "FORMING"}
    assert build_setup_candidate(**waiting)["decision"] == "WAIT"

    avoided = sample_inputs()
    avoided["setup"] = {"timeframe": "60m", "state": "EARLY_WAVE_3", "status": "INVALIDATED"}
    assert build_setup_candidate(**avoided)["decision"] == "AVOID"

    non_vcp = sample_inputs()
    non_vcp["bonus_evidence"] = {"vcp": {"present": False}}
    assert build_setup_candidate(**non_vcp)["decision"] == "REVIEW"


def test_explicit_failed_structure_and_risk_statuses_avoid():
    for status in ("FAILED", "BROKEN", "DO_NOT_CHASE", "FAILED_STRUCTURE"):
        inputs = sample_inputs()
        inputs["setup"] = {"status": status}
        assert build_setup_candidate(**inputs)["decision"] == "AVOID"
    inputs = sample_inputs()
    inputs["setup"] = {"status": "FORMING", "risk_status": "RISK_FAILED"}
    assert build_setup_candidate(**inputs)["decision"] == "AVOID"


def test_blocked_data_precedes_failed_statuses():
    inputs = sample_inputs()
    inputs["data_status"] = {"sufficient": False, "freshness": "stale"}
    inputs["setup"] = {"status": "DO_NOT_CHASE"}
    assert build_setup_candidate(**inputs)["decision"] == "DATA_BLOCKED"


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
    second = dict(first, symbol="XYZ", decision="DATA_BLOCKED")
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
