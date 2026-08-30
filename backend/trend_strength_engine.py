"""Pure Daily trend and strength evidence for setup candidates."""

from __future__ import annotations

import math

import pandas as pd

from signal_core import _close_series


NEAR_52W_HIGH_PCT = 5.0
_MIN_TREND_ROWS = 20


def _number(value):
    """Return a JSON-safe Python number, or ``None`` for missing values."""
    if value is None or pd.isna(value):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _change_pct(close: pd.Series, lookback: int):
    if len(close) <= lookback:
        return None
    start = _number(close.iloc[-lookback - 1])
    end = _number(close.iloc[-1])
    if start in (None, 0) or end is None:
        return None
    return round((end / start - 1.0) * 100.0, 2)


def compute_trend_strength(
    daily_df: pd.DataFrame,
    relative_strength: float | None = None,
    prior_ath: float | None = None,
) -> dict:
    """Return conservative Daily trend/strength evidence.

    The function deliberately leaves unavailable calculations as ``None``.
    ``prior_ath`` is an optional authoritative all-time-high reference; when it
    is absent, the observed Daily close history is used as a bounded fallback.
    """
    empty = {
        "state": "UNKNOWN",
        "rise_20d_pct": None,
        "rise_60d_pct": None,
        "relative_strength": _number(relative_strength),
        "near_52w_high": False,
        "is_52w_high_breakout": False,
        "is_ath_breakout": False,
    }
    if daily_df is None or len(daily_df) == 0 or "Close" not in daily_df:
        return empty

    close = pd.to_numeric(_close_series(daily_df), errors="coerce").dropna()
    if close.empty:
        return empty

    rise_20 = _change_pct(close, 20)
    rise_60 = _change_pct(close, 60)
    latest = _number(close.iloc[-1])
    result = {**empty, "rise_20d_pct": rise_20, "rise_60d_pct": rise_60}

    # Use the prior 252 closes so a new close can be identified as a breakout.
    prior_52w = close.iloc[-253:-1] if len(close) >= 253 else close.iloc[:-1]
    high_52w = _number(prior_52w.max()) if not prior_52w.empty else None
    result["near_52w_high"] = bool(
        latest is not None and high_52w is not None
        and latest >= high_52w * (1.0 - NEAR_52W_HIGH_PCT / 100.0)
    )
    result["is_52w_high_breakout"] = bool(
        latest is not None and high_52w is not None and latest > high_52w
    )

    ath_reference = _number(prior_ath)
    if ath_reference is None:
        prior_all = close.iloc[:-1]
        ath_reference = _number(prior_all.max()) if not prior_all.empty else None
    result["is_ath_breakout"] = bool(
        latest is not None and ath_reference is not None and latest > ath_reference
    )

    if len(close) < _MIN_TREND_ROWS or rise_20 is None:
        return result
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else None
    above_ma20 = latest is not None and latest >= float(ma20)
    above_ma60 = ma60 is not None and latest >= float(ma60)
    if rise_20 > 0 and (rise_60 is None or rise_60 > 0) and above_ma20 and (rise_60 is None or above_ma60):
        result["state"] = "uptrend" if rise_60 is not None else "emerging_uptrend"
    elif rise_20 < 0 and (rise_60 is None or rise_60 < 0) and not above_ma20:
        result["state"] = "downtrend"
    elif rise_20 == 0 and (rise_60 in (None, 0)):
        result["state"] = "flat"
    else:
        result["state"] = "emerging_uptrend" if rise_20 > 0 else "UNKNOWN"
    return result
