"""Isolated deterministic 60-minute VCP candidate finder.

This module intentionally does not import the legacy scanner or intraday evaluator.
It owns only the vcp_finder_60m contract.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
import math
import uuid
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


POLICY_VERSION = "signalix/vcp-finder-60m-v1"
REQUIRED_COLUMNS = ("ts", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class VCP60Config:
    interval: str = "60m"
    min_bars: int = 80
    pattern_bars: int = 60
    pivot_left: int = 2
    pivot_right: int = 2
    atr_bars: int = 14
    min_prominence_pct: float = 1.0
    base_depth_min_pct: float = 5.0
    base_depth_max_pct: float = 35.0
    contraction_ratio: float = 0.85
    latest_contraction_max_pct: float = 12.0
    dryup_ratio: float = 0.80
    breakout_volume_ratio: float = 1.50
    breakout_buffer_pct: float = 0.005
    breakout_atr_fraction: float = 0.10
    extension_limit_pct: float = 3.0
    failure_atr_fraction: float = 0.10
    freshness_sessions: int = 2


def _plain(value: Any):
    if value is None:
        return None
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def _empty_result(state: str, reasons: list[str], *, data=None, as_of=None, config=None):
    cfg = config or VCP60Config()
    return {
        "schema_version": "signalix.vcp_finder_60m.v1",
        "finder": "vcp_finder_60m",
        "interval": cfg.interval,
        "state": state,
        "actionable": False,
        "reason_codes": list(reasons),
        "data": data or {},
        "trend": {},
        "price": {},
        "pattern": {"pivots": [], "contractions_pct": [], "contraction_ratios": []},
        "volume": {},
        "breakout": {},
        "evidence": {},
        "reasons": list(reasons),
        "provenance": {
            "as_of": _plain(as_of),
            "finder_version": POLICY_VERSION,
            "legacy_scanner_used": False,
            "source": "intraday_price_data",
        },
    }


def _normalize(frame: pd.DataFrame):
    if frame is None:
        return pd.DataFrame(columns=REQUIRED_COLUMNS), 0, 0
    if not isinstance(frame, pd.DataFrame):
        frame = pd.DataFrame(frame)
    if frame.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS), 0, 0
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"missing OHLCV columns: {','.join(missing)}")
    df = frame.loc[:, REQUIRED_COLUMNS].copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    for col in REQUIRED_COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    duplicate_rows = int(df.duplicated(subset=["ts"], keep="last").sum())
    df = df.sort_values("ts", kind="mergesort").drop_duplicates("ts", keep="last")
    numeric_cols = list(REQUIRED_COLUMNS[1:])
    finite = df[numeric_cols].notna().all(axis=1)
    finite &= df[numeric_cols].apply(lambda col: col.map(math.isfinite)).all(axis=1)
    valid = finite
    valid &= df["low"] > 0
    valid &= df["close"] > 0
    valid &= df["volume"] >= 0
    valid &= df["high"] >= df[["open", "close", "low"]].max(axis=1)
    valid &= df["low"] <= df[["open", "close", "high"]].min(axis=1)
    invalid_rows = int((~valid).sum())
    df = df.loc[valid].reset_index(drop=True)
    return df, invalid_rows, duplicate_rows


def _atr14(close, high, low, n):
    tr = []
    for i in range(len(close)):
        prev = close[i - 1] if i else close[i]
        tr.append(max(high[i] - low[i], abs(high[i] - prev), abs(low[i] - prev)))
    if len(tr) < n:
        return None, tr
    atr = [sum(tr[:n]) / n]
    for x in tr[n:]:
        atr.append((atr[-1] * (n - 1) + x) / n)
    return atr[-1], tr


def _pivots(df: pd.DataFrame, cfg: VCP60Config):
    start = max(cfg.pivot_left, len(df) - cfg.pattern_bars)
    end = len(df) - cfg.pivot_right
    found = []
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    for i in range(start, max(start, end)):
        left = range(i - cfg.pivot_left, i)
        right = range(i + 1, i + cfg.pivot_right + 1)
        around_high = [highs[j] for j in (*left, *right)]
        around_low = [lows[j] for j in (*left, *right)]
        is_high = highs[i] >= max(around_high) and highs[i] > min(around_high)
        is_low = lows[i] <= min(around_low) and lows[i] < max(around_low)
        if is_high:
            local_low = min(lows[max(0, i - 8): min(len(lows), i + 9)])
            prominence = (highs[i] - local_low) / highs[i] * 100 if highs[i] else 0
            if prominence >= cfg.min_prominence_pct:
                found.append({"kind": "high", "idx": i, "ts": df.iloc[i]["ts"], "price": float(highs[i])})
        if is_low:
            local_high = max(highs[max(0, i - 8): min(len(highs), i + 9)])
            prominence = (local_high - lows[i]) / local_high * 100 if local_high else 0
            if prominence >= cfg.min_prominence_pct:
                found.append({"kind": "low", "idx": i, "ts": df.iloc[i]["ts"], "price": float(lows[i])})
    found.sort(key=lambda x: x["idx"])
    # Collapse adjacent same-kind pivots, retaining the more extreme one.
    alternating = []
    for pivot in found:
        if alternating and alternating[-1]["kind"] == pivot["kind"]:
            better = (pivot["price"] > alternating[-1]["price"]) if pivot["kind"] == "high" else (pivot["price"] < alternating[-1]["price"])
            if better:
                alternating[-1] = pivot
        else:
            alternating.append(pivot)
    return alternating


def _sequence(pivots):
    for i in range(len(pivots) - 4):
        seq = pivots[i:i + 5]
        if [p["kind"] for p in seq] == ["high", "low", "high", "low", "high"]:
            return seq
    return None


def _set_session_open(local_dt):
    if local_dt.weekday() >= 5:
        return False
    minutes = local_dt.hour * 60 + local_dt.minute
    return 615 <= minutes < 750 or 885 <= minutes < 990


def _session_age(start_date, end_date):
    try:
        from set_market_day_guard import SET_CLOSED_DATES
    except ImportError:
        SET_CLOSED_DATES = {}
    if start_date > end_date:
        return 0
    days = 0
    cursor = start_date
    while cursor < end_date:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5 and cursor.isoformat() not in SET_CLOSED_DATES:
            days += 1
    return days


def _closed_bar_context(latest_dt, as_of_dt):
    bkk = ZoneInfo("Asia/Bangkok")
    latest_local = latest_dt.astimezone(bkk)
    as_of_local = as_of_dt.astimezone(bkk)
    latest_may_be_open = latest_local.date() == as_of_local.date() and _set_session_open(as_of_local)
    return latest_local, as_of_local, latest_may_be_open


def find_vcp_60m(frame: pd.DataFrame, *, as_of=None, config: VCP60Config | None = None) -> dict:
    cfg = config or VCP60Config()
    try:
        df, invalid_rows, duplicate_rows = _normalize(frame)
    except ValueError as exc:
        return _empty_result("NOT_VERIFIED", ["invalid_schema", str(exc)])
    if df.empty:
        result = _empty_result("NOT_VERIFIED", ["no_data"], config=cfg)
        result["data"] = {"bar_count": 0, "valid_bar_count": 0, "invalid_rows": invalid_rows, "duplicate_rows": duplicate_rows}
        return result
    latest = df.iloc[-1]["ts"].to_pydatetime()
    observed_as_of = as_of or datetime.now(timezone.utc)
    if observed_as_of.tzinfo is None:
        observed_as_of = observed_as_of.replace(tzinfo=timezone.utc)
    latest_local, as_of_local, latest_may_be_open = _closed_bar_context(latest, observed_as_of)
    session_age = _session_age(latest_local.date(), as_of_local.date())
    freshness = "fresh" if session_age <= cfg.freshness_sessions else "stale"
    data = {
        "bar_count": int(len(frame)), "valid_bar_count": int(len(df)),
        "invalid_rows": invalid_rows, "duplicate_rows": duplicate_rows,
        "first_bar_ts": _plain(df.iloc[0]["ts"]), "last_bar_ts": _plain(df.iloc[-1]["ts"]),
        "max_gap_hours": max([((df.iloc[i]["ts"] - df.iloc[i-1]["ts"]).total_seconds() / 3600) for i in range(1, len(df))] or [0]),
        "freshness": freshness, "freshness_session_age": session_age,
        "session_timezone": "Asia/Bangkok", "latest_bar_may_be_open": latest_may_be_open,
        "in_progress_bar_excluded": latest_may_be_open,
    }
    if len(df) < cfg.min_bars:
        return {**_empty_result("NOT_VERIFIED", ["insufficient_history"], data=data, as_of=observed_as_of, config=cfg), "data": data}
    work = df.iloc[:-1].reset_index(drop=True) if latest_may_be_open else df.reset_index(drop=True)
    close = work["close"].astype(float)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema_slope = float((ema20.iloc[-1] / ema20.iloc[-11] - 1) * 100) if len(ema20) >= 11 and ema20.iloc[-11] else None
    prior_idx = max(0, len(work) - cfg.pattern_bars)
    prior_return = float((close.iloc[prior_idx] / close.iloc[max(0, prior_idx - 20)] - 1) * 100) if prior_idx > 0 and close.iloc[max(0, prior_idx - 20)] else 0.0
    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) >= 2 else None
    change_pct = ((last_close / prev_close) - 1) * 100 if prev_close else None
    atr, _ = _atr14(close.tolist(), work["high"].tolist(), work["low"].tolist(), cfg.atr_bars)
    trend_pass = last_close > float(ema20.iloc[-1]) and (ema_slope or 0) > 0 and prior_return > 0
    result_base = _empty_result("FORMING", [], data=data, as_of=observed_as_of, config=cfg)
    result_base["data"] = data
    result_base["trend"] = {"ema20": _plain(float(ema20.iloc[-1])), "ema20_slope_pct": _plain(ema_slope), "prior_trend_return_pct": _plain(prior_return), "pass": bool(trend_pass)}
    result_base["price"] = {"last_close": last_close, "previous_close": prev_close, "change_pct": _plain(change_pct), "atr14": _plain(atr)}
    if not trend_pass:
        result_base["reason_codes"] = ["prior_trend_not_confirmed"]
        result_base["reasons"] = ["Prior 60m trend is not confirmed; shrinking candles alone are not a VCP."]
    pivots = _pivots(work, cfg)
    result_base["pattern"]["pivots"] = [{"kind": p["kind"], "ts": _plain(p["ts"]), "price": p["price"]} for p in pivots]
    seq = _sequence(pivots)
    if not seq:
        result_base["state"] = "FORMING" if len(pivots) >= 3 else "NOT_VERIFIED"
        result_base["reason_codes"] = ["no_valid_base_sequence"]
        result_base["reasons"] = ["At least H-L-H-L-H confirmed structure is required."]
        return result_base
    depths = [(seq[0]["price"] - seq[1]["price"]) / seq[0]["price"] * 100, (seq[2]["price"] - seq[3]["price"]) / seq[2]["price"] * 100]
    ratios = [depths[i] / depths[i - 1] if depths[i - 1] else None for i in range(1, len(depths))]
    base_high = max(p["price"] for p in seq if p["kind"] == "high")
    base_low = min(p["price"] for p in seq if p["kind"] == "low")
    base_depth = (base_high - base_low) / base_high * 100 if base_high else None
    latest_contraction = depths[-1]
    contraction_pass = len(depths) >= 2 and all(r is not None and r <= cfg.contraction_ratio for r in ratios)
    base_pass = cfg.base_depth_min_pct <= (base_depth or 0) <= cfg.base_depth_max_pct and latest_contraction <= cfg.latest_contraction_max_pct
    failure = seq[3]["price"]
    pivot = seq[-1]["price"]
    required_close = pivot * (1 + max(cfg.breakout_buffer_pct, cfg.breakout_atr_fraction * atr / pivot if atr else 0))
    distance_pct = (last_close / pivot - 1) * 100 if pivot else None
    volume = work["volume"].astype(float).tolist()
    leg_average_volume = []
    for high_p, low_p in zip(seq[0::2], seq[1::2]):
        leg_average_volume.append(sum(volume[high_p["idx"]:low_p["idx"] + 1]) / max(1, low_p["idx"] - high_p["idx"] + 1))
    leg_volume_pass = len(leg_average_volume) >= 2 and all(
        leg_average_volume[i] <= leg_average_volume[i - 1] for i in range(1, len(leg_average_volume))
    )
    recent = sum(volume[-5:]) / 5 if len(volume) >= 5 else 0
    baseline = sum(volume[-20:-5]) / 15 if len(volume) >= 20 else 0
    dryup = recent / baseline if baseline > 0 else None
    volume_pass = dryup is not None and dryup <= cfg.dryup_ratio
    breakout_volume = volume[-1] / (sum(volume[-20:-1]) / 19) if len(volume) >= 20 and sum(volume[-20:-1]) > 0 else None
    close_pass = last_close > required_close
    volume_confirmed = breakout_volume is not None and breakout_volume >= cfg.breakout_volume_ratio
    structure_pass = bool(trend_pass and contraction_pass and base_pass and leg_volume_pass)
    if last_close < failure:
        state = "FAILED"
    elif structure_pass and close_pass and volume_confirmed:
        state = "EXTENDED" if (distance_pct or 0) > cfg.extension_limit_pct else "CONFIRMED"
    elif structure_pass and close_pass:
        state = "EXTENDED" if (distance_pct or 0) > cfg.extension_limit_pct else "NEAR_TRIGGER"
    elif structure_pass and distance_pct is not None and distance_pct >= -0.5:
        state = "NEAR_TRIGGER"
    elif structure_pass:
        state = "READY"
    elif base_pass:
        state = "FORMING"
    else:
        state = "FORMING"
    if freshness == "stale" and state not in {"FAILED", "NOT_VERIFIED"}:
        state = "STALE"
    reasons = []
    if not trend_pass: reasons.append("prior_trend_not_confirmed")
    if contraction_pass: reasons.append("descending_pullback_contractions")
    if base_pass: reasons.append("base_depth_and_latest_contraction_pass")
    if volume_pass: reasons.append("recent_volume_dryup")
    if not volume_pass: reasons.append("volume_dryup_not_confirmed")
    if leg_volume_pass: reasons.append("leg_volume_non_increasing")
    if not leg_volume_pass: reasons.append("leg_volume_not_contracted")
    if close_pass and not volume_confirmed: reasons.append("breakout_close_without_volume_confirmation")
    if state == "FAILED": reasons.append("below_structural_invalidation")
    result_base.update({
        "state": state, "actionable": state in {"READY", "CONFIRMED", "NEAR_TRIGGER"},
        "reason_codes": reasons,
        "reasons": reasons,
        "price": {"last_close": last_close, "previous_close": prev_close, "change_pct": _plain(change_pct), "atr14": _plain(atr), "pivot_high": pivot, "distance_to_pivot_pct": _plain(distance_pct), "invalidation": _plain(failure)},
        "pattern": {"pivots": [{"kind": p["kind"], "ts": _plain(p["ts"]), "price": p["price"]} for p in seq], "base_depth_pct": _plain(base_depth), "contractions_pct": [_plain(x) for x in depths], "contraction_ratios": [_plain(x) for x in ratios], "latest_contraction_pct": _plain(latest_contraction)},
        "volume": {"leg_average_volume": [_plain(x) for x in leg_average_volume], "leg_volume_non_increasing": bool(leg_volume_pass), "recent_5_avg": _plain(recent), "baseline_15_avg": _plain(baseline), "dryup_ratio": _plain(dryup), "volume_dryup": bool(volume_pass), "breakout_volume_ratio": _plain(breakout_volume)},
        "breakout": {"pivot_level": pivot, "required_close": required_close, "close_confirmed": bool(close_pass), "volume_confirmed": bool(volume_confirmed)},
        "evidence": {"prior_trend_pass": bool(trend_pass), "price_contraction_pass": bool(contraction_pass), "base_pass": bool(base_pass), "leg_volume_pass": bool(leg_volume_pass), "volume_contraction_pass": bool(volume_pass), "breakout_close_pass": bool(close_pass), "breakout_volume_pass": bool(volume_confirmed)},
    })
    return result_base


def new_run_id():
    return f"vcp60-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
