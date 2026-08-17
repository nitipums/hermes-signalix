from us_data import normalize_yahoo_chart


def test_normalize_yahoo_chart_adjusts_ohlc_for_a_stock_split():
    payload = {
        "chart": {"result": [{
            "timestamp": [1704067200],
            "indicators": {"quote": [{"open": [100], "high": [110], "low": [90], "close": [100], "volume": [5]}],
                           "adjclose": [{"adjclose": [50]}]},
        }]}
    }

    rows = normalize_yahoo_chart("TEST", payload)

    assert rows == [("US", "TEST", "2024-01-01", 50.0, 55.0, 45.0, 50.0, 5.0, "ORD")]
