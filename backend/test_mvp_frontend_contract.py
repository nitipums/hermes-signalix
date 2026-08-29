"""Focused source contract tests for the owner-only MVP frontend."""
from pathlib import Path


ROOT = Path(__file__).parent / "frontend"


def test_stage_colors_and_rising_lane_are_declared():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'id="shortlist-rising"' in html
    assert 'id="explorer-stage"' in html
    for token in ("--s1", "--s2", "--s3", "--s4", "stage--s1", "stage--s2", "stage--s3", "stage--s4"):
        assert token in css
    assert "function isRising" in js
    assert "S2_uptrend" in js


def test_explorer_filters_are_sent_to_api():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'params += "&stage="' in js
    assert 'params += "&search="' in js
    assert "explorer-apply" not in html
    assert "addEventListener(\"change\"" in js


def test_chart_timeframes_are_real_controls_not_labels_only():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    for timeframe in ("1D", "1W", "60M"):
        assert f'data-timeframe="{timeframe}"' in html
    assert "?timeframe=" in js
    assert "chart-timeframe" in js
    assert 'let chartTimeframe = "60M"' in js
    assert 'var requestedTimeframe = isVcp ? "60M" : chartTimeframe;' in js
    assert "setChartTimeframeButtons(requestedTimeframe, isVcp)" in js
    assert "position:absolute; right:8px" not in (ROOT / "styles.css").read_text(encoding="utf-8")


def test_drawer_timeframe_switch_preserves_surface_item_and_discards_stale_chart():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "var currentItem = chartSymbol ? drawerItemForSymbol(chartSymbol) : null" in js
    assert "openDrawer(currentItem || {symbol: chartSymbol, name: chartSymbol}, chartSymbol, drawerSymbols, drawerIndex)" in js
    assert "var chartCache = {}" in js
    assert "chartCache[chartKey]" in js
    assert "requestSeq !== chartRequestSeq" in js
    assert "VCP charts support 60M only" in js
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "function drawerItemForSymbol(symbol)" in js
    assert "Both VCP surfaces feed the same drawer contract" in js
    assert "item = drawerItemForSymbol(symbol);" in js
    assert "openDrawer(item, symbol, navSymbols, navIndex);" in js
    assert "change_pct: vp.change_pct" in js
    assert "avgDailyValue20: (vd.daily_metrics || {}).avg_trade_value_20" in js


def test_vcp_confirmed_quality_gaps_are_decision_visible():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "function vcpQualityFlags(result)" in js
    assert 'flags.push("NO VOLUME DRY-UP")' in js
    assert 'flags.push("DAILY CONTEXT FAIL")' in js
    assert 'return "TRIGGER CONFIRMED · QUALITY INCOMPLETE"' in js
    assert "vcpDecisionLabel(vr)" in js
    assert 'item.vcp_result ? item.action : shortAction(item.action || item.phase)' in js
    assert '"TRIGGER CONFIRMED · QUALITY INCOMPLETE"' in js


def test_vcp_type_filter_and_badges_are_presentation_only():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'id="daily-vcp-type"' in html
    assert 'id="vcp-type"' in html
    assert 'value="low_cheat_vcp">Low-Cheat' in html
    assert 'value="standard_vcp">VCP' in html
    assert 'return base === "low_cheat_vcp" ? "Low-Cheat"' in js
    assert "vcpTypeMatches" in js
    assert '"STANDARD"' not in js
    assert '"FAILED", "STALE", "NOT_VERIFIED"' in js
    assert "No Low-Cheat setups in focused review." in js
    assert "Switch to All states." in js


def test_daily_vcp_default_filters_are_literal_presentation_filters():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "dom.dailyFilterMarginable.checked" in js
    assert "dom.dailyFilterTradeValue.checked" in js
    assert "dom.dailyFilterPrice.checked" in js
    assert (
        "if (dom.dailyFilterTradeValue.checked && "
        "!(Number(metrics.avg_trade_value_20) > 10000000)) return false;"
    ) in js
    assert "&& !r.reviewable" not in js


def test_freshness_surface_keeps_daily_and_intraday_timestamps_separate():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    source = (Path(__file__).parent / "build_dashboard.py").read_text(encoding="utf-8")
    assert "intraday_fetched_at" in source
    assert "setFreshness(fStatus, freshness.data_fetched_at || freshness.as_of, freshness.intraday_fetched_at)" in js
    assert 'scan_time: vm.fetch_completed_at || vm.as_of' in js
    assert "60m " in js


def test_unavailable_hour_chart_is_explicit_not_blank():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "60m unavailable · Daily EOD remains the decision source" in js
    assert 'chart.provenance && chart.provenance.note' in js
    assert "AbortController" in js
    assert "chartRequestSeq" in js


def test_chart_contract_has_real_layers_and_fail_closed_runtime():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    for marker in ("function drawChart", "chartLayers.candles", "chartLayers.volume", "chartLayers.ma", "chartLayers.rsi"):
        assert marker in js
    for marker in ("decisionLine", 'data-timeframe="60M"', 'data-timeframe="1D"', 'data-timeframe="1W"'):
        assert marker in html or marker in js
    for marker in ('data-layer="candles"', 'data-layer="volume"', 'data-layer="ma"', 'data-layer="rsi"'):
        assert marker not in html
    assert 'id="drawer-indicator-legend"' not in html
    assert "tryFixtureShortlist" not in js
    assert "tryFixtureExplorer" not in js


def test_mobile_interactive_targets_are_touch_safe():
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    assert ".chart-timeframe { min-height:44px; min-width:44px;" in css

    assert ".explorer-control select, .explorer-control input { min-height:44px;" in css
    assert ".vcp-table th:first-child, .vcp-table td:first-child { width:26%;" in css
    assert ".vcp-table th:not(:first-child), .vcp-table td:not(:first-child) { width:18.5%;" in css
    assert ".vcp-row__symbol { flex-direction:column; align-items:flex-start;" in css
