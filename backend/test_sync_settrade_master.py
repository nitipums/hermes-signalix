from sync_settrade_master import parse_stock_master


def test_parse_only_set_mai_common_stock():
    rows = parse_stock_master({"securitySymbols": [
        {"symbol": "AOT", "market": "SET", "securityType": "S"},
        {"symbol": "88TH", "market": "mai", "securityType": "S"},
        {"symbol": "3BBIF", "market": "SET", "securityType": "S", "isIFF": True},
        {"symbol": "AOT-W1", "market": "SET", "securityType": "W"},
        {"symbol": "DR1", "market": "SET", "securityType": "X"},
        {"symbol": "", "market": "SET", "securityType": "S"},
    ]})
    assert [r["symbol"] for r in rows] == ["3BBIF", "88TH", "AOT"]
    assert all(r["source"] == "settrade_stock_master" for r in rows)
