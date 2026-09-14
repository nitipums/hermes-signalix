"""Behavioral contract tests for the additive Daily decision dimensions."""

from decision_dimensions import project_decision_dimensions


def card(**overrides):
    item = {
        "symbol": "TEST",
        "stage": "S2_uptrend",
        "phase": "waiting_breakout",
        "action_queue": "pre_breakout",
        "action": "WAIT FOR QUALIFIED BREAKOUT",
        "close": 99.0,
        "breakoutLevel": 100.0,
        "setup_quality": {
            "pass": True,
            "range_20d_pct": 8.0,
            "vol_ratio_50": 0.7,
            "reasons": ["tight_range", "vol_contraction", "not_extended"],
        },
        "setup_proximity": {"state": "near_trigger"},
    }
    item.update(overrides)
    return item


def test_healthy_setup_with_pending_entry_has_independent_dimensions():
    result = project_decision_dimensions(card())

    assert set(result) == {"setup_quality", "event_timing", "entry_action"}
    assert result["setup_quality"]["state"] == "pass"
    assert result["event_timing"]["state"] == "near_trigger"
    assert result["entry_action"]["state"] == "pending"


def test_confirmed_entry_requires_authoritative_trigger_evidence():
    result = project_decision_dimensions(card(
        phase="breakout_new",
        action_queue="fresh_breakout",
        action="REVIEW FRESH BREAKOUT",
        close=100.0,
        setup_proximity={"state": "action"},
    ))

    assert result["setup_quality"]["state"] == "pass"
    assert result["event_timing"]["state"] == "action"
    assert result["entry_action"]["state"] == "confirmed"


def test_invalidated_setup_is_not_promoted_by_old_quality_pass():
    result = project_decision_dimensions(card(
        stage="S4_down",
        phase="broken",
        action_queue="avoid_new_longs",
        action="AVOID_BROKEN_SETUP",
        setup_proximity={"state": None},
    ))

    assert result["setup_quality"]["state"] == "pass"
    assert result["event_timing"]["state"] == "invalidated"
    assert result["entry_action"]["state"] == "avoid"


def test_missing_evidence_is_unknown_and_forming_timing_stays_explicit():
    result = project_decision_dimensions({
        "stage": "S1_basing",
        "phase": "base_early",
        "action_queue": "monitor_only",
        "setup_quality": {"pass": False, "reasons": ["insufficient_history"]},
        "setup_proximity": {"state": "forming"},
    })

    assert result["setup_quality"]["state"] == "unknown"
    assert "MISSING_SETUP_EVIDENCE" in result["setup_quality"]["reason_codes"]
    assert result["event_timing"]["state"] == "forming"
    assert result["entry_action"]["state"] == "unknown"


def test_dimensions_do_not_cross_promote_each_other():
    weak = project_decision_dimensions(card(
        setup_quality={"pass": False, "reasons": ["range_too_wide"]},
        setup_proximity={"state": "action"},
        action_queue="fresh_breakout",
        phase="breakout_new",
        close=110.0,
    ))
    assert weak["setup_quality"]["state"] == "fail"
    assert weak["event_timing"]["state"] == "action"
    assert weak["entry_action"]["state"] != "confirmed"

    timing_only = project_decision_dimensions(card(
        setup_proximity={"state": "action"},
        phase="waiting_breakout",
    ))
    assert timing_only["setup_quality"]["state"] == "pass"
    assert timing_only["event_timing"]["state"] == "action"
    assert timing_only["entry_action"]["state"] == "pending"


def test_daily_api_card_exposes_the_additive_object():
    from mvp_api import _card_to_shortlist_item, project_shortlist_response

    result = _card_to_shortlist_item(card(), "2026-08-30", "run-1")
    assert set(result["decision_dimensions"]) == {
        "setup_quality", "event_timing", "entry_action",
    }
    assert result["decision_dimensions"]["entry_action"]["state"] == "pending"

    served = project_shortlist_response([
        card(
            phase="breakout_new",
            action_queue="fresh_breakout",
            setup_proximity={"state": "action"},
            close=100.0,
            avgDailyValue20=20_000_000,
            dataFreshness="fresh",
            daily_eod_freshness={"status": "latest_available", "as_of": "2026-08-30"},
        )
    ], marginable_filter="all")
    assert served["ready"][0]["decision_dimensions"]["entry_action"]["state"] == "confirmed"
