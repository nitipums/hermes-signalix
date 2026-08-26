from unittest.mock import MagicMock

from vcp_finder_db import _classify_types, find_vcp_universe_60m


def test_type_classification_is_separate_and_deterministic():
    result = {"state": "READY", "price": {"last_close": 100, "pivot_high": 98, "distance_to_pivot_pct": 2}, "pattern": {"pivots": [{"kind": "high"}], "base_depth_pct": 10, "latest_contraction_pct": 5}, "evidence": {"price_contraction_pass": True, "leg_volume_pass": True}}
    out = _classify_types(result, ath_context={"observed_ath_all_time": 99}, listing_context=None)
    assert out["vcp_type"]["base_type"] == "low_cheat_vcp"
    assert out["vcp_type"]["overlays"] == ["break_ath"]
    assert out["state"] == "READY"


def test_new_stock_requires_listing_evidence():
    result = {"state": "FORMING", "price": {"last_close": 10}, "pattern": {}, "evidence": {}}
    out = _classify_types(result, ath_context={}, listing_context=None)
    assert "new_stock" not in out["vcp_type"]["types"]



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
