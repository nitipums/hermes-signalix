import pandas as pd
from unittest.mock import MagicMock

import screening


class _Pg:
    def cursor(self):
        cur = MagicMock()
        # symbol_master may not exist in the unit-test fixture; return no
        # excluded symbols and no stored price rows so the scan uses only the
        # monkeypatched load_symbol / benchmark data. to_regclass() must
        # return a falsy row tuple, not None, to match psycopg2 semantics.
        cur.fetchall.return_value = []
        cur.fetchone.return_value = (None,)
        return cur

    def close(self):
        pass


def _bars(close=100.0):
    index = pd.date_range("2025-01-01", periods=300, freq="B")
    values = [close + i * 0.1 for i in range(300)]
    return pd.DataFrame(
        {"Open": values, "High": [v + 1 for v in values], "Low": [v - 1 for v in values],
         "Close": values, "Volume": [1_000_000] * 300}, index=index
    )


def _short_bars(close=100.0):
    index = pd.date_range("2025-01-01", periods=40, freq="B")
    values = [close + i * 0.1 for i in range(40)]
    return pd.DataFrame(
        {"Open": values, "High": [v + 1 for v in values], "Low": [v - 1 for v in values],
         "Close": values, "Volume": [1_000_000] * 40}, index=index
    )


def test_scan_universe_uses_explicit_symbols_and_benchmark(monkeypatch):
    bars = _bars()
    requested = []

    def load(symbol, pg=None, lookback=None, market="TH", **kwargs):
        requested.append((symbol, market))
        return bars

    monkeypatch.setattr(screening, "load_symbol", load)
    monkeypatch.setattr(screening, "annotate_all_time_highs", lambda *args, **kwargs: None)

    results, near = screening.scan_universe(
        min_conditions=0,
        pg=_Pg(),
        market="US",
        benchmark_symbol="SPY",
        symbols=("MU",),
        min_price=None,
        min_today_trade_value=None,
    )

    assert [row["symbol"] for row in results] == ["MU"]
    assert near == []
    assert requested[0] == ("SPY", "US")
    assert ("MU", "US") in requested


def test_scan_universe_keeps_short_daily_history_fail_closed(monkeypatch):
    daily = _short_bars()
    captured = []
    intraday_calls = []

    def load(symbol, pg=None, lookback=None, market="TH", **kwargs):
        if symbol == "SPY":
            return _bars()
        return daily

    def intraday(*args, **kwargs):
        intraday_calls.append((args, kwargs))
        raise AssertionError("Daily scan must not use 60m as a history fallback")

    monkeypatch.setattr(screening, "load_symbol", load)
    monkeypatch.setattr(screening, "load_symbol_intraday", intraday)
    monkeypatch.setattr(
        screening,
        "annotate_all_time_highs",
        lambda pg, rows, **kwargs: captured.extend(rows),
    )

    results, near = screening.scan_universe(
        min_conditions=0,
        pg=_Pg(),
        market="US",
        benchmark_symbol="SPY",
        symbols=("NEW",),
        min_price=None,
        min_today_trade_value=None,
    )

    assert intraday_calls == []
    assert near == []
    assert [row["symbol"] for row in results] == ["NEW"]
    assert [row["symbol"] for row in captured] == ["NEW"]
    row = results[0]
    assert row["analysis_status"] == "INSUFFICIENT_HISTORY"
    assert row["trend_source"] == "daily"
    assert row["trend_template"]["conditions_met"] == 0
    assert row["trade_readiness"]["status"] == "INSUFFICIENT_HISTORY"


def test_scan_universe_keeps_missing_daily_history_fail_closed(monkeypatch):
    intraday_calls = []
    captured = []

    def load(symbol, pg=None, lookback=None, market="TH", **kwargs):
        return _bars() if symbol == "SPY" else None

    def intraday(*args, **kwargs):
        intraday_calls.append((args, kwargs))
        raise AssertionError("Daily scan must not use 60m as a missing-data fallback")

    monkeypatch.setattr(screening, "load_symbol", load)
    monkeypatch.setattr(screening, "load_symbol_intraday", intraday)
    monkeypatch.setattr(
        screening,
        "annotate_all_time_highs",
        lambda pg, rows, **kwargs: captured.extend(rows),
    )

    results, near = screening.scan_universe(
        min_conditions=0,
        pg=_Pg(),
        market="US",
        benchmark_symbol="SPY",
        symbols=("MISSING",),
        min_price=None,
        min_today_trade_value=None,
    )

    assert intraday_calls == []
    assert near == []
    assert [row["symbol"] for row in results] == ["MISSING"]
    assert [row["symbol"] for row in captured] == ["MISSING"]
    assert results[0]["analysis_status"] == "INSUFFICIENT_HISTORY"
    assert results[0]["close"] is None
    assert results[0]["last_date"] is None
    assert results[0]["trend_source"] == "daily"


def test_scan_universe_normal_daily_row_does_not_change_without_fallback(monkeypatch):
    daily = _bars(close=123.0)
    intraday_calls = []

    def load(symbol, pg=None, lookback=None, market="TH", **kwargs):
        return daily

    def intraday(*args, **kwargs):
        intraday_calls.append((args, kwargs))
        raise AssertionError("normal Daily rows must not consult intraday data")

    monkeypatch.setattr(screening, "load_symbol", load)
    monkeypatch.setattr(screening, "load_symbol_intraday", intraday)
    monkeypatch.setattr(screening, "annotate_all_time_highs", lambda *args, **kwargs: None)

    results, near = screening.scan_universe(
        min_conditions=0,
        pg=_Pg(),
        market="US",
        benchmark_symbol="SPY",
        symbols=("NORMAL",),
        min_price=None,
        min_today_trade_value=None,
    )

    assert intraday_calls == []
    assert near == []
    assert len(results) == 1
    assert results[0]["symbol"] == "NORMAL"
    assert "analysis_status" not in results[0]
    assert results[0]["trend_source"] == "daily"
    assert results[0]["close"] == 152.9
