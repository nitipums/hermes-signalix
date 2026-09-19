"""Deterministic Daily Main Trend 1--4 evidence.

This is intentionally separate from the historical machine-lane classifier.
It consumes completed Daily technical-indicator output and has no action or
order semantics.  The boundaries are deliberately broad calibration rules;
the owner-labelled diagnostic matrix remains the authority for future tuning.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Mapping


POLICY_VERSION = "main-trend-ma-calibration-v6"
SOURCE_TIMEFRAME = "1D"
SLOPE_WINDOW = 20
MA_PERIODS = (5, 10, 20, 50, 100, 200)
MEDIUM_PERIOD = 50
LONG_PERIODS = (100, 200)
SHORT_PERIODS = (5, 10, 20)
PRODUCTION_READ_ONLY = "PRODUCTION_READ_ONLY"
TRIGGER_POLICY_VERSION = "main-trend-classifier-transition-v1"
TRIGGER_SEARCH_STEPS = 128
TRIGGER_REFINEMENT_STEPS = 45
TRIGGER_PRECISION = 10
PRICE_REFERENCE_MINIMUM = 0.01


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _latest(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    value = snapshot.get("latest")
    return value if isinstance(value, Mapping) else snapshot


def _series_value(snapshot: Mapping[str, Any], name: str, index: int) -> float | None:
    series = snapshot.get("series")
    values = series.get(name) if isinstance(series, Mapping) else None
    if not isinstance(values, (list, tuple)) or not values:
        return None
    try:
        return _number(values[index])
    except IndexError:
        return None


def _ma_values(snapshot: Mapping[str, Any], latest: Mapping[str, Any]) -> dict[str, float | None]:
    supplied = latest.get("ma", latest.get("moving_averages"))
    supplied = supplied if isinstance(supplied, Mapping) else {}
    return {
        str(period): _number(supplied.get(str(period)))
        if str(period) in supplied
        else _ma_series_value(snapshot, period, -1)
        for period in MA_PERIODS
    }


def _ma_series_value(snapshot: Mapping[str, Any], period: int, index: int) -> float | None:
    series = snapshot.get("series")
    ma_series = series.get("ma") if isinstance(series, Mapping) else None
    values = ma_series.get(str(period)) if isinstance(ma_series, Mapping) else None
    if not isinstance(values, (list, tuple)):
        return None
    try:
        return _number(values[index])
    except IndexError:
        return None


def _slope(snapshot: Mapping[str, Any], period: int) -> float | None:
    """Return normalized change from exactly 20 bars before the latest bar."""
    current = _ma_series_value(snapshot, period, -1)
    prior = _ma_series_value(snapshot, period, -(SLOPE_WINDOW + 1))
    if current is None or prior in (None, 0):
        return None
    return (current / prior - 1.0) * 100.0


def _ordered(values: Mapping[str, float | None], periods: tuple[int, ...], descending: bool) -> bool:
    selected = [values[str(period)] for period in periods]
    return all(value is not None for value in selected) and all(
        (left > right if descending else left < right)
        for left, right in zip(selected, selected[1:]))


def _direction(values: Mapping[str, float | None], periods: tuple[int, ...], positive: bool) -> bool:
    selected = [values[str(period)] for period in periods]
    return all(value is not None and (value > 0 if positive else value < 0) for value in selected)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def classify_main_trend(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build exactly one deterministic Main Trend evidence result."""
    source = snapshot if isinstance(snapshot, Mapping) else {}
    latest = _latest(source)
    close = _number(latest.get("close"))
    if close is None:
        close = _series_value(source, "close", -1)
    ma = _ma_values(source, latest)
    slopes = {str(period): _slope(source, period) for period in MA_PERIODS}
    missing_periods = [str(period) for period in MA_PERIODS if ma[str(period)] is None]
    missing_slope_periods = [str(period) for period in MA_PERIODS if slopes[str(period)] is None]
    quality = "FULL" if not missing_periods and not missing_slope_periods else "PARTIAL"

    close_position = {
        str(period): ("ABOVE" if close is not None and ma[str(period)] is not None and close > ma[str(period)]
                      else "BELOW" if close is not None and ma[str(period)] is not None and close < ma[str(period)]
                      else "UNAVAILABLE")
        for period in MA_PERIODS
    }
    bullish_order = _ordered(ma, MA_PERIODS, True)
    bearish_order = _ordered(ma, MA_PERIODS, False)
    long_intact = _ordered(ma, LONG_PERIODS, True)
    bullish_slopes = _direction(slopes, MA_PERIODS, True)
    bearish_slopes = _direction(slopes, MA_PERIODS, False)
    long_distance_pct = {
        str(period): ((ma[str(period)] - close) / ma[str(period)] * 100.0
                      if close is not None and ma[str(period)] not in (None, 0) else None)
        for period in LONG_PERIODS
    }
    available_long_distances = [value for value in long_distance_pct.values() if value is not None]
    long_distance_median_pct = _median(available_long_distances)
    long_distance_max_pct = max(available_long_distances, default=None)
    negative_slope_count = sum(value is not None and value < 0 for value in slopes.values())
    long_negative_slope_count = sum(slopes[str(period)] is not None and slopes[str(period)] < 0
                                    for period in LONG_PERIODS)
    slope_continuity = {
        "negative_count": negative_slope_count,
        "negative_ratio": negative_slope_count / len(MA_PERIODS),
        "long_negative_count": long_negative_slope_count,
        "long_negative_ratio": long_negative_slope_count / len(LONG_PERIODS),
    }
    short_weakening = ((ma["5"] is not None and ma["10"] is not None and ma["5"] < ma["10"])
                       or (slopes["5"] is not None and slopes["5"] < 0)
                       or (close is not None and ma["20"] is not None and close < ma["20"]))
    short_stack_median = _median([
        value for period in SHORT_PERIODS
        if (value := ma[str(period)]) is not None
    ])
    short_stack_vs_ma50_pct = (
        (short_stack_median / ma[str(MEDIUM_PERIOD)] - 1.0) * 100.0
        if short_stack_median is not None and ma[str(MEDIUM_PERIOD)] not in (None, 0) else None
    )
    short_negative_count = sum(
        value is not None and value < 0
        for period in SHORT_PERIODS
        if (value := slopes[str(period)]) is not None
    )
    long_regime_bullish = (
        close is not None
        and close_position["100"] == "ABOVE"
        and close_position["200"] == "ABOVE"
        and slopes["100"] is not None and slopes["100"] > 0
        and slopes["200"] is not None and slopes["200"] > 0
    )
    short_pullback_in_bullish_long_regime = (
        long_regime_bullish
        and short_stack_vs_ma50_pct is not None
        and short_stack_vs_ma50_pct <= -2.0
        and long_distance_pct["200"] is not None
        and -17.0 < long_distance_pct["200"] <= -10.0
        and short_negative_count >= 2
    )

    # Main 4 is deliberately gated by normalized long-term distance and slope
    # continuity.  The first branch catches sustained full-structure damage;
    # the second catches a severe short/medium deterioration before every long
    # MA has inverted.  These are evidence rules, not symbol rules.
    full_bearish_severity = (
        close is not None and all(close_position[str(period)] == "BELOW" for period in LONG_PERIODS)
        and negative_slope_count >= 4 and long_negative_slope_count >= 2
        and (long_distance_median_pct or 0.0) >= 3.5
    )
    short_medium_severity = (
        close is not None and close_position["10"] == "BELOW" and close_position["20"] == "BELOW"
        and all(slopes[str(period)] is not None and slopes[str(period)] < 0 for period in SHORT_PERIODS)
        and long_negative_slope_count >= 1 and (long_distance_max_pct or 0.0) >= 3.5
    )
    main4_severe = full_bearish_severity or short_medium_severity
    # An isolated long-MA inversion with price still above MA5/MA10 is not
    # sustained deterioration; it remains Main 1 unless other evidence wins.
    isolated_long_inversion = (
        close is not None and not long_intact
        and close_position["5"] == "ABOVE" and close_position["10"] == "ABOVE"
        and negative_slope_count >= 4 and (long_distance_max_pct or 0.0) >= 4.5
        and (long_distance_median_pct or 0.0) < 3.5
    )
    long_advance_slowdown = (
        bullish_slopes and long_distance_median_pct is not None
        and -22.0 <= long_distance_median_pct <= -20.0
        and min(slopes[str(period)] for period in LONG_PERIODS) < 2.0
    )

    long_slope_available = slopes["100"] is not None and slopes["200"] is not None
    long_slope_100 = slopes["100"]
    long_slope_200 = slopes["200"]
    long_slope_bullish = (
        long_slope_100 is not None and long_slope_100 >= 0.5
        and long_slope_200 is not None and long_slope_200 >= 0.5
    )

    main4_transition_override = (
        slopes["50"] is not None and slopes["50"] > 0
        and close_position["50"] == "BELOW"
        and close_position["100"] == "BELOW"
        and close_position["200"] == "BELOW"
        and close_position["10"] == "ABOVE"
        and short_negative_count >= 2
    )

    if main4_transition_override:
        main_trend = 3
        reason = "medium_term_recovery_against_deep_long_term_damage"
    elif main4_severe:
        main_trend = 4
        reason = "sustained_severe_deterioration_by_long_distance_and_slope_continuity"
    elif (short_stack_vs_ma50_pct is not None and short_stack_vs_ma50_pct < 0
          and short_negative_count >= 2 and long_intact
          and not short_pullback_in_bullish_long_regime):
        main_trend = 4
        reason = "short_ma_stack_below_ma50_with_persistent_short_term_weakness"
    elif (close is not None
          and all(close_position[str(period)] == "ABOVE" for period in (10, 20, 50, 100, 200))
          and bullish_slopes and long_slope_bullish and not long_advance_slowdown):
        main_trend = 2
        reason = "bullish_advance_close_above_all_ma_and_positive_20_bar_slopes"
    elif long_advance_slowdown:
        main_trend = 3
        reason = "bullish_price_with_long_term_advance_slowdown_requires_review"
    elif isolated_long_inversion:
        main_trend = 1
        reason = "mixed_bearish_structure_without_sustained_severity"
    elif short_pullback_in_bullish_long_regime:
        main_trend = 3
        reason = "short_ma_pullback_inside_bullish_ma100_ma200_regime"
    elif (short_stack_vs_ma50_pct is not None and short_stack_vs_ma50_pct > 0
          and close_position["100"] == "ABOVE" and close_position["200"] == "ABOVE"
          and (close_position["10"] == "BELOW" or close_position["20"] == "BELOW")):
        main_trend = 3
        reason = "short_stack_above_ma50_with_medium_ma_pressure"
    elif (short_stack_vs_ma50_pct is not None and short_stack_vs_ma50_pct > 0
          and not bullish_slopes):
        main_trend = 3
        reason = "short_ma_stack_above_ma50_with_non_bullish_pressure"
    elif long_intact and short_weakening:
        main_trend = 3
        reason = "pullback_or_weakening_without_severe_deterioration"
    else:
        main_trend = 1
        reason = "no_reliable_bullish_multi_ma_alignment"

    long_slope_gate_rejected_main3 = main_trend == 3 and long_slope_available and not long_slope_bullish
    if long_slope_gate_rejected_main3:
        main_trend = 1
        reason = "main3_rejected_long_ma100_ma200_slope_not_bullish"

    # Suffixes are display-only evidence layered on top of the canonical
    # numeric Main Trend. They run after classification and never use quote,
    # momentum, volume, broad-state, legacy-lane, or chart output.
    main_trend_display = str(main_trend)
    if quality == "FULL":
        short_close_below = (close_position["10"] == "BELOW" or close_position["20"] == "BELOW")
        short_slopes_positive = _direction(slopes, SHORT_PERIODS, True)
        short_slopes_negative = _direction(slopes, SHORT_PERIODS, False)
        if main_trend == 1:
            strict_bullish = (
                close_position["10"] == "ABOVE" and close_position["20"] == "ABOVE"
                and short_slopes_positive
            )
            broad_bullish = close_position["20"] == "ABOVE" and short_slopes_positive
            if strict_bullish:
                main_trend_display = "1++"
            elif broad_bullish:
                main_trend_display = "1+"
        elif main_trend == 3:
            strict_bearish = short_slopes_negative and short_close_below
            broad_bearish = short_negative_count >= 2 and short_close_below
            if strict_bearish:
                main_trend_display = "3--"
            elif broad_bearish:
                main_trend_display = "3-"

    as_of = latest.get("as_of", source.get("as_of"))
    if as_of is None:
        provenance = source.get("provenance")
        as_of = provenance.get("as_of") if isinstance(provenance, Mapping) else None
    timeframe = str(source.get("timeframe", latest.get("timeframe", SOURCE_TIMEFRAME))).upper()
    ambiguity = []
    if quality == "PARTIAL":
        ambiguity.append("partial_ma_or_slope_evidence")
    if main_trend == 1 and any(value is None for value in ma.values()):
        ambiguity.append("classification_falls_back_without_complete_alignment")
    if (long_intact and short_weakening and negative_slope_count > 0
            and long_negative_slope_count < len(LONG_PERIODS)):
        ambiguity.append("mixed_long_term_and_short_term_evidence_requires_review")
    return {
        "main_trend": main_trend,
        "main_trend_display": main_trend_display,
        "evidence_quality": quality,
        "used_periods": [period for period in MA_PERIODS if ma[str(period)] is not None],
        "slope_window": SLOPE_WINDOW,
        "as_of": as_of,
        "source_timeframe": timeframe,
        "policy_version": POLICY_VERSION,
        "close": close,
        "moving_averages": ma,
        "close_position": close_position,
        "ma_ordering": {"bullish": bullish_order, "bearish": bearish_order, "long_term_intact": long_intact},
        "slopes_20d_pct": slopes,
        "normalized_long_term_distance_pct": long_distance_pct,
        "long_term_distance_median_pct": long_distance_median_pct,
        "long_term_distance_max_pct": long_distance_max_pct,
        "slope_continuity": slope_continuity,
        "short_stack_median": short_stack_median,
        "short_stack_vs_ma50_pct": short_stack_vs_ma50_pct,
        "short_negative_count": short_negative_count,
        "missing_periods": missing_periods,
        "missing_slope_periods": missing_slope_periods,
        "reason": reason,
        "ambiguity_reasons": ambiguity,
        "actionability": "NONE",
    }


build_main_trend_evidence = classify_main_trend


def _trigger_snapshot(snapshot: Mapping[str, Any], close: float) -> dict[str, Any]:
    """Build a copy-on-write view for one hypothetical latest close.

    Classifier transition probes must preserve every non-close evidence value,
    but only the top-level mapping, ``latest`` mapping, ``series`` mapping, and
    close-series endpoint need to be detached.  In particular, the indicator
    history and MA series remain shared and are never recursively copied.
    """
    candidate = dict(snapshot)
    latest = candidate.get("latest")
    if isinstance(latest, Mapping):
        latest = dict(latest)
        latest["close"] = close
        candidate["latest"] = latest
    else:
        candidate["close"] = close
    series = candidate.get("series")
    if isinstance(series, Mapping):
        series = dict(series)
        closes = series.get("close")
        if isinstance(closes, (list, tuple)) and closes:
            closes = list(closes)
            closes[-1] = close
            series["close"] = closes
        candidate["series"] = series
    return candidate


def _trigger_unverified(reason: str) -> dict[str, Any]:
    return {
        "up_trigger": None,
        "down_trigger": None,
        "up_trigger_operator": ">=",
        "down_trigger_operator": "<=",
        "trigger_basis": "NOT_VERIFIED",
        "trigger_quality": "NOT_VERIFIED",
        "trigger_reason": reason,
        "quality": "NOT_VERIFIED",
        "reason": reason,
        "actionability": "NONE",
    }


def _structural_reference_triggers(snapshot: Mapping[str, Any], classification: Mapping[str, Any]) -> tuple[float | None, float | None]:
    """Return nearest finite Daily reference levels around the EOD close.

    These levels are display evidence only.  They are deliberately not
    described as classifier transitions: a structural reference cannot
    guarantee that the Main Trend changes at that price.
    """
    close = _number(classification.get("close"))
    if close is None or close <= 0:
        return None, None
    latest = _latest(snapshot)
    supplied = classification.get("moving_averages")
    supplied = supplied if isinstance(supplied, Mapping) else {}
    ma = _ma_values(snapshot, latest)
    ma.update({str(key): _number(value) for key, value in supplied.items()})
    above = [value for value in ma.values() if value is not None and value > close]
    below = [value for value in ma.values() if value is not None and 0 < value < close]
    supports = []
    for container in (latest, snapshot):
        if not isinstance(container, Mapping):
            continue
        for key in ("explicit_support", "support", "support_reference"):
            value = _number(container.get(key))
            if value is not None and 0 < value < close:
                supports.append(value)
    atr_values = []
    for container in (latest, snapshot):
        if not isinstance(container, Mapping):
            continue
        for key in ("atr", "atr14", "average_true_range"):
            value = _number(container.get(key))
            if value is not None and value > 0:
                atr_values.append(value)
    above.extend(close + value for value in atr_values)
    below.extend(close - value for value in atr_values if 0 < close - value < close)
    return (min(above) if above else None,
            max([*below, *supports]) if [*below, *supports] else None)


def _price_reference_triggers(close: Any) -> tuple[float | None, float | None]:
    """Return deterministic positive price references when structure is absent.

    These are numeric display references only.  They intentionally do not
    claim that the classifier changes at either level.
    """
    close = _number(close)
    if close is None or close <= 0:
        return None, None
    distance = max(close * 0.01, PRICE_REFERENCE_MINIMUM)
    up = round(close + distance, TRIGGER_PRECISION)
    down = round(max(close - distance, PRICE_REFERENCE_MINIMUM), TRIGGER_PRECISION)
    up = up if math.isfinite(up) and up > 0 else None
    down = down if math.isfinite(down) and down > 0 else None
    return up, down


def _with_structural_fallback(result: dict[str, Any], snapshot: Mapping[str, Any],
                              classification: Mapping[str, Any], reason: str) -> dict[str, Any]:
    if result.get("up_trigger") is not None and result.get("down_trigger") is not None:
        return result
    up, down = _structural_reference_triggers(snapshot, classification)
    result = dict(result)
    structural_directions = set()
    if result.get("up_trigger") is None:
        result["up_trigger"] = up
        if up is not None:
            structural_directions.add("up")
    if result.get("down_trigger") is None:
        result["down_trigger"] = down
        if down is not None:
            structural_directions.add("down")
    price_up, price_down = _price_reference_triggers(classification.get("close"))
    price_directions = set()
    if result.get("up_trigger") is None:
        result["up_trigger"] = price_up
        if price_up is not None:
            price_directions.add("up")
    if result.get("down_trigger") is None:
        result["down_trigger"] = price_down
        if price_down is not None:
            price_directions.add("down")
    missing = [direction for direction in ("up", "down")
               if result.get(f"{direction}_trigger") is None]
    result["up_trigger_reason"] = ("classifier_transition_verified" if result.get("up_trigger") is not None and "up" not in structural_directions and "up" not in price_directions
                                    else "structural_reference_fallback" if "up" in structural_directions
                                    else "up_price_reference_fallback" if "up" in price_directions
                                    else "up_trigger_not_verified")
    result["down_trigger_reason"] = ("classifier_transition_verified" if result.get("down_trigger") is not None and "down" not in structural_directions and "down" not in price_directions
                                      else "structural_reference_fallback" if "down" in structural_directions
                                      else "down_price_reference_fallback" if "down" in price_directions
                                      else "down_trigger_not_verified")
    if missing:
        if price_directions:
            result["trigger_quality"] = "PARTIAL"
            result["quality"] = "PARTIAL"
            result["trigger_basis"] = "PRICE_REFERENCE_FALLBACK"
            result["trigger_reason"] = ";".join(
                f"{direction}_price_reference_fallback" for direction in ("up", "down")
                if direction in price_directions)
        else:
            result["trigger_quality"] = "NOT_VERIFIED"
            result["quality"] = "NOT_VERIFIED"
            result["trigger_basis"] = "NOT_VERIFIED"
            result["trigger_reason"] = ("no_numeric_structural_reference"
                                        if len(missing) == 2
                                        else f"{missing[0]}_trigger_not_verified")
        result["reason"] = result["trigger_reason"]
    elif price_directions:
        result["trigger_quality"] = "PARTIAL"
        result["quality"] = "PARTIAL"
        result["trigger_basis"] = "PRICE_REFERENCE_FALLBACK"
        result["trigger_reason"] = ";".join(
            f"{direction}_price_reference_fallback" for direction in ("up", "down")
            if direction in price_directions)
        result["reason"] = result["trigger_reason"]
    elif structural_directions:
        result["trigger_quality"] = "PARTIAL"
        result["quality"] = "PARTIAL"
        result["trigger_basis"] = "STRUCTURAL_REFERENCE_FALLBACK"
        result["trigger_reason"] = reason
        result["reason"] = reason
    return result


def _transition_level(snapshot: Mapping[str, Any], current_close: float, current_trend: int,
                     *, direction: str, lower: float, upper: float) -> float | None:
    """Find and verify the nearest classifier transition in one direction."""
    increasing = direction == "up"

    def changed(level: float) -> bool:
        result = classify_main_trend(_trigger_snapshot(snapshot, level))
        trend = _history_trend(result.get("main_trend"))
        return trend is not None and ((trend < current_trend) if increasing else (trend > current_trend))

    start, end = (current_close, upper) if increasing else (current_close, lower)
    if (not _number(start) or not _number(end)
            or (increasing and end <= start) or (not increasing and end >= start)):
        return None
    step = (end - start) / TRIGGER_SEARCH_STEPS
    previous = start
    for index in range(1, TRIGGER_SEARCH_STEPS + 1):
        level = start + step * index
        if changed(level):
            lo, hi = (previous, level) if increasing else (level, previous)
            for _ in range(TRIGGER_REFINEMENT_STEPS):
                middle = (lo + hi) / 2.0
                if changed(middle):
                    if increasing:
                        hi = middle
                    else:
                        lo = middle
                else:
                    if increasing:
                        lo = middle
                    else:
                        hi = middle
            candidate = round(hi if increasing else lo, TRIGGER_PRECISION)
            if not changed(candidate):
                candidate = hi if increasing else lo
            verified = changed(candidate)
            if verified and (candidate >= current_close if increasing else candidate <= current_close):
                return candidate
            return None
        previous = level
    return None


def build_main_trend_trigger_evidence(snapshot: Mapping[str, Any] | None,
                                      classification: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Calculate verified EOD classifier-transition boundaries.

    Only the hypothetical latest close changes.  The bounded search is
    deterministic and every returned level is reclassified before publication.
    """
    source = snapshot if isinstance(snapshot, Mapping) else {}
    current = classification if isinstance(classification, Mapping) else classify_main_trend(source)
    current_close = _number(current.get("close"))
    current_trend = _history_trend(current.get("main_trend"))
    values = current.get("moving_averages")
    ma_values = [_number(value) for value in values.values()] if isinstance(values, Mapping) else []
    if current.get("evidence_quality") != "FULL":
        return _with_structural_fallback(
            _trigger_unverified("partial_or_missing_classifier_evidence"), source, current,
            "partial_or_missing_classifier_evidence")
    if current_close is None or current_trend is None or not ma_values or any(value is None or value <= 0 for value in ma_values):
        return _with_structural_fallback(
            _trigger_unverified("non_finite_or_insufficient_search_evidence"), source, current,
            "non_finite_or_insufficient_search_evidence")
    lower = max(min([current_close, *ma_values]) * 0.5, 10 ** -TRIGGER_PRECISION)
    upper = max([current_close, *ma_values]) * 1.5
    if not math.isfinite(lower) or not math.isfinite(upper) or lower >= current_close or upper <= current_close:
        return _with_structural_fallback(
            _trigger_unverified("insufficient_search_domain"), source, current,
            "insufficient_search_domain")
    up = _transition_level(source, current_close, current_trend, direction="up", lower=lower, upper=upper)
    down = _transition_level(source, current_close, current_trend, direction="down", lower=lower, upper=upper)
    if up is None and down is None:
        return _with_structural_fallback(
            _trigger_unverified("no_verified_classifier_transition_in_bounded_domain"), source, current,
            "no_verified_classifier_transition_in_bounded_domain")
    missing = []
    if up is None:
        missing.append("up")
    if down is None:
        missing.append("down")
    reason = f"{missing[0]}_transition_not_verified" if len(missing) == 1 else "incomplete_classifier_transition_evidence"
    return _with_structural_fallback({
        "up_trigger": up,
        "down_trigger": down,
        "up_trigger_operator": ">=",
        "down_trigger_operator": "<=",
        "trigger_basis": f"{TRIGGER_POLICY_VERSION};hold_all_evidence_except_latest_close",
        "trigger_quality": "VERIFIED" if not missing else "PARTIAL",
        "trigger_reason": None if not missing else reason,
        "quality": "VERIFIED" if not missing else "PARTIAL",
        "reason": None if not missing else reason,
        "actionability": "NONE",
    }, source, current, reason)


build_classifier_transition_triggers = build_main_trend_trigger_evidence


def _history_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _history_trend(value: Any) -> int | None:
    if isinstance(value, Mapping):
        value = value.get("main_trend", value.get("value"))
    if isinstance(value, bool):
        return None
    try:
        trend = int(value)
    except (TypeError, ValueError):
        return None
    return trend if trend in (1, 2, 3, 4) else None


def _history_trigger(observation: Mapping[str, Any], name: str) -> float | None:
    value = observation.get(name)
    if value is None:
        evidence = observation.get("trigger_evidence")
        value = evidence.get(name) if isinstance(evidence, Mapping) else None
    return _number(value)


def _unverified_history_row(*, reason: str, as_of: Any = None, trend: int | None = None) -> dict[str, Any]:
    return {
        "as_of": as_of,
        "trend_state": trend,
        "main_trend": trend,
        "trend_changed_date": None,
        "trend_duration_sessions": None,
        "up_trigger": None,
        "down_trigger": None,
        "up_trigger_operator": ">=",
        "down_trigger_operator": "<=",
        "trigger_basis": "NOT_VERIFIED",
        "trigger_quality": "NOT_VERIFIED",
        "trigger_reason": reason,
        "quality": "NOT_VERIFIED",
        "reason": reason,
        "status": PRODUCTION_READ_ONLY,
        "research_only": False,
        "actionability": "NONE",
    }


def build_trend_history_evidence(observations: Any, *, symbol: str | None = None) -> list[dict[str, Any]]:
    """Build deterministic per-completed-EOD trend duration evidence.

    ``observations`` must be ordered completed-EOD classifier output for one
    symbol.  Trigger levels are deliberately not calculated here: only
    explicit finite levels supplied by the classifier evidence are accepted.
    This keeps the history seam from introducing an undocumented threshold.
    """
    raw = observations if isinstance(observations, (list, tuple)) else []
    if not raw:
        row = _unverified_history_row(reason="no_completed_eod_observations")
        row["symbol"] = symbol
        return [row]

    parsed: list[tuple[Mapping[str, Any], date, int]] = []
    structural_reason = None
    previous_date = None
    for observation in raw:
        if not isinstance(observation, Mapping):
            structural_reason = "invalid_observation"
            break
        observed_date = _history_date(observation.get("as_of", observation.get("date", observation.get("session_date"))))
        trend = _history_trend(observation.get("main_trend", observation.get("trend_state", observation.get("trend"))))
        if observed_date is None:
            structural_reason = "invalid_observation_date"
            break
        if trend is None:
            structural_reason = "invalid_trend_state"
            break
        if previous_date is not None and observed_date <= previous_date:
            structural_reason = "observations_not_strictly_ordered"
            break
        parsed.append((observation, observed_date, trend))
        previous_date = observed_date

    if structural_reason is not None:
        return [_unverified_history_row(reason=structural_reason,
                                         as_of=(item.get("as_of", item.get("date"))
                                                if isinstance(item, Mapping) else None))
                for item in raw]

    result = []
    previous_trend = None
    changed_date = None
    duration = 0
    for observation, observed_date, trend in parsed:
        if trend != previous_trend:
            changed_date = observed_date.isoformat()
            duration = 1
        else:
            duration += 1
        up_trigger = _history_trigger(observation, "up_trigger")
        down_trigger = _history_trigger(observation, "down_trigger")
        trigger_basis = observation.get("trigger_basis")
        missing_directions = [direction for direction, value in (
            ("up", up_trigger), ("down", down_trigger)) if value is None]
        if len(missing_directions) == 2:
            trigger_reason = "authoritative_trigger_fields_unavailable"
            trigger_quality = "NOT_VERIFIED"
            trigger_basis = "NOT_VERIFIED"
        elif missing_directions:
            trigger_reason = f"{missing_directions[0]}_trigger_not_verified"
            trigger_quality = "PARTIAL"
            trigger_basis = str(trigger_basis or "supplied_classifier_evidence")
        else:
            trigger_reason = None
            trigger_quality = "VERIFIED"
            trigger_basis = str(trigger_basis or "supplied_classifier_evidence")
        item = {
            "symbol": symbol,
            "as_of": observed_date.isoformat(),
            "trend_state": trend,
            "main_trend": trend,
            "trend_changed_date": changed_date,
            "trend_duration_sessions": duration,
            "up_trigger": up_trigger,
            "down_trigger": down_trigger,
            "up_trigger_operator": ">=",
            "down_trigger_operator": "<=",
            "trigger_basis": trigger_basis,
            "trigger_quality": trigger_quality,
            "trigger_reason": trigger_reason,
            "quality": "VERIFIED" if trigger_quality == "VERIFIED" else "NOT_VERIFIED",
            "reason": trigger_reason,
            "status": PRODUCTION_READ_ONLY,
            "research_only": False,
            "actionability": "NONE",
        }
        result.append(item)
        previous_trend = trend
    return result


build_trend_history = build_trend_history_evidence
