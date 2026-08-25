"""Contract tests for non-actionable mover/caution lanes."""

from mvp_api import project_shortlist_response


def _base(symbol, stage, phase, change, volume_ratio, queue):
    return {
        "symbol": symbol,
        "stage": stage,
        "phase": phase,
        "action": "WAIT",
        "action_queue": queue,
        "close": 1.0,
        "change": change,
        "volumeRatio50": volume_ratio,
        "volumeSurge": True,
        "avgDailyValue20": 20_000_000,
        "dataFreshness": "fresh",
        "daily_eod_freshness": {"status": "latest_available", "source": "price_data", "as_of": "2026-08-25"},
        "setup_quality": {"pass": False, "reasons": ["range_too_wide", "vol_expanding"]},
        "setup_proximity": {"state": "action"},
        "riskStop": 0.9,
        "rs": 40,
    }


def test_movers_are_watch_only_and_not_ready():
    xpg = _base("XPG", "S1_basing", "base_early", 14.29, 9.06, "monitor_only")
    result = project_shortlist_response([xpg], snapshot_meta={"freshness": {}})
    assert result["ready"] == []
    assert result["pre_ready"] == []
    assert result["rising_movers"][0]["symbol"] == "XPG"
    assert result["rising_movers"][0]["action"] == "WATCH ONLY"
    assert result["rising_movers"][0]["publication_state"] == "WATCH_ONLY"
    assert result["rising_movers"][0]["rank_components"] == {}


def test_s3_movers_are_caution_and_do_not_chase():
    ziga = _base("ZIGA", "S3_distributing", "topping", 7.02, 6.21, "intraday_emerging")
    ziga["setup_quality"]["reasons"].append("extended")
    result = project_shortlist_response([ziga], snapshot_meta={"freshness": {}})
    assert result["ready"] == []
    assert result["caution"][0]["symbol"] == "ZIGA"
    assert result["caution"][0]["action"] == "DO NOT CHASE"
    assert result["caution"][0]["watch_state"] == "CAUTION"
