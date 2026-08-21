"""Serialize + sort tests for setup state fields (Task 3 of stage-setup-state redesign).

NOTE: plan named test_compact_cards.py but that file exists only as uncommitted
master-working-tree work (not at HEAD). Controller ruling R7: dedicated file.
"""
from build_dashboard import serialize, dashboard_sort_key


def _s2_row():
    return {
        "symbol": "TEST", "close": 51.5, "last_date": "2026-08-19",
        "trend_template": {"ma": {"ma200": 40.0}, "conditions_met": 8,
                           "rs_rating": 80.0, "rs_threshold": 70.0},
        "trade_readiness": {"status": "BUY", "buy_zones_90d": {"50": 54.0, "62": 50.0},
                            "swing_high_90d": 60.0, "rsi_daily": 60.0,
                            "volume_ratio_50": 0.6, "range_20d_pct": 8.0,
                            "breakout_level_20d": 52.0},
        "daily_state": {
            "stage": "S2_uptrend", "phase": "uptrend_pullback",
            "setup_quality": {"pass": True, "reasons": ["tight_range"], "range_20d_pct": 8.0, "vol_ratio_50": 0.6},
            "setup_proximity": {"state": "near_trigger", "pivot": 60.0, "distance_pct": 0.02,
                                "zone": {"lo": 50.0, "hi": 54.0}},
        },
    }


def test_item_exposes_setup_state_and_radar():
    item = serialize("uptrend_pullback", _s2_row(), {})
    assert item["setup_quality"]["pass"] is True
    assert item["setup_proximity"]["state"] == "near_trigger"
    assert item["radar"] is True
    assert item["radarBadge"] == "WATCH"


def test_item_s3_radar_false():
    row = {
        "symbol": "TEST", "close": 30.0, "last_date": "2026-08-19",
        "trend_template": {"ma": {"ma200": 40.0}, "conditions_met": 3,
                           "rs_rating": 20.0, "rs_threshold": 70.0},
        "trade_readiness": {"status": "WAIT"},
        "daily_state": {
            "stage": "S3_distributing", "phase": "topping",
            "setup_quality": {"pass": False, "reasons": ["range_too_wide"], "range_20d_pct": 30.0, "vol_ratio_50": 1.5},
            "setup_proximity": {"state": None, "pivot": None, "distance_pct": None, "zone": None},
        },
    }
    item = serialize("down_or_broken", row, {})
    assert item["radar"] is False
    assert item["radarBadge"] is None


def test_item_quality_pass_action_is_ready():
    row = _s2_row()
    row["daily_state"]["setup_proximity"]["state"] = "action"
    item = serialize("uptrend_pullback", row, {})
    assert item["radar"] is True
    assert item["radarBadge"] == "READY"


def test_dashboard_sort_proximity_before_rs():
    mk = lambda prox, rs: {"stage": "S2_uptrend", "setup_proximity": {"state": prox}, "rs": rs}
    a = dashboard_sort_key(mk("near_trigger", 90))
    b = dashboard_sort_key(mk("action", 60))
    c = dashboard_sort_key(mk("forming", 99))
    assert b < a < c  # action first, then near_trigger, then forming (rs is last tiebreak)
