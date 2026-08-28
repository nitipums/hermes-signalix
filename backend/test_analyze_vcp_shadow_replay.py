from analyze_vcp_shadow_replay import summarize_shadow


def record(symbol, state, lane, actionability, *, tradable=True, failing=None, outcome=None):
    item = {
        "symbol": symbol,
        "state": state,
        "decision_shadow_v2": {
            "policy_version": "signalix/vcp-decision-shadow-v2",
            "symbol": symbol,
            "lifecycle_state": state,
            "decision_lane": lane,
            "actionability": actionability,
            "quality": {"failing_evidence": failing or []},
            "tradability": {"passes_default_filters": tradable},
        },
    }
    if outcome is not None:
        item["replay_evaluation"] = {"outcome": outcome}
    return item


def test_summarize_shadow_counts_each_record_once_and_surfaces_missing_evidence():
    records = [
        record("AAA", "READY", "REVIEW_NOW", "ACTIONABLE_REVIEW", outcome="target_hit"),
        record("BBB", "EXTENDED", "DO_NOT_CHASE", "NO_ACTION", tradable=False),
        record("CCC", "FORMING", "EVENT_WATCH", "WATCH_ONLY",
               failing=["PRIOR_TREND_NOT_CONFIRMED"]),
        {"symbol": "DDD", "state": "NOT_VERIFIED"},
    ]

    out = summarize_shadow(records)

    assert out["records"] == 4
    assert out["shadow_records"] == 3
    assert out["missing_shadow"] == 1
    assert out["lane_counts"] == {
        "REVIEW_NOW": 1,
        "DO_NOT_CHASE": 1,
        "EVENT_WATCH": 1,
    }
    assert out["tradability"] == {"default_pass": 2, "default_fail": 1}
    assert out["missing_evidence"] == {"PRIOR_TREND_NOT_CONFIRMED": 1}
    assert out["outcomes"] == {"target_hit": 1, "NOT_VERIFIED": 2}
    assert out["contradictions"] == {
        "extended_in_action_lane": 0,
        "failed_in_action_lane": 0,
        "event_watch_actionable": 0,
        "data_blocked_actionable": 0,
    }


def test_summarize_shadow_detects_lane_actionability_contradictions():
    records = [
        record("EXT", "EXTENDED", "REVIEW_NOW", "ACTIONABLE_REVIEW"),
        record("FAIL", "FAILED", "PREPARE", "WATCH_ONLY"),
        record("EVENT", "FORMING", "EVENT_WATCH", "ACTIONABLE_REVIEW"),
        record("DATA", "STALE", "DATA_BLOCKED", "WATCH_ONLY"),
    ]

    out = summarize_shadow(records)

    assert out["contradictions"] == {
        "extended_in_action_lane": 1,
        "failed_in_action_lane": 1,
        "event_watch_actionable": 1,
        "data_blocked_actionable": 1,
    }
