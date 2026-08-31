"""T2 contract tests: Daily Elliott engine production boundary (spec §2.2/§2.7).

Deterministic fixtures are frozen 1Y Daily OHLCV for CRC/BGRIM/AWC (as_of
2026-08-28, price_data market=TH, read-only replay path). Regenerate only with
fixtures/elliott/generate_fixtures.py and only with owner approval.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from elliott_structure_engine import (
    WAVE_STATES,
    _swing_legs_ohlc,
    build_wave_contract,
    classify_wave_candidate,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "elliott"
WAVE_ENUM = {
    "WAVE_1_ADVANCE",
    "WAVE_2_FORMING",
    "WAVE_2_NEAR_COMPLETION",
    "EARLY_WAVE_3",
    "WAVE_3_CONTINUATION",
    "WAVE_4_CORRECTION",
    "WAVE_5_ADVANCE",
    "UNKNOWN",
}

# Owner-verified ground truth (decision record 2026-08-31, chart-gate approved).
EXPECTED_STATES = {
    "CRC": "WAVE_1_ADVANCE",       # retrace 85.71% > 60% must NOT promote to W3
    "BGRIM": "WAVE_3_CONTINUATION",  # retrace 29.17%, close above Wave 1 high
    "AWC": "WAVE_1_ADVANCE",       # retrace 91.18% > 60% must NOT promote to W3
}


def load_frame(symbol: str) -> pd.DataFrame:
    fixture = json.loads((FIXTURE_DIR / f"{symbol}_daily_1y.json").read_text())
    assert fixture["symbol"] == symbol and fixture["as_of"] == "2026-08-28"
    return pd.DataFrame(fixture["rows"]).rename(
        columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    )


def rising_frame(values):
    close = pd.Series(values, dtype=float)
    return pd.DataFrame({"Close": close, "Open": close, "High": close, "Low": close, "Volume": 1})


def test_engine_states_stay_within_spec_enum():
    assert WAVE_STATES == WAVE_ENUM
    assert "INVALIDATED" not in WAVE_STATES
    assert "EXTENDED" not in WAVE_STATES


@pytest.mark.parametrize("symbol", ["CRC", "BGRIM", "AWC"])
def test_frozen_fixture_reproduces_owner_verified_state(symbol):
    result = classify_wave_candidate(load_frame(symbol))
    assert result["state"] == EXPECTED_STATES[symbol]


@pytest.mark.parametrize("symbol", ["CRC", "BGRIM", "AWC"])
def test_retracement_gate_blocks_wave3_promotion(symbol):
    """CRC/AWC retrace >60% must never reach EARLY_WAVE_3/WAVE_3_CONTINUATION."""
    result = classify_wave_candidate(load_frame(symbol))
    retrace = result["evidence"]["retracement_pct"]
    assert retrace is not None
    if retrace > 60:
        assert result["state"] not in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"}
        assert result["state"] in {"WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_4_CORRECTION", "UNKNOWN"}
    else:
        assert result["evidence"]["holds_above_wave1_low"] is not False


@pytest.mark.parametrize("symbol", ["CRC", "BGRIM", "AWC"])
def test_wave_contract_shape_and_confidence(symbol):
    contract = build_wave_contract(load_frame(symbol))
    assert contract["timeframe"] == "daily"
    assert contract["primary_state"] == EXPECTED_STATES[symbol]
    assert contract["alternative_state"] in WAVE_ENUM
    assert contract["confidence"] in {"LOW", "MEDIUM", "HIGH"}
    for key in ("supporting_evidence", "contradicting_evidence", "missing_evidence"):
        assert isinstance(contract[key], list)
    assert contract["policy"] == "elliott-v1-observable-proxy"
    json.dumps(contract)  # JSON-safe boundary


def test_unknown_contract_still_exposes_arrays_and_low_confidence():
    contract = build_wave_contract(None, {})
    assert contract["primary_state"] == "UNKNOWN"
    assert contract["alternative_state"] == "UNKNOWN"
    assert contract["confidence"] == "LOW"
    assert "daily_ohlcv" in contract["missing_evidence"]
    assert contract["supporting_evidence"] == []
    json.dumps(contract)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda frame: frame.drop(columns=["High"]),
        lambda frame: frame.drop(columns=["Low"]),
        lambda frame: frame.assign(High=lambda value: value["High"].mask(value.index == 3)),
        lambda frame: frame.assign(Low=lambda value: value["Low"].mask(value.index == 3)),
        lambda frame: frame.assign(High=lambda value: value["High"].mask(value.index == 3, 0)),
        lambda frame: frame.assign(Low=lambda value: value["Low"].mask(value.index == 3, -1)),
        lambda frame: frame.assign(High=lambda value: value["High"].mask(value.index == 3, value["Low"] - 1)),
        lambda frame: frame.assign(Open=lambda value: value["Open"].mask(value.index == 3, value["High"] + 1)),
    ],
)
def test_invalid_or_incomplete_daily_ohlc_fails_closed(mutate):
    daily = rising_frame(list(range(1, 26)))
    daily = mutate(daily)

    assert _swing_legs_ohlc(daily) == []
    contract = build_wave_contract(daily)
    assert contract["primary_state"] == "UNKNOWN"
    assert contract["confidence"] == "LOW"
    assert "daily_ohlcv" in contract["missing_evidence"]
    assert contract["evidence"].get("ohlc_swing_legs") is None


def test_valid_flat_daily_candle_is_not_rejected_as_malformed_ohlc():
    daily = rising_frame([10] * 25)
    assert _swing_legs_ohlc(daily) == []
    contract = build_wave_contract(daily)
    assert contract["primary_state"] == "UNKNOWN"
    assert "daily_ohlcv" not in contract["missing_evidence"]


def test_confidence_tokens_map_into_contract_scale():
    short = build_wave_contract(rising_frame([10] * 10), {})
    assert short["confidence"] in {"LOW", "MEDIUM", "HIGH"}
    assert short["primary_state"] in WAVE_ENUM


def test_dual_degree_is_evidence_only_and_never_alters_large_state():
    for symbol in ("CRC", "BGRIM", "AWC"):
        frame = load_frame(symbol)
        with_small = build_wave_contract(frame)
        assert isinstance(with_small.get("dual_degree"), dict)
        assert with_small["dual_degree"]["large"]["pct"] == 0.05
        assert with_small["dual_degree"]["large"]["bars"] == 5
        assert with_small["dual_degree"]["small"]["pct"] == 0.03
        assert with_small["dual_degree"]["small"]["bars"] == 2
        assert with_small["evidence"].get("small_wave_legs") is not None
        # Small degree lives in evidence only; contract primary fields stay large-degree.
        assert with_small["primary_state"] == EXPECTED_STATES[symbol]


def test_dual_degree_labels_and_structure_are_deterministic():
    contract = build_wave_contract(load_frame("BGRIM"))
    assert contract["dual_degree"]["large"]["label"] == "1,2,3"
    assert contract["dual_degree"]["small"]["label"] == "(1),(2),(3)"
    labels = contract["evidence"].get("small_wave_labels")
    assert labels is not None and isinstance(labels, list)


def test_wave_contract_confidence_respects_review_lane_boundary():
    """Only MEDIUM/HIGH may be actionable downstream; LOW never reaches REVIEW_NOW."""
    for symbol in ("CRC", "BGRIM", "AWC"):
        contract = build_wave_contract(load_frame(symbol))
        if contract["primary_state"] == "UNKNOWN":
            assert contract["confidence"] == "LOW"
        else:
            assert contract["confidence"] in {"MEDIUM", "HIGH"}


def test_contradicting_evidence_flags_broken_gates():
    """>60% retrace + 30-day pullback fails the W2 window → unknown fail-closed."""
    values = list(range(1, 51)) + list(range(50, 19, -1)) + [21.0] * 3
    contract = build_wave_contract(rising_frame(values))
    assert contract["primary_state"] == "UNKNOWN"
    assert contract["confidence"] == "LOW"
    evidence = contract["evidence"]
    assert evidence["retracement_pct"] > 60
    assert evidence["pullback_duration_days"] > 25


def test_unknown_from_failed_gates_does_not_claim_positive_confidence():
    """>60% retrace must stay UNKNOWN with LOW confidence — never a positive candidate."""
    values = list(range(1, 51)) + list(range(50, 15, -1)) + [20.0] * 3
    contract = build_wave_contract(rising_frame(values))
    assert contract["primary_state"] == "UNKNOWN"
    assert contract["confidence"] == "LOW"
    assert contract["primary_state"] not in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION", "WAVE_2_NEAR_COMPLETION"}


def test_wave1_low_break_routes_away_from_wave2_near_completion():
    """>60% retrace or Wave1-low break routes to WAVE_4_CORRECTION/UNKNOWN, never W2-NC."""
    broken = list(range(1, 51)) + list(range(50, 24, -1)) + [14.0, 13.5]
    result = classify_wave_candidate(rising_frame(broken))
    retrace = result["evidence"].get("retracement_pct")
    holds = result["evidence"].get("holds_above_wave1_low")
    if (retrace is not None and retrace > 60) or holds is False:
        assert result["state"] in {"WAVE_4_CORRECTION", "WAVE_2_FORMING", "UNKNOWN", "WAVE_1_ADVANCE"}
        assert result["state"] not in {"WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3", "WAVE_3_CONTINUATION"}
