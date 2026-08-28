"""MVP chart candle ordering contracts."""

from datetime import date

from mvp_chart_db import _chart_source, _fetch_candles


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))

    def fetchall(self):
        return list(self.rows)


def test_chart_source_matches_timeframe_storage_boundary():
    assert _chart_source("60M") == "intraday_price_data"
    for timeframe in ("1D", "1W", "1M"):
        assert _chart_source(timeframe) == "price_data"


def test_week_and_month_candles_are_ascending():
    rows = [
        (date(2026, 8, 25), 3, 4, 2, 3, 100),
        (date(2026, 8, 24), 2, 3, 1, 2, 90),
        (date(2026, 8, 3), 1, 2, 0.5, 1.5, 80),
        (date(2026, 8, 2), 1, 1.5, 0.8, 1.0, 70),
    ]
    for timeframe in ("1W", "1M"):
        result = _fetch_candles(_Cursor(rows), "TEST", timeframe=timeframe, limit=20)
        dates = [x["date"] for x in result]
        assert dates == sorted(dates)


def test_daily_and_hourly_candles_are_ascending():
    rows = [
        ("2026-08-25T10:00:00+00:00", 3, 4, 2, 3, 100),
        ("2026-08-25T09:00:00+00:00", 2, 3, 1, 2, 90),
    ]
    for timeframe in ("1D", "60M"):
        result = _fetch_candles(_Cursor(rows), "TEST", timeframe=timeframe, limit=20)
        dates = [x["date"] for x in result]
        assert dates == sorted(dates)
