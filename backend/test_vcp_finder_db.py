from datetime import date, timedelta
from unittest.mock import MagicMock

from vcp_finder_db import (
    _classify_types,
    _daily_context_from_rows,
    _daily_metrics_from_rows,
    find_vcp_universe_60m,
)


def test_type_classification_is_separate_and_deterministic():
    result = {"state": "READY", "price": {"last_close": 100, "pivot_high": 98, "distance_to_pivot_pct": 0.5, "invalidation": 95, "atr14": 2}, "pattern": {"pivots": [{"kind": kind} for kind in ("high", "low", "high", "low", "high")], "base_depth_pct": 10, "latest_contraction_pct": 5}, "evidence": {"prior_trend_pass": True, "price_contraction_pass": True, "base_pass": True, "leg_volume_pass": True}}
    out = _classify_types(result, ath_context={"observed_ath_all_time": 99}, listing_context=None)
    assert out["vcp_type"]["base_type"] == "low_cheat_vcp"
    assert out["vcp_type"]["entry_profile"] == "early_entry"
    assert out["vcp_type"]["overlays"] == ["break_ath"]
    assert out["state"] == "READY"


def test_new_stock_requires_listing_evidence():
    result = {"state": "FORMING", "price": {"last_close": 10}, "pattern": {}, "evidence": {}}
    out = _classify_types(result, ath_context={}, listing_context=None)
    assert "new_stock" not in out["vcp_type"]["types"]


def test_low_cheat_requires_non_failed_early_entry_state():
    result = {
        "state": "FAILED",
        "price": {"last_close": 100, "pivot_high": 98, "distance_to_pivot_pct": 0.5, "invalidation": 95, "atr14": 2},
        "pattern": {"pivots": [{"kind": kind} for kind in ("high", "low", "high", "low", "high")], "base_depth_pct": 10, "latest_contraction_pct": 5},
        "evidence": {"prior_trend_pass": True, "price_contraction_pass": True, "base_pass": True, "leg_volume_pass": True},
    }

    out = _classify_types(result, ath_context={"observed_ath_all_time": 99}, listing_context=None)

    assert out["vcp_type"]["base_type"] == "standard_vcp"
    assert out["vcp_type"]["entry_profile"] == "standard_entry"
    assert out["state"] == "FAILED"


def test_low_cheat_requires_healthy_trend_and_tight_risk():
    result = {
        "state": "READY",
        "price": {"last_close": 100, "pivot_high": 99, "distance_to_pivot_pct": 0.5, "invalidation": 80, "atr14": 2},
        "pattern": {"pivots": [{"kind": kind} for kind in ("high", "low", "high", "low", "high")], "base_depth_pct": 10, "latest_contraction_pct": 5},
        "evidence": {"prior_trend_pass": False, "price_contraction_pass": True, "base_pass": True, "leg_volume_pass": True},
    }

    out = _classify_types(result, ath_context={}, listing_context=None)

    assert out["vcp_type"]["base_type"] is None
    assert out["vcp_type"]["type_evidence"]["healthy_trend_60m"] is False
    assert out["vcp_type"]["type_evidence"]["tight_risk_pass"] is False



def test_universe_keeps_missing_and_insufficient_symbols(monkeypatch):
    pg = MagicMock()
    monkeypatch.setattr("vcp_finder_db.active_ord_symbols", lambda _: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr("vcp_finder_db.load_vcp_60m_rows", lambda *_args, **_kwargs: {
        "AAA": [], "BBB": [], "CCC": []
    })
    result = find_vcp_universe_60m(pg)
    assert result["universe"] == {"eligible": 3, "evaluated": 3, "returned": 3}
    assert [x["symbol"] for x in result["results"]] == ["AAA", "BBB", "CCC"]
    assert all(x["state"] == "NOT_VERIFIED" for x in result["results"])
    assert all(x["provenance"]["legacy_scanner_used"] is False for x in result["results"])
    assert all("vcp_type" in x for x in result["results"])
    assert all("type_policy_version" in x["vcp_type"] for x in result["results"])


def test_daily_metrics_latest_close_is_newest_independent_of_input_order():
    rows = [
        {"date": date(2026, 8, 27), "close": 47.0, "volume": 10},
        {"date": date(2026, 8, 25), "close": 45.5, "volume": 20},
        {"date": date(2026, 8, 26), "close": 46.0, "volume": 30},
    ]

    out = _daily_metrics_from_rows([rows[1], rows[0], rows[2]])

    assert out["latest_daily_close"] == 47.0
    assert out["as_of"] == "2026-08-27"
    assert out["avg_trade_value_20"] == (45.5 * 20 + 47.0 * 10 + 46.0 * 30) / 3
    assert out["bars"] == 3


def test_daily_context_is_chronological_independent_of_input_order():
    start = date(2026, 6, 1)
    rows = [
        {"date": start + timedelta(days=i), "close": float(100 + i)}
        for i in range(40)
    ]

    out = _daily_context_from_rows(rows[::2] + rows[1::2])

    assert out["as_of"] == str(start + timedelta(days=39))
    assert out["bars"] == 40
    assert out["return_20d_pct"] == (139.0 / 119.0 - 1) * 100
    assert out["recent_avg_20"] == sum(range(120, 140)) / 20
    assert out["prior_avg_20"] == sum(range(100, 120)) / 20
    assert out["trend_pass"] is True
