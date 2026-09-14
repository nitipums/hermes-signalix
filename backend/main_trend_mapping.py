"""Deterministic Daily Main Trend 1--4 evidence.

This is intentionally separate from the historical machine-lane classifier.
It consumes completed Daily technical-indicator output and has no action or
order semantics.  The boundaries are deliberately broad calibration rules;
the owner-labelled diagnostic matrix remains the authority for future tuning.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


POLICY_VERSION = "main-trend-ma-calibration-v6"
SOURCE_TIMEFRAME = "1D"
SLOPE_WINDOW = 20
MA_PERIODS = (5, 10, 20, 50, 100, 200)
MEDIUM_PERIOD = 50
LONG_PERIODS = (100, 200)
SHORT_PERIODS = (5, 10, 20)


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
