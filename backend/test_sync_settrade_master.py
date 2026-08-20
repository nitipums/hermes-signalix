from sync_settrade_master import parse_stock_master


def test_dashboard_rebuild_hook_reports_success(monkeypatch):
    class FakeBuilder:
        @staticmethod
        def build():
            return {"securities": 904}

    monkeypatch.setitem(__import__("sys").modules, "build_dashboard", FakeBuilder)
    from sync_settrade_master import rebuild_dashboard_after_master_sync
    assert rebuild_dashboard_after_master_sync() == {
        "dashboard_rebuilt": True,
        "dashboard_securities": 904,
    }


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
