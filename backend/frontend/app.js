/* ═══════════════════════════════════════════════════════════
   Signalix MVP Reset — Vanilla JS
   Owner-only. No auth. No tiers. No watchlist.
   Surfaces: Daily Shortlist + All Stocks Explorer
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
    dailyFilterMarginable: $("#daily-filter-marginable"),
    dailyFilterTradeValue: $("#daily-filter-trade-value"),
    dailyFilterPrice: $("#daily-filter-price"),
    dailyVcpType:   $("#daily-vcp-type"),
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
    drawerSymbol:  $("#drawer-symbol"),
    drawerName:    $("#drawer-name"),
    drawerPrice:   $("#drawer-price"),
    drawerChange:  $("#drawer-change"),
    drawerTrend:    $("#drawer-trend"),
    drawerAction:   $("#drawer-action"),
    drawerSector:   $("#drawer-sector"),
    drawerIndustry: $("#drawer-industry"),
    drawerMarketCap: $("#drawer-market-cap"),
    drawerTradeValue: $("#drawer-trade-value"),
    drawerDescription: $("#drawer-description"),
    drawerChart:    $("#drawer-chart"),
    drawerCanvas:  $("#drawer-canvas"),
    drawerChartPH: $("#drawer-chart-placeholder"),
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
  const chartLayers = { candles: true, volume: true, ma: true, rsi: true };
  let chartTimeframe = "60M";
  let chartSymbol = null;
  let drawerSymbols = [];
  let drawerIndex = -1;
  let drawerTouchStartX = null;
  let chartRequestSeq = 0;
  let chartAbort = null;
  var chartCache = {};
  let dailyVcpRequestSeq = 0;
  let dailyVcpAbort = null;
  let vcpRequestSeq = 0;
  let vcpAbort = null;

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
  function setFreshness(status, asOf, intradayAt) {
    dom.freshnessDot.className = "freshness-dot freshness-dot--" + status;
    dom.freshnessLabel.textContent = status === "loading" ? "60m loading…"
      : intradayAt ? "60m updated · " + timeAgo(intradayAt)
      : status === "fresh" ? "60m updated · " + timeAgo(asOf)
      : status === "market_closed" ? "60m updated · " + (intradayAt ? timeAgo(intradayAt) : "–")
      : status === "stale" ? "60m stale · " + timeAgo(asOf)
      : "60m update unavailable";
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

  function mergeChartDecisionOverlay(chart, item) {
    var overlay = vcpChartOverlay(item);
    ["trigger", "stop", "target"].forEach(function(field) {
      if (overlay[field] != null) chart[field] = overlay[field];
    });
    return chart;
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

  function renderDrawerChart(chart) {
    window.__signalixLastChart = chart;
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
    decisionLine(chart.trigger, "#f4c95d", "Required close");
    decisionLine(chart.stop, "#ef7777", "Stop");
    decisionLine(chart.target, "#6ee7b7", "Target");
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
    var hasItems = drawerSymbols.length > 1 && drawerIndex >= 0;
    dom.drawerPrev.disabled = !hasItems || drawerIndex <= 0;
    dom.drawerNext.disabled = !hasItems || drawerIndex >= drawerSymbols.length - 1;
    dom.drawerPrev.title = hasItems ? "Previous stock" : "No previous stock";
    dom.drawerNext.title = hasItems ? "Next stock" : "No next stock";
  }

  function visibleDrawerSymbols() {
    var selector = currentTab === "daily-vcp"
      ? "#panel-daily-vcp .vcp-card[data-symbol]"
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

  function navigateDrawer(delta) {
    var nextIndex = drawerIndex + delta;
    if (nextIndex < 0 || nextIndex >= drawerSymbols.length) return;
    var symbol = drawerSymbols[nextIndex];
    drawerIndex = nextIndex;
    openDrawer(drawerItemForSymbol(symbol), symbol, drawerSymbols, drawerIndex);
  }

  function openDrawer(item, symbol, navSymbols, navIndex) {
    chartSymbol = symbol;
    if (Array.isArray(navSymbols)) drawerSymbols = navSymbols.slice();
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
    renderDrawerDetail(item);

    var cachedChart = chartCache[chartKey];
    if (cachedChart) {
      renderDrawerChart(mergeChartDecisionOverlay(cachedChart, item));
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
          renderDrawerDetail(item.vcp_result ? mergeCanonicalDailyMetadata(item, fresh) : fresh);
          var currentChart = chartCache[chartKey];
          if (currentChart && item.vcp_result) {
            // Daily metadata can arrive after candles. It can provide an
            // optional target, but never supplies VCP trigger/invalidation.
            renderDrawerChart(mergeChartDecisionOverlay(currentChart, item));
          }
        }
      })
      .catch(function() {
        // Metadata failure is distinct from VCP evidence being NOT_VERIFIED.
        if (requestSeq !== chartRequestSeq || chartSymbol !== symbol) return;
        if (item.vcp_result) {
          item._canonicalMetadataPending = false;
          renderDrawerDetail(item);
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
  dom.drawerClose.addEventListener("click", closeDrawer);
  dom.drawerOverlay.addEventListener("click", closeDrawer);
  dom.drawerPrev.addEventListener("click", function() { navigateDrawer(-1); });
  dom.drawerNext.addEventListener("click", function() { navigateDrawer(1); });
  dom.drawer.addEventListener("touchstart", function(e) {
    if (e.touches && e.touches.length === 1) drawerTouchStartX = e.touches[0].clientX;
  }, {passive: true});
  dom.drawer.addEventListener("touchend", function(e) {
    if (drawerTouchStartX == null || !e.changedTouches || !e.changedTouches.length) return;
    var delta = e.changedTouches[0].clientX - drawerTouchStartX;
    drawerTouchStartX = null;
    if (Math.abs(delta) < 50) return;
    navigateDrawer(delta > 0 ? -1 : 1);
  }, {passive: true});
  document.addEventListener("keydown", function(e) {
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
      '<td class="vcp-row__symbol"><span class="vcp-card__primary"><strong>' + escapeHTML(symbol) + '</strong><span class="vcp-card__decision">' + escapeHTML(primaryStatus) + '</span><span class="vcp-card__evidence">' + escapeHTML(primaryEvidence) + '</span><button type="button" class="vcp-row__details" aria-label="View details for ' + escapeHTML(symbol) + '">Details</button></span>' + tagHTML + '</td>' +
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
    var order = ["REVIEW_NOW · ACTIONABLE_REVIEW", "PREPARE · WATCH_ONLY", "EVENT_WATCH · WATCH_ONLY", "RESEARCH · NO_ACTION", "DO_NOT_CHASE · NO_ACTION", "DATA_BLOCKED · NO_ACTION", "FORMING · WAIT", "READY · WAIT", "CONFIRMED · REVIEW", "EXTENDED · WAIT", "INVALIDATED · AVOID", "UNKNOWN"];
    var groups = {};
    results.forEach(function(result) { var key = vcpDisplayGroup(result); (groups[key] || (groups[key] = [])).push(result); });
    target.innerHTML = order.filter(function(key){ return groups[key] && groups[key].length; }).map(function(key) {
      return '<section class="vcp-lane"><h2 class="section-head">' + escapeHTML(key) + ' <span class="section-subhead">' + groups[key].length + '</span></h2><div class="vcp-table-wrap"><table class="vcp-table"><thead><tr><th>Symbol</th><th>Price</th><th>% Change</th><th>Distance</th><th class="vcp-row__rr">R/R</th></tr></thead><tbody>' + groups[key].map(vcpCard).join("") + '</tbody></table></div></section>';
    }).join("") || vcpEmptyState(target);
  }

  function renderDailyVcpWatchlist(lanes, target) {
    target = target || dom.dailyVcpCards;
    var order = ["action_review", "near_trigger", "breakout_watch"];
    var capKeys = {
      action_review: "ACTION_REVIEW",
      near_trigger: "NEAR_TRIGGER",
      breakout_watch: "BREAKOUT_WATCH"
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
    ["REVIEW_NOW · ACTIONABLE_REVIEW", "PREPARE · WATCH_ONLY", "EVENT_WATCH · WATCH_ONLY", "RESEARCH · NO_ACTION", "DO_NOT_CHASE · NO_ACTION", "DATA_BLOCKED · NO_ACTION", "FORMING · WAIT", "READY · WAIT", "CONFIRMED · REVIEW", "EXTENDED · WAIT", "INVALIDATED · AVOID", "UNKNOWN"].forEach(function(status) {
      if (!groups[status]) return;
      var subhead = groupHasCaps[status] ? String(groups[status].length) + " / " + String(groupCaps[status]) : String(groups[status].length);
      html += '<section class="vcp-lane"><h2 class="section-head">' + escapeHTML(status) + ' <span class="section-subhead">' + escapeHTML(subhead) + '</span></h2><div class="vcp-table-wrap"><table class="vcp-table"><thead><tr><th>Symbol</th><th>Price</th><th>% Change</th><th>Distance</th><th class="vcp-row__rr">R/R</th></tr></thead><tbody>' + groups[status].map(vcpCard).join("") + '</tbody></table></div></section>';
    });
    target.innerHTML = html || vcpEmptyState(target);
  }

  function loadDailyVcp() {
    var requestSeq = ++dailyVcpRequestSeq;
    if (dailyVcpAbort) dailyVcpAbort.abort();
    var ac = dailyVcpAbort = new AbortController();
    show(dom.dailyVcpLoading); hide(dom.dailyVcpError); hide(dom.dailyVcpContent);
    fetch("/api/vcp-finder?interval=60m&market=TH&daily_watchlist=true&universe=marginable_long", {signal: ac.signal})
      .then(function(res){ if (!res.ok) throw new Error("HTTP " + res.status); return res.json(); })
      .then(function(data){
        if (requestSeq !== dailyVcpRequestSeq) return;
        hide(dom.dailyVcpLoading); show(dom.dailyVcpContent);
        vcpRunMeta = {run_id: data.run_id || "", as_of: data.as_of || "", fetch_completed_at: data.fetch_completed_at || ""};
        setFreshness("fresh", data.as_of, data.fetch_completed_at || data.as_of);
        vcpResultsBySymbol = {};
        var lanes = data.daily_watchlist || {action_review: [], near_trigger: [], breakout_watch: []};
        var filtered = {action_review: [], near_trigger: [], breakout_watch: []};
        var insufficientCount = 0;
        ["action_review", "near_trigger", "breakout_watch"].forEach(function(key) {
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
        var total = filtered.action_review.length + filtered.near_trigger.length + filtered.breakout_watch.length;
        var coverage = (lanes && lanes.coverage) || {};
        var rejectionCounts = coverage.rejection_counts || {};
        var rejectionSummary = Object.keys(rejectionCounts).sort(function(a, b) { return rejectionCounts[b] - rejectionCounts[a]; }).slice(0, 3).map(function(key) { return key + " " + rejectionCounts[key]; }).join(", ");
        dom.dailyVcpMeta.textContent = marginableUniverseMeta(data) + " · Run " + (data.run_id || "NOT_VERIFIED") + " · " + total + " reviewable / " + ((data.universe || {}).evaluated || 0) + " evaluated" + (insufficientCount ? " · " + insufficientCount + " hidden: insufficient/unknown data" : "") + (rejectionSummary ? " · rejected: " + rejectionSummary : "") + (data.coverage && data.coverage.feed_unavailable ? " · " + data.coverage.feed_unavailable + " feed unavailable" : "");
        renderDailyVcpWatchlist(filtered, dom.dailyVcpCards);
      })
      .catch(function(err){ if (err.name === "AbortError" || requestSeq !== dailyVcpRequestSeq) return; hide(dom.dailyVcpLoading); show(dom.dailyVcpError); setFreshness("error"); dom.dailyVcpErrorMsg.textContent = "Unable to load Watchlist: " + err.message; });
  }

  function loadVcp() {
    var requestSeq = ++vcpRequestSeq;
    if (vcpAbort) vcpAbort.abort();
    var ac = vcpAbort = new AbortController();
    show(dom.vcpLoading); hide(dom.vcpError); hide(dom.vcpContent);
    var selected = dom.vcpState.value || "ALL";
    var endpoint = "/api/vcp-finder?interval=60m&market=TH&universe=marginable_long";
    if (selected === "actionable") endpoint += "&focused=true";
    else if (selected.indexOf("FORMING_") === 0) endpoint += "&state=FORMING";
    else if (selected !== "ALL") endpoint += "&state=" + encodeURIComponent(selected);
    else endpoint += "&limit=5000";
    fetch(endpoint, {signal: ac.signal})
      .then(function(res) { if (!res.ok) throw new Error("HTTP " + res.status); return res.json(); })
      .then(function(data) {
        if (requestSeq !== vcpRequestSeq) return;
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
      })
      .catch(function(err) { if (err.name === "AbortError" || requestSeq !== vcpRequestSeq) return; hide(dom.vcpLoading); show(dom.vcpError); dom.vcpErrorMsg.textContent = "Unable to load VCP Finder: " + err.message; });
  }

  [dom.dailyFilterMarginable, dom.dailyFilterTradeValue, dom.dailyFilterPrice].forEach(function(input) {
    if (input) input.addEventListener("change", loadDailyVcp);
  });
  if (dom.dailyVcpType) dom.dailyVcpType.addEventListener("change", loadDailyVcp);
  [dom.dailyVcpDecisionState, dom.dailyVcpDecision, dom.dailyVcpQuality].forEach(function(input) {
    if (input) input.addEventListener("change", loadDailyVcp);
  });
  /* ── tab switching ── */
  function switchTab(tab) {
    currentTab = tab;
    dom.tabDailyVcp.classList.toggle("nav-tab--active", tab === "daily-vcp");
    dom.tabDailyVcp.setAttribute("aria-selected", tab === "daily-vcp");
    dom.tabVcp.classList.toggle("nav-tab--active", tab === "vcp");
    dom.tabVcp.setAttribute("aria-selected", tab === "vcp");
    dom.panelDailyVcp.classList.toggle("panel--active", tab === "daily-vcp");
    dom.panelDailyVcp.classList.toggle("panel--hidden", tab !== "daily-vcp");
    dom.panelVcp.classList.toggle("panel--active", tab === "vcp");
    dom.panelVcp.classList.toggle("panel--hidden", tab !== "vcp");
    if (tab === "daily-vcp") loadDailyVcp();
    if (tab === "vcp") loadVcp();
  }

  dom.tabDailyVcp.addEventListener("click", function() { switchTab("daily-vcp"); });
  dom.tabVcp.addEventListener("click", function() { switchTab("vcp"); });
  dom.vcpState.addEventListener("change", loadVcp);
  dom.vcpType.addEventListener("change", loadVcp);
  [dom.vcpDecisionState, dom.vcpDecision, dom.vcpQuality].forEach(function(input) {
    if (input) input.addEventListener("change", loadVcp);
  });
  dom.vcpRetry.addEventListener("click", loadVcp);
  if (dom.dailyVcpRetry) dom.dailyVcpRetry.addEventListener("click", loadDailyVcp);

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
  dom.exPrev.addEventListener("click", function() {
    if (explorerPage > 1) loadExplorer(explorerPage - 1);
  });
  dom.exNext.addEventListener("click", function() {
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
  dom.slMarginable.addEventListener("change", function() {
    marginableFilter = dom.slMarginable.value || "krungsri";
    dom.exMarginable.value = marginableFilter;
    loadShortlist();
  });
  dom.exMarginable.addEventListener("change", function() {
    marginableFilter = dom.exMarginable.value || "krungsri";
    dom.slMarginable.value = marginableFilter;
    loadExplorer(1);
  });
  dom.exStage.addEventListener("change", function() {
    explorerStage = dom.exStage.value;
    loadExplorer(1);
  });
  var explorerSearchTimer = null;
  dom.exSearch.addEventListener("input", function() {
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
  dom.slRetry.addEventListener("click", loadShortlist);
  dom.slStaleRetry.addEventListener("click", loadShortlist);
  dom.exRetry.addEventListener("click", function() { loadExplorer(explorerPage); });

  /* ── init ── */
  setFreshness("loading");
  loadDailyVcp();
  setInterval(function() {
    if (currentTab === "daily-vcp") loadDailyVcp();
    else if (currentTab === "vcp" && dom.vcpState.value !== "ALL") loadVcp();
  }, 60000);
})();
