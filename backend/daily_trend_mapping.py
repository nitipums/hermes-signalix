"""Pure, deterministic Daily trend mapping (issue #7).

This module is deliberately not wired into the serving path.  It consumes a
canonical Daily technical snapshot (normally the ``latest`` projection from
``technical_indicators``) and optionally the preceding mapping result.  It
does not calculate indicators, consult other timeframes, or persist state.

The thresholds are v0.1 hypotheses.  They are configuration, not production
claims, and every result records the policy version and input provenance.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


POLICY_VERSION = "daily-trend-mapping-v0.1"
MACHINE_LANES = ("S1_1", "S1_2", "S2_1", "S2_2", "S3_3", "S4_1", "S4_2")
BROAD_STATES = {
    "S1_1": "BASING", "S1_2": "BASING",
    "S2_1": "EMERGING_UPTREND", "S2_2": "EMERGING_UPTREND",
    "S3_3": "DISTRIBUTING",
    "S4_1": "DOWNTREND", "S4_2": "DOWNTREND",
}
NORMAL_GRAPH = {
    "S1_1": "S1_2", "S1_2": "S2_1", "S2_1": "S2_2",
    "S2_2": "S3_3", "S3_3": "S4_1", "S4_1": "S4_2", "S4_2": None,
}
DEFAULT_THRESHOLDS = {
    "ma_slope_pct": 0.0,
    "bullish_rsi": 50.0,
    "bearish_rsi": 50.0,
    "volume_ratio": 1.0,
    "near_high_pct": 0.05,
    "upper_wick_ratio": 0.40,
    "down_volume_ratio": 1.0,
    "minimum_history": 20,
}


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clean(value: Any) -> Any:
    """Recursively make output JSON-safe without changing string semantics."""
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _latest(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    latest = snapshot.get("latest")
    return latest if isinstance(latest, Mapping) else snapshot


def _value(latest: Mapping[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value: Any = latest
        for key in path:
            if not isinstance(value, Mapping) or key not in value:
                value = None
                break
            value = value[key]
        if value is not None:
            return value
    return None


def _series_count(snapshot: Mapping[str, Any]) -> int:
    series = snapshot.get("series")
    if not isinstance(series, Mapping):
        return 0
    counts = []
    for key in ("close", "high", "low"):
        values = series.get(key)
        if isinstance(values, (list, tuple)):
            counts.append(len(values))
    return max(counts, default=0)


def _series_last(snapshot: Mapping[str, Any], *path: str) -> Any:
    value: Any = snapshot.get("series")
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value[-1] if isinstance(value, (list, tuple)) and value else None


def _series_previous(snapshot: Mapping[str, Any], *path: str) -> Any:
    value: Any = snapshot.get("series")
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value[-2] if isinstance(value, (list, tuple)) and len(value) >= 2 else None


def _series_window_max(snapshot: Mapping[str, Any], path: tuple[str, ...], window: int) -> float | None:
    value: Any = snapshot.get("series")
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    if not isinstance(value, (list, tuple)) or not value:
        return None
    numbers = [_finite(item) for item in value[-window:]]
    numbers = [item for item in numbers if item is not None]
    return max(numbers) if numbers else None


def _slope(series: Any, period: int = 5) -> float | None:
    if not isinstance(series, (list, tuple)) or len(series) <= period:
        return None
    current, prior = _finite(series[-1]), _finite(series[-period - 1])
    if current is None or prior in (None, 0):
        return None
    return (current / prior - 1.0) * 100.0


def _evidence(snapshot: Mapping[str, Any], latest: Mapping[str, Any], thresholds: Mapping[str, float]):
    close = _finite(_value(latest, ("close",)) if _value(latest, ("close",)) is not None
                    else _series_last(snapshot, "close"))
    low = _finite(_value(latest, ("low",)) if _value(latest, ("low",)) is not None
                  else _series_last(snapshot, "low"))
    high = _finite(_value(latest, ("high",)) if _value(latest, ("high",)) is not None
                   else _series_last(snapshot, "high"))
    open_price = _finite(_value(latest, ("open",)) if _value(latest, ("open",)) is not None
                         else _series_last(snapshot, "open"))
    ma = _value(latest, ("ma",), ("moving_averages",))
    if ma is None:
        ma = {period: _series_last(snapshot, "ma", period) for period in ("5", "10", "20", "60", "120", "240")}
    ma = ma if isinstance(ma, Mapping) else {}
    values = {period: _finite(ma.get(period)) for period in ("5", "10", "20", "60", "120", "240")}
    rsi_value = _value(latest, ("rsi",), ("rsi14",))
    rsi = _finite(rsi_value if rsi_value is not None else _series_last(snapshot, "rsi"))
    macd_value = _value(latest, ("macd", "histogram"), ("macd_histogram",))
    macd_hist = _finite(macd_value if macd_value is not None else _series_last(snapshot, "macd", "histogram"))
    volume = _value(latest, ("window_summary", "20", "volume_average"), ("volume_average",))
    current_volume = _finite(_value(latest, ("volume",), ("volume_total",)))
    average_volume = _finite(volume)
    volume_ratio = current_volume / average_volume if current_volume is not None and average_volume not in (None, 0) else None
    slope_values = {}
    series = snapshot.get("series") if isinstance(snapshot.get("series"), Mapping) else {}
    for period in ("20", "60", "120", "240"):
        slope_values[period] = _slope((series.get("ma") or {}).get(period) if isinstance(series.get("ma"), Mapping) else None)
    support = _finite(_value(latest, ("explicit_support",), ("support_reference",)))
    previous_close = _finite(_series_previous(snapshot, "close"))
    window_high = _series_window_max(snapshot, ("high",), 20)
    candle_range = high - low if high is not None and low is not None else None
    upper_wick_ratio = ((high - max(item for item in (open_price, close) if item is not None)) / candle_range
                        if candle_range and candle_range > 0 and (open_price is not None or close is not None)
                        else None)
    near_high = bool(high is not None and window_high is not None and
                     high >= window_high * (1.0 - float(thresholds["near_high_pct"])))
    close_below_support = bool(close is not None and support is not None and close < support)
    previous_close_below_support = bool(previous_close is not None and support is not None and previous_close < support)
    available = _series_count(snapshot)
    missing = []
    for name, value in (("close", close), ("low", low), ("ma_20", values["20"]), ("ma_60", values["60"]), ("rsi", rsi)):
        if value is None:
            missing.append(name)
    return {
        "close": close, "low": low, "ma": values, "rsi": rsi,
        "macd_histogram": macd_hist, "volume_ratio": volume_ratio,
        "slopes": slope_values, "support": support, "available_bars": available,
        "high": high, "previous_close": previous_close, "near_high": near_high,
        "upper_wick_ratio": upper_wick_ratio, "close_below_support": close_below_support,
        "previous_close_below_support": previous_close_below_support,
        "missing": missing, "thresholds": thresholds,
    }


def _base_lane(e: Mapping[str, Any]) -> str:
    close, ma = e["close"], e["ma"]
    if close is None or ma["20"] is None or ma["60"] is None:
        return "S1_1"
    slope = e["slopes"]["20"]
    bullish = close > ma["20"] > ma["60"] and (slope is None or slope >= e["thresholds"]["ma_slope_pct"])
    bearish = close < ma["20"] < ma["60"] and (slope is None or slope <= e["thresholds"]["ma_slope_pct"])
    rsi = e["rsi"]
    momentum_up = (rsi is not None and rsi >= e["thresholds"]["bullish_rsi"])
    momentum_down = (rsi is not None and rsi < e["thresholds"]["bearish_rsi"])
    # A break is a price/support event.  Bearish indicators alone cannot
    # manufacture either downside lane.
    if e["close_below_support"] and e["previous_close_below_support"] and bearish and momentum_down:
        return "S4_2"
    if e["close_below_support"]:
        return "S4_1"
    distribution = (
        (e["near_high"] and (bearish or e["slopes"]["20"] is not None and
                              e["slopes"]["20"] <= e["thresholds"]["ma_slope_pct"]))
        or (e["upper_wick_ratio"] is not None and
            e["upper_wick_ratio"] >= e["thresholds"]["upper_wick_ratio"] and
            e["volume_ratio"] is not None and
            e["volume_ratio"] >= e["thresholds"]["down_volume_ratio"] and
            e["previous_close"] is not None and e["close"] is not None and
            e["close"] < e["previous_close"])
    )
    if distribution:
        return "S3_3"
    if bullish and momentum_up:
        return "S2_2"
    if bullish:
        return "S2_1"
    return "S1_2" if close >= ma["20"] else "S1_1"


def classify_daily_trend(
    snapshot: Mapping[str, Any] | None,
    previous: Mapping[str, Any] | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Map one Daily snapshot to exactly one machine lane.

    ``snapshot`` may be the full technical-indicator payload or its canonical
    ``latest`` object.  Historical series are inspected at their full supplied
    length; no 260-bar truncation is performed.
    """
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    latest = _latest(snapshot)
    config = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    evidence = _evidence(snapshot, latest, config)
    previous_lane = previous.get("machine_lane") if isinstance(previous, Mapping) else None
    previous_lane = previous_lane if previous_lane in MACHINE_LANES else None
    data_status = "AVAILABLE"
    if str(_value(snapshot, ("timeframe",))).upper() not in ("", "1D", "DAILY", "D"):
        data_status = "DATA_BLOCKED"
        evidence["missing"].append("daily_timeframe")
    if evidence["available_bars"] < int(config["minimum_history"]):
        data_status = "DATA_BLOCKED"
        evidence["missing"].append("minimum_history")
    if previous_lane == "S4_1" and evidence["support"] is None:
        evidence["missing"].append("explicit_support")
    if evidence["missing"]:
        data_status = "DATA_BLOCKED"

    candidate = _base_lane(evidence)
    transition = {"from": previous_lane, "to": candidate, "type": "INITIAL" if previous_lane is None else "NORMAL"}
    break_meta = None
    wick_breach = evidence["low"] is not None and evidence["support"] is not None and evidence["low"] < evidence["support"]
    close_break = evidence["close_below_support"]
    if previous_lane == "S3_3" and (wick_breach or close_break):
        candidate = "S4_1"
        break_meta = {
            "break_type": "WICK_BREACH" if wick_breach else "CLOSE_BELOW_SUPPORT",
            "support_reference": evidence["support"],
            "close_below_support": close_break,
        }
    elif wick_breach and previous_lane is None:
        candidate = "S4_1"
        break_meta = {"break_type": "WICK_BREACH", "support_reference": evidence["support"],
                      "close_below_support": evidence["close_below_support"]}
    elif wick_breach and previous_lane != "S4_1":
        candidate = "S4_1"
        break_meta = {"break_type": "WICK_BREACH", "support_reference": evidence["support"],
                      "close_below_support": evidence["close_below_support"]}
    elif previous_lane == "S4_1":
        if candidate != "S4_2" and wick_breach:
            candidate = "S4_1"
            break_meta = {"break_type": "WICK_BREACH", "support_reference": evidence["support"],
                          "close_below_support": evidence["close_below_support"]}
        elif evidence["close"] is not None and evidence["ma"]["20"] is not None and evidence["close"] > evidence["ma"]["20"]:
            candidate = "S3_3"
            transition["type"] = "RECOVERY"
    elif previous_lane is not None and candidate != previous_lane:
        next_lane = NORMAL_GRAPH.get(previous_lane)
        if next_lane is None:
            candidate = previous_lane
            transition["type"] = "HOLD"
        elif candidate not in (next_lane, "S4_1", "S4_2"):
            candidate = next_lane
            transition["type"] = "NORMAL_STEP"
        elif candidate in ("S4_1", "S4_2") and previous_lane not in ("S3_3", "S4_1", "S4_2"):
            candidate = "S4_1"
            transition["type"] = "REVERSAL"
    transition["to"] = candidate
    broad_state = BROAD_STATES[candidate]
    supporting, contradicting = [], []
    if evidence["close"] is not None and evidence["ma"]["20"] is not None:
        supporting.append("price_above_ma20" if evidence["close"] >= evidence["ma"]["20"] else "price_below_ma20")
    if evidence["rsi"] is not None:
        supporting.append("rsi_bullish" if evidence["rsi"] >= config["bullish_rsi"] else "rsi_bearish")
    if evidence["macd_histogram"] is not None:
        supporting.append("macd_histogram_positive" if evidence["macd_histogram"] >= 0 else "macd_histogram_negative")
    if candidate == "S3_3":
        if evidence["near_high"]:
            supporting.append("near_window_high")
        if evidence["upper_wick_ratio"] is not None and evidence["upper_wick_ratio"] >= config["upper_wick_ratio"]:
            supporting.append("upper_wick")
        if evidence["volume_ratio"] is not None and evidence["volume_ratio"] >= config["down_volume_ratio"]:
            supporting.append("down_volume")
        if evidence["slopes"]["20"] is not None and evidence["slopes"]["20"] <= config["ma_slope_pct"]:
            supporting.append("ma20_weakness")
    if candidate.startswith("S2") and "rsi_bearish" in supporting:
        contradicting.append("rsi_bearish")
    if candidate.startswith("S4") and "price_above_ma20" in supporting:
        contradicting.append("price_above_ma20")
    confidence = "LOW" if data_status == "DATA_BLOCKED" else ("HIGH" if not contradicting and len(supporting) >= 2 else "MEDIUM")
    as_of = _value(snapshot, ("as_of",), ("provenance", "as_of"))
    provenance = _clean(snapshot.get("provenance") if isinstance(snapshot.get("provenance"), Mapping) else {})
    provenance.setdefault("source_timeframe", "daily")
    provenance.setdefault("policy_version", POLICY_VERSION)
    result = {
        "broad_state": broad_state, "machine_lane": candidate, "data_status": data_status,
        "confidence": confidence, "supporting_evidence": sorted(set(supporting)),
        "contradicting_evidence": sorted(set(contradicting)),
        "missing_evidence": sorted(set(evidence["missing"])), "transition": transition,
        "break_metadata": break_meta, "policy_version": POLICY_VERSION,
        "as_of": as_of, "provenance": provenance,
    }
    return _clean(result)


# A descriptive alias keeps the seam easy to discover for callers using the
# issue's noun phrase while retaining one implementation.
map_daily_trend = classify_daily_trend
