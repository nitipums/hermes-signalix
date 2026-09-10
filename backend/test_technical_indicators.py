"""Focused deterministic technical-indicator contract tests."""

import json
import math

import pytest

import mvp_chart_db
from technical_indicators import (
    HIGH_LOW_PERIODS,
    MA_PERIODS,
    POLICY_VERSION,
    build_technical_indicators,
)


def _candles(count=260):
    candles = []
    for index in range(count):
        close = 100.0 + index + (0.5 if index % 2 else -0.25)
        candles.append({
            "date": f"2025-01-{index + 1:03d}",
            "open": close - 0.4,
            "high": close + 1.25,
            "low": close - 1.5,
            "close": close,
            "volume": 1000.0 + index,
            "provisional": False,
        })
    return candles


def test_schema_is_aligned_json_safe_and_preserves_latest_high_low():
    candles = _candles()
    result = build_technical_indicators(candles, "1D")

    assert result["policy_version"] == POLICY_VERSION == "technical-indicators-v1"
    assert result["timeframe"] == "1D"
    assert result["alignment"] == "candle_index"
    assert set(result["series"]["ma"]) == {"5", "10", "20", "60", "120", "240"}
    assert MA_PERIODS == (5, 10, 20, 60, 120, 240)
    assert HIGH_LOW_PERIODS == (5, 10, 20, 60, 120, 260)
    assert set(result["series"]["rolling_high"]) == {"5", "10", "20", "60", "120", "260"}
    assert set(result["series"]["rolling_low"]) == {"5", "10", "20", "60", "120", "260"}
    for values in result["series"]["ma"].values():
        assert len(values) == len(candles)
    for key in ("rsi", "atr", "high", "low"):
        assert len(result["series"][key]) == len(candles)
    for key in ("line", "signal", "histogram"):
        assert len(result["series"]["macd"][key]) == len(candles)
    assert result["series"]["high"] == [row["high"] for row in candles]
    assert result["series"]["low"] == [row["low"] for row in candles]
    assert result["latest"]["high"] == candles[-1]["high"]
    assert result["latest"]["low"] == candles[-1]["low"]
    assert set(result["latest"]["ma"]) == {"5", "10", "20", "60", "120", "240"}
    assert set(result["latest"]["rolling_high_low"]) == {"5", "10", "20", "60", "120", "260"}
    assert result["provenance"]["no_lookahead"] is True
    json.dumps(result, allow_nan=False)


def test_rolling_high_low_exact_windows_and_first_available_boundary():
    candles = _candles(12)
    highs = [10, 12, 11, 15, 14, 13, 16, 9, 18, 17, 8, 20]
    lows = [5, 4, 6, 3, 7, 2, 8, 1, 9, 0, -1, 10]
    for candle, high, low in zip(candles, highs, lows):
        candle["high"], candle["low"] = high, low
        candle["close"] = (high + low) / 2

    result = build_technical_indicators(candles, "1D")

    assert result["series"]["rolling_high"]["5"][:4] == [None] * 4
    assert result["series"]["rolling_low"]["5"][:4] == [None] * 4
    assert result["series"]["rolling_high"]["5"][4:] == [15, 15, 16, 16, 18, 18, 18, 20]
    assert result["series"]["rolling_low"]["5"][4:] == [3, 2, 2, 1, 1, 0, -1, -1]
    assert result["series"]["rolling_high"]["10"][8] is None
    assert result["series"]["rolling_high"]["10"][9] == 18
    assert result["series"]["rolling_low"]["10"][9] == 0
    assert result["latest"]["rolling_high_low"]["5"] == {"high": 20, "low": -1}
    assert result["latest"]["rolling_high_low"]["10"] == {"high": 20, "low": -1}
    assert result["latest"]["rolling_high_low"]["20"] == {"high": None, "low": None}


def test_rolling_260_exact_window_boundary_and_ma240_remains_present():
    candles = _candles(261)
    candles[0]["high"], candles[0]["low"] = 9999, -9999
    candles[1]["high"], candles[1]["low"] = 700, -700
    result = build_technical_indicators(candles, "1D")

    assert result["series"]["rolling_high"]["260"][258] is None
    assert result["series"]["rolling_low"]["260"][258] is None
    assert result["series"]["rolling_high"]["260"][259] == 9999
    assert result["series"]["rolling_low"]["260"][259] == -9999
    assert result["series"]["rolling_high"]["260"][260] == 700
    assert result["series"]["rolling_low"]["260"][260] == -700
    assert result["series"]["ma"]["240"][239] is not None
    assert "260" not in result["series"]["ma"]
    assert "240" not in result["series"]["rolling_high"]
    assert result["availability"]["rolling_high_260"] == {
        "status": "AVAILABLE", "required_candles": 260, "available_candles": 261,
    }


def test_rolling_high_low_availability_reports_each_period():
    result = build_technical_indicators(_candles(19), "1D")
    assert result["availability"]["rolling_high_5"] == {
        "status": "AVAILABLE", "required_candles": 5, "available_candles": 19,
    }
    assert result["availability"]["rolling_low_20"] == {
        "status": "NOT_VERIFIED", "required_candles": 20, "available_candles": 19,
    }


def test_sma_macd_rsi_and_atr_use_documented_seed_and_wilder_rules():
    candles = _candles(50)
    result = build_technical_indicators(candles, "60M")
    closes = [row["close"] for row in candles]

    assert result["series"]["ma"]["5"][3] is None
    assert result["series"]["ma"]["5"][4] == round(sum(closes[:5]) / 5, 4)
    assert result["series"]["ma"]["5"][-1] == round(sum(closes[-5:]) / 5, 4)

    # EMA12/26 are SMA-seeded; MACD first exists at index 25 and signal at 33.
    assert result["series"]["macd"]["line"][24] is None
    assert result["series"]["macd"]["line"][25] is not None
    assert result["series"]["macd"]["signal"][32] is None
    assert result["series"]["macd"]["signal"][33] is not None
    assert result["series"]["macd"]["histogram"][33] == round(
        result["series"]["macd"]["line"][33]
        - result["series"]["macd"]["signal"][33], 4
    )

    assert result["series"]["rsi"][13] is None
    assert result["series"]["rsi"][14] is not None
    # ATR14 starts after 14 true ranges; first TR is high-low without prev_close.
    true_ranges = [candles[0]["high"] - candles[0]["low"]]
    for index in range(1, 14):
        row = candles[index]
        prev_close = candles[index - 1]["close"]
        true_ranges.append(max(row["high"] - row["low"],
                               abs(row["high"] - prev_close),
                               abs(row["low"] - prev_close)))
    assert result["series"]["atr"][12] is None
    assert result["series"]["atr"][13] == round(sum(true_ranges) / 14, 4)


@pytest.mark.parametrize("timeframe", ["1D", "1W", "60M", "1M"])
def test_insufficient_history_is_explicit_null_for_every_timeframe(timeframe):
    result = build_technical_indicators(_candles(4), timeframe)
    assert result["timeframe"] == timeframe
    assert result["latest"]["ma"] == {str(p): None for p in (5, 10, 20, 60, 120, 240)}
    assert result["latest"]["macd"] == {"line": None, "signal": None, "histogram": None}
    assert result["latest"]["rsi"] is None
    assert result["latest"]["atr"] is None
    assert result["latest"]["rolling_high_low"] == {
        str(p): {"high": None, "low": None} for p in (5, 10, 20, 60, 120, 260)
    }
    assert result["availability"]["ma_5"]["status"] == "NOT_VERIFIED"
    assert result["availability"]["atr"]["required_candles"] == 14


def test_empty_series_is_not_verified_instead_of_vacuously_available():
    result = build_technical_indicators([], "1D")
    assert result["series"]["high"] == []
    assert result["availability"]["input"]["status"] == "NOT_VERIFIED"
    assert result["latest"]["close"] is None


def test_as_of_prefix_never_changes_prior_indicator_values():
    candles = _candles(280)
    prefix = build_technical_indicators(candles[:270], "1D")
    full = build_technical_indicators(candles, "1D")
    assert full["series"]["ma"]["20"][:270] == prefix["series"]["ma"]["20"]
    assert full["series"]["macd"]["line"][:270] == prefix["series"]["macd"]["line"]
    assert full["series"]["macd"]["signal"][:270] == prefix["series"]["macd"]["signal"]
    assert full["series"]["rsi"][:270] == prefix["series"]["rsi"]
    assert full["series"]["atr"][:270] == prefix["series"]["atr"]
    for period in ("5", "10", "20", "60", "120", "260"):
        assert full["series"]["rolling_high"][period][:270] == prefix["series"]["rolling_high"][period]
        assert full["series"]["rolling_low"][period][:270] == prefix["series"]["rolling_low"][period]


def test_non_finite_market_input_fails_closed_and_remains_json_safe():
    candles = _candles(20)
    candles[7]["close"] = math.nan
    result = build_technical_indicators(candles, "1D")
    assert result["availability"]["input"]["status"] == "NOT_VERIFIED"
    assert all(value is None for value in result["series"]["rsi"])
    assert all(value is None for value in result["series"]["rolling_high"]["5"])
    assert result["series"]["high"][7] == candles[7]["high"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("timeframe", ["1D", "1W", "60M", "1M"])
def test_chart_api_projection_exposes_canonical_schema_for_each_timeframe(monkeypatch, timeframe):
    candles = _candles(40)

    class Cursor:
        def close(self):
            pass

    class Connection:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(mvp_chart_db, "_get_db_connection", lambda: Connection())
    monkeypatch.setattr(mvp_chart_db, "_release_db_connection", lambda connection: None)
    monkeypatch.setattr(mvp_chart_db, "_fetch_candles_with_metadata",
                        lambda cursor, symbol, timeframe: (candles, {"as_of": candles[-1]["date"]}))
    response = mvp_chart_db.project_chart_db_response("TEST", timeframe=timeframe)
    assert response["timeframe"] == timeframe
    assert response["candles"][-1]["high"] == candles[-1]["high"]
    assert response["candles"][-1]["low"] == candles[-1]["low"]
    assert response["indicators"]["timeframe"] == timeframe
    assert len(response["indicators"]["series"]["atr"]) == len(candles)
    assert len(response["indicators"]["series"]["rolling_high"]["20"]) == len(candles)
    assert response["indicators"]["latest"]["rolling_high_low"]["20"] == {
        "high": max(row["high"] for row in candles[-20:]),
        "low": min(row["low"] for row in candles[-20:]),
    }
    assert set(response["indicators"]["series"]["rolling_high"]) == {
        "5", "10", "20", "60", "120", "260",
    }
    json.dumps(response, allow_nan=False)
