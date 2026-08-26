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
    assert 'var requestedTimeframe = item.vcp_result ? "60M" : chartTimeframe;' in js
    assert "setChartTimeframeButtons(requestedTimeframe)" in js
    assert "position:absolute; right:8px" not in (ROOT / "styles.css").read_text(encoding="utf-8")


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
