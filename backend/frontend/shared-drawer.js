/* Signalix shared drawer: one controller and one deterministic chart renderer for /mvp and shadow. */
(function () {
  "use strict";
  var $ = function (selector) { return document.querySelector(selector); };
  var $$ = function (selector) { return document.querySelectorAll(selector); };
  var chartLayers = {candles:true, volume:true, ma:true, rsi:true, macd:true,
    maPeriods: {"5":true,"10":true,"20":true,"50":true,"100":false,"200":false}, waveEvidence:true};
  var chartTimeframe = "1D", chartSymbol = null, drawerItem = null, drawerItems = [], drawerSymbols = [], drawerIndex = -1;
  var chartRequestSeq = 0, chartAbort = null, chartCache = {}, swipeStart = null, drawerTriggerElement = null;
  var dom = {};

  function drawerMarkup() {
    return '<aside id="drawer" class="drawer drawer--hidden" role="dialog" aria-modal="true" aria-labelledby="drawer-symbol">' +
      '<div class="drawer-overlay" id="drawer-overlay"></div><div class="drawer-panel"><header class="drawer-header">' +
      '<div class="drawer-identity"><a id="drawer-symbol" class="drawer-title drawer-symbol-link" target="_blank" rel="noopener noreferrer"></a>' +
      '<span id="drawer-name" class="drawer-name"></span><span id="drawer-lane" class="drawer-lane">Not verified</span></div>' +
      '<div class="drawer-nav" aria-label="Navigate stocks"><button id="drawer-prev" class="drawer-nav-button" type="button" aria-label="Previous stock">←</button>' +
      '<span id="drawer-position" class="drawer-position" aria-live="polite">– of –</span><button id="drawer-next" class="drawer-nav-button" type="button" aria-label="Next stock">→</button></div>' +
      '<button id="drawer-close" class="drawer-close" type="button" aria-label="Close detail">&times;</button></header><div id="drawer-body" class="drawer-body">' +
      '<div class="drawer-price-row"><strong id="drawer-price">–</strong><span id="drawer-change" class="drawer-change">–</span><span id="drawer-trade-value" class="drawer-trade-value">Trade value –</span></div>' +
      '<div id="drawer-quote-source" class="drawer-quote-source">Quote · Not verified</div><div class="drawer-decision"><span id="drawer-trend" class="drawer-trend">–</span><strong id="drawer-action" class="drawer-action">–</strong></div>' +
      '<div class="drawer-wave-summary" aria-label="Primary Daily Wave"><span>Primary Daily Wave <strong id="drawer-wave">Not verified</strong></span><span>Confidence <strong id="drawer-wave-confidence">NOT_VERIFIED</strong></span><span id="drawer-wave-source">Daily structural · source unavailable</span></div>' +
      '<div id="drawer-deep-pullback" class="deep-pullback-evidence" hidden></div><div id="drawer-chart" class="drawer-chart"><canvas id="drawer-canvas" width="720" height="440"></canvas><p id="drawer-chart-placeholder" class="chart-placeholder">Chart loading…</p><button id="drawer-chart-retry" class="chart-retry" type="button" hidden>Retry chart</button></div>' +
      '<div id="drawer-chart-legend" class="wave-chart-legend" aria-label="Chart evidence legend"></div>' +
      '<div class="chart-timeframe-controls" aria-label="Chart timeframe"><span class="chart-control-label">Timeframe</span><button type="button" class="chart-timeframe" data-timeframe="60M">60m</button><button type="button" class="chart-timeframe is-active" data-timeframe="1D">1D</button><button type="button" class="chart-timeframe" data-timeframe="1W">1W</button><button type="button" class="chart-timeframe" data-timeframe="1M">1M</button></div>' +
      '<div class="ma-controls" aria-label="Moving average overlays"><span class="chart-control-label">Moving averages</span><label><input type="checkbox" data-ma-period="5" checked> MA5</label><label><input type="checkbox" data-ma-period="10" checked> MA10</label><label><input type="checkbox" data-ma-period="20" checked> MA20</label><label><input type="checkbox" data-ma-period="50" checked> MA50</label><label><input type="checkbox" data-ma-period="100"> MA100</label><label><input type="checkbox" data-ma-period="200"> MA200</label></div>' +
      '<section id="technical-latest" class="technical-summary" aria-label="Latest deterministic technical values" aria-live="polite"><div><span>High / Low</span><strong id="technical-high-low">Not verified</strong></div><div><span>MACD / Signal / Hist</span><strong id="technical-macd">Not verified</strong></div><div><span>RSI 14</span><strong id="technical-rsi">Not verified</strong></div><div><span>ATR 14</span><strong id="technical-atr">Not verified</strong></div></section>' +
      '<section id="rolling-high-low" class="rolling-high-low" aria-labelledby="rolling-high-low-title" aria-live="polite"><h2 id="rolling-high-low-title">OHLCV Window Summary (candles)</h2><div class="rolling-high-low__table-wrap"><table><thead><tr><th>Candles</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Avg Vol</th><th>MA</th></tr></thead><tbody>' +
      ["5","10","20","50","100","200","260"].map(function (p) { return '<tr data-rolling-period="' + p + '"><th>' + p + '<small class="window-detail">Not verified</small></th><td>Not verified</td><td>Not verified</td><td>Not verified</td><td>Not verified</td><td>Not verified</td><td>Not verified</td></tr>'; }).join("") +
      '</tbody></table></div></section>' +
      '<section class="drawer-section drawer-section--setup" aria-labelledby="drawer-setup-title"><h2 id="drawer-setup-title" class="drawer-section-title">Key setup</h2><dl class="drawer-setup-grid"><div class="drawer-setup-field"><dt>Current</dt><dd id="drawer-current">Not verified</dd></div><div class="drawer-setup-field"><dt>Trigger</dt><dd id="drawer-trigger">Not ready</dd></div><div class="drawer-setup-field"><dt>Stop</dt><dd id="drawer-stop">Not ready</dd></div><div class="drawer-setup-field"><dt>Target 1</dt><dd id="drawer-target">Not ready</dd></div><div class="drawer-setup-field"><dt>R:R</dt><dd id="drawer-rr">Unavailable</dd></div></dl></section>' +
      '<section class="drawer-section drawer-section--company" aria-labelledby="drawer-company-title"><h2 id="drawer-company-title" class="drawer-section-title">Company context</h2><div class="drawer-company-context"><span id="drawer-market-cap">Market cap –</span><span id="drawer-sector">Sector –</span><span id="drawer-industry">Industry –</span></div></section>' +
      '<section class="drawer-section drawer-section--route" aria-labelledby="drawer-route-title"><h2 id="drawer-route-title" class="drawer-section-title">Trend Route</h2><div id="drawer-route-status" class="trend-route-status" aria-live="polite">Loading…</div><div id="drawer-route-graph" class="trend-route-graph" role="list" aria-label="Trend Route from older to latest"></div><div id="drawer-route-detail" class="trend-route-detail" hidden></div><button id="drawer-route-retry" class="chart-retry" type="button" hidden>Retry Trend Route</button></section></div></div></aside>';
  }

  function bindDom() {
    var mount = document.querySelector("#drawer-mount");
    if (mount && !document.querySelector("#drawer")) mount.innerHTML = drawerMarkup();
    ["drawer","drawerOverlay","drawerClose","drawerPrev","drawerNext","drawerPosition","drawerSymbol","drawerName","drawerLane","drawerPrice","drawerCurrent","drawerChange","drawerQuoteSource","drawerTrend","drawerAction","drawerWave","drawerWaveConfidence","drawerWaveSource","drawerDeepPullback","drawerSector","drawerIndustry","drawerMarketCap","drawerTradeValue","drawerCanvas","drawerChartPH","drawerChartRetry","drawerChartLegend","drawerRouteStatus","drawerRouteGraph","drawerRouteDetail","drawerRouteRetry","technicalHighLow","technicalMacd","technicalRsi","technicalAtr","rollingHighLow","drawerTarget","drawerTrigger","drawerStop","drawerRR","drawerBody"].forEach(function (key) {
      var ids = {
        drawerChartPH:"drawer-chart-placeholder",
        drawerRR:"drawer-rr"
      };
      var id = ids[key] || key.replace(/[A-Z]/g, function (c) { return "-" + c.toLowerCase(); });
      if (key === "drawer") id = "drawer";
      dom[key] = document.getElementById(id);
    });
  }

  function compactWaveLabel(item) {
    var labels = {
      WAVE_1_ADVANCE: "W1 ↑ · advance",
      WAVE_2_FORMING: "W2 ↘ · forming",
      WAVE_2_NEAR_COMPLETION: "W2 ↘ · near completion",
      EARLY_WAVE_3: "W3 ↑ · early",
      WAVE_3_CONTINUATION: "W3 ↑ · continuation",
      WAVE_4_CORRECTION: "W4 ↘ · correction",
      WAVE_5_ADVANCE: "W5 ↑ · advance"
    };
    return labels[canonicalWaveState(item)] || "Wave · Not verified";
  }

  function compactWaveConfidence(item) {
    var wave = item && item.wave;
    var confidence = wave && wave.confidence;
    confidence = confidence == null ? "" : String(confidence).toUpperCase();
    return ["LOW", "MEDIUM", "HIGH"].indexOf(confidence) >= 0 ? confidence : "NOT_VERIFIED";
  }

  function deepPullbackEvidence(item) {
    var evidence = item && item.wave && item.wave.deep_pullback_evidence;
    return evidence && evidence.status === "DEEP_PULLBACK_W3_EVIDENCE" &&
      evidence.actionability === "NONE" && evidence.source_timeframe === "daily" ? evidence : null;
  }

  function deepPullbackRetracementText(evidence) {
    if (!evidence || typeof evidence.retracement !== "number" || !Number.isFinite(evidence.retracement)) return "Not verified";
    return (evidence.retracement * 100).toFixed(4).replace(/0+$/, "").replace(/\.$/, "") + "%";
  }

  function deepPullbackBadge(item) {
    var evidence = deepPullbackEvidence(item);
    if (!evidence) return "";
    return '<span class="setup-candidate__deep-pullback-badge" data-actionability="NONE">Deep pullback evidence · ' +
      escapeHTML(deepPullbackRetracementText(evidence)) + '<small>Non-actionable · Daily evidence</small></span>';
  }

  function renderDeepPullbackEvidence(item) {
    if (!dom.drawerDeepPullback) return;
    var evidence = deepPullbackEvidence(item);
    dom.drawerDeepPullback.hidden = !evidence;
    if (!evidence) { dom.drawerDeepPullback.innerHTML = ""; return; }
    var anchors = evidence.anchors || {};
    function anchorText(anchor) {
      if (!anchor || anchor.price == null) return "Not verified";
      return String(anchor.price) + (anchor.date ? " · " + anchor.date : "");
    }
    dom.drawerDeepPullback.innerHTML = '<strong>DEEP_PULLBACK_W3_EVIDENCE · ' + escapeHTML(deepPullbackRetracementText(evidence)) + '</strong>' +
      '<span>Non-actionable · Daily evidence</span><dl>' +
      '<div><dt>Exact retracement</dt><dd>' + escapeHTML(String(evidence.retracement)) + ' (' + escapeHTML(deepPullbackRetracementText(evidence)) + ')</dd></div>' +
      '<div><dt>W1 low</dt><dd>' + escapeHTML(anchorText(anchors.w1_low)) + '</dd></div>' +
      '<div><dt>W1 high</dt><dd>' + escapeHTML(anchorText(anchors.w1_high)) + '</dd></div>' +
      '<div><dt>W2 low</dt><dd>' + escapeHTML(anchorText(anchors.w2_low)) + '</dd></div></dl>';
  }

  function renderTrendRoute(route) {
    if (!dom.drawerRouteStatus || !dom.drawerRouteGraph) return;
    var payload = route && route.route ? route.route : null;
    dom.drawerRouteGraph.innerHTML = "";
    if (!payload || payload.status === "NOT_VERIFIED") {
      dom.drawerRouteStatus.textContent = "Trend Route unavailable · Not verified";
      if (dom.drawerRouteRetry) { dom.drawerRouteRetry.hidden = false; dom.drawerRouteRetry.onclick = function () { requestTrendRoute(chartSymbol); }; }
      return;
    }
    dom.drawerRouteStatus.textContent = (payload.status === "FULL" ? "Complete Daily history" : "Partial Daily history") +
      " · " + ((payload.coverage || {}).sessions || 0) + " sessions";
    (payload.segments || []).forEach(function (segment) {
      var button = document.createElement("button");
      button.type = "button"; button.className = "trend-route-segment"; button.setAttribute("role", "listitem");
      button.style.flex = "" + Math.max(1, Number(segment.sessions) || 1) + " 1 0%";
      button.setAttribute("aria-label", segment.label + ", " + segment.sessions + " sessions, " + segment.start + " to " + segment.end);
      button.textContent = segment.label;
      button.setAttribute("data-current", segment.current === true ? "true" : "false");
      button.onclick = function () { if (dom.drawerRouteDetail) { dom.drawerRouteDetail.hidden = false; dom.drawerRouteDetail.textContent = "Main Trend " + (segment.main_trend == null ? "Not verified" : segment.main_trend) + " · " + segment.label + " · " + (segment.quality || "Not verified") + " · " + ((segment.provenance || {}).source || "Provenance unavailable") + " · " + (segment.date || segment.end || "Date unavailable") + " · " + (segment.session_count || segment.sessions || 0) + " sessions"; } };
      dom.drawerRouteGraph.appendChild(button);
    });
    if (dom.drawerRouteRetry) dom.drawerRouteRetry.hidden = true;
  }
  function requestTrendRoute(symbol) {
    if (!symbol || !dom.drawerRouteStatus) return;
    dom.drawerRouteStatus.textContent = "Loading Trend Route…";
    fetch("/api/trend-map/" + encodeURIComponent(symbol) + "/route", {cache:"no-store"})
      .then(function (response) { if (!response.ok) throw new Error("Route HTTP " + response.status); return response.json(); })
      .then(renderTrendRoute)
      .catch(function () { renderTrendRoute(null); });
  }

  function waveContextPresentation(item) {
    var context = waveContextForItem(item);
    var state = canonicalWaveState(item);
    var secondary = context && Array.isArray(context.secondary_markers)
        ? context.secondary_markers.filter(function(value) { return value === "WAVE_3_EXTENDED"; }) : [];
    var nonActionable = ["WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "WAVE_4_CORRECTION", "Unknown / Not verified"].indexOf(state) >= 0;
    return {
      state: state, secondary: secondary, confidence: compactWaveConfidence(item),
      contextState: context && context.mapped_state,
      rule: context && context.rule_version,
      source: context && context.source_timeframe === "daily" ? "Daily structural · daily" : "Daily structural · source unavailable",
      supporting: context && context.supporting_evidence, contradicting: context && context.contradicting_evidence,
      missing: context && context.missing_evidence, rationale: context && context.rationale,
      firstDate: context && context.first_context_date,
      lastDate: context && context.last_context_date,
      transitions: context && Array.isArray(context.transitions) ? context.transitions : [],
      actionability: item && item.decision_lane === "REVIEW_NOW" ? "Review eligible · backend REVIEW_NOW" :
        nonActionable ? "Non-actionable context · backend lane " + ((item && item.decision_lane) || "DATA_BLOCKED") :
        "Not review eligible · backend lane " + ((item && item.decision_lane) || "DATA_BLOCKED")
    };
  }

  function shadowMainTrendDisplay(item) {
    var evidence = item && item.main_trend;
    var value = evidence && evidence.main_trend;
    if ([1, 2, 3, 4].indexOf(value) < 0) return "Main Trend · Not verified";
    var quality = evidence && String(evidence.evidence_quality || "").toUpperCase();
    if (["FULL", "PARTIAL"].indexOf(quality) < 0) quality = "NOT_VERIFIED";
    var display = evidence && evidence.main_trend_display;
    var validDisplays = ["1++", "1+", "1", "2", "3", "3-", "3--", "4"];
    display = quality === "FULL" && validDisplays.indexOf(String(display)) >= 0 ? String(display) : String(value);
    return "Main Trend " + display + " · " + quality;
  }

  function normalizeDrawerTrendDisplay(item, trend) {
    var itemTrend = item && item.trend;
    var candidate = itemTrend && typeof itemTrend === "object" && !Array.isArray(itemTrend)
      ? (itemTrend.state != null ? itemTrend.state : itemTrend.primary_state)
      : itemTrend;
    if (candidate == null || candidate === "") {
      candidate = item && item.stage;
    }
    if (candidate == null || candidate === "") {
      candidate = trend && typeof trend === "object" && !Array.isArray(trend)
        ? (trend.state != null ? trend.state : trend.primary_state)
        : trend;
    }
    return candidate != null && candidate !== "" && typeof candidate !== "object"
      ? String(candidate) : "Not verified";
  }

  function mergeCanonicalDailyMetadata(item, canonical) {
    // VCP remains authoritative for intraday price/action/trigger/invalidation.
    // Fill only drawer metadata that the VCP finder payload does not carry.
    var fields = ["name", "sector", "industry", "market_cap", "description",
                  "high52", "low52", "ath_high", "ath_low", "rr", "target",
                  "change_amount", "trade_value", "index_membership"];
    fields.forEach(function(field) {
      if (canonical[field] != null && item[field] == null) item[field] = canonical[field];
    });
    item._canonicalMetadataPending = false;
    return item;
  }

  function mergeCanonicalSetupDetail(item, detail) {
    // /api/setup-candidates is authoritative for the compact item. The
    // symbol detail response is the same canonical candidate with heavy
    // evidence restored; fill only fields omitted by the list projection.
    // Never spread the response over canonical fields or accept legacy
    // top-level aliases as a competing contract.
    var merged = Object.assign({}, item || {});
    var metadataFields = ["name", "sector", "industry", "market_cap", "description",
      "close", "change_pct", "change_amount", "trade_value", "avgDailyValue20",
      "index_membership", "margin_pct", "margin_rate_pct", "high52", "low52",
      "ath_high", "ath_low"];
    metadataFields.forEach(function(field) {
      if (merged[field] == null && detail && detail[field] != null) merged[field] = detail[field];
    });
    if (merged.quote == null && detail && detail.quote != null) merged.quote = detail.quote;

    function fillNestedFields(parent, source, fields) {
      if (!source || typeof source !== "object" || Array.isArray(source)) return;
      fields.forEach(function(field) {
        if (parent[field] == null && source[field] != null) parent[field] = source[field];
      });
    }

    var compactWave = merged.wave && typeof merged.wave === "object" && !Array.isArray(merged.wave)
      ? Object.assign({}, merged.wave) : {};
    var detailWave = detail && detail.wave;
    fillNestedFields(compactWave, detailWave, [
      "evidence_explanation", "evidence", "supporting_evidence",
      "contradicting_evidence", "missing_evidence", "alternative_state",
      "markers", "evidence_markers", "snapshot_identity", "snapshot_id", "context"
    ]);
    if (Object.keys(compactWave).length) merged.wave = compactWave;

    var compactSetup = merged.setup && typeof merged.setup === "object" && !Array.isArray(merged.setup)
      ? Object.assign({}, merged.setup) : {};
    var detailSetup = detail && detail.setup;
    // Chart evidence is canonical only under setup; do not import a legacy
    // top-level detail.chart_evidence field.
    fillNestedFields(compactSetup, detailSetup, ["chart_evidence"]);
    if (Object.keys(compactSetup).length) merged.setup = compactSetup;

    // The compact projection retains provenance scalars, but detail may carry
    // the canonical identity/policy when those fields were absent.
    var compactProvenance = merged.provenance && typeof merged.provenance === "object" && !Array.isArray(merged.provenance)
      ? Object.assign({}, merged.provenance) : {};
    fillNestedFields(compactProvenance, detail && detail.provenance,
      ["policy_version", "snapshot_id", "snapshot_identity"]);
    if (Object.keys(compactProvenance).length) merged.provenance = compactProvenance;
    merged._canonicalMetadataPending = false;
    return merged;
  }

  function shouldUseSnapshotChartFallback(item) {
    return !(item && item.decision_lane);
  }

  function drawerNavigationState(symbols, index) {
    var count = Array.isArray(symbols) ? symbols.length : 0;
    return {index: index, count: count, position: index >= 0 && index < count ? (index + 1) + " of " + count : "– of –",
      previousDisabled: index <= 0 || count === 0, nextDisabled: index < 0 || index >= count - 1 || count === 0};
  }

  function renderSharedDetail(envelope) {
    var item = envelope.item || {}, shadow = envelope.source === "trend-map";
    dom.drawer.classList.toggle("drawer--shadow", shadow);
    var routeSection = dom.drawerRouteStatus && dom.drawerRouteStatus.closest(".drawer-section--route");
    if (routeSection) routeSection.hidden = !shadow;
    var waveSummary = dom.drawer.querySelector(".drawer-wave-summary");
    if (waveSummary) waveSummary.hidden = shadow;
    if (dom.drawerChartLegend) dom.drawerChartLegend.hidden = shadow;
    dom.drawerSymbol.textContent = item.symbol || "–";
    dom.drawerSymbol.href = "https://www.tradingview.com/symbols/" + encodeURIComponent(item.symbol || "") + "/?exchange=SET";
    dom.drawerName.textContent = item.name && String(item.name).toUpperCase() !== String(item.symbol || "").toUpperCase() ? item.name : "";
    dom.drawerName.hidden = !dom.drawerName.textContent;
    var shadowMainTrend = shadow ? shadowMainTrendDisplay(item) : null;
    dom.drawerLane.textContent = shadow ? shadowMainTrend : (envelope.lane || "Not verified");
    dom.drawerTrend.textContent = shadow ? shadowMainTrend.replace(/ · (FULL|PARTIAL|NOT_VERIFIED)$/, "") : normalizeDrawerTrendDisplay(item, envelope.trend);
    dom.drawerAction.textContent = shadow ? "" : (item.action || item.decision || "Not verified");
    dom.drawerAction.hidden = shadow;
    if (dom.drawerAction.parentElement) dom.drawerAction.parentElement.hidden = shadow;
    dom.drawerWave.textContent = shadow ? "Not applicable · Daily classification" : (typeof window.compactWaveLabel === "function" ? window.compactWaveLabel(item) : ((item.wave || {}).primary_state || "Not verified"));
    dom.drawerWaveConfidence.textContent = shadow ? "NOT_APPLICABLE" : (typeof window.compactWaveConfidence === "function" ? window.compactWaveConfidence(item) : "NOT_VERIFIED");
    dom.drawerWaveSource.textContent = shadow ? "Production read-only Daily evidence" : "Daily structural · source unavailable";
    var quote = item.quote || {};
    var price = quote.price != null ? quote.price : item.close;
    dom.drawerPrice.textContent = price != null ? Number(price).toFixed(2) : "Not verified";
    dom.drawerCurrent.textContent = dom.drawerPrice.textContent;
    var change = quote.change_pct != null ? quote.change_pct : item.change_pct;
    var changeText = fmtChange(change);
    dom.drawerChange.textContent = changeText[0] + " (" + fmtChangeAmount(quote.change_amount != null ? quote.change_amount : item.change_amount) + ")";
    dom.drawerChange.className = "drawer-change drawer-change--" + changeText[1];
    dom.drawerPrice.className = "drawer-price drawer-price--" + changeText[1];
    dom.drawerQuoteSource.textContent = quote.source === "intraday_price_data" ? "Quote · 60m provisional (intraday_price_data)" : quote.source === "price_data" ? "Quote · Daily official (price_data) · Daily close" : quote.source === "derived_daily_price_data" ? "Quote · Daily derived (derived_daily_price_data · 60m-derived)" : "Quote · Not verified";
    dom.drawerTradeValue.textContent = shadow ? "Trade value Not applicable" : "Trade value " + fmtNum(item.trade_value);
    dom.drawerChartPH.textContent = "Chart loading…";
    dom.drawerChartPH.style.display = "block"; dom.drawerCanvas.style.display = "none";
    ["drawerTrigger","drawerStop","drawerTarget","drawerRR"].forEach(function (key) {
      var field = dom[key] && dom[key].closest(".drawer-setup-field");
      if (field) field.hidden = shadow;
    });
    var setupSection = dom.drawerTrigger && dom.drawerTrigger.closest(".drawer-section--setup");
    if (setupSection) setupSection.hidden = shadow;
    if (!shadow) {
      ["drawerTrigger","drawerStop","drawerTarget","drawerRR"].forEach(function (key) {
        var field = dom[key] && dom[key].closest(".drawer-setup-field");
        if (field) field.hidden = false;
      });
      var setup = item.setup || {};
      dom.drawerCurrent.textContent = price != null ? Number(price).toFixed(2) : "Not verified";
      dom.drawerTrigger.textContent = setup.trigger != null ? setup.trigger : "Not ready";
      dom.drawerStop.textContent = setup.trade_stop != null ? setup.trade_stop : "Not ready";
      dom.drawerTarget.textContent = setup.target_1 != null ? setup.target_1 : "Not ready";
      dom.drawerRR.textContent = item.rr != null ? item.rr : "Unavailable";
    } else {
      if (dom.drawerTrigger) dom.drawerTrigger.textContent = "Not applicable";
      if (dom.drawerStop) dom.drawerStop.textContent = "Not applicable";
      if (dom.drawerTarget) dom.drawerTarget.textContent = "Not applicable";
      if (dom.drawerRR) dom.drawerRR.textContent = "Not applicable";
    }
    dom.drawerSector.textContent = shadow ? "Sector Not applicable" : "Sector " + (item.sector || "Unknown");
    dom.drawerIndustry.textContent = shadow ? "Industry Not applicable" : "Industry " + (item.industry || "Unknown");
    dom.drawerMarketCap.textContent = shadow ? "Market cap Not applicable" : "Market cap " + fmtNum(item.market_cap);
    dom.drawer.classList.remove("drawer--hidden");
    document.body.style.overflow = "hidden";
    if (dom.drawerClose && typeof dom.drawerClose.focus === "function") dom.drawerClose.focus();
  }

  function setChartTimeframeButtons(value) {
    $$(".chart-timeframe").forEach(function (button) { button.classList.toggle("is-active", button.getAttribute("data-timeframe") === value); });
  }
  function updateSharedDrawerNavigation(symbols, items) {
    if (Array.isArray(symbols)) {
      var currentSymbol = drawerSymbols[drawerIndex] || (drawerItem && drawerItem.symbol);
      drawerSymbols = symbols.slice();
      drawerItems = Array.isArray(items) ? items.slice() : drawerItems;
      drawerIndex = drawerSymbols.indexOf(currentSymbol);
    }
    var hasItems = drawerSymbols.length > 0 && drawerIndex >= 0;
    var open = dom.drawer && !dom.drawer.classList.contains("drawer--hidden");
    if (open && !hasItems) { closeSharedDrawer(); return; }
    if (dom.drawerPrev) dom.drawerPrev.disabled = !hasItems || drawerIndex <= 0;
    if (dom.drawerNext) dom.drawerNext.disabled = !hasItems || drawerIndex >= drawerSymbols.length - 1;
    if (dom.drawerPosition) dom.drawerPosition.textContent = hasItems ? (drawerIndex + 1) + " of " + drawerSymbols.length : "– of –";
  }
  function closeSharedDrawer() {
    chartRequestSeq += 1; if (chartAbort) chartAbort.abort(); chartAbort = null; drawerItem = null; chartSymbol = null;
    if (dom.drawer) dom.drawer.classList.add("drawer--hidden");
    document.body.style.overflow = "";
    if (drawerTriggerElement && typeof drawerTriggerElement.focus === "function") drawerTriggerElement.focus();
    drawerTriggerElement = null;
  }
  function chartRequestUrl(envelope, symbol, timeframe) {
    var base = timeframe === "1D" && envelope && envelope.chartUrl
      ? envelope.chartUrl
      : "/api/chart-db/" + encodeURIComponent(symbol) + "?timeframe=" + encodeURIComponent(timeframe);
    return base + (base.indexOf("?") >= 0 ? "&" : "?") + "view=chart";
  }
  function requestChart(envelope, symbol, timeframe, seq) {
    var key = symbol + "|" + timeframe + "|chart";
    var cached = chartCache[key];
    if (cached) { renderDrawerChart(cached); return; }
    dom.drawerChartPH.style.display = "block"; dom.drawerChartPH.textContent = "Chart loading…"; dom.drawerCanvas.style.display = "none"; if (dom.drawerChartRetry) dom.drawerChartRetry.hidden = true;
    fetch(chartRequestUrl(envelope, symbol, timeframe), {signal: chartAbort.signal, cache:"no-store"})
      .then(function (response) { if (!response.ok) throw new Error("Chart HTTP " + response.status); return response.json(); })
      .then(function (chart) {
        if (seq !== chartRequestSeq || symbol !== chartSymbol || timeframe !== chartTimeframe) return;
        chart = chart || {};
        if (envelope.source === "canonical-mvp" && typeof mergeChartDecisionOverlay === "function") {
          mergeChartDecisionOverlay(chart, envelope.item);
        }
        chartCache[key] = chart;
        if (!Array.isArray(chart.candles) || chart.candles.length < 2) chart.candles = [];
        renderDrawerChart(chart);
      })
      .catch(function (error) {
        if (error && error.name === "AbortError") return;
        if (seq !== chartRequestSeq || symbol !== chartSymbol || timeframe !== chartTimeframe) return;
        dom.drawerChartPH.style.display = "block"; dom.drawerChartPH.textContent = timeframe === "60M" ? "60m unavailable · Daily EOD remains the decision source" : "Chart data unavailable";
        dom.drawerCanvas.style.display = "none";
        if (dom.drawerChartRetry) { dom.drawerChartRetry.hidden = false; dom.drawerChartRetry.onclick = function () { requestChart(envelope, symbol, timeframe, seq); }; }
      });
  }
  function openSharedDrawer(envelope) {
    envelope = envelope || {};
    var item = envelope.item || {};
    var symbol = item.symbol;
    if (!symbol) return;
    if (envelope.triggerElement) drawerTriggerElement = envelope.triggerElement;
    else if (!drawerTriggerElement && document.activeElement && document.activeElement !== document.body) drawerTriggerElement = document.activeElement;
    chartSymbol = symbol; item.__sharedEnvelope = envelope; drawerItem = item; drawerSymbols = envelope.navigation && Array.isArray(envelope.navigation.symbols) ? envelope.navigation.symbols.slice() : [symbol];
    drawerItems = envelope.navigation && Array.isArray(envelope.navigation.items) ? envelope.navigation.items.slice() : [item];
    drawerIndex = envelope.navigation && Number.isInteger(envelope.navigation.index) ? envelope.navigation.index : drawerSymbols.indexOf(symbol);
    updateSharedDrawerNavigation();
    chartRequestSeq += 1; if (chartAbort) chartAbort.abort(); chartAbort = new AbortController();
    var seq = chartRequestSeq; chartTimeframe = "1D"; setChartTimeframeButtons(chartTimeframe);
    renderSharedDetail(envelope);
    if (envelope.source === "trend-map") requestTrendRoute(symbol);
    requestChart(envelope, symbol, chartTimeframe, seq);
    if (envelope.detailUrl) fetch(envelope.detailUrl, {signal: chartAbort.signal, cache:"no-store"}).then(function (response) { if (!response.ok) throw new Error("Detail HTTP " + response.status); return response.json(); }).then(function (detail) {
      if (seq === chartRequestSeq && symbol === chartSymbol && envelope.source === "canonical-mvp") {
        envelope.item = Object.assign({}, envelope.item, detail || {}); renderSharedDetail(envelope);
      }
    }).catch(function () {});
  }
  function navigateSharedDrawer(delta) {
    var next = drawerIndex + delta; if (next < 0 || next >= drawerSymbols.length) return;
    var item = drawerItems[next] || {symbol: drawerSymbols[next]};
    var envelope = drawerItem && drawerItem.__sharedEnvelope || {};
    openSharedDrawer({item:item, lane:item.decision_lane || item.machine_lane, trend:item.trend || item.classifier_status || item.stage, broad_state:item.broad_state, source:envelope.source || "canonical-mvp", actionability:item.actionability, detailUrl:envelope.detailUrl || null, chartUrl:envelope.source === "trend-map" ? null : (envelope.chartUrl || null), navigation:{symbols:drawerSymbols,items:drawerItems,index:next}});
  }

    function escapeHTML(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  function fmtChange(pct) {
    if (pct == null || pct === "" || !Number.isFinite(Number(pct))) return ["Not verified", "flat"];
    var n = Number(pct);
    var s = (n >= 0 ? "+" : "") + n.toFixed(1) + "%";
    var dir = n > 0 ? "up" : n < 0 ? "down" : "flat";
    return [s, dir];
  }

  function fmtNum(n) {
    if (n == null) return "–";
    if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(1) + "B";
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(0) + "M";
    if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(0) + "K";
    return String(n);
  }

  function fmtChangeAmount(value) {
    if (value == null || value === "" || Number.isNaN(Number(value))) return "Not verified";
    var n = Number(value);
    return (n >= 0 ? "+" : "") + n.toFixed(2);
  }

  function shortStage(value) {
    return ({S2_uptrend: "S2 Uptrend", S1_basing: "S1 Base", S3_distributing: "S3 Distribution", S4_down: "S4 Down"})[value] || value || "–";
  }

  function shortAction(value) {
    return ({"VALIDATE FRESH BREAKOUT": "Fresh Breakout", "QUALIFIED PULLBACK": "Pullback", "WAIT FOR CONFIRMATION": "Wait for Breakout"})[value] || compactText(value || "", 20);
  }

  function setupLaneLabel(lane) {
    return ({REVIEW_NOW: "Review now", SETUP_FORMING: "Setup forming", DAILY_CANDIDATE: "Daily candidate", WAIT: "Wait", AVOID: "Avoid", DATA_BLOCKED: "Data blocked"})[lane] || "Not verified";
  }

  function displayMetadataValue(value, pending) {
    if (value != null && value !== "") return value;
    return pending ? "Loading…" : "Unavailable";
  }

  function formatRange(high, low, pending) {
    if (high == null && low == null) return pending ? "Loading…" : "Unavailable";
    return (high == null ? "–" : Number(high).toFixed(2)) + " / " + (low == null ? "–" : Number(low).toFixed(2));
  }

  function setOptionalDrawerField(el, value) {
    var present = value != null && String(value).trim() !== "";
    el.textContent = present ? String(value) : "";
    var row = el.closest(".drawer-field");
    if (row) row.hidden = !present;
  }

  function canonicalChartOverlay(item) {
    var setup = item && item.setup;
    if (!setup || typeof setup !== "object" || Array.isArray(setup)) return {};
    // target_1 is the canonical risk gate and chart decision target. Never
    // substitute target_2 when target_1 is absent or malformed.
    return {
      trigger: setup.trigger,
      // The chart stop is the executable trade-risk level. Thesis
      // invalidation is separate evidence and must not replace it.
      stop: setup.trade_stop,
      target: setup.target_1 != null && setup.target_1 !== "" && Number.isFinite(Number(setup.target_1))
        ? Number(setup.target_1) : null
    };
  }

  function chartTimestampKey(value) {
    if (value == null) return "";
    var raw = String(value).trim();
    return raw.length > 10 && raw.charAt(10) === " " ? raw.slice(0, 10) + "T" + raw.slice(11) : raw;
  }

  function waveEvidenceForItem(item) {
    var wave = item && item.wave;
    if (!wave || typeof wave !== "object" || Array.isArray(wave)) return {};
    var context = wave.context && typeof wave.context === "object" && !Array.isArray(wave.context) ? wave.context : {};
    var provenance = item.provenance && typeof item.provenance === "object" && !Array.isArray(item.provenance) ? item.provenance : {};
    var explanation = wave.evidence_explanation && typeof wave.evidence_explanation === "object" && !Array.isArray(wave.evidence_explanation)
      ? wave.evidence_explanation : wave.explanation && typeof wave.explanation === "object" && !Array.isArray(wave.explanation) ? wave.explanation : {};
    return {
      timeframe: "1D", source: provenance.daily_source || "price_data", confidence: wave.confidence,
      rule: context.rule_version || explanation.rule, evidence: explanation.evidence, policy: explanation.policy,
      supporting_evidence: context.supporting_evidence || wave.supporting_evidence,
      contradicting_evidence: context.contradicting_evidence || wave.contradicting_evidence,
      missing_evidence: context.missing_evidence || wave.missing_evidence, alternative_state: wave.alternative_state,
      snapshot_identity: wave.snapshot_identity || wave.snapshot_id || provenance.snapshot_identity || provenance.snapshot_id,
      evidence_refs: explanation.evidence_refs,
      markers: window.SignalixCanonicalClient.markers(item)
    };
  }

  function dailyWaveMarkerPresentation(kind) {
    return ({
      WAVE_1_LOW: {label: "Wave 1 low", shape: "circle", color: "#a78bfa"},
      WAVE_1_HIGH: {label: "Wave 1 high", shape: "square", color: "#a78bfa"},
      WAVE_2_PULLBACK_LOW: {label: "Wave 2 pullback low", shape: "diamond", color: "#60a5fa"},
      WAVE_3_CLOSE_CONFIRMATION: {label: "Wave 3 close confirmation", shape: "triangle", color: "#93c5fd"},
      TESTED_HIGH: {label: "Tested high", shape: "diamond", color: "#7dd3fc"},
      STRUCTURE_BREAK: {label: "Structure break", shape: "cross", color: "#c4b5fd"},
      THESIS_INVALIDATION: {label: "Thesis invalidation", shape: "cross", color: "#8896a6"},
      TRIGGER: {label: "Trigger", shape: "triangle", color: "#60a5fa"},
      TRADE_STOP: {label: "Trade stop", shape: "cross", color: "#8896a6"}
    })[kind] || null;
  }

  function dailyWaveMarkersForChart(chart) {
    if (!chart || chart.timeframe !== "1D" || !chart.wave_evidence ||
        !Array.isArray(chart.wave_evidence.markers)) return [];
    return chart.wave_evidence.markers.filter(function(marker) {
      return marker && typeof marker === "object" && !Array.isArray(marker) &&
        marker.timeframe === "daily" && marker.timestamp != null && String(marker.timestamp).trim() !== "" &&
        marker.price != null && marker.price !== "" && Number.isFinite(Number(marker.price)) &&
        dailyWaveMarkerPresentation(marker.kind) != null;
    });
  }

  function latestIndicatorValue(value) {
    if (Array.isArray(value)) {
      for (var i = value.length - 1; i >= 0; i--) {
        if (value[i] != null && Number.isFinite(Number(value[i]))) return Number(value[i]);
      }
      return null;
    }
    if (value && typeof value === "object") {
      var candidate = value.histogram != null ? value.histogram
        : value.macd_line != null ? value.macd_line
        : value.value;
      return candidate != null && Number.isFinite(Number(candidate)) ? Number(candidate) : null;
    }
    return value != null && Number.isFinite(Number(value)) ? Number(value) : null;
  }

  function renderChartLegend(chart) {
    if (!dom.drawerChartLegend) return;
    var isDaily = (chart && chart.timeframe || chartTimeframe) === "1D";
    var dailyMarkerCount = isDaily ? dailyWaveMarkersForChart(chart).length : 0;
    var markerState = isDaily ? (dailyMarkerCount ? String(dailyMarkerCount) : "none") : "Day only";
    var timeframe = chart && chart.timeframe || chartTimeframe;
    dom.drawerChartLegend.setAttribute("aria-label", "Chart evidence legend: OHLC candles use green/red direction colors; MA5, MA10, MA20, MA50, MA100, and MA200 use distinct neutral colors; wave markers are source-linked by shape and label; 60m trigger, stop, and target use labelled line styles.");
    var selectedMa = Object.keys(chartLayers.maPeriods).filter(function(period){ return chartLayers.maPeriods[period]; }).map(function(period){ return "MA" + period; }).join(" · ");
    dom.drawerChartLegend.innerHTML = '<span><i class="legend-line legend-line--price"></i>OHLC High/Low</span><span><i class="legend-line legend-line--ma20"></i>' + escapeHTML(selectedMa || "MA hidden") + '</span><span><i class="legend-dot legend-dot--wave"></i>markers (' + escapeHTML(markerState) + ') <button type="button" class="legend-info" aria-label="Show full chart legend">(i)</button></span>';
  }

  function formatCompactVolume(value) {
    if (value == null || !Number.isFinite(Number(value))) return "Not verified";
    var number = Number(value);
    var absolute = Math.abs(number);
    var units = [
      {threshold: 1e12, suffix: "T"},
      {threshold: 1e9, suffix: "B"},
      {threshold: 1e6, suffix: "M"},
      {threshold: 1e3, suffix: "K"}
    ];
    for (var index = 0; index < units.length; index += 1) {
      if (absolute >= units[index].threshold) {
        var scaled = (number / units[index].threshold).toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
        return scaled + units[index].suffix;
      }
    }
    return String(Math.round(number));
  }

  function renderTechnicalSummary(chart) {
    var latest = chart && chart.indicators && chart.indicators.latest;
    var display = function(value) { return value == null || !Number.isFinite(Number(value)) ? "Not verified" : Number(value).toFixed(2); };
    if (dom.technicalHighLow) dom.technicalHighLow.textContent = latest ? display(latest.high) + " / " + display(latest.low) : "Not verified";
    if (dom.technicalMacd) dom.technicalMacd.textContent = latest && latest.macd ? display(latest.macd.line) + " / " + display(latest.macd.signal) + " / " + display(latest.macd.histogram) : "Not verified";
    if (dom.technicalRsi) dom.technicalRsi.textContent = latest ? display(latest.rsi) : "Not verified";
    if (dom.technicalAtr) dom.technicalAtr.textContent = latest ? display(latest.atr) : "Not verified";
    var windowSummary = latest && latest.window_summary;
    var percent = function(value) { return value == null || !Number.isFinite(Number(value)) ? "Not verified" : Number(value).toFixed(2) + "%"; };
    if (dom.rollingHighLow) dom.rollingHighLow.querySelectorAll("[data-rolling-period]").forEach(function(row) {
      var period = row.dataset.rollingPeriod;
      var values = windowSummary && windowSummary[period];
      var available = values && values.availability && values.availability.status === "AVAILABLE";
      ["open", "high", "low", "close"].forEach(function(key, index) {
        row.children[index + 1].textContent = available ? display(values[key]) : "Not verified";
      });
      row.children[5].textContent = available ? formatCompactVolume(values.volume_average) : "Not verified";
      row.children[6].textContent = available ? (period === "260" ? "—" : display(values.ma)) : "Not verified";
      var detail = row.querySelector && row.querySelector(".window-detail");
      if (detail) detail.textContent = available ? "Total " + formatCompactVolume(values.volume_total) + " · Change " + percent(values.change_pct) + " · Range " + percent(values.range_pct) : "Not verified";
    });
  }

  function resizeCanvasToDisplaySize(canvas) {
    if (!canvas) return {width: 1, height: 1, pixelRatio: 1};
    var rect = canvas.getBoundingClientRect ? canvas.getBoundingClientRect() : null;
    var width = Math.max(1, Math.round((rect && rect.width) || canvas.clientWidth || canvas.width || 1));
    var height = Math.max(1, Math.round((rect && rect.height) || canvas.clientHeight || canvas.height || 1));
    var pixelRatio = Math.max(1, Number(window.devicePixelRatio) || 1);
    var pixelWidth = Math.max(1, Math.round(width * pixelRatio));
    var pixelHeight = Math.max(1, Math.round(height * pixelRatio));
    if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
    if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
    var ctx = canvas.getContext && canvas.getContext("2d");
    if (ctx) {
      if (typeof ctx.setTransform === "function") ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      else {
        if (typeof ctx.resetTransform === "function") ctx.resetTransform();
        if (typeof ctx.scale === "function") ctx.scale(pixelRatio, pixelRatio);
      }
    }
    return {width: width, height: height, pixelRatio: pixelRatio};
  }

  function chartLayout(h) {
    var top = 22, fixed = {priceH: 205, volH: 48, macdH: 68, rsiH: 62};
    var available = Math.max(0, h - top - 8);
    var total = fixed.priceH + fixed.volH + fixed.macdH + fixed.rsiH;
    if (available < total) {
      fixed.priceH = available * 0.52;
      fixed.volH = available * 0.12;
      fixed.macdH = available * 0.18;
      fixed.rsiH = available * 0.18;
    }
    fixed.top = top;
    fixed.rsiLabelY = top + fixed.priceH + fixed.volH + fixed.macdH + 16;
    return fixed;
  }

  function drawChart(chart) {
    var canvas = dom.drawerCanvas;
    // Clear hit targets before validating optional chart evidence so malformed
    // or absent payloads cannot leave stale markers clickable.
    window.__signalixWaveMarkerHits = [];
    if (!canvas || !chart || !chart.candles || chart.candles.length < 2) return;
    var ctx = canvas.getContext("2d");
    var displaySize = resizeCanvasToDisplaySize(canvas);
    var w = displaySize.width, h = displaySize.height;
    ctx.clearRect(0, 0, w, h);
    var candles = chart.candles.slice(-120);
    var start = chart.candles.length - candles.length;
    var left = 38, right = 8, layout = chartLayout(h), top = layout.top;
    var priceH = layout.priceH, volH = layout.volH, macdH = layout.macdH, rsiH = layout.rsiH;
    var plotW = w - left - right;
    var closes = candles.map(function(c) { return Number(c.close); });
    var highs = candles.map(function(c) { return Number(c.high); });
    var lows = candles.map(function(c) { return Number(c.low); });
    var visibleCandleKeys = candles.map(function(c) { return chartTimestampKey(c.date); });
    var dailyWaveMarkers = chartLayers.waveEvidence && chart.timeframe === "1D"
      ? dailyWaveMarkersForChart(chart).filter(function(marker) {
          return visibleCandleKeys.indexOf(chartTimestampKey(marker.timestamp)) >= 0;
        }) : [];
    var levels = chart.timeframe === "60M"
      ? [chart.trigger, chart.stop, chart.target].map(Number).filter(Number.isFinite) : [];
    levels = levels.concat(dailyWaveMarkers.map(function(marker) { return Number(marker.price); }));
    var allLows = lows.filter(function(v){return Number.isFinite(v);}).concat(levels);
    var allHighs = highs.filter(function(v){return Number.isFinite(v);}).concat(levels);
    var min = Math.min.apply(null, allLows);
    var max = Math.max.apply(null, allHighs);
    var range = (max - min) || 1;
    var xFor = function(i) { return left + (i / Math.max(1, candles.length - 1)) * plotW; };
    var yPrice = function(v) { return top + priceH - ((v - min) / range) * priceH; };
    // Green/red communicate candle and volume direction only. All other
    // chart evidence uses neutral/blue annotation colors.
    var colors = { grid: "#2a3345", text: "#8896a6", up: "#26a69a", down: "#ef5350", ma20: "#93c5fd", ma50: "#60a5fa", ma200: "#a78bfa", rsi: "#93c5fd",
      ma: {"5":"#d8bc65","10":"#7dd3fc","20":"#93c5fd","50":"#60a5fa","100":"#a78bfa","200":"#c4b5fd"}, macd:"#93c5fd", signal:"#a78bfa" };
    ctx.font = "11px sans-serif";
    ctx.strokeStyle = colors.grid; ctx.lineWidth = 1;
    [top, top + priceH, top + priceH + volH, top + priceH + volH + macdH, top + priceH + volH + macdH + rsiH].forEach(function(y){ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();});
    ctx.fillStyle = colors.text; ctx.fillText("PRICE", 2, top + 10); ctx.fillText("VOL", 7, top + priceH + 16); ctx.fillText("MACD", 2, top + priceH + volH + 16); ctx.fillText("RSI", 8, top + priceH + volH + macdH + 16);
    if (chartLayers.candles) {
      var candleW = Math.max(2, Math.min(8, plotW / candles.length * 0.64));
      candles.forEach(function(c, i) {
        var o=Number(c.open), cl=Number(c.close), hi=Number(c.high), lo=Number(c.low);
        if (![o,cl,hi,lo].every(Number.isFinite)) return;
        var x=xFor(i), up=cl>=o, color=up?colors.up:colors.down;
        ctx.strokeStyle=color; ctx.fillStyle=color; ctx.lineWidth=1;
        ctx.beginPath();ctx.moveTo(x,yPrice(hi));ctx.lineTo(x,yPrice(lo));ctx.stroke();
        var y1=yPrice(Math.max(o,cl)), y2=yPrice(Math.min(o,cl));
        ctx.fillRect(x-candleW/2,y1,candleW,Math.max(1,y2-y1));
      });
    }
    function overlay(values, color) {
      if (!Array.isArray(values)) return;
      ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.beginPath();var started=false;
      values.slice(start, start+candles.length).forEach(function(v,i){if(v==null||!Number.isFinite(Number(v)))return;var x=xFor(i),y=yPrice(Number(v));if(!started){ctx.moveTo(x,y);started=true;}else ctx.lineTo(x,y);});
      if(started)ctx.stroke();
    }
    var maSeries = chart.indicators && chart.indicators.series && chart.indicators.series.ma;
    if (chartLayers.ma && maSeries) Object.keys(chartLayers.maPeriods).forEach(function(period) { if (chartLayers.maPeriods[period]) overlay(maSeries[period], colors.ma[period]); });
    if (chartLayers.volume) {
      var vols=candles.map(function(c){return Number(c.volume)||0;}), vmax=Math.max.apply(null,vols)||1;
      vols.forEach(function(v,i){ctx.fillStyle=Number(candles[i].close)>=Number(candles[i].open)?colors.up:colors.down;var bh=(v/vmax)*volH;ctx.fillRect(xFor(i)-2,top+priceH+volH-bh,4,bh);});
    }
    if (chartLayers.macd && chart.indicators && chart.indicators.series.macd) {
      var macd = chart.indicators.series.macd, macdValues = (macd.line || []).slice(start,start+candles.length).concat((macd.signal || []).slice(start,start+candles.length)).filter(function(v){return v!=null&&Number.isFinite(Number(v));});
      var macdMax = Math.max.apply(null, macdValues.map(function(v){return Math.abs(Number(v));})) || 1;
      var macdBase = top + priceH + volH + macdH / 2, yMacd = function(v){return macdBase - Number(v) / macdMax * (macdH / 2 - 5);};
      var histogram = (macd.histogram || []).slice(start,start+candles.length);
      histogram.forEach(function(v,i){if(v==null||!Number.isFinite(Number(v)))return;ctx.fillStyle=Number(v)>=0?colors.up:colors.down;ctx.fillRect(xFor(i)-2,Math.min(macdBase,yMacd(v)),4,Math.max(1,Math.abs(yMacd(v)-macdBase)));});
      function oscillator(values,color,yMap){ctx.strokeStyle=color;ctx.lineWidth=1.25;ctx.beginPath();var begun=false;values.slice(start,start+candles.length).forEach(function(v,i){if(v==null||!Number.isFinite(Number(v)))return;var x=xFor(i),y=yMap(v);if(!begun){ctx.moveTo(x,y);begun=true;}else ctx.lineTo(x,y);});if(begun)ctx.stroke();}
      oscillator(macd.line || [], colors.macd, yMacd); oscillator(macd.signal || [], colors.signal, yMacd);
    }
    if (chartLayers.rsi) {
      var rsi=chart.indicators && Array.isArray(chart.indicators.series.rsi)?chart.indicators.series.rsi.slice(start,start+candles.length):[];
      ctx.strokeStyle=colors.rsi;ctx.lineWidth=1.5;ctx.beginPath();var rs=false;
      rsi.forEach(function(v,i){if(v==null||!Number.isFinite(Number(v)))return;var x=xFor(i),y=top+priceH+volH+macdH+rsiH-(Number(v)/100)*rsiH;if(!rs){ctx.moveTo(x,y);rs=true;}else ctx.lineTo(x,y);});if(rs)ctx.stroke();
      ctx.strokeStyle=colors.grid;ctx.setLineDash([3,3]);[30,70].forEach(function(v){var y=top+priceH+volH+macdH+rsiH-(v/100)*rsiH;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();});ctx.setLineDash([]);
    }
    // Decision levels live on the price chart; no duplicate metric boxes below it.
    var decisionLabelYs = [];
    function decisionLine(value, color, dash, label) {
      value = Number(value);
      if (!Number.isFinite(value)) return;
      var y = yPrice(value);
      ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.setLineDash(dash);
      ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(w - right, y); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = color; ctx.font = "11px sans-serif";
      var labelY = Math.max(top + 12, Math.min(top + priceH - 2, y - 4));
      var attempts = 0;
      while (decisionLabelYs.some(function(previous) { return Math.abs(previous - labelY) < 14; }) && attempts < 20) {
        labelY += 14;
        if (labelY > top + priceH - 2) labelY = Math.max(top + 12, labelY - 28);
        attempts += 1;
      }
      decisionLabelYs.push(labelY);
      ctx.fillText(label + " " + value.toFixed(2), left + 4, labelY);
    }
    if (chart.timeframe === "60M") {
      decisionLine(chart.trigger, "#60a5fa", [7, 5], "Required close");
      decisionLine(chart.stop, "#8896a6", [2, 4], "Stop");
      decisionLine(chart.target, "#93c5fd", [11, 4, 2, 4], "Target");
    }
    if (chartLayers.waveEvidence && chart.timeframe === "1D") {
      var markerLabelBoxes = [];
      dailyWaveMarkers.forEach(function(marker) {
        var sourceIndex = chart.candles.findIndex(function(c) { return chartTimestampKey(c.date) === chartTimestampKey(marker.timestamp); });
        if (sourceIndex < start || sourceIndex >= start + candles.length || sourceIndex < 0) return;
        var price = Number(marker.price); if (!Number.isFinite(price)) return;
        var localIndex = sourceIndex - start, x = xFor(localIndex), y = yPrice(price);
        var presentation = dailyWaveMarkerPresentation(marker.kind);
        if (!presentation) return;
        ctx.strokeStyle = presentation.color;
        ctx.fillStyle = ctx.strokeStyle;
        ctx.lineWidth = 1.5;
        var shape = presentation.shape;
        ctx.beginPath();
        if (shape === "square") ctx.rect(x - 4, y - 4, 8, 8);
        else if (shape === "diamond") { ctx.moveTo(x, y - 5); ctx.lineTo(x + 5, y); ctx.lineTo(x, y + 5); ctx.lineTo(x - 5, y); ctx.closePath(); }
        else if (shape === "triangle") { ctx.moveTo(x, y - 5); ctx.lineTo(x + 5, y + 4); ctx.lineTo(x - 5, y + 4); ctx.closePath(); }
        else if (shape === "cross") { ctx.moveTo(x - 4, y - 4); ctx.lineTo(x + 4, y + 4); ctx.moveTo(x + 4, y - 4); ctx.lineTo(x - 4, y + 4); }
        else ctx.arc(x, y, 4, 0, Math.PI * 2);
        shape === "cross" ? ctx.stroke() : ctx.fill();
        var label = presentation.label;
        var labelWidth = ctx.measureText(label).width;
        var labelX = Math.max(left, Math.min(w - right - labelWidth, x - labelWidth / 2));
        var labelY = Math.max(top + 11, Math.min(top + priceH - 2, y - 9));
        var attempts = 0;
        while (markerLabelBoxes.some(function(box) {
          return labelX < box.right + 4 && labelX + labelWidth > box.left - 4 &&
            labelY > box.top - 12 && labelY - 12 < box.bottom + 2;
        }) && attempts < 12) {
          labelY += 13;
          if (labelY > top + priceH - 2) labelY = Math.max(top + 11, y - 22 - attempts * 4);
          attempts += 1;
        }
        markerLabelBoxes.push({left: labelX, right: labelX + labelWidth, top: labelY - 12, bottom: labelY + 2});
        ctx.fillText(label, labelX, labelY);
        window.__signalixWaveMarkerHits.push({x: x, y: y, marker: marker});
      });
    }
  }

  function usableChartCandles(chart) {
    return chart && Array.isArray(chart.candles) ? chart.candles.filter(function (candle) {
      return candle && ["open", "high", "low", "close"].every(function (field) {
        return candle[field] != null && Number.isFinite(Number(candle[field]));
      });
    }) : [];
  }

  function renderDrawerChart(chart) {
    window.__signalixLastChart = chart; renderChartLegend(chart); renderTechnicalSummary(chart);
    if (usableChartCandles(chart).length >= 2) {
      dom.drawerChartPH.style.display = "none"; dom.drawerCanvas.style.display = "block"; if (dom.drawerChartRetry) dom.drawerChartRetry.hidden = true; drawChart(chart);
    } else {
      dom.drawerChartPH.style.display = "block"; dom.drawerChartPH.textContent = "Chart unavailable: insufficient candle history";
      dom.drawerCanvas.style.display = "none"; if (dom.drawerChartRetry) dom.drawerChartRetry.hidden = true;
    }
  }

  function bindEvents() {
    if (!dom.drawer) return;
    dom.drawerClose.addEventListener("click", closeSharedDrawer);
    dom.drawerOverlay.addEventListener("click", closeSharedDrawer);
    dom.drawerPrev.addEventListener("click", function () { navigateSharedDrawer(-1); });
    dom.drawerNext.addEventListener("click", function () { navigateSharedDrawer(1); });
    dom.drawerBody.addEventListener("touchstart", function (event) {
      if (!event.touches || event.touches.length !== 1) return;
      swipeStart = {x: event.touches[0].clientX, y: event.touches[0].clientY};
    }, {passive: true});
    dom.drawerBody.addEventListener("touchend", function (event) {
      if (!swipeStart || !event.changedTouches || event.changedTouches.length !== 1) { swipeStart = null; return; }
      var touch = event.changedTouches[0], deltaX = touch.clientX - swipeStart.x, deltaY = touch.clientY - swipeStart.y;
      swipeStart = null;
      if (Math.abs(deltaX) < 50 || Math.abs(deltaX) <= Math.abs(deltaY)) return;
      var target = event.target;
      if (target && typeof target.closest === "function" && target.closest("button, input, select, a")) return;
      navigateSharedDrawer(deltaX < 0 ? 1 : -1);
    }, {passive: true});
    $$(".chart-timeframe").forEach(function (button) { button.addEventListener("click", function () {
      chartTimeframe = button.getAttribute("data-timeframe") || "1D";
      var envelope = drawerItem && drawerItem.__sharedEnvelope; if (envelope) requestChart(envelope, chartSymbol, chartTimeframe, chartRequestSeq);
      setChartTimeframeButtons(chartTimeframe);
    }); });
    $$("[data-ma-period]").forEach(function (input) { input.addEventListener("change", function () {
      chartLayers.maPeriods[input.getAttribute("data-ma-period")] = input.checked;
      if (window.__signalixLastChart) drawChart(window.__signalixLastChart);
    }); });
    window.addEventListener("resize", function () { if (dom.drawer && !dom.drawer.classList.contains("drawer--hidden") && window.__signalixLastChart) drawChart(window.__signalixLastChart); });
    document.addEventListener("keydown", function (event) {
      if (!dom.drawer || dom.drawer.classList.contains("drawer--hidden")) return;
      if (event.key === "Escape") { closeSharedDrawer(); return; }
      if (event.key !== "Tab") return;
      var focusable = Array.prototype.slice.call(dom.drawer.querySelectorAll("a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex=\"-1\"])"));
      focusable = focusable.filter(function (element) {
        return !element.hidden && element.getAttribute("aria-hidden") !== "true" && !element.closest("[hidden],[aria-hidden=\"true\"]");
      });
      if (!focusable.length) { event.preventDefault(); return; }
      var first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
  }
  bindDom(); bindEvents();
  window.SignalixSharedDrawer = {openSharedDrawer: openSharedDrawer, closeSharedDrawer: closeSharedDrawer, drawChart: drawChart, updateNavigation: updateSharedDrawerNavigation};
})();
