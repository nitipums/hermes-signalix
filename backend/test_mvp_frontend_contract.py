"""Focused source contract tests for the owner-only MVP frontend."""
from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).parent / "frontend"


def _extract_function(source, name):
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
    raise AssertionError("unclosed JavaScript function: " + name)


def _run_node(functions, expression):
    client = (ROOT / "canonical-client.js").read_text(encoding="utf-8")
    script = "var window = globalThis;\n" + client + "\n" + "\n".join(functions) + "\nconsole.log(JSON.stringify(" + expression + "));"
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_v2_serving_contract_has_explicit_marginable_long_requests_and_metadata():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert js.count("universe=marginable_long") >= 1
    for marker in (
        "decision_shadow_v2", "decision_lane", "actionability",
        "eligible_count", "universe_filter", "margin_source_document",
        "margin_effective_date", "selected",
    ):
        assert marker in js
    assert "Marginable long universe" in html
    assert 'id="daily-vcp-retry"' in html


def test_request_cache_script_loads_before_app_script():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    cache_script = html.index('<script src="request_cache.js"></script>')
    app_script = html.index('<script src="app.js"></script>')
    assert cache_script < app_script


def test_v2_primary_label_and_drawer_keep_raw_lifecycle_evidence():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'return decisionLane(result) + " · " + actionability(result);' in js
    assert 'id="drawer-v2-decision"' in html
    assert 'id="drawer-raw-state"' in html
    assert 'item.vcp_result.state || "NOT_VERIFIED"' in js


def test_v2_success_empty_and_transport_error_states_are_distinct():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "zero candidates matched the current presentation filters" in js
    assert 'show(dom.dailyVcpError)' in js
    assert 'dom.dailyVcpErrorMsg.textContent = "Unable to load setup candidates: " + err.message' in js
    assert 'dom.vcpErrorMsg.textContent = "Unable to load VCP Finder: " + err.message' in js


def test_daily_wave_presentation_uses_canonical_state_and_compact_confidence():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    wave_state = _extract_function(js, "canonicalWaveState")
    wave_confidence = _extract_function(js, "compactWaveConfidence")
    states = 'var canonicalDailyWaveStates = ["WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3", "WAVE_3_CONTINUATION", "WAVE_4_CORRECTION", "WAVE_5_ADVANCE"];'
    context = _extract_function(js, "waveContextForItem")
    assert _run_node(
        [states, context, wave_state, wave_confidence],
        "({state: canonicalWaveState({wave: {context:{mapped_state:'EARLY_WAVE_3', confidence:'MEDIUM'}}}), confidence: compactWaveConfidence({wave: {context:{mapped_state:'EARLY_WAVE_3', confidence:'MEDIUM'}}})})",
    ) == {"state": "EARLY_WAVE_3", "confidence": "MEDIUM"}
    assert _run_node(
        [states, context, wave_state, wave_confidence],
        "({unknown: canonicalWaveState({wave: {context:{mapped_state:'NOT_VERIFIABLE'}}}), wave2: canonicalWaveState({wave: {context:{mapped_state:'WAVE_2_FORMING'}}}), confidence: compactWaveConfidence({wave: {context:{confidence:'UNSURE'}}})})",
    ) == {"unknown": "Unknown / Not verified", "wave2": "WAVE_2_FORMING", "confidence": "NOT_VERIFIED"}
    assert 'Daily context ' in js and 'Confidence ' in js


def test_daily_wave_bucket_consumes_all_mapped_context_and_collapses_unmapped_values():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    helper = _extract_function(js, "setupCandidateWaveBucket")
    states = ["WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3", "WAVE_3_CONTINUATION", "WAVE_4_CORRECTION", "WAVE_5_ADVANCE"]
    declaration = 'var canonicalDailyWaveStates = ' + json.dumps(states) + ';'
    context = _extract_function(js, "waveContextForItem")
    result = _run_node([declaration, context, helper], "[" + ",".join(
        "setupCandidateWaveBucket({wave:{context:{mapped_state:" + json.dumps(state) + "}}})" for state in states
    ) + ", setupCandidateWaveBucket({wave:{primary_state:'WAVE_5_ADVANCE'}}), setupCandidateWaveBucket({})]")
    assert result == states + ["UNKNOWN", "UNKNOWN"]


def test_t08_wave_filter_composes_with_search_and_lane_without_inference():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    helper = _extract_function(js, "setupCandidateMatchesToolbar")
    bucket = _extract_function(js, "setupCandidateWaveBucket")
    states = 'var canonicalDailyWaveStates = ["WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3", "WAVE_3_CONTINUATION", "WAVE_4_CORRECTION", "WAVE_5_ADVANCE"];'
    context = _extract_function(js, "waveContextForItem")
    dom = 'var dom = {dailySetupSearch:{value:"alpha"}, dailySetupLane:{value:"DAILY_CANDIDATE"}, dailySetupWave:{value:"EARLY_WAVE_3"}};'
    expression = "[setupCandidateMatchesToolbar({symbol:'ALPHA',name:'Alpha Co',decision_lane:'DAILY_CANDIDATE',wave:{context:{mapped_state:'EARLY_WAVE_3'}}}), setupCandidateMatchesToolbar({symbol:'ALPHA',name:'Alpha Co',decision_lane:'DAILY_CANDIDATE',wave:{context:{mapped_state:'WAVE_1_ADVANCE'}}}), setupCandidateMatchesToolbar({symbol:'BETA',name:'Beta Co',decision_lane:'DAILY_CANDIDATE',wave:{context:{mapped_state:'EARLY_WAVE_3'}}})]"
    assert _run_node([states, context, bucket, dom, helper], expression) == [True, False, False]


def test_t08_grouping_has_canonical_wave_order_unknown_bucket_and_stable_symbol_order():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    helper = _extract_function(js, "groupSetupCandidates")
    bucket = _extract_function(js, "setupCandidateWaveBucket")
    stable = _extract_function(js, "stableSetupCandidateOrder")
    states = 'var canonicalDailyWaveStates = ["WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3", "WAVE_3_CONTINUATION", "WAVE_4_CORRECTION", "WAVE_5_ADVANCE"];'
    context = _extract_function(js, "waveContextForItem")
    items = "[{symbol:'ZZZ',decision_lane:'DAILY_CANDIDATE',wave:{context:{mapped_state:'EARLY_WAVE_3'}}},{symbol:'AAA',decision_lane:'DAILY_CANDIDATE',wave:{context:{mapped_state:'WAVE_3_CONTINUATION'}}},{symbol:'ONE',decision_lane:'DAILY_CANDIDATE',wave:{context:{mapped_state:'WAVE_1_ADVANCE'}}},{symbol:'BAD',decision_lane:'DAILY_CANDIDATE',wave:{context:{mapped_state:'NOPE'}}}]"
    result = _run_node([states, context, bucket, stable, helper], "(function(g){return {order:g.waveOrder, early:g.waveGroups.EARLY_WAVE_3[0].symbol, one:g.waveGroups.WAVE_1_ADVANCE[0].symbol, unknown:g.waveGroups.UNKNOWN.map(function(x){return x.symbol;})};})(groupSetupCandidates(" + items + "))")
    assert result == {"order": ["WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3", "WAVE_3_CONTINUATION", "WAVE_4_CORRECTION", "WAVE_5_ADVANCE", "UNKNOWN"], "early": "ZZZ", "one": "ONE", "unknown": ["BAD"]}


def test_t08_wave_control_and_filter_render_preserve_counts_empty_and_drawer_reconciliation():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'id="daily-setup-wave"' in html
    assert "Unknown / Not verified" in html and "Unknown / Not verified" in js
    assert html.count('value="EARLY_WAVE_3"') == 1
    assert html.count('value="WAVE_3_CONTINUATION"') == 1
    for context_state in ("WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "WAVE_4_CORRECTION", "WAVE_5_ADVANCE"):
        assert html.count('value="' + context_state + '"') == 1
    assert "laneItems.length + ' / ' + Number(laneTotals[lane] || 0)" in js
    assert "No setup candidates matched the current presentation filters." in js
    assert 'dom.dailySetupWave.addEventListener("change"' in js
    assert "reconcileDailyDrawerNavigation();" in js
    assert '#panel-daily-vcp' in js and '[data-symbol].setup-candidate-card' in js


def test_review_cockpit_primary_toolbar_is_lane_wave_only_and_cards_have_compact_risk_direction_fields():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    toolbar = html[html.index('id="daily-setup-toolbar"'):html.index('</div>', html.index('id="daily-setup-toolbar"')) + 6]
    assert 'id="daily-setup-search"' not in toolbar
    assert 'id="daily-setup-refresh"' not in toolbar
    assert 'id="daily-setup-lane"' in toolbar and 'id="daily-setup-wave"' in toolbar
    assert 'summary>More filters</summary>' in html
    card = _extract_function(js, "setupCandidateCard")
    for token in ("Current", "Entry", "Invalidation", "R:R", "setup-candidate__confidence", "Bullish", "Bearish"):
        assert token in card
    assert 'id="drawer-chart-context"' in html
    assert "chart.provenance && (chart.provenance.source || chart.provenance.interval)" in js


def test_daily_wave_card_and_drawer_keep_daily_structural_provenance_separate_from_60m():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'id="drawer-wave"' in html
    assert 'id="drawer-wave-confidence"' in html
    assert 'id="drawer-wave-source"' in html
    assert 'Daily structural' in html
    card = _extract_function(js, "setupCandidateCard")
    assert 'canonicalWaveState(item)' in card
    assert 'compactWaveConfidence(item)' in card
    drawer = _extract_function(js, "renderDrawerDetail")
    assert 'dom.drawerWave.textContent = canonicalWaveState(item)' in drawer
    assert 'dom.drawerWaveSource.textContent = waveContextPresentation(item).source' in drawer
    assert 'setup.minor_structure' not in drawer
    assert '60m' in js


def test_canonical_chart_overlay_uses_trade_stop_not_thesis_invalidation():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    overlay = _extract_function(js, "canonicalChartOverlay")
    result = _run_node(
        [overlay],
        'canonicalChartOverlay({setup: {trigger: 12, invalidation: 8, trade_stop: 10, target_1: 20}})',
    )
    assert result == {"trigger": 12, "stop": 10, "target": 20}


def test_stage_colors_and_rising_lane_are_declared():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'id="shortlist-rising"' not in html
    assert 'id="explorer-stage"' not in html
    for token in ("--s1", "--s2", "--s3", "--s4", "stage--s1", "stage--s2", "stage--s3", "stage--s4"):
        assert token in css
    assert "function isRising" in js
    assert "S2_uptrend" in js


def test_mobile_freshness_stays_inside_viewport_and_ellipsizes():
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    mobile = css[css.index("@media (max-width: 620px)"):]
    assert ".freshness" in mobile
    assert "box-sizing: border-box" in mobile
    assert "padding-right: 4px" in mobile
    assert "overflow: hidden" in mobile
    assert "text-overflow: ellipsis" in css


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
    assert 'let chartTimeframe = "1D"' in js
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


def test_daily_vcp_renders_explicit_event_watch_lane_as_watch_only():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert '"event_watch"' in js
    assert 'event_watch: "EVENT_WATCH"' in js
    assert '"EVENT_WATCH · WATCH_ONLY"' in js
    assert 'var subhead = groupHasCaps[status] ?' in js
    assert 'if (cap != null)' in js


def test_vcp_refreshes_abort_previous_requests_and_ignore_stale_results():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "let dailyVcpRequestSeq = 0;" in js
    assert "let vcpRequestSeq = 0;" in js
    assert "SignalixRequestCache()" in js
    assert "requestFactory(entry.controller.signal)" in (ROOT / "request_cache.js").read_text(encoding="utf-8")
    assert 'var endpoint = "/api/vcp-finder?interval=60m&market=TH&universe=marginable_long";' in js
    assert "if (requestSeq !== dailyVcpRequestSeq) return;" in js
    assert "if (requestSeq !== vcpRequestSeq) return;" in js
    assert 'err.name === "AbortError"' in js


def test_vcp_drawer_keeps_not_verified_for_decision_evidence():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'NOT_VERIFIED: "NOT VERIFIED"' in js
    assert 'return decision.state || "NOT_VERIFIED";' in js
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
    assert 'id="daily-vcp-type"' not in html
    assert 'id="vcp-type"' not in html
    assert 'value="low_cheat_vcp">Low-Cheat' not in html
    assert 'value="standard_vcp">VCP' not in html
    assert 'return base === "low_cheat_vcp" ? "Low-Cheat"' in js
    assert "vcpTypeMatches" in js
    assert '"STANDARD"' not in js
    assert 'var state = canonicalDecisionState(result);' in js
    assert 'canonicalDataSufficiency(result) !== "SUFFICIENT"' in js
    assert "No Low-Cheat setups in focused review." in js
    assert "Switch to All states." in js


def test_vcp_defaults_to_all_states_and_keeps_focused_query_explicit():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'id="panel-vcp"' not in html
    assert 'id="tab-vcp"' not in html
    assert 'var selected = dom.vcpState.value || "ALL";' in js
    assert 'if (selected === "actionable") endpoint += "&focused=true";' in js


def test_vcp_cards_label_52_week_high_overlay_and_distance_without_state_change():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'if (type === "near_52w_high") { hasNear52wHigh = true; return; }' in js
    assert 'var high52Label = hasNear52wHigh || (Number.isFinite(high52Distance) && high52Distance >= -5 && high52Distance <= 0) ? "NEAR 52W HIGH" : "52W HIGH";' in js
    assert 'return decision.state || "NOT_VERIFIED";' in js


def test_daily_vcp_default_filters_are_literal_presentation_filters():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "dom.dailyFilterMarginable.checked" in js
    assert "dom.dailyFilterTradeValue.checked" in js
    assert "dom.dailyFilterPrice.checked" in js
    assert (
        "if (dom.dailyFilterTradeValue.checked && "
        "!(Number(metrics.avg_trade_value_20) > 10000000)) return;"
    ) in js
    assert "&& !r.reviewable" not in js


def test_freshness_surface_keeps_daily_and_intraday_timestamps_separate():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    source = (Path(__file__).parent / "build_dashboard.py").read_text(encoding="utf-8")
    assert "intraday_fetched_at" in source
    assert "setFreshness(freshness.status || \"unknown\", freshness.data_fetched_at || data.as_of, intradayFetchedAt, dailyStatus, intradayStatus)" in js
    assert 'id="freshness-daily"' in html
    assert 'id="freshness-60m"' in html
    assert "Daily EOD" in js
    assert "intraday_60m_as_of" in js
    assert "latest completed 60m candle" in js
    assert "freshness.intraday_fetched_at" in js
    assert 'scan_time: vm.fetch_completed_at || vm.as_of' in js
    assert "60m " in js


def test_setup_candidate_freshness_reports_mixed_timeframes_without_collapsing_to_unavailable():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    normalizer = _extract_function(js, "normalizeFreshnessStatus")
    summary = _extract_function(js, "freshnessSummary")
    assert _run_node([normalizer, summary], 'freshnessSummary("expected_previous_session", "fresh")') == "mixed"
    assert _run_node([normalizer, summary], 'freshnessSummary("unknown", "fresh")') == "partial"
    assert '"Freshness mixed by timeframe"' in js
    assert 'expected previous completed session' in js
    assert 'prefix + ": fresh · "' in js


def test_setup_candidate_freshness_prefers_full_universe_aggregate_statuses():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "freshness.daily_status" in js
    assert "freshness.intraday_status" in js


def test_canonical_setup_refresh_failure_clears_cached_rows_and_retry_is_forced():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "dailyVcpRequests.clear(endpoint);" in js
    assert "hide(dom.dailyVcpContent); show(dom.dailyVcpError);" in js
    assert 'dom.dailyVcpErrorMsg.textContent = "Unable to load setup candidates: " + err.message' in js
    assert 'dom.dailyVcpRetry.addEventListener("click", function() { loadDailyVcp(true); });' in js
    assert "}, !!force);" in js
    # A cached response is still guarded by the request generation, so a
    # stale cached completion cannot repaint rows after a failed refresh.
    assert "cachedRequestSeq === dailyVcpRequestSeq" in js


def test_unavailable_hour_chart_is_explicit_not_blank():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "60m unavailable · Daily EOD remains the decision source" in js
    assert 'chart.provenance && chart.provenance.note' in js
    assert "AbortController" in js
    assert "chartRequestSeq" in js


def test_chart_provisional_status_is_visible_and_timestamped():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'id="drawer-chart-status"' in html
    assert "function renderChartStatus(chart)" in js
    assert "Provisional" in js
    assert "latest_time" in js
    assert "chart.candles[chart.candles.length - 1].provisional" in js


def test_wave_evidence_layer_is_toggleable_and_explains_payload_without_frontend_rules():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'id="chart-wave-evidence"' in html
    assert "chartLayers.waveEvidence" in js
    assert "window.__signalixWaveMarkerHits" in js
    assert "showWaveExplanation" in js
    for field in ("details.rule", "details.evidence", "details.alternative", "details.missing", "details.policy",
                  "marker.timeframe", "marker.source", "marker.confidence", "marker.evidence_refs",
                  "marker.snapshot_identity"):
        assert field in js
    for label in ("How this wave was identified", "Supporting evidence", "Contradicting evidence", "Missing evidence", "Alternative state", "Snapshot identity"):
        assert label in js or label in html
    assert 'timeframe === "1D" ? evidence.daily : timeframe === "60M" ? evidence["60m"] : null' in js


def test_wave_drawer_projects_daily_contract_and_toggle_has_visible_fail_closed_state():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    helper = _extract_function(js, "waveEvidenceForItem")
    result = _run_node([helper], "waveEvidenceForItem({wave:{confidence:'MEDIUM',supporting_evidence:['advance'],contradicting_evidence:[],missing_evidence:['60m'],alternative_state:'WAVE_2_FORMING',snapshot_id:'snap-1'},provenance:{daily_source:'price_data'}})")
    assert result["timeframe"] == "1D"
    assert result["snapshot_identity"] == "snap-1"
    assert result["supporting_evidence"] == ["advance"]
    assert _run_node([helper], "waveEvidenceForItem({wave:[]})") == {}
    assert 'innerHTML = "<strong>Wave Evidence hidden</strong>' in js
    assert "window.__signalixWaveMarkerHits = [];" in js


def test_wave_drawer_projects_evidence_explanation_and_marker_aliases():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    helper = _extract_function(js, "waveEvidenceForItem")
    result = _run_node([helper], "waveEvidenceForItem({wave:{confidence:'HIGH',evidence_explanation:{rule:'Daily close rule',evidence:['close_above_high'],policy:'elliott-v1'},evidence_markers:[{kind:'WAVE_3_CLOSE_CONFIRMATION'}],snapshot_id:'daily:2026-08-31'},provenance:{daily_source:'price_data'}})")
    assert result["rule"] == "Daily close rule"
    assert result["evidence"] == ["close_above_high"]
    assert result["markers"] == [{"kind": "WAVE_3_CLOSE_CONFIRMATION"}]
    assert result["snapshot_identity"] == "daily:2026-08-31"


def test_setup_retry_recovers_from_transport_error_without_changing_contract():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'id="daily-vcp-error"' in html and 'id="daily-vcp-retry"' in html
    assert "show(dom.dailyVcpError)" in js
    assert "loadDailyVcp(true)" in js
    assert "hide(dom.dailyVcpError); hide(dom.dailyVcpContent);" in js
    assert "renderSetupCandidates(data);" in js


def test_wave_marker_window_alignment_uses_source_candle_index():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "var candles = chart.candles.slice(-120);" in js
    assert "var start = chart.candles.length - candles.length;" in js
    assert "sourceIndex < start || sourceIndex >= start + candles.length" in js
    assert "sourceIndex - start" in js
    assert 'if (!marker || typeof marker !== "object" || Array.isArray(marker)) return;' in js
    assert "chartTimestampKey(c.date) === chartTimestampKey(marker.timestamp)" in js
    assert 'marker.timeframe !== "daily" || marker.timestamp == null || marker.price == null' in js
    assert 'chart.timeframe === "1D"' in js


def test_wave_context_cards_and_drawer_consume_nested_contract_without_creating_review_lane():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    context = _extract_function(js, "waveContextForItem")
    presentation = _extract_function(js, "waveContextPresentation")
    wave_state = _extract_function(js, "canonicalWaveState")
    confidence = _extract_function(js, "compactWaveConfidence")
    states = 'var canonicalDailyWaveStates = ["WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3", "WAVE_3_CONTINUATION", "WAVE_4_CORRECTION", "WAVE_5_ADVANCE"];'
    item = "{decision_lane:'DAILY_CANDIDATE',wave:{context:{mapped_state:'WAVE_2_FORMING',secondary_markers:[],confidence:'HIGH',rule_version:'ctx-v1',source_timeframe:'daily',supporting_evidence:['pullback'],contradicting_evidence:['volume'],missing_evidence:['60m'],rationale:'Daily pullback'}}}"
    result = _run_node([states, context, wave_state, confidence, presentation], "waveContextPresentation(" + item + ")")
    assert result["state"] == "WAVE_2_FORMING"
    assert result["source"] == "Daily structural · daily"
    assert result["actionability"] == "Non-actionable context · backend lane DAILY_CANDIDATE"
    assert result["supporting"] == ["pullback"]
    assert "firstDate" not in result and result["transitions"] == []
    assert 'id="drawer-wave-context"' in html
    assert "first_context_date" in js and "Unavailable · no source-linked transition history" in js
    assert 'item.decision_lane === "REVIEW_NOW"' in presentation
    assert "context.mapped_state" in wave_state
    assert "primary_state" not in presentation + wave_state + context


def test_wave_3_extended_is_secondary_only_and_missing_marker_coordinates_are_not_inferred():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    presentation = _extract_function(js, "waveContextPresentation")
    context = _extract_function(js, "waveContextForItem")
    wave_state = _extract_function(js, "canonicalWaveState")
    confidence = _extract_function(js, "compactWaveConfidence")
    states = 'var canonicalDailyWaveStates = ["WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3", "WAVE_3_CONTINUATION", "WAVE_4_CORRECTION", "WAVE_5_ADVANCE"];'
    result = _run_node([states, context, wave_state, confidence, presentation], "waveContextPresentation({decision_lane:'WAIT',wave:{context:{mapped_state:'WAVE_3_CONTINUATION',secondary_markers:['WAVE_3_EXTENDED'],confidence:'HIGH',source_timeframe:'daily'}}})")
    assert result["state"] == "WAVE_3_CONTINUATION"
    assert result["secondary"] == ["WAVE_3_EXTENDED"]
    draw = _extract_function(js, "drawChart")
    assert "marker.timestamp" in draw and "marker.price" in draw
    for forbidden in ("marker.date", "marker.close", "marker.high", "marker.label.split", "item.high52"):
        assert forbidden not in draw


def test_daily_marker_legend_and_60m_setup_levels_are_timeframe_separated():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    assert 'id="drawer-chart-legend"' in html
    assert 'data-timeframe="1D">1D' in html
    assert 'data-timeframe="60M">60m' in html
    assert 'if (chart.timeframe === "60M")' in _extract_function(js, "drawChart")
    legend = _extract_function(js, "renderChartLegend")
    assert 'marker.timeframe === "daily"' in legend
    assert "Daily markers unavailable" in legend
    assert "60m trigger / stop / target" in legend
    assert ".wave-chart-legend" in css and "flex-wrap:wrap" in css
    merge = _extract_function(js, "mergeChartDecisionOverlay")
    assert 'chart.wave_evidence = waveEvidenceForItem(item)' in merge
    assert 'timeframe === "1D" && item && item.decision_lane' in merge


def test_canonical_chart_overlay_selects_target_1_without_target_2_fallback():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    overlay = _extract_function(js, "canonicalChartOverlay")
    result = _run_node(
        [overlay],
        "canonicalChartOverlay({setup:{trigger:12, invalidation:10, target_1:20, target_2:30}})",
    )
    assert result["target"] == 20
    missing = _run_node([overlay], "canonicalChartOverlay({setup:{target_2:30}})")
    assert "target" not in missing or missing["target"] is None
    assert "target_2" in overlay  # documented fail-closed rationale


def test_wave_explanation_deduplicates_metadata_and_normalizes_optional_values():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    helper = _extract_function(js, "waveEvidenceText")
    assert _run_node([helper], "waveEvidenceText([null, 'close', {source: 'daily'}])") == 'close · {"source":"daily"}'
    assert _run_node([helper], "waveEvidenceText([])") == "Unavailable"
    explanation = _extract_function(js, "showWaveExplanation")
    assert explanation.count('"<div>Timeframe: "') == 1
    assert explanation.count('"<div>Confidence: "') == 1
    assert explanation.count('"<div>Evidence refs: "') == 1
    assert explanation.count('"<div>Snapshot: "') == 1
    assert "marker.explanation && typeof marker.explanation === \"object\"" in explanation
    assert 'if (!marker || typeof marker !== "object" || Array.isArray(marker)) {' in explanation
    assert 'panel.hidden = true; panel.textContent = ""; return;' in explanation


def test_wave_controls_guard_optional_dom_nodes():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    for listener in ("drawerClose", "drawerOverlay", "drawerPrev", "drawerNext", "drawer", "drawerCanvas", "chartWaveEvidence"):
        assert f"if (dom.{listener})" in js
    assert "if (!dom.drawer) return;" in js


def test_setup_targets_render_ordered_metadata_and_malformed_targets_fail_closed():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "targets = Array.isArray(setup.targets) ? setup.targets : [];" in js
    assert 'target.name === "target_1"' in js
    assert "target1 = firstTarget && firstTarget.price;" in js
    assert 'Target 1 <b>' in js


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
    assert ".vcp-table th:nth-child(2), .vcp-table td:nth-child(2) { width:16%; }" in css
    assert ".vcp-row__symbol-content { flex-direction:column; align-items:flex-start;" in css


def test_watchlist_table_and_filters_are_contained_on_mobile():
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    assert ".vcp-table-wrap { width:100%; max-width:100%; min-width:0; overflow:hidden;" in css
    assert ".vcp-table { display:table; width:100%; max-width:100%;" in css
    assert "min-width:0; max-width:0; padding:10px 12px;" in css
    assert "text-overflow:ellipsis;" in css
    assert ".vcp-row__symbol { display:flex;" not in css
    assert ".vcp-row__symbol-content { display:flex; align-items:flex-start; gap:8px; min-width:0; max-width:100%; overflow:hidden; }" in css
    assert ".vcp-card__tags { display:flex; flex-wrap:wrap; gap:4px; min-width:0; max-width:100%;" in css
    assert ".watchlist-default-filters { display:flex; align-items:center; flex-wrap:wrap;" in css
    assert ".watchlist-default-filters > label { display:inline-flex; align-items:center;" in css


def test_symbol_table_cell_keeps_table_layout_and_inner_content_owns_flex():
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert ".vcp-row__symbol { display:flex;" not in css
    assert ".vcp-row__symbol-content { display:flex;" in css
    assert '<td class="vcp-row__symbol"><div class="vcp-row__symbol-content">' in js
    assert '</div></td>' in js


def test_mobile_vcp_table_keeps_status_readable_and_rr_in_detail_drawer():
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert '.vcp-card__decision { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2;' in css
    assert '.vcp-table .vcp-row__rr { display:none; }' in css
    assert '.vcp-table { table-layout:fixed; }' in css
    assert '.vcp-table th:nth-child(2), .vcp-table td:nth-child(2) { width:16%; }' in css
    assert 'class="vcp-row__details" aria-label="View details for ' in js
    assert 'class="vcp-row__rr">' in js
    assert '<th class="vcp-row__rr">R/R</th>' in js
    assert '<div class="drawer-field"><dt>R/R</dt><dd id="drawer-rr">–</dd></div>' in (ROOT / "index.html").read_text(encoding="utf-8")


def test_mobile_vcp_secondary_evidence_and_freshness_have_containment_contracts():
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    assert ".vcp-card__primary { display:flex; flex-direction:column; width:100%; max-width:100%; min-width:0;" in css
    assert ".vcp-card__primary .vcp-card__evidence { display:block; width:100%; max-width:100%; min-width:0;" in css
    assert "overflow:hidden; text-overflow:ellipsis;" in css
    assert ".freshness { display: flex; align-items: center; gap: 6px; min-width: 0; max-width: 58%;" in css
    assert ".freshness-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }" in css


def test_vcp_mobile_390_contract_uses_fixed_five_column_layout_without_page_overflow():
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "body {" in css and "overflow-x: hidden;" in css
    assert ".vcp-table-wrap { width:100%; max-width:100%; min-width:0; overflow:hidden;" in css
    assert ".vcp-table { display:table; width:100%; max-width:100%;" in css
    assert ".vcp-table th, .vcp-table td { min-width:0; max-width:0;" in css
    assert ".vcp-table { table-layout:fixed; }" in css
    assert ".vcp-table th:nth-child(4), .vcp-table td:nth-child(4) { width:22%; }" in css
    assert 'class="vcp-row__rr">' in js and '<th class="vcp-row__rr">R/R</th>' in js
    assert "<th>%</th>" in js
    assert 'aria-label="View details for ' in js
    assert 'meta name="viewport"' in html


def test_vcp_payloads_are_cached_and_presentation_filters_do_not_duplicate_fetches():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    cache = (ROOT / "request_cache.js").read_text(encoding="utf-8")
    assert "SignalixRequestCache" in cache
    assert "if (!force && Object.prototype.hasOwnProperty.call(cache, key))" in cache
    assert "if (inFlight[key]) inFlight[key].controller.abort();" in cache
    assert "if (force) delete cache[key];" in cache
    assert "if (inFlight[key] === entry) cache[key] = data;" in cache
    assert "if (inFlight[key] === entry) delete inFlight[key];" in cache
    assert "function renderDailyVcpData(data)" in js
    assert "renderVcpData(data);" in js
    assert "loadDailyVcp(true);" in js
    assert 'loadVcp(true);' in js


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
    assert 'dom.dailySetupRefresh.addEventListener("click", function() { loadDailyVcp(true, 1); });' in js
    assert 'dom.dailyVcpType.addEventListener("change", loadDailyVcp)' not in js
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
    assert 'decision_shadow_v2' in js
    assert 'return decisionLane(result) + " · " + actionability(result);' in js
    assert 'function canonicalDecision(result)' in js
    assert 'return canonicalDecisionState(result) + " · " + canonicalDecisionValue(result);' in js
    assert 'canonicalDataSufficiency(result)' in js
    assert 'return "V2 " + decisionLane(result) + " · " + actionability(result)' in js
    assert 'var entry = shadow.entry || {};' in js
    assert 'entry.pivot' in js
    assert 'vcpPrimaryStatus(result)' in js
    assert 'vcpPrimaryEvidence(result)' in js
    assert 'var groups = {};' in js[js.index('function renderDailyVcpWatchlist'):js.index('function loadDailyVcp')]
    assert 'escapeHTML(status)' in js[js.index('function renderDailyVcpWatchlist'):js.index('function loadDailyVcp')]
    assert 'var trigger = entry.pivot == null ? "—"' in js
    assert 'var invalidation = entry.invalidation == null ? "—"' in js
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
    assert 'var legacyPair = canonicalDecisionState(result) + " · " + canonicalDecisionValue(result);' in display_group
    assert 'var pair = decisionLane(result) + " · " + actionability(result);' in display_group
    assert 'return allowed.indexOf(pair) >= 0 ? pair : "UNKNOWN";' in display_group


def test_daily_watchlist_consolidates_duplicate_primary_status_sections():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    render = js[js.index("function renderDailyVcpWatchlist"):js.index("function loadDailyVcp")]

    # Daily lanes are grouped into canonical state buckets before rendering.
    assert render.index("var groups = {};") < render.index("order.forEach(function(key)")
    assert render.index("items.forEach(function(item)") < render.index("[\"REVIEW_NOW · ACTIONABLE_REVIEW\"")
    assert render.count("html += '<section class=\"vcp-lane\">") == 1
    assert "(groups[status] || (groups[status] = [])).push(item);" in render
    assert "groupCaps[status] = (groupCaps[status] || 0) + Number(cap);" in render


def test_canonical_vcp_controls_exist_on_both_surfaces_and_filter_client_side():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    for field in ("decision-state", "decision", "quality"):
        assert f'id="daily-vcp-{field}"' in html
    for field in ("decision-state", "decision", "quality"):
        assert f'id="vcp-{field}"' not in html
    for value in ("ALL", "FORMING", "READY", "CONFIRMED", "EXTENDED", "INVALIDATED", "REVIEW", "WAIT", "AVOID", "PASS", "PARTIAL", "FAIL", "UNKNOWN"):
        assert f'value="{value}"' in html
    assert "function canonicalFilterMatches(result" in js
    assert "canonicalFilterMatches(r, dom.dailyVcpDecisionState, dom.dailyVcpDecision, dom.dailyVcpQuality)" in js
    assert "canonicalFilterMatches(r, dom.vcpDecisionState, dom.vcpDecision, dom.vcpQuality)" in js
    assert 'var results = (data.results || [])' in js
    assert 'results = results.filter(function(r){ return canonicalFilterMatches' in js


def test_daily_watchlist_hides_non_sufficient_data_and_reports_coverage():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'var insufficientCount = 0;' in js
    assert 'if (canonicalDataSufficiency(r) !== "SUFFICIENT") { insufficientCount += 1; return; }' in js
    assert 'hidden: insufficient/unknown data' in js
    assert 'reviewable / ' in js


def test_canonical_card_evidence_and_mobile_controls_are_visible_and_touch_safe():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    assert 'V2 " + decisionLane(result)' in js
    assert 'Structure " + passCount' in js
    assert 'var pair = decisionLane(result) + " · " + actionability(result);' in js
    assert '.watchlist-default-filters select { min-height:44px;' in css
    assert '.explorer-control select, .explorer-control input { min-height:44px;' in css
    assert 'flex-wrap:wrap' in css


def test_vcp_grouping_uses_canonical_state_decision_pairs_on_both_surfaces():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    helper = js[js.index("function vcpDisplayGroup"):js.index("function vcpEmptyState")]
    for pair in (
        "FORMING · WAIT",
        "READY · WAIT",
        "CONFIRMED · REVIEW",
        "EXTENDED · WAIT",
        "INVALIDATED · AVOID",
    ):
        assert f'"{pair}"' in helper
    assert 'return allowed.indexOf(pair) >= 0 ? pair : "UNKNOWN";' in helper
    assert 'var status = vcpDisplayGroup(item);' in js
    assert 'var key = vcpDisplayGroup(result);' in js
    assert '"REVIEW_NOW · ACTIONABLE_REVIEW"' in js
    assert '"DATA_BLOCKED · NO_ACTION"' in js


def test_vcp_type_presentation_fails_closed_on_canonical_data_and_state():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    type_label = js[js.index("function vcpTypeLabel"):js.index("function vcpTypeMatches")]
    assert "var state = canonicalDecisionState(result);" in type_label
    assert 'if (canonicalDataSufficiency(result) !== "SUFFICIENT") return null;' in type_label
    assert 'if (["INVALIDATED", "NOT_VERIFIED"].indexOf(state) >= 0) return null;' in type_label


def test_daily_trade_value_filter_callback_fails_without_return_value():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert (
        "if (dom.dailyFilterTradeValue.checked && "
        "!(Number(metrics.avg_trade_value_20) > 10000000)) return;"
    ) in js
    assert (
        "if (dom.dailyFilterTradeValue.checked && "
        "!(Number(metrics.avg_trade_value_20) > 10000000)) return false;"
    ) not in js


def test_primary_mvp_requests_canonical_setup_candidates_and_renders_layers():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'SignalixCanonicalClient.setupCandidatesRequestKey(dailySetupPage, 50, requestOptions)' in js
    assert "function renderSetupCandidates(data)" in js
    assert "setupCandidateCard" in js
    assert "setupCandidateCard" in js
    assert "Trigger readiness" in js and "Target 1" in js and "Stop" in js


def test_shared_canonical_client_is_loaded_by_both_surfaces_and_owns_policy():
    client = (ROOT / "canonical-client.js").read_text(encoding="utf-8")
    classic = (ROOT / "index.html").read_text(encoding="utf-8")
    wave = (ROOT / "wave-context.html").read_text(encoding="utf-8")
    assert 'window.SignalixCanonicalClient' in client
    assert 'fetchSetupCandidatesPage' in client and 'fetchAllCandidates' in client and 'dailyMarkers' in client
    assert 'setupCandidatesRequestKey' in client
    assert '<script src="canonical-client.js"></script>' in classic
    assert '<script src="canonical-client.js"></script>' in wave
    assert classic.index('canonical-client.js') < classic.index('app.js')
    assert wave.index('canonical-client.js') < wave.index('wave-context.js')
    assert 'var fetchAllCandidates=window.SignalixCanonicalClient.fetchAllCandidates;' in (ROOT / "wave-context.js").read_text(encoding="utf-8")
    assert 'window.SignalixCanonicalClient.markers(item)' in (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'SignalixCanonicalClient.setupCandidatesRequestKey(dailySetupPage, 50, requestOptions)' in (ROOT / "app.js").read_text(encoding="utf-8")


def test_t03_compact_card_keeps_decision_hierarchy_and_moves_evidence_to_drawer():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    card = _extract_function(js, "setupCandidateCard")
    assert 'class="setup-candidate__decision"' in card
    assert 'class="setup-candidate__readiness"' in card
    assert 'class="setup-candidate__plan"' in card
    for marker in ("Trigger readiness", "R:R", "Target 1", "Stop"):
        assert marker in card
    for evidence_marker in ("setup-candidate__evidence", "Market / sector", "Peers", "VCP bonus", "as of"):
        assert evidence_marker not in card
    assert "function openDrawer" in js
    assert "waveEvidenceForItem" in js and "formatProvenance" in js
    assert ".setup-candidate__plan {" in css
    assert ".setup-candidate__plan span {" in css
    assert ".setup-candidate__plan b {" in css


def test_setup_candidate_review_uses_explicit_compact_toolbar_and_collapsed_advanced_filters():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'id="daily-setup-toolbar"' in html
    assert 'id="daily-setup-search"' in html
    assert 'id="daily-setup-lane"' in html
    assert 'id="daily-setup-refresh"' in html
    assert 'id="daily-setup-advanced"' in html
    assert 'id="daily-setup-live-refresh"' in html
    assert 'id="daily-setup-updated"' in html
    assert 'dom.dailySetupRefresh.addEventListener("click"' in js
    assert 'dom.dailySetupSearch.addEventListener("input"' in js
    assert 'dom.dailySetupLane.addEventListener("change"' in js
    assert 'dailySetupData' in js
    assert 'dom.dailyFilterMarginable, dom.dailyFilterTradeValue, dom.dailyFilterPrice' in js
    assert 'liveRefreshTimer = liveRefreshEnabled ? setTimeout' in js
    assert 'setInterval(function()' not in js


def test_mobile_review_surface_uses_fullscreen_drawer_guide_and_state_aware_copy():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    assert 'id="method-guide"' in html
    assert 'id="drawer-method-link"' in html
    assert "@media (max-width: 600px)" in css
    assert ".drawer-panel { max-width:none; max-height:none; height:100dvh;" in css
    assert "methodGuideContent" in js and "drawerMethodLink" in js
    assert "Awaiting 60m structure" in js and "Setup forming" in js
    helper = _extract_function(js, "setupReadinessLabel")
    result = _run_node(
        [helper],
        "[setupReadinessLabel({decision_lane:'DAILY_CANDIDATE'}, {status:'FORMING'}), "
        "setupReadinessLabel({decision_lane:'SETUP_FORMING'}, {status:'FORMING', minor_structure:true}), "
        "setupReadinessLabel({decision_lane:'DATA_BLOCKED'}, {status:'DATA_BLOCKED'})]"
    )
    assert result == ["Setup forming", "Awaiting 60m structure", "Data blocked"]


def test_setup_candidate_refresh_is_the_update_boundary_and_idle_is_not_live_by_default():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'Refresh' in html
    assert 'aria-live="polite"' in html
    assert "liveRefreshEnabled" in js
    assert "dailySetupUpdated.textContent" in js
    assert 'liveRefreshTimer = liveRefreshEnabled ? setTimeout' in js
    assert 'setInterval(function()' not in js


def test_vcp_is_not_primary_navigation_and_api_is_marked_audit_only():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'id="tab-vcp"' not in html
    assert "VCP Audit · Compatibility / Rollback" not in html
    assert "Audit / compatibility / rollback only" not in html
    assert 'id="tab-daily-vcp"' in html
    assert 'if (dom.tabVcp) dom.tabVcp.addEventListener' in js
    assert 'id="daily-setup-sector"' in html
    assert 'var endpoint = "/api/vcp-finder?interval=60m&market=TH&universe=marginable_long";' in js


def test_setup_candidate_payload_validation_fails_closed_and_checks_lane_totals():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    validator = _extract_function(js, "validateSetupCandidatePayload")
    base = {
        "items": [{"symbol": "AAA", "decision_lane": "DAILY_CANDIDATE"}],
        "counts": {"DAILY_CANDIDATE": 1, "DATA_BLOCKED": 0},
        "evaluated_count": 1,
    }
    assert _run_node([validator], "validateSetupCandidatePayload(" + json.dumps(base) + ")") is True
    malformed = dict(base, items={"symbol": "AAA"})
    assert _run_node([validator], "validateSetupCandidatePayload(" + json.dumps(malformed) + ")") is False
    negative = dict(base, counts={"DAILY_CANDIDATE": -1, "DATA_BLOCKED": 2})
    assert _run_node([validator], "validateSetupCandidatePayload(" + json.dumps(negative) + ")") is False
    inconsistent = dict(base, counts={"DAILY_CANDIDATE": 0, "DATA_BLOCKED": 1})
    assert _run_node([validator], "validateSetupCandidatePayload(" + json.dumps(inconsistent) + ")") is False


def test_setup_candidate_compact_items_and_canonical_detail_merge_are_safe():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    validator = _extract_function(js, "validateSetupCandidatePayload")
    compact = {
        "items": [{"symbol": "AAA", "decision_lane": "DAILY_CANDIDATE"}],
        "counts": {"DAILY_CANDIDATE": 1},
        "evaluated_count": 1,
    }
    assert _run_node([validator], "validateSetupCandidatePayload(" + json.dumps(compact) + ")") is True
    merge = _extract_function(js, "mergeCanonicalSetupDetail")
    fields = ("trend", "wave", "setup", "context", "bonus_evidence", "chart_evidence")
    item = {field: {"source": "list"} for field in fields}
    item.update({"symbol": "AAA", "decision_lane": "DAILY_CANDIDATE"})
    detail = {field: {"source": "detail"} for field in fields}
    detail["name"] = "Alpha"
    result = _run_node([merge], "mergeCanonicalSetupDetail(" + json.dumps(item) + ", " + json.dumps(detail) + ")")
    for field in fields:
        assert result[field] == {"source": "list"}
    assert result["name"] == "Alpha"


def test_canonical_detail_merge_enriches_compact_nested_evidence_without_overwrite():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    merge = _extract_function(js, "mergeCanonicalSetupDetail")
    item = {
        "symbol": "AAA",
        "decision_lane": "REVIEW_NOW",
        "wave": {"primary_state": "EARLY_WAVE_3", "confidence": "HIGH"},
        "setup": {"trigger": 12, "trade_stop": 10, "target_1": 20},
        "provenance": {"snapshot_id": "snap-canonical", "source": "setup-candidates"},
        "name": "Canonical name",
    }
    detail = {
        "name": "Legacy name",
        "sector": "Technology",
        "wave": {"primary_state": "WAVE_1_ADVANCE", "snapshot_id": "snap-legacy"},
        "setup": {"trigger": 99, "chart_evidence": {"daily": {"markers": ["detail-marker"]}}},
        "provenance": {"snapshot_id": "snap-legacy"},
        "decision_lane": "AVOID",
        "unexpected_legacy_field": "must not enter canonical item",
    }
    result = _run_node([merge], "mergeCanonicalSetupDetail(" + json.dumps(item) + ", " + json.dumps(detail) + ")")
    assert result["name"] == "Canonical name"
    assert result["sector"] == "Technology"
    assert result["wave"]["primary_state"] == "EARLY_WAVE_3"
    assert result["wave"]["snapshot_id"] == "snap-legacy"
    assert result["setup"]["trigger"] == 12
    assert result["setup"]["chart_evidence"] == detail["setup"]["chart_evidence"]
    assert result["provenance"] == item["provenance"]
    assert result["decision_lane"] == "REVIEW_NOW"
    assert "unexpected_legacy_field" not in result


def test_compact_item_plus_canonical_detail_provides_full_drawer_evidence():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    merge = _extract_function(js, "mergeCanonicalSetupDetail")
    wave_evidence = _extract_function(js, "waveEvidenceForItem")
    compact = {
        "symbol": "AAA", "decision_lane": "REVIEW_NOW",
        "wave": {"primary_state": "EARLY_WAVE_3", "confidence": "HIGH"},
        "setup": {"trigger": 12, "trade_stop": 10},
        "provenance": {"source": "setup-candidates"},
    }
    detail = {
        "wave": {
            "primary_state": "WAVE_1_ADVANCE",
            "evidence_explanation": {"rule": "Daily close above Wave 1 high", "policy": "elliott-v1"},
            "supporting_evidence": ["prior advance"],
            "contradicting_evidence": ["weak volume"],
            "missing_evidence": ["60m confirmation"],
            "markers": [{"kind": "WAVE_3_CLOSE_CONFIRMATION"}],
            "evidence_markers": [{"kind": "WAVE_1_HIGH"}],
            "snapshot_identity": "daily:2026-08-31",
            "snapshot_id": "daily:2026-08-31",
        },
        "setup": {"chart_evidence": {"daily": {"markers": ["daily-marker"]}, "60m": {"markers": ["60m-marker"]}}},
        "provenance": {"policy_version": "setup-candidates-v1", "snapshot_identity": "daily:2026-08-31"},
    }
    result = _run_node([merge, wave_evidence], "(function(){var item = mergeCanonicalSetupDetail(" + json.dumps(compact) + ", " + json.dumps(detail) + "); return {item:item, evidence:waveEvidenceForItem(item)};})()")
    assert result["item"]["wave"]["primary_state"] == "EARLY_WAVE_3"
    assert result["evidence"]["rule"] == "Daily close above Wave 1 high"
    assert result["evidence"]["supporting_evidence"] == ["prior advance"]
    assert result["evidence"]["contradicting_evidence"] == ["weak volume"]
    assert result["evidence"]["missing_evidence"] == ["60m confirmation"]
    assert result["evidence"]["markers"] == [{"kind": "WAVE_3_CLOSE_CONFIRMATION"}]
    assert result["evidence"]["snapshot_identity"] == "daily:2026-08-31"
    assert result["item"]["setup"]["chart_evidence"]["60m"]["markers"] == ["60m-marker"]


def test_canonical_chart_failure_never_uses_snapshot_fallback():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    helper = _extract_function(js, "shouldUseSnapshotChartFallback")
    assert _run_node([helper], 'shouldUseSnapshotChartFallback({"symbol":"AAA","decision_lane":"DAILY_CANDIDATE"})') is False
    assert _run_node([helper], 'shouldUseSnapshotChartFallback({"symbol":"AAA"})') is True
    assert "if (!shouldUseSnapshotChartFallback(item)) throw err;" in js
    assert 'data-detail-source="canonical-setup-candidate"' in (ROOT / "index.html").read_text(encoding="utf-8")


def test_setup_candidate_pagination_is_reachable_and_accessible():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    for marker in ('id="daily-setup-pagination"', 'id="daily-setup-prev"',
                   'id="daily-setup-next"', 'aria-live="polite"'):
        assert marker in html
    assert "dailySetupPage - 1" in js
    assert "dailySetupPage + 1" in js
    assert "data.total_pages || 0" in js
    assert 'loadDailyVcp(true, 1)' in js
    assert 'if (force && typeof force === "object")' not in js


def test_primary_setup_states_keep_empty_error_and_data_blocked_distinct_and_mobile_safe():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    assert "empty result, not an API failure" in js
    assert "Unable to load setup candidates:" in js
    assert 'decision = item.decision_lane || "DATA_BLOCKED"' in js
    assert ".setup-candidate-card { width: 100%; max-width: 100%; }" in css
    assert "overflow-x: hidden" in css
    assert "390px" not in html or 'meta name="viewport"' in html


def test_setup_candidates_use_canonical_lane_and_wave_evidence_projection():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "item.decision ||" not in js
    for marker in ("item.decision_lane", "rr.to_target_1", "function waveEvidenceForItem", "function openDrawer"):
        assert marker in js
    card = _extract_function(js, "setupCandidateCard")
    assert "wave.primary_state" not in card
    assert "setup.entry_zone" not in card


def test_setup_candidates_group_in_canonical_lane_order_and_block_unknown_lanes():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    lane_order = '["REVIEW_NOW", "SETUP_FORMING", "DAILY_CANDIDATE", "WAIT", "AVOID", "DATA_BLOCKED"]'
    assert lane_order in js
    assert "function groupSetupCandidates(items)" in js
    assert 'var lane = laneOrder.indexOf(item.decision_lane) >= 0 ? item.decision_lane : "DATA_BLOCKED"' in js
    assert "groups.REVIEW_NOW" in js and '"PRE_TRIGGER", "TESTED_TRIGGER", "TRIGGERED"' in js
    assert "laneItems.map(setupCandidateCard).join(\"\")" in js


def test_setup_candidate_layout_has_no_horizontal_overflow_at_390px():
    """Use a real layout engine for the mobile overflow contract."""
    import glob
    import pytest
    playwright = pytest.importorskip("playwright.sync_api")
    executables = glob.glob("/root/.cache/ms-playwright/*/chrome-linux64/chrome")
    if not executables:
        pytest.skip("Chromium executable is not installed")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    markup = """
      <main class="app"><article class="decision-card setup-candidate-card">
        <div class="decision-card__top"><strong>LONGSYMBOL</strong><b>DATA_BLOCKED</b></div>
        <p class="setup-candidate__evidence">Trend emerging_uptrend · 20D 18.4% · 60D 42.1% · RS 91 · 52W BREAKOUT · ATH NO BREAKOUT</p>
        <div class="setup-candidate__grid"><span>Wave <b>EARLY_WAVE_3 · structure intact</b></span><span>Setup <b>DATA_BLOCKED · trigger – · invalidation –</b></span><span>Targets <b>– / –</b></span><span>R:R <b>–</b></span><span>Market / sector <b>UNKNOWN · Electronic Components</b></span><span>Peers <b>6/10</b></span></div>
      </article></main>
    """
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=executables[0])
        page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        page.set_content(f"<style>{css}</style>{markup}")
        result = page.evaluate("""() => ({
          viewport: document.documentElement.clientWidth,
          scroll: document.documentElement.scrollWidth,
          card: document.querySelector('.setup-candidate-card').getBoundingClientRect().width,
          grid: document.querySelector('.setup-candidate__grid').getBoundingClientRect().width
        })""")
        browser.close()
    assert result["scroll"] <= result["viewport"]
    assert result["card"] <= 390
    assert result["grid"] <= result["card"]


def test_t07_drawer_navigation_uses_filtered_deterministic_collection_and_boundaries():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    collection = _extract_function(js, "setupDrawerCollection")
    grouping = _extract_function(js, "groupSetupCandidates")
    stable = _extract_function(js, "stableSetupCandidateOrder")
    bucket = _extract_function(js, "setupCandidateWaveBucket")
    context = _extract_function(js, "waveContextForItem")
    navigation = _extract_function(js, "drawerNavigationState")
    items = [
        {"symbol": "ZZZ", "decision_lane": "DAILY_CANDIDATE"},
        {"symbol": "AAA", "decision_lane": "REVIEW_NOW", "setup": {"status": "TRIGGERED"}},
        {"symbol": "AAA", "decision_lane": "REVIEW_NOW", "setup": {"status": "PRE_TRIGGER"}},
        {"symbol": "MID", "decision_lane": "SETUP_FORMING"},
    ]
    states = 'var canonicalDailyWaveStates = ["EARLY_WAVE_3", "WAVE_3_CONTINUATION"];'
    assert _run_node([states, context, bucket, grouping, stable, collection], "setupDrawerCollection(" + json.dumps(items) + ").map(function(item) { return item.symbol; })") == ["AAA", "MID", "ZZZ"]
    assert _run_node([navigation], "drawerNavigationState(['AAA','MID','ZZZ'], 0)") == {"index": 0, "count": 3, "position": "1 of 3", "previousDisabled": True, "nextDisabled": False}
    assert _run_node([navigation], "drawerNavigationState(['AAA','MID','ZZZ'], 2)") == {"index": 2, "count": 3, "position": "3 of 3", "previousDisabled": False, "nextDisabled": True}
    assert 'id="drawer-position"' in html
    assert "drawerItems[nextIndex] || drawerItemForSymbol(symbol)" in js
    assert "items = items.filter(setupCandidateMatchesToolbar)" in js
    assert "drawerItems = setupDrawerCollection(items)" in js


def test_t07_drawer_navigation_atomically_guards_stale_enrichment_and_chart_responses():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    assert "drawerItem = item;" in js
    assert "requestSeq !== chartRequestSeq || chartSymbol !== symbol" in js
    assert "requestSeq !== chartRequestSeq || chartSymbol !== symbol || chartTimeframe !== requestedTimeframe" in js
    assert "drawerItem = drawerItem.vcp_result ? mergeCanonicalDailyMetadata(item, fresh) : mergeCanonicalSetupDetail(item, fresh);" in js
    assert ".drawer-position" in css
