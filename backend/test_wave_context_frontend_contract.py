"""Focused contracts for the presentation-only Wave Context surface."""
from pathlib import Path
import subprocess


ROOT = Path(__file__).parent / "frontend"


def test_wave_context_route_is_explicit_and_classic_mvp_mapping_is_preserved():
    source = (Path(__file__).parent / "mvp_server.py").read_text(encoding="utf-8")
    assert 'path in ("/mvp", "/mvp/")' in source
    assert 'self.path = "/index.html" + suffix' in source
    assert 'path in ("/wave-context", "/wave-context/")' in source
    assert 'self.path = "/wave-context.html" + suffix' in source
    classic = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "wave-context.js" not in classic
    assert "wave-context.css" not in classic


def test_surface_uses_shared_canonical_contract_and_aggregates_every_page():
    client = (ROOT / "canonical-client.js").read_text(encoding="utf-8")
    js = (ROOT / "wave-context.js").read_text(encoding="utf-8")
    assert "fetchAllCandidates" in client
    assert "while (page <= totalPages)" in client
    assert "all.length !== first.total_items" in client
    assert 'data.universe_filter !== DEFAULT_UNIVERSE' in client
    assert "window.SignalixCanonicalClient.fetchAllCandidates" in js
    assert "window.SignalixCanonicalClient.dailyMarkers" in js
    assert "classifier" not in js.lower()


def test_context_labels_actionability_and_timeframes_are_source_bounded():
    client = (ROOT / "canonical-client.js").read_text(encoding="utf-8")
    html = (ROOT / "wave-context.html").read_text(encoding="utf-8")
    js = (ROOT / "wave-context.js").read_text(encoding="utf-8")
    for value in ("WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION",
                  "EARLY_WAVE_3", "WAVE_3_CONTINUATION", "WAVE_4_CORRECTION",
                  "WAVE_5_ADVANCE", "UNKNOWN", "WAVE_3_EXTENDED"):
        assert value in js or value in html
    assert 'lane==="REVIEW_NOW"' in js
    assert "Non-actionable context · backend lane" in js
    assert 'marker.timeframe === "daily"' in client
    assert 'marker.timestamp != null' in client
    assert 'fetch("/api/symbol/"+encodeURIComponent(item.symbol))' in js
    assert '/api/chart-db/"+encodeURIComponent(item.symbol)+"?timeframe=1D' in js
    assert "no 60m marker is plotted on this Daily chart" in html
    assert "canonical API has no source-linked transition history" in js


def test_loading_empty_blocked_error_retry_and_responsive_contracts_exist():
    html = (ROOT / "wave-context.html").read_text(encoding="utf-8")
    css = (ROOT / "wave-context.css").read_text(encoding="utf-8")
    js = (ROOT / "wave-context.js").read_text(encoding="utf-8")
    for marker in ('id="loading"', 'id="empty"', 'id="error"', 'id="error-retry"',
                   'id="blocked"', 'id="chart-empty"'):
        assert marker in html
    assert 'showOnly("error")' in js and 'showOnly("empty")' in js
    assert "DATA_BLOCKED" in js and 'status.daily_freshness==="stale"' in js
    assert "@media(max-width:420px)" in css
    assert "overflow-x:hidden" in css
    assert "minmax(0,1fr)" in css


def test_wave_context_javascript_parses():
    subprocess.run(
        ["node", "--check", str(ROOT / "wave-context.js")],
        check=True, capture_output=True, text=True,
    )
