import pandas as pd

from screening import scan_exclusion_reason


def _bars(close=10.0, volume=2_000_000.0, previous_close=None):
    idx = pd.date_range("2025-01-01", periods=220, freq="B")
    closes = [close] * 220
    if previous_close is not None:
        closes[-2] = previous_close
    return pd.DataFrame({
        "Open": closes,
        "High": [v + 0.1 for v in closes],
        "Low": [v - 0.1 for v in closes],
        "Close": closes,
        "Volume": [volume] * 220,
    }, index=idx)


def test_low_today_trade_value_is_excluded_before_technical_scan():
    df = _bars(close=10.0, volume=1_000_000.0)  # THB 10m, below THB 15m

    assert scan_exclusion_reason(df) == "low_today_trade_value"


def test_price_below_sixty_satang_is_excluded_before_technical_scan():
    df = _bars(close=0.59, volume=100_000_000.0)  # THB 59m, so price is the reason

    assert scan_exclusion_reason(df) == "price_below_minimum"


def test_clear_downtrend_with_negative_day_remains_in_scan_for_review():
    idx = pd.date_range("2025-01-01", periods=220, freq="B")
    closes = [100 - i * (90 / 219) for i in range(220)]
    df = pd.DataFrame({
        "Open": closes,
        "High": [v + 0.1 for v in closes],
        "Low": [v - 0.1 for v in closes],
        "Close": closes,
        "Volume": [2_000_000.0] * 220,
    }, index=idx)

    assert scan_exclusion_reason(df) is None
