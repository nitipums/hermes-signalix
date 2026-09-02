"""Deterministic 60m trade-setup preparation for Daily Elliott candidates.

This module prepares evidence for review.  It never authorizes an order.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

import risk_stop_target


ANCHOR_POLICY = "relaxed-1bar-scaled-20260831"


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


def _empty_setup(state: str, status: str, freshness=None, reason=None,
                 reason_code=None, data_reason_code=None) -> dict:
    setup = {
        "timeframe": "60m",
        "state": state,
        "status": status,
        "trigger": None,
        "entry_zone": {"low": None, "high": None},
        "invalidation": None,
        "trade_stop": None,
        "thesis_invalidation": None,
        "risk_stop_separate": False,
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
    if reason_code:
        setup["reason_code"] = reason_code
    if data_reason_code:
        setup["data_reason_code"] = data_reason_code
    return setup


def _valid_ohlcv(df: pd.DataFrame | None) -> bool:
    required = {"Open", "High", "Low", "Close", "Volume"}
    if df is None or len(df) < 3 or not required.issubset(df.columns):
        return False
    values = df[list(required)].apply(pd.to_numeric, errors="coerce")
    if not values.apply(lambda column: column.map(lambda value: _number(value) is not None and value > 0)).all().all():
        return False
    if not ((values["High"] >= values[["Open", "Close"]].max(axis=1)) &
            (values["Low"] <= values[["Open", "Close"]].min(axis=1)) &
            (values["High"] >= values["Low"])).all():
        return False
    return True


def _intraday_anchors(df: pd.DataFrame) -> dict[str, float | str | None]:
    """Return confirmed recent pullback/advance anchors, excluding observation."""
    if not _valid_ohlcv(df) or df.attrs.get("timeframe") != "60m":
        return {}
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.hasnans:
        return {}
    if not df.index.is_monotonic_increasing or not df.index.is_unique:
        return {}
    as_of = df.attrs.get("as_of")
    if as_of is not None:
        try:
            as_of_timestamp = pd.Timestamp(as_of)
            if pd.isna(as_of_timestamp) or as_of_timestamp < df.index[-1]:
                return {}
        except (TypeError, ValueError):
            return {}
    # A bounded recent window prevents an old 90-bar extreme from becoming the
    # current setup anchor. The latest candle is the observation under test.
    # Relaxed 2026-08-31: inspect the prior 30 bars and allow 1-bar legs.
    prior = df.iloc[:-1].tail(30)
    closes = [float(value) for value in prior["Close"]]
    if len(closes) < 2:
        return {}

    legs = []
    start = 0
    direction = 0
    for index in range(1, len(closes)):
        step = 1 if closes[index] > closes[index - 1] else -1 if closes[index] < closes[index - 1] else 0
        if not step:
            if direction:
                legs.append((direction, start, index - 1))
            direction = 0
            start = index - 1
            continue
        if direction and step != direction:
            legs.append((direction, start, index - 1))
            start = index - 1
        elif not direction:
            start = index - 1
        direction = step
    legs.append((direction, start, len(closes) - 1))
    # Relaxed 2026-08-31: allow 1-bar legs to accept minimal 60m structure.
    up_legs = [leg for leg in legs if leg[0] == 1 and leg[2] - leg[1] >= 1]
    if not up_legs:
        return {}
    _, leg_start, leg_end = up_legs[-1]
    preceding = [leg for leg in legs if leg[2] <= leg_start and leg[0] == -1]
    if not preceding:
        return {}
    _, pullback_start, pullback_end = preceding[-1]
    if pullback_end - pullback_start < 1:
        return {}
    pullback_start_close = _number(closes[pullback_start])
    pullback_end_close = _number(closes[pullback_end])
    advance_start_close = _number(closes[leg_start])
    advance_end_close = _number(closes[leg_end])
    if any(value is None for value in (
        pullback_start_close, pullback_end_close, advance_start_close, advance_end_close
    )):
        return {}
    # A structural pullback and advance need price significance as well as
    # direction. One-bar legs use a scaled threshold; longer legs retain 3%.
    pullback_pct = 0.01 if pullback_end - pullback_start == 1 else 0.03
    advance_pct = 0.01 if leg_end - leg_start == 1 else 0.03
    if pullback_end_close > pullback_start_close * (1 - pullback_pct):
        return {}
    if advance_end_close < advance_start_close * (1 + advance_pct):
        return {}
    leg = prior.iloc[leg_start:leg_end + 1]
    pivot = prior.iloc[pullback_end]
    pivot_low = _number(pivot["Low"])
    swing_low = _number(leg["Low"].min())
    swing_high = _number(leg["High"].max())
    close = _number(df["Close"].iloc[-1])
    if (pivot_low is None or swing_low is None or swing_high is None or close is None or
            pivot_low <= 0 or swing_low <= 0 or swing_high <= swing_low or
            abs(swing_low - pivot_low) > max(pivot_low * 0.02, 1e-12)):
        return {}
    swing_low = pivot_low
    pullback_low = swing_low + (swing_high - swing_low) * 0.5
    if not _number(pullback_low) or pullback_low <= swing_low:
        return {}
    timestamp = df.index[-1]
    freshness = timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)
    is_minimal = (leg_end - leg_start == 1) or (pullback_end - pullback_start == 1)
    trigger_pos = leg_start + int(leg["High"].astype(float).values.argmax())
    trigger_timestamp = prior.index[trigger_pos]
    if hasattr(trigger_timestamp, "isoformat"):
        trigger_timestamp = trigger_timestamp.isoformat()
    else:
        trigger_timestamp = str(trigger_timestamp)
    trade_stop_timestamp = prior.index[pullback_end]
    if hasattr(trade_stop_timestamp, "isoformat"):
        trade_stop_timestamp = trade_stop_timestamp.isoformat()
    else:
        trade_stop_timestamp = str(trade_stop_timestamp)
    return {
        "anchor_policy": ANCHOR_POLICY,
        "trigger": swing_high,
        "invalidation": swing_low,
        "swing_low": swing_low,
        "swing_high": swing_high,
        "pullback_low": pullback_low,
        "close": close,
        "freshness": freshness,
        "is_minimal": is_minimal,
        "as_of": as_of,
        "trigger_timestamp": trigger_timestamp,
        "trade_stop_timestamp": trade_stop_timestamp,
    }


def _valid_60m_series(df: pd.DataFrame | None) -> bool:
    if not _valid_ohlcv(df) or df.attrs.get("timeframe") != "60m":
        return False
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.hasnans:
        return False
    if not df.index.is_monotonic_increasing or not df.index.is_unique:
        return False
    as_of = df.attrs.get("as_of")
    if as_of is not None:
        try:
            timestamp = pd.Timestamp(as_of)
            if pd.isna(timestamp) or timestamp < df.index[-1]:
                return False
        except (TypeError, ValueError):
            return False
    return True


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
    state = daily_wave.get("state") or daily_wave.get("primary_state") or "UNKNOWN"
    if daily_wave.get("timeframe") != "daily":
        return _empty_setup(
            state, "DATA_BLOCKED", reason="missing or mismatched Daily timeframe",
            data_reason_code="INVALID_DAILY_OHLCV",
        )
    if intraday_df is None or len(intraday_df) == 0:
        return _empty_setup(
            state, "DATA_BLOCKED", reason="missing 60m OHLCV",
            data_reason_code="NO_60M_DATA",
        )
    if not _valid_60m_series(intraday_df):
        return _empty_setup(
            state, "DATA_BLOCKED", reason="invalid 60m OHLCV",
            data_reason_code="INVALID_60M_OHLCV",
        )
    anchors = _intraday_anchors(intraday_df) if intraday_df is not None else {}
    if not anchors:
        return _empty_setup(
            state, "FORMING", intraday_df.index[-1].isoformat(),
            reason="insufficient recent 60m structural anchors",
            reason_code="NO_SETUP_DETECTED",
        )

    setup = _empty_setup(state, "FORMING", anchors["freshness"])
    setup["snapshot_id"] = "60m:" + str(anchors["freshness"])
    setup["snapshot_identity"] = setup["snapshot_id"]
    setup["trigger_timestamp"] = anchors["trigger_timestamp"]
    setup["trade_stop_timestamp"] = anchors["trade_stop_timestamp"]
    thesis_invalidation = _number(daily_wave.get("thesis_invalidation"))
    if thesis_invalidation is None:
        thesis_invalidation = _number((daily_wave.get("evidence") or {}).get("wave1_low"))
    trigger = anchors["trigger"]
    invalidation = anchors["invalidation"]
    current = anchors["close"]
    risk = trigger - invalidation
    setup["trigger"] = round(trigger, 4)
    setup["entry_zone"] = {
        "low": round(trigger - 0.25 * risk, 4),
        "high": round(trigger + 0.5 * risk, 4),
    }
    setup["invalidation"] = round(invalidation, 4)
    setup["trade_stop"] = round(invalidation, 4)
    setup["thesis_invalidation"] = thesis_invalidation
    setup["risk_stop_separate"] = thesis_invalidation is not None

    fib = risk_helper.compute_fib_targets(
        anchors["swing_low"], anchors["swing_high"], anchors["pullback_low"]
    )
    targets = [(method, fib.get(method)) for method in ("fib_1272", "fib_1618")]
    targets = [(method, round(_number(target), 4)) for method, target in targets
               if _number(target) is not None and _number(target) > trigger]
    if (fib.get("status") not in {None, "OK"} or not targets or
            not _number(risk) or risk <= 0):
        setup["status"] = "INVALIDATED"
        setup["risk_status"] = "INVALID"
        setup["reason_code"] = "RISK_INVALID"
        setup["reason"] = "invalid Fib or risk anchors"
        return _json_value(setup)
    setup["targets"] = [
        {"name": f"target_{index}", "price": price, "method": method}
        for index, (method, price) in enumerate(targets[:2], start=1)
    ]
    # Numeric aliases preserve the pre-marker setup payload for older callers;
    # the ordered objects above are the canonical chart/API representation.
    setup["target_1"] = targets[0][1]
    setup["target_2"] = targets[1][1] if len(targets) > 1 else None
    setup["rr"] = {
        "to_target_1": _ratio(targets[0][1], trigger, invalidation),
        "to_target_2": _ratio(targets[1][1], trigger, invalidation) if len(targets) > 1 else None,
    }
    setup["risk"] = round(trigger - invalidation, 4)
    setup["reward"] = round(targets[0][1] - trigger, 4)
    setup["rr_bands"] = {
        "minimum_review": 2,
        "lower_priority": [2, 4],
        "preferred": [4, 8],
        "exceptional": 8,
    }

    observation_low = _number(intraday_df["Low"].iloc[-1])
    if observation_low is None or observation_low <= invalidation:
        setup["status"] = "INVALIDATED"
    elif current > setup["entry_zone"]["high"]:
        setup["status"] = "EXTENDED"
        setup["reason"] = "do_not_chase"
    elif setup["rr"]["to_target_1"] is None or setup["rr"]["to_target_1"] < 2:
        setup["status"] = "EXTENDED"
        setup["reason"] = "do_not_chase_below_2_to_1"
    elif anchors.get("as_of") is not None:
        age_days = (pd.Timestamp(anchors["as_of"]).date() - intraday_df.index[-1].date()).days
        if age_days > 3:
            setup["status"] = "EXPIRED"
            setup["reason"] = "stale 60m setup"
    if setup["status"] == "FORMING":
        latest_high = _number(intraday_df["High"].iloc[-1])
        if latest_high is None:
            setup["status"] = "DATA_BLOCKED"
            setup["reason"] = "invalid latest 60m observation"
        elif state in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"} and current >= trigger:
            setup["status"] = "TRIGGERED"
        elif state in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"} and latest_high > trigger:
            setup["status"] = "TESTED_TRIGGER"
        elif state in {"EARLY_WAVE_3", "WAVE_3_CONTINUATION"}:
            setup["status"] = "PRE_TRIGGER"
    # Relaxed 2026-08-31: minimal 60m structure (1-bar legs, prior 30-bar window) can still
    # return a valid pre-trigger plan. Map minimal FORMING anchors to PRE_TRIGGER
    # so the UI can show trigger/invalidation even with sparse intraday history.
    if anchors.get("is_minimal") and setup["status"] == "FORMING":
        setup["status"] = "PRE_TRIGGER"
    if observation_low is not None and observation_low <= invalidation:
        setup["status"] = "INVALIDATED"
    return _json_value(setup)
