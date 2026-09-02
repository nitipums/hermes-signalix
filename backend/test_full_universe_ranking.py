"""Full-universe ordering and retention contract tests."""

from mvp_api import project_setup_candidates_response


LANES = (
    "REVIEW_NOW",
    "SETUP_FORMING",
    "DAILY_CANDIDATE",
    "WAIT",
    "AVOID",
    "DATA_BLOCKED",
)


def canonical_candidate(symbol, lane):
    return {
        "symbol": symbol,
        "as_of": "2026-08-30",
        "data_status": {"sufficient": True, "freshness": "fresh"},
        "trend": {"state": "uptrend", "relative_strength": 90},
        "wave": {
            "timeframe": "daily",
            "state": "EARLY_WAVE_3",
            "primary_state": "EARLY_WAVE_3",
            "confidence": "MEDIUM",
            "evidence": {},
        },
        "setup": {
            "timeframe": "60m",
            "status": "PRE_TRIGGER",
            "trigger": 100,
            "invalidation": 90,
            "targets": [120],
            "rr": {"to_target_1": 2.0},
            "close": 101,
        },
        "context": {"sector": "Technology"},
        "bonus_evidence": {},
        "decision_lane": lane,
        "provenance": {
            "policy_version": "setup-candidates-v1",
            "source": "test",
            "as_of": "2026-08-30",
            "freshness": "fresh",
        },
    }


def test_full_universe_is_ranked_before_pagination_and_retained():
    rows = [canonical_candidate(f"S{index}", lane) for index, lane in enumerate(reversed(LANES))]

    first = project_setup_candidates_response(rows, page=1, page_size=3)
    second = project_setup_candidates_response(rows, page=1, page_size=3)

    assert [item["decision_lane"] for item in first["items"]] == list(LANES[:3])
    assert first["items"] == second["items"]
    assert first["evaluated_count"] == len(LANES)
    assert first["total_items"] == 6
    assert first["returned_count"] == 3
    assert first["counts"] == {lane: 1 for lane in LANES}


def test_presentation_filters_do_not_change_full_universe_counts():
    rows = [canonical_candidate(f"S{index}", lane) for index, lane in enumerate(LANES)]

    result = project_setup_candidates_response(rows, sector="Technology", page_size=100)

    assert len(result["items"]) == 6
    assert result["evaluated_count"] == 6
    assert result["counts"] == {lane: 1 for lane in LANES}


def test_unrecognized_lane_is_not_counted_as_positive():
    row = canonical_candidate("UNKNOWN", "UNRECOGNIZED")

    result = project_setup_candidates_response([row])

    assert result["evaluated_count"] == 1
    assert result["items"][0]["decision_lane"] == "UNRECOGNIZED"
    assert sum(result["counts"].values()) == 0
