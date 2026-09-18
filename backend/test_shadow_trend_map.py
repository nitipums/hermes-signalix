import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time

import pytest

import shadow_trend_map as subject


def bars(count=45, *, invalid=False):
    rows = []
    for i in range(count):
        close = 100 + i
        rows.append({"date": f"2026-01-{(i % 28) + 1:02d}", "open": close - 1,
                     "high": close + 1, "low": close - 2, "close": close, "volume": 1000})
    if invalid:
        rows[0]["low"] = "bad"
    return rows


def test_policy_window_and_prior_support_excludes_current():
    result = subject.evaluate_symbol("AAA", bars(400), "2026-09-11")
    assert result["bars_used"] == 400
    assert result["support"]["excluded_current_bar"] is True
    assert result["support"]["prior_bars"] == 10
    assert result["main_trend"]["main_trend"] in (1, 2, 3, 4)
    assert result["main_trend"]["source_timeframe"] == "1D"
    assert result["main_trend"]["actionability"] == "NONE"


def test_current_eod_path_computes_indicators_once_and_marks_missing_history_not_verified(monkeypatch):
    calls = 0
    original = subject.build_technical_indicators

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(subject, "build_technical_indicators", counted)
    result = subject.evaluate_symbol("AAA", bars(75), "2026-09-11")

    assert calls == 1
    assert result["trend_duration_sessions"] is None
    assert result["history_quality"] == "NOT_VERIFIED"
    assert result["history_reason"] == "ordered_history_unavailable"
    assert result["main_trend"]["trigger_basis"].startswith("main-trend-classifier-transition-v1") or result["main_trend"]["trigger_basis"] == "NOT_VERIFIED"


def test_supplied_ordered_history_is_consumed_without_recomputing_indicators():
    history = [
        {"as_of": "2026-09-09", "main_trend": 2, "up_trigger": 110, "down_trigger": 90},
        {"as_of": "2026-09-10", "main_trend": 2, "up_trigger": 111, "down_trigger": 89},
        {"as_of": "2026-09-11", "main_trend": 3, "up_trigger": 112, "down_trigger": 88},
    ]
    result = subject.evaluate_symbol("AAA", bars(75), "2026-09-11", history_observations=history)

    assert result["trend_changed_date"] == "2026-09-11"
    assert result["trend_duration_sessions"] == 1
    assert result["history_quality"] == "VERIFIED"


def test_prior_history_adds_duration_without_replacing_current_trigger_fields(monkeypatch):
    monkeypatch.setattr(subject, "build_main_trend_trigger_evidence", lambda *_: {
        "up_trigger": 150.0, "down_trigger": None,
        "up_trigger_operator": ">=", "down_trigger_operator": "<=",
        "trigger_basis": "current-test-basis", "trigger_quality": "PARTIAL",
        "trigger_reason": "down_transition_not_verified", "quality": "PARTIAL",
        "reason": "down_transition_not_verified", "actionability": "NONE",
    })
    history = [
        {"as_of": "2026-09-09", "main_trend": 3, "up_trigger": 120.0, "down_trigger": 80.0},
        {"as_of": "2026-09-10", "main_trend": 3, "up_trigger": 121.0, "down_trigger": 79.0},
    ]
    result = subject.evaluate_symbol("AAA", bars(75), "2026-09-11", history_observations=history)

    assert result["trend_duration_sessions"] == 3
    assert result["trend_changed_date"] == "2026-09-09"
    assert result["up_trigger"] == 150.0
    assert result["down_trigger"] is None
    assert result["trigger_quality"] == "PARTIAL"


def test_compact_projection_exposes_direction_quality_and_reason():
    row = {"symbol": "AAA", "main_trend": {"main_trend": 2},
           "up_trigger": 150.0, "down_trigger": None,
           "up_trigger_operator": ">=", "down_trigger_operator": "<=",
           "trigger_basis": "classifier-transition-v1", "trigger_quality": "PARTIAL",
           "trigger_reason": "down_transition_not_verified"}
    compact = subject.compact_public_trend_map_report({"rows": [row]})
    assert {key: compact["rows"][0][key] for key in (
        "up_trigger", "down_trigger", "up_trigger_operator", "down_trigger_operator",
        "trigger_basis", "trigger_quality", "trigger_reason")} == {
        "up_trigger": 150.0, "down_trigger": None, "up_trigger_operator": ">=",
        "down_trigger_operator": "<=", "trigger_basis": "classifier-transition-v1",
        "trigger_quality": "PARTIAL", "trigger_reason": "down_transition_not_verified",
    }


def test_scale_smoke_237_synthetic_rows_is_bounded_and_batch_only(monkeypatch):
    """SCALE SMOKE ONLY: synthetic 237-row producer path, not market evidence."""
    symbols = [f"S{i:03d}" for i in range(237)]
    frames = {symbol: bars(60) for symbol in symbols}

    class ScaleSmokeAdapter:
        db_reads = 0

        def load_daily_pit_batch(self, conn, requested_symbols, as_of):
            assert requested_symbols == symbols
            return {symbol: (frames[symbol], as_of, {
                "quality_scan": "scale_smoke_synthetic",
                "invalid_count": 0,
                "quality_established": True,
                "full_history_claim": False,
            }) for symbol in requested_symbols}

    original = subject.build_technical_indicators
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(subject, "build_technical_indicators", counted)
    started = time.perf_counter()
    report = subject._build_shadow_report(
        ScaleSmokeAdapter(), object(), symbols, {"universe_filter": subject.UNIVERSE}, "2026-09-11")
    elapsed = time.perf_counter() - started

    assert elapsed < 20.0
    assert calls == len(symbols)
    assert report["status"] == subject.PRODUCTION_READ_ONLY
    assert len(report["rows"]) == len(symbols)
    assert ScaleSmokeAdapter.db_reads == 0


def test_retrieval_cap_fails_closed_when_it_cannot_establish_full_valid_window():
    result = subject.evaluate_symbol("AAA", bars(subject.RETRIEVAL_CAP), "2026-09-11", subject.RETRIEVAL_CAP)
    result_frame = bars(subject.RETRIEVAL_CAP)
    for row in result_frame[:31]:
        row["low"] = "bad"
    blocked = subject.evaluate_symbol("AAA", result_frame, "2026-09-11", subject.RETRIEVAL_CAP)
    assert blocked["status"] == "DATA_BLOCKED"
    assert blocked["retrieval_cap_reached"] is True
    assert blocked["bars_used"] == 0
    assert result["bars_used"] == 0
    assert result["data_quality_status"] == "DATA_BLOCKED"


def test_cap_hit_with_no_selected_invalid_rows_is_not_available():
    frame = bars(subject.RETRIEVAL_CAP + 1)
    for i, row in enumerate(frame):
        row["date"] = f"2025-{i // 28 + 1:02d}-{i % 28 + 1:02d}"
    frame[0]["low"] = "bad"
    result = subject.evaluate_symbol("BTS", frame, "2026-09-11")
    assert result["status"] == "DATA_BLOCKED"
    assert result["data_quality_status"] == "DATA_BLOCKED"
    assert result["invalid_row_count"] == 0
    assert result["retrieval_cap"] == subject.RETRIEVAL_CAP
    assert result["cap"] == subject.RETRIEVAL_CAP
    assert result["cap_reached"] is True
    assert result["retrieval_cap_reached"] is True
    assert "cannot establish the required valid/invalid" in result["note"]
    assert "No fallback or full-history retrieval used" in result["note"]


def test_cap_hit_with_established_zero_invalid_quality_is_available():
    frame = bars(subject.RETRIEVAL_CAP + 1)
    for i, row in enumerate(frame):
        row["date"] = f"2025-{i // 28 + 1:02d}-{i % 28 + 1:02d}"
    result = subject.evaluate_symbol(
        "VALID_LONG_HISTORY", frame, "2026-09-11",
        quality_metadata={"quality_scan": "filtered_daily_source", "invalid_count": 0,
                          "quality_established": True, "full_history_claim": False},
    )
    assert result["status"] == "AVAILABLE"
    assert result["cap_reached"] is True
    assert result["quality_established"] is True
    assert result["invalid_count"] == 0
    assert result["full_history_claim"] is False


def test_invalid_row_outside_selected_cap_does_not_block_selected_window():
    frame = bars(subject.RETRIEVAL_CAP + 1)
    for i, row in enumerate(frame):
        row["date"] = f"2025-{i // 28 + 1:02d}-{i % 28 + 1:02d}"
    frame[0]["low"] = "bad"  # older than the selected newest-430 window
    result = subject.evaluate_symbol(
        "BTS", frame, "2026-09-11",
        quality_metadata={"quality_scan": "selected_window_only", "invalid_count": 0,
                          "quality_established": True, "full_history_claim": False},
    )
    assert result["status"] == "AVAILABLE"
    assert result["data_quality_status"] == "AVAILABLE"
    assert result["invalid_count"] == 0
    assert result["invalid_row_count"] == 0


def test_invalid_row_inside_selected_cap_still_blocks_classification():
    frame = bars(subject.RETRIEVAL_CAP)
    frame[-1]["low"] = "bad"  # within the selected newest-430 window
    result = subject.evaluate_symbol("CPN", frame, "2026-09-11")
    assert result["status"] == "DATA_BLOCKED"
    assert result["data_quality_status"] == "INVALID_DATA"
    assert result["invalid_count"] == 1
    assert result["invalid_row_count"] == 1


def test_cap_hit_keeps_selected_invalid_rows_visible():
    frame = bars(subject.RETRIEVAL_CAP)
    frame[-1]["low"] = "bad"
    result = subject.evaluate_symbol("CPN", frame, "2026-09-11")
    assert result["status"] == "DATA_BLOCKED"
    assert result["data_quality_status"] == "INVALID_DATA"
    assert result["invalid_row_count"] == 1
    assert result["retrieval_cap_reached"] is True
    assert "invalid filtered-source row" in result["note"]


def test_evaluator_enforces_cap_for_oversized_caller_frame_and_records_selection():
    frame = [{"date": f"2025-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}", "open": 99 + i,
              "high": 101 + i, "low": 98 + i, "close": 100 + i, "volume": 1000}
             for i in range(500)]
    result = subject.evaluate_symbol("AAA", frame, "2026-09-11", retrieval_cap=999)
    assert result["retrieval_cap"] == subject.RETRIEVAL_CAP
    assert result["bars_retrieved"] == subject.RETRIEVAL_CAP
    assert result["bars_used"] == 0
    assert result["status"] == "DATA_BLOCKED"
    assert result["retrieval_cap_reached"] is True
    assert result["retrieval_selection"] == {
        "requested_rows": 500, "selected_rows": subject.RETRIEVAL_CAP,
        "retrieval_cap": subject.RETRIEVAL_CAP, "cap_applied": True,
        "method": "newest_daily_rows", "tie_break": "input_order",
    }


def test_report_policy_has_explicit_quote_representation_revision():
    result = subject._policy()
    assert subject.REPORT_VERSION == "daily-trend-map-shadow-v2-quotes"
    assert subject.REPRESENTATION_REVISION == "quote-envelope-v2"
    assert result["report"] == subject.REPORT_VERSION
    assert result["representation_revision"] == subject.REPRESENTATION_REVISION


def test_report_uses_canonical_production_read_only_envelope():
    class Adapter:
        def resolve_universe(self, conn, value):
            return ["AAA"], {"universe_filter": value}
        def _exec_select(self, conn, sql, params=None):
            return [("2026-09-11",)], ["max_date"]
        def load_daily_pit(self, conn, symbol, as_of):
            return bars(75), as_of
    report = subject.build_shadow_report(Adapter(), object())
    assert report["status"] == subject.PRODUCTION_READ_ONLY
    assert report["research_only"] is False
    assert report["actionability"] == "NONE"


def test_explicit_error_states():
    no_data = subject.evaluate_symbol("A", [], "2026-09-11")
    assert no_data["status"] == "DATA_BLOCKED"
    assert no_data["data_quality_status"] == "NO_DATA"
    assert no_data["quote"]["availability"] == "NOT_VERIFIED"
    short = subject.evaluate_symbol("B", bars(2), "2026-09-11")
    assert short["status"] == "DATA_BLOCKED"
    assert short["data_quality_status"] == "INSUFFICIENT_HISTORY"
    invalid = subject.evaluate_symbol("C", bars(31, invalid=True), "2026-09-11")
    assert invalid["status"] == "DATA_BLOCKED"
    assert invalid["data_quality_status"] == "INVALID_DATA"
    assert invalid["quote"]["availability"] == "NOT_VERIFIED"


def test_quote_is_daily_close_delta_with_positive_negative_and_zero_values():
    for current, previous, expected_amount, expected_pct in ((110, 100, 10, 10), (90, 100, -10, -10), (100, 100, 0, 0)):
        frame = bars(45)
        frame[-2]["close"], frame[-1]["close"] = previous, current
        for row in frame[-2:]:
            row["open"], row["high"], row["low"] = row["close"] - 1, row["close"] + 1, row["close"] - 2
        result = subject.evaluate_symbol("AAA", frame, "2026-09-11")
        quote = result["quote"]
        assert quote["price"] == current
        assert quote["change_amount"] == expected_amount
        assert quote["change_pct"] == expected_pct
        assert quote["change_basis"] == "previous_daily_close"
        assert quote["provenance"]["timeframe"] == "1D"


def test_quote_preserves_price_when_previous_daily_close_is_unavailable():
    frame = [bars(1)[0]]
    result = subject.evaluate_symbol("AAA", frame, "2026-09-11")
    assert result["quote"]["price"] == frame[-1]["close"]
    assert result["quote"]["change_amount"] is None
    assert result["quote"]["change_pct"] is None
    assert result["quote"]["change_availability"] == "NOT_VERIFIED"
    assert result["quote"]["change_basis"] == "NOT_VERIFIED"


def _published_quote_report():
    return {"rows": [{"symbol": "AAA", "main_trend": {"main_trend": 2},
                      "quote": {"price": 100, "change_amount": 1,
                                "change_pct": 1, "source": "price_data",
                                "provisional": False}}]}


def test_intraday_quote_overlay_uses_latest_completed_bar_and_previous_daily_close(monkeypatch):
    class Adapter:
        def load_intraday_quotes(self, conn, symbols, now):
            assert symbols == ["AAA"]
            return {"AAA": {"ts": "2026-09-11T09:00:00+00:00", "close": 110,
                            "daily_close": 100, "daily_date": "2026-09-10",
                            "daily_source": "price_data"}}

    report = _published_quote_report()
    subject.overlay_intraday_quotes(
        report, adapter=Adapter(), conn=object(),
        now=datetime(2026, 9, 11, 9, 30, tzinfo=timezone.utc),
    )
    quote = report["rows"][0]["quote"]
    assert quote["price"] == 110
    assert quote["change_amount"] == 10
    assert quote["change_pct"] == 10
    assert quote["source"] == "intraday_price_data"
    assert quote["timeframe"] == "60m"
    assert quote["provisional"] is True
    assert quote["as_of"] == "2026-09-11T09:00:00+00:00"
    assert quote["change_basis"] == "previous_daily_close"
    assert quote["provenance"]["daily_baseline"] == {
        "source": "price_data", "timeframe": "1D", "date": "2026-09-10"
    }
    assert quote["eod_fallback"]["source"] == "price_data"


@pytest.mark.parametrize("quote_row", [
    {"ts": "2026-09-11T10:00:00+00:00", "close": 110, "daily_close": 100,
     "daily_date": "2026-09-10", "daily_source": "price_data"},
    {"ts": "2026-09-10T09:00:00+00:00", "close": 110, "daily_close": 100,
     "daily_date": "2026-09-09", "daily_source": "price_data"},
    {"ts": "2026-09-11T09:00:00+00:00", "close": "bad", "daily_close": 100,
     "daily_date": "2026-09-10", "daily_source": "price_data"},
    {"ts": "2026-09-11T09:00:00+00:00", "close": 110, "daily_close": 0,
     "daily_date": "2026-09-10", "daily_source": "price_data"},
])
def test_intraday_quote_overlay_fails_closed_to_immutable_eod_quote(quote_row):
    class Adapter:
        def load_intraday_quotes(self, conn, symbols, now):
            return {"AAA": quote_row}

    report = _published_quote_report()
    original = dict(report["rows"][0]["quote"])
    subject.overlay_intraday_quotes(
        report, adapter=Adapter(), conn=object(),
        now=datetime(2026, 9, 11, 9, 30, tzinfo=timezone.utc),
    )
    assert report["rows"][0]["quote"] == original
    assert report["rows"][0]["main_trend"] == {"main_trend": 2}


def test_intraday_overlay_does_not_change_scan_or_classifier_fields():
    class Adapter:
        def load_intraday_quotes(self, conn, symbols, now):
            return {"AAA": {"ts": "2026-09-11T09:00:00+00:00", "close": 110,
                            "daily_close": 100, "daily_date": "2026-09-10",
                            "daily_source": "derived_daily_price_data"}}

    report = _published_quote_report()
    report["rows"][0].update({"status": "AVAILABLE", "machine_lane": "REVIEW_NOW",
                               "classifier_status": "AVAILABLE", "data_quality_status": "AVAILABLE"})
    invariant = {key: report["rows"][0][key] for key in
                 ("main_trend", "status", "machine_lane", "classifier_status", "data_quality_status")}
    subject.overlay_intraday_quotes(
        report, adapter=Adapter(), conn=object(),
        now=datetime(2026, 9, 11, 9, 30, tzinfo=timezone.utc),
    )
    assert {key: report["rows"][0][key] for key in invariant} == invariant
    assert report["rows"][0]["quote"]["provenance"]["daily_baseline"]["source"] == "derived_daily_price_data"


def test_published_overlay_reads_artifact_without_request_database(monkeypatch):
    artifact = {"generated_at": "2026-09-15T09:00:00+00:00", "quotes": [{
        "symbol": "AAA", "status": "UNAVAILABLE"}]}
    monkeypatch.setattr("intraday_quote_read_model.read_current", lambda **_: artifact)
    monkeypatch.setattr(subject.BackendDailyAdapter, "_get_conn",
                        lambda *_: (_ for _ in ()).throw(AssertionError("request DB access")))
    report = _published_quote_report()
    subject.overlay_intraday_quotes(report, now=datetime(2026, 9, 15, 9, 30, tzinfo=timezone.utc))
    assert report["rows"][0]["quote"]["source"] == "price_data"
    assert report["intraday_quote_overlay"]["query_mode"] == "PREBUILT_READ_MODEL"


def _trigger_report(*, up=110, down=90, price=100):
    return {
        "status": subject.PRODUCTION_READ_ONLY,
        "research_only": False,
        "actionability": "NONE",
        "snapshot": {"kind": "current", "as_of": "2026-09-17", "artifact_id": "eod-1"},
        "rows": [{
            "symbol": "AAA", "as_of": "2026-09-17", "status": "AVAILABLE",
            "main_trend": {"main_trend": 2, "up_trigger": up, "down_trigger": down,
                            "up_trigger_operator": ">=", "down_trigger_operator": "<=",
                            "trigger_basis": "supplied_classifier_evidence"},
            "quote": {"price": 100, "provisional": False},
        }],
    }, {"generated_at": "2026-09-18T03:00:00+00:00", "quotes": [{
        "symbol": "AAA", "status": "AVAILABLE", "price": price,
        "latest_completed_60m": "2026-09-18T03:00:00+00:00",
    }]}


@pytest.mark.parametrize("price, expected", [
    (110, "UP TRIGGER REACHED"), (111, "UP TRIGGER REACHED"),
    (90, "DOWN TRIGGER REACHED"), (89, "DOWN TRIGGER REACHED"),
    (100, "NO MARKER"),
])
def test_intraday_trigger_marker_boundaries_are_inclusive_and_provisional(price, expected):
    report, artifact = _trigger_report(price=price)
    subject.project_intraday_trigger_markers(report, artifact=artifact)
    marker = report["rows"][0]["trigger_marker"]
    assert marker["label"] == expected
    assert marker["provisional"] is True
    assert marker["eod_close_required"] is True
    assert report["rows"][0]["main_trend"]["main_trend"] == 2


@pytest.mark.parametrize("artifact, reason", [
    (None, "quote_unavailable"),
    ({"generated_at": "2026-09-18T03:00:00+00:00", "quotes": [{"symbol": "AAA", "status": "UNAVAILABLE"}]}, "quote_unavailable"),
])
def test_intraday_trigger_marker_fails_closed_for_missing_quote(artifact, reason):
    report, _ = _trigger_report()
    subject.project_intraday_trigger_markers(report, artifact=artifact)
    marker = report["rows"][0]["trigger_marker"]
    assert marker["status"] == "NOT_VERIFIED"
    assert marker["reason"] == reason
    assert marker["provenance"]["source"] == "intraday_quote_read_model"


def test_intraday_trigger_marker_fails_closed_when_validated_quote_model_is_stale(monkeypatch):
    report, _ = _trigger_report()

    def stale_read_current(**_):
        raise ValueError("intraday quote artifact is stale")

    monkeypatch.setattr("intraday_quote_read_model.read_current", stale_read_current)
    subject.overlay_intraday_quotes(report)
    assert report["rows"][0]["trigger_marker"]["status"] == "NOT_VERIFIED"
    assert report["rows"][0]["trigger_marker"]["reason"] == "quote_read_model_unavailable"
    assert report["intraday_trigger_projection"]["query_mode"] == "PREBUILT_READ_MODEL"


@pytest.mark.parametrize("up, down", [(None, 90), (110, None), ("bad", 90), (110, float("nan"))])
def test_intraday_trigger_marker_fails_closed_for_missing_or_invalid_trigger(up, down):
    report, artifact = _trigger_report(up=up, down=down, price=100)
    subject.project_intraday_trigger_markers(report, artifact=artifact)
    marker = report["rows"][0]["trigger_marker"]
    assert marker["status"] == "NOT_VERIFIED"
    assert marker["reason"] == "authoritative_trigger_fields_unavailable"
    assert report["rows"][0]["main_trend"]["up_trigger"] == up


def test_intraday_trigger_marker_never_overlays_historical_snapshot():
    report, artifact = _trigger_report(price=110)
    report["snapshot"]["kind"] = "historical"
    subject.project_intraday_trigger_markers(report, artifact=artifact)
    marker = report["rows"][0]["trigger_marker"]
    assert marker["status"] == "NOT_VERIFIED"
    assert marker["reason"] == "historical_snapshot_no_intraday_overlay"
    assert marker["provenance"]["quote_applied"] is False


def test_intraday_trigger_marker_preserves_non_actionable_contract_and_eod_identity():
    report, artifact = _trigger_report(price=110)
    before = {key: report[key] for key in ("status", "research_only", "actionability")}
    row_before = {key: report["rows"][0][key] for key in ("as_of", "main_trend", "quote")}
    subject.project_intraday_trigger_markers(report, artifact=artifact)
    assert {key: report[key] for key in before} == before
    assert {key: report["rows"][0][key] for key in row_before} == row_before


def test_valid_classifier_row_is_available_and_has_diagnostic_trace():
    result = subject.evaluate_symbol("AAA", bars(75), "2026-09-11")
    assert result["status"] == "AVAILABLE"
    assert result["classifier_status"] == "AVAILABLE"
    assert result["diagnostic_trace"]["classification"]["machine_lane"] == result["machine_lane"]


def test_compact_public_projection_preserves_envelope_rows_and_display_evidence():
    row = subject.evaluate_symbol("AAA", bars(75), "2026-09-11")
    row["provenance"] = {
        "source": "price_data+derived_daily_price_data", "timeframe": "1D",
        "latest_returned_date": "2026-09-11", "selected_daily_lineage": [
            {"source": "derived_daily_price_data", "source_timeframe": "60m",
             "source_run_id": "run-1", "source_bar_count": 8,
             "derivation_method": subject.DERIVED_DAILY_METHOD},
            {"source": "derived_daily_price_data", "source_timeframe": "60m",
             "source_run_id": "run-1", "source_bar_count": 8,
             "derivation_method": subject.DERIVED_DAILY_METHOD},
        ],
    }
    report = {"status": subject.PRODUCTION_READ_ONLY, "as_of": "2026-09-11",
              "freshness": {"status": "FRESH"}, "counts": {"declared": 1},
              "quality": {"verified": True}, "universe": {"declared_count": 1},
              "policy": {"hash": "policy"}, "provenance": {"source": "artifact"},
              "read_path": {"validated_every_request": True},
              "rows": [row]}

    compact = subject.compact_public_trend_map_report(report)

    assert compact is not report
    assert compact["rows"] is not report["rows"]
    assert compact["rows"][0]["symbol"] == "AAA"
    assert compact["rows"][0]["main_trend"] == {
        key: row["main_trend"][key]
        for key in ("main_trend", "evidence_quality", "main_trend_display",
                    "source_timeframe", "as_of", "policy_version")}
    assert compact["rows"][0]["quote"] == row["quote"]
    assert compact["rows"][0]["provenance"] == {
        "source": "price_data+derived_daily_price_data", "timeframe": "1D",
        "latest_returned_date": "2026-09-11", "no_lookahead": True,
        "lineage_summary": {
            "source": "price_data+derived_daily_price_data", "derived_row_count": 2,
            "source_timeframe": "60m", "source_bar_count": 8,
            "derivation_method": subject.DERIVED_DAILY_METHOD, "source_run_id": "run-1",
        },
    }
    assert set(compact["rows"][0]) == {
        "symbol", "as_of", "status", "data_quality_status", "classifier_status",
        "confidence", "machine_lane", "broad_state", "main_trend", "quote",
        "provenance", "note", "trend_changed_date", "trend_duration_sessions",
        "up_trigger", "down_trigger", "up_trigger_operator", "down_trigger_operator",
        "trigger_basis", "trigger_quality", "trigger_reason",
    }
    assert "diagnostic_trace" not in compact["rows"][0]
    assert "evidence" not in compact["rows"][0]
    assert "retrieval_selection" not in compact["rows"][0]
    assert "selected_daily_lineage" not in json.dumps(compact["rows"][0])
    assert len(json.dumps(compact["rows"][0], separators=(",", ":"))) < 5000
    assert compact["universe"] == report["universe"]
    assert compact["counts"] == report["counts"]
    assert compact["read_path"] == report["read_path"]
    assert "diagnostic_trace" in row


def test_compact_public_projection_preserves_history_and_trigger_fields_from_row():
    row = {"symbol": "AAA", "main_trend": {"main_trend": 2},
           "trend_changed_date": "2026-09-01", "trend_duration_sessions": 4,
           "up_trigger": 110.5, "down_trigger": 90.25,
           "trigger_basis": "supplied_classifier_evidence"}

    compact = subject.compact_public_trend_map_report({"rows": [row]})

    assert {key: compact["rows"][0][key] for key in (
        "trend_changed_date", "trend_duration_sessions", "up_trigger",
        "down_trigger", "trigger_basis")} == {
        "trend_changed_date": "2026-09-01", "trend_duration_sessions": 4,
        "up_trigger": 110.5, "down_trigger": 90.25,
        "trigger_basis": "supplied_classifier_evidence",
    }


def test_compact_public_projection_promotes_nested_main_trend_history_and_triggers():
    row = {"symbol": "AAA", "main_trend": {
        "main_trend": 2, "trend_changed_date": "2026-09-02",
        "trend_duration_sessions": 2, "up_trigger": 111.0,
        "down_trigger": 89.0, "trigger_basis": "classifier_evidence",
    }}

    compact = subject.compact_public_trend_map_report({"rows": [row]})

    assert {key: compact["rows"][0][key] for key in (
        "trend_changed_date", "trend_duration_sessions", "up_trigger",
        "down_trigger", "trigger_basis")} == {
        "trend_changed_date": "2026-09-02", "trend_duration_sessions": 2,
        "up_trigger": 111.0, "down_trigger": 89.0,
        "trigger_basis": "classifier_evidence",
    }


def test_compact_public_projection_keeps_missing_and_explicit_not_verified_fields():
    row = {"symbol": "AAA", "main_trend": {
        "trend_changed_date": None, "trend_duration_sessions": None,
        "up_trigger": None, "down_trigger": None,
        "trigger_basis": "NOT_VERIFIED", "trigger_reason": "missing_evidence",
    }}

    compact = subject.compact_public_trend_map_report({"rows": [row]})

    assert {key: compact["rows"][0][key] for key in (
        "trend_changed_date", "trend_duration_sessions", "up_trigger",
        "down_trigger", "trigger_basis")} == {
        "trend_changed_date": None, "trend_duration_sessions": None,
        "up_trigger": None, "down_trigger": None,
        "trigger_basis": "NOT_VERIFIED",
    }


def test_compact_public_projection_uses_nested_legacy_value_when_top_level_is_unset():
    row = {"symbol": "AAA", "trend_duration_sessions": None,
           "main_trend": {"trend_duration_sessions": 9}}

    compact = subject.compact_public_trend_map_report({"rows": [row]})

    assert compact["rows"][0]["trend_duration_sessions"] == 9


def test_api_route_serializes_compact_public_projection(monkeypatch):
    class Handler:
        def __init__(self):
            self.body = bytearray()
            self.wfile = self
        def send_response(self, status):
            self.status = status
        def send_header(self, key, value):
            pass
        def end_headers(self):
            pass
        def write(self, body):
            self.body.extend(body)

    row = subject.evaluate_symbol("AAA", bars(75), "2026-09-11")
    row["provenance"] = {"source": "price_data", "timeframe": "1D",
                         "latest_returned_date": "2026-09-11",
                         "selected_daily_lineage": []}
    monkeypatch.setattr(subject, "build_shadow_report", lambda: {
        "status": subject.PRODUCTION_READ_ONLY, "research_only": False,
        "actionability": "NONE", "rows": [row],
    })

    handler = Handler()
    assert subject.handle_shadow_trend_map_api("/api/trend-map", handler)
    payload = json.loads(bytes(handler.body))
    public_row = payload["rows"][0]
    assert public_row["main_trend"]["main_trend_display"] == row["main_trend"]["main_trend_display"]
    assert public_row["provenance"]["no_lookahead"] is True
    assert "diagnostic_trace" not in public_row
    assert "evidence" not in public_row
    assert "retrieval_selection" not in public_row


def test_report_preserves_canonical_universe_and_as_of():
    class Adapter:
        def resolve_universe(self, conn, value):
            assert value == "marginable_long"
            return ["AAA", "BBB"], {"universe_filter": value, "eligible_count": 2}
        def _exec_select(self, conn, sql, params=None):
            assert sql.startswith("SELECT")
            return [("2026-09-11",)], ["max_date"]
        def load_daily_pit(self, conn, symbol, as_of):
            return (bars(75) if symbol == "AAA" else []), as_of
    report = subject.build_shadow_report(Adapter(), object())
    assert report["as_of"] == "2026-09-11"
    assert [row["symbol"] for row in report["rows"]] == ["AAA", "BBB"]
    assert report["universe"]["scope"] == "marginable_long"
    assert report["policy"]["review_window"] == "current_history_bounded"
    assert report["policy"]["min_valid_bars"] == 30
    assert report["policy"]["max_valid_bars"] == 400
    assert report["policy"]["prior_10d_low"]["prior_bars"] == 10
    assert report["provenance"]["source"] == "price_data+derived_daily_price_data"
    assert report["provenance"]["tables"] == ["price_data", "derived_daily_price_data"]
    assert report["provenance"]["timeframe"] == "1D"
    assert report["provenance"]["query_mode"] == "SELECT_ONLY"
    assert report["provenance"]["point_in_time_filter"] == "date <= as_of"
    assert report["status_by_symbol"] == {"AAA": "AVAILABLE", "BBB": "DATA_BLOCKED"}


def test_report_keeps_every_declared_symbol_and_all_data_quality_reasons():
    class Adapter:
        def resolve_universe(self, conn, value):
            return ["AVAILABLE", "NO_DATA", "INVALID", "SHORT"], {"universe_filter": value}
        def _exec_select(self, conn, sql, params=None):
            return [("2026-09-11",)], ["max_date"]
        def load_daily_pit(self, conn, symbol, as_of):
            if symbol == "AVAILABLE":
                return bars(75), as_of
            if symbol == "INVALID":
                invalid_rows = bars(2)
                for row in invalid_rows:
                    row["low"] = "bad"
                return invalid_rows, as_of
            if symbol == "SHORT":
                return bars(2), as_of
            return [], None

    report = subject.build_shadow_report(Adapter(), object())
    assert set(report["status_by_symbol"]) == {"AVAILABLE", "NO_DATA", "INVALID", "SHORT"}
    assert report["summary"] == {"DATA_BLOCKED": 3, "AVAILABLE": 1}
    assert report["data_quality_summary"]["AVAILABLE"] == 1
    assert report["data_quality_summary"]["NO_DATA"] == 1
    assert report["data_quality_summary"]["INVALID_DATA"] == 1
    assert report["data_quality_summary"]["INSUFFICIENT_HISTORY"] == 1


def test_template_has_main_trend_accordion_filter_drawer_chart_and_shadow_markers():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    shared = Path(__file__).with_name("frontend") / "shared-drawer.js"
    combined = html + shared.read_text()
    for marker in ("<table", "<th>Price</th>", "<th>Change</th>", "<th>% Change</th>", "<th>Main Trend</th>", "quoteValue", "quoteChangePct", "change_amount", "change_pct", "Search symbol", "id=\"main-trend\"", "All Main Trends", "Main Trend 1", "Main Trend 2", "Main Trend 3", "Main Trend 4", "mainTrendGroups", "class=\"trend-section\"", "class=\"trend-toggle\"", "aria-expanded=\"false\"", "data-trend-section", "window.SignalixSharedDrawer.openSharedDrawer({", "lane:trend", "trend:trend", "source:\"trend-map\"", "actionability:\"NONE\"", "renderedRows", "/api/trend-map", "/api/chart-db/", 'data-timeframe="1D"', "Chart loading…", "Chart data unavailable", "DATA_BLOCKED", "drawChart", "chartRequestSeq", "mainTrendValue", "row.main_trend", "evidence.evidence_quality", "main_trend_display", "1++", "1+", "1", "2", "3", "3-", "3--", "4", "shadowMainTrendDisplay", "shadowMainTrend", "Main Trend ", "shadow ? shadowMainTrend", "[1,2,3,4].includes", 'return "Not verified"', 'id=\"theme-toggle\"', "signalix-theme", "theme-light", "localStorage", "event.target.closest"):
        assert marker in combined
    for removed in ("Daily lane", "machine_lane", "Machine lane", "broad_state", "id=\"lane\"", "id=\"broad-state\"", "All lanes", "All broad states"):
        assert removed not in html
    main_trend_renderer = html.split("function mainTrendValue", 1)[1].split("function render", 1)[0]
    assert "machine_lane" not in main_trend_renderer
    assert "broad_state" not in main_trend_renderer
    assert 'id="status"' not in html
    assert '<th>Status</th>' not in html
    assert '<th>Data quality</th>' not in html
    assert 'r.data_quality_status' not in html
    assert 'r.status===s' not in html


def test_trend_map_accordion_is_closed_single_open_and_defers_symbol_rows_until_open():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    assert "Main Trend shows the Daily direction. Open a group to see its evidence." in html
    assert 'aria-expanded="false"' in html
    assert 'aria-label="Open evidence"' in html
    assert '"Close evidence"' in html
    assert 'class="trend-toggle__action">Open evidence</span>' in html
    assert 'button.setAttribute("aria-label",expanded?"Close evidence":"Open evidence")' in html
    assert 'action.textContent=expanded?"Close evidence":"Open evidence"' in html
    assert 'panel.hidden=true' in html
    assert 'panel.hidden=true;panel.innerHTML=""' in html
    assert 'if(openTrend&&openTrend!==trend)closeOpenTrend()' in html
    assert "panel.innerHTML='<table>" in html
    assert 'document.querySelector("#rows").addEventListener("click"' in html


def test_trend_map_first_screen_uses_plain_language_and_keeps_raw_audit_details_lower_down():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    assert 'Data date <strong id="as-of">' in html
    assert 'Status <strong id="freshness">' in html
    assert 'Scope <strong id="scope">Thai listed universe</strong>' in html
    assert 'Showing <strong id="shown-count">' in html
    assert 'Total <strong id="declared-count">' in html
    assert 'Daily direction is classified from end-of-day data.' in html
    assert 'The 60-minute price is for display only and does not change the Daily classification.' in html
    assert 'The classification date and displayed price time may differ.' in html
    assert 'function displayFreshness(status){return status==="FRESH"?"Current"' in html
    assert 'document.querySelector("#freshness").textContent=displayFreshness((report.freshness||{}).status)' in html
    assert '<details class="audit-details"><summary>Technical details</summary>' in html
    assert 'id="policy-id"' in html
    first_screen = html.split('<details class="audit-details"', 1)[0]
    assert 'main_trend_classifier' not in first_screen
    assert 'trend-map-v1' not in first_screen
    summary_markup = html.split('<p id="summary"', 1)[1].split('</p>', 1)[0]
    assert 'policy' not in summary_markup.lower()


def test_trend_map_theme_defaults_dark_persists_and_exposes_light_mode():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    assert 'var initialTheme="dark"' in html
    assert 'localStorage.getItem("signalix-theme")' in html
    assert 'localStorage.setItem("signalix-theme",light?"light":"dark")' in html
    assert 'body.trend-page.theme-light' in html
    assert '--surface:#fffdf8' in html
    assert '--text:#1d2733' in html
    assert '--border:#d8d0c2' in html
    assert 'body.trend-page.theme-light{background:#f4f1ea;color:#1d2733}' in html
    assert '.trend-page.theme-light .drawer-panel{--bg:#f4f1ea' in html
    assert 'aria-pressed="false"' in html


def test_trend_map_lazy_drawer_is_single_flight_and_opens_after_script_load():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text(encoding="utf-8")
    assert '<script src="/shared-drawer.js"></script>' not in html
    inline = html.split("<script>", 1)[1].split("</script>", 1)[0]
    harness = r'''
const vm = require("vm");
function Element(id) {
  this.id = id; this.value = ""; this.hidden = false; this.textContent = "";
  this.innerHTML = ""; this.dataset = {}; this.onclick = null; this.onkeydown = null;
  this.classList = {contains: function () { return true; }, toggle: function () {}};
  this.attributes = {};
  this.setAttribute = function (name, value) { this.attributes[name] = String(value); };
  this.getAttribute = function (name) { return this.attributes[name] || null; };
  this.addEventListener = function (name, handler) { this["on" + name] = handler; };
  this.querySelector = function () { return null; };
  this.querySelectorAll = function () { return []; };
  this.closest = function () { return this; };
}
function Button(section) {
  const button = new Element("trend-toggle");
  button.section = section;
  button.querySelector = function (selector) { return selector === ".trend-toggle__action" ? button.action : null; };
  button.closest = function (selector) { return selector === ".trend-toggle" ? button : selector === ".trend-section" ? section : null; };
  button.action = new Element("trend-toggle__action");
  return button;
}
function Panel(section) {
  const panel = new Element("trend-panel");
  panel.section = section;
  Object.defineProperty(panel, "innerHTML", {
    get: function () { return this._html || ""; },
    set: function (value) {
      this._html = value;
      this.rendered = [];
      for (const match of value.matchAll(/data-symbol="([^"]+)"/g)) {
        const row = new Element("row");
        row.dataset.symbol = match[1];
        row.getAttribute = function (name) { return name === "data-symbol" ? this.dataset.symbol : null; };
        row.closest = function (selector) { return selector === "tr[data-symbol]" ? row : null; };
        this.rendered.push(row);
      }
    }
  });
  return panel;
}
function Section(trend) {
  const section = new Element("trend-section");
  section.trend = trend;
  section.attributes["data-trend-section"] = trend;
  section.button = Button(section);
  section.panel = Panel(section);
  section.panel.hidden = true;
  section.querySelector = function (selector) {
    return selector === ".trend-toggle" ? this.button : selector === ".trend-panel" ? this.panel : null;
  };
  section.closest = function (selector) { return selector === ".trend-section" ? section : null; };
  return section;
}
const elements = {};
["search", "main-trend", "summary", "error", "retry", "reload", "rows", "theme-toggle", "shown-count", "declared-count", "as-of", "freshness", "report-status", "report-freshness", "policy-id", "snapshot-banner"].forEach(function (id) {
  elements[id] = new Element(id);
});
Object.defineProperty(elements.rows, "innerHTML", {
  get: function () { return this._html || ""; },
  set: function (value) {
    this._html = value;
    this.sections = [];
    for (const match of value.matchAll(/data-trend-section="([^"]+)"/g)) this.sections.push(Section(match[1]));
  }
});
elements.rows.querySelectorAll = function (selector) { return selector === ".trend-section" ? this.sections : []; };
const scripts = [];
const document = {
  body: {classList: {toggle: function () {}}},
  head: {appendChild: function (script) { scripts.push(script); }},
  querySelector: function (selector) {
    if (selector[0] === "#") return elements[selector.slice(1)] || null;
    const trend = selector.match(/^\[data-trend-section="([^"]+)"\]$/);
    return trend && elements.rows.sections.find(function (section) { return section.trend === trend[1]; }) || null;
  },
  querySelectorAll: function (selector) { return selector === "#rows tr[data-symbol]" ? [].concat.apply([], elements.rows.sections.map(function (section) { return section.panel.rendered || []; })) : []; },
  createElement: function () { return {}; }
};
let opens = [];
const responseData = {
  status: "PRODUCTION_READ_ONLY", research_only: false, actionability: "NONE",
  verification_status: "VERIFIED", freshness: {status: "FRESH"}, as_of: "2026-09-11",
  universe: {declared_count: 1}, policy: {classifier: "trend-map-v1"},
  rows: [
    {symbol: "AAA", machine_lane: "REVIEW_NOW", broad_state: "UPTREND", classifier_status: "UPTREND", main_trend: {main_trend: 2, evidence_quality: "FULL"}, quote: {price: 10, change_amount: 1, change_pct: 10}},
    {symbol: "BBB", machine_lane: "AVOID", broad_state: "DOWNTREND", main_trend: {main_trend: 3, evidence_quality: "FULL"}, quote: {price: 11, change_amount: -1, change_pct: -9}},
    {symbol: "CCC", machine_lane: "REVIEW_NOW", broad_state: "UPTREND", quote: {price: 12, change_amount: 0, change_pct: 0}}
  ]
};
const context = {
  window: {}, document: document, localStorage: {getItem: function () { return null; }, setItem: function () {}},
  fetch: function () { return Promise.resolve({ok: true, json: function () { return Promise.resolve(responseData); }}); },
  console: console, Promise: Promise, encodeURIComponent: encodeURIComponent
};
vm.runInNewContext(%s, context);
setImmediate(function () {
  if (elements.rows.sections.length !== 3 || elements.rows.sections.some(function (section) { return !section.panel.hidden && section.panel.innerHTML; })) process.exit(3);
  const first = elements.rows.sections[0], second = elements.rows.sections[1];
  elements.rows.onclick({target: first.button});
  if (first.panel.hidden || first.panel.rendered.length !== 1 || first.button.attributes["aria-expanded"] !== "true") process.exit(4);
  elements.rows.onclick({target: first.button});
  if (!first.panel.hidden || first.panel.innerHTML !== "") process.exit(5);
  elements.rows.onclick({target: first.button});
  elements.rows.onclick({target: second.button});
  if (first.panel.hidden !== true || first.panel.innerHTML !== "" || second.panel.hidden || second.panel.rendered.length !== 1) process.exit(6);
  const row = second.panel.rendered[0];
  elements.rows.onclick({target: row});
  elements.rows.onclick({target: row});
  if (scripts.length !== 1 || opens.length !== 0) process.exit(7);
  context.window.SignalixSharedDrawer = {openSharedDrawer: function (payload) { opens.push(payload); }};
  scripts[0].onload();
  setImmediate(function () {
    if (opens.length !== 2 || opens[0].item.symbol !== "BBB" || opens[0].source !== "trend-map" || opens[0].actionability !== "NONE" || opens[0].lane !== "3 · FULL") process.exit(8);
    process.stdout.write("ok");
  });
});
''' % json.dumps(inline)
    result = subprocess.run(["node", "-e", harness], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ok"
    assert "Detail drawer could not be loaded" in inline


def test_shadow_page_removes_public_research_copy_but_keeps_read_only_source_contract():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    normalized = html.lower()
    for removed in ("permanent public read-only research surface", "no authentication required", "research only", "no financial calculations"):
        assert removed not in normalized
    assert 'source:"trend-map"' in html
    assert 'actionability:"NONE"' in html
    for forbidden in ("owner-only", "owner decision", "access control", "auth pending", "authentication pending"):
        assert forbidden not in normalized


def test_shadow_table_contract_sorts_quotes_and_navigates_filtered_rendered_rows():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    assert "group[1].sort" in html
    assert "return bv-av||String(a.symbol).localeCompare(String(b.symbol))" in html
    assert 'typeof value==="number"&&Number.isFinite(value)' in html
    assert 'var change=quoteChangePct(row),changeClass=change===null?"neutral":change>0?"positive":change<0?"negative":"neutral"' in html
    assert 'navigation:{symbols:renderedRows.map(function(candidate){return candidate.symbol;}),items:renderedRows,index:renderedRows.indexOf(item)}' in html
    assert 'window.SignalixSharedDrawer.updateNavigation(renderedRows.map(function(candidate){return candidate.symbol;}),renderedRows)' in html
    assert 'String(value)===mainTrend' in html
    assert 'groups.verified' in html
    assert 'return [1,2,3,4]' in html
    assert '<th>Broad state</th>' not in html
    assert '<th>Bars used</th>' not in html
    assert '<th>As-of</th>' not in html
    assert 'colspan="8"' not in html


def test_shadow_table_orders_display_suffixes_before_quote_and_symbol_ties():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    inline = html.split("<script>", 1)[1].split("</script>", 1)[0]
    harness = r'''
const elements = {};
function Element(id) { this.id = id; this.value = ""; this.hidden = false; this.textContent = ""; this.classList = {toggle: function () {}}; this.setAttribute = function () {}; this.addEventListener = function () {}; this.querySelectorAll = function () { return []; }; }
["search", "main-trend", "summary", "error", "retry", "reload", "rows", "theme-toggle", "shown-count", "declared-count", "as-of", "freshness", "report-status", "report-freshness", "policy-id", "snapshot-banner"].forEach(function (id) { elements[id] = new Element(id); });
Object.defineProperty(elements.rows, "innerHTML", { set: function (value) {
  this.renderedSymbols = Array.from(value.matchAll(/data-symbol="([^"]+)"/g), function (match) { return match[1]; });
} });
const document = {
  body: {classList: {toggle: function () {}}},
  querySelector: function (selector) { return elements[selector.slice(1)] || null; },
  querySelectorAll: function () { return []; }
};
const rows = [
  {symbol: "Z1PP", main_trend: {main_trend: 1, main_trend_display: "1++", evidence_quality: "FULL"}, quote: {change_pct: 5}},
  {symbol: "A1PP", main_trend: {main_trend: 1, main_trend_display: "1++", evidence_quality: "FULL"}, quote: {change_pct: 5}},
  {symbol: "B1P", main_trend: {main_trend: 1, main_trend_display: "1+", evidence_quality: "FULL"}, quote: {change_pct: 10}},
  {symbol: "C1", main_trend: {main_trend: 1, main_trend_display: "1", evidence_quality: "FULL"}, quote: {change_pct: 20}},
  {symbol: "Z3DD", main_trend: {main_trend: 3, main_trend_display: "3--", evidence_quality: "FULL"}, quote: {change_pct: 2}},
  {symbol: "A3DD", main_trend: {main_trend: 3, main_trend_display: "3--", evidence_quality: "FULL"}, quote: {change_pct: 2}},
  {symbol: "B3D", main_trend: {main_trend: 3, main_trend_display: "3-", evidence_quality: "FULL"}, quote: {change_pct: 10}},
  {symbol: "C3", main_trend: {main_trend: 3, main_trend_display: "3", evidence_quality: "FULL"}, quote: {change_pct: 20}}
];
const context = {
  window: {}, document: document, localStorage: {getItem: function () { return null; }, setItem: function () {}}, Promise: Promise,
  fetch: function () { return Promise.resolve({ok: true, json: function () { return Promise.resolve({
    status: "PRODUCTION_READ_ONLY", research_only: false, actionability: "NONE",
    verification_status: "VERIFIED", freshness: {status: "FRESH"}, rows: rows
  }); }}); }
};
vm.runInNewContext(%s, context);
setImmediate(function () {
  const expected = [];
  if (JSON.stringify(elements.rows.renderedSymbols) !== JSON.stringify(expected)) process.exit(1);
  process.stdout.write("ok");
});
''' % json.dumps(inline)
    result = subprocess.run(["node", "-e", "const vm = require('vm');\n" + harness], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ok"


def test_shadow_drawer_removes_wave_evidence_and_chart_prose_but_preserves_markers_and_identity():
    template = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    shared = (Path(__file__).parent / "frontend" / "shared-drawer.js").read_text()
    assert 'dom.drawer.classList.toggle("drawer--shadow", shadow)' in shared
    assert 'if (waveSummary) waveSummary.hidden = shadow' in shared
    assert 'if (dom.drawerChartLegend) dom.drawerChartLegend.hidden = shadow' in shared
    assert 'marker.timestamp != null' in shared and 'marker.price != null' in shared
    assert 'String(item.name).toUpperCase() !== String(item.symbol || "").toUpperCase()' in shared
    assert "drawer-chart-status" not in (template + shared)
    assert "drawer-chart-context" not in (template + shared)
    assert "Evidence details" not in (template + shared)


def test_shadow_adapter_uses_shared_drawer_and_suppresses_action_setup_semantics():
    template = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    shared = Path(__file__).with_name("frontend") / "shared-drawer.js"
    combined = template + shared.read_text()
    assert 'source:"trend-map"' in combined
    assert 'actionability:"NONE"' in combined
    assert 'dom.drawerAction.hidden = shadow' in combined
    assert 'if (setupSection) setupSection.hidden = shadow' in combined
    assert 'shadow ? "Not applicable · Daily classification"' in combined
    assert 'shadow ? "Production read-only Daily evidence"' in combined


def test_shadow_shared_drawer_does_not_restore_removed_evidence_metadata_nodes():
    shared = (Path(__file__).parent / "frontend" / "shared-drawer.js").read_text()
    for removed in ('drawer-52w', 'drawer-ath', 'drawer-provenance', 'Evidence details and provenance'):
        assert removed not in shared
    assert 'dom.drawer.classList.remove("drawer--hidden");' in shared


def test_shadow_shared_drawer_owns_ohlcv_table_overflow_without_page_overflow():
    shared = (Path(__file__).parent / "frontend" / "shared-drawer.js").read_text()
    css = (Path(__file__).parent / "frontend" / "styles.css").read_text()
    assert '<div class="rolling-high-low__table-wrap"><table>' in shared
    assert '</tbody></table></div></section>' in shared
    assert ".rolling-high-low__table-wrap { width:100%; max-width:100%; min-width:0; overflow-x:auto; }" in css
    assert ".rolling-high-low table { width:100%; min-width:520px;" in css
    assert "font-size:12px" in css
    assert "body {" in css and "overflow-x: hidden;" in css


def test_template_has_mobile_safe_accordion_strategy():
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    assert ".accordion" in html
    assert "min-width:0" in html
    assert "table-layout:fixed" in html
    assert "overflow-x:hidden" in html
    mobile = html.split("@media (max-width:720px)", 1)[1]
    assert ".trend-page th,.trend-page td{padding:9px 5px;font-size:12px}" in mobile
    for column, width in ((1, "22%"), (2, "18%"), (3, "18%"), (4, "19%"), (5, "23%")):
        assert f"nth-child({column})" in mobile
        assert f"width:{width}" in mobile
    assert "white-space:nowrap" in html
    assert "text-overflow:ellipsis" in html


def test_shadow_accordion_renders_inside_390px_viewport_with_helper_metadata_and_rows_contained():
    playwright = pytest.importorskip("playwright.sync_api")
    html = Path(__file__).with_name("shadow_trend_map_template.html").read_text()
    css = html.split("<style>", 1)[1].split("</style>", 1)[0]
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as error:
            pytest.skip("Chromium cannot start in this sandbox: " + str(error).splitlines()[0])
        page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        page.set_content(f'''<style>*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
          body {{ margin: 0; background: #0a0e17; overflow-x: hidden; }}
          {css}</style>
          <body class="trend-page"><main>
            <div class="trend-meta"><span class="meta-chip">Data date <strong>2026-09-11</strong></span><span class="meta-chip">Status <strong>Current</strong></span><span class="meta-chip">Scope <strong>Thai listed universe</strong></span><span class="meta-chip">Showing <strong>1</strong></span><span class="meta-chip">Total <strong>1</strong></span></div>
            <p class="shadow-provenance">Daily direction is classified from end-of-day data. The 60-minute price is for display only.</p>
            <div id="rows" class="accordion"><section class="trend-section" data-trend-section="1"><h2><button class="trend-toggle">Main Trend 1</button></h2><div class="trend-panel"><table>
              <thead><tr><th>Symbol</th><th>Price</th><th>Change</th><th>% Change</th><th>Main Trend</th></tr></thead>
              <tbody><tr tabindex="0" data-symbol="AAA"><td>AAA</td><td>100.00</td><td>1.00</td><td>1.00%</td><td>1++ · FULL</td></tr></tbody>
            </table></div></section></div>
          </main></body>''')
        result = page.evaluate("""() => {
          const section = document.querySelector('.trend-section');
          const panel = document.querySelector('.trend-panel');
          const table = document.querySelector('table');
          const cells = [...document.querySelectorAll('tbody td')];
          return {
            viewport: document.documentElement.clientWidth,
            documentScroll: document.documentElement.scrollWidth,
            bodyScroll: document.body.scrollWidth,
            helper: !!document.querySelector('.shadow-provenance'),
            metadata: document.querySelector('.trend-meta').getBoundingClientRect().width,
            accordion: document.querySelector('.accordion').getBoundingClientRect().width,
            section: section.getBoundingClientRect().width,
            panel: panel.getBoundingClientRect().width,
            table: table.getBoundingClientRect().width,
            main: document.querySelector('main').getBoundingClientRect().width,
            cells: cells.map(cell => ({width: cell.getBoundingClientRect().width, text: cell.textContent}))
          };
        }""")
        browser.close()
    assert result["documentScroll"] <= result["viewport"]
    assert result["bodyScroll"] <= result["viewport"]
    assert result["helper"] is True
    assert result["metadata"] <= result["main"]
    assert result["accordion"] <= result["main"]
    assert result["section"] <= result["accordion"]
    assert result["panel"] <= result["section"]
    assert result["table"] <= result["main"]
    assert len(result["cells"]) == 5
    assert all(cell["width"] > 0 for cell in result["cells"])
    assert result["cells"][-1]["text"] == "1++ · FULL"


def test_shadow_module_has_no_database_write_operations():
    source = Path(subject.__file__).read_text()
    for token in ("INSERT", "UPDATE", "DELETE", "CREATE TABLE", "ALTER TABLE", "DROP TABLE"):
        assert token not in source.upper()


def test_backend_local_adapter_uses_select_only_pit_query_and_filters_as_of():
    class Cursor:
        description = [(name,) for name in ("date", "open", "high", "low", "close", "volume")]

        def __init__(self):
            self.sql = None
            self.params = None

        def execute(self, sql, params):
            self.sql, self.params = sql, params

        def fetchall(self):
            return [("2026-09-10", 99, 101, 98, 100, 1234)]

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

    conn = Connection()
    rows, latest = subject.BackendDailyAdapter().load_daily_pit(conn, "AAA", "2026-09-11")
    assert rows[0]["close"] == 100
    assert latest == "2026-09-10"
    assert conn.cursor_instance.sql.lstrip().upper().startswith("WITH")
    assert "date <= %s" in conn.cursor_instance.sql
    assert conn.cursor_instance.params == ("AAA", "2026-09-11", "AAA", "2026-09-11", "2026-09-11")


class _ResultSetCursor:
    def __init__(self, rows):
        self.rows = rows
        self.description = [(f"column_{index}",) for index in range(len(rows[0]))] if rows else []
        self.calls = []

    def execute(self, sql, params):
        self.sql = sql
        self.calls.append((sql, params))

    def fetchall(self):
        if "source_completion_cutoff >=" not in self.sql:
            return self.rows
        official_dates = {row[0] for row in self.rows if row[6] == "price_data"}
        return [row for row in self.rows
                if row[6] == "price_data"
                or (row[0] not in official_dates
                    and row[8] == subject.DERIVED_DAILY_METHOD
                    and "2026-09-11T10:00:00+00:00" <= row[12] <= "2026-09-11T10:00:00+00:00")]

    def close(self):
        pass


class _ResultSetConnection:
    def __init__(self, rows):
        self.cursor_instance = _ResultSetCursor(rows)

    def cursor(self):
        return self.cursor_instance


def _official_row(date, close):
    return (date, close - 1, close + 1, close - 2, close, 1000,
            "price_data", None, None, None, None, None, None)


def _derived_row(date, close, run_id="run-derived"):
    return (date, close - 1, close + 1, close - 2, close, 8000,
            "derived_daily_price_data", "60m", "settrade_60m_complete_bangkok_session_ohlcv_v1",
            run_id, "2026-09-11T02:00:00+00:00", "2026-09-11T09:00:00+00:00",
            "2026-09-11T10:00:00+00:00", 8)


def test_backend_adapter_rejects_pre_completion_and_accepts_17_00_completion():
    before = list(_derived_row("2026-09-11", 109, "run-before"))
    before[12] = "2026-09-11T09:59:59+00:00"
    after = _derived_row("2026-09-11", 110, "run-after")
    late = list(_derived_row("2026-09-11", 111, "run-late"))
    late[12] = "2026-09-11T11:00:00+00:00"
    rows, latest = subject.BackendDailyAdapter().load_daily_pit(
        _ResultSetConnection([tuple(before), after, tuple(late)]), "AAA", "2026-09-11")
    assert [(row["close"], row["source_run_id"]) for row in rows] == [(110, "run-after")]
    assert latest == "2026-09-11"


def test_backend_adapter_selects_official_first_and_fills_missing_dates_from_fake_result_set():
    # The fake result set models PostgreSQL's already-resolved official-first
    # UNION result; assertions below exercise the adapter mapping, not SQL text.
    conn = _ResultSetConnection([
        _official_row("2026-09-10", 100),
        _derived_row("2026-09-11", 110),
    ])
    rows, latest = subject.BackendDailyAdapter().load_daily_pit(
        conn, "AAA", "2026-09-11")
    assert [(row["date"], row["source"]) for row in rows] == [
        ("2026-09-10", "price_data"),
        ("2026-09-11", "derived_daily_price_data"),
    ]
    assert latest == "2026-09-11"
    assert rows[0]["source_run_id"] is None
    assert rows[1]["source_run_id"] == "run-derived"


def test_backend_adapter_official_same_date_wins_in_fake_result_set():
    conn = _ResultSetConnection([
        _official_row("2026-09-11", 100),
        _derived_row("2026-09-11", 110),
    ])
    rows, latest = subject.BackendDailyAdapter().load_daily_pit(
        conn, "AAA", "2026-09-11")
    assert len(rows) == 1
    assert rows[0]["source"] == "price_data"
    assert rows[0]["close"] == 100
    assert latest == "2026-09-11"


def test_backend_adapter_preserves_complete_derived_lineage_from_fake_result_set():
    conn = _ResultSetConnection([_derived_row("2026-09-11", 110, "run-22")])
    rows, _ = subject.BackendDailyAdapter().load_daily_pit(
        conn, "AAA", "2026-09-11")
    assert rows[0] == {
        "date": "2026-09-11", "open": 109, "high": 111, "low": 108,
        "close": 110, "volume": 8000,
        "source": "derived_daily_price_data", "source_timeframe": "60m",
        "derivation_method": "settrade_60m_complete_bangkok_session_ohlcv_v1",
        "source_run_id": "run-22", "source_first_ts": "2026-09-11T02:00:00+00:00",
        "source_last_ts": "2026-09-11T09:00:00+00:00",
        "source_completion_cutoff": "2026-09-11T10:00:00+00:00", "source_bar_count": 8,
    }


def test_backend_adapter_selects_latest_completed_60m_row_and_daily_baseline():
    class Cursor:
        description = [(name,) for name in ("symbol", "ts", "close", "date", "daily_close", "daily_source")]

        def execute(self, sql, params):
            self.sql, self.params = sql, params

        def fetchall(self):
            return [
                ("AAA", "2026-09-11T08:00:00+00:00", 109, "2026-09-10", 100, "price_data"),
                ("AAA", "2026-09-11T09:00:00+00:00", 110, "2026-09-10", 100, "price_data"),
            ]

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

    conn = Connection()
    result = subject.BackendDailyAdapter().load_intraday_quotes(
        conn, ["AAA"], now=datetime(2026, 9, 11, 9, 30, tzinfo=timezone.utc),
    )
    assert result["AAA"] == {
        "ts": "2026-09-11T09:00:00+00:00", "close": 110.0,
        "daily_close": 100.0, "daily_date": "2026-09-10", "daily_source": "price_data",
    }
    assert "intraday_price_data" in conn.cursor_instance.sql
    assert "SELECT DISTINCT ON (symbol)" in conn.cursor_instance.sql
    assert "LEFT JOIN LATERAL" in conn.cursor_instance.sql
    assert "daily_candidates" not in conn.cursor_instance.sql
    assert "p.date < (i.ts AT TIME ZONE 'Asia/Bangkok')::date" in conn.cursor_instance.sql
    assert "ORDER BY daily.date DESC, daily.source_priority ASC" in conn.cursor_instance.sql
    assert "NOT EXISTS" in conn.cursor_instance.sql
    assert conn.cursor_instance.params == (["AAA"],)


@pytest.mark.parametrize("daily_source", ["price_data", "derived_daily_price_data"])
def test_backend_adapter_preserves_official_first_or_derived_daily_baseline(daily_source):
    class Cursor:
        description = [(name,) for name in ("symbol", "ts", "close", "date", "daily_close", "daily_source")]

        def execute(self, sql, params):
            self.sql, self.params = sql, params

        def fetchall(self):
            return [("AAA", "2026-09-11T09:00:00+00:00", 110, "2026-09-10", 100, daily_source)]

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

    result = subject.BackendDailyAdapter().load_intraday_quotes(
        Connection(), ["AAA"], now=datetime(2026, 9, 11, 9, 30, tzinfo=timezone.utc),
    )
    assert result["AAA"]["daily_source"] == daily_source
    assert result["AAA"]["daily_close"] == 100.0


def test_backend_local_adapter_batches_symbols_with_exact_as_of_filter():
    class Cursor:
        description = [(name,) for name in ("symbol", "date", "open", "high", "low", "close", "volume", "invalid_count")]

        def __init__(self):
            self.sql = None
            self.params = None

        def execute(self, sql, params):
            self.sql, self.params = sql, params

        def fetchall(self):
            return [("AAA", "2026-09-10", 99, 101, 98, 100, 1234, 0)]

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

    conn = Connection()
    loaded = subject.BackendDailyAdapter().load_daily_pit_batch(conn, ["AAA", "BBB"], "2026-09-11")
    assert list(loaded) == ["AAA", "BBB"]
    assert len(loaded["AAA"][0]) == 1
    assert loaded["BBB"][0:2] == ([], None)
    assert loaded["BBB"][2]["quality_established"] is False
    assert loaded["AAA"][2]["invalid_count"] == 0
    assert conn.cursor_instance.sql.lstrip().upper().startswith("WITH")
    assert "symbol=ANY(%s)" in conn.cursor_instance.sql
    assert "market='TH'" in conn.cursor_instance.sql
    assert "date <= %s" in conn.cursor_instance.sql
    assert "ORDER BY symbol ASC, date ASC" in conn.cursor_instance.sql
    assert conn.cursor_instance.params == (["AAA", "BBB"], "2026-09-11", ["AAA", "BBB"], "2026-09-11", "2026-09-11", subject.RETRIEVAL_CAP, subject.RETRIEVAL_CAP)
    assert "row_number() OVER (PARTITION BY filtered.symbol ORDER BY filtered.date DESC)" in conn.cursor_instance.sql
    assert "FROM bounded_rows\n                WHERE retrieval_row <= %s" in conn.cursor_instance.sql
    assert "invalid_count" in conn.cursor_instance.sql


def test_report_uses_one_batch_select_and_preserves_counts():
    class Adapter:
        def __init__(self):
            self.batch_calls = []

        def resolve_universe(self, conn, value):
            return ["AAA", "BBB"], {"universe_filter": value, "eligible_count": 2}

        def _exec_select(self, conn, sql, params=None):
            assert sql.startswith("SELECT")
            return [("2026-09-11",)], ["max_date"]

        def load_daily_pit_batch(self, conn, symbols, as_of):
            self.batch_calls.append((list(symbols), as_of))
            return {"AAA": (bars(75), as_of), "BBB": ([], None)}

    adapter = Adapter()
    report = subject.build_shadow_report(adapter, object())
    assert adapter.batch_calls == [(["AAA", "BBB"], "2026-09-11")]
    assert report["summary"] == {"DATA_BLOCKED": 1, "AVAILABLE": 1}
    assert report["status_by_symbol"] == {"AAA": "AVAILABLE", "BBB": "DATA_BLOCKED"}
    assert report["universe"]["declared_count"] == 2


def test_batch_error_is_visible_as_blocked_and_not_verified():
    class Adapter:
        def resolve_universe(self, conn, value):
            return ["AAA", "BBB"], {"universe_filter": value}

        def _exec_select(self, conn, sql, params=None):
            return [("2026-09-11",)], ["max_date"]

        def load_daily_pit_batch(self, conn, symbols, as_of):
            raise OSError("database unavailable")

    report = subject.build_shadow_report(Adapter(), object())
    assert report["status"] == "DATA_BLOCKED"
    assert report["status_by_symbol"] == {"AAA": "DATA_BLOCKED", "BBB": "DATA_BLOCKED"}
    assert all(row["provenance"]["availability"] == "NOT_VERIFIED" for row in report["rows"])


def test_default_report_cache_reuses_and_invalidates_on_as_of(monkeypatch):
    subject.clear_report_cache()
    adapter = subject.BackendDailyAdapter()
    calls = {"as_of": 0, "batch": 0}

    class Connection:
        def close(self):
            pass

    def fake_get_conn():
        return Connection()

    def resolve(conn, value):
        return ["AAA"], {"universe_filter": value}

    def select(conn, sql, params=None):
        calls["as_of"] += 1
        return [("2026-09-11" if calls["as_of"] < 3 else "2026-09-12",)], ["max_date"]

    def batch(conn, symbols, current_as_of):
        calls["batch"] += 1
        return {"AAA": (bars(75), current_as_of)}

    monkeypatch.setattr(subject, "_adapter", lambda: adapter)
    monkeypatch.setattr(adapter, "_get_conn", fake_get_conn)
    monkeypatch.setattr(adapter, "resolve_universe", resolve)
    monkeypatch.setattr(adapter, "_exec_select", select)
    monkeypatch.setattr(adapter, "load_daily_pit_batch", batch)

    cold = subject.build_shadow_report(source="database")
    warm = subject.build_shadow_report(source="database")
    refreshed = subject.build_shadow_report(source="database")
    assert cold["cache"]["status"] == "cold"
    assert warm["cache"]["status"] == "warm"
    assert warm["cache"]["as_of"] == "2026-09-11"
    assert warm["cache"]["policy_hash"] == warm["policy"]["hash"]
    assert refreshed["as_of"] == "2026-09-12"
    assert refreshed["cache"]["status"] == "cold"
    assert calls["batch"] == 2
    subject.clear_report_cache()


@pytest.mark.parametrize("sql", [
    "UPDATE price_data SET close=1",
    "WITH changed AS (DELETE FROM price_data RETURNING symbol) SELECT * FROM changed",
    "WITH changed AS (UPDATE price_data SET close=1 RETURNING symbol) SELECT * FROM changed",
    "WITH changed AS (INSERT INTO price_data(symbol) VALUES ('AAA') RETURNING symbol) SELECT * FROM changed",
])
def test_backend_local_adapter_rejects_mutating_sql_anywhere(sql):
    with pytest.raises(RuntimeError, match="SELECT/WITH"):
        subject._assert_select(sql)


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "WITH source AS (SELECT 1 AS value) SELECT value FROM source",
])
def test_backend_local_adapter_accepts_read_only_select_and_with(sql):
    subject._assert_select(sql)


def test_report_builds_with_injected_backend_local_adapter(monkeypatch):
    adapter = subject.BackendDailyAdapter()
    monkeypatch.setattr(adapter, "resolve_universe", lambda conn, value: (["AAA"], {"universe_filter": value}))
    monkeypatch.setattr(adapter, "_exec_select", lambda conn, sql, params=None: ([("2026-09-11",)], ["max_date"]))
    monkeypatch.setattr(adapter, "load_daily_pit", lambda conn, symbol, as_of: (bars(75), as_of))
    report = subject.build_shadow_report(adapter=adapter, conn=object())
    assert report["status_by_symbol"] == {"AAA": "AVAILABLE"}
    assert report["provenance"]["adapter"] == "BackendDailyAdapter"


def test_api_route_is_same_origin_read_only_envelope(monkeypatch):
    class Handler:
        def __init__(self):
            self.headers = {}
            self.body = bytearray()
            self.wfile = self
        def send_response(self, status):
            self.status = status
        def send_header(self, key, value):
            self.headers[key] = value
        def end_headers(self):
            pass
        def write(self, body):
            self.body.extend(body)
    handler = Handler()
    monkeypatch.setattr(subject, "build_shadow_report", lambda: {"status": subject.PRODUCTION_READ_ONLY, "research_only": False, "actionability": "NONE", "rows": []})
    assert subject.handle_shadow_trend_map_api("/api/trend-map", handler)
    assert handler.status == 200
    payload = json.loads(bytes(handler.body))
    assert payload["status"] == subject.PRODUCTION_READ_ONLY
    assert payload["research_only"] is False
    assert payload["actionability"] == "NONE"


def test_history_trigger_ui_contract_is_explicit_and_fail_closed():
    template = Path(__file__).with_name("shadow_trend_map_template.html").read_text(encoding="utf-8")
    drawer = (Path(__file__).parent / "frontend" / "shared-drawer.js").read_text(encoding="utf-8")
    for marker in (
        'id="snapshot-select"', "Latest EOD", "Historical EOD snapshot", "snapshot=",
        "HISTORICAL_DATA_BLOCKED", "no current fallback used", "snapshotIsHistorical",
        "Trend changed", "trend_duration_sessions", "UP TRIGGER REACHED",
        "DOWN TRIGGER REACHED", "NO MARKER", "confirmation requires a completed EOD close/classification",
        "NO CURRENT-SESSION MARKER", "Not verified", "actionability===\"NONE\"",
    ):
        assert marker in template
    assert "drawer-trend-evidence" in drawer
    assert "trend_changed_date" in drawer and "trend_duration_sessions" in drawer
    assert "completed EOD close/classification" in drawer


def test_history_trigger_ui_keeps_current_freshness_gate_separate_from_historical():
    template = Path(__file__).with_name("shadow_trend_map_template.html").read_text(encoding="utf-8")
    assert 'data.freshness.status!=="FRESH"' in template
    assert 'data.freshness.status==="HISTORICAL"' in template
    assert 'fetch(path,{cache:"no-store"})' in template
    assert 'selectedSnapshot?"?snapshot="+encodeURIComponent(selectedSnapshot)' in template


def test_snapshot_selector_populates_from_successful_responses_and_preserves_history_selection():
    template = Path(__file__).with_name("shadow_trend_map_template.html").read_text(encoding="utf-8")
    inline = template.split("<script>", 1)[1].split("</script>", 1)[0]
    assert 'function render(){renderSnapshotOptions(report);renderSnapshotBanner();' in inline
    assert 'function snapshotSessions(data){var values=data&&data.snapshots;' in inline
    assert "snapshot.sessions" not in inline
    harness = r'''
const vm = require("vm");
const options = [];
function Element(id) {
  this.id = id; this.value = ""; this.hidden = false; this.textContent = "";
  this.innerHTML = ""; this.onclick = null; this.onchange = null;
  this.classList = {contains: function () { return false; }, toggle: function () {}};
  this.setAttribute = function () {};
  this.addEventListener = function (name, handler) { this["on" + name] = handler; };
  this.querySelector = function () { return null; };
  this.querySelectorAll = function () { return []; };
  this.closest = function () { return this; };
  Object.defineProperty(this, "innerHTML", {
    get: function () { return this._innerHTML || ""; },
    set: function (value) {
      this._innerHTML = value;
      if (this.id !== "snapshot-select") return;
      options.length = 0;
      String(value).replace(/<option value="([^"]*)">/g, function (_, optionValue) {
        options.push(optionValue);
        return _;
      });
      if (options.indexOf(this.value) < 0) this.value = "";
    },
  });
}
const elements = {};
const ids = ["snapshot-select", "snapshot-banner", "error", "retry", "drawer-retry",
  "summary", "shown-count", "declared-count", "as-of", "freshness", "report-status",
  "report-freshness", "policy-id", "search", "main-trend", "rows", "theme-toggle", "reload"];
ids.forEach(function (id) { elements[id] = new Element(id); });
elements["error"].hidden = true; elements["retry"].hidden = true;
const current = {
  status: "PRODUCTION_READ_ONLY", research_only: false, actionability: "NONE",
  verification_status: "VERIFIED", freshness: {status: "FRESH"}, rows: [],
  snapshots: ["2026-09-15", "2026-09-14", "2026-09-11"],
  snapshot: {kind: "current", row_count: 0}, universe: {declared_count: 0}, policy: {},
};
const historical = Object.assign({}, current, {
  freshness: {status: "HISTORICAL"},
  snapshot: {kind: "historical", as_of: "2026-09-14", row_count: 0},
});
const corrupt = Object.assign({}, current, {snapshots: null});
const requests = [];
const context = {
  console: console, setTimeout: setTimeout, clearTimeout: clearTimeout,
  window: {}, document: {
    body: elements.body || (elements.body = new Element("body")),
    querySelector: function (selector) {
      if (selector.charAt(0) === "#") return elements[selector.slice(1)] || null;
      return null;
    },
  },
  localStorage: {getItem: function () { return null; }, setItem: function () {}},
  fetch: function (path) {
    requests.push(path);
    return Promise.resolve({ok: true, json: function () {
      return Promise.resolve(requests.length === 1 ? current : requests.length === 2 ? historical : corrupt);
    }});
  },
};
vm.runInNewContext(INLINE, context);
setTimeout(function () {
  if (options.join(",") !== ",2026-09-15,2026-09-14,2026-09-11") process.exit(1);
  if (elements["snapshot-banner"].innerHTML.indexOf("Latest EOD") < 0 || elements["snapshot-banner"].innerHTML.indexOf("0 rows in this snapshot") < 0 || elements["snapshot-banner"].innerHTML.indexOf("Current session markers are provisional") < 0) process.exit(6);
  elements["snapshot-select"].value = "2026-09-14";
  elements["snapshot-select"].onchange();
  setTimeout(function () {
    if (requests.join("|") !== "/api/trend-map|/api/trend-map?snapshot=2026-09-14") process.exit(2);
    if (options.join(",") !== ",2026-09-15,2026-09-14,2026-09-11") process.exit(3);
    if (elements["snapshot-select"].value !== "2026-09-14") process.exit(4);
    if (elements["snapshot-banner"].innerHTML.indexOf("Historical EOD snapshot · 2026-09-14") < 0 || elements["snapshot-banner"].innerHTML.indexOf("0 rows in this snapshot") < 0 || elements["snapshot-banner"].innerHTML.indexOf("Historical EOD only; current-session quote and trigger markers are not shown.") < 0) process.exit(7);
    elements["snapshot-select"].value = "";
    elements["snapshot-select"].onchange();
    setTimeout(function () {
      if (requests.length !== 3 || options.join(",") !== "") process.exit(5);
      process.exit(0);
    }, 0);
  }, 0);
}, 0);
'''.replace("INLINE", json.dumps(inline))
    result = subprocess.run(["node", "-e", harness], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout
