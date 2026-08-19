"""Setup state (quality gate + proximity) tests — Task 1 of stage-setup-state redesign."""
import pytest
from setup_state import (
    compute_setup_quality,
    compute_setup_proximity,
    compute_setup_state,
    SETUP_PROXIMITY_PCT,
    EXTENDED_FROM_TRIGGER_PCT,
    EXTENDED_RSI,
    TIGHT_RANGE_20D_PCT,
)


def _ev(close=50.0, stage="S1_basing", pivot=52.0, rsi=60.0, range20=8.0,
        vol_ratio=0.6, buy_zones=None, swing_high=None):
    e = {"close": close, "rolling_trigger": pivot, "rsi_daily": rsi,
         "range_20d_pct": range20, "volume_ratio_50": vol_ratio,
         "buy_zones_90d": buy_zones, "swing_high_90d": swing_high}
    return e


def test_quality_pass_all_criteria():
    q = compute_setup_quality(_ev())
    assert q["pass"] is True
    assert "tight_range" in q["reasons"]
    assert "vol_contraction" in q["reasons"]
    assert "not_extended" in q["reasons"]


def test_quality_fail_wide_range():
    q = compute_setup_quality(_ev(range20=25.0))
    assert q["pass"] is False
    assert "range_too_wide" in q["reasons"]


def test_quality_fail_expanding_volume():
    q = compute_setup_quality(_ev(vol_ratio=2.5))
    assert q["pass"] is False
    assert "vol_expanding" in q["reasons"]


def test_quality_fail_extended():
    q = compute_setup_quality(_ev(close=60.0, pivot=52.0))  # +15% above pivot
    assert q["pass"] is False
    assert "extended" in q["reasons"]


def test_quality_fail_overbought_rsi():
    q = compute_setup_quality(_ev(rsi=80.0))
    assert q["pass"] is False
    assert "extended" in q["reasons"]


def test_s1_near_trigger():
    # close 49.8 vs pivot 52.0 => -4.2% => within 5% proximity
    p = compute_setup_proximity("S1_basing", _ev(close=49.8, pivot=52.0))
    assert p["state"] == "near_trigger"
    assert p["pivot"] == 52.0
    assert p["distance_pct"] is not None


def test_s1_action_breakout():
    p = compute_setup_proximity("S1_basing", _ev(close=52.5, pivot=52.0))
    assert p["state"] == "action"


def test_s1_extended():
    p = compute_setup_proximity("S1_basing", _ev(close=57.0, pivot=52.0))  # +9.6%
    assert p["state"] == "extended"


def test_s1_forming():
    p = compute_setup_proximity("S1_basing", _ev(close=45.0, pivot=52.0))  # -13%
    assert p["state"] == "forming"


def test_s1_no_pivot_is_forming():
    p = compute_setup_proximity("S1_basing", _ev(pivot=None))
    assert p["state"] == "forming"
    assert p["pivot"] is None


def test_s2_action_in_zone():
    # buy_zones_90d {"50": 54.0, "62": 50.0} -> zone lo 50.0 hi 54.0
    e = _ev(stage="S2_uptrend", close=52.0, buy_zones={"50": 54.0, "62": 50.0}, swing_high=60.0)
    p = compute_setup_proximity("S2_uptrend", e)
    assert p["state"] == "action"
    assert p["zone"] == {"lo": 50.0, "hi": 54.0}


def test_s2_near_trigger_above_zone():
    e = _ev(stage="S2_uptrend", close=55.5, buy_zones={"50": 54.0, "62": 50.0}, swing_high=60.0)
    p = compute_setup_proximity("S2_uptrend", e)
    assert p["state"] == "near_trigger"


def test_s2_forming_below_zone():
    e = _ev(stage="S2_uptrend", close=47.0, buy_zones={"50": 54.0, "62": 50.0}, swing_high=60.0)
    p = compute_setup_proximity("S2_uptrend", e)
    assert p["state"] == "forming"


def test_s2_extended_rsi():
    e = _ev(stage="S2_uptrend", close=52.0, rsi=78.0, buy_zones={"50": 54.0, "62": 50.0}, swing_high=60.0)
    p = compute_setup_proximity("S2_uptrend", e)
    assert p["state"] == "extended"


def test_s2_extended_beyond_leg_high():
    e = _ev(stage="S2_uptrend", close=66.0, buy_zones={"50": 54.0, "62": 50.0}, swing_high=60.0)
    p = compute_setup_proximity("S2_uptrend", e)
    assert p["state"] == "extended"


def test_s3_s4_proximity_null():
    assert compute_setup_proximity("S3_distributing", _ev())["state"] is None
    assert compute_setup_proximity("S4_down", _ev())["state"] is None


def test_compute_setup_state_bundle():
    out = compute_setup_state("S1_basing", _ev())
    assert out["quality"]["pass"] is True
    assert out["proximity"]["state"] in ("near_trigger", "action", "forming", "extended")


def test_all_outputs_json_safe():
    import json
    out = compute_setup_state("S2_uptrend", _ev(stage="S2_uptrend", close=52.0,
                                                buy_zones={"50": 54.0, "62": 50.0}, swing_high=60.0))
    json.dumps(out)  # must not raise (no numpy scalars)


# --- Integration: group_scan_results attaches setup state ---
def _row(close=50.0, stage_hint=None):
    return {
        "symbol": "TEST",
        "close": close,
        "last_date": "2026-08-19",
        "trend_template": {
            "ma": {"ma50": 49.0, "ma150": 45.0, "ma200": 40.0},
            "conditions_met": 8, "rs_rating": 80.0, "rs_threshold": 70.0,
        },
        "trade_readiness": {
            "above_ma50": True, "above_ma150": True, "above_ma200": True,
            "ma50_slope_20d_pct": 1.5, "ma150_slope_20d_pct": 1.0, "ma200_slope_20d_pct": 0.8,
            "rsi_daily": 60.0, "macd": 0.1, "volume_ratio_50": 0.6,
            "breakout_level_20d": 52.0, "range_20d_pct": 8.0, "status": "BUY",
            "buy_zones_90d": {"50": 54.0, "62": 50.0}, "swing_high_90d": 60.0,
        },
        "vcp": {"is_vcp": True},
        "trend_source": "daily",
    }


def test_group_scan_attaches_setup_fields(monkeypatch):
    from screening import group_scan_results
    rows = [_row(close=51.5)]  # S2 uptrend, near_trigger
    groups = group_scan_results(rows, events={})
    flat = [r for values in groups.values() for r in values]
    assert len(flat) == 1
    ds = flat[0]["daily_state"]
    assert "setup_quality" in ds and "setup_proximity" in ds
    assert ds["setup_quality"]["pass"] is True
    assert ds["setup_proximity"]["state"] in ("near_trigger", "action", "forming", "extended")


def test_group_scan_s4_proximity_null(monkeypatch):
    from screening import group_scan_results
    row = _row(close=30.0)
    row["trade_readiness"].update({"above_ma50": False, "above_ma150": False, "above_ma200": False,
                                   "ma200_slope_20d_pct": -1.5})
    groups = group_scan_results([row], events={})
    flat = [r for values in groups.values() for r in values]
    ds = flat[0]["daily_state"]
    assert ds["stage"] == "S4_down"
    assert ds["setup_proximity"]["state"] is None
    assert ds["setup_quality"]["pass"] is False  # quality still computed (never omitted)