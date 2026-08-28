from analyze_vcp_shadow_replay import summarize_sequence_ab, summarize_shadow


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


def test_summarize_sequence_ab_counts_divergence_and_outcomes():
    records = [
        {
            "symbol": "AAA", "state": "READY",
            "price": {"pivot_high": 10.0, "invalidation": 9.0},
            "replay_trade_plan": {"base_type": "standard_vcp"},
            "replay_evaluation": {"outcome": "target_hit", "entry_activated": True, "pre_entry_bars": 2},
            "sequence_policy_shadow_v2": {
                "state": "CONFIRMED", "low_cheat_observed": False,
                "price": {"pivot_high": 11.0, "invalidation": 9.5},
            },
            "sequence_v2_trade_plan": {"base_type": "standard_vcp", "entry_profile": "standard_entry"},
            "sequence_v2_replay_evaluation": {"outcome": "stop_hit", "entry_activated": True, "pre_entry_bars": 1},
        },
        {
            "symbol": "BBB", "state": "FORMING",
            "price": {"pivot_high": 20.0, "invalidation": 18.0},
            "replay_trade_plan": None,
            "sequence_policy_shadow_v2": {
                "state": "FORMING", "low_cheat_observed": True,
                "price": {"pivot_high": 20.0, "invalidation": 18.0},
            },
            "sequence_v2_trade_plan": None,
        },
        {"symbol": "CCC", "state": "NOT_VERIFIED"},
    ]

    out = summarize_sequence_ab(records)

    assert out["records"] == 3
    assert out["shadow_present"] == 2
    assert out["missing_shadow"] == 1
    assert out["pivot_comparable"] == 2
    assert out["pivot_divergence"] == 1
    assert out["state_divergence"] == 1
    assert out["v1_plan_count"] == 1
    assert out["sequence_v2_plan_count"] == 1
    assert out["v1_outcomes"] == {"target_hit": 1}
    assert out["sequence_v2_outcomes"] == {"stop_hit": 1}
    assert out["low_cheat_observed"] == 1
    assert out["low_cheat_promotion_violations"] == 0
    assert out["v1_pre_entry_bars"] == {"count": 1, "average": 2.0}
    assert out["sequence_v2_pre_entry_bars"] == {"count": 1, "average": 1.0}


def test_summarize_sequence_ab_flags_low_cheat_plan_violation():
    records = [{
        "sequence_policy_shadow_v2": {"state": "READY", "price": {}},
        "sequence_v2_trade_plan": {
            "base_type": "low_cheat_vcp", "entry_profile": "early_entry",
        },
    }]
    assert summarize_sequence_ab(records)["low_cheat_promotion_violations"] == 1
