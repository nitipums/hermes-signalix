from datetime import datetime, timezone

import run_vcp_replay_1m
from run_vcp_replay_1m import (
    attach_replay_evaluation,
    attach_sequence_v2_evaluation,
    build_replay_result,
    evaluate_trade,
    make_replay_id,
    pending_replay_points,
    sequence_v2_trade_plan,
    trade_plan,
)


def test_low_cheat_trade_plan_uses_close_and_three_r_target():
    plan = trade_plan({
        "vcp_type": {"base_type": "low_cheat_vcp", "entry_profile": "early_entry"},
        "price": {"last_close": 100, "invalidation": 95},
        "breakout": {"required_close": 101},
    })

    assert plan == {
        "base_type": "low_cheat_vcp",
        "entry_profile": "early_entry",
        "entry": 100.0,
        "stop": 95.0,
        "target": 115.0,
        "rr_multiple": 3.0,
    }


def test_standard_trade_plan_uses_breakout_entry_and_three_r_target():
    plan = trade_plan({
        "vcp_type": {"base_type": "standard_vcp", "entry_profile": "standard_entry"},
        "price": {"last_close": 100, "invalidation": 96},
        "breakout": {"required_close": 102},
    })

    assert plan["entry"] == 102.0
    assert plan["stop"] == 96.0
    assert plan["target"] == 120.0
    assert plan["rr_multiple"] == 3.0


def test_same_bar_stop_and_target_is_ambiguous():
    plan = {"entry": 100.0, "stop": 95.0, "target": 115.0}

    result = evaluate_trade(plan, [{"high": 116, "low": 94}])

    assert result["outcome"] == "ambiguous_same_bar"
    assert result["mfe_r"] == 3.2
    assert result["mae_r"] == -1.2


def test_future_outcome_reads_only_bars_after_detection():
    plan = {"entry": 100.0, "stop": 95.0, "target": 115.0}

    result = evaluate_trade(plan, [{"high": 110, "low": 98}, {"high": 116, "low": 105}])

    assert result["outcome"] == "target_hit"
    assert result["bars_observed"] == 2


def test_standard_plan_ignores_stop_before_entry_activation():
    plan = {"base_type": "standard_vcp", "entry": 102.0, "stop": 96.0, "target": 120.0}
    rows = [
        {"ts": "a", "high": 101.0, "low": 95.0},
        {"ts": "b", "high": 103.0, "low": 100.0},
        {"ts": "c", "high": 121.0, "low": 105.0},
    ]

    result = evaluate_trade(plan, rows)

    assert result["entry_activated"] is True
    assert result["entry_ts"] == "b"
    assert result["pre_entry_bars"] == 1
    assert result["outcome"] == "target_hit"


def test_standard_plan_reports_not_activated_when_entry_never_trades():
    plan = {"base_type": "standard_vcp", "entry": 102.0, "stop": 96.0, "target": 120.0}

    result = evaluate_trade(plan, [{"ts": "a", "high": 101.0, "low": 95.0}])

    assert result["entry_activated"] is False
    assert result["outcome"] == "entry_not_activated"
    assert result["bars_observed"] == 0


def test_low_cheat_plan_is_active_from_detection():
    plan = {"base_type": "low_cheat_vcp", "entry": 100.0, "stop": 95.0, "target": 115.0}

    result = evaluate_trade(plan, [{"ts": "a", "high": 101.0, "low": 94.0}])

    assert result["entry_activated"] is True
    assert result["entry_ts"] == "detection"
    assert result["pre_entry_bars"] == 0
    assert result["outcome"] == "stop_hit"


def test_build_replay_result_passes_point_in_time_daily_context(monkeypatch):
    captured = {}

    def fake_find(frame, *, as_of, daily_context, include_sequence_policy_shadow):
        captured["as_of"] = as_of
        captured["daily_context"] = daily_context
        captured["include_sequence_policy_shadow"] = include_sequence_policy_shadow
        return {
            "state": "FORMING", "actionable": False,
            "data": {}, "price": {}, "breakout": {}, "pattern": {},
            "evidence": {}, "provenance": {},
        }

    monkeypatch.setattr(run_vcp_replay_1m, "find_vcp_60m", fake_find)
    monkeypatch.setattr(run_vcp_replay_1m, "_classify_types", lambda result, **_: result)
    as_of = datetime(2026, 8, 27, 6, tzinfo=timezone.utc)

    result = build_replay_result(
        "AAA", [], as_of=as_of, replay_id="replay-1",
        daily_context={"trend_pass": True, "as_of": "2026-08-26"},
        daily_metrics={"avg_trade_value_20": 20_000_000, "as_of": "2026-08-26"},
        marginable_record={"margin_rate_pct": 50},
    )

    assert captured == {
        "as_of": as_of,
        "daily_context": {"trend_pass": True, "as_of": "2026-08-26"},
        "include_sequence_policy_shadow": True,
    }
    assert result["data"]["daily_metrics"]["avg_trade_value_20"] == 20_000_000
    assert result["provenance"]["replay_id"] == "replay-1"
    assert result["decision_shadow_v2"]["policy_version"] == "signalix/vcp-decision-shadow-v2"
    assert result["decision_shadow_v2"]["symbol"] == "AAA"
    assert result["marginable"] == {"is_marginable": True, "margin_rate_pct": 50}
    assert result["decision_shadow_v2"]["tradability"]["marginable_pass"] is True
    assert "sequence_v2_trade_plan" in result


def test_replay_id_prefix_is_explicit_and_isolated():
    as_of = datetime(2026, 8, 27, 6, tzinfo=timezone.utc)

    replay_id = make_replay_id("vcp-shadow-v2", "60m", as_of, 3)

    assert replay_id == "vcp-shadow-v2-60m-20260827T060000Z-003"


def test_pending_replay_points_skip_already_persisted_ids():
    snapshots = [
        datetime(2026, 8, 27, hour, tzinfo=timezone.utc)
        for hour in (2, 3, 4)
    ]
    existing = {make_replay_id("shadow", "60m", snapshots[0], 1)}

    pending = pending_replay_points("shadow", "60m", snapshots, existing)

    assert pending == [
        (2, snapshots[1], "shadow-60m-20260827T030000Z-002"),
        (3, snapshots[2], "shadow-60m-20260827T040000Z-003"),
    ]


def test_attach_replay_evaluation_persists_descriptive_outcome():
    result = {"symbol": "AAA"}
    plan = {"base_type": "standard_vcp", "entry": 100.0, "stop": 95.0, "target": 115.0}
    future = [{"ts": "next", "high": 116.0, "low": 100.0}]

    evaluation = attach_replay_evaluation(result, plan, future)

    assert evaluation["outcome"] == "target_hit"
    assert result["replay_evaluation"] == evaluation


def test_sequence_v2_trade_plan_uses_shadow_required_close_and_invalidation():
    result = {
        "sequence_policy_shadow_v2": {
            "standard_entry_eligible": True,
            "low_cheat_observed": False,
            "breakout": {"required_close": 102.0},
            "price": {"invalidation": 96.0},
        }
    }

    plan = sequence_v2_trade_plan(result)

    assert plan == {
        "base_type": "standard_vcp",
        "entry_profile": "standard_entry",
        "entry": 102.0,
        "stop": 96.0,
        "target": 120.0,
        "rr_multiple": 3.0,
        "sequence_policy_version": "signalix/vcp-sequence-policy-shadow-v2",
    }


def test_sequence_v2_trade_plan_rejects_incomplete_morphology():
    result = {
        "sequence_policy_shadow_v2": {
            "standard_entry_eligible": False,
            "breakout": {"required_close": 102.0},
            "price": {"invalidation": 96.0},
        }
    }
    assert sequence_v2_trade_plan(result) is None


def test_low_cheat_observation_never_creates_early_entry_plan():
    result = {
        "sequence_policy_shadow_v2": {
            "policy_version": "signalix/vcp-sequence-policy-shadow-v2",
            "standard_entry_eligible": True,
            "low_cheat_observed": True,
            "breakout": {"required_close": 102.0},
            "price": {"last_close": 100.0, "invalidation": 96.0},
        }
    }
    plan = sequence_v2_trade_plan(result)
    assert plan["base_type"] == "standard_vcp"
    assert plan["entry"] == 102.0


def test_attach_sequence_v2_evaluation_uses_separate_namespace():
    result = {
        "sequence_v2_trade_plan": {
            "base_type": "standard_vcp", "entry": 100.0,
            "stop": 95.0, "target": 115.0,
        }
    }
    evaluation = attach_sequence_v2_evaluation(
        result, [{"ts": "next", "high": 116.0, "low": 100.0}],
    )
    assert evaluation["outcome"] == "target_hit"
    assert result["sequence_v2_replay_evaluation"] == evaluation
    assert "replay_evaluation" not in result
