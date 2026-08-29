import json
import math

from unified_vcp_decision import project_unified_vcp_decision


def result(state="READY", **overrides):
    value = {
        "state": state,
        "data": {"freshness": "fresh", "feed_status": "ok"},
        "price": {
            "pivot_high": 10.0,
            "last_close": 10.0,
            "distance_to_pivot_pct": 0.0,
            "invalidation": 9.0,
        },
        "evidence": {
            "prior_trend_pass": True,
            "price_contraction_pass": True,
            "base_pass": True,
            "leg_volume_pass": True,
            "breakout_volume_pass": True,
        },
    }
    value.update(overrides)
    return value


def test_lifecycle_states_map_to_compact_decisions():
    assert project_unified_vcp_decision(result("FORMING"))["decision"] == "WAIT"
    assert project_unified_vcp_decision(result("READY"))["decision"] == "WAIT"
    assert project_unified_vcp_decision(result("CONFIRMED"))["decision"] == "REVIEW"
    assert project_unified_vcp_decision(result("EXTENDED"))["decision"] == "WAIT"
    assert project_unified_vcp_decision(result("FAILED"))["decision"] == "AVOID"


def test_extended_is_wait_not_avoid():
    output = project_unified_vcp_decision({
        "state": "EXTENDED",
        "data": {"freshness": "fresh", "feed_status": "ok"},
        "price": {"pivot_high": 10.0, "last_close": 11.0, "invalidation": 9.0},
        "evidence": {"prior_trend_pass": True, "price_contraction_pass": True,
                     "base_pass": True, "leg_volume_pass": True},
    })
    assert output["state"] == "EXTENDED"
    assert output["decision"] == "WAIT"


def test_insufficient_data_is_unknown_and_clears_state():
    output = project_unified_vcp_decision(result("READY", data={"freshness": "stale", "feed_status": "ok"}))
    assert output["state"] is None
    assert output["decision"] is None
    assert output["quality"] == "UNKNOWN"
    assert output["data_sufficient"] is False


def test_stale_and_not_verified_are_insufficient_even_with_override():
    for state in ("STALE", "NOT_VERIFIED"):
        output = project_unified_vcp_decision(
            result(state), data_sufficient=True
        )
        assert output["state"] is None
        assert output["decision"] is None
        assert output["quality"] == "UNKNOWN"
        assert output["data_sufficient"] is False


def test_quality_requires_all_60m_structural_evidence():
    output = project_unified_vcp_decision(result("READY", evidence={"prior_trend_pass": True}))
    assert output["quality"] == "PARTIAL"
    output = project_unified_vcp_decision(result("READY"))
    assert output["quality"] == "PASS"


def test_event_partial_morphology_is_partial():
    output = project_unified_vcp_decision(result(
        "BREAKOUT_WATCH",
        review_lane="PRICE_VOLUME_BREAKOUT",
        evidence={"prior_trend_pass": True, "price_contraction_pass": True},
    ))
    assert output["quality"] == "PARTIAL"


def test_failed_structure_is_fail_with_sufficient_data():
    output = project_unified_vcp_decision(result("FAILED", evidence={"base_pass": False}))
    assert output["quality"] == "FAIL"


def test_daily_context_is_copy_only_and_cannot_promote_state():
    context = {"trend_pass": True, "nested": {"value": 1}}
    source = result("READY")
    output = project_unified_vcp_decision(source, context)
    assert output["state"] == "READY"
    assert output["decision"] == "WAIT"
    assert output["evidence"]["daily_context"] == context
    output["evidence"]["daily_context"]["nested"]["value"] = 2
    assert context["nested"]["value"] == 1

    confirmed = project_unified_vcp_decision(result("CONFIRMED"), {"trend_pass": False})
    assert confirmed["state"] == "CONFIRMED"
    assert confirmed["decision"] == "REVIEW"


def test_projection_has_exact_keys_and_strictly_json_safe_nested_context():
    class Unsupported:
        pass

    context = {
        "finite": 1.5,
        "nested": {"nan": math.nan, "infinity": math.inf, "object": Unsupported()},
        "items": (math.inf, Unsupported()),
    }
    output = project_unified_vcp_decision(
        result("CONFIRMED", price={"pivot_high": math.nan}), context
    )

    assert set(output) == {"state", "decision", "quality", "data_sufficient", "evidence"}
    assert set(output["evidence"]) == {
        "timeframe", "trigger", "invalidation", "distance_to_trigger_pct",
        "volume_confirmation", "daily_context",
    }
    assert output["evidence"]["trigger"] is None
    assert output["evidence"]["daily_context"] == {
        "finite": 1.5,
        "nested": {"nan": None, "infinity": None, "object": None},
        "items": [None, None],
    }
    json.dumps(output, allow_nan=False)


def test_projection_does_not_mutate_result():
    source = result("CONFIRMED")
    before = json.dumps(source, sort_keys=True)
    output = project_unified_vcp_decision(source)
    json.dumps(output)
    assert json.dumps(source, sort_keys=True) == before
