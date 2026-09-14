"""Focused contracts for the bounded canonical /mvp UI feedback pass."""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).parent / "frontend"


def extract(source, name):
    start = source.index("function " + name)
    brace = source.index("{", start)
    depth = 0
    quote = None
    escaped = False
    for index in range(brace, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(name)


def run(functions, expression):
    script = "\n".join(functions) + "\nconsole.log(JSON.stringify(" + expression + "));"
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_canonical_surface_removes_research_copy_and_drawer_sections():
    html = (ROOT / "index.html").read_text()
    shared = (ROOT / "shared-drawer.js").read_text()
    assert "Marginable long universe · Daily trend/wave" not in html
    for label in ("drawer-chart-status", "drawer-chart-context", "chart-wave-evidence",
                  "chart-wave-explanation", "Evidence details and provenance",
                  "drawer-evidence-details"):
        assert label not in shared
    assert 'data-timeframe="1D"' in shared and 'data-timeframe="60M"' in shared


def test_advanced_filters_are_collapsed_and_live_refresh_is_explicitly_opt_in():
    html = (ROOT / "index.html").read_text()
    js = (ROOT / "app.js").read_text()
    advanced = html[html.index('id="daily-setup-advanced"'):html.index('</details>', html.index('id="daily-setup-advanced"'))]
    assert '<details id="daily-setup-advanced"' in html
    assert "<summary>Advanced filters</summary>" in advanced
    for control in ("daily-filter-marginable", "daily-filter-trade-value", "daily-filter-price",
                    "daily-vcp-decision-state", "daily-vcp-decision", "daily-vcp-quality"):
        assert f'id="{control}"' in advanced
    assert 'id="daily-setup-live-refresh"' in advanced
    assert "Live refresh (opt in)" in advanced
    assert 'liveRefreshTimer = liveRefreshEnabled ? setTimeout' in js
    assert "!dailySetupHasActiveBoundary()" in js
    assert "setInterval(function()" not in js


def test_canonical_setup_path_guards_legacy_controls_and_keeps_server_filters():
    js = (ROOT / "app.js").read_text()
    assert 'dom.dailySetupSector && dom.dailySetupSector.value.trim()' in js
    assert 'dom.dailySetupLane && dom.dailySetupLane.value !== "ALL"' in js
    assert 'dom.dailyFilterMarginable && dom.dailyFilterMarginable.checked' in js
    assert 'if (dom.dailyVcpType && !vcpTypeMatches' in js
    assert 'if (dom.dailySetupPrev)' in js and 'if (dom.dailySetupNext)' in js


def test_sort_is_quote_change_descending_then_symbol_and_identity_deduplicates():
    app = (ROOT / "app.js").read_text()
    stable = extract(app, "stableSetupCandidateOrder")
    identity = extract(app, "identityName")
    items = [
        {"symbol": "ZZZ", "name": "ZZZ", "quote": {"change_pct": 2}},
        {"symbol": "AAA", "name": "Alpha", "quote": {"change_pct": 2}},
        {"symbol": "MID", "name": "MID", "quote": {"change_pct": 8}},
        {"symbol": "NIL", "name": "NIL", "quote": {}},
    ]
    assert run([stable], "stableSetupCandidateOrder(" + json.dumps(items) + ").map(function(i){return i.symbol;})") == ["MID", "AAA", "ZZZ", "NIL"]
    assert run([identity], "[identityName({symbol:'AAA',name:'AAA'}), identityName({symbol:'AAA',name:'Alpha'})]") == ["", "Alpha"]


def test_navigation_uses_rendered_collection_and_reconciles_page_changes():
    app = (ROOT / "app.js").read_text()
    shared = (ROOT / "shared-drawer.js").read_text()
    assert "items: navSymbols.map(function(navSymbol)" in app
    assert "drawerItems.find(function(candidate)" in app
    assert "updateNavigation(drawerSymbols, drawerItems)" in app
    assert "function updateSharedDrawerNavigation(symbols, items)" in shared
    assert "drawerIndex = drawerSymbols.indexOf(currentSymbol)" in shared


def test_shared_drawer_binds_rr_to_markup_id_for_canonical_open_path():
    shared = (ROOT / "shared-drawer.js").read_text()
    bind_dom = extract(shared, "bindDom")
    assert 'drawerRR:"drawer-rr"' in bind_dom
    assert 'id="drawer-rr"' in shared
    assert "dom.drawerRR.textContent = item.rr" in shared


def test_shared_drawer_normalizes_object_trend_for_readable_display():
    shared = (ROOT / "shared-drawer.js").read_text()
    normalize = extract(shared, "normalizeDrawerTrendDisplay")
    cases = [
        ("state", {"trend": {"state": "UPTREND", "primary_state": "ignored"}, "stage": "S2_uptrend"}, {"state": "envelope"}),
        ("primary_state", {"trend": {"primary_state": "EMERGING_UPTREND"}}, {"trend": {"primary_state": "ENVELOPE_TREND"}}),
        ("stage", {"trend": {}, "stage": "S2_uptrend"}, {"trend": {}}),
        ("string", {"trend": "S2_uptrend"}, {"trend": "S2_uptrend"}),
        ("not verified", {"trend": {}}, {"trend": {}}),
    ]
    expected = ["UPTREND", "EMERGING_UPTREND", "S2_uptrend", "S2_uptrend", "Not verified"]
    actual = [run([normalize], "normalizeDrawerTrendDisplay(" + json.dumps(item) + ", " + json.dumps(envelope) + ")")
              for _, item, envelope in cases]
    assert actual == expected
    assert "dom.drawerTrend.textContent = shadow ? shadowMainTrend.replace" in shared or "shadowMainTrendDisplay" in shared


def test_chart_markers_remain_source_linked_and_are_not_derived_in_browser():
    shared = (ROOT / "shared-drawer.js").read_text()
    marker_fn = extract(shared, "dailyWaveMarkersForChart")
    draw = extract(shared, "drawChart")
    assert "marker.timestamp != null" in marker_fn and "marker.price != null" in marker_fn
    assert "chartTimestampKey(c.date) === chartTimestampKey(marker.timestamp)" in draw
    for forbidden in ("marker.date", "marker.close", "marker.high", "marker.low"):
        assert forbidden not in draw


def test_shared_drawer_supports_horizontal_swipe_navigation_without_breaking_scroll():
    shared = (ROOT / "shared-drawer.js").read_text()
    assert "touchstart" in shared
    assert "touchend" in shared
    assert "navigateSharedDrawer(1)" in shared
    assert "navigateSharedDrawer(-1)" in shared
    assert "Math.abs(deltaX)" in shared
    assert "Math.abs(deltaY)" in shared
    assert 'envelope.source === "trend-map" ? null' in shared


def test_chart_layout_keeps_all_mobile_panels_inside_canvas():
    shared = (ROOT / "shared-drawer.js").read_text()
    layout = extract(shared, "chartLayout")
    result = run([layout], "chartLayout(360)")
    assert result["top"] + result["priceH"] + result["volH"] + result["macdH"] + result["rsiH"] <= 360
    assert result["rsiLabelY"] <= 360
    assert result["priceH"] < 205
