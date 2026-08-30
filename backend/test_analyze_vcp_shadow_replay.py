import json
import sys

import pytest

import analyze_vcp_shadow_replay as shadow_replay
from analyze_vcp_shadow_replay import (
    summarize_sequence_ab,
    summarize_shadow,
    summarize_timeline,
)


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


def test_summarize_timeline_orders_states_and_counts_transitions():
    records = [
        {"symbol": "AAA", "as_of": "2026-08-01T09:45:00+00:00", "state": "READY", "decision_shadow_v2": {"decision_lane": "PREPARE", "actionability": "ACTIONABLE_REVIEW"}, "replay_evaluation": {"outcome": "target_hit"}},
        {"symbol": "AAA", "as_of": "2026-08-01T05:30:00+00:00", "state": "FORMING", "decision_shadow_v2": {"decision_lane": "RESEARCH", "actionability": "NO_ACTION"}},
    ]

    out = summarize_timeline(records)

    assert out["AAA"]["states"] == ["FORMING", "READY"]
    assert out["AAA"]["transition_count"] == 1
    assert out["AAA"]["first_action_lane"] == "PREPARE"
    assert out["AAA"]["first_watch"] == "2026-08-01T09:45:00+00:00"
    assert out["AAA"]["first_action_as_of"] == "2026-08-01T09:45:00+00:00"
    assert out["AAA"]["outcome_counts"] == {"target_hit": 1, "NOT_VERIFIED": 1}


def test_summarize_timeline_repeated_states_and_bounded_diagnostics():
    records = [
        {"symbol": "AAA", "as_of": f"2026-08-01T{hour:02d}:00:00+00:00", "state": state}
        for hour, state in enumerate(("FORMING", "FORMING", "READY", "FAILED", "READY"))
    ]

    out = summarize_timeline(records, max_diagnostic_items=2)["AAA"]

    assert out["states"] == ["FORMING", "READY", "FAILED", "READY"]
    assert out["transition_count"] == 3
    assert len(out["transitions"]) == 2
    assert out["outcome_counts"] == {"NOT_VERIFIED": 5}


def test_summarize_timeline_legacy_summary_keys_remain_present():
    legacy_keys = {
        "records", "shadow_records", "missing_shadow", "lane_counts",
        "actionability_counts", "tradability", "state_lane_matrix",
        "missing_evidence", "outcomes", "contradictions",
    }

    out = summarize_shadow([record("AAA", "READY", "PREPARE", "ACTIONABLE_REVIEW")])

    assert legacy_keys <= out.keys()


def test_summarize_shadow_fails_closed_for_expected_count_and_missing_shadow():
    records = [record("AAA", "READY", "PREPARE", "ACTIONABLE_REVIEW")]

    with pytest.raises(ValueError, match="expected 237 result records"):
        summarize_shadow(records, expected_count=237)

    out = summarize_shadow(records + [{"symbol": "BBB", "state": "FORMING"}])

    assert out["validation_failures"] == 1
    assert out["missing_shadow"] == 1
    assert out["shadow_records"] == 1


def test_summarize_shadow_rejects_missing_or_invalid_result_collection():
    with pytest.raises(ValueError, match="result collection"):
        summarize_shadow(None)
    with pytest.raises(ValueError, match="result collection"):
        summarize_shadow({"results": {"AAA": {}}})


def test_summarize_shadow_preserves_replay_envelope_metadata():
    out = summarize_shadow({
        "results": [record("AAA", "READY", "PREPARE", "ACTIONABLE_REVIEW")],
        "universe": {
            "universe_filter": "marginable_long",
            "eligible_count": 237,
            "excluded_count": 694,
        },
        "cadence": "daily",
        "snapshots_per_day": 2,
    })

    assert out["universe_filter"] == "marginable_long"
    assert out["eligible_count"] == 237
    assert out["excluded_count"] == 694
    assert out["cadence"] == "daily"
    assert out["snapshots_per_day"] == 2


def test_main_propagates_eligible_count_from_replay_run(monkeypatch, capsys):
    result = record("AAA", "READY", "PREPARE", "ACTIONABLE_REVIEW")
    row = {
        "replay_id": "replay-20260830",
        "result": result,
        "eligible_count": 1,
        "universe_filter": "marginable_long",
        "base_active_ord_count": 1,
        "excluded_count": 0,
        "margin_schema_version": "v1",
        "margin_source_document": "fixture",
        "margin_effective_date": "2026-08-30",
        "cadence": "daily",
        "snapshots_per_day": 1,
    }

    class Cursor:
        def execute(self, query, params):
            pass

        def fetchall(self):
            return [row]

    class Connection:
        def cursor(self, **kwargs):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(shadow_replay.psycopg2, "connect", lambda **kwargs: Connection())
    monkeypatch.setattr(sys, "argv", ["analyze_vcp_shadow_replay.py", "--replay-prefix", "replay-"])

    shadow_replay.main()

    output = json.loads(capsys.readouterr().out)
    assert output["eligible_count"] == 1
    assert output["universe_filter"] == "marginable_long"


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
