"""Deterministic 60m trade-setup preparation for Daily Elliott candidates.

This module prepares evidence for review.  It never authorizes an order.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

import risk_stop_target


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _json_value(value: Any):
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    numeric = _number(value)
    return numeric if numeric is not None else str(value)


def _empty_setup(state: str, status: str, freshness=None, reason=None) -> dict:
    setup = {
        "timeframe": "60m",
        "state": state,
        "status": status,
        "trigger": None,
        "entry_zone": {"low": None, "high": None},
        "invalidation": None,
        "targets": [],
        "rr": {"to_target_1": None, "to_target_2": None},
        "provenance": {
            "timeframe": "60m",
            "source": "intraday_ohlcv",
            "as_of": freshness,
        },
    }
    if reason:
        setup["reason"] = reason
    return setup


def _intraday_anchors(df: pd.DataFrame) -> dict[str, float | str | None]:
    """Return prior-structure anchors, excluding the observation being tested."""
    if df is None or len(df) < 2 or not {"High", "Low", "Close"}.issubset(df.columns):
        return {}
    recent = df.tail(90)
    prior = recent.iloc[:-1]
    if prior.empty:
        return {}
    high = pd.to_numeric(prior["High"], errors="coerce").dropna()
    low = pd.to_numeric(prior["Low"], errors="coerce").dropna()
    close = _number(df["Close"].iloc[-1])
    if high.empty or low.empty or close is None:
        return {}
    swing_high = _number(high.max())
    swing_low = _number(low.min())
    if swing_high is None or swing_low is None or swing_high <= swing_low:
        return {}
    pullback_low = swing_low + (swing_high - swing_low) * 0.5
    timestamp = df.index[-1]
    freshness = timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)
    return {
        "trigger": swing_high,
        "invalidation": swing_low,
        "swing_low": swing_low,
        "swing_high": swing_high,
        "pullback_low": pullback_low,
        "close": close,
        "freshness": freshness,
    }


def _ratio(target: float | None, trigger: float | None, invalidation: float | None):
    risk = None if trigger is None or invalidation is None else trigger - invalidation
    reward = None if target is None or trigger is None else target - trigger
    if risk is None or reward is None or risk <= 0:
        return None
    return round(reward / risk, 4)


def build_trade_setup(
    daily_wave: dict,
    intraday_df: pd.DataFrame | None,
    *,
    risk_helper=risk_stop_target,
) -> dict:
    """Prepare, but never authorize, a 60m trade setup."""
    daily_wave = daily_wave or {}
    state = daily_wave.get("state") or "UNKNOWN"
    anchors = _intraday_anchors(intraday_df) if intraday_df is not None else {}
    if not anchors:
        return _empty_setup(state, "DATA_BLOCKED", reason="missing or invalid 60m OHLCV")

    setup = _empty_setup(state, "FORMING", anchors["freshness"])
    trigger = anchors["trigger"]
    invalidation = anchors["invalidation"]
    current = anchors["close"]
    setup["trigger"] = round(trigger, 4)
    setup["entry_zone"] = {"low": round(trigger * 0.99, 4), "high": round(trigger, 4)}
    setup["invalidation"] = round(invalidation, 4)

    fib = risk_helper.compute_fib_targets(
        anchors["swing_low"], anchors["swing_high"], anchors["pullback_low"]
    )
    targets = [fib.get("fib_1272"), fib.get("fib_1618")]
    targets = [target for target in targets if _number(target) is not None]
    if not targets or trigger <= invalidation:
        setup["status"] = "DATA_BLOCKED"
        setup["reason"] = "invalid Fib or risk anchors"
        return _json_value(setup)
    setup["targets"] = targets
    setup["rr"] = {
        "to_target_1": _ratio(targets[0], trigger, invalidation),
        "to_target_2": _ratio(targets[1], trigger, invalidation) if len(targets) > 1 else None,
    }
    setup["risk"] = round(trigger - invalidation, 4)
    setup["reward"] = round(targets[0] - trigger, 4)
    setup["rr_bands"] = {
        "minimum_interesting": 3,
        "preferred": [4, 5],
        "exceptional": [8, 10],
    }

    if current < invalidation:
        setup["status"] = "INVALIDATED"
    elif current > trigger * 1.03:
        setup["status"] = "EXTENDED"
    elif state in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"} and current >= trigger:
        setup["status"] = "TRIGGERED"
    elif state in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"}:
        setup["status"] = "READY"
    else:
        setup["status"] = "FORMING"
    return _json_value(setup)
