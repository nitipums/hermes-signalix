import json

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
                 {"symbol": "BBB", "analysis_status": "INSUFFICIENT_HISTORY"}], [])

    monkeypatch.setattr(screening, "scan_universe", fake_scan_universe)
    rows = screening.load_evaluated_ord_rows(object(), market="TH")
    assert [row["symbol"] for row in rows] == ["AAA", "BBB"]
    assert captured["min_conditions"] == -1
    assert captured["market"] == "TH"
    assert captured["annotate_ath"] is False
