import json

from setup_candidate_contract import (
    attach_bonus_vcp,
    build_peer_context,
    build_setup_candidate,
)


def _candidate_inputs():
    return {
        "symbol": "ABC",
        "as_of": "2026-08-30",
        "data_status": {"sufficient": True, "freshness": "fresh"},
        "trend": {"state": "uptrend"},
        "wave": {"state": "EARLY_WAVE_3", "confidence": "HIGH"},
        "setup": {
            "status": "PRE_TRIGGER", "trigger": 12, "invalidation": 10,
            "targets": [16], "rr": {"to_target_1": 3},
        },
        "provenance": {"policy_version": "setup-candidates-v1"},
    }


def test_peer_symbols_are_preserved_and_missing_context_is_explicit():
    context = build_peer_context("ABC", {
        "sector": "Technology", "industry": "Components", "market_cap": 174900000000,
        "peer_symbols": ["AAA", "BBB"],
    })
    assert context["peer_symbols"] == ["AAA", "BBB"]
    assert context["market_cap"] == 174900000000
    assert context["peer_trend_breadth"] is None
    assert context["peer_breakout_count"] is None

    missing = build_peer_context("ABC")
    assert missing["peer_data_status"] == "UNKNOWN"
    assert missing["peer_symbols"] == []
    assert missing["sector_trend"] is None
    assert missing["relative_strength_vs_sector"] is None
    assert missing["market_cap"] is None
    json.dumps(missing)


def test_attach_bonus_vcp_only_attaches_verified_positive_evidence():
    item = {"bonus_evidence": {}}
    attach_bonus_vcp(item, {"present": True, "quality": "OK", "source": "vcp_engine", "extra": 1})
    assert item["bonus_evidence"]["vcp"] == {
        "present": True, "quality": "OK", "source": "vcp_engine"
    }

    for evidence, expected_present in (
        ({"present": None, "quality": "NOT_VERIFIED", "source": "legacy_audit_only"}, None),
        ({"present": False, "quality": "NOT_VERIFIED", "source": "old"}, False),
        ({"present": True, "quality": "NOT_VERIFIED", "source": "old"}, None),
    ):
        item = {"bonus_evidence": {}}
        attach_bonus_vcp(item, evidence)
        assert item["bonus_evidence"]["vcp"] == {
            "present": expected_present,
            "quality": "NOT_VERIFIED",
            "source": "not_computed",
        }


def test_sector_context_and_vcp_bonus_do_not_change_decision_lane():
    base = _candidate_inputs()
    with_context = {
        **base,
        "context": {"sector": "Weak sector", "sector_trend": "DOWN"},
        "bonus_evidence": {"vcp": {"present": None, "quality": "NOT_VERIFIED",
                                    "source": "not_computed"}},
    }
    without_context = {
        **base,
        "context": {},
        "bonus_evidence": {},
    }
    assert build_setup_candidate(**with_context)["decision_lane"] == build_setup_candidate(
        **without_context
    )["decision_lane"]
