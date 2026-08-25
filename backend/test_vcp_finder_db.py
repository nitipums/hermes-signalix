from unittest.mock import MagicMock

from vcp_finder_db import find_vcp_universe_60m


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
