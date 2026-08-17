"""P0 contracts: dashboard first paint must not require per-symbol DB queries."""
import json


def test_progressive_overview_preserves_persisted_scan_contract(tmp_path):
    from app import dashboard_overview_payload

    source = tmp_path / "scan.json"
    source.write_text(json.dumps({
        "scan_time": "2026-08-14T12:00:00Z",
        "groups": {"waiting_breakout": [{"symbol": "PTT", "close": 30.0}]},
    }))

    payload = dashboard_overview_payload(source)

    assert payload["scan_time"] == "2026-08-14T12:00:00Z"
    assert payload["groups"]["waiting_breakout"][0]["symbol"] == "PTT"


def test_us_overview_is_a_separate_lightweight_market_payload(tmp_path):
    from app import us_watchlist_overview_payload

    source = tmp_path / "us.json"
    source.write_text(json.dumps({
        "universe": "us_ai_buildout", "market": "US", "benchmark_symbol": "SPY",
        "source": "bootstrap", "results": [{"symbol": "MU", "close": 100.0}],
    }))

    payload = us_watchlist_overview_payload(source)

    assert payload["market"] == "US"
    assert payload["universe"] == "us_ai_buildout"
    assert payload["cards"] == [{"symbol": "MU", "close": 100.0}]
