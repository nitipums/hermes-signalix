import pandas as pd
import numpy as np
from screening import compute_layer2_momentum

MOMENTUM_VALID = {"strong", "up", "down", "overbought", "oversold", "neutral"}


def _make_60m(close_trend, n=120):
    idx = pd.date_range("2026-01-01", periods=n, freq="60min")
    close = np.array(close_trend)
    df = pd.DataFrame({"Open": close, "High": close*1.01, "Low": close*0.99, "Close": close, "Volume": 1000.0}, index=idx)
    return df


def test_compute_layer2_momentum_bullish():
    # Rising trend with oscillations → MACD bullish, RSI ~60
    df = _make_60m(np.linspace(100, 110, num=120) + np.sin(np.linspace(0, 8*np.pi, 120)) * 4)
    r = compute_layer2_momentum("TEST", df)
    assert r["group"] in MOMENTUM_VALID
    assert "macd" in r["signals"] and "rsi" in r["signals"]
    assert r["signals"]["macd"] in ("bullish", "bearish", "cross")
    assert isinstance(r["signals"]["rsi"], float)
    assert 0 <= r["signals"]["rsi"] <= 100
    assert r["group"] in ("strong", "up")  # bullish trend


def test_compute_layer2_momentum_bearish():
    df = _make_60m(np.linspace(150, 80, num=120))
    r = compute_layer2_momentum("TEST", df)
    assert r["group"] in ("down", "oversold")


def test_compute_layer2_momentum_overbought():
    # Sharp rise → RSI ≥ 70
    df = _make_60m(np.linspace(100, 200, num=60), n=60)
    r = compute_layer2_momentum("TEST", df)
    assert r["group"] == "overbought"


def test_compute_layer2_momentum_oversold():
    df = _make_60m(np.linspace(200, 80, num=60), n=60)
    r = compute_layer2_momentum("TEST", df)
    assert r["group"] == "oversold"


def test_compute_layer2_momentum_enum_closed():
    df = _make_60m(np.linspace(100, 110, num=120))
    r = compute_layer2_momentum("TEST", df)
    assert r["group"] in MOMENTUM_VALID


def test_compute_layer2_momentum_short_data_returns_neutral():
    r = compute_layer2_momentum("TEST", None)
    assert r["group"] == "neutral"
    assert r["signals"]["macd"] == "cross"
    assert r["signals"]["rsi"] == 50.0
    df_short = _make_60m([100, 101], n=2)
    r2 = compute_layer2_momentum("TEST", df_short)
    assert r2["group"] == "neutral"