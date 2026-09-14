import pytest

from actionable_signal_policy import (
    POLICY_VERSION,
    project_market_buy_signal,
)


def candidate(*, price=10.2, lane="REVIEW_NOW", setup_status="TRIGGERED"):
    return {
        "symbol": "AAA",
        "as_of": "2026-09-11T16:00:00+07:00",
        "decision_lane": lane,
        "data_status": {
            "sufficient": True,
            "daily_freshness": "fresh",
            "intraday_60m_freshness": "fresh",
        },
        "quote": {"price": price, "basis": "latest_completed_60m"},
        "trend": {"state": "uptrend"},
        "wave": {"primary_state": "EARLY_WAVE_3", "confidence": "HIGH"},
        "setup": {
            "status": setup_status,
            "trigger": 10.0,
            "entry_zone": {"low": 9.8, "high": 10.5},
            "trade_stop": 9.0,
            "target_1": 13.0,
            "targets": [{"price": 13.0}],
            "rr": {"to_target_1": 3.0},
        },
        "provenance": {"policy_version": "setup-candidates-v1"},
    }


def test_confirmed_fresh_coherent_setup_emits_buy_now_without_order_payload():
    signal = project_market_buy_signal(candidate())

    assert signal["signal"] == "BUY_NOW"
    assert signal["reason_codes"] == ["ALL_BUY_NOW_GATES_PASSED"]
    assert signal["execution"] == {"authorized": False, "order_payload": None}
    assert signal["confidence"]["score"] >= 80
    assert signal["confidence"]["calibration_status"] == "NOT_CALIBRATED"
    assert signal["confidence"]["calibrated_probability"] is None


@pytest.mark.parametrize("setup_status", ["PRE_TRIGGER", "TESTED_TRIGGER"])
def test_reviewable_unconfirmed_setup_waits_for_trigger(setup_status):
    signal = project_market_buy_signal(candidate(setup_status=setup_status))
    assert signal["signal"] == "BUY_ON_TRIGGER"
    assert signal["reason_codes"] == ["WAITING_FOR_COMPLETED_60M_TRIGGER"]


def test_buy_now_fails_closed_when_rr_or_entry_zone_is_invalid():
    bad_rr = candidate()
    bad_rr["setup"]["rr"]["to_target_1"] = 1.9
    assert project_market_buy_signal(bad_rr)["signal"] == "WAIT"

    extended = candidate(price=10.8)
    assert project_market_buy_signal(extended)["signal"] == "WAIT"


def test_stale_market_data_blocks_every_actionable_signal():
    row = candidate()
    row["data_status"]["intraday_60m_freshness"] = "stale"
    signal = project_market_buy_signal(row)
    assert signal["signal"] == "DATA_BLOCKED"
    assert signal["reason_codes"] == ["MARKET_EVIDENCE_NOT_FRESH_OR_COMPLETE"]


def test_avoid_lane_remains_avoid_for_unheld_symbol():
    signal = project_market_buy_signal(candidate(lane="AVOID", setup_status="INVALIDATED"))
    assert signal["signal"] == "AVOID"
    assert signal["policy_version"] == POLICY_VERSION


def test_market_buy_scan_does_not_require_portfolio_state():
    signal = project_market_buy_signal(candidate())
    assert signal["signal"] == "BUY_NOW"
    assert signal["scope"] == "MARKET_BUY_SCAN"
    assert "position" not in signal
    assert signal["execution"]["authorized"] is False
