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

    def execute(self, query, params):
        pass

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
    assert {"candles", "ma20", "ma50", "ma200", "macd", "rsi", "wave_evidence", "source", "as_of", "latest_time", "provenance"}.issubset(payload)


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


def test_chart_db_uses_named_legacy_wave_fallback_when_canonical_evidence_unavailable(monkeypatch):
    connection = _Connection(
        [(datetime(2026, 8, 27), 9, 10, 8, 9.5, 900, False)], []
    )
    monkeypatch.setattr(mvp_chart_db, "_get_db_connection", lambda: connection)
    monkeypatch.setattr("mvp_chart_db.build_legacy_chart_wave_evidence",
                        lambda candles, timeframe, as_of: {"mapping": {"daily": "legacy_fallback"}, "markers": []})
    response = mvp_chart_db.project_chart_db_response("sis")
    assert response["wave_evidence"]["mapping"]["daily"] == "legacy_fallback"


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
