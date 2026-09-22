"""Focused contract tests for provisional 60m chart bars."""
from datetime import datetime, timezone

import pytest

import app
import mvp_chart_db
import mvp_routes
from app import fetch_chart_rows
from canonical_chart_read import ChartReadResult, read_chart_result


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def execute(self, query, params):
        self.queries.append((query, params))

    def fetchall(self):
        return self.rows


class _DailyAndIntradayCursor:
    def __init__(self, daily, intraday):
        self.responses = [daily, intraday]
        self.index = 0
        self.queries = []

    def execute(self, query, params):
        self.queries.append((query, params))

    def fetchall(self):
        result = self.responses[self.index]
        self.index += 1
        return result

    def close(self):
        pass


def test_60m_marks_only_latest_stored_bar_provisional():
    rows = [
        (datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc), 10, 11, 9, 10.5, 100, False),
        (datetime(2026, 8, 27, 6, 0, tzinfo=timezone.utc), 10.5, 12, 10, 11.5, 200, True),
    ]
    cursor = _Cursor(rows)

    actual, _ = fetch_chart_rows(cursor, "SIS", "60M", 30)

    assert [row[-1] for row in actual] == [False, True]
    assert "ROW_NUMBER" in cursor.queries[0][0]


def test_60m_empty_rows_remain_empty_without_fabricating_provisional_bar():
    actual, label = fetch_chart_rows(_Cursor([]), "SIS", "60M", 30)

    assert actual == []
    assert "latest candle may be in progress" in label


def test_chart_response_exposes_provisional_status_and_exact_as_of():
    """The chart contract must let the UI distinguish an open bar from EOD."""
    rows = [
        (datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc), 10, 11, 9, 10.5, 100, False),
        (datetime(2026, 8, 27, 6, 0, tzinfo=timezone.utc), 10.5, 12, 10, 11.5, 200, True),
    ]
    cursor = _Cursor(rows)

    # Avoid DB setup; exercise the response shaping seam directly.
    actual_rows, label = fetch_chart_rows(cursor, "SIS", "60M", 30)
    assert actual_rows[-1][-1] is True
    assert actual_rows[-1][0].isoformat() == "2026-08-27T06:00:00+00:00"
    assert "in progress" in label


def test_day_replaces_existing_same_day_daily_row_with_provisional_60m_aggregate():
    daily = [(datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False)]
    intra = [(datetime(2026, 8, 27, 5, tzinfo=timezone.utc), 10, 12, 9, 11, 100,)]
    rows, label = fetch_chart_rows(_DailyAndIntradayCursor(daily, intra), "SIS", "1D", 30)
    assert len(rows) == 1
    assert rows[0][1:6] == (10, 12, 9, 11, 100)
    assert rows[0][-1] is True
    assert "provisional" in label


def test_day_without_current_session_data_keeps_daily_eod_provenance():
    rows, label = fetch_chart_rows(_DailyAndIntradayCursor(
        [(datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False)], []), "SIS", "1D", 30)
    assert rows[-1][-1] is False
    assert "no current-session 60m data" in label


def test_daily_chart_reads_valid_derived_rows_when_official_daily_is_absent():
    cursor = _DailyAndIntradayCursor([
        (datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False, "derived_daily_price_data"),
    ], [])

    result = read_chart_result(cursor, "PR9", "1D", 30)

    assert result.source == "derived_daily_price_data"
    assert result.as_of == "2026-08-27"
    assert result.candles[-1]["source"] == "derived_daily_price_data"
    assert "derived_daily_price_data" in cursor.queries[0][0]
    assert "NOT EXISTS" in cursor.queries[0][0]


def test_same_date_official_daily_remains_selected_over_derived_row():
    cursor = _DailyAndIntradayCursor([
        (datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False, "price_data"),
        (datetime(2026, 8, 27), 10, 11, 9, 10.5, 800, False, "derived_daily_price_data"),
    ], [])

    result = read_chart_result(cursor, "PR9", "1D", 30)

    assert len(result.candles) == 1
    assert result.candles[0]["source"] == "price_data"
    assert result.candles[0]["close"] == 9.5


def test_derived_read_rejects_rows_after_explicit_read_cutoff():
    cursor = _DailyAndIntradayCursor([], [])
    cutoff = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)

    read_chart_result(cursor, "PR9", "1D", 30, read_cutoff=cutoff)

    query, params = cursor.queries[0]
    assert "source_completion_cutoff <=" in query
    assert cutoff in params


def test_derived_read_requires_valid_ohlcv_geometry():
    cursor = _DailyAndIntradayCursor([], [])

    read_chart_result(cursor, "PR9", "1D", 30)

    query = cursor.queries[0][0]
    assert "high >= GREATEST(open, close, low)" in query
    assert "low <= LEAST(open, close, high)" in query
    assert "volume >= 0" in query
    assert "open::text NOT IN ('NaN', 'Infinity', '-Infinity')" in query


def test_derived_lineage_is_preserved_on_selected_candle():
    lineage = (
        "run-22", datetime(2026, 8, 27, 2, tzinfo=timezone.utc),
        datetime(2026, 8, 27, 9, tzinfo=timezone.utc),
        datetime(2026, 8, 27, 10, tzinfo=timezone.utc), "60m", 8,
        "settrade_60m_complete_bangkok_session_ohlcv_v1",
    )
    cursor = _DailyAndIntradayCursor([(
        datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False,
        "derived_daily_price_data", *lineage,
    )], [])

    result = read_chart_result(cursor, "PR9", "1D", 30)

    assert result.candles[0]["provenance"] == {
        "source": "derived_daily_price_data", "source_run_id": "run-22",
        "source_first_ts": "2026-08-27T02:00:00+00:00",
        "source_last_ts": "2026-08-27T09:00:00+00:00",
        "source_completion_cutoff": "2026-08-27T10:00:00+00:00",
        "source_timeframe": "60m", "source_bar_count": 8,
        "derivation_method": "settrade_60m_complete_bangkok_session_ohlcv_v1",
    }


def test_provisional_current_session_has_intraday_source_separate_from_daily_source():
    cursor = _DailyAndIntradayCursor([
        (datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False, "derived_daily_price_data"),
    ], [(datetime(2026, 8, 27, 5, tzinfo=timezone.utc), 10, 12, 9, 11, 100)])

    result = read_chart_result(cursor, "PR9", "1D", 30)

    assert result.candles[-1]["provisional"] is True
    assert result.candles[-1]["source"] == "intraday_price_data"
    assert result.candles[-1]["provenance"]["source"] == "intraday_price_data"


def test_mixed_weekly_sources_are_marked_mixed_with_constituent_provenance():
    cursor = _DailyAndIntradayCursor([
        (datetime(2026, 8, 24), 9, 10, 8, 9.5, 900, False, "price_data"),
        (datetime(2026, 8, 25), 10, 11, 9, 10.5, 800, False, "derived_daily_price_data"),
    ], [])

    result = read_chart_result(cursor, "PR9", "1W", 30)

    assert result.candles[0]["source"] == "mixed"
    assert result.candles[0]["provenance"]["sources"] == [
        "price_data", "derived_daily_price_data"
    ]


def test_chart_db_response_preserves_derived_daily_provenance(monkeypatch):
    monkeypatch.setattr(
        mvp_chart_db,
        "_get_db_connection",
        lambda: _Connection([
            (datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False,
             "derived_daily_price_data"),
        ], []),
    )

    response = mvp_chart_db.project_chart_db_response("PR9", timeframe="1D")

    assert response["source"] == "derived_daily_price_data"
    assert response["provenance"]["source"] == "derived_daily_price_data"
    assert response["as_of"] == "2026-08-27"


def test_chart_view_is_trimmed_but_default_chart_remains_full(monkeypatch):
    daily = [
        (datetime(2025, 1, 1) + __import__("datetime").timedelta(days=index),
         100 + index, 101 + index, 99 + index, 100.5 + index, 1000 + index, False)
        for index in range(260)
    ]
    monkeypatch.setattr(mvp_chart_db, "_get_db_connection", lambda: _Connection(daily, []))

    full = mvp_chart_db.project_chart_db_response("TEAM", timeframe="1D")
    compact = mvp_chart_db.compact_chart_db_response(full)

    assert len(full["candles"]) == 260
    assert len(full["indicators"]["series"]["ma"]["200"]) == 260
    assert len(compact["candles"]) == 120
    assert compact["candles"] == full["candles"][-120:]
    for values in compact["indicators"]["series"]["ma"].values():
        assert len(values) == 120
    for values in compact["indicators"]["series"]["macd"].values():
        assert len(values) == 120
    assert len(compact["indicators"]["series"]["rsi"]) == 120
    assert "atr" not in compact["indicators"]["series"]
    assert "atr" in full["indicators"]["series"]
    assert compact["indicators"]["latest"] == full["indicators"]["latest"]
    assert compact["indicators"]["latest"]["ma"]["100"] == full["indicators"]["latest"]["ma"]["100"]
    assert compact["indicators"]["latest"]["ma"]["200"] == full["indicators"]["latest"]["ma"]["200"]
    assert compact["source"] == full["source"]
    assert compact["as_of"] == full["as_of"]
    assert compact["candles"][-1]["provenance"] == full["candles"][-1]["provenance"]
    assert compact["provenance"]["representation"] == "chart_view"
    assert compact["provenance"]["representation_authoritative"] is False
    assert "ma20" not in compact and "ma50" not in compact and "ma200" not in compact
    assert len(__import__("json").dumps(compact)) < len(__import__("json").dumps(full))


@pytest.mark.parametrize("timeframe", ["1D", "1W"])
def test_chart_db_adapter_replaces_same_day_daily_row(monkeypatch, timeframe):
    daily = [(datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False)]
    intraday = [(datetime(2026, 8, 27, 5, tzinfo=timezone.utc), 10, 12, 9, 11, 100)]
    cursor = _DailyAndIntradayCursor(daily, intraday)
    connection = _Connection(daily, intraday)
    connection.cursor_value = cursor
    monkeypatch.setattr(mvp_chart_db, "_get_db_connection", lambda: connection)

    response = mvp_chart_db.project_chart_db_response("sis", timeframe=timeframe)

    assert response["candles"][-1]["close"] == 11.0
    assert response["candles"][-1]["volume"] == 100.0
    assert response["candles"][-1]["provisional"] is True
    assert response["latest_time"] == "2026-08-27T05:00:00+00:00"
    assert response["as_of"] == ("2026-08-27" if timeframe == "1D" else "2026-08-24")
    assert response["provenance"]["source"] == "price_data"
    assert "provisional 60m aggregation" in response["provenance"]["note"]


def test_chart_db_weekly_candles_are_ascending_with_latest_provisional_period(monkeypatch):
    daily = [
        (datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False),
        (datetime(2026, 8, 24), 8, 9, 7, 8.5, 800, False),
        (datetime(2026, 8, 14), 7, 8, 6, 7.5, 700, False),
        (datetime(2026, 8, 10), 6, 7, 5, 6.5, 600, False),
        (datetime(2026, 8, 3), 5, 6, 4, 5.5, 500, False),
    ]
    intraday = [
        (datetime(2026, 8, 27, 5, tzinfo=timezone.utc), 10, 12, 9, 11, 100),
    ]
    monkeypatch.setattr(
        mvp_chart_db,
        "_get_db_connection",
        lambda: _Connection(daily, intraday),
    )

    response = mvp_chart_db.project_chart_db_response("sis", timeframe="1W")

    assert [c["date"] for c in response["candles"]] == [
        "2026-08-03", "2026-08-10", "2026-08-24",
    ]
    assert response["candles"][-1]["provisional"] is True
    assert response["as_of"] == "2026-08-24"
    assert response["latest_time"] == "2026-08-27T05:00:00+00:00"


@pytest.mark.parametrize("timeframe", ["1D", "1W"])
def test_chart_db_route_preserves_legacy_fields_and_falls_back_to_daily_eod(monkeypatch, timeframe):
    connection = _Connection(
        [(datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False)], []
    )
    monkeypatch.setattr(mvp_chart_db, "_get_db_connection", lambda: connection)
    monkeypatch.setattr(mvp_chart_db, "_release_db_connection", lambda pg: None)
    monkeypatch.setattr(mvp_routes, "load_payload", lambda: {"items": []})
    handler = type("Handler", (), {
        "wfile": type("Writer", (), {"write": lambda self, data: setattr(self, "body", data)})(),
        "send_response": lambda self, status: setattr(self, "status", status),
        "send_header": lambda self, *args: None,
        "end_headers": lambda self: None,
    })()

    assert mvp_routes.handle_mvp_api(f"/api/chart-db/SIS?timeframe={timeframe}", handler)
    payload = __import__("json").loads(handler.wfile.body)
    assert handler.status == 200
    assert payload["timeframe"] == timeframe
    assert payload["candles"][-1]["close"] == 9.5
    assert payload["candles"][-1]["provisional"] is False
    assert payload["latest_time"] == "2026-08-27"
    assert {"candles", "indicators", "ma20", "ma50", "ma200", "macd", "rsi", "wave_evidence", "source", "as_of", "latest_time", "provenance"}.issubset(payload)
    assert payload["indicators"]["timeframe"] == timeframe
    assert len(payload["indicators"]["series"]["high"]) == len(payload["candles"])


def test_chart_db_route_does_not_require_legacy_snapshot(monkeypatch):
    connection = _Connection(
        [(datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False)], []
    )
    monkeypatch.setattr(mvp_chart_db, "_get_db_connection", lambda: connection)
    monkeypatch.setattr(mvp_chart_db, "_release_db_connection", lambda pg: None)
    monkeypatch.setattr(mvp_routes, "load_payload", lambda: (_ for _ in ()).throw(
        ValueError("malformed legacy snapshot")
    ))
    handler = type("Handler", (), {
        "wfile": type("Writer", (), {"write": lambda self, data: setattr(self, "body", data)})(),
        "send_response": lambda self, status: setattr(self, "status", status),
        "send_header": lambda self, *args: None,
        "end_headers": lambda self: None,
    })()

    assert mvp_routes.handle_mvp_api("/api/chart-db/SIS?timeframe=1D", handler)
    assert handler.status == 200
    assert __import__("json").loads(handler.wfile.body)["candles"]


def test_chart_db_route_view_chart_serves_compact_representation(monkeypatch):
    daily = [
        (datetime(2025, 1, 1) + __import__("datetime").timedelta(days=index),
         100 + index, 101 + index, 99 + index, 100.5 + index, 1000 + index, False)
        for index in range(260)
    ]
    connection = _Connection(daily, [])
    monkeypatch.setattr(mvp_chart_db, "_get_db_connection", lambda: connection)
    monkeypatch.setattr(mvp_chart_db, "_release_db_connection", lambda pg: None)
    monkeypatch.setattr(mvp_routes, "load_payload", lambda: {"items": []})
    handler = type("Handler", (), {
        "wfile": type("Writer", (), {"write": lambda self, data: setattr(self, "body", data)})(),
        "send_response": lambda self, status: setattr(self, "status", status),
        "send_header": lambda self, *args: None,
        "end_headers": lambda self: None,
    })()

    assert mvp_routes.handle_mvp_api("/api/chart-db/TEAM?timeframe=1D&view=chart", handler)
    payload = __import__("json").loads(handler.wfile.body)
    assert handler.status == 200
    assert len(payload["candles"]) == 120
    series = payload["indicators"]["series"]
    assert "high" not in series
    assert "low" not in series
    assert len(series["ma"]["20"]) == 120
    assert len(series["macd"]["line"]) == 120
    assert len(series["rsi"]) == 120
    assert payload["indicators"]["latest"]["window_summary"]
    assert payload["provenance"]["representation"] == "chart_view"
    assert "ma20" not in payload


def test_chart_db_prefers_canonical_daily_wave_evidence(monkeypatch):
    connection = _Connection(
        [(datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False)], []
    )
    monkeypatch.setattr(mvp_chart_db, "_get_db_connection", lambda: connection)
    canonical = {"symbol": "SIS", "wave": {"evidence_markers": [
        {"timestamp": "2026-08-27", "price": 12, "source": "canonical"}
    ]}, "provenance": {"snapshot_id": "daily:canonical"}}
    response = mvp_chart_db.project_chart_db_response("sis", canonical_item=canonical)
    assert response["wave_evidence"]["markers"] == canonical["wave"]["evidence_markers"]
    assert response["wave_evidence"]["snapshot_id"] == "daily:canonical"


def test_60m_chart_never_emits_daily_wave_markers_or_primary_state(monkeypatch):
    connection = _Connection(
        [(datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False)],
        [(datetime(2026, 8, 27, 5, tzinfo=timezone.utc), 10, 12, 9, 11, 100)],
    )
    monkeypatch.setattr(mvp_chart_db, "_get_db_connection", lambda: connection)
    canonical = {"symbol": "SIS", "wave": {"evidence_markers": [
        {"timestamp": "2026-08-27", "price": 12, "source": "canonical"}
    ], "primary_state": "EARLY_WAVE_3"}}

    response = mvp_chart_db.project_chart_db_response("sis", timeframe="60M",
                                                       canonical_item=canonical)
    evidence = response["wave_evidence"]
    assert evidence["markers"] == []
    assert evidence["status"] == "NOT_VERIFIED"
    assert "primary_state" not in evidence
    assert evidence["mapping"]["daily"] != "authoritative"


def test_chart_db_marks_missing_canonical_daily_evidence_neutral_and_audit_only(monkeypatch):
    connection = _Connection(
        [(datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False)], []
    )
    monkeypatch.setattr(mvp_chart_db, "_get_db_connection", lambda: connection)
    monkeypatch.setattr("mvp_chart_db.build_legacy_chart_wave_evidence",
                        lambda candles, timeframe, as_of: {"mapping": {"daily": "legacy_fallback"}, "markers": []})
    response = mvp_chart_db.project_chart_db_response("sis")
    evidence = response["wave_evidence"]
    assert evidence["status"] == "NOT_VERIFIED"
    assert evidence["markers"] == []
    assert evidence["mapping"]["daily"] == "not_verified"
    assert evidence["audit_compatibility"]["status"] == "audit_only"
    assert evidence["audit_compatibility"]["source"] == "legacy_chart_generated"
    assert evidence["audit_compatibility"]["wave_evidence"]["mapping"]["daily"] == "legacy_fallback"


class _Connection:
    def __init__(self, daily, intraday):
        self.cursor_value = _DailyAndIntradayCursor(daily, intraday)

    def cursor(self):
        return self.cursor_value


@pytest.mark.parametrize("timeframe", ["1D", "1W", "60M", "1M"])
def test_canonical_chart_read_result_normalizes_each_supported_timeframe(timeframe):
    if timeframe == "60M":
        cursor = _Cursor([
            (datetime(2026, 8, 27, 6, 0, tzinfo=timezone.utc), 10.5, 12, 10, 11.5, 200, True),
            (datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc), 10, 11, 9, 10.5, 100, False),
        ])
    else:
        cursor = _DailyAndIntradayCursor([
            (datetime(2026, 8, 27), 10, 11, 9, 10.5, 100, False),
            (datetime(2026, 8, 26), 9, 10, 8, 9.5, 90, False),
        ], [])

    result = read_chart_result(cursor, "SIS", timeframe, 30)

    assert isinstance(result, ChartReadResult)
    assert result.source_timeframe == timeframe
    assert [c["date"] for c in result.candles] == sorted(c["date"] for c in result.candles)
    assert result.as_of == result.candles[-1]["date"]
    assert result.latest_time == ("2026-08-27T06:00:00+00:00" if timeframe == "60M" else "2026-08-27")
    assert result.provisional is (timeframe == "60M")
    assert result.candles[-1]["provisional"] is (timeframe == "60M")


def test_chart_db_wave_evidence_keeps_legacy_marker_shape_while_read_is_separate(monkeypatch):
    connection = _Connection(
        [(datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False)], []
    )
    monkeypatch.setattr(mvp_chart_db, "_get_db_connection", lambda: connection)

    response = mvp_chart_db.project_chart_db_response("sis", timeframe="1D")

    assert set((response or {})["wave_evidence"]) >= {"timeframe", "markers", "mapping"}
    assert response["wave_evidence"]["timeframe"] == "daily"
    assert isinstance(response["wave_evidence"]["markers"], list)


@pytest.mark.parametrize("timeframe", ["1D", "1W"])
def test_chart_route_returns_provenance_for_non_empty_daily_timeframes(monkeypatch, timeframe):
    daily = [(datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False)]
    intraday = [(datetime(2026, 8, 27, 5, tzinfo=timezone.utc), 10, 12, 9, 11, 100)]
    connection = _Connection(daily, intraday)
    monkeypatch.setattr(app, "get_pg", lambda: connection)

    response = app.chart_data("sis", timeframe=timeframe, limit=30)

    assert response["timeframe"] == timeframe
    assert response["provenance"] == {
        "source": "price_data + intraday_price_data",
        "intraday_current_session": True,
        "daily_decision_source": "price_data EOD",
        "note": "current-session 60m aggregate is provisional/as-is; not official EOD",
    }
