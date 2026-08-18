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
