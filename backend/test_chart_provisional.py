"""Focused contract tests for provisional 60m chart bars."""
from datetime import datetime, timezone

import pytest

import app
from app import fetch_chart_rows


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


class _Connection:
    def __init__(self, daily, intraday):
        self.cursor_value = _DailyAndIntradayCursor(daily, intraday)

    def cursor(self):
        return self.cursor_value


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
