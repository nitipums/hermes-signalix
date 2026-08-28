import json
from pathlib import Path

from marginable import filter_items, load_marginable_data, lookup, normalize_rates
from mvp_api import project_explorer_response
from mvp_api import filter_price_band


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


def test_multiple_margin_rates_are_normalized_and_applied():
    assert normalize_rates("60,50,60,invalid") == [50, 60]
    items = [{"symbol": "ADVANC"}, {"symbol": "CREDIT"}, {"symbol": "AIE"}]
    result = filter_items(items, "krungsri", "50,60")
    assert [x["symbol"] for x in result] == ["ADVANC", "CREDIT"]


def test_explorer_response_exposes_margin_fields_and_filter_metadata():
    items = [{"symbol": "ADVANC", "stage": "S2_uptrend", "close": 100}]
    result = project_explorer_response(items, marginable_filter="krungsri")
    assert result["total_items"] == 1
    assert result["marginable_filter"] == "krungsri"
    assert result["marginable_source"]["effective_date"] == "2026-08-25"
    card = result["items"][0]
    assert card["margin_rate_pct"] == 50
    assert card["marginable"]["can_short"] is True




def test_price_band_filter_is_presentation_only():
    items = [{"symbol": "LOW", "close": 1.99}, {"symbol": "MID", "close": 5}, {"symbol": "HIGH", "close": 10.01}]
    assert [x["symbol"] for x in filter_price_band(items, "below_2")] == ["LOW"]
    assert [x["symbol"] for x in filter_price_band(items, "2_to_10")] == ["MID"]
    assert [x["symbol"] for x in filter_price_band(items, "above_10")] == ["HIGH"]


def test_frontend_has_both_filters_and_drawer_permissions():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
    assert 'id="shortlist-marginable"' in html
    assert 'id="explorer-marginable"' in html
    assert 'id="shortlist-price-band"' in html
    assert 'id="explorer-price-band"' in html
    assert 'id="vcp-price-band"' in html
    assert 'data-surface="vcp"' in html
    assert 'class="margin-rate-toggle"' in html
    assert '<dt>Marginable</dt>' in html
    # Decision levels live as dashed chart overlays; duplicate metric boxes
    # below the chart were intentionally removed from the MVP drawer.
    assert '<dt>Trigger</dt>' not in html
    assert '<dt>Stop</dt>' not in html
    assert 'decisionLine(chart.trigger' in js
    assert 'decisionLine(chart.stop' in js
    assert 'decisionLine(chart.target' in js
    assert 'drawer-margin-rights' not in html
    assert 'id="drawer-prev"' in html
    assert 'id="drawer-next"' in html
    assert 'decision-card__risk' in js
    assert 'visibleDrawerSymbols' in js
    assert 'touchstart' in js
    assert 'ArrowLeft' in js
    assert 'marginable=' in js
    assert "margin_rates=" in js
    assert "%Margin " in js
