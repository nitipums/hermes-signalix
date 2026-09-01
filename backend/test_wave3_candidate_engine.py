"""Wave-3-only production candidate contract and adversarial regressions."""
import json
from pathlib import Path

import pandas as pd

from elliott_structure_engine import build_wave_contract
from setup_candidate_contract import project_decision_lane
from wave3_candidate_engine import (_raw, anchor_contradictions,
                                    classify_candles, classify_frame)


BASE = [10.2, 10.1, 9.8, 9.5, 9.8, 10.0, 10.5, 11, 12, 13, 14, 15,
        14.8, 14.2, 13.5, 12.8, 12, 12.2, 12.8, 13.5, 14.2, 14.7]


def candles(tail, volumes=None):
    values = [10.0] * 55 + tail
    volumes = volumes or [1000] * len(values)
    return [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
             "open": float(v), "high": float(v + .08), "low": float(v - .08),
             "close": float(v), "volume": float(volumes[i])}
            for i, v in enumerate(values)]


def frame(rows):
    return pd.DataFrame(rows).rename(columns={"open": "Open", "high": "High", "low": "Low",
                                                   "close": "Close", "volume": "Volume"}).set_index("date")


def test_only_wave3_states_are_publishable_and_api_fails_closed():
    for tail in ([], [10] * 20, BASE + [14.8, 14.9], BASE + [15.2, 15.4, 15.6]):
        contract = build_wave_contract(frame(candles(tail)))
        assert contract["primary_state"] in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION", "NOT_VERIFIABLE"}
        assert contract["state"] == contract["primary_state"]
        assert contract["policy"] == "wave3-confirmed-pivots-v1"
        assert "legacy_full_wave" in contract["audit_compatibility"]


def test_ordered_w1_w2_and_invalid_relation():
    result = _raw(candles(BASE + [14.8, 14.9]))
    low, high, w2 = (result["anchors"][k] for k in ("w1_low", "w1_high", "w2_low"))
    assert low["index"] < high["index"] < w2["index"]
    assert low["price"] < w2["price"] < high["price"]
    invalid = {"w1_low": {"index": 1, "price": 10}, "w1_high": {"index": 2, "price": 15},
               "w2_low": {"index": 3, "price": 9}}
    assert "invalid_w2_relation_requires_w1_low<w2_low<w1_high" in anchor_contradictions(invalid)


def test_close_only_early_continuation_and_post_impulse_exclusion():
    wick = candles(BASE + [14.8, 14.9]); wick[-1]["high"] = 16
    assert _raw(wick)["close_vs_wick_confirmation"] == "WICK_ONLY"
    assert _raw(wick)["raw_state"] != "WAVE_3_CONTINUATION"
    assert _raw(candles(BASE + [14.8, 14.9]))["raw_state"] == "EARLY_WAVE_3"
    assert _raw(candles(BASE + [15.2, 15.4, 15.6]))["raw_state"] == "WAVE_3_CONTINUATION"
    corrected = _raw(candles(BASE + [15.2, 15.6, 16.2, 17, 18, 17.8, 17.1, 16.2, 15.2]))
    assert corrected["raw_state"] == "NOT_VERIFIABLE"
    assert "post_impulse_correction_excluded" in corrected["rejection_reasons"]


def test_missing_short_flat_no_lookahead_hysteresis_and_json_safety():
    assert classify_candles([])["published_state"] == "NOT_VERIFIABLE"
    assert classify_candles(candles([])[:40])["published_state"] == "NOT_VERIFIABLE"
    flat = candles([10] * 10)
    for row in flat: row.update(open=10, high=10, low=10, close=10)
    assert classify_candles(flat)["published_state"] == "NOT_VERIFIABLE"
    prefix = candles(BASE + [14.8, 14.9])
    future = {**prefix[-1], "date": "2026-04-01", "open": 99, "high": 99, "low": 99, "close": 99}
    assert classify_candles(prefix) == classify_candles((prefix + [future])[:-1])
    result = classify_candles(prefix)
    assert result["evidence"]["adjacent_as_of_raw_states"] == ["EARLY_WAVE_3", "EARLY_WAVE_3"]
    json.dumps(build_wave_contract(frame(prefix)), allow_nan=False)


def test_bcp_bbgi_regression_snapshots_are_explicit_not_forced():
    root = Path("/tmp/signalix-wave-validation-20260901")
    observed = {}
    for symbol in ("BCP", "BBGI"):
        payload = json.loads((root / f"{symbol}-day.json").read_text())
        rows = [r for r in payload["candles"] if not r.get("provisional", False)]
        observed[symbol] = classify_candles(rows)
    assert observed["BCP"]["published_state"] == "NOT_VERIFIABLE"
    assert "no_valid_ordered_w1_w2_retracement" in observed["BCP"]["rejection_reasons"]
    assert observed["BBGI"]["published_state"] == "WAVE_3_CONTINUATION"
    assert observed["BBGI"]["follow_through"]["status"] == "PASS"


def test_dataframe_adapter_rejects_duplicate_dates():
    rows = candles(BASE + [14.8, 14.9])
    rows[-1]["date"] = rows[-2]["date"]
    assert classify_frame(frame(rows))["published_state"] == "NOT_VERIFIABLE"


def test_not_verifiable_is_wait_not_daily_candidate_when_data_is_available():
    wave = {"timeframe": "daily", "primary_state": "NOT_VERIFIABLE", "confidence": "LOW"}
    setup = {"timeframe": "60m", "status": "FORMING"}
    assert project_decision_lane({"sufficient": True, "freshness": "fresh"}, wave, setup) == "WAIT"
