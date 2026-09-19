"""Focused tests for the isolated issue #7 Daily trend mapping seam."""

import json

from daily_trend_mapping import BROAD_STATES, MACHINE_LANES, classify_daily_trend


def snapshot(close=110.0, low=109.0, rsi=60.0, *, bars=300, support=100.0,
             ma20=100.0, ma60=90.0, high=None, previous_close=100.0,
             volume=100.0, open_price=None, prior_high=100.0):
    closes = [100.0] * bars
    closes[-2] = previous_close
    closes[-1] = close
    highs = [prior_high] * bars
    highs[-1] = close if high is None else high
    lows = [100.0] * bars
    lows[-1] = low
    ma_series = {str(period): [100.0] * bars for period in (20, 60, 120, 240)}
    return {
        "timeframe": "1D", "as_of": "2026-09-11", "provenance": {"source": "test"},
        "series": {"close": closes, "high": highs, "low": lows, "ma": ma_series},
        "latest": {"close": close, "low": low, "high": highs[-1],
                   "ma": {"20": ma20, "60": ma60, "120": 85.0, "240": 80.0},
                   "rsi": rsi, "macd": {"histogram": 1.0}, "volume": volume,
                   "window_summary": {"20": {"volume_average": 100.0}},
                   "explicit_support": support,
                   **({"open": open_price} if open_price is not None else {})},
    }


def test_every_lane_has_exact_broad_state_and_json_safe_output():
    distribution = snapshot(close=110, low=100, high=120, previous_close=115,
                            ma20=115, ma60=100, volume=150, open_price=105)
    cases = [
        snapshot(close=95, low=95, rsi=60, support=90, ma20=100, ma60=110, prior_high=200),
        snapshot(close=100, rsi=60, prior_high=200),
        snapshot(close=105, rsi=45, prior_high=200),
        snapshot(close=105, rsi=60, prior_high=200),
        distribution, snapshot(close=105, low=99, support=100),
        snapshot(close=90, low=90, previous_close=95, support=100, rsi=30, ma20=100, ma60=110, prior_high=200),
    ]
    results = [classify_daily_trend(item,
                                    {"machine_lane": "S4_1"} if index == 6 else None,
                                    {"bullish_rsi": 50, "bearish_rsi": 40})
               for index, item in enumerate(cases)]
    assert [result["machine_lane"] for result in results] == list(MACHINE_LANES)
    assert [result["broad_state"] for result in results] == [
        "BASING", "BASING", "EMERGING_UPTREND", "EMERGING_UPTREND",
        "DISTRIBUTING", "DOWNTREND", "DOWNTREND"]
    assert BROAD_STATES == {lane: result["broad_state"] for lane, result in zip(MACHINE_LANES, results)}
    for result in results:
        json.dumps(result, allow_nan=False)


def test_initial_wick_breach_is_price_event_and_records_metadata():
    result = classify_daily_trend(snapshot(close=105, low=99, support=100, rsi=80,
                                           ma20=90, ma60=80))
    assert result["machine_lane"] == "S4_1"
    assert result["break_metadata"] == {"break_type": "WICK_BREACH", "support_reference": 100.0,
                                        "close_below_support": False}


def test_s3_3_is_normal_distribution_classifier_result():
    result = classify_daily_trend(snapshot(close=110, low=100, high=120, previous_close=115,
                                           ma20=115, ma60=100, volume=150, open_price=105))
    assert result["machine_lane"] == "S3_3"
    assert result["broad_state"] == "DISTRIBUTING"
    assert result["break_metadata"] is None
    assert result["supporting_evidence"]
    assert result["contradicting_evidence"] == []


def test_s4_2_requires_two_daily_closes_and_medium_bearish_evidence():
    persistent = classify_daily_trend(snapshot(close=90, low=90, previous_close=95,
                                               support=100, rsi=30, ma20=100, ma60=110),
                                      {"machine_lane": "S4_1"}, {"bearish_rsi": 40})
    one_day = classify_daily_trend(snapshot(close=90, low=90, previous_close=105,
                                            support=100, rsi=30, ma20=100, ma60=110),
                                   {"machine_lane": "S4_1"}, {"bearish_rsi": 40})
    assert persistent["machine_lane"] == "S4_2"
    assert one_day["machine_lane"] == "S4_1"
    assert one_day["break_metadata"]["break_type"] == "WICK_BREACH"


def test_s3_3_downside_break_enters_s4_1_before_s4_2():
    result = classify_daily_trend(snapshot(close=90, low=100, previous_close=95,
                                           support=100, rsi=30, ma20=100, ma60=110),
                                  {"machine_lane": "S3_3"}, {"bearish_rsi": 40})
    assert result["machine_lane"] == "S4_1"
    assert result["machine_lane"] != "S4_2"
    assert result["break_metadata"] == {
        "break_type": "CLOSE_BELOW_SUPPORT",
        "support_reference": 100.0,
        "close_below_support": True,
    }


def test_recovery_and_normal_graph_have_no_skips():
    result = classify_daily_trend(snapshot(close=110, rsi=60), {"machine_lane": "S1_1"})
    assert result["machine_lane"] == "S1_2"
    assert result["transition"]["type"] == "NORMAL_STEP"
    recovery = classify_daily_trend(snapshot(close=105, low=104), {"machine_lane": "S4_1"})
    assert recovery["machine_lane"] == "S3_3"
    assert recovery["transition"]["type"] == "RECOVERY"
    terminal = classify_daily_trend(snapshot(close=110, rsi=60), {"machine_lane": "S4_2"})
    assert terminal["machine_lane"] == "S4_2"
    assert terminal["transition"]["type"] == "HOLD"


def test_full_transition_chain_is_deterministic_and_single_lane():
    lane = "S1_1"
    seen = []
    for target in MACHINE_LANES[1:]:
        if target == "S3_3":
            item = snapshot(close=110, low=100, high=120, previous_close=115,
                            ma20=115, ma60=100, volume=150, open_price=105)
        elif target == "S4_1":
            item = snapshot(close=105, low=99, support=100)
        elif target == "S4_2":
            item = snapshot(close=90, low=90, previous_close=95, support=100,
                            rsi=30, ma20=100, ma60=110)
        else:
            item = snapshot(close=110 if target != "S2_1" else 105,
                            rsi=60 if target == "S2_2" else 45)
        current = classify_daily_trend(item, {"machine_lane": lane}, {"bearish_rsi": 40})
        repeat = classify_daily_trend(item, {"machine_lane": lane}, {"bearish_rsi": 40})
        assert current["machine_lane"] in MACHINE_LANES
        assert repeat == current
        seen.append(current["machine_lane"])
        lane = current["machine_lane"]
    assert seen == ["S1_2", "S2_1", "S2_2", "S3_3", "S4_1", "S4_2"]


def test_missing_contradictory_and_fallback_series_data_fail_closed():
    result = classify_daily_trend({"timeframe": "1D", "latest": {"close": 10}})
    assert result["data_status"] == "DATA_BLOCKED"
    assert result["confidence"] == "LOW"
    assert result["machine_lane"] in MACHINE_LANES
    contradictory = classify_daily_trend(snapshot(close=105, rsi=40, prior_high=200),
                                          thresholds={"bullish_rsi": 60, "bearish_rsi": 30})
    assert contradictory["contradicting_evidence"] == ["rsi_bearish"]
    item = snapshot()
    item["series"]["rsi"] = [60.0] * 300
    item["series"]["macd"] = {"histogram": [1.0] * 300}
    del item["latest"]["rsi"]
    del item["latest"]["macd"]
    assert "rsi_bullish" in classify_daily_trend(item)["supporting_evidence"]


def test_support_requirement_and_full_history_are_preserved():
    item = snapshot()
    del item["latest"]["explicit_support"]
    assert classify_daily_trend(item)["data_status"] == "AVAILABLE"
    blocked = classify_daily_trend(item, {"machine_lane": "S4_1"})
    assert blocked["data_status"] == "DATA_BLOCKED"
    assert "explicit_support" in blocked["missing_evidence"]
    assert classify_daily_trend(snapshot(bars=400))["missing_evidence"] == []
