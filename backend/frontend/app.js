/* ═══════════════════════════════════════════════════════════
   Signalix MVP Reset — Vanilla JS
   Owner-only. No auth. No tiers. No watchlist.
   Primary surface: Trend · Elliott · Trade Setup; VCP is audit/compatibility only
   States: loading / empty / stale / error / retry
   ═══════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  /* ── DOM refs ── */
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  const dom = {
    freshness:       $("#freshness"),
    freshnessDot:    $(".freshness-dot"),
    freshnessLabel:  $(".freshness-label"),
    freshnessDaily:  $("#freshness-daily"),
    freshness60m:    $("#freshness-60m"),

    tabShortlist:    $("#tab-shortlist"),
    tabExplorer:     $("#tab-explorer"),
    panelShortlist:  $("#panel-shortlist"),
    panelExplorer:   $("#panel-explorer"),
    tabDailyVcp:     $("#tab-daily-vcp"),
    panelDailyVcp:   $("#panel-daily-vcp"),
    dailyVcpLoading: $("#daily-vcp-loading"),
    dailyVcpError:   $("#daily-vcp-error"),
    dailyVcpErrorMsg: $("#daily-vcp-error-msg"),
    dailyVcpRetry:   $("#daily-vcp-retry"),
    dailyVcpContent: $("#daily-vcp-content"),
    dailyVcpCards:   $("#daily-vcp-cards"),
    dailyVcpMeta:    $("#daily-vcp-meta"),
    dailySetupSearch: $("#daily-setup-search"),
    dailySetupLane: $("#daily-setup-lane"),
    dailySetupWave: $("#daily-setup-wave"),
    dailySetupRefresh: $("#daily-setup-refresh"),
    dailySetupUpdated: $("#daily-setup-updated"),
    dailySetupLiveRefresh: $("#daily-setup-live-refresh"),
    dailySetupPrev:  $("#daily-setup-prev"),
    dailySetupNext:  $("#daily-setup-next"),
    dailySetupPageInfo: $("#daily-setup-page-info"),
    dailyFilterMarginable: $("#daily-filter-marginable"),
    dailyFilterTradeValue: $("#daily-filter-trade-value"),
    dailyFilterPrice: $("#daily-filter-price"),
    dailyVcpType:   $("#daily-vcp-type"),
    dailySetupSector: $("#daily-setup-sector"),
    dailyVcpDecisionState: $("#daily-vcp-decision-state"),
    dailyVcpDecision: $("#daily-vcp-decision"),
    dailyVcpQuality: $("#daily-vcp-quality"),
    tabVcp:          $("#tab-vcp"),
    panelVcp:        $("#panel-vcp"),
    vcpLoading:      $("#vcp-loading"),
    vcpError:        $("#vcp-error"),
    vcpErrorMsg:     $("#vcp-error-msg"),
    vcpRetry:        $("#vcp-retry"),
    vcpContent:      $("#vcp-content"),
    vcpCards:        $("#vcp-cards"),
    vcpState:        $("#vcp-state"),
    vcpDecisionState: $("#vcp-decision-state"),
    vcpDecision:     $("#vcp-decision"),
    vcpQuality:      $("#vcp-quality"),
    vcpType:         $("#vcp-type"),
    vcpPriceBand:    $("#vcp-price-band"),
    vcpMeta:         $("#vcp-meta"),
    vcpMarginAll:    $("#vcp-margin-all"),
    vcpMarginClear:  $("#vcp-margin-clear"),
    vcpFilterApply:  $("#vcp-filter-apply"),

    // shortlist states
    slLoading:     $("#shortlist-loading"),
    slError:       $("#shortlist-error"),
    slErrorMsg:    $("#shortlist-error-msg"),
    slRetry:       $("#shortlist-retry"),
    slEmpty:       $("#shortlist-empty"),
    slStale:       $("#shortlist-stale"),
    slStaleTime:   $("#shortlist-stale-time"),
    slStaleRetry:  $("#shortlist-stale-retry"),
    slMarginable: $("#shortlist-marginable"),
    slPriceBand: $("#shortlist-price-band"),
    slMarginableMeta: $("#shortlist-marginable-meta"),
    slRising:      $("#shortlist-rising"),
    slRisingCards: $("#shortlist-rising-cards"),
    slCaution:     $("#shortlist-caution"),
    slCautionCards: $("#shortlist-caution-cards"),
    slReadyCards:  $("#shortlist-ready-cards"),
    slPreCards:    $("#shortlist-pre-ready-cards"),

    // explorer states
    exLoading:     $("#explorer-loading"),
    exError:       $("#explorer-error"),
    exErrorMsg:    $("#explorer-error-msg"),
    exRetry:       $("#explorer-retry"),
    exEmpty:       $("#explorer-empty"),
    exCards:       $("#explorer-cards"),
    exPrev:        $("#explorer-prev"),
    exNext:        $("#explorer-next"),
    exPageInfo:    $("#explorer-page-info"),
    exStage:       $("#explorer-stage"),
    exSearch:      $("#explorer-search"),
    exMarginable:  $("#explorer-marginable"),
    exPriceBand:   $("#explorer-price-band"),

    // drawer
    drawer:        $("#drawer"),
    drawerOverlay: $("#drawer-overlay"),
    drawerClose:   $("#drawer-close"),
    drawerPrev:    $("#drawer-prev"),
    drawerNext:    $("#drawer-next"),
    drawerPosition: $("#drawer-position"),
    drawerSymbol:  $("#drawer-symbol"),
    drawerName:    $("#drawer-name"),
    drawerPrice:   $("#drawer-price"),
    drawerChange:  $("#drawer-change"),
    drawerTrend:    $("#drawer-trend"),
    drawerAction:   $("#drawer-action"),
    drawerWave:     $("#drawer-wave"),
    drawerWaveConfidence: $("#drawer-wave-confidence"),
    drawerWaveSource: $("#drawer-wave-source"),
    drawerWaveContext: $("#drawer-wave-context"),
    drawerSector:   $("#drawer-sector"),
    drawerIndustry: $("#drawer-industry"),
    drawerMarketCap: $("#drawer-market-cap"),
    drawerTradeValue: $("#drawer-trade-value"),
    drawerDescription: $("#drawer-description"),
    drawerChart:    $("#drawer-chart"),
    drawerCanvas:  $("#drawer-canvas"),
    drawerChartPH: $("#drawer-chart-placeholder"),
    drawerChartStatus: $("#drawer-chart-status"),
    drawerChartContext: $("#drawer-chart-context"),
    drawerChartLegend: $("#drawer-chart-legend"),
    chartWaveEvidence: $("#chart-wave-evidence"),
    chartWaveExplanation: $("#chart-wave-explanation"),
    methodGuide: $("#method-guide"),
    methodGuideContent: $("#method-guide-content"),
    drawerMethodLink: $("#drawer-method-link"),
    indMa20:       $("#ind-ma20"),
    indMa50:       $("#ind-ma50"),
    indMa200:      $("#ind-ma200"),
    indMacd:       $("#ind-macd"),
    indRsi:        $("#ind-rsi"),
    indTrigger:    $("#ind-trigger"),
    indStop:       $("#ind-stop"),
    indTarget:     $("#ind-target"),
    drawerTarget:   $("#drawer-target"),
    drawerTrigger:  $("#drawer-trigger"),
    drawerStop:     $("#drawer-stop"),
    drawerRR:       $("#drawer-rr"),
    drawerV2Decision: $("#drawer-v2-decision"),
    drawerRawState: $("#drawer-raw-state"),
    drawerMembership: $("#drawer-membership"),
    drawerMargin:   $("#drawer-margin"),
    drawer52W:      $("#drawer-52w"),
    drawerATH:      $("#drawer-ath"),
    drawerProv:     $("#drawer-provenance"),
  };

  /* ── state ── */
  let currentTab = "daily-vcp";
  let explorerPage = 1;
  let explorerTotalPages = 1;
  let explorerStage = "";
  let explorerSearch = "";
  let marginableFilter = "krungsri";
  let marginRates = [];
  let priceBand = [];
  let shortlistData = null;
  let vcpResultsBySymbol = {};
  let vcpRunMeta = {};
  const chartLayers = { candles: true, volume: true, ma: true, rsi: true, waveEvidence: true };
  let chartTimeframe = "1D";
  let chartSymbol = null;
  let drawerSymbols = [];
  let drawerItems = [];
  let drawerIndex = -1;
  let drawerItem = null;
  let drawerTouchStartX = null;
  let chartRequestSeq = 0;
  let chartAbort = null;
  var chartCache = {};
  let dailyVcpRequestSeq = 0;
  let dailySetupPage = 1;
  let dailySetupTotalPages = 1;
  let dailySetupData = null;
  let liveRefreshEnabled = false;
  let liveRefreshTimer = null;
  let vcpRequestSeq = 0;
  var dailyVcpRequests = SignalixRequestCache();
  var vcpRequests = SignalixRequestCache();

  /* ── helpers ── */
  function hideAll(cls) { $$(cls).forEach(function(el) { el.classList.add("state--hidden"); }); }
  function show(el) { if (el) el.classList.remove("state--hidden"); }
  function hide(el) { if (el) el.classList.add("state--hidden"); }

  function fmtChange(pct) {
    if (pct == null) return ["0.00%", "flat"];
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

  function compactText(value, max) {
    var text = String(value == null ? "" : value).trim();
    if (text.length <= max) return text;
    return text.slice(0, max - 1).trimEnd() + "…";
  }

  function fmtChangeAmount(value) {
    if (value == null || Number.isNaN(Number(value))) return "–";
    var n = Number(value);
    return (n >= 0 ? "+" : "") + n.toFixed(2);
  }

  function shortStage(value) {
    return ({S2_uptrend: "S2 Uptrend", S1_basing: "S1 Base", S3_distributing: "S3 Distribution", S4_down: "S4 Down"})[value] || value || "–";
  }

  function stageClass(value) {
    return ({S1_basing: "s1", S2_uptrend: "s2", S3_distributing: "s3", S4_down: "s4"})[value] || "unknown";
  }

  function shortAction(value) {
    return ({"VALIDATE FRESH BREAKOUT": "Fresh Breakout", "QUALIFIED PULLBACK": "Pullback", "WAIT FOR CONFIRMATION": "Wait for Breakout"})[value] || compactText(value || "", 20);
  }

  function vcpTypeLabel(result) {
    var state = canonicalDecisionState(result);
    if (canonicalDataSufficiency(result) !== "SUFFICIENT") return null;
    if (["INVALIDATED", "NOT_VERIFIED"].indexOf(state) >= 0) return null;
    var base = (result.vcp_type || {}).base_type;
    return base === "low_cheat_vcp" ? "Low-Cheat" : base === "standard_vcp" ? "VCP" : null;
  }

  function vcpTypeMatches(result, selected) {
    return !selected || selected === "all" || (result.vcp_type || {}).base_type === selected;
  }

  function canonicalDecision(result) {
    return result && result.decision && typeof result.decision === "object" ? result.decision : {};
  }

  function decisionShadowV2(result) {
    return result && result.decision_shadow_v2 && typeof result.decision_shadow_v2 === "object" ? result.decision_shadow_v2 : {};
  }

  function decisionLane(result) {
    var shadow = decisionShadowV2(result);
    return shadow.decision_lane || (result && result.decision_lane) || "DATA_BLOCKED";
  }

  function actionability(result) {
    var shadow = decisionShadowV2(result);
    return shadow.actionability || (result && result.actionability) || "NO_ACTION";
  }

  function canonicalDecisionState(result) {
    var decision = canonicalDecision(result);
    return decision.state || "NOT_VERIFIED";
  }

  function canonicalDecisionValue(result) {
    return canonicalDecision(result).decision || "UNKNOWN";
  }

  function canonicalQuality(result) {
    return canonicalDecision(result).quality || "UNKNOWN";
  }

  function canonicalDataSufficiency(result) {
    var value = canonicalDecision(result).data_sufficient;
    return value === true ? "SUFFICIENT" : value === false ? "INSUFFICIENT" : "UNKNOWN";
  }

  function canonicalFilterMatches(result, stateSelect, decisionSelect, qualitySelect) {
    var decisionState = stateSelect && stateSelect.value || "ALL";
    var decision = decisionSelect && decisionSelect.value || "ALL";
    var quality = qualitySelect && qualitySelect.value || "ALL";
    return (decisionState === "ALL" || canonicalDecisionState(result) === decisionState)
      && (decision === "ALL" || canonicalDecisionValue(result) === decision)
      && (quality === "ALL" || canonicalQuality(result) === quality);
  }

  function vcpRiskReward(result) {
    // VCP rows may carry the canonical Daily projection's rr enrichment.
    // Never calculate R/R or interpret scoring fields as a ratio here.
    var value = result && result.rr;
    return value == null || value === "" || !Number.isFinite(Number(value)) ? null : Number(value);
  }

  function escapeHTML(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  function timeAgo(iso) {
    if (!iso) return "–";
    try {
      var then = new Date(iso);
      var now = new Date();
      var diff = (now - then) / 1000;
      if (diff < 60) return "just now";
      if (diff < 3600) return Math.floor(diff / 60) + "m ago";
      if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
      return Math.floor(diff / 86400) + "d ago";
    } catch (e) { return "–"; }
  }

  function formatProvenance(iso) {
    if (!iso) return "–";
    try {
      // A date-only value has no time-of-day. Never reinterpret it as UTC midnight.
      if (/^\d{4}-\d{2}-\d{2}$/.test(String(iso))) {
        var dateOnly = new Date(String(iso) + "T00:00:00Z");
        return dateOnly.toLocaleDateString("en-GB", {day:"2-digit", month:"short", year:"numeric", timeZone:"Asia/Bangkok"})
          + " time unavailable (Bangkok)";
      }
      var d = new Date(iso);
      return d.toLocaleDateString("en-GB", {day:"2-digit", month:"short", year:"numeric", timeZone:"Asia/Bangkok"})
        + " " + d.toLocaleTimeString("en-GB", {hour:"2-digit", minute:"2-digit", second:"2-digit", hour12:false, timeZone:"Asia/Bangkok"})
        + " ICT (Bangkok)";
    } catch (e) { return "–"; }
  }

  function displayValue(value) {
    return value == null || value === "" ? "NOT_VERIFIED" : value;
  }

  function displayMetadataValue(value, pending) {
    if (value != null && value !== "") return value;
    return pending ? "Loading…" : "Unavailable";
  }

  function setupReadinessLabel(item, setup) {
    var status = String((setup || {}).status || "").toUpperCase();
    if (item && item.decision_lane === "DATA_BLOCKED") return "Data blocked";
    if (status === "FORMING" || status === "PRE_TRIGGER" || !setup.trigger) {
      return setup.minor_structure ? "Awaiting 60m structure" : "Setup forming";
    }
    if (status === "TESTED_TRIGGER") return "Trigger tested · awaiting close";
    if (status === "TRIGGERED") return "Triggered";
    return status ? status.replaceAll("_", " ") : "Not ready";
  }

  function marginBadge(item) {
    var rate = item.margin_rate_pct != null ? item.margin_rate_pct : item.margin_pct;
    return rate == null ? "" : '<span class="marginable-badge">%Margin ' + Number(rate).toFixed(0) + '%</span>';
  }

  function marginFilterMeta(data) {
    var source = data && data.marginable_source || {};
    var total = source.total == null ? "–" : source.total;
    var ord = source.ord_total == null ? "–" : source.ord_total;
    var dr = source.dr_total == null ? "–" : source.dr_total;
    var date = source.effective_date || "NOT_VERIFIED";
    return "Krungsri list · " + total + " securities (" + ord + " ORD + " + dr + " DR) · effective " + date;
  }

  function marginableUniverseMeta(data) {
    var universe = data && data.universe || {};
    var selected = data && data.eligible_count != null ? data.eligible_count : universe.eligible;
    var filter = data && data.universe_filter || "marginable_long";
    var source = data && (data.margin_source_document || data.margin_source) || "NOT_VERIFIED";
    var effective = data && data.margin_effective_date || "NOT_VERIFIED";
    return "Universe " + filter + " · " + (selected == null ? "NOT_VERIFIED" : selected) + " selected · source " + source + " · effective " + effective;
  }

  function formatRange(high, low, pending) {
    if (high == null && low == null) return pending ? "Loading…" : "Unavailable";
    return (high == null ? "–" : Number(high).toFixed(2)) + " / " + (low == null ? "–" : Number(low).toFixed(2));
  }

  /* ── freshness ── */
  function normalizeFreshnessStatus(status) {
    status = String(status || "unknown").toLowerCase();
    return status === "latest_available" || status === "expected_previous_session" ? "expected_previous" : status;
  }

  function freshnessSummary(dailyStatus, intradayStatus) {
    var daily = normalizeFreshnessStatus(dailyStatus);
    var intraday = normalizeFreshnessStatus(intradayStatus);
    if (daily === "loading" || intraday === "loading") return "loading";
    if (daily === "unknown" && intraday === "unknown") return "unknown";
    if (daily === intraday) return daily;
    return daily === "unknown" || intraday === "unknown" ? "partial" : "mixed";
  }

  function freshnessTimeLabel(prefix, status, timestamp) {
    status = normalizeFreshnessStatus(status);
    if (status === "loading") return prefix + ": Loading…";
    if (status === "fresh" || status === "market_closed") return prefix + ": fresh · " + timeAgo(timestamp);
    if (status === "expected_previous") return prefix + ": expected previous completed session · " + timeAgo(timestamp);
    if (status === "stale") return prefix + ": stale · " + timeAgo(timestamp);
    return prefix + ": unavailable";
  }

  function setFreshness(status, asOf, intradayAt, dailyStatus, intradayStatus) {
    var effectiveDailyStatus = normalizeFreshnessStatus(dailyStatus || status);
    var effectiveIntradayStatus = normalizeFreshnessStatus(intradayStatus || (intradayAt ? "fresh" : "unknown"));
    var summary = freshnessSummary(effectiveDailyStatus, effectiveIntradayStatus);
    dom.freshnessDot.className = "freshness-dot freshness-dot--" + (summary === "mixed" || summary === "partial" ? "stale" : summary);
    var daily = freshnessTimeLabel("Daily EOD", effectiveDailyStatus, asOf);
    var intraday = freshnessTimeLabel("60m", effectiveIntradayStatus, intradayAt);
    if (dom.freshnessDaily) dom.freshnessDaily.textContent = daily;
    if (dom.freshness60m) dom.freshness60m.textContent = intraday;
    dom.freshnessLabel.textContent = summary === "loading" ? "Freshness loading…"
      : summary === "fresh" || summary === "market_closed" ? "Freshness available"
      : summary === "expected_previous" ? "Freshness current through previous completed session"
      : summary === "mixed" ? "Freshness mixed by timeframe"
      : summary === "partial" ? "Freshness partial by timeframe"
      : summary === "stale" ? "Freshness stale"
      : "Freshness unavailable";
  }

  /* ── render card ── */
  function buildDecisionCard(item) {
    var chg = fmtChange(item.change_pct);
    var changeAmount = fmtChangeAmount(item.change_amount);
    var action = shortAction(item.action || item.phase || "");
    var stage = shortStage(item.stage);
    var watchNote = item.watch_state ? '<div class="decision-card__watch-note"><strong>' + escapeHTML(item.watch_state === "CAUTION" ? "DO NOT CHASE" : "WATCH ONLY") + '</strong> · ' + escapeHTML(item.watch_reason || "Price/volume move; setup not actionable") + '</div>' : '';
    return "" +
      '<div class="decision-card" data-symbol="' + escapeHTML(item.symbol) + '">' +
        '<div class="decision-card__top">' +
          '<div><span class="decision-card__symbol">' + escapeHTML(item.symbol) + '</span></div>' +
          '<div style="text-align:right">' +
            '<div class="decision-card__price">' + (item.close != null ? item.close.toFixed(2) : "–") + '</div>' +
            '<div class="decision-card__change decision-card__change--' + chg[1] + '">' + chg[0] + ' <span class="decision-card__change-amount">(' + changeAmount + ')</span></div>' +
          '</div>' +
        '</div>' +
        '<div class="decision-card__mid">' +
          '<span class="decision-card__stage decision-card__stage--' + stageClass(item.stage) + '">' + escapeHTML(stage) + '</span>' +
          '<span class="decision-card__action">' + escapeHTML(action) + '</span>' +
        '</div>' +
        watchNote +
        '<div class="decision-card__meta">' +
          '<span>Stop ' + (item.risk_stop != null ? item.risk_stop.toFixed(2) : "–") + '</span>' +
          '<span>RS ' + (item.rs != null ? Math.round(item.rs) : "–") + '</span>' +
          '<span>Vol ' + fmtNum(item.avgDailyValue20) + '</span>' +
          marginBadge(item) +
        '</div>' +
        '<div class="decision-card__risk">' +
          '<span>Required close ' + escapeHTML(item.trigger || "NOT_VERIFIED") + '</span>' +
          '<span>Stop ' + (item.risk_stop != null ? item.risk_stop.toFixed(2) : "NOT_VERIFIED") + '</span>' +
          '<span>Target ' + (item.target != null ? item.target.toFixed(2) : "NOT_VERIFIED") + '</span>' +
        '</div>' +
      '</div>';
  }

  function buildExplorerCard(item) {
    var chg = fmtChange(item.change_pct);
    return "" +
      '<div class="explorer-card" data-symbol="' + escapeHTML(item.symbol) + '">' +
        '<div class="explorer-card__row">' +
          '<span class="explorer-card__symbol">' + escapeHTML(item.symbol) + '</span>' +
          '<span class="explorer-card__name">' + escapeHTML(item.name || "") + '</span>' +
          '<span class="explorer-card__stage explorer-card__stage--' + stageClass(item.stage) + '">' + escapeHTML(shortStage(item.stage)) + '</span>' +
          marginBadge(item) +
          '<span class="explorer-card__price ' + (chg[1] !== "flat" ? "decision-card__change--" + chg[1] : "") + '">' +
            (item.close != null ? item.close.toFixed(2) : "–") +
          '</span>' +
        '</div>' +
      '</div>';
  }

  function setOptionalDrawerField(el, value) {
    var present = value != null && String(value).trim() !== "";
    el.textContent = present ? String(value) : "";
    var row = el.closest(".drawer-field");
    if (row) row.hidden = !present;
  }

  function vcpChartOverlay(item) {
    var vr = item && item.vcp_result;
    if (!vr) return {};
    var price = vr.price || {};
    var breakout = vr.breakout || {};
    return {
      trigger: breakout.required_close != null ? breakout.required_close : item.trigger,
      stop: price.invalidation != null ? price.invalidation : item.risk_stop,
      target: item.target != null ? item.target : vr.target
    };
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

  function mergeChartDecisionOverlay(chart, item) {
    var overlay = item && item.decision_lane ? canonicalChartOverlay(item) : vcpChartOverlay(item);
    ["trigger", "stop", "target"].forEach(function(field) {
      if (overlay[field] != null) chart[field] = overlay[field];
    });
    var timeframe = chart.timeframe || chartTimeframe;
    var evidence = item && item.setup && item.setup.chart_evidence;
    // Keep the compatibility surface readable for older VCP drawer items;
    // canonical setup candidates use setup.chart_evidence above.
    if (!evidence && item) evidence = item.chart_evidence;
    if (evidence) {
      var bucket = timeframe === "1D" ? evidence.daily : timeframe === "60M" ? evidence["60m"] : null;
      if (bucket) chart.wave_evidence = bucket;
    }
    if (timeframe === "1D" && item && item.decision_lane) {
      // Canonical Daily markers live under wave.evidence_markers. Use those
      // exact source coordinates; never derive marker points from chart bars.
      chart.wave_evidence = waveEvidenceForItem(item);
    }
    return chart;
  }

  function waveEvidenceText(value) {
    if (value == null || value === "") return "Unavailable";
    if (Array.isArray(value)) {
      var values = value.map(waveEvidenceText).filter(function(entry) { return entry !== "Unavailable"; });
      return values.length ? values.join(" · ") : "Unavailable";
    }
    if (typeof value === "object") {
      try { return JSON.stringify(value); } catch (e) { return "Unavailable"; }
    }
    return String(value);
  }

  var canonicalDailyWaveStates = ["WAVE_1_ADVANCE", "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION",
    "EARLY_WAVE_3", "WAVE_3_CONTINUATION", "WAVE_4_CORRECTION", "WAVE_5_ADVANCE"];

  function waveContextForItem(item) {
    var wave = item && item.wave;
    var context = wave && typeof wave === "object" && !Array.isArray(wave) ? wave.context : null;
    return context && typeof context === "object" && !Array.isArray(context) ? context : null;
  }

  function canonicalWaveState(item) {
    var context = waveContextForItem(item);
    var state = context && context.mapped_state;
    return canonicalDailyWaveStates.indexOf(state) >= 0 ? state : "Unknown / Not verified";
  }

  function setupCandidateWaveBucket(item) {
    var context = waveContextForItem(item);
    var state = context && context.mapped_state;
    return canonicalDailyWaveStates.indexOf(state) >= 0 ? state : "UNKNOWN";
  }

  function compactWaveConfidence(item) {
    var context = waveContextForItem(item);
    var confidence = context && context.confidence;
    confidence = confidence == null ? "" : String(confidence).toUpperCase();
    return ["LOW", "MEDIUM", "HIGH"].indexOf(confidence) >= 0 ? confidence : "NOT_VERIFIED";
  }

  function waveContextPresentation(item) {
    var context = waveContextForItem(item);
    var state = canonicalWaveState(item);
    var secondary = context && Array.isArray(context.secondary_markers)
      ? context.secondary_markers.filter(function(value) { return value === "WAVE_3_EXTENDED"; }) : [];
    var nonActionable = ["WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "WAVE_4_CORRECTION", "Unknown / Not verified"].indexOf(state) >= 0;
    return {
      state: state, secondary: secondary, confidence: compactWaveConfidence(item),
      rule: context && context.rule_version,
      source: context && context.source_timeframe === "daily" ? "Daily structural · daily" : "Daily structural · source unavailable",
      supporting: context && context.supporting_evidence, contradicting: context && context.contradicting_evidence,
      missing: context && context.missing_evidence, rationale: context && context.rationale,
      firstDate: context && context.first_context_date, lastDate: context && context.last_context_date,
      transitions: context && Array.isArray(context.transitions) ? context.transitions : [],
      actionability: item && item.decision_lane === "REVIEW_NOW" ? "Review eligible · backend REVIEW_NOW" :
        nonActionable ? "Non-actionable context · backend lane " + ((item && item.decision_lane) || "DATA_BLOCKED") :
        "Not review eligible · backend lane " + ((item && item.decision_lane) || "DATA_BLOCKED")
    };
  }

  function renderWaveContextDetail(item) {
    if (!dom.drawerWaveContext) return;
    var view = waveContextPresentation(item);
    var evidenceRow = function(label, value) {
      return '<div><dt>' + label + '</dt><dd>' + escapeHTML(waveEvidenceText(value)) + '</dd></div>';
    };
    var transitions = view.transitions.length ? view.transitions.map(function(entry) {
      return '<li>' + escapeHTML(waveEvidenceText(entry)) + '</li>';
    }).join("") : '<li>Unavailable · no source-linked transition history</li>';
    dom.drawerWaveContext.innerHTML = '<strong class="wave-context-detail__status">' + escapeHTML(view.actionability) + '</strong>' +
      '<dl>' + evidenceRow("Secondary", view.secondary) + evidenceRow("Rule", view.rule) +
      evidenceRow("First / last context", view.firstDate && view.lastDate ? view.firstDate + " / " + view.lastDate : null) +
      evidenceRow("Supporting", view.supporting) + evidenceRow("Contradicting", view.contradicting) +
      evidenceRow("Missing", view.missing) + evidenceRow("Rationale", view.rationale) + '</dl>' +
      '<div class="wave-context-transitions"><span>Source transitions</span><ul>' + transitions + '</ul></div>';
  }

  function showWaveExplanation(marker) {
    var panel = dom.chartWaveExplanation;
    var guide = dom.methodGuideContent;
    if (!panel) return;
    if (!marker || typeof marker !== "object" || Array.isArray(marker)) {
      if (guide) guide.textContent = "No wave evidence is available for this candidate.";
      // Legacy drawer reset shape retained as a compatibility comment:
      // panel.hidden = true; panel.textContent = ""; return;
      return;
    }
    var valid = marker;
    var details = marker.explanation && typeof marker.explanation === "object" && !Array.isArray(marker.explanation)
      ? marker.explanation : valid;
    function text(value) { return waveEvidenceText(value); }
    var refs = Array.isArray(marker.evidence_refs) ? marker.evidence_refs.map(text).filter(function(ref) {
      return ref !== "Unavailable";
    }) : [];
    var snapshot = marker.snapshot_identity || marker.snapshot_id;
    if (guide) guide.innerHTML = "<strong>How this wave was identified</strong>" +
      "<div>Timeframe: " + escapeHTML(text(marker.timeframe)) + " · Source: " + escapeHTML(text(marker.source)) + "</div>" +
      "<div>Confidence: " + escapeHTML(text(marker.confidence)) + "</div>" +
      "<div>Rule: " + escapeHTML(text(details.rule)) + "</div>" +
      "<div>Supporting evidence: " + escapeHTML(text(details.supporting_evidence != null ? details.supporting_evidence : details.evidence)) + "</div>" +
      "<div>Contradicting evidence: " + escapeHTML(text(details.contradicting_evidence)) + "</div>" +
      "<div>Missing evidence: " + escapeHTML(text(details.missing_evidence != null ? details.missing_evidence : details.missing)) + "</div>" +
      "<div>Alternative state: " + escapeHTML(text(details.alternative_state != null ? details.alternative_state : details.alternative)) + " · Policy: " + escapeHTML(text(details.policy)) + "</div>" +
      "<div>Evidence refs: " + escapeHTML(refs.length ? refs.join(" · ") : "Unavailable") + "</div>" +
      "<div>Snapshot: " + escapeHTML(text(snapshot)) + " · identity</div>";
    panel.hidden = false;
  }

  function waveEvidenceForItem(item) {
    var wave = item && item.wave;
    if (!wave || typeof wave !== "object" || Array.isArray(wave)) return {};
    var context = wave.context && typeof wave.context === "object" && !Array.isArray(wave.context) ? wave.context : {};
    var provenance = item.provenance && typeof item.provenance === "object" && !Array.isArray(item.provenance) ? item.provenance : {};
    var explanation = wave.evidence_explanation && typeof wave.evidence_explanation === "object" && !Array.isArray(wave.evidence_explanation)
      ? wave.evidence_explanation : wave.explanation && typeof wave.explanation === "object" && !Array.isArray(wave.explanation) ? wave.explanation : {};
    return {
      timeframe: "1D", source: provenance.daily_source || "price_data", confidence: context.confidence || wave.confidence,
      rule: context.rule_version || explanation.rule, evidence: explanation.evidence, policy: explanation.policy,
      supporting_evidence: context.supporting_evidence || wave.supporting_evidence,
      contradicting_evidence: context.contradicting_evidence || wave.contradicting_evidence,
      missing_evidence: context.missing_evidence || wave.missing_evidence, alternative_state: wave.alternative_state,
      snapshot_identity: wave.snapshot_identity || wave.snapshot_id || provenance.snapshot_identity || provenance.snapshot_id,
      evidence_refs: explanation.evidence_refs,
      markers: window.SignalixCanonicalClient.markers(item)
    };
  }

  function renderDrawerDetail(item) {
    if (item.vcp_result) {
      var vr = item.vcp_result;
      var vp = vr.price || {};
      var vd = vr.data || {};
      var vm = vcpRunMeta || {};
      var overlay = vcpChartOverlay(item);
      item = Object.assign({}, item, {
        name: item.symbol,
        action: vcpPrimaryStatus(vr),
        close: vp.last_close,
        change_pct: vp.change_pct,
        trigger: overlay.trigger,
        risk_stop: overlay.stop,
        avgDailyValue20: (vd.daily_metrics || {}).avg_trade_value_20,
        index_membership: vr.index_membership || [],
        margin_rate_pct: vr.margin_rate_pct,
        description: null,
        provenance: {source: "intraday_price_data", interval: "60m", scan_run_id: vm.run_id || "", scan_time: vm.fetch_completed_at || vm.as_of || "", latest_closed_bar: vd.latest_closed_bar || vd.last_bar_ts || ""}
      });
    }
    dom.drawerSymbol.textContent = item.symbol;
    dom.drawerSymbol.href = "https://www.tradingview.com/symbols/" + encodeURIComponent(item.symbol) + "/?exchange=SET";
    dom.drawerName.textContent = item.name || "–";
    dom.drawerTrend.textContent = shortStage(item.stage);
    dom.drawerAction.textContent = item.vcp_result ? item.action : shortAction(item.action || item.phase);
    if (dom.drawerWave) dom.drawerWave.textContent = canonicalWaveState(item);
    if (dom.drawerWaveConfidence) dom.drawerWaveConfidence.textContent = compactWaveConfidence(item);
    if (dom.drawerWaveSource) dom.drawerWaveSource.textContent = waveContextPresentation(item).source;
    renderWaveContextDetail(item);
    if (dom.drawerV2Decision) setOptionalDrawerField(dom.drawerV2Decision, item.vcp_result ? vcpPrimaryStatus(item.vcp_result) : null);
    if (dom.drawerRawState) setOptionalDrawerField(dom.drawerRawState, item.vcp_result ? (item.vcp_result.state || "NOT_VERIFIED") : null);
    dom.drawerSector.textContent = item.sector || "Sector –";
    dom.drawerIndustry.textContent = item.industry || "Industry –";
    dom.drawerMarketCap.textContent = "Market cap " + fmtNum(item.market_cap);
    dom.drawerTradeValue.textContent = "Trade value " + fmtNum(item.trade_value || item.avgDailyValue20);
    dom.drawerDescription.textContent = item.description || "";
    dom.drawerDescription.hidden = !item.description;
    dom.drawerPrice.textContent = item.close != null ? Number(item.close).toFixed(2) : "–";
    var drawerChg = fmtChange(item.change_pct);
    dom.drawerChange.textContent = drawerChg[0] + " (" + fmtChangeAmount(item.change_amount) + ")";
    var metadataPending = item._canonicalMetadataPending === true;
    dom.drawerRR.textContent = displayMetadataValue(item.rr != null ? Number(item.rr).toFixed(2) + "R" : null, metadataPending);
    setOptionalDrawerField(dom.drawerMembership, (item.index_membership || []).join(" · "));
    var marginRate = item.margin_rate_pct != null ? item.margin_rate_pct : item.margin_pct;
    setOptionalDrawerField(dom.drawerMargin, marginRate != null ? Number(marginRate).toFixed(0) + "%" : null);
    dom.drawer52W.textContent = formatRange(item.high52, item.low52, metadataPending);
    dom.drawerATH.textContent = formatRange(item.ath_high, item.ath_low, metadataPending);
    var prov = item.provenance || {};
    dom.drawerProv.textContent = formatProvenance(prov.scan_time || item.as_of);
    showWaveExplanation(waveEvidenceForItem(item));
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

  function renderChartStatus(chart) {
    if (!dom.drawerChartStatus) return;
    var candles = chart && Array.isArray(chart.candles) ? chart.candles : [];
    var latest = candles.length ? candles[candles.length - 1] : null;
    var provisional = chart && chart.provisional === true;
    if (chart && chart.candles && chart.candles.length && chart.candles[chart.candles.length - 1].provisional === true) provisional = true;
    var timestamp = chart && chart.latest_time || (latest && (latest.date || latest.time));
    var label = provisional ? "Provisional · current candle" : "Confirmed candle";
    dom.drawerChartStatus.textContent = "Chart status: " + label + (timestamp ? " · " + timestamp : "");
    dom.drawerChartStatus.classList.toggle("chart-status--provisional", provisional);
    if (dom.drawerChartContext) {
      var timeframe = chart && chart.timeframe || chartTimeframe;
      var source = chart && chart.provenance && (chart.provenance.source || chart.provenance.interval);
      var sourceLabel = timeframe === "60M" ? "60m intraday price data" : timeframe === "1W" ? "Weekly price data" : "Daily price data";
      dom.drawerChartContext.textContent = "Timeframe: " + timeframe + " · Source: " + (source || sourceLabel);
    }
  }

  function renderChartLegend(chart) {
    if (!dom.drawerChartLegend) return;
    var isDaily = (chart && chart.timeframe || chartTimeframe) === "1D";
    var markers = chart && chart.wave_evidence && Array.isArray(chart.wave_evidence.markers) ? chart.wave_evidence.markers : [];
    var dailyMarkerCount = markers.filter(function(marker) {
      return marker && marker.timeframe === "daily" && marker.timestamp != null && Number.isFinite(Number(marker.price));
    }).length;
    var markerState = isDaily ? (dailyMarkerCount ? dailyMarkerCount + " exact Daily source marker(s)" : "Daily markers unavailable") : "Daily markers shown on Day only";
    var timeframe = chart && chart.timeframe || chartTimeframe;
    dom.drawerChartLegend.innerHTML = '<span><i class="legend-line legend-line--price"></i>' + escapeHTML(timeframe) + " OHLC</span>" +
      '<span><i class="legend-line legend-line--ma20"></i>MA20</span><span><i class="legend-line legend-line--ma50"></i>MA50</span>' +
      '<span><i class="legend-dot legend-dot--wave"></i>' + escapeHTML(markerState) + '</span>' +
      '<span><i class="legend-line legend-line--setup"></i>60m trigger / stop / target</span>';
  }

  function renderDrawerChart(chart) {
    window.__signalixLastChart = chart;
    renderChartStatus(chart);
    renderChartLegend(chart);
    if (chart.candles && chart.candles.length > 0) {
      // A real OHLCV series is present — draw it (basic canvas line render).
      dom.drawerChartPH.style.display = "none";
      if (dom.drawerCanvas) {
        dom.drawerCanvas.style.display = "block";
        drawChart(chart);
      }
    } else {
      // No candle series available — keep placeholder honest.
      dom.drawerChartPH.style.display = "block";
      dom.drawerChartPH.textContent = (chart.provenance && chart.provenance.note) || (chart.timeframe === "60M" ? "60m unavailable · Daily EOD remains the decision source" : "No chart data available (candles NOT_VERIFIED)");
      if (dom.drawerCanvas) dom.drawerCanvas.style.display = "none";
    }
  }

  function drawChart(chart) {
    var canvas = dom.drawerCanvas;
    // Clear hit targets before validating optional chart evidence so malformed
    // or absent payloads cannot leave stale markers clickable.
    window.__signalixWaveMarkerHits = [];
    if (!canvas || !chart || !chart.candles || chart.candles.length < 2) return;
    var ctx = canvas.getContext("2d");
    var w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    var candles = chart.candles.slice(-120);
    var start = chart.candles.length - candles.length;
    var left = 34, right = 8, top = 28, priceH = 205, volH = 62, rsiH = 62;
    var plotW = w - left - right;
    var closes = candles.map(function(c) { return Number(c.close); });
    var highs = candles.map(function(c) { return Number(c.high); });
    var lows = candles.map(function(c) { return Number(c.low); });
    var levels = [chart.trigger, chart.stop, chart.target].map(Number).filter(Number.isFinite);
    var allLows = lows.filter(function(v){return Number.isFinite(v);}).concat(levels);
    var allHighs = highs.filter(function(v){return Number.isFinite(v);}).concat(levels);
    var min = Math.min.apply(null, allLows);
    var max = Math.max.apply(null, allHighs);
    var range = (max - min) || 1;
    var xFor = function(i) { return left + (i / Math.max(1, candles.length - 1)) * plotW; };
    var yPrice = function(v) { return top + priceH - ((v - min) / range) * priceH; };
    var colors = { grid: "#2a3345", text: "#8896a6", up: "#26a69a", down: "#ef5350", ma20: "#c9a84c", ma50: "#60a5fa", ma200: "#a78bfa", rsi: "#f472b6" };
    ctx.font = "11px sans-serif";
    ctx.strokeStyle = colors.grid; ctx.lineWidth = 1;
    [top, top + priceH, top + priceH + volH, top + priceH + volH + rsiH].forEach(function(y){ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();});
    ctx.fillStyle = colors.text; ctx.fillText("PRICE", 4, top + 10); ctx.fillText("VOL", 8, top + priceH + 16); ctx.fillText("RSI", 10, top + priceH + volH + 16);
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
    if (chartLayers.ma) { overlay(chart.ma20, colors.ma20); overlay(chart.ma50, colors.ma50); overlay(chart.ma200, colors.ma200); }
    if (chartLayers.volume) {
      var vols=candles.map(function(c){return Number(c.volume)||0;}), vmax=Math.max.apply(null,vols)||1;
      vols.forEach(function(v,i){ctx.fillStyle=Number(candles[i].close)>=Number(candles[i].open)?colors.up:colors.down;var bh=(v/vmax)*volH;ctx.fillRect(xFor(i)-2,top+priceH+volH-bh,4,bh);});
    }
    if (chartLayers.rsi) {
      var rsi=Array.isArray(chart.rsi)?chart.rsi.slice(start,start+candles.length):[];
      ctx.strokeStyle=colors.rsi;ctx.lineWidth=1.5;ctx.beginPath();var rs=false;
      rsi.forEach(function(v,i){if(v==null||!Number.isFinite(Number(v)))return;var x=xFor(i),y=top+priceH+volH+rsiH-(Number(v)/100)*rsiH;if(!rs){ctx.moveTo(x,y);rs=true;}else ctx.lineTo(x,y);});if(rs)ctx.stroke();
      ctx.strokeStyle=colors.grid;ctx.setLineDash([3,3]);[30,70].forEach(function(v){var y=top+priceH+volH+rsiH-(v/100)*rsiH;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();});ctx.setLineDash([]);
    }
    // Decision levels live on the price chart; no duplicate metric boxes below it.
    var decisionLabelYs = [];
    function decisionLine(value, color, label) {
      value = Number(value);
      if (!Number.isFinite(value)) return;
      var y = yPrice(value);
      ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.setLineDash([7, 5]);
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
      decisionLine(chart.trigger, "#f4c95d", "Required close");
      decisionLine(chart.stop, "#ef7777", "Stop");
      decisionLine(chart.target, "#6ee7b7", "Target");
    }
    if (chartLayers.waveEvidence && chart.timeframe === "1D" && chart.wave_evidence && Array.isArray(chart.wave_evidence.markers)) {
      var markerColors = {WAVE_1_LOW: "#a78bfa", WAVE_1_HIGH: "#a78bfa", WAVE_2_PULLBACK_LOW: "#60a5fa",
        WAVE_3_CLOSE_CONFIRMATION: "#26a69a", TESTED_HIGH: "#ffa726", STRUCTURE_BREAK: "#ef5350",
        THESIS_INVALIDATION: "#ef5350", TRIGGER: "#f4c95d", TRADE_STOP: "#ef7777"};
      chart.wave_evidence.markers.forEach(function(marker) {
        if (!marker || typeof marker !== "object" || Array.isArray(marker)) return;
        if (marker.timeframe !== "daily" || marker.timestamp == null || marker.price == null) return;
        var sourceIndex = chart.candles.findIndex(function(c) { return chartTimestampKey(c.date) === chartTimestampKey(marker.timestamp); });
        if (sourceIndex < start || sourceIndex >= start + candles.length || sourceIndex < 0) return;
        var price = Number(marker.price); if (!Number.isFinite(price)) return;
        var localIndex = sourceIndex - start, x = xFor(localIndex), y = yPrice(price);
        ctx.fillStyle = markerColors[marker.kind] || "#c9a84c";
        ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill();
        ctx.fillText(waveEvidenceText(marker.label || marker.kind), Math.max(left, x - 24), Math.max(top + 10, y - 8));
        window.__signalixWaveMarkerHits.push({x: x, y: y, marker: marker});
      });
    }
  }

  function setChartTimeframeButtons(value) {
    $$(".chart-timeframe").forEach(function(btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-timeframe") === value);
      btn.disabled = false;
      btn.removeAttribute("aria-disabled");
      btn.removeAttribute("title");
    });
  }

  function updateDrawerNav() {
    var hasItems = drawerSymbols.length > 0 && drawerIndex >= 0;
    dom.drawerPrev.disabled = !hasItems || drawerIndex <= 0;
    dom.drawerNext.disabled = !hasItems || drawerIndex >= drawerSymbols.length - 1;
    dom.drawerPrev.title = hasItems ? "Previous stock" : "No previous stock";
    dom.drawerNext.title = hasItems ? "Next stock" : "No next stock";
    if (dom.drawerPosition) {
      dom.drawerPosition.textContent = hasItems ? (drawerIndex + 1) + " of " + drawerSymbols.length : "– of –";
      dom.drawerPosition.setAttribute("aria-label", hasItems ? "Stock " + (drawerIndex + 1) + " of " + drawerSymbols.length : "Stock position unavailable");
    }
  }

  function drawerNavigationState(symbols, index) {
    var count = Array.isArray(symbols) ? symbols.length : 0;
    return {index: index, count: count, position: index >= 0 && index < count ? (index + 1) + " of " + count : "– of –",
      previousDisabled: index <= 0 || count === 0, nextDisabled: index < 0 || index >= count - 1 || count === 0};
  }

  function visibleDrawerSymbols() {
    var selector = currentTab === "daily-vcp"
      ? "#panel-daily-vcp [data-symbol].setup-candidate-card, #panel-daily-vcp .vcp-card[data-symbol]"
      : currentTab === "vcp"
        ? "#panel-vcp .vcp-card[data-symbol]"
        : "#panel-explorer .explorer-card[data-symbol]";
    return Array.from(document.querySelectorAll(selector)).map(function(card) {
      return card.getAttribute("data-symbol");
    }).filter(Boolean);
  }

  function localShortlistItem(symbol) {
    if (!shortlistData) return null;
    var lanes = ["ready", "pre_ready", "rising_movers", "caution"];
    for (var i = 0; i < lanes.length; i++) {
      var found = (shortlistData[lanes[i]] || []).find(function(item) { return item.symbol === symbol; });
      if (found) return found;
    }
    return null;
  }

  function drawerItemForSymbol(symbol) {
    var vcp = vcpResultsBySymbol[symbol];
    if (vcp) {
      // Both VCP surfaces feed the same drawer contract, including navigation.
      return Object.assign({symbol: symbol, vcp_result: vcp}, vcp, {
        name: symbol,
        action: vcpPrimaryStatus(vcp),
        description: null
      });
    }
    return localShortlistItem(symbol) || {symbol: symbol, name: symbol, provenance: {}};
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

  function navigateDrawer(delta) {
    var nextIndex = drawerIndex + delta;
    if (nextIndex < 0 || nextIndex >= drawerSymbols.length) return;
    var symbol = drawerSymbols[nextIndex];
    drawerIndex = nextIndex;
    openDrawer(drawerItems[nextIndex] || drawerItemForSymbol(symbol), symbol, drawerSymbols, drawerIndex);
  }

  function openDrawer(item, symbol, navSymbols, navIndex) {
    if (item && item.trend) {
      var trend = item.trend || {}, setup = item.setup || {}, context = item.context || {};
      item = Object.assign({}, item, {name: item.name || symbol, stage: trend.state,
        action: item.decision, sector: context.sector, industry: context.industry,
        trigger: setup.trigger, invalidation: setup.invalidation,
        risk_stop: setup.trade_stop, rr: (setup.rr || {}).to_target_1});
    }
    chartSymbol = symbol;
    if (Array.isArray(navSymbols)) {
      drawerSymbols = navSymbols.slice();
      if (drawerItems.length !== drawerSymbols.length || !drawerItems[navIndex] || drawerItems[navIndex].symbol !== symbol) {
        drawerItems = drawerSymbols.map(drawerItemForSymbol);
      }
    }
    if (navIndex != null) drawerIndex = navIndex;
    else {
      drawerIndex = drawerSymbols.indexOf(symbol);
      if (drawerIndex < 0) drawerIndex = -1;
    }
    updateDrawerNav();
    var requestSeq = ++chartRequestSeq;
    var requestedTimeframe = chartTimeframe;
    var chartKey = symbol + "|" + requestedTimeframe;
    setChartTimeframeButtons(requestedTimeframe);
    if (chartAbort) chartAbort.abort();
    var chartController = new AbortController();
    chartAbort = chartController;
    // Immediate render from local card data (fast path).
    if (item.vcp_result) item._canonicalMetadataPending = true;
    drawerItem = item;
    renderDrawerDetail(drawerItem);

    var cachedChart = chartCache[chartKey];
    if (cachedChart) {
      renderDrawerChart(mergeChartDecisionOverlay(cachedChart, drawerItem));
    } else {
      dom.drawerChartPH.style.display = "block";
      dom.drawerChartPH.textContent = "Chart loading…";
      if (dom.drawerCanvas) dom.drawerCanvas.style.display = "none";
    }

    dom.drawer.classList.remove("drawer--hidden");
    document.body.style.overflow = "hidden";

    // VCP owns intraday decision fields; canonical Daily detail fills metadata.
    fetch("/api/symbol/" + encodeURIComponent(symbol), {signal: chartController.signal})
      .then(function(res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function(fresh) {
        if (requestSeq !== chartRequestSeq || chartSymbol !== symbol) return;
        if (fresh && fresh.symbol) {
          drawerItem = drawerItem.vcp_result ? mergeCanonicalDailyMetadata(item, fresh) : mergeCanonicalSetupDetail(item, fresh);
          renderDrawerDetail(drawerItem);
          var currentChart = chartCache[chartKey];
          if (currentChart && drawerItem.vcp_result) {
            // Daily metadata can arrive after candles. It can provide an
            // optional target, but never supplies VCP trigger/invalidation.
            renderDrawerChart(mergeChartDecisionOverlay(currentChart, drawerItem));
          }
        }
      })
      .catch(function() {
        // Metadata failure is distinct from VCP evidence being NOT_VERIFIED.
        if (requestSeq !== chartRequestSeq || chartSymbol !== symbol) return;
        if (drawerItem && drawerItem.vcp_result) {
          drawerItem._canonicalMetadataPending = false;
          renderDrawerDetail(drawerItem);
        }
      });

    if (!cachedChart) {
      // Fetch DB-backed candles first; snapshot overlay is fallback only.
      fetch("/api/chart-db/" + encodeURIComponent(symbol) + "?timeframe=" + encodeURIComponent(requestedTimeframe), {signal: chartController.signal})
        .then(function(res) {
          if (!res.ok) throw new Error("DB chart HTTP " + res.status);
          return res.json();
        })
        .catch(function(err) {
          if (err && err.name === "AbortError") throw err;
          if (!shouldUseSnapshotChartFallback(item)) throw err;
          return fetch("/api/chart/" + encodeURIComponent(symbol) + "?timeframe=" + encodeURIComponent(requestedTimeframe), {signal: chartController.signal}).then(function(res) {
            if (!res.ok) throw new Error("snapshot chart HTTP " + res.status);
            return res.json();
          });
        })
        .then(function(chart) {
          if (requestSeq !== chartRequestSeq || chartSymbol !== symbol || chartTimeframe !== requestedTimeframe) return;
          if (chart && chart.symbol) {
            mergeChartDecisionOverlay(chart, item);
            if (!Array.isArray(chart.candles) || chart.candles.length < 2) {
              chart.candles = [];
              chart.provenance = chart.provenance || {};
              chart.provenance.note = chart.provenance.note || (requestedTimeframe === "60M" ? "60m unavailable · Daily EOD remains the decision source." : "Chart candles NOT_VERIFIED.");
            }
            chartCache[chartKey] = chart;
            renderDrawerChart(chart);
          }
        })
        .catch(function(err) {
          if (err && err.name === "AbortError") return;
          if (requestSeq !== chartRequestSeq || chartSymbol !== symbol) return;
          dom.drawerChartPH.style.display = "block";
          dom.drawerChartPH.textContent = requestedTimeframe === "60M" ? "60m unavailable · Daily EOD remains the decision source" : "Chart data unavailable";
          if (dom.drawerCanvas) dom.drawerCanvas.style.display = "none";
        });
    }
  }

  function closeDrawer() {
    chartRequestSeq += 1;
    if (chartAbort) chartAbort.abort();
    chartAbort = null;
    drawerItem = null;
    dom.drawer.classList.add("drawer--hidden");
    document.body.style.overflow = "";
  }

  function isRising(item) {
    var transition = item.stage_transition || item.stageTransition || item.previous_stage || item.previousStage;
    if (transition && /S1.*S2|promotion|uptrend/i.test(String(transition))) return true;
    var prox = item.setup_proximity || {};
    return item.stage === "S2_uptrend" && (
      item.phase === "breakout_new" || item.action_queue === "fresh_breakout" ||
      (item.phase === "uptrend_pullback" && ["action", "near_trigger"].indexOf(prox.state) >= 0)
    );
  }

  /* ── card click delegation ── */
  document.addEventListener("click", function(e) {
    var card = e.target.closest(".decision-card, .explorer-card, .vcp-card");
    if (!card) return;
    var symbol = card.getAttribute("data-symbol");
    if (!symbol) return;

    var item = null;
    if (card.classList.contains("vcp-card")) {
      item = drawerItemForSymbol(symbol);
    }
    if (!item && card.classList.contains("setup-candidate-card")) item = vcpResultsBySymbol[symbol];

    // Find local item for immediate fast-path render; authoritative detail is fetched below.
    if (!card.classList.contains("vcp-card") && shortlistData) {
      var all = (shortlistData.ready || []).concat(shortlistData.pre_ready || []);
      for (var i = 0; i < all.length; i++) {
        if (all[i].symbol === symbol) { item = all[i]; break; }
      }
    }
    if (!item) {
      // Explorer card has no full detail — build a symbol-only stub;
      // authoritative detail will come from /api/symbol/.
      item = {
        symbol: symbol,
        name: symbol,
        stage: null,
        phase: null,
        action: null,
        sector: null,
        industry: null,
        market_cap: null,
        trade_value: null,
        description: null,
        close: null,
        change_pct: null,
        change_amount: null,
        target: null,
        rr: null,
        index_membership: [],
        margin_pct: null,
        high52: null,
        low52: null,
        ath_high: null,
        ath_low: null,
        provenance: {}
      };
    }
    var navSymbols = visibleDrawerSymbols();
    var navIndex = navSymbols.indexOf(symbol);
    openDrawer(item, symbol, navSymbols, navIndex);
  });

  /* ── close drawer ── */
  if (dom.drawerClose) dom.drawerClose.addEventListener("click", closeDrawer);
  if (dom.drawerOverlay) dom.drawerOverlay.addEventListener("click", closeDrawer);
  if (dom.drawerPrev) dom.drawerPrev.addEventListener("click", function() { navigateDrawer(-1); });
  if (dom.drawerNext) dom.drawerNext.addEventListener("click", function() { navigateDrawer(1); });
  if (dom.drawerMethodLink) dom.drawerMethodLink.addEventListener("click", function() {
    if (dom.methodGuide) dom.methodGuide.open = true;
    if (dom.methodGuide) dom.methodGuide.scrollIntoView({behavior:"smooth", block:"start"});
  });
  if (dom.drawer) dom.drawer.addEventListener("touchstart", function(e) {
    if (e.touches && e.touches.length === 1) drawerTouchStartX = e.touches[0].clientX;
  }, {passive: true});
  if (dom.drawer) dom.drawer.addEventListener("touchend", function(e) {
    if (drawerTouchStartX == null || !e.changedTouches || !e.changedTouches.length) return;
    var delta = e.changedTouches[0].clientX - drawerTouchStartX;
    drawerTouchStartX = null;
    if (Math.abs(delta) < 50) return;
    navigateDrawer(delta > 0 ? -1 : 1);
  }, {passive: true});
  if (dom.chartWaveEvidence) dom.chartWaveEvidence.addEventListener("change", function() {
    chartLayers.waveEvidence = dom.chartWaveEvidence.checked;
    if (window.__signalixLastChart) drawChart(window.__signalixLastChart);
    if (!chartLayers.waveEvidence) {
      if (dom.chartWaveExplanation) {
        dom.chartWaveExplanation.hidden = false;
        dom.chartWaveExplanation.innerHTML = "<strong>Wave Evidence hidden</strong><div>Markers and evidence overlays are turned off.</div>";
      }
    } else if (chartSymbol) {
      showWaveExplanation(waveEvidenceForItem(drawerItemForSymbol(chartSymbol)));
    }
  });
  if (dom.drawerCanvas) dom.drawerCanvas.addEventListener("click", function(e) {
    if (!chartLayers.waveEvidence || !window.__signalixWaveMarkerHits) return;
    var rect = dom.drawerCanvas.getBoundingClientRect();
    var scaleX = dom.drawerCanvas.width / rect.width, scaleY = dom.drawerCanvas.height / rect.height;
    var x = (e.clientX - rect.left) * scaleX, y = (e.clientY - rect.top) * scaleY;
    var hit = window.__signalixWaveMarkerHits.find(function(candidate) {
      return Math.hypot(candidate.x - x, candidate.y - y) <= 12;
    });
    showWaveExplanation(hit && hit.marker);
  });
  document.addEventListener("keydown", function(e) {
    if (!dom.drawer) return;
    if (e.key === "ArrowLeft" && !dom.drawer.classList.contains("drawer--hidden")) navigateDrawer(-1);
    if (e.key === "ArrowRight" && !dom.drawer.classList.contains("drawer--hidden")) navigateDrawer(1);
    if (e.key === "Escape" && !dom.drawer.classList.contains("drawer--hidden")) closeDrawer();
  });

  function vcpStateLabel(state) {
    return ({READY: "SETUP READY · WAIT FOR BREAKOUT", NEAR_TRIGGER: "NEAR TRIGGER · VOLUME CHECK", BREAKOUT_WATCH: "BREAKOUT WATCH · INTRABAR", CONFIRMED: "TRIGGER CONFIRMED", EXTENDED: "DO NOT CHASE", FORMING: "FORMING", FAILED: "FAILED", STALE: "STALE 60m DATA", NOT_VERIFIED: "NOT VERIFIED"})[state] || state || "NOT VERIFIED";
  }

  function vcpQualityFlags(result) {
    var flags = [];
    var volume = result.volume || {};
    var trend = result.trend || {};
    if (volume.volume_dryup === false) flags.push("NO VOLUME DRY-UP");
    if (trend.daily_context_pass === false) flags.push("DAILY CONTEXT FAIL");
    return flags;
  }

  function vcpDecisionLabel(result) {
    if (result && result.state === "CONFIRMED" && vcpQualityFlags(result).length) {
      return "TRIGGER CONFIRMED · QUALITY INCOMPLETE";
    }
    return vcpStateLabel(result && result.state);
  }

  function vcpPrimaryStatus(result) {
    if (!decisionShadowV2(result).policy_version && !(result && result.decision_lane)) {
      return canonicalDecisionState(result) + " · " + canonicalDecisionValue(result);
    }
    return decisionLane(result) + " · " + actionability(result);
  }

  function vcpPrimaryEvidence(result) {
    if (!decisionShadowV2(result).policy_version && !(result && result.decision_lane)) {
      var legacyEvidence = canonicalDecision(result).evidence || {};
      var legacyTrigger = legacyEvidence.trigger == null ? "—" : Number(legacyEvidence.trigger).toFixed(2);
      var legacyInvalidation = legacyEvidence.invalidation == null ? "—" : Number(legacyEvidence.invalidation).toFixed(2);
      return "Quality " + canonicalQuality(result) + " · Data " + canonicalDataSufficiency(result) + " · Trigger " + legacyTrigger + " · Invalidation " + legacyInvalidation;
    }
    var shadow = decisionShadowV2(result);
    var quality = shadow.quality || {};
    var entry = shadow.entry || {};
    var trigger = entry.pivot == null ? "—" : Number(entry.pivot).toFixed(2);
    var invalidation = entry.invalidation == null ? "—" : Number(entry.invalidation).toFixed(2);
    var passCount = quality.structural_pass_count == null ? "—" : quality.structural_pass_count + "/" + (quality.structural_required_count || 4);
    return "V2 " + decisionLane(result) + " · " + actionability(result) + " · Structure " + passCount + " · Trigger " + trigger + " · Invalidation " + invalidation;
  }

  function vcpCard(result) {
    var price = result.price || {}, pattern = result.pattern || {}, volume = result.volume || {}, data = result.data || {};
    var symbol = result.symbol || "–";
    var state = canonicalDecisionState(result);
    var cls = state.toLowerCase().replace(/_/g, "-");
    var reason = (result.reasons || result.reason_codes || []).join(" · ");
    var feed = data.feed_status === "unavailable" ? "Feed unavailable · " + (data.feed_reason || "retry pending") : "60m feed " + (data.feed_status || "NOT_VERIFIED");
    var typeInfo = result.vcp_type || {};
    var typeTags = [];
    var baseType = vcpTypeLabel(result);
    if (baseType) typeTags.push(baseType);
    var hasNear52wHigh = false;
    (typeInfo.overlays || []).forEach(function(type){
      if (type === "near_52w_high") { hasNear52wHigh = true; return; }
      typeTags.push(type === "break_ath" ? "BREAK ATH" : type === "new_stock" ? "NEW" : type);
    });
    if (hasNear52wHigh || price.distance_to_52w_high_pct != null) {
      var high52Distance = price.distance_to_52w_high_pct == null ? null : Number(price.distance_to_52w_high_pct);
      var high52Label = hasNear52wHigh || (Number.isFinite(high52Distance) && high52Distance >= -5 && high52Distance <= 0) ? "NEAR 52W HIGH" : "52W HIGH";
      typeTags.push(high52Label + (high52Distance == null ? "" : " · " + high52Distance.toFixed(2) + "%"));
    }
    var tags = typeTags;
    if (state === "CONFIRMED") tags = tags.concat(vcpQualityFlags(result));
    if (Array.isArray(result.index_membership)) tags = tags.concat(result.index_membership);
    if (result.margin_rate_pct != null) tags.push(Number(result.margin_rate_pct).toFixed(0) + "%");
    var avgTrade = Number((data.daily_metrics || {}).avg_trade_value_20);
    if (result.reviewable && Number.isFinite(avgTrade) && avgTrade <= 10000000) tags.push("Liquidity < THB 10M");
    var tagHTML = tags.length ? '<div class="vcp-card__tags">' + tags.map(function(tag){ return '<span class="tag">' + escapeHTML(tag) + '</span>'; }).join("") + '</div>' : '';
    var primaryStatus = vcpPrimaryStatus(result);
    var primaryEvidence = vcpPrimaryEvidence(result);
    return '<tr class="vcp-row vcp-card vcp-card--' + escapeHTML(cls) + '" data-symbol="' + escapeHTML(result.symbol || "") + '">' +
      '<td class="vcp-row__symbol"><div class="vcp-row__symbol-content"><span class="vcp-card__primary"><strong>' + escapeHTML(symbol) + '</strong><span class="vcp-card__decision">' + escapeHTML(primaryStatus) + '</span><span class="vcp-card__evidence">' + escapeHTML(primaryEvidence) + '</span><button type="button" class="vcp-row__details" aria-label="View details for ' + escapeHTML(symbol) + '">Details</button></span>' + tagHTML + '</div></td>' +
      '<td>' + (price.last_close == null || price.last_close === "" ? "—" : displayValue(price.last_close)) + '</td>' +
      '<td class="vcp-row__change">' + (price.change_pct == null ? "—" : Number(price.change_pct).toFixed(2) + "%") + '</td>' +
      '<td>' + (price.distance_to_pivot_pct == null ? "—" : Number(price.distance_to_pivot_pct).toFixed(2) + "%") + '</td>' +
      '<td class="vcp-row__rr">' + (vcpRiskReward(result) == null ? "—" : vcpRiskReward(result).toFixed(2) + "R") + '</td>' +
    '</tr>';
  }

  function vcpDisplayGroup(result) {
    if (!decisionShadowV2(result).policy_version && !(result && result.decision_lane)) {
      var legacyPair = canonicalDecisionState(result) + " · " + canonicalDecisionValue(result);
      var legacyAllowed = ["FORMING · WAIT", "READY · WAIT", "CONFIRMED · REVIEW", "EXTENDED · WAIT", "INVALIDATED · AVOID"];
      return legacyAllowed.indexOf(legacyPair) >= 0 ? legacyPair : "UNKNOWN";
    }
    var pair = decisionLane(result) + " · " + actionability(result);
    var allowed = [
      "REVIEW_NOW · ACTIONABLE_REVIEW",
      "STRUCTURE_WATCH · WATCH_ONLY",
      "PREPARE · WATCH_ONLY",
      "EVENT_WATCH · WATCH_ONLY",
      "RESEARCH · NO_ACTION",
      "DO_NOT_CHASE · NO_ACTION",
      "DATA_BLOCKED · NO_ACTION"
    ];
    return allowed.indexOf(pair) >= 0 ? pair : "UNKNOWN";
  }

  function vcpEmptyState(target) {
    var type = target === dom.vcpCards ? dom.vcpType.value : dom.dailyVcpType.value;
    var focused = target === dom.vcpCards && dom.vcpState.value === "actionable";
    if (type === "low_cheat_vcp" && focused) {
      return '<div class="state"><div class="state-icon">⌛</div><p class="state-text">No Low-Cheat setups in focused review.</p><p class="state-hint">Low-Cheat patterns may exist outside focused review. Switch to All states.</p></div>';
    }
    return '<div class="state"><div class="state-icon">⌛</div><p class="state-text">No candidates in the marginable-long universe for this filter.</p><p class="state-hint">The universe loaded successfully; zero candidates matched the current presentation filters.</p></div>';
  }

  function renderVcpResults(results, target) {
    target = target || dom.vcpCards;
    var order = ["REVIEW_NOW · ACTIONABLE_REVIEW", "STRUCTURE_WATCH · WATCH_ONLY", "PREPARE · WATCH_ONLY", "EVENT_WATCH · WATCH_ONLY", "RESEARCH · NO_ACTION", "DO_NOT_CHASE · NO_ACTION", "DATA_BLOCKED · NO_ACTION", "FORMING · WAIT", "READY · WAIT", "CONFIRMED · REVIEW", "EXTENDED · WAIT", "INVALIDATED · AVOID", "UNKNOWN"];
    var groups = {};
    results.forEach(function(result) { var key = vcpDisplayGroup(result); (groups[key] || (groups[key] = [])).push(result); });
    target.innerHTML = order.filter(function(key){ return groups[key] && groups[key].length; }).map(function(key) {
      return '<section class="vcp-lane"><h2 class="section-head">' + escapeHTML(key) + ' <span class="section-subhead">' + groups[key].length + '</span></h2><div class="vcp-table-wrap"><table class="vcp-table"><thead><tr><th>Symbol</th><th>Price</th><th>%</th><th>Distance</th><th class="vcp-row__rr">R/R</th></tr></thead><tbody>' + groups[key].map(vcpCard).join("") + '</tbody></table></div></section>';
    }).join("") || vcpEmptyState(target);
  }

  function renderDailyVcpWatchlist(lanes, target) {
    target = target || dom.dailyVcpCards;
    var order = ["action_review", "near_trigger", "breakout_watch", "structure_watch", "event_watch"];
    var capKeys = {
      action_review: "ACTION_REVIEW",
      near_trigger: "NEAR_TRIGGER",
      breakout_watch: "BREAKOUT_WATCH",
      structure_watch: "STRUCTURE_WATCH",
      event_watch: "EVENT_WATCH"
    };
    var caps = (lanes && lanes.caps) || {};
    var groups = {};
    var groupCaps = {};
    var groupHasCaps = {};
    var html = "";
    order.forEach(function(key) {
      var items = (lanes && lanes[key]) || [];
      if (!items.length) return;
      var cap = caps[capKeys[key]];
      items.forEach(function(item) {
        var status = vcpDisplayGroup(item);
        (groups[status] || (groups[status] = [])).push(item);
        if (cap != null) {
          groupCaps[status] = (groupCaps[status] || 0) + Number(cap);
          groupHasCaps[status] = true;
        }
      });
    });
    ["REVIEW_NOW · ACTIONABLE_REVIEW", "STRUCTURE_WATCH · WATCH_ONLY", "PREPARE · WATCH_ONLY", "EVENT_WATCH · WATCH_ONLY", "RESEARCH · NO_ACTION", "DO_NOT_CHASE · NO_ACTION", "DATA_BLOCKED · NO_ACTION", "FORMING · WAIT", "READY · WAIT", "CONFIRMED · REVIEW", "EXTENDED · WAIT", "INVALIDATED · AVOID", "UNKNOWN"].forEach(function(status) {
      if (!groups[status]) return;
      var subhead = groupHasCaps[status] ? String(groups[status].length) + " / " + String(groupCaps[status]) : String(groups[status].length);
      html += '<section class="vcp-lane"><h2 class="section-head">' + escapeHTML(status) + ' <span class="section-subhead">' + escapeHTML(subhead) + '</span></h2><div class="vcp-table-wrap"><table class="vcp-table"><thead><tr><th>Symbol</th><th>Price</th><th>%</th><th>Distance</th><th class="vcp-row__rr">R/R</th></tr></thead><tbody>' + groups[status].map(vcpCard).join("") + '</tbody></table></div></section>';
    });
    target.innerHTML = html || vcpEmptyState(target);
  }

  function setupCandidateCard(item) {
    var setup = item.setup || {};
    var rr = setup.rr || {};
    var decision = item.decision_lane || "DATA_BLOCKED";
    var status = setup.status || "NOT_VERIFIED";
    var triggerReady = setup.trigger != null && setup.trigger !== "";
    var readiness = setupReadinessLabel(item, setup) + (triggerReady ? " · trigger ready" : "");
    var target1 = setup.target_1;
    if (target1 == null) {
      var targets = Array.isArray(setup.targets) ? setup.targets : [];
      var firstTarget = targets.find(function(target) { return target && target.name === "target_1"; });
      target1 = firstTarget && firstTarget.price;
    }
    var valueOrUnavailable = function(value) { return value == null || value === "" ? "Not ready" : value; };
    var confidence = compactWaveConfidence(item).toLowerCase().replace("_", "-");
    var dataStatus = item.data_status || {};
    var incomplete = decision === "DATA_BLOCKED" || [dataStatus.daily_freshness, dataStatus.intraday_60m_freshness].some(function(value) {
      return ["stale", "unknown", "unavailable", "not_verified"].indexOf(String(value || "").toLowerCase()) >= 0;
    });
    var direction = incomplete ? "neutral" : Number(item.change_pct) > 0 ? "bullish" : Number(item.change_pct) < 0 ? "bearish" : "neutral";
    var directionCue = direction === "bullish" ? "↑ Bullish" : direction === "bearish" ? "↓ Bearish" : "→ Neutral";
    return '<article class="decision-card setup-candidate-card setup-candidate-card--' + direction + '" data-symbol="' + escapeHTML(item.symbol || "") + '" tabindex="0">' +
      '<div class="setup-candidate__header"><div><strong class="setup-candidate__symbol">' + escapeHTML(item.symbol || "–") + '</strong><span class="setup-candidate__name">' + escapeHTML(item.name || "") + '</span></div><span class="setup-candidate__direction setup-candidate__direction--' + direction + '" aria-label="' + directionCue + '">' + directionCue + '</span></div>' +
      '<div class="setup-candidate__wave"><span>Daily context <b>' + escapeHTML(canonicalWaveState(item)) + '</b></span><span class="setup-candidate__confidence setup-candidate__confidence--' + confidence + '"><i aria-hidden="true"></i> Confidence <b>' + escapeHTML(compactWaveConfidence(item)) + '</b></span></div>' +
      '<div class="setup-candidate__plan"><span>Current <b>' + escapeHTML(valueOrUnavailable(item.close)) + '</b></span><span>Entry <b>' + escapeHTML(valueOrUnavailable(setup.trigger)) + '</b></span><span>Invalidation / Stop <b>' + escapeHTML(valueOrUnavailable(setup.invalidation || setup.trade_stop)) + '</b></span><span>R:R <b>' + escapeHTML(valueOrUnavailable(rr.to_target_1)) + '</b></span><span>Target 1 <b>' + escapeHTML(valueOrUnavailable(target1)) + '</b></span></div>' +
      '<p class="setup-candidate__readiness"><span class="setup-candidate__decision">' + escapeHTML(decision) + '</span><b>Trigger readiness · ' + escapeHTML(readiness) + '</b></p></article>';
  }

  function setupCandidateMatchesToolbar(item) {
    var search = dom.dailySetupSearch ? dom.dailySetupSearch.value.trim().toLowerCase() : "";
    var lane = dom.dailySetupLane ? dom.dailySetupLane.value : "ALL";
    var wave = dom.dailySetupWave ? dom.dailySetupWave.value : "ALL";
    var haystack = ((item.symbol || "") + " " + (item.name || "")).toLowerCase();
    return (!search || haystack.indexOf(search) >= 0) && (lane === "ALL" || item.decision_lane === lane) &&
      (wave === "ALL" || setupCandidateWaveBucket(item) === wave);
  }

  function stableSetupCandidateOrder(items) {
    return (items || []).map(function(item, index) { return {item: item, index: index}; }).sort(function(a, b) {
      var left = String(a.item.symbol || "").toUpperCase();
      var right = String(b.item.symbol || "").toUpperCase();
      return left < right ? -1 : left > right ? 1 : a.index - b.index;
    }).map(function(entry) { return entry.item; });
  }

  function groupSetupCandidates(items) {
    var laneOrder = ["REVIEW_NOW", "SETUP_FORMING", "DAILY_CANDIDATE", "WAIT", "AVOID", "DATA_BLOCKED"];
    var groups = {};
    var reviewOrder = ["PRE_TRIGGER", "TESTED_TRIGGER", "TRIGGERED"];
    laneOrder.forEach(function(lane) { groups[lane] = []; });
    stableSetupCandidateOrder(items).forEach(function(item) {
      var lane = laneOrder.indexOf(item.decision_lane) >= 0 ? item.decision_lane : "DATA_BLOCKED";
      groups[lane].push(item);
    });
    if (groups.REVIEW_NOW.length) {
      var reviewGroups = {};
      reviewOrder.forEach(function(status) { reviewGroups[status] = []; });
      var reviewUnknown = [];
      groups.REVIEW_NOW.forEach(function(item) {
        var status = (item.setup || {}).status;
        if (reviewGroups[status]) reviewGroups[status].push(item);
        else reviewUnknown.push(item);
      });
      groups.REVIEW_NOW = reviewOrder.reduce(function(result, status) {
        return result.concat(reviewGroups[status]);
      }, []).concat(reviewUnknown);
    }
    var waveOrder = canonicalDailyWaveStates.concat(["UNKNOWN"]);
    var waveGroups = {};
    waveOrder.forEach(function(state) { waveGroups[state] = []; });
    groups.DAILY_CANDIDATE.forEach(function(item) { waveGroups[setupCandidateWaveBucket(item)].push(item); });
    return {order: laneOrder, groups: groups, waveOrder: waveOrder, waveGroups: waveGroups};
  }

  function reconcileDailyDrawerNavigation() {
    if (!dom.drawer || dom.drawer.classList.contains("drawer--hidden")) return;
    var symbols = visibleDrawerSymbols();
    var index = chartSymbol ? symbols.indexOf(chartSymbol) : -1;
    if (index < 0) {
      closeDrawer();
      return;
    }
    drawerSymbols = symbols;
    drawerIndex = index;
    updateDrawerNav();
  }

  function setupDrawerCollection(items) {
    var grouped = groupSetupCandidates(items || []);
    return grouped.order.reduce(function(result, lane) {
      return result.concat(grouped.groups[lane]);
    }, []).filter(function(item, index, all) {
      return item && item.symbol && all.findIndex(function(candidate) { return candidate.symbol === item.symbol; }) === index;
    });
  }

  function validateSetupCandidatePayload(data) {
    if (!data || !Array.isArray(data.items) || !data.counts ||
        typeof data.counts !== "object" || Array.isArray(data.counts)) return false;
    var items = data.items;
    var laneTotals = data.counts;
    var laneItemCounts = {};
    var laneOrder = ["REVIEW_NOW", "SETUP_FORMING", "DAILY_CANDIDATE", "WAIT", "AVOID", "DATA_BLOCKED"];
    var laneTotalCount = 0;
    for (var lane in laneTotals) {
      if (!Object.prototype.hasOwnProperty.call(laneTotals, lane)) continue;
      var count = laneTotals[lane];
      if (!Number.isInteger(count) || count < 0) return false;
      laneTotalCount += count;
    }
    items.forEach(function(item) {
      if (!item || typeof item !== "object" || Array.isArray(item)) return;
      var lane = laneOrder.indexOf(item.decision_lane) >= 0 ? item.decision_lane : "DATA_BLOCKED";
      laneItemCounts[lane] = (laneItemCounts[lane] || 0) + 1;
    });
    if (items.some(function(item) { return !item || typeof item !== "object" || Array.isArray(item); })) return false;
    for (var itemLane in laneItemCounts) {
      if (!Object.prototype.hasOwnProperty.call(laneTotals, itemLane) || laneItemCounts[itemLane] > laneTotals[itemLane]) return false;
    }
    return laneTotalCount === Number(data.evaluated_count);
  }

  function renderSetupCandidates(data) {
    data = data || {};
    dailySetupData = data;
    hide(dom.dailyVcpLoading); show(dom.dailyVcpContent);
    var items = data && Array.isArray(data.items) ? data.items : [];
    var returnedCount = Number(data.returned_count);
    var evaluatedCount = Number(data.evaluated_count);
    var totalItems = Number(data.total_items);
    var page = Number(data.page);
    var pageSize = Number(data.page_size);
    var totalPages = Number(data.total_pages || 0);
    var laneTotals = data && data.counts || {};
    var laneTotalCount = Object.keys(laneTotals).reduce(function(total, lane) { return total + Number(laneTotals[lane] || 0); }, 0);
    var paginationValid = Number.isInteger(returnedCount) && returnedCount === items.length &&
      Number.isInteger(evaluatedCount) && evaluatedCount >= returnedCount &&
      Number.isInteger(totalItems) && totalItems >= returnedCount && totalItems <= evaluatedCount &&
      Number.isInteger(page) && page >= 1 && Number.isInteger(pageSize) && pageSize >= 1 &&
      Number.isInteger(totalPages) && totalPages === (totalItems ? Math.ceil(totalItems / pageSize) : 0) &&
      page <= Math.max(1, totalPages) && laneTotalCount === evaluatedCount &&
      validateSetupCandidatePayload(data);
    if (!paginationValid) {
      dom.dailyVcpMeta.textContent = "Canonical setup-candidate response inconsistent · DATA_BLOCKED";
      dom.dailySetupPageInfo && (dom.dailySetupPageInfo.textContent = "Page unavailable");
      dom.dailyVcpCards.innerHTML = '<div class="state"><div class="state-icon">⚠️</div><p class="state-text">Setup candidate data is inconsistent.</p><p class="state-hint">Refresh before reviewing evidence.</p></div>';
      return;
    }
    items = items.filter(setupCandidateMatchesToolbar);
    drawerItems = setupDrawerCollection(items);
    drawerSymbols = drawerItems.map(function(item) { return item.symbol; });
    vcpResultsBySymbol = {};
    items.forEach(function(item) { vcpResultsBySymbol[item.symbol] = item; });
    var freshness = data.freshness || {};
    var intradayFetchedAt = freshness.intraday_fetched_at || null;
    var intradayLatestBarAt = items.reduce(function(latest, item) {
      var status = item && item.data_status || {}, provenance = item && item.provenance || {};
      var candidate = status.intraday_60m_as_of || provenance.intraday_as_of;
      return candidate && (!latest || String(candidate) > String(latest)) ? candidate : latest;
    }, null);
    var dailyStatuses = items.map(function(item) { return (item.data_status || {}).daily_freshness; }).filter(Boolean);
    var intradayStatuses = items.map(function(item) { return (item.data_status || {}).intraday_60m_freshness; }).filter(Boolean);
    var dailyStatus = freshness.daily_status || (dailyStatuses.indexOf("stale") >= 0 ? "stale" : dailyStatuses.length && dailyStatuses.every(function(value) { return value === "fresh"; }) ? "fresh" : null);
    var intradayStatus = freshness.intraday_status || (intradayStatuses.indexOf("stale") >= 0 ? "stale" : intradayStatuses.length && intradayStatuses.every(function(value) { return value === "fresh"; }) ? "fresh" : null);
    setFreshness(freshness.status || "unknown", freshness.data_fetched_at || data.as_of, intradayFetchedAt, dailyStatus, intradayStatus);
    var universeLabel = data.universe_filter === "marginable_long" ? "Marginable long" : (data.universe_filter || "Signalix");
    var provenanceSource = freshness.source || (items[0] && items[0].provenance && items[0].provenance.source) || "price_data+intraday_price_data";
    dom.dailyVcpMeta.textContent = universeLabel + " · Daily EOD " + formatProvenance(freshness.data_fetched_at || data.as_of) + " · 60m fetched " + (intradayFetchedAt ? formatProvenance(intradayFetchedAt) : "Unavailable") + " · latest completed 60m candle " + (intradayLatestBarAt ? formatProvenance(intradayLatestBarAt) : "Unavailable") + " · source " + provenanceSource + " · " + (data.returned_count || 0) + " shown / " + (data.evaluated_count || 0) + " evaluated · " + (data.policy_version || "setup-candidates-v1");
    dailySetupPage = data.page || 1;
    dailySetupTotalPages = totalPages;
    dom.dailySetupPageInfo.textContent = dailySetupTotalPages ? "Page " + dailySetupPage + " of " + dailySetupTotalPages : "Page 0 of 0";
    dom.dailySetupPrev.disabled = dailySetupPage <= 1;
    dom.dailySetupNext.disabled = !dailySetupTotalPages || dailySetupPage >= dailySetupTotalPages;
    var grouped = groupSetupCandidates(items);
    var groupedHTML = grouped.order.reduce(function(html, lane) {
      var laneItems = grouped.groups[lane];
      if (!laneItems.length) return html;
      var content = lane === "DAILY_CANDIDATE" ? grouped.waveOrder.reduce(function(waveHTML, wave) {
        var waveItems = grouped.waveGroups[wave];
        if (!waveItems.length) return waveHTML;
        var label = wave === "UNKNOWN" ? "Unknown / Not verified" : wave;
        return waveHTML + '<section class="setup-candidate-wave-group"><h3 class="section-head">' + escapeHTML(label) + ' <span class="section-subhead">' + waveItems.length + '</span></h3>' + waveItems.map(setupCandidateCard).join("") + '</section>';
      }, "") : laneItems.map(setupCandidateCard).join("");
      return html + '<section class="setup-candidate-lane"><h2 class="section-head">' + escapeHTML(lane) + ' <span class="section-subhead">' + laneItems.length + ' / ' + Number(laneTotals[lane] || 0) + '</span></h2>' + content + '</section>';
    }, "");
    dom.dailyVcpCards.innerHTML = groupedHTML ||
      '<div class="state"><div class="state-icon">⌛</div><p class="state-text">No setup candidates matched the current presentation filters.</p><p class="state-hint">The universe loaded successfully; this is an empty result, not an API failure.</p></div>';
    if (dom.dailySetupUpdated) dom.dailySetupUpdated.textContent = "Updated " + formatProvenance(freshness.fetch_completed_at || data.fetch_completed_at || data.as_of || "unknown");
    reconcileDailyDrawerNavigation();
  }

  function loadDailyVcp(force, page) {
    // Legacy DOM/function names remain for compatibility; primary requests use
    // the canonical setup-candidates contract.
    if (page != null) dailySetupPage = Math.max(1, Number(page) || 1);
    var requestOptions = {};
    if (dom.dailySetupSector && dom.dailySetupSector.value.trim()) requestOptions.sector = dom.dailySetupSector.value.trim();
    var endpoint = SignalixCanonicalClient.setupCandidatesRequestKey(dailySetupPage, 50, requestOptions);
    var request = dailyVcpRequests.load(endpoint, function(signal) {
      return SignalixCanonicalClient.fetchSetupCandidatesPage(dailySetupPage, 50, signal, requestOptions);
    }, !!force);
    if (request.cached) {
      var cachedRequestSeq = ++dailyVcpRequestSeq;
      request.promise.then(function(data) { if (cachedRequestSeq === dailyVcpRequestSeq) renderSetupCandidates(data); });
      return;
    }
    if (request.pending) return;
    var requestSeq = ++dailyVcpRequestSeq;
    show(dom.dailyVcpLoading); hide(dom.dailyVcpError); hide(dom.dailyVcpContent);
    request.promise.then(function(data){
        if (requestSeq !== dailyVcpRequestSeq) return;
        renderSetupCandidates(data);
      })
      .catch(function(err){
        if (err.name === "AbortError" || requestSeq !== dailyVcpRequestSeq) return;
        dailyVcpRequests.clear(endpoint);
        hide(dom.dailyVcpLoading); hide(dom.dailyVcpContent); show(dom.dailyVcpError);
        setFreshness("error", null, null, "unknown", "unknown");
        dom.dailyVcpErrorMsg.textContent = "Unable to load setup candidates: " + err.message;
      });
  }

  function renderDailyVcpData(data) {
        hide(dom.dailyVcpLoading); show(dom.dailyVcpContent);
        vcpRunMeta = {run_id: data.run_id || "", as_of: data.as_of || "", fetch_completed_at: data.fetch_completed_at || ""};
        setFreshness("fresh", data.as_of, data.fetch_completed_at || data.as_of);
        vcpResultsBySymbol = {};
        var lanes = data.daily_watchlist || {action_review: [], near_trigger: [], breakout_watch: [], structure_watch: [], event_watch: []};
        var filtered = {action_review: [], near_trigger: [], breakout_watch: [], structure_watch: [], event_watch: []};
        var insufficientCount = 0;
        ["action_review", "near_trigger", "breakout_watch", "structure_watch", "event_watch"].forEach(function(key) {
          (lanes[key] || []).forEach(function(r){
            var metrics = (r.data || {}).daily_metrics || {};
            if (canonicalDataSufficiency(r) !== "SUFFICIENT") { insufficientCount += 1; return; }
            if (dom.dailyFilterMarginable.checked && !(r.marginable && r.marginable.is_marginable)) return;
            if (dom.dailyFilterTradeValue.checked && !(Number(metrics.avg_trade_value_20) > 10000000)) return;
            if (dom.dailyFilterPrice.checked && !(Number((r.price || {}).last_close) > 0.6)) return;
            if (!vcpTypeMatches(r, dom.dailyVcpType.value)) return;
            if (!canonicalFilterMatches(r, dom.dailyVcpDecisionState, dom.dailyVcpDecision, dom.dailyVcpQuality)) return;
            filtered[key].push(r);
            vcpResultsBySymbol[r.symbol] = r;
          });
        });
        var total = filtered.action_review.length + filtered.near_trigger.length + filtered.breakout_watch.length + filtered.structure_watch.length + filtered.event_watch.length;
        var coverage = (lanes && lanes.coverage) || {};
        var rejectionCounts = coverage.rejection_counts || {};
        var rejectionSummary = Object.keys(rejectionCounts).sort(function(a, b) { return rejectionCounts[b] - rejectionCounts[a]; }).slice(0, 3).map(function(key) { return key + " " + rejectionCounts[key]; }).join(", ");
        dom.dailyVcpMeta.textContent = marginableUniverseMeta(data) + " · Run " + (data.run_id || "NOT_VERIFIED") + " · " + total + " reviewable / " + ((data.universe || {}).evaluated || 0) + " evaluated" + (insufficientCount ? " · " + insufficientCount + " hidden: insufficient/unknown data" : "") + (rejectionSummary ? " · rejected: " + rejectionSummary : "") + (data.coverage && data.coverage.feed_unavailable ? " · " + data.coverage.feed_unavailable + " feed unavailable" : "");
        renderDailyVcpWatchlist(filtered, dom.dailyVcpCards);
  }

  function loadVcp(force) {
    var selected = dom.vcpState.value || "ALL";
    // VCP is an explicitly secondary audit/compatibility/rollback surface.
    var endpoint = "/api/vcp-finder?interval=60m&market=TH&universe=marginable_long";
    if (selected === "actionable") endpoint += "&focused=true";
    else if (selected.indexOf("FORMING_") === 0) endpoint += "&state=FORMING";
    else if (selected !== "ALL") endpoint += "&state=" + encodeURIComponent(selected);
    else endpoint += "&limit=5000";
    var request = vcpRequests.load(endpoint, function(signal) {
      return fetch(endpoint, {signal: signal}).then(function(res) { if (!res.ok) throw new Error("HTTP " + res.status); return res.json(); });
    }, !!force);
    if (request.cached) {
      ++vcpRequestSeq;
      request.promise.then(renderVcpData);
      return;
    }
    if (request.pending) return;
    var requestSeq = ++vcpRequestSeq;
    show(dom.vcpLoading); hide(dom.vcpError); hide(dom.vcpContent);
    request.promise.then(function(data) {
        if (requestSeq !== vcpRequestSeq) return;
        renderVcpData(data);
      })
      .catch(function(err) { if (err.name === "AbortError" || requestSeq !== vcpRequestSeq) return; hide(dom.vcpLoading); show(dom.vcpError); dom.vcpErrorMsg.textContent = "Unable to load VCP Finder: " + err.message; });
  }

  function renderVcpData(data) {
        hide(dom.vcpLoading); show(dom.vcpContent);
        vcpRunMeta = {run_id: data.run_id || "", as_of: data.as_of || "", fetch_completed_at: data.fetch_completed_at || ""};
        setFreshness("fresh", data.as_of, data.fetch_completed_at || data.as_of);
        vcpResultsBySymbol = {};
        (data.results || []).forEach(function(r) { vcpResultsBySymbol[r.symbol] = r; });
        var selected = dom.vcpState.value || "ALL";
        var results = (data.results || []).filter(function(r){ return vcpTypeMatches(r, dom.vcpType.value); });
        if (marginRates.length) results = results.filter(function(r){ return marginRates.indexOf(Number(r.margin_rate_pct)) >= 0; });
        results = results.filter(priceMatches);
        results = results.filter(function(r){ return canonicalFilterMatches(r, dom.vcpDecisionState, dom.vcpDecision, dom.vcpQuality); });
        if (selected === "actionable") results = results.filter(function(r){ return ["READY","NEAR_TRIGGER","CONFIRMED","BREAKOUT_WATCH"].indexOf(r.state) >= 0 || (r.state === "FORMING" && r.forming_group === "maturing"); });
        else if (selected.indexOf("FORMING_") === 0) results = results.filter(function(r){ return r.state === "FORMING" && r.forming_group === selected.slice(8).toLowerCase(); });
        else if (selected !== "ALL") results = results.filter(function(r){ return r.state === selected; });
        dom.vcpMeta.textContent = marginableUniverseMeta(data) + " · Run " + (data.run_id || "NOT_VERIFIED") + " · " + (results.length) + " shown / " + ((data.universe || {}).evaluated || 0) + " evaluated";
        renderVcpResults(results);
  }

  if (dom.dailySetupRefresh) dom.dailySetupRefresh.addEventListener("click", function() { loadDailyVcp(true, 1); });
  [dom.dailyFilterMarginable, dom.dailyFilterTradeValue, dom.dailyFilterPrice,
   dom.dailyVcpDecisionState, dom.dailyVcpDecision, dom.dailyVcpQuality].forEach(function(input) {
    if (input) input.addEventListener("change", function() { loadDailyVcp(false, 1); });
  });
  if (dom.dailySetupSector) dom.dailySetupSector.addEventListener("change", function() { loadDailyVcp(false, 1); });
  if (dom.dailySetupSearch) dom.dailySetupSearch.addEventListener("input", function() {
    if (dailySetupData) renderSetupCandidates(dailySetupData);
  });
  if (dom.dailySetupLane) dom.dailySetupLane.addEventListener("change", function() {
    if (dailySetupData) renderSetupCandidates(dailySetupData);
  });
  if (dom.dailySetupWave) dom.dailySetupWave.addEventListener("change", function() {
    if (dailySetupData) renderSetupCandidates(dailySetupData);
  });
  function scheduleLiveRefresh() {
    if (liveRefreshTimer) clearTimeout(liveRefreshTimer);
    liveRefreshTimer = liveRefreshEnabled ? setTimeout(function() {
      liveRefreshTimer = null;
      if (currentTab === "daily-vcp") loadDailyVcp(true);
      scheduleLiveRefresh();
    }, 60000) : null;
  }
  if (dom.dailySetupLiveRefresh) dom.dailySetupLiveRefresh.addEventListener("change", function() {
    liveRefreshEnabled = dom.dailySetupLiveRefresh.checked;
    scheduleLiveRefresh();
  });
  /* ── tab switching ── */
  function switchTab(tab) {
    currentTab = tab;
    dom.tabDailyVcp.classList.toggle("nav-tab--active", tab === "daily-vcp");
    dom.tabDailyVcp.setAttribute("aria-selected", tab === "daily-vcp");
    if (dom.tabVcp) {
      dom.tabVcp.classList.toggle("nav-tab--active", tab === "vcp");
      dom.tabVcp.setAttribute("aria-selected", tab === "vcp");
    }
    dom.panelDailyVcp.classList.toggle("panel--active", tab === "daily-vcp");
    dom.panelDailyVcp.classList.toggle("panel--hidden", tab !== "daily-vcp");
    if (dom.panelVcp) {
      dom.panelVcp.classList.toggle("panel--active", tab === "vcp");
      dom.panelVcp.classList.toggle("panel--hidden", tab !== "vcp");
    }
    if (tab === "daily-vcp") loadDailyVcp();
    if (tab === "vcp") loadVcp();
  }

  dom.tabDailyVcp.addEventListener("click", function() { switchTab("daily-vcp"); });
  if (dom.tabVcp) dom.tabVcp.addEventListener("click", function() { switchTab("vcp"); });
  if (dom.vcpState) {
    dom.vcpState.addEventListener("change", loadVcp);
    if (dom.vcpType) dom.vcpType.addEventListener("change", loadVcp);
    [dom.vcpDecisionState, dom.vcpDecision, dom.vcpQuality].forEach(function(input) {
      if (input) input.addEventListener("change", loadVcp);
    });
    if (dom.vcpRetry) dom.vcpRetry.addEventListener("click", function() { loadVcp(true); });
  }
  if (dom.dailyVcpRetry) dom.dailyVcpRetry.addEventListener("click", function() { loadDailyVcp(true); });

  function marginRateQuery() {
    return marginRates.length ? "&margin_rates=" + encodeURIComponent(marginRates.join(",")) : "";
  }
  function priceBandQuery() {
    return priceBand.length ? "&price_band=" + encodeURIComponent(priceBand[0]) : "";
  }
  function priceMatches(item) {
    if (!priceBand.length) return true;
    var value = Number(item.close != null ? item.close : ((item.price || {}).last_close));
    if (!Number.isFinite(value)) return false;
    return priceBand.some(function(band) { return band === "below_2" ? value < 2 : band === "2_to_10" ? value >= 2 && value <= 10 : value > 10; });
  }

  /* ── fetch shortlist ── */
  function loadShortlist() {
    setFreshness("loading");
    hideAll(".shortlist-section");
    hide(dom.slError);
    hide(dom.slEmpty);
    hide(dom.slStale);
    show(dom.slLoading);

    fetch("/api/daily-shortlist?marginable=" + encodeURIComponent(marginableFilter) + marginRateQuery() + priceBandQuery())
      .then(function(res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function(data) {
        shortlistData = data;
        if (dom.slMarginableMeta) dom.slMarginableMeta.textContent = marginFilterMeta(data);
        hide(dom.slLoading);

        var freshness = data.freshness || {};
        var fStatus = (freshness.status === "stale") ? "stale"
          : (freshness.status === "market_closed") ? "market_closed"
          : (freshness.status === "fresh" || freshness.status === "latest_available") ? "fresh"
          : "stale";
        setFreshness(fStatus, freshness.data_fetched_at || freshness.as_of, freshness.intraday_fetched_at);

        // stale state
        if (fStatus === "stale") {
          show(dom.slStale);
          dom.slStaleTime.textContent = freshness.as_of || freshness.data_fetched_at || "–";
        } else {
          hide(dom.slStale);
        }

        var ready = data.ready || [];
        var preReady = data.pre_ready || [];
        var rising = data.rising_movers || [];
        var caution = data.caution || [];

        if (ready.length === 0 && preReady.length === 0 && rising.length === 0 && caution.length === 0) {
          show(dom.slEmpty);
          return;
        }
        hide(dom.slEmpty);

        if (rising.length > 0) {
          show(dom.slRising);
          dom.slRisingCards.innerHTML = "";
          rising.forEach(function(item) { dom.slRisingCards.insertAdjacentHTML("beforeend", buildDecisionCard(item)); });
        }
        if (caution.length > 0) {
          show(dom.slCaution);
          dom.slCautionCards.innerHTML = "";
          caution.forEach(function(item) { dom.slCautionCards.insertAdjacentHTML("beforeend", buildDecisionCard(item)); });
        }

        // render READY
        if (ready.length > 0) {
          show($("#shortlist-ready"));
          dom.slReadyCards.innerHTML = "";
          ready.forEach(function(item) {
            dom.slReadyCards.insertAdjacentHTML("beforeend", buildDecisionCard(item));
          });
        } else {
          hide($("#shortlist-ready"));
        }

        // render PRE-READY
        if (preReady.length > 0) {
          show($("#shortlist-pre-ready"));
          dom.slPreCards.innerHTML = "";
          preReady.forEach(function(item) {
            dom.slPreCards.insertAdjacentHTML("beforeend", buildDecisionCard(item));
          });
        } else {
          hide($("#shortlist-pre-ready"));
        }
      })
      .catch(function(err) {
        hide(dom.slLoading);
        show(dom.slError);
        dom.slErrorMsg.textContent = "Unable to load: " + err.message;
        setFreshness("error");
      });
  }

  /* ── fetch explorer ── */
  function loadExplorer(page) {
    page = page || 1;
    explorerPage = page;
    show(dom.exLoading);
    hide(dom.exError);
    hide(dom.exEmpty);
    hide($("#explorer-content"));

    var params = "page=" + page + "&page_size=20";
    params += "&marginable=" + encodeURIComponent(marginableFilter) + marginRateQuery() + priceBandQuery();
    if (explorerStage) params += "&stage=" + encodeURIComponent(explorerStage);
    if (explorerSearch) params += "&search=" + encodeURIComponent(explorerSearch);
    fetch("/api/explorer?" + params)
      .then(function(res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function(data) {
        hide(dom.exLoading);
        show($("#explorer-content"));

        var items = data.items || [];
        if (items.length === 0) {
          show(dom.exEmpty);
          return;
        }
        hide(dom.exEmpty);

        dom.exCards.innerHTML = "";
        items.forEach(function(item) {
          dom.exCards.insertAdjacentHTML("beforeend", buildExplorerCard(item));
        });

        explorerTotalPages = data.total_pages || 1;
        dom.exPageInfo.textContent = "Page " + page + " of " + explorerTotalPages;
        dom.exPrev.disabled = page <= 1;
        dom.exNext.disabled = page >= explorerTotalPages;
      })
      .catch(function(err) {
        hide(dom.exLoading);
        show(dom.exError);
        dom.exErrorMsg.textContent = "Unable to load: " + err.message;
      });
  }

  /* ── pagination controls ── */
  if (dom.exPrev) dom.exPrev.addEventListener("click", function() {
    if (explorerPage > 1) loadExplorer(explorerPage - 1);
  });
  if (dom.exNext) dom.exNext.addEventListener("click", function() {
    if (explorerPage < explorerTotalPages) loadExplorer(explorerPage + 1);
  });
  function updateMarginRates(surface, apply) {
    marginRates = Array.from(document.querySelectorAll('.margin-rate-toggle[data-surface="' + surface + '"]:checked'))
      .map(function(input) { return Number(input.value); }).sort(function(a, b) { return a - b; });
    $$( '.margin-rate-toggle[data-surface="' + surface + '"]' ).forEach(function(input) {
      input.checked = marginRates.indexOf(Number(input.value)) >= 0;
    });
    if (!apply && surface === "vcp") return;
    if (surface === "shortlist") loadShortlist();
    else if (surface === "vcp") loadVcp();
    else loadExplorer(1);
  }
  $$(".margin-rate-toggle").forEach(function(input) {
    input.addEventListener("change", function() {
      updateMarginRates(input.getAttribute("data-surface") || "explorer");
    });
  });
  if (dom.vcpMarginAll) dom.vcpMarginAll.addEventListener("click", function() {
    $$(".margin-rate-toggle[data-surface=\"vcp\"]").forEach(function(input){ input.checked = true; });
    updateMarginRates("vcp", false);
  });
  if (dom.vcpMarginClear) dom.vcpMarginClear.addEventListener("click", function() {
    $$(".margin-rate-toggle[data-surface=\"vcp\"]").forEach(function(input){ input.checked = false; });
    updateMarginRates("vcp", false);
  });
  if (dom.vcpFilterApply) dom.vcpFilterApply.addEventListener("click", function() {
    updateMarginRates("vcp", true);
  });
  function updatePriceBand(value) {
    priceBand = Array.isArray(value) ? value : (value ? [value] : []);
    [dom.slPriceBand, dom.exPriceBand, dom.vcpPriceBand].forEach(function(select) { if (select) Array.from(select.options).forEach(function(option){ option.selected = priceBand.indexOf(option.value) >= 0; }); });
    if (currentTab === "shortlist") loadShortlist();
    else if (currentTab === "explorer") loadExplorer(1);
    else loadVcp();
  }
  [dom.slPriceBand, dom.exPriceBand, dom.vcpPriceBand].forEach(function(select) {
    if (select) select.addEventListener("change", function() { updatePriceBand(Array.from(select.selectedOptions).map(function(option){ return option.value; })); });
  });
  if (dom.slMarginable) dom.slMarginable.addEventListener("change", function() {
    marginableFilter = dom.slMarginable.value || "krungsri";
    if (dom.exMarginable) dom.exMarginable.value = marginableFilter;
    loadShortlist();
  });
  if (dom.exMarginable) dom.exMarginable.addEventListener("change", function() {
    marginableFilter = dom.exMarginable.value || "krungsri";
    if (dom.slMarginable) dom.slMarginable.value = marginableFilter;
    loadExplorer(1);
  });
  if (dom.exStage) dom.exStage.addEventListener("change", function() {
    explorerStage = dom.exStage.value;
    loadExplorer(1);
  });
  var explorerSearchTimer = null;
  if (dom.exSearch) dom.exSearch.addEventListener("input", function() {
    clearTimeout(explorerSearchTimer);
    explorerSearch = dom.exSearch.value.trim();
    explorerSearchTimer = setTimeout(function() { loadExplorer(1); }, 250);
  });
  $$(".chart-timeframe").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var nextTimeframe = btn.getAttribute("data-timeframe") || "1D";
      var currentItem = chartSymbol ? drawerItemForSymbol(chartSymbol) : null;
      chartTimeframe = nextTimeframe;
      if (chartSymbol) {
        openDrawer(currentItem || {symbol: chartSymbol, name: chartSymbol}, chartSymbol, drawerSymbols, drawerIndex);
      }
    });
  });

  /* ── retry buttons ── */
  if (dom.slRetry) dom.slRetry.addEventListener("click", loadShortlist);
  if (dom.slStaleRetry) dom.slStaleRetry.addEventListener("click", loadShortlist);
  if (dom.exRetry) dom.exRetry.addEventListener("click", function() { loadExplorer(explorerPage); });
  dom.dailySetupPrev.addEventListener("click", function() {
    if (dailySetupPage > 1) loadDailyVcp(false, dailySetupPage - 1);
  });
  dom.dailySetupNext.addEventListener("click", function() {
    if (dailySetupPage < dailySetupTotalPages) loadDailyVcp(false, dailySetupPage + 1);
  });

  /* ── init ── */
  setFreshness("loading");
  loadDailyVcp();
})();
