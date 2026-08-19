import pandas as pd
import numpy as np
from screening import compute_layer2_momentum, compute_layer3_qualifier

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


# --- compute_layer3_qualifier tests ---

def test_compute_layer3_qualifier_q3():
    # All 3 flags true
    df_daily = pd.DataFrame({"Close": [100]*50, "Volume": [1_000_000]*50})
    df_60m = pd.DataFrame({"Close": [100]*100, "Volume": [1000]*100})
    snap = {"avgDailyValue20": 50_000_000, "high52": 95, "athHigh": 98, "close": 105, "volume": 12_000_000}
    r = compute_layer3_qualifier("TEST", df_daily, df_60m, snap)
    assert r["score"] == 3
    assert r["flags"] == {"vol": True, "wk52": True, "ath": True}

def test_compute_layer3_qualifier_q2():
    df_daily = pd.DataFrame({"Close": [100]*50, "Volume": [1_000_000]*50})
    df_60m = pd.DataFrame({"Close": [100]*100, "Volume": [1000]*100})
    snap = {"avgDailyValue20": 50_000_000, "high52": 95, "athHigh": 110, "close": 105, "volume": 12_000_000}
    r = compute_layer3_qualifier("TEST", df_daily, df_60m, snap)
    assert r["score"] == 2
    assert r["flags"]["vol"] and r["flags"]["wk52"] and not r["flags"]["ath"]

def test_compute_layer3_qualifier_q1():
    df_daily = pd.DataFrame({"Close": [100]*50, "Volume": [1_000_000]*50})
    df_60m = pd.DataFrame({"Close": [100]*100, "Volume": [1000]*100})
    snap = {"avgDailyValue20": 50_000_000, "high52": 110, "athHigh": 110, "close": 105, "volume": 5_000_000}
    r = compute_layer3_qualifier("TEST", df_daily, df_60m, snap)
    assert r["score"] == 1
    assert sum(r["flags"].values()) == 1

def test_compute_layer3_qualifier_q0():
    df_daily = pd.DataFrame({"Close": [100]*50, "Volume": [1_000_000]*50})
    df_60m = pd.DataFrame({"Close": [100]*100, "Volume": [1000]*100})
    snap = {"avgDailyValue20": 50_000_000, "high52": 110, "athHigh": 110, "close": 90, "volume": 1_000_000}
    r = compute_layer3_qualifier("TEST", df_daily, df_60m, snap)
    assert r["score"] == 0
    assert all(not v for v in r["flags"].values())

def test_compute_layer3_qualifier_missing_data():
    r = compute_layer3_qualifier("TEST", None, None, {})
    assert r["score"] == 0
    assert r["flags"] == {"vol": False, "wk52": False, "ath": False}