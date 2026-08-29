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
    assert 'var requestedTimeframe = chartTimeframe;' in js
    assert "setChartTimeframeButtons(requestedTimeframe)" in js
    assert "position:absolute; right:8px" not in (ROOT / "styles.css").read_text(encoding="utf-8")


def test_drawer_timeframe_switch_preserves_surface_item_and_discards_stale_chart():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "var currentItem = chartSymbol ? drawerItemForSymbol(chartSymbol) : null" in js
    assert "openDrawer(currentItem || {symbol: chartSymbol, name: chartSymbol}, chartSymbol, drawerSymbols, drawerIndex)" in js
    assert "var chartCache = {}" in js
    assert "chartCache[chartKey]" in js
    assert "requestSeq !== chartRequestSeq" in js
    assert "if (!cachedChart) {" in js
    assert "VCP charts support 60M only" not in js
    assert "btn.disabled = !supported" not in js
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "function drawerItemForSymbol(symbol)" in js
    assert "Both VCP surfaces feed the same drawer contract" in js
    assert "item = drawerItemForSymbol(symbol);" in js
    assert "openDrawer(item, symbol, navSymbols, navIndex);" in js
    assert "change_pct: vp.change_pct" in js
    assert "avgDailyValue20: (vd.daily_metrics || {}).avg_trade_value_20" in js


def test_vcp_drawer_fetches_canonical_metadata_without_overwriting_vcp_fields():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "function mergeCanonicalDailyMetadata(item, canonical)" in js
    assert '"high52", "low52", "ath_high", "ath_low", "rr", "target"' in js
    assert 'fetch("/api/symbol/" + encodeURIComponent(symbol), {signal: chartController.signal})' in js
    assert "mergeCanonicalDailyMetadata(item, fresh)" in js
    assert "requestSeq !== chartRequestSeq || chartSymbol !== symbol" in js
    assert "VCP owns intraday decision fields" in js
    assert "function vcpChartOverlay(item)" in js
    assert "trigger: breakout.required_close != null ? breakout.required_close : item.trigger" in js
    assert "stop: price.invalidation != null ? price.invalidation : item.risk_stop" in js
    assert "function mergeChartDecisionOverlay(chart, item)" in js
    assert "mergeChartDecisionOverlay(chart, item);" in js
    assert "Required close" in js


def test_vcp_drawer_distinguishes_pending_metadata_from_unverified_evidence():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "function displayMetadataValue(value, pending)" in js
    assert 'return pending ? "Loading…" : "Unavailable";' in js
    assert "if (item.vcp_result) item._canonicalMetadataPending = true;" in js
    assert "item._canonicalMetadataPending = false;" in js
    assert "formatRange(item.high52, item.low52, metadataPending)" in js
    assert "formatRange(item.ath_high, item.ath_low, metadataPending)" in js
    assert "Metadata failure is distinct from VCP evidence being NOT_VERIFIED." in js


def test_daily_vcp_surfaces_rejection_telemetry():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "rejection_counts" in js
    assert "rejected:" in js


def test_vcp_drawer_keeps_not_verified_for_decision_evidence():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'NOT_VERIFIED: "NOT VERIFIED"' in js
    assert 'var state = result.state || "NOT_VERIFIED";' in js
    assert 'data.feed_status || "NOT_VERIFIED"' in js

    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "function vcpQualityFlags(result)" in js
    assert 'flags.push("NO VOLUME DRY-UP")' in js
    assert 'flags.push("DAILY CONTEXT FAIL")' in js
    assert 'return "TRIGGER CONFIRMED · QUALITY INCOMPLETE"' in js
    assert "action: vcpPrimaryStatus(vr)" in js
    assert "action: vcpPrimaryStatus(vcp)" in js
    assert "action: vcpDecisionLabel(vr)" not in js
    assert "action: vcpDecisionLabel(vcp)" not in js
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


def test_vcp_defaults_to_all_states_and_keeps_focused_query_explicit():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert '<option value="ALL" selected>All states</option>' in html
    assert '<option value="actionable">Focused review · actionable + watch</option>' in html
    assert 'var selected = dom.vcpState.value || "ALL";' in js
    assert 'if (selected === "actionable") endpoint += "&focused=true";' in js


def test_vcp_cards_label_52_week_high_overlay_and_distance_without_state_change():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'if (type === "near_52w_high") { hasNear52wHigh = true; return; }' in js
    assert 'var high52Label = hasNear52wHigh || (Number.isFinite(high52Distance) && high52Distance >= -5 && high52Distance <= 0) ? "NEAR 52W HIGH" : "52W HIGH";' in js
    assert 'result.state || "NOT_VERIFIED"' in js


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
    assert ".vcp-table th:first-child, .vcp-table td:first-child { width:42%; min-width:0; }" in css
    assert ".vcp-table th:nth-child(2), .vcp-table td:nth-child(2) { width:18%; }" in css
    assert ".vcp-row__symbol { flex-direction:column; align-items:flex-start;" in css


def test_watchlist_table_and_filters_are_contained_on_mobile():
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    assert ".vcp-table-wrap { max-width:100%; overflow:hidden;" in css
    assert ".vcp-table { width:100%; max-width:100%;" in css
    assert "min-width:0; padding:10px 12px;" in css
    assert "text-overflow:ellipsis;" in css
    assert ".vcp-row__symbol { display:flex; align-items:flex-start; gap:8px; min-width:0; max-width:100%; overflow:hidden; }" in css
    assert ".vcp-card__tags { display:flex; flex-wrap:wrap; gap:4px; min-width:0; max-width:100%;" in css
    assert ".watchlist-default-filters { display:flex; align-items:center; flex-wrap:wrap;" in css
    assert ".watchlist-default-filters > label { display:inline-flex; align-items:center;" in css


def test_mobile_vcp_table_keeps_status_readable_and_rr_in_detail_drawer():
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert '.vcp-card__decision { white-space:normal; overflow:visible;' in css
    assert '.vcp-table .vcp-row__rr { display:none; }' in css
    assert '.vcp-table th:first-child, .vcp-table td:first-child { width:42%; min-width:0; }' in css
    assert 'class="vcp-row__details" aria-label="View details for ' in js
    assert 'class="vcp-row__rr">' in js
    assert '<th class="vcp-row__rr">R/R</th>' in js
    assert '<div class="drawer-field"><dt>R/R</dt><dd id="drawer-rr">–</dd></div>' in (ROOT / "index.html").read_text(encoding="utf-8")


def test_vcp_tables_use_canonical_rr_and_compact_tags():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    assert "function vcpRiskReward(result)" in js
    assert "var value = result && result.rr;" in js
    assert "risk_reward_ratio" not in js
    assert 'Number(result.margin_rate_pct).toFixed(0) + "%"' in js
    assert '"NEAR 52W HIGH"' in js
    assert ".vcp-table .vcp-card__tags" in css


def test_vcp_filter_events_render_the_selected_client_state():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "dom.dailyVcpType.addEventListener(\"change\", loadDailyVcp)" in js
    assert "dom.vcpState.addEventListener(\"change\", loadVcp)" in js
    assert "dom.vcpType.addEventListener(\"change\", loadVcp)" in js
    assert "results = results.filter(priceMatches)" in js
    assert "if (marginRates.length) results = results.filter" in js
    assert 'if (dom.vcpFilterApply) dom.vcpFilterApply.addEventListener("click", function() {' in js
    assert 'if (!apply && surface === "vcp") return;' in js
    assert 'updateMarginRates("vcp", true);' in js


def test_vcp_drawer_membership_and_chart_overlay_contracts():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    db = (Path(__file__).parent / "vcp_finder_db.py").read_text(encoding="utf-8")
    assert 'index_membership: vr.index_membership || []' in js
    assert "var decisionLabelYs = [];" in js
    assert "Math.abs(previous - labelY) < 14" in js
    assert "FROM index_memberships" in db
    assert 'result["index_membership"] = memberships.get' in db


def test_vcp_primary_cards_use_unified_state_decision_and_evidence():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    for status in (
        'FORMING · WAIT',
        'READY · WAIT',
        'CONFIRMED · REVIEW',
        'EXTENDED · WAIT',
        'INVALIDATED · AVOID',
    ):
        assert status in js
    assert 'var state = decision.state || (result && result.state);' in js
    assert 'if (decision.data_sufficient === false) return "—";' in js
    assert 'return state + " · " + decision.decision' in js
    assert 'evidence.trigger' in js
    assert 'evidence.invalidation' in js
    assert 'vcpPrimaryStatus(result)' in js
    assert 'vcpPrimaryEvidence(result)' in js
    assert 'var groups = {};' in js[js.index('function renderDailyVcpWatchlist'):js.index('function loadDailyVcp')]
    assert 'escapeHTML(status)' in js[js.index('function renderDailyVcpWatchlist'):js.index('function loadDailyVcp')]
    assert 'BREAKOUT_WATCH: ["READY", "WAIT"]' in js
    assert 'NEAR_TRIGGER: ["READY", "WAIT"]' in js
    assert 'FAILED: ["INVALIDATED", "AVOID"]' in js
    assert 'if (["FORMING", "READY", "CONFIRMED", "EXTENDED", "INVALIDATED"].indexOf(state) < 0) return "—";' in js
    assert 'var trigger = evidence.trigger == null ? "—"' in js
    assert 'var invalidation = evidence.invalidation == null ? "—"' in js
    assert 'if (evidence.trigger == null && evidence.invalidation == null) return "—";' in js
    assert '(price.last_close == null || price.last_close === "" ? "—" : displayValue(price.last_close))' in js
    primary_group = js[js.index('function vcpDisplayGroup'):js.index('function vcpEmptyState')]
    for legacy in (
        'TRIGGER CONFIRMED',
        'PRICE-VOLUME BREAKOUT',
        'PIVOT TOUCH',
        'DO NOT CHASE',
        'STALE DATA',
        'NOT VERIFIED',
        'BREAKOUT_WATCH · WAIT',
        'NEAR_TRIGGER · WAIT',
        'FAILED · AVOID',
        'DATA UNAVAILABLE',
    ):
        assert legacy not in primary_group
    primary_helpers = js[js.index('function vcpPrimaryStatus'):js.index('function vcpCard')]
    for implementation_label in ('DATA UNAVAILABLE', 'NOT_VERIFIED', 'STALE DATA', 'INSUFFICIENT DATA'):
        assert implementation_label not in primary_helpers
    daily_render = js[js.index('function renderDailyVcpWatchlist'):js.index('function loadDailyVcp')]
    for implementation_label in ('ACTION / REVIEW', 'NEAR TRIGGER · VOLUME CHECK', 'BREAKOUT WATCH · INTRABAR'):
        assert implementation_label not in daily_render


def test_vcp_primary_render_cannot_read_legacy_decision_fields():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    primary = js[js.index("function vcpPrimaryStatus"):js.index("function vcpEmptyState")]
    for legacy_field in (
        "trade_readiness",
        "daily_state",
        "setup_proximity",
        "action_queue",
        "shortlist_lane",
        "review_lane",
        "insurance_context_watch",
        "late_watch",
    ):
        assert legacy_field not in primary
    assert "function vcpDisplayGroup(result)" in js
    display_group = js[js.index("function vcpDisplayGroup"):js.index("function vcpEmptyState")]
    assert "return vcpPrimaryStatus(result);" in display_group


def test_daily_watchlist_consolidates_duplicate_primary_status_sections():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    render = js[js.index("function renderDailyVcpWatchlist"):js.index("function loadDailyVcp")]

    # Compatibility lanes are grouped into shared primary-status buckets before
    # the ordered section render, so READY · WAIT cannot render twice.
    assert render.index("var groups = {};") < render.index("order.forEach(function(key)")
    assert render.index("items.forEach(function(item)") < render.index("[\"FORMING · WAIT\"")
    assert render.count("html += '<section class=\"vcp-lane\">") == 1
    assert "(groups[status] || (groups[status] = [])).push(item);" in render
    assert "groupCaps[status] = (groupCaps[status] || 0) + Number(cap);" in render
