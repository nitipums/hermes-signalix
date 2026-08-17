import pandas as pd

import screening


class _Pg:
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

    def load(symbol, pg=None, lookback=None, market="TH"):
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
