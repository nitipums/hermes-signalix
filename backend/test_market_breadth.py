import json
import time
from datetime import date, timedelta

import pytest

from market_breadth import (_quality, build_market_breadth,
                            build_direction_metadata,
                            select_official_first_daily)


def row(symbol, date, close, *, high=None, low=None, volume=100, trend=None, quality="FULL", **extra):
    value = {"symbol": symbol, "session_date": date, "open": close, "high": high or close,
             "low": low or close, "close": close, "volume": volume, **extra}
    if trend is not None:
        value["main_trend_evidence"] = {"main_trend": trend, "evidence_quality": quality}
    return value


def test_official_first_selection_is_a_separate_deterministic_seam():
    selected = select_official_first_daily(
        [row("AAA", "2026-09-10", 10, source="price_data")],
        [row("AAA", "2026-09-10", 11, source="derived_daily_price_data"),
         row("AAA", "2026-09-11", 12, source="derived_daily_price_data")],
        universe=["AAA"], as_of="2026-09-11")
    assert [(item["session_date"], item["close"], item["source"]) for item in selected] == [
        ("2026-09-10", 10, "price_data"), ("2026-09-11", 12, "derived_daily_price_data")]


def test_price_breadth_ratio_and_quality_use_valid_price_denominator():
    data = [row("A", "2026-09-09", 10), row("B", "2026-09-09", 20), row("C", "2026-09-09", 30),
            row("A", "2026-09-10", 11), row("B", "2026-09-10", 19), row("C", "2026-09-10", 30),
            row("D", "2026-09-10", 40)]
    current = build_market_breadth(data)["current"]
    assert current["price"] == {"advancers": 1, "decliners": 1, "unchanged": 1,
                                  "valid_rows": 3, "coverage_rows": 4, "denominator": 3,
                                  "quality": {"status": "PARTIAL", "reason": "incomplete_input_coverage",
                                              "valid_rows": 3, "coverage_rows": 4}}
    assert current["ad_ratio"] == {"value": 1.0, "status": "AVAILABLE"}
    assert current["participation"]["valid_count"] == 3
    assert current["participation"]["denominator"] == 3
    assert current["participation"]["declared_count"] == 4
    for category in ("advancing", "declining", "unchanged"):
        assert current["participation"][category]["count"] == 1
        assert current["participation"][category]["percentage"] == pytest.approx(100 / 3)
    assert current["participation"]["quality"] == current["price"]["quality"]


def test_ad_ratio_and_line_no_decliners_no_valid_and_continuation():
    data = [row("A", "2026-09-08", 10), row("B", "2026-09-08", 20),
            row("A", "2026-09-09", 11), row("B", "2026-09-09", 21),
            row("A", "2026-09-10", None), row("B", "2026-09-10", None)]
    result = build_market_breadth(data)
    assert result["sessions"]["2026-09-09"]["ad_ratio"] == {"value": None, "status": "NO_DECLINERS"}
    assert result["sessions"]["2026-09-09"]["ad_line"] == 0
    assert result["sessions"]["2026-09-10"]["ad_ratio"] == {"value": None, "status": "NO_VALID_ROWS"}
    assert result["sessions"]["2026-09-10"]["ad_line"] is None
    assert result["sessions"]["2026-09-10"]["ad_line_status"] == "AVAILABLE"


def test_direction_uses_first_and_last_valid_ad_line_and_is_rising():
    sessions = [
        {"session_date": "2026-09-01", "ad_line": None, "net_advances": 2},
        {"session_date": "2026-09-02", "ad_line": 0, "net_advances": 1},
        {"session_date": "2026-09-03", "ad_line": 1, "net_advances": 0},
        {"session_date": "2026-09-04", "ad_line": 1, "net_advances": 2},
    ]
    direction = build_direction_metadata(sessions)
    assert direction == {
        "label": "Rising", "status": "PARTIAL",
        "reason": "incomplete_input_coverage",
        "baseline": {"value": 0, "session_date": "2026-09-02", "kind": "first_valid_report_ad_line"},
        "endpoint": {"value": 1, "session_date": "2026-09-04"},
        "delta": 1, "valid_sessions": 3,
    }


@pytest.mark.parametrize(("steps", "label"), [
    ([-2, -1], "Falling"),
    ([1, -1], "Mixed"),
    ([0, 0], "Mixed"),
])
def test_direction_classifies_falling_mixed_and_zero_steps(steps, label):
    sessions = [{"session_date": "2026-09-01", "ad_line": 10, "net_advances": 0}]
    value = 10
    for index, step in enumerate(steps, start=2):
        value += step
        sessions.append({"session_date": f"2026-09-{index:02d}",
                         "ad_line": value, "net_advances": step})
    assert build_direction_metadata(sessions)["label"] == label


def test_direction_is_unavailable_with_fewer_than_two_valid_points():
    direction = build_direction_metadata([
        {"session_date": "2026-09-01", "ad_line": None, "net_advances": 1},
        {"session_date": "2026-09-02", "ad_line": 0, "net_advances": 1},
    ])
    assert direction["label"] == "Unavailable"
    assert direction["status"] == "DATA_BLOCKED"
    assert direction["baseline"]["value"] == 0
    assert direction["endpoint"] == {"value": 0, "session_date": "2026-09-02"}
    assert direction["delta"] is None
    assert direction["valid_sessions"] == 1


def test_direction_is_built_for_each_report_range_without_lookahead():
    data = [row("A", f"2026-09-{index:02d}", 10 + index)
            for index in range(1, 5)]
    result = build_market_breadth(data, report_session_dates=[
        "2026-09-01", "2026-09-02", "2026-09-03"])
    assert set(result["directions"]) == {"history_20", "history_60", "history_260", "history_all"}
    assert result["directions"]["history_all"]["endpoint"]["session_date"] == "2026-09-03"
    assert "2026-09-04" not in result["sessions"]


def test_volume_excludes_invalid_values_and_only_counts_advancers_decliners():
    data = [row("A", "2026-09-09", 10), row("B", "2026-09-09", 20), row("C", "2026-09-09", 30),
            row("A", "2026-09-10", 11, volume=5), row("B", "2026-09-10", 19, volume=0),
            row("C", "2026-09-10", 30, volume="bad"), row("D", "2026-09-10", 40, volume=100)]
    volume = build_market_breadth(data)["current"]["volume"]
    assert volume == {"up": 5.0, "down": 0.0, "up_rows": 1, "down_rows": 0,
                      "price_valid_advancer_decliner_rows": 2,
                      "unchanged_or_blocked_rows": 2, "invalid_volume_rows": 2,
                      "invalid_or_excluded_rows": 2, "quality": {"status": "PARTIAL",
                      "reason": "incomplete_input_coverage", "valid_rows": 1, "coverage_rows": 2}}


def test_main_trend_full_partial_counts_and_missing_ma_is_not_false():
    data = [row("A", "2026-09-09", 10), row("A", "2026-09-10", 11, trend=2, quality="FULL",
                above_ma50=True, above_ma200=None),
            row("B", "2026-09-09", 20), row("B", "2026-09-10", 19, trend=3, quality="PARTIAL",
                above_ma50=False)]
    current = build_market_breadth(data)["current"]
    assert current["main_trend"]["totals"] == {"1": {"total": 0, "full": 0, "partial": 0},
        "2": {"total": 1, "full": 1, "partial": 0}, "3": {"total": 1, "full": 0, "partial": 1},
        "4": {"total": 0, "full": 0, "partial": 0}}
    assert current["moving_average_breadth"]["above_ma200"]["valid_rows"] == 0


def test_available_main_trend_and_ma_breadth_use_available_reason():
    current = build_market_breadth([
        row("A", "2026-09-09", 10),
        row("A", "2026-09-10", 11, trend=2, above_ma50=True, above_ma200=False),
    ])['current']
    assert current["quality"]["main_trend"] == {
        "status": "AVAILABLE", "reason": "valid_inputs_available",
        "valid_rows": 1, "coverage_rows": 1,
    }
    assert current["quality"]["moving_average_breadth"] == {
        "status": "AVAILABLE", "reason": "valid_inputs_available",
        "valid_rows": 2, "coverage_rows": 2,
    }


def test_top_level_quality_summarizes_current_required_metrics():
    data = [row("A", "2026-09-09", 10), row("A", "2026-09-10", 11,
                trend=2, above_ma50=True, above_ma200=False)]
    result = build_market_breadth(data)
    assert result["quality"]["status"] == "PARTIAL"
    assert result["current"]["quality"]["status"] == "PARTIAL"
    assert result["current"]["quality"]["summary"]["reason"] == "incomplete_or_blocked_required_metric"


def test_declared_universe_filters_rows_and_preserves_coverage_accounting():
    data = [row("A", "2026-09-09", 10), row("A", "2026-09-10", 11),
            row("OUT", "2026-09-10", 99)]
    result = build_market_breadth(data, universe_snapshot={"name": "active_ord", "symbols": ["A", "B"], "count": 2})
    assert result["universe"] == {"name": "active_ord", "symbols": ["A", "B"], "count": 2,
                                  "declared_count": 2, "observed_count": 1, "blocked_count": 1,
                                  "historical_declared_count": 2, "historical_observed_count": 1,
                                  "historical_blocked_count": 1, "current_declared_count": 2,
                                  "current_observed_count": 1, "current_blocked_count": 1,
                                  "out_of_universe_rows": 1, "resolution": "declared_snapshot",
                                  "declared_symbol_count": 2, "snapshot_count_matches_symbols": True}
    assert result["current"]["price"]["coverage_rows"] == 2
    assert result["current"]["price"]["quality"]["status"] == "PARTIAL"


def test_ma_numeric_contract_counts_invalid_and_missing_as_blocked():
    data = [row("A", "2026-09-09", 10), row("A", "2026-09-10", 11, ma50=10, ma200="bad"),
            row("B", "2026-09-09", 10), row("B", "2026-09-10", 9, ma50=None, ma200=10)]
    ma = build_market_breadth(data)["current"]["moving_average_breadth"]
    assert ma["above_ma50"] == {"count": 1, "below_count": 0, "blocked_rows": 1, "valid_rows": 1,
                                 "coverage_rows": 2, "quality": {"status": "PARTIAL", "reason": "incomplete_input_coverage", "valid_rows": 1, "coverage_rows": 2}}
    assert ma["above_ma200"]["blocked_rows"] == 1


def test_new_high_low_aggregates_are_deterministic_and_sparse_history_is_blocked():
    data = [row("A", "2026-08-01", 10, high=10, low=10),
            row("A", "2026-08-03", 10, high=10, low=10),
            row("A", "2026-08-04", 10, high=10, low=10),
            row("A", "2026-08-05", 10, high=11, low=9)]
    result = build_market_breadth(data, completed_session_dates=["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"])
    window = result["current"]["new_high_low"]["aggregate"]["20"]
    assert window["new_high_count"] == 0 and window["new_low_count"] == 0
    assert window["quality"]["new_high"]["status"] == "DATA_BLOCKED"
    assert result["current"]["new_high_low"]["A"]["20"]["new_high"] is None


def test_new_high_low_aggregate_counts_completed_prior_sessions_only():
    data = [row("A", f"2026-01-{index:02d}", 10, high=100 + index, low=50 - index)
            for index in range(1, 22)]
    result = build_market_breadth(data, completed_session_dates=[f"2026-01-{index:02d}" for index in range(1, 22)])
    window = result["current"]["new_high_low"]["aggregate"]["20"]
    assert window["new_high_count"] == 1 and window["new_low_count"] == 1
    assert window["quality"]["new_high"]["status"] == "AVAILABLE"


def test_absent_main_trend_evidence_is_blocked_not_an_implicit_stage():
    data = [row("A", "2026-09-09", 10), row("A", "2026-09-10", 11)]
    current = build_market_breadth(data)["current"]
    assert current["main_trend"]["missing_or_blocked"] == 1
    assert current["quality"]["main_trend"] == {
        "status": "DATA_BLOCKED", "reason": "main_trend_evidence_absent",
        "valid_rows": 0, "coverage_rows": 1}


def test_quality_preserves_blocked_custom_reason_but_not_untruthful_partial_reason():
    assert _quality(0, 1, True, "main_trend_evidence_absent") == {
        "status": "DATA_BLOCKED", "reason": "main_trend_evidence_absent",
        "valid_rows": 0, "coverage_rows": 1,
    }
    assert _quality(0, 1, True, "moving_average_evidence_absent")["reason"] == "moving_average_evidence_absent"
    assert _quality(1, 2, True, "history_unavailable")["reason"] == "incomplete_input_coverage"
    assert _quality(1, 2, True, "incomplete_input_coverage")["reason"] == "incomplete_input_coverage"


def test_new_extreme_excludes_current_and_requires_full_prior_window():
    data = []
    for index in range(20):
        date = f"2026-08-{12 + index:02d}"
        data.append(row("A", date, 10, high=100 + index, low=50 - index))
    data.append(row("A", "2026-09-01", 10, high=121, low=29))
    completed = [f"2026-08-{12 + index:02d}" for index in range(20)] + ["2026-09-01"]
    current = build_market_breadth(data, completed_session_dates=completed)["current"]["new_high_low"]["A"]["20"]
    assert current["new_high"] is True and current["new_low"] is True
    assert current["reason"] == "strictly_exceeds_prior_window_excluding_current"
    assert build_market_breadth(data[:-1], completed_session_dates=completed[:-1])["current"]["new_high_low"]["A"]["20"]["new_high"] is None


def test_output_is_repeatable_and_json_safe():
    data = [row("A", "2026-09-01", 10), row("A", "2026-09-02", 11, volume=float("nan"))]
    first = build_market_breadth(data)
    second = build_market_breadth(list(reversed(data)))
    assert first == second
    json.dumps(first, allow_nan=False)


def test_report_sessions_are_selected_but_context_metrics_use_full_completed_history():
    data = [row("A", f"2026-01-{index:02d}", 10 + index, high=100 + index, low=50 - index)
            for index in range(1, 24)]
    result = build_market_breadth(
        data,
        completed_session_dates=[f"2026-01-{index:02d}" for index in range(1, 24)],
        report_session_dates=["2026-01-22", "2026-01-23"],
    )

    assert result["history"]["sessions"] == ["2026-01-22", "2026-01-23"]
    assert list(result["sessions"]) == ["2026-01-22", "2026-01-23"]
    assert result["as_of"] == "2026-01-23"
    # The first emitted point starts the A/D line, while its previous close
    # comes from the immediately preceding pre-roll session (2026-01-21).
    assert result["sessions"]["2026-01-22"]["price"]["advancers"] == 1
    assert result["sessions"]["2026-01-22"]["ad_line"] == 0
    assert result["sessions"]["2026-01-23"]["ad_line"] == 1
    assert result["current"]["new_high_low"]["A"]["20"]["new_high"] is True


def test_sparse_completed_context_preserves_missing_extreme_reason():
    completed = [f"2026-01-{index:02d}" for index in range(1, 22)]
    data = [row("A", date, 10, high=100, low=50) for date in completed if date != "2026-01-10"]
    result = build_market_breadth(data, completed_session_dates=completed,
                                   report_session_dates=["2026-01-21"])
    extreme = result["current"]["new_high_low"]["A"]["20"]
    assert extreme["new_high"] is None
    assert extreme["new_low"] is None
    assert extreme["reason"] == "missing_prior_20_session_values"


def test_indexed_extremes_complete_bounded_scale_smoke():
    symbols = [f"S{index:03d}" for index in range(80)]
    dates = [(date(2025, 1, 1) + timedelta(days=index)).isoformat() for index in range(520)]
    data = [row(symbol, date, 100 + position, high=200 + position, low=50 - position)
            for symbol in symbols for position, date in enumerate(dates)]
    started = time.perf_counter()
    result = build_market_breadth(data, completed_session_dates=dates,
                                   report_session_dates=dates[-260:])
    elapsed = time.perf_counter() - started
    assert result["history"]["sessions"] == dates[-260:]
    assert len(result["sessions"]) == 260
    assert elapsed < 10, f"indexed breadth smoke too slow: {elapsed:.2f}s"
