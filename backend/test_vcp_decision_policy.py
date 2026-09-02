from copy import deepcopy

import pytest

from vcp_decision_policy import POLICY_VERSION, project_vcp_decision_shadow


def result_fixture(state="READY"):
    return {
        "symbol": "AAA",
        "state": state,
        "actionable": state in {"READY", "NEAR_TRIGGER", "CONFIRMED"},
        "reviewable": False,
        "review_lane": None,
        "late_watch": False,
        "data": {
            "freshness": "fresh",
            "feed_status": "ok",
            "daily_metrics": {
                "avg_trade_value_20": 20_000_000,
                "latest_daily_close": 10.0,
                "as_of": "2026-08-27",
            },
        },
        "price": {
            "last_close": 10.0,
            "pivot_high": 10.2,
            "distance_to_pivot_pct": -1.96,
            "invalidation": 9.5,
        },
        "breakout": {
            "close_confirmed": False,
            "volume_confirmed": False,
        },
        "evidence": {
            "prior_trend_pass": True,
            "price_contraction_pass": True,
            "base_pass": True,
            "leg_volume_pass": True,
            "volume_contraction_pass": False,
            "breakout_close_pass": False,
            "breakout_volume_pass": False,
        },
        "trend": {"daily_context_pass": True},
        "pattern": {
            "sequence_diagnostics": {
                "candidate_count": 2,
                "v2_final_pivot_age_hours": 12.0,
            }
        },
        "vcp_type": {"base_type": "standard_vcp"},
        "marginable": {"is_marginable": True},
    }


def test_ready_valid_morphology_projects_to_review_now():
    out = project_vcp_decision_shadow(result_fixture())

    assert out["policy_version"] == POLICY_VERSION
    assert out["lifecycle_state"] == "READY"
    assert out["decision_lane"] == "REVIEW_NOW"
    assert out["actionability"] == "ACTIONABLE_REVIEW"
    assert out["quality"]["structural_pass_count"] == 4
    assert out["tradability"]["passes_default_filters"] is True
    assert "rr" not in out


@pytest.mark.parametrize("state", ["EXTENDED", "FAILED"])
def test_extended_and_failed_never_enter_action_lanes(state):
    out = project_vcp_decision_shadow(result_fixture(state))

    assert out["decision_lane"] == "DO_NOT_CHASE"
    assert out["actionability"] == "NO_ACTION"


@pytest.mark.parametrize("state", ["STALE", "NOT_VERIFIED"])
def test_unusable_data_is_blocked(state):
    item = result_fixture(state)
    item["data"]["freshness"] = "stale" if state == "STALE" else "fresh"

    out = project_vcp_decision_shadow(item)

    assert out["decision_lane"] == "DATA_BLOCKED"
    assert out["actionability"] == "NO_ACTION"


def test_review_event_with_incomplete_structure_is_watch_only():
    item = result_fixture("FORMING")
    item["evidence"]["prior_trend_pass"] = False
    item["review_lane"] = "PRICE_VOLUME_BREAKOUT"
    item["reviewable"] = True

    out = project_vcp_decision_shadow(item)

    assert out["decision_lane"] == "EVENT_WATCH"
    assert out["actionability"] == "WATCH_ONLY"
    assert "STRUCTURE_INCOMPLETE" in out["reason_codes"]


def test_extended_review_event_stays_do_not_chase():
    item = result_fixture("EXTENDED")
    item["review_lane"] = "CLOSE_BREAKOUT_VOLUME_PENDING"
    item["reviewable"] = True

    out = project_vcp_decision_shadow(item)

    assert out["decision_lane"] == "DO_NOT_CHASE"
    assert out["actionability"] == "NO_ACTION"


def test_low_liquidity_ready_is_retained_but_tagged_untradable_by_default():
    item = result_fixture()
    item["data"]["daily_metrics"]["avg_trade_value_20"] = 5_000_000

    out = project_vcp_decision_shadow(item)

    assert out["decision_lane"] == "REVIEW_NOW"
    assert out["tradability"]["passes_default_filters"] is False
    assert "AVG_TRADE_VALUE_BELOW_10M" in out["tradability"]["reason_codes"]


def test_non_marginable_and_sub_min_price_are_independent_filters():
    item = result_fixture()
    item["marginable"]["is_marginable"] = False
    item["price"].update({
        "last_close": 0.5,
        "pivot_high": 0.51,
        "distance_to_pivot_pct": -1.96,
        "invalidation": 0.45,
    })

    out = project_vcp_decision_shadow(item)

    assert out["decision_lane"] == "REVIEW_NOW"
    assert out["tradability"]["marginable_pass"] is False
    assert out["tradability"]["price_pass"] is False
    assert out["tradability"]["passes_default_filters"] is False


def test_missing_invalidation_cannot_be_actionable():
    item = result_fixture()
    item["price"]["invalidation"] = None

    out = project_vcp_decision_shadow(item)

    assert out["decision_lane"] == "RESEARCH"
    assert out["actionability"] == "NO_ACTION"
    assert "INVALIDATION_NOT_COHERENT" in out["reason_codes"]


def test_partial_quality_near_trigger_is_structure_watch_not_actionable():
    item = result_fixture("NEAR_TRIGGER")
    item["evidence"]["leg_volume_pass"] = False
    item["vcp_type"]["base_type"] = None

    out = project_vcp_decision_shadow(item)

    assert out["quality"]["structural_pass_count"] == 3
    assert out["decision_lane"] == "STRUCTURE_WATCH"
    assert out["actionability"] == "WATCH_ONLY"
    assert "LEG_VOLUME_NOT_CONTRACTED" in out["quality"]["failing_evidence"]


def test_structure_first_candidate_does_not_require_leg_volume_and_is_watch_only():
    item = result_fixture("READY")
    item["evidence"]["leg_volume_pass"] = False

    out = project_vcp_decision_shadow(item)

    assert out["projection_marker"] == "signalix/structure-first-candidate-v1"
    assert out["candidate_policy"] == "structure_first/volume_not_required_for_candidate"
    assert out["decision_lane"] == "STRUCTURE_WATCH"
    assert out["actionability"] == "WATCH_ONLY"
    assert out["quality"]["structure_pass"] is True
    assert "LEG_VOLUME_NOT_CONTRACTED" in out["quality"]["failing_evidence"]


def test_projection_is_pure_and_sort_fields_are_stable():
    item = result_fixture()
    original = deepcopy(item)

    first = project_vcp_decision_shadow(item)
    second = project_vcp_decision_shadow(item)

    assert item == original
    assert first == second
    assert first["sort"]["key"] == second["sort"]["key"]
    assert len(first["sort"]["key"]) == 6
