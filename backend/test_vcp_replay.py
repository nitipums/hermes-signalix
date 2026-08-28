from run_vcp_replay_1m import evaluate_trade, trade_plan


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
