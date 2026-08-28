"""Focused contract tests for provisional 60m chart bars."""
from datetime import datetime, timezone

from app import fetch_chart_rows


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def execute(self, query, params):
        self.queries.append((query, params))

    def fetchall(self):
        return self.rows


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
