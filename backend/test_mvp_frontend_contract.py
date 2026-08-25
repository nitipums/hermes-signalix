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
    assert "position:absolute; right:8px" not in (ROOT / "styles.css").read_text(encoding="utf-8")


def test_chart_contract_has_real_layers_and_fail_closed_runtime():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    for marker in ('data-layer="candles"', 'data-layer="volume"', 'data-layer="ma"', 'data-layer="rsi"'):
        assert marker in html
    for marker in ("function drawChart", "chartLayers.candles", "chartLayers.volume", "chartLayers.ma", "chartLayers.rsi"):
        assert marker in js
    assert "tryFixtureShortlist" not in js
    assert "tryFixtureExplorer" not in js
