from setup_candidate_contract import (
    DECISION_LANES,
    project_decision_lane,
    sort_setup_candidates,
)
from mvp_api import project_setup_candidates_response


def evidence(**overrides):
    result = {"structure_intact": True}
    result.update(overrides)
    return result


def wave(confidence="MEDIUM", state="EARLY_WAVE_3", **overrides):
    result = {"timeframe": "daily", "state": state, "confidence": confidence,
              "evidence": evidence()}
    result.update(overrides)
    return result


def setup(status="PRE_TRIGGER", **overrides):
    result = {"timeframe": "60m", "status": status, "trigger": 100,
              "invalidation": 90, "targets": [120],
              "rr": {"to_target_1": 2.0}}
    result.update(overrides)
    return result


def fresh():
    return {"sufficient": True, "freshness": "fresh"}


def test_full_review_now_accepts_legacy_and_canonical_medium_confidence():
    assert project_decision_lane(fresh(), wave("MEDIUM"), setup()) == "REVIEW_NOW"
    assert project_decision_lane(fresh(), wave("HIGH"), setup("TRIGGERED")) == "REVIEW_NOW"
    assert project_decision_lane(fresh(), wave("PARTIAL"), setup()) == "REVIEW_NOW"


def test_low_confidence_cannot_reach_review_now():
    assert project_decision_lane(fresh(), wave("LOW"), setup()) == "SETUP_FORMING"


def test_rr_below_two_stays_setup_forming():
    assert project_decision_lane(fresh(), wave(), setup(rr={"to_target_1": 1.99})) == "SETUP_FORMING"


def test_forming_complete_plan_is_setup_forming():
    assert project_decision_lane(fresh(), wave(), setup("FORMING")) == "SETUP_FORMING"


def test_valid_daily_wave_without_usable_60m_plan_is_daily_candidate():
    assert project_decision_lane(fresh(), wave(), setup("FORMING", trigger=None)) == "DAILY_CANDIDATE"


def test_stale_or_unknown_wave_is_data_blocked():
    assert project_decision_lane({"sufficient": True, "freshness": "stale"}, wave(), setup()) == "DATA_BLOCKED"
    assert project_decision_lane(fresh(), wave(state="UNKNOWN", confidence="LOW"), setup()) == "DATA_BLOCKED"


def test_structure_failure_and_expiry_avoid():
    assert project_decision_lane(fresh(), wave(evidence=evidence(structure_intact=False)), setup()) == "AVOID"
    assert project_decision_lane(fresh(), wave(), setup("EXPIRED")) == "AVOID"


def test_sort_setup_candidates_uses_deterministic_lane_key():
    def item(symbol, lane, confidence="HIGH", trend_state="uptrend", close=101, trigger=100, rr=3):
        return {"symbol": symbol, "decision_lane": lane,
                "wave": {"confidence": confidence}, "trend": {"state": trend_state},
                "setup": {"close": close, "trigger": trigger, "rr": {"to_target_1": rr}}}

    items = [
        item("WAIT", "WAIT"), item("DAILY", "DAILY_CANDIDATE"),
        item("FORMING", "SETUP_FORMING", "LOW"),
        item("TRIGGERED", "REVIEW_NOW", "HIGH", close=100.5),
        item("PRE", "REVIEW_NOW", "MEDIUM", close=102),
        item("BLOCKED", "DATA_BLOCKED"),
    ]
    assert [row["symbol"] for row in sort_setup_candidates(items)] == [
        "TRIGGERED", "PRE", "FORMING", "DAILY", "WAIT", "BLOCKED"
    ]
    assert set(row["decision_lane"] for row in items) <= DECISION_LANES


def test_response_counts_include_all_new_lanes():
    # The response projector preserves canonical rows and counts every lane.
    rows = []
    for index, lane in enumerate(("REVIEW_NOW", "SETUP_FORMING", "DAILY_CANDIDATE",
                                  "WAIT", "AVOID", "DATA_BLOCKED")):
        rows.append({"symbol": f"S{index}", "as_of": "2026-08-30",
                     "data_status": {"sufficient": True, "freshness": "fresh"},
                     "trend": {}, "wave": {}, "setup": {}, "context": {},
                     "bonus_evidence": {}, "decision_lane": lane,
                     "provenance": {"policy_version": "setup-candidates-v1", "source": "test",
                                     "as_of": "2026-08-30", "freshness": "fresh"}})
    counts = project_setup_candidates_response(rows)["counts"]
    assert counts == {lane: 1 for lane in ("REVIEW_NOW", "SETUP_FORMING", "DAILY_CANDIDATE",
                                           "WAIT", "AVOID", "DATA_BLOCKED")}
