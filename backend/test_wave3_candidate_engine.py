"""Wave-3-only production candidate contract and adversarial regressions."""
import json
from pathlib import Path

import pandas as pd
import pytest

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


def test_daily_structure_exposes_full_wave_phase_without_promoting_it(monkeypatch):
    import elliott_structure_engine as engine

    monkeypatch.setattr(engine, "classify_wave_candidate", lambda *_: {
        "timeframe": "daily", "state": "WAVE_2_NEAR_COMPLETION", "confidence": "HIGH",
        "evidence": {"retracement_pct": 42, "wave1_low": 10, "wave1_high": 20,
                     "pullback_low": 14, "missing_evidence": []},
    })
    monkeypatch.setattr(engine, "classify_wave3_candidate", lambda *_: {
        "published_state": "EARLY_WAVE_3", "raw_state": "EARLY_WAVE_3", "confidence": "MEDIUM",
        "anchors": {}, "evidence": {}, "rejection_reasons": [],
    })
    result = build_wave_contract(frame(candles([10] * 5)), snapshot_id="daily:test")
    daily = result["daily_structure"]
    assert result["primary_state"] == "EARLY_WAVE_3"
    assert daily["phase"] == "WAVE_2_NEAR_COMPLETION"
    assert daily["actionability"] == "NONE"
    assert daily["source_timeframe"] == "daily"
    assert daily["policy_version"] == "daily-structure-evidence-v1"
    assert daily["retracement"] == pytest.approx(0.42)
    assert daily["snapshot_id"] == "daily:test"


def test_daily_structure_unknown_keeps_missing_evidence_explicit():
    result = build_wave_contract(pd.DataFrame())
    daily = result["daily_structure"]
    assert result["primary_state"] == "NOT_VERIFIABLE"
    assert daily["phase"] == "UNKNOWN"
    assert daily["actionability"] == "NONE"
    assert "full_wave_phase" in daily["missing_evidence"]
    assert daily["source_timeframe"] == "daily"


def test_ordered_w1_w2_and_invalid_relation():
    result = _raw(candles(BASE + [14.8, 14.9]))
    low, high, w2 = (result["anchors"][k] for k in ("w1_low", "w1_high", "w2_low"))
    assert low["index"] < high["index"] < w2["index"]
    assert low["price"] < w2["price"] < high["price"]
    invalid = {"w1_low": {"index": 1, "price": 10}, "w1_high": {"index": 2, "price": 15},
               "w2_low": {"index": 3, "price": 9}}
    assert "invalid_w2_relation_requires_w1_low<w2_low<w1_high" in anchor_contradictions(invalid)


def test_invalid_anchor_denominator_fails_closed_without_wave3_publication():
    flat = candles([10] * 10)
    raw = _raw(flat)
    assert raw["raw_state"] == "NOT_VERIFIABLE"
    assert raw["retracement"] is None
    assert "no_valid_ordered_w1_w2_retracement" in raw["rejection_reasons"]


def test_close_only_early_continuation_and_post_impulse_exclusion():
    wick = candles(BASE + [14.8, 14.9]); wick[-1]["high"] = 16
    assert _raw(wick)["close_vs_wick_confirmation"] == "WICK_ONLY"
    assert _raw(wick)["raw_state"] != "WAVE_3_CONTINUATION"
    assert _raw(candles(BASE + [14.8, 14.9]))["raw_state"] == "NOT_VERIFIABLE"
    assert _raw(candles(BASE + [15.2, 15.4, 15.6]))["raw_state"] == "WAVE_3_CONTINUATION"
    corrected = _raw(candles(BASE + [15.2, 15.6, 16.2, 17, 18, 17.8, 17.1, 16.2, 15.2]))
    assert corrected["raw_state"] == "NOT_VERIFIABLE"
    assert "post_impulse_correction_excluded" in corrected["rejection_reasons"]


@pytest.mark.parametrize("retracement", [0.5999, 0.6000])
@pytest.mark.parametrize("state", ["EARLY_WAVE_3", "WAVE_3_CONTINUATION"])
def test_publication_boundary_allows_raw_retracement_at_or_below_sixty(monkeypatch, retracement, state):
    candidate = {"raw_state": state, "published_state": state, "retracement": retracement,
                 "rejection_reasons": [], "evidence": {}}
    monkeypatch.setattr("wave3_candidate_engine._raw", lambda _candles: dict(candidate))
    monkeypatch.setattr("wave3_candidate_engine._safe", lambda value: value)
    result = classify_candles(candles([10] * 5))
    assert result["published_state"] == state


@pytest.mark.parametrize("retracement", [0.6001, 0.6049, 0.625])
@pytest.mark.parametrize("state", ["EARLY_WAVE_3", "WAVE_3_CONTINUATION"])
def test_publication_boundary_blocks_raw_retracement_above_sixty_even_with_hysteresis(monkeypatch, retracement, state):
    candidate = {"raw_state": state, "published_state": state, "retracement": retracement,
                 "rejection_reasons": [], "evidence": {}}
    monkeypatch.setattr("wave3_candidate_engine._raw", lambda _candles: dict(candidate))
    monkeypatch.setattr("wave3_candidate_engine._safe", lambda value: value)
    result = classify_candles(candles([10] * 5))
    assert result["raw_state"] == state
    assert result["published_state"] == "NOT_VERIFIABLE"
    assert "retracement_gate_exceeded" in result["rejection_reasons"]
    assert "adjacent_as_of_hysteresis_not_satisfied" not in result["rejection_reasons"]


@pytest.mark.parametrize("retracement", [None, float("nan")])
def test_publication_requires_finite_raw_retracement(monkeypatch, retracement):
    candidate = {"raw_state": "EARLY_WAVE_3", "published_state": "EARLY_WAVE_3",
                 "retracement": retracement, "rejection_reasons": [], "evidence": {}}
    monkeypatch.setattr("wave3_candidate_engine._raw", lambda _candles: dict(candidate))
    monkeypatch.setattr("wave3_candidate_engine._safe", lambda value: value)
    result = classify_candles(candles([10] * 5))
    assert result["published_state"] == "NOT_VERIFIABLE"
    assert "retracement_gate_unmeasured" in result["rejection_reasons"]


@pytest.mark.parametrize("symbol, expected_retracement", [("CRC", 0.7307692307692308), ("BGRIM", 0.6249999999999999)])
def test_frozen_crc_bgrim_candidates_do_not_publish_above_raw_gate(symbol, expected_retracement):
    payload = json.loads((Path(__file__).parent / "fixtures" / "elliott" / f"{symbol}_daily_1y.json").read_text())
    daily = pd.DataFrame(payload["rows"]).rename(
        columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    )
    daily.index = pd.date_range("2026-01-01", periods=len(daily), freq="D")
    candidate = classify_frame(daily.drop(columns=["date"]))
    assert candidate["retracement"] == pytest.approx(expected_retracement)
    assert candidate["published_state"] == "NOT_VERIFIABLE"
    if candidate["raw_state"] in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"}:
        assert "retracement_gate_exceeded" in candidate["rejection_reasons"]


def test_hysteresis_suppresses_only_an_otherwise_eligible_candidate(monkeypatch):
    calls = {"count": 0}
    def raw(_candles):
        calls["count"] += 1
        state = "EARLY_WAVE_3" if len(_candles) == 60 else "NOT_VERIFIABLE"
        return {"raw_state": state, "published_state": state, "retracement": 0.60,
                "rejection_reasons": [], "evidence": {}}
    monkeypatch.setattr("wave3_candidate_engine._raw", raw)
    monkeypatch.setattr("wave3_candidate_engine._safe", lambda value: value)
    result = classify_candles(candles([10] * 5))
    assert result["published_state"] == "NOT_VERIFIABLE"
    assert "adjacent_as_of_hysteresis_not_satisfied" in result["rejection_reasons"]


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
    assert result["evidence"]["adjacent_as_of_raw_states"] == ["NOT_VERIFIABLE", "NOT_VERIFIABLE"]
    json.dumps(build_wave_contract(frame(prefix)), allow_nan=False)


def test_bcp_bbgi_regression_snapshots_are_explicit_not_forced():
    root = Path("/tmp/signalix-wave-validation-20260901")
    missing = [symbol for symbol in ("BCP", "BBGI")
               if not (root / f"{symbol}-day.json").is_file()]
    if missing:
        pytest.skip("external wave validation fixtures unavailable: " + ", ".join(missing))
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
