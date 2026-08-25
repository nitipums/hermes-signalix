import json
from pathlib import Path

from marginable import filter_items, load_marginable_data, lookup
from mvp_api import project_explorer_response


ROOT = Path(__file__).parent


def test_pdf_dataset_contract_and_counts():
    data = load_marginable_data()
    assert data["schema_version"] == "signalix.marginable.v1"
    assert data["effective_date"] == "2026-08-25"
    assert len(data["securities"]) == 353
    assert sum(r["instrument_type"] == "ORD" for r in data["securities"]) == 323
    assert sum(r["instrument_type"] == "DR" for r in data["securities"]) == 30
    assert {r["margin_rate_pct"] for r in data["securities"]} == {50, 60, 70, 80, 100}


def test_rights_markers_are_preserved():
    assert lookup("ADVANC")["margin_rate_pct"] == 50
    assert lookup("ADVANC")["can_short"] is True
    assert lookup("INET")["can_buy"] is False
    assert lookup("INET")["can_short"] is False
    assert lookup("AIE")["margin_rate_pct"] == 100


def test_filter_default_is_krungsri_and_all_is_explicit():
    items = [{"symbol": "ADVANC"}, {"symbol": "ZZZ_NOT_IN_LIST"}]
    assert [x["symbol"] for x in filter_items(items, "krungsri")] == ["ADVANC"]
    assert [x["symbol"] for x in filter_items(items, "non_marginable")] == ["ZZZ_NOT_IN_LIST"]
    assert len(filter_items(items, "all")) == 2


def test_explorer_response_exposes_margin_fields_and_filter_metadata():
    items = [{"symbol": "ADVANC", "stage": "S2_uptrend", "close": 100}]
    result = project_explorer_response(items, marginable_filter="krungsri")
    assert result["total_items"] == 1
    assert result["marginable_filter"] == "krungsri"
    assert result["marginable_source"]["effective_date"] == "2026-08-25"
    card = result["items"][0]
    assert card["margin_rate_pct"] == 50
    assert card["marginable"]["can_short"] is True


def test_frontend_has_both_filters_and_drawer_permissions():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
    assert 'id="shortlist-marginable"' in html
    assert 'id="explorer-marginable"' in html
    assert 'id="drawer-margin-rights"' in html
    assert 'marginable=' in js
    assert "marginPermissions" in js
