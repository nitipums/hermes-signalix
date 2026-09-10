"""Deterministic, no-lookahead technical indicators for aligned OHLCV candles.

Policy ``technical-indicators-v1`` uses SMA over 5/10/20/60/120/240 candles
and rolling High/Low over 5/10/20/60/120/260 candles (260 trading candles is
the canonical 52-week window),
MACD(12,26,9) with each EMA seeded by the first period's SMA, Wilder RSI(14),
and Wilder ATR(14).  True range is ``max(high-low, abs(high-prev_close),
abs(low-prev_close))`` (the first candle uses ``high-low``).  Wilder RSI and
ATR are seeded with the arithmetic mean of their first 14 observations, then
use ``(previous * 13 + current) / 14``.  Values use only candles at or before
their aligned index and public numeric output is rounded to four decimals.
"""

from __future__ import annotations

import math
from typing import Any


POLICY_VERSION = "technical-indicators-v1"
MA_PERIODS = (5, 10, 20, 60, 120, 240)
HIGH_LOW_PERIODS = (5, 10, 20, 60, 120, 260)
ROUND_DECIMALS = 4


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rounded(values: list[float | None]) -> list[float | None]:
    return [round(value, ROUND_DECIMALS) if value is not None else None for value in values]


def _sma(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    total = sum(values[:period])
    result[period - 1] = total / period
    for index in range(period, len(values)):
        total += values[index] - values[index - period]
        result[index] = total / period
    return result


def _rolling_extreme(values: list[float], period: int, *, highest: bool) -> list[float | None]:
    """Return a trailing-window extreme aligned to its window's final candle."""
    result: list[float | None] = [None] * len(values)
    extreme = max if highest else min
    for index in range(period - 1, len(values)):
        result[index] = extreme(values[index - period + 1:index + 1])
    return result


def _ema(values: list[float], period: int) -> list[float | None]:
    """SMA-seeded EMA with unrounded internal state and aligned null padding."""
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    alpha = 2.0 / (period + 1)
    previous = sum(values[:period]) / period
    result[period - 1] = previous
    for index in range(period, len(values)):
        previous = previous + alpha * (values[index] - previous)
        result[index] = previous
    return result


def _macd(values: list[float]) -> dict[str, list[float | None]]:
    ema12, ema26 = _ema(values, 12), _ema(values, 26)
    line: list[float | None] = [None] * len(values)
    for index in range(25, len(values)):
        if ema12[index] is not None and ema26[index] is not None:
            line[index] = ema12[index] - ema26[index]

    signal: list[float | None] = [None] * len(values)
    histogram: list[float | None] = [None] * len(values)
    available_line = [value for value in line[25:] if value is not None]
    signal_values = _ema(available_line, 9)
    for offset, value in enumerate(signal_values):
        if value is not None:
            index = 25 + offset
            signal[index] = value
            histogram[index] = line[index] - value  # type: ignore[operator]
    return {"line": _rounded(line), "signal": _rounded(signal),
            "histogram": _rounded(histogram)}


def _rsi(values: list[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period + 1:
        return result
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    average_gain = sum(max(change, 0.0) for change in changes[:period]) / period
    average_loss = sum(max(-change, 0.0) for change in changes[:period]) / period

    def value() -> float:
        if average_gain == 0.0 and average_loss == 0.0:
            return 50.0
        if average_loss == 0.0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + average_gain / average_loss)

    result[period] = value()
    for index in range(period + 1, len(values)):
        change = changes[index - 1]
        average_gain = (average_gain * (period - 1) + max(change, 0.0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0.0)) / period
        result[index] = value()
    return _rounded(result)


def _atr(highs: list[float], lows: list[float], closes: list[float],
         period: int = 14) -> list[float | None]:
    result: list[float | None] = [None] * len(closes)
    if not closes:
        return result
    true_ranges = [highs[0] - lows[0]]
    for index in range(1, len(closes)):
        true_ranges.append(max(highs[index] - lows[index],
                               abs(highs[index] - closes[index - 1]),
                               abs(lows[index] - closes[index - 1])))
    if len(true_ranges) < period:
        return result
    previous = sum(true_ranges[:period]) / period
    result[period - 1] = previous
    for index in range(period, len(true_ranges)):
        previous = (previous * (period - 1) + true_ranges[index]) / period
        result[index] = previous
    return _rounded(result)


def _availability(count: int, required: int) -> dict[str, Any]:
    return {"status": "AVAILABLE" if count >= required else "NOT_VERIFIED",
            "required_candles": required, "available_candles": count}


def build_technical_indicators(candles: list[dict[str, Any]], timeframe: str) -> dict[str, Any]:
    """Return one JSON-safe indicator payload aligned 1:1 to oldest-first candles.

    A non-finite/missing High, Low, or Close makes calculated series fail closed;
    raw finite High/Low context remains exposed without inventing replacements.
    """
    count = len(candles)
    closes = [_finite(candle.get("close")) for candle in candles]
    highs = [_finite(candle.get("high")) for candle in candles]
    lows = [_finite(candle.get("low")) for candle in candles]
    input_valid = count > 0 and all(value is not None for value in closes + highs + lows)
    nulls = [None] * count
    if input_valid:
        close_values = [value for value in closes if value is not None]
        high_values = [value for value in highs if value is not None]
        low_values = [value for value in lows if value is not None]
        ma = {str(period): _rounded(_sma(close_values, period)) for period in MA_PERIODS}
        rolling_high = {
            str(period): _rounded(_rolling_extreme(high_values, period, highest=True))
            for period in HIGH_LOW_PERIODS
        }
        rolling_low = {
            str(period): _rounded(_rolling_extreme(low_values, period, highest=False))
            for period in HIGH_LOW_PERIODS
        }
        macd = _macd(close_values)
        rsi = _rsi(close_values)
        atr = _atr(high_values, low_values, close_values)
    else:
        ma = {str(period): list(nulls) for period in MA_PERIODS}
        rolling_high = {str(period): list(nulls) for period in HIGH_LOW_PERIODS}
        rolling_low = {str(period): list(nulls) for period in HIGH_LOW_PERIODS}
        macd = {key: list(nulls) for key in ("line", "signal", "histogram")}
        rsi, atr = list(nulls), list(nulls)

    def last(values: list[float | None]) -> float | None:
        return values[-1] if values else None

    availability = {"input": {"status": "AVAILABLE" if input_valid else "NOT_VERIFIED",
                               "required_fields": ["high", "low", "close"]}}
    for period in MA_PERIODS:
        availability[f"ma_{period}"] = _availability(count if input_valid else 0, period)
    for period in HIGH_LOW_PERIODS:
        availability[f"rolling_high_{period}"] = _availability(
            count if input_valid else 0, period)
        availability[f"rolling_low_{period}"] = _availability(
            count if input_valid else 0, period)
    availability["macd_line"] = _availability(count if input_valid else 0, 26)
    availability["macd_signal"] = _availability(count if input_valid else 0, 34)
    availability["rsi"] = _availability(count if input_valid else 0, 15)
    availability["atr"] = _availability(count if input_valid else 0, 14)

    return {
        "policy_version": POLICY_VERSION,
        "timeframe": str(timeframe).upper(),
        "alignment": "candle_index",
        "series": {"ma": ma, "rolling_high": rolling_high,
                   "rolling_low": rolling_low, "macd": macd, "rsi": rsi, "atr": atr,
                   "high": highs, "low": lows},
        "latest": {
            "high": last(highs), "low": last(lows), "close": last(closes),
            "ma": {period: last(values) for period, values in ma.items()},
            "rolling_high_low": {
                period: {"high": last(rolling_high[period]),
                         "low": last(rolling_low[period])}
                for period in (str(value) for value in HIGH_LOW_PERIODS)
            },
            "macd": {key: last(values) for key, values in macd.items()},
            "rsi": last(rsi), "atr": last(atr),
        },
        "availability": availability,
        "provenance": {
            "input": "ordered OHLCV candles through response as_of",
            "no_lookahead": True,
            "rounding_decimal_places": ROUND_DECIMALS,
            "formulas": {
                "ma": "SMA(5,10,20,60,120,240)",
                "rolling_high_low": "trailing max(High)/min(Low) over 5,10,20,60,120,260 candles; 260 trading candles = 52 weeks",
                "macd": "EMA(12)-EMA(26), signal EMA(9), SMA-seeded",
                "rsi": "Wilder RSI(14), first value after 14 close changes",
                "atr": "Wilder ATR(14), TR=max(H-L,abs(H-prevC),abs(L-prevC))",
            },
        },
    }
