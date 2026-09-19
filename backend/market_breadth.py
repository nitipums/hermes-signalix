"""Pure deterministic active-ORD market breadth foundation (MB-1).

This module deliberately has no database, HTTP, artifact, or action imports.
Callers resolve the fixed active-ORD snapshot and normalized completed Daily
rows, then pass them here.  The two source lists are accepted separately so
an adapter can enforce official-first lineage without making a production
readback claim in this foundation ticket.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_left
from collections import defaultdict
from collections import deque
from typing import Any, Callable, Iterable, Mapping, Sequence

from main_trend_mapping import classify_main_trend


POLICY_VERSION = "market-breadth-mb1"
SOURCE_TIMEFRAME = "1D"
WINDOWS = (20, 60, 260)
_PARTIAL_REASON_CODES = {"incomplete_input_coverage"}


def _finite(value: Any, *, positive: bool = False) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or (positive and number <= 0):
        return None
    return number


def _clean(value: Any) -> Any:
    """Return recursively JSON-safe values, retaining nulls explicitly."""
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def build_direction_metadata(sessions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Describe A/D-line direction for one ordered, prebuilt report range.

    Only report-session values are considered. Invalid A/D-line sessions are
    retained as quality evidence and never filled or interpolated. Net
    advances are inspected only at valid points after the first point, so the
    result cannot use a later session to classify an earlier one.
    """
    ordered = [dict(session) for session in sessions]
    valid = [session for session in ordered if _finite(session.get("ad_line")) is not None]
    first = valid[0] if valid else None
    last = valid[-1] if valid else None
    baseline = ({"value": _finite(first["ad_line"]), "session_date": _date(first),
                 "kind": "first_valid_report_ad_line"} if first else None)
    endpoint = ({"value": _finite(last["ad_line"]), "session_date": _date(last)} if last else None)
    valid_sessions = len(valid)
    quality_states = []
    for session in ordered:
        quality = session.get("quality")
        price_quality = quality.get("price") if isinstance(quality, Mapping) else None
        if isinstance(price_quality, Mapping) and price_quality.get("status"):
            quality_states.append(price_quality["status"])
    blocked = "DATA_BLOCKED" in quality_states
    incomplete = len(valid) != len(ordered) or any(state == "PARTIAL" for state in quality_states)
    if valid_sessions < 2 or blocked:
        return {"label": "Unavailable", "status": "DATA_BLOCKED",
                "reason": ("fewer_than_two_valid_ad_line_points" if valid_sessions < 2
                           else "blocked_input_quality"),
                "baseline": baseline, "endpoint": endpoint, "delta": None,
                "valid_sessions": valid_sessions}

    steps = []
    ambiguous = False
    for session in valid[1:]:
        step = _finite(session.get("net_advances"))
        if step is None:
            ambiguous = True
        else:
            steps.append(step)
    positive = any(step > 0 for step in steps)
    negative = any(step < 0 for step in steps)
    if ambiguous or (positive and negative) or not positive and not negative:
        label = "Mixed"
    elif positive and not negative:
        label = "Rising"
    else:
        label = "Falling"
    return {"label": label, "status": "PARTIAL" if incomplete else "AVAILABLE",
            "reason": "incomplete_input_coverage" if incomplete else "valid_inputs_available",
            "baseline": baseline, "endpoint": endpoint,
            "delta": endpoint["value"] - baseline["value"],
            "valid_sessions": valid_sessions}


def _date(row: Mapping[str, Any]) -> str | None:
    value = row.get("session_date", row.get("date", row.get("as_of")))
    return str(value)[:10] if value is not None else None


def _row_key(row: Mapping[str, Any]) -> tuple[str, str] | None:
    symbol, session = row.get("symbol"), _date(row)
    return (str(symbol), session) if symbol is not None and session else None


def select_official_first_daily(
    official_rows: Iterable[Mapping[str, Any]],
    derived_rows: Iterable[Mapping[str, Any]],
    *,
    universe: Iterable[str],
    as_of: str,
) -> list[dict[str, Any]]:
    """Select at most one row per active-ORD symbol/date.

    Official ``price_data`` wins. Derived rows only fill an absent official
    date. Input rows are copied, not mutated, and sorted for repeatability.
    Eligibility/completeness/cutoff decisions belong to the injected source
    adapter; this function only applies the lineage precedence seam.
    """
    symbols = {str(symbol) for symbol in universe}
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for source_rows, source_name in ((official_rows, "price_data"),
                                     (derived_rows, "derived_daily_price_data")):
        for source_row in source_rows:
            row = dict(source_row)
            key = _row_key(row)
            if key is None or key[0] not in symbols or key[1] > str(as_of):
                continue
            row["symbol"], row["session_date"] = key
            row.setdefault("source", source_name)
            prior = selected.get(key)
            # Official precedence is absolute. Duplicate rows from the same
            # source retain the former deterministic sorted/overwrite result
            # without materializing a second normalized input list.
            if (prior is None
                    or source_name == "price_data" and prior.get("source") != "price_data"
                    or (prior.get("source") == row.get("source")
                        and json.dumps(row, sort_keys=True, default=str)
                        > json.dumps(prior, sort_keys=True, default=str))):
                selected[key] = row
    return [selected[key] for key in sorted(selected)]


def _quality(valid: int, coverage: int, required: bool, reason: str | None = None) -> dict[str, Any]:
    if not required:
        status = "DATA_BLOCKED"
        reason = reason or "required_history_unavailable"
    elif valid == 0:
        status = "DATA_BLOCKED"
        reason = reason or "no_valid_rows"
    elif valid < coverage:
        status = "PARTIAL"
        reason = reason if reason in _PARTIAL_REASON_CODES else "incomplete_input_coverage"
    else:
        status = "AVAILABLE"
        reason = "valid_inputs_available"
    return {"status": status, "reason": reason, "valid_rows": valid, "coverage_rows": coverage}


def _stage_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    totals = {str(stage): {"total": 0, "full": 0, "partial": 0} for stage in (1, 2, 3, 4)}
    missing = 0
    for row in rows:
        trend = row.get("main_trend", row.get("main_trend_value"))
        if trend in (1, 2, 3, 4, "1", "2", "3", "4"):
            bucket = totals[str(trend)]
            bucket["total"] += 1
            quality = row.get("evidence_quality", "PARTIAL")
            bucket["full" if quality == "FULL" else "partial"] += 1
        else:
            missing += 1
    return {"totals": totals, "missing_or_blocked": missing}


def _trend(row: Mapping[str, Any], classifier: Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> dict[str, Any] | None:
    supplied = row.get("main_trend_evidence")
    if isinstance(supplied, Mapping):
        return dict(supplied)
    snapshot = row.get("trend_snapshot", row.get("technical_snapshot"))
    if isinstance(snapshot, Mapping):
        return dict(classifier(snapshot))
    return None


def _build_extreme_index(
    history: Mapping[str, Mapping[str, Mapping[str, Any]]],
    completed_dates: Sequence[str],
) -> dict[str, dict[int, dict[str, list[tuple[int, float | None, float | None]]]]]:
    """Index completed-session prior-window stats once per symbol.

    Each tuple is ``(valid_count, high_max, low_min)`` for the completed
    sessions immediately preceding that position.  Missing values remain
    missing in ``valid_count`` so the existing reason-code contract is kept.
    """
    index = {}
    for symbol, by_date in history.items():
        high_values = [_finite(by_date.get(date, {}).get("high")) for date in completed_dates]
        low_values = [_finite(by_date.get(date, {}).get("low")) for date in completed_dates]
        windows = {}
        for window in WINDOWS:
            stats = []
            high_queue: deque[tuple[int, float]] = deque()
            low_queue: deque[tuple[int, float]] = deque()
            for position in range(len(completed_dates) + 1):
                start = max(0, position - window)
                while high_queue and high_queue[0][0] < start:
                    high_queue.popleft()
                while low_queue and low_queue[0][0] < start:
                    low_queue.popleft()
                stats.append((
                    0,
                    high_queue[0][1] if high_queue else None,
                    low_queue[0][1] if low_queue else None,
                ))
                if position == len(completed_dates):
                    break
                prior_high = high_values[position]
                if prior_high is not None:
                    while high_queue and high_queue[-1][1] <= prior_high:
                        high_queue.pop()
                    high_queue.append((position, prior_high))
                prior_low = low_values[position]
                if prior_low is not None:
                    while low_queue and low_queue[-1][1] >= prior_low:
                        low_queue.pop()
                    low_queue.append((position, prior_low))
            # Deque extrema above are correct for each prior window; valid
            # counts use prefix differences so missing values stay explicit.
            high_prefix = [0]
            low_prefix = [0]
            for value in high_values:
                high_prefix.append(high_prefix[-1] + (value is not None))
            for value in low_values:
                low_prefix.append(low_prefix[-1] + (value is not None))
            windows[window] = {
                "high": [(high_prefix[position] - high_prefix[max(0, position - window)], stats[position][1], None)
                         for position in range(len(completed_dates) + 1)],
                "low": [(low_prefix[position] - low_prefix[max(0, position - window)], None, stats[position][2])
                        for position in range(len(completed_dates) + 1)],
            }
        index[symbol] = windows
    return index


def _extreme(row: Mapping[str, Any], extreme_index: Mapping[str, Any], window: int, *, high: bool,
             completed_dates: Sequence[str]) -> dict[str, Any]:
    current = _finite(row.get("high" if high else "low"))
    symbol = str(row.get("symbol"))
    session = _date(row)
    name = "new_high" if high else "new_low"
    if current is None:
        return {name: None, "reason": f"{name}_current_value_invalid"}
    position = bisect_left(completed_dates, session)
    prior_count = min(position, window)
    if prior_count < window:
        return {name: None, "reason": f"insufficient_prior_{window}_sessions"}
    stats = extreme_index.get(symbol, {}).get(window, {}).get("high" if high else "low", [])
    valid_count, high_max, low_min = stats[position] if position < len(stats) else (0, None, None)
    if valid_count < window:
        return {name: None, "reason": f"missing_prior_{window}_session_values"}
    extreme = high_max if high else low_min
    return {name: current > extreme if high else current < extreme,
            "reason": "strictly_exceeds_prior_window_excluding_current"}


def _session_metrics(session_rows: Sequence[Mapping[str, Any]], prior_rows: Sequence[Mapping[str, Any]],
                     extreme_index: Mapping[str, Any], classifier: Callable,
                     completed_dates: Sequence[str], coverage_expected: int | None = None) -> dict[str, Any]:
    previous = {_row_key(row)[0]: _finite(row.get("close")) for row in prior_rows if _row_key(row)}
    valid_price = []
    for row in session_rows:
        current, prior = _finite(row.get("close"), positive=True), previous.get(str(row.get("symbol")))
        if current is not None and prior is not None and prior > 0:
            valid_price.append((row, current, prior))
    advancers = sum(current > prior for _, current, prior in valid_price)
    decliners = sum(current < prior for _, current, prior in valid_price)
    unchanged = sum(current == prior for _, current, prior in valid_price)
    valid_count, coverage = len(valid_price), coverage_expected or len(session_rows)
    ratio_status = "AVAILABLE"
    ratio = None
    if valid_count == 0:
        ratio_status = "NO_VALID_ROWS"
    elif decliners == 0:
        ratio_status = "NO_DECLINERS"
    else:
        ratio = advancers / decliners
    volume_up = volume_down = 0.0
    volume_up_rows = volume_down_rows = 0
    unchanged_or_blocked_rows = coverage - (advancers + decliners)
    invalid_volume_rows = 0
    for row, current, prior in valid_price:
        volume = _finite(row.get("volume"), positive=True)
        if volume is None:
            invalid_volume_rows += 1
            continue
        if current > prior:
            volume_up += volume; volume_up_rows += 1
        elif current < prior:
            volume_down += volume; volume_down_rows += 1
    price_quality = _quality(valid_count, coverage, True)
    volume_valid = volume_up_rows + volume_down_rows
    volume_coverage = advancers + decliners
    volume_quality = _quality(volume_valid, volume_coverage, volume_coverage > 0,
                              "no_valid_advancer_or_decliner_volume" if volume_valid == 0 else None)
    participation = {
        "advancing": {"count": advancers, "percentage": (advancers / valid_count * 100) if valid_count else None},
        "declining": {"count": decliners, "percentage": (decliners / valid_count * 100) if valid_count else None},
        "unchanged": {"count": unchanged, "percentage": (unchanged / valid_count * 100) if valid_count else None},
        "valid_count": valid_count, "declared_count": coverage, "denominator": valid_count,
        "quality": price_quality,
    }
    trend_rows = []
    for row in session_rows:
        evidence = _trend(row, classifier)
        if evidence is not None and evidence.get("main_trend") in (1, 2, 3, 4, "1", "2", "3", "4"):
            trend_rows.append({**row, **evidence})
    stage = _stage_counts(trend_rows)
    stage["missing_or_blocked"] = coverage - len(trend_rows)
    ma_counts = {}
    for period in (50, 200):
        above = below = blocked = 0
        for row in session_rows:
            explicit = row.get(f"above_ma{period}")
            if isinstance(explicit, bool):
                above += explicit
                below += not explicit
                continue
            close = _finite(row.get("close"), positive=True)
            ma = _finite(row.get(f"ma{period}", row.get(f"ma_{period}")), positive=True)
            if close is None or ma is None:
                blocked += 1
            else:
                above += close > ma
                below += close <= ma
        valid = above + below
        ma_counts[f"above_ma{period}"] = {"count": above, "below_count": below,
                                            "blocked_rows": blocked, "valid_rows": valid,
                                            "coverage_rows": coverage,
                                            "quality": _quality(valid, coverage, True)}
    by_symbol = {}
    for row in session_rows:
        symbol = str(row.get("symbol"))
        by_symbol[symbol] = {str(window): {**_extreme(row, extreme_index, window, high=True, completed_dates=completed_dates),
                                           **_extreme(row, extreme_index, window, high=False, completed_dates=completed_dates)}
                             for window in WINDOWS}
    aggregates = {}
    for window in WINDOWS:
        values = [by_symbol[symbol][str(window)] for symbol in sorted(by_symbol)]
        high_valid = sum(item["new_high"] is not None for item in values)
        low_valid = sum(item["new_low"] is not None for item in values)
        high_count = sum(item["new_high"] is True for item in values)
        low_count = sum(item["new_low"] is True for item in values)
        aggregates[str(window)] = {"new_high_count": high_count, "new_low_count": low_count,
                                   "new_high_valid_rows": high_valid, "new_low_valid_rows": low_valid,
                                   "coverage_rows": coverage,
                                   "quality": {"new_high": _quality(high_valid, coverage, True),
                                               "new_low": _quality(low_valid, coverage, True)}}
    return {"price": {"advancers": advancers, "decliners": decliners, "unchanged": unchanged,
                       "valid_rows": valid_count, "coverage_rows": coverage, "denominator": valid_count,
                       "quality": price_quality},
            "participation": participation,
            "ad_ratio": {"value": ratio, "status": ratio_status},
            "net_advances": advancers - decliners,
            "volume": {"up": volume_up, "down": volume_down, "up_rows": volume_up_rows,
                       "down_rows": volume_down_rows, "price_valid_advancer_decliner_rows": volume_coverage,
                       "unchanged_or_blocked_rows": unchanged_or_blocked_rows,
                       "invalid_volume_rows": invalid_volume_rows,
                       "invalid_or_excluded_rows": invalid_volume_rows,
                       "quality": volume_quality},
            "main_trend": stage, "moving_average_breadth": ma_counts,
            "new_high_low": {**by_symbol, **aggregates, "by_symbol": by_symbol, "aggregate": aggregates},
            "quality": {"price": price_quality, "volume": volume_quality,
                        "main_trend": _quality(len(trend_rows), coverage, bool(session_rows), "main_trend_evidence_absent"),
                        "moving_average_breadth": _quality(sum(item["valid_rows"] for item in ma_counts.values()), coverage * 2, bool(session_rows), "moving_average_evidence_absent"),
                        "new_high_low": _quality(sum(item["new_high_valid_rows"] + item["new_low_valid_rows"] for item in aggregates.values()), coverage * len(aggregates) * 2, bool(session_rows), "history_unavailable")}}


def build_market_breadth(
    observations: Iterable[Mapping[str, Any]],
    *,
    universe_snapshot: Mapping[str, Any] | None = None,
    classifier: Callable[[Mapping[str, Any]], Mapping[str, Any]] = classify_main_trend,
    completed_session_dates: Iterable[str] | None = None,
    report_session_dates: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Aggregate normalized completed-Daily observations by market session.

    The latest completed session is the sole market-wide ``as_of``. Historical
    sessions remain available for the 20/60/260 output consumers. A/D line is
    accumulated chronologically from each session's net advances and carries
    forward across no-valid sessions without interpolation or reset.
    """
    raw_rows = [dict(row) for row in observations if isinstance(row, Mapping)]
    declared_symbols = universe_snapshot.get("symbols") if isinstance(universe_snapshot, Mapping) else None
    declared_symbols = universe_snapshot.get("declared_symbols", declared_symbols) if isinstance(universe_snapshot, Mapping) else None
    declared_set = {str(symbol) for symbol in declared_symbols} if declared_symbols is not None else None
    out_of_universe_rows = sum(str(row.get("symbol")) not in declared_set for row in raw_rows) if declared_set is not None else 0
    rows = [row for row in raw_rows if declared_set is None or str(row.get("symbol")) in declared_set]
    rows = [row for row in rows if _date(row)]
    dates = sorted({_date(row) for row in rows})
    if completed_session_dates is None and isinstance(universe_snapshot, Mapping):
        completed_session_dates = universe_snapshot.get("completed_session_dates", universe_snapshot.get("completed_sessions"))
    completed_dates = sorted({str(date)[:10] for date in completed_session_dates}) if completed_session_dates is not None else []
    snapshot_count = (universe_snapshot or {}).get("count")
    declared_count = snapshot_count if snapshot_count is not None else (
        len(declared_set) if declared_set is not None else None)
    context_dates = completed_dates or dates
    report_dates = ([str(date)[:10] for date in report_session_dates]
                    if report_session_dates is not None else dates)
    report_dates = sorted(set(report_dates))
    as_of = report_dates[-1] if report_dates else None
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[_date(row)].append(row)
    history_index = defaultdict(dict)
    for row in rows:
        symbol, session = _row_key(row) or (None, None)
        if symbol is not None:
            history_index[symbol][session] = row
    extreme_index = _build_extreme_index(history_index, context_dates)
    metrics = {}
    ad_line, seen_valid = 0, False
    for session in report_dates:
        context_position = bisect_left(context_dates, session)
        previous_session = context_dates[context_position - 1] if context_position else None
        previous_rows = by_date.get(previous_session, []) if previous_session else []
        metric = _session_metrics(by_date.get(session, []), previous_rows, extreme_index, classifier, context_dates,
                                   declared_count if declared_set is not None else None)
        if metric["price"]["valid_rows"]:
            if seen_valid:
                ad_line += metric["net_advances"]
            else:
                ad_line = 0
            seen_valid = True
            metric["ad_line"] = ad_line
        else:
            metric["ad_line"] = None
        metric["ad_line_status"] = "AVAILABLE" if seen_valid else "NO_VALID_ROWS"
        metrics[session] = metric
    current = metrics.get(as_of, {})
    # ``observed_count`` is deliberately the historical-union count for the
    # emitted input window. Current-session coverage is separate because a
    # symbol can have history while being absent from the latest session.
    observed_symbols = {str(row.get("symbol")) for row in rows if row.get("symbol") is not None}
    current_rows = by_date.get(as_of, []) if as_of else []
    current_symbols = {str(row.get("symbol")) for row in current_rows if row.get("symbol") is not None}
    universe = dict(universe_snapshot or {"name": "active_ord"})
    universe.update({"declared_count": declared_count, "observed_count": len(observed_symbols),
                     "blocked_count": max((declared_count or 0) - len(observed_symbols), 0),
                     "historical_declared_count": declared_count,
                     "historical_observed_count": len(observed_symbols),
                     "historical_blocked_count": max((declared_count or 0) - len(observed_symbols), 0),
                     "current_declared_count": declared_count,
                     "current_observed_count": len(current_symbols),
                     "current_blocked_count": max((declared_count or 0) - len(current_symbols), 0),
                     "out_of_universe_rows": out_of_universe_rows,
                     "resolution": "declared_snapshot" if declared_set is not None else "unresolved_snapshot"})
    if declared_set is not None:
        universe["declared_symbol_count"] = len(declared_set)
        universe["snapshot_count_matches_symbols"] = snapshot_count is None or snapshot_count == len(declared_set)
    current_quality = current.get("quality", {})
    statuses = [value.get("status") for key, value in current_quality.items() if isinstance(value, Mapping) and key != "status"]
    usable = [status for status in statuses if status in {"AVAILABLE", "PARTIAL"}]
    summary_status = "AVAILABLE" if statuses and all(status == "AVAILABLE" for status in statuses) else ("PARTIAL" if usable else "DATA_BLOCKED")
    summary = {"status": summary_status, "reason": "all_required_metrics_available" if summary_status == "AVAILABLE" else ("incomplete_or_blocked_required_metric" if summary_status == "PARTIAL" else "no_current_metric_usable")}
    current_quality["status"] = summary_status
    current_quality["summary"] = summary
    ordered_sessions = [{"session_date": session, **metrics[session]} for session in report_dates]
    directions = {
        "history_20": build_direction_metadata(ordered_sessions[-20:]),
        "history_60": build_direction_metadata(ordered_sessions[-60:]),
        "history_260": build_direction_metadata(ordered_sessions[-260:]),
        "history_all": build_direction_metadata(ordered_sessions),
    }
    return _clean({"policy_version": POLICY_VERSION, "universe": universe,
                   "as_of": as_of, "source_timeframe": SOURCE_TIMEFRAME,
                   "sessions": metrics, "current": current, "quality": summary,
                   "history": {"windows": list(WINDOWS), "sessions": report_dates},
                   "directions": directions})


build_breadth = build_market_breadth
