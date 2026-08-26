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
    dailyVcpContent: $("#daily-vcp-content"),
    dailyVcpCards:   $("#daily-vcp-cards"),
    dailyVcpMeta:    $("#daily-vcp-meta"),
    tabVcp:          $("#tab-vcp"),
    panelVcp:        $("#panel-vcp"),
    vcpLoading:      $("#vcp-loading"),
    vcpError:        $("#vcp-error"),
    vcpErrorMsg:     $("#vcp-error-msg"),
    vcpRetry:        $("#vcp-retry"),
    vcpContent:      $("#vcp-content"),
    vcpCards:        $("#vcp-cards"),
    vcpState:        $("#vcp-state"),
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
  let chartTimeframe = "1D";
  let chartSymbol = null;
  let drawerSymbols = [];
  let drawerIndex = -1;
  let drawerTouchStartX = null;
  let chartRequestSeq = 0;
  let chartAbort = null;

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

  function formatRange(high, low) {
    if (high == null && low == null) return "NOT_VERIFIED";
    return (high == null ? "–" : Number(high).toFixed(2)) + " / " + (low == null ? "–" : Number(low).toFixed(2));
  }

  /* ── freshness ── */
  function setFreshness(status, asOf, intradayAt) {
    dom.freshnessDot.className = "freshness-dot freshness-dot--" + status;
    dom.freshnessLabel.textContent = status === "loading" ? "Loading…"
      : status === "fresh" ? "Fresh · " + timeAgo(asOf)
      : status === "market_closed" ? "Daily EOD · " + timeAgo(asOf) + " · 60m " + (intradayAt ? timeAgo(intradayAt) : "NOT_VERIFIED")
      : status === "stale" ? "Stale · " + timeAgo(asOf)
      : "Error";
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
          '<span>Trigger ' + escapeHTML(item.trigger || "NOT_VERIFIED") + '</span>' +
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

  function renderDrawerDetail(item) {
    if (item.vcp_result) {
      var vr = item.vcp_result;
      var vp = vr.price || {};
      var vd = vr.data || {};
      var vm = vcpRunMeta || {};
      item = Object.assign({}, item, {
        name: item.symbol,
        action: vcpStateLabel(vr.state),
        close: vp.last_close,
        trigger: vp.pivot_high,
        risk_stop: vp.invalidation,
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
    dom.drawerAction.textContent = shortAction(item.action || item.phase);
    dom.drawerSector.textContent = item.sector || "Sector –";
    dom.drawerIndustry.textContent = item.industry || "Industry –";
    dom.drawerMarketCap.textContent = "Market cap " + fmtNum(item.market_cap);
    dom.drawerTradeValue.textContent = "Trade value " + fmtNum(item.trade_value || item.avgDailyValue20);
    dom.drawerDescription.textContent = item.description || "";
    dom.drawerDescription.hidden = !item.description;
    dom.drawerPrice.textContent = item.close != null ? Number(item.close).toFixed(2) : "–";
    var drawerChg = fmtChange(item.change_pct);
    dom.drawerChange.textContent = drawerChg[0] + " (" + fmtChangeAmount(item.change_amount) + ")";
    dom.drawerTrigger.textContent = displayValue(item.trigger);
    dom.drawerStop.textContent = displayValue(item.risk_stop != null ? Number(item.risk_stop).toFixed(2) : null);
    dom.drawerTarget.textContent = displayValue(item.target != null ? Number(item.target).toFixed(2) : null);
    dom.drawerRR.textContent = displayValue(item.rr != null ? Number(item.rr).toFixed(2) + "R" : null);
    setOptionalDrawerField(dom.drawerMembership, (item.index_membership || []).join(" · "));
    var marginRate = item.margin_rate_pct != null ? item.margin_rate_pct : item.margin_pct;
    setOptionalDrawerField(dom.drawerMargin, marginRate != null ? Number(marginRate).toFixed(0) + "%" : null);
    dom.drawer52W.textContent = formatRange(item.high52, item.low52);
    dom.drawerATH.textContent = formatRange(item.ath_high, item.ath_low);
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
    // Populate overlay legend with real values; null → NOT_VERIFIED.
    var ma20 = latestIndicatorValue(chart.ma20);
    var ma50 = latestIndicatorValue(chart.ma50);
    var ma200 = latestIndicatorValue(chart.ma200);
    var macd = latestIndicatorValue(chart.macd);
    var rsi = latestIndicatorValue(chart.rsi);
    dom.indMa20.textContent = ma20 != null ? ma20.toFixed(2) : "NOT_VERIFIED";
    dom.indMa50.textContent = ma50 != null ? ma50.toFixed(2) : "NOT_VERIFIED";
    dom.indMa200.textContent = ma200 != null ? ma200.toFixed(2) : "NOT_VERIFIED";
    dom.indMacd.textContent = macd != null ? macd.toFixed(3) : "NOT_VERIFIED";
    dom.indRsi.textContent = rsi != null ? rsi.toFixed(1) : "NOT_VERIFIED";
    dom.indTrigger.textContent = chart.trigger != null ? String(chart.trigger) : "NOT_VERIFIED";
    dom.indStop.textContent = chart.stop != null ? Number(chart.stop).toFixed(2) : "NOT_VERIFIED";
    dom.indTarget.textContent = chart.target != null ? Number(chart.target).toFixed(2) : "NOT_VERIFIED";

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
    var min = Math.min.apply(null, lows.filter(function(v){return Number.isFinite(v);}));
    var max = Math.max.apply(null, highs.filter(function(v){return Number.isFinite(v);}));
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
    return localShortlistItem(symbol) || {symbol: symbol, name: symbol, provenance: {}};
  }

  function navigateDrawer(delta) {
    var nextIndex = drawerIndex + delta;
    if (nextIndex < 0 || nextIndex >= drawerSymbols.length) return;
    var symbol = drawerSymbols[nextIndex];
    drawerIndex = nextIndex;
    openDrawer(drawerItemForSymbol(symbol), symbol, drawerSymbols, drawerIndex);
  }

  function openDrawer(item, symbol, navSymbols, navIndex) {
    var sameSymbolOpen = chartSymbol === symbol && !dom.drawer.classList.contains("drawer--hidden");
    chartSymbol = symbol;
    if (Array.isArray(navSymbols)) drawerSymbols = navSymbols.slice();
    if (navIndex != null) drawerIndex = navIndex;
    else {
      drawerIndex = drawerSymbols.indexOf(symbol);
      if (drawerIndex < 0) drawerIndex = -1;
    }
    updateDrawerNav();
    var requestSeq = ++chartRequestSeq;
    var requestedTimeframe = item.vcp_result ? "60M" : chartTimeframe;
    if (item.vcp_result) chartTimeframe = "60M";
    if (chartAbort) chartAbort.abort();
    var chartController = new AbortController();
    chartAbort = chartController;
    // Immediate render from local card data (fast path).
    renderDrawerDetail(item);

    // Reset overlay legend to loading placeholder.
    dom.indMa20.textContent = "…"; dom.indMa50.textContent = "…";
    dom.indMa200.textContent = "…"; dom.indMacd.textContent = "…";
    dom.indRsi.textContent = "…"; dom.indTrigger.textContent = "…";
    dom.indStop.textContent = "…"; dom.indTarget.textContent = "…";
    if (sameSymbolOpen && window.__signalixLastChart && Array.isArray(window.__signalixLastChart.candles) && window.__signalixLastChart.candles.length >= 2) {
      // Keep the last-good plot visible while a new timeframe request is in flight.
      dom.drawerChartPH.style.display = "none";
      if (dom.drawerCanvas) dom.drawerCanvas.style.display = "block";
    } else {
      dom.drawerChartPH.style.display = "block";
      dom.drawerChartPH.textContent = "Chart loading…";
      if (dom.drawerCanvas) dom.drawerCanvas.style.display = "none";
    }

    dom.drawer.classList.remove("drawer--hidden");
    document.body.style.overflow = "hidden";

    // Daily/Explorer details are intentionally not fetched for VCP: card payload is the authoritative VCP detail.
    if (!item.vcp_result) fetch("/api/symbol/" + encodeURIComponent(symbol))
      .then(function(res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function(fresh) {
        if (fresh && fresh.symbol) renderDrawerDetail(fresh);
      })
      .catch(function() { /* keep card-local detail on failure */ });

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
          if (!Array.isArray(chart.candles) || chart.candles.length < 2) {
            chart.candles = [];
            chart.provenance = chart.provenance || {};
            chart.provenance.note = chart.provenance.note || (requestedTimeframe === "60M" ? "60m unavailable · Daily EOD remains the decision source." : "Chart candles NOT_VERIFIED.");
          }
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
      item = Object.assign({symbol: symbol, vcp_result: vcpResultsBySymbol[symbol] || null}, vcpResultsBySymbol[symbol] || {});
      item.name = symbol;
      item.action = vcpStateLabel(item.state);
      item.description = null;
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
    return ({READY: "SETUP READY · WAIT FOR BREAKOUT", NEAR_TRIGGER: "NEAR TRIGGER · VOLUME CHECK", BREAKOUT_WATCH: "BREAKOUT WATCH · INTRABAR", EXTENDED: "DO NOT CHASE", FORMING: "FORMING", FAILED: "FAILED", STALE: "STALE 60m DATA", NOT_VERIFIED: "NOT VERIFIED"})[state] || state || "NOT VERIFIED";
  }

  function vcpCard(result) {
    var price = result.price || {}, pattern = result.pattern || {}, volume = result.volume || {}, data = result.data || {};
    var state = result.state || "NOT_VERIFIED";
    var cls = state.toLowerCase().replace(/_/g, "-");
    var reason = (result.reasons || result.reason_codes || []).join(" · ");
    var feed = data.feed_status === "unavailable" ? "Feed unavailable · " + (data.feed_reason || "retry pending") : "60m feed " + (data.feed_status || "NOT_VERIFIED");
    var tags = [];
    if (Array.isArray(result.index_membership)) tags = tags.concat(result.index_membership);
    if (result.margin_rate_pct != null) tags.push("%Margin " + Number(result.margin_rate_pct).toFixed(0) + "%");
    var tagHTML = tags.length ? '<div class="vcp-card__tags">' + tags.map(function(tag){ return '<span class="tag">' + escapeHTML(tag) + '</span>'; }).join("") + '</div>' : '';
    return '<tr class="vcp-row vcp-card vcp-card--' + escapeHTML(cls) + '" data-symbol="' + escapeHTML(result.symbol || "") + '">' +
      '<td class="vcp-row__symbol"><strong>' + escapeHTML(result.symbol || "–") + '</strong>' + tagHTML + '</td>' +
      '<td>' + displayValue(price.last_close) + '</td>' +
      '<td class="vcp-row__change">' + (price.change_pct == null ? "—" : Number(price.change_pct).toFixed(2) + "%") + '</td>' +
      '<td>' + (price.distance_to_pivot_pct == null ? "—" : Number(price.distance_to_pivot_pct).toFixed(2) + "%") + '</td>' +
      '<td>' + (result.rr == null ? "—" : Number(result.rr).toFixed(2) + "R") + '</td>' +
    '</tr>';
  }

  function vcpDisplayGroup(result) {
    if (result.state === "FORMING") return "FORMING · " + ({maturing: "MATURING", early: "EARLY", needs_work: "NEEDS WORK"}[result.forming_group] || "NEEDS WORK");
    return ({BREAKOUT_WATCH: "BREAKOUT WATCH · INTRABAR", CONFIRMED: "CONFIRMED · REVIEW", NEAR_TRIGGER: "NEAR TRIGGER · VOLUME CHECK", READY: "READY · WAIT FOR BREAKOUT", EXTENDED: "EXTENDED · DO NOT CHASE", FAILED: "FAILED / INVALIDATED", STALE: "STALE DATA", NOT_VERIFIED: "NOT VERIFIED"}[result.state] || result.state || "OTHER");
  }

  function renderVcpResults(results, target) {
    target = target || dom.vcpCards;
    var order = ["BREAKOUT WATCH · INTRABAR", "CONFIRMED · REVIEW", "NEAR TRIGGER · VOLUME CHECK", "READY · WAIT FOR BREAKOUT", "FORMING · MATURING", "FORMING · EARLY", "FORMING · NEEDS WORK", "EXTENDED · DO NOT CHASE", "FAILED / INVALIDATED", "STALE DATA", "NOT VERIFIED"];
    var groups = {};
    results.forEach(function(result) { var key = vcpDisplayGroup(result); (groups[key] || (groups[key] = [])).push(result); });
    target.innerHTML = order.filter(function(key){ return groups[key] && groups[key].length; }).map(function(key) {
      return '<section class="vcp-lane"><h2 class="section-head">' + escapeHTML(key) + ' <span class="section-subhead">' + groups[key].length + '</span></h2><div class="vcp-table-wrap"><table class="vcp-table"><thead><tr><th>Symbol</th><th>Price</th><th>% Change</th><th>Distance</th><th>R/R</th></tr></thead><tbody>' + groups[key].map(vcpCard).join("") + '</tbody></table></div></section>';
    }).join("") || '<div class="state"><div class="state-icon">⌛</div><p class="state-text">No VCP results for this filter.</p></div>';
  }

  function loadDailyVcp() {
    show(dom.dailyVcpLoading); hide(dom.dailyVcpError); hide(dom.dailyVcpContent);
    fetch("/api/vcp-finder?interval=60m&market=TH&actionable=true")
      .then(function(res){ if (!res.ok) throw new Error("HTTP " + res.status); return res.json(); })
      .then(function(data){
        hide(dom.dailyVcpLoading); show(dom.dailyVcpContent);
        vcpRunMeta = {run_id: data.run_id || "", as_of: data.as_of || "", fetch_completed_at: data.fetch_completed_at || ""};
        vcpResultsBySymbol = {};
        var results = (data.results || []).filter(function(r){ return ["READY","NEAR_TRIGGER","CONFIRMED","BREAKOUT_WATCH"].indexOf(r.state) >= 0; });
        results.forEach(function(r){ vcpResultsBySymbol[r.symbol] = r; });
        dom.dailyVcpMeta.textContent = "Run " + (data.run_id || "NOT_VERIFIED") + " · " + results.length + " actionable / " + ((data.universe || {}).evaluated || 0) + " evaluated";
        renderVcpResults(results, dom.dailyVcpCards);
      })
      .catch(function(err){ hide(dom.dailyVcpLoading); show(dom.dailyVcpError); dom.dailyVcpErrorMsg.textContent = "Unable to load Daily VCP shortlist: " + err.message; });
  }

  function loadVcp() {
    show(dom.vcpLoading); hide(dom.vcpError); hide(dom.vcpContent);
    var selected = dom.vcpState.value || "actionable";
    var endpoint = "/api/vcp-finder?interval=60m&market=TH";
    if (selected === "actionable") endpoint += "&focused=true";
    else if (selected.indexOf("FORMING_") === 0) endpoint += "&state=FORMING";
    else if (selected !== "ALL") endpoint += "&state=" + encodeURIComponent(selected);
    else endpoint += "&limit=5000";
    fetch(endpoint)
      .then(function(res) { if (!res.ok) throw new Error("HTTP " + res.status); return res.json(); })
      .then(function(data) {
        hide(dom.vcpLoading); show(dom.vcpContent);
        vcpRunMeta = {run_id: data.run_id || "", as_of: data.as_of || "", fetch_completed_at: data.fetch_completed_at || ""};
        vcpResultsBySymbol = {};
        (data.results || []).forEach(function(r) { vcpResultsBySymbol[r.symbol] = r; });
        var selected = dom.vcpState.value || "actionable";
        var results = data.results || [];
        if (marginRates.length) results = results.filter(function(r){ return marginRates.indexOf(Number(r.margin_rate_pct)) >= 0; });
        results = results.filter(priceMatches);
        if (selected === "actionable") results = results.filter(function(r){ return ["READY","NEAR_TRIGGER","CONFIRMED","BREAKOUT_WATCH"].indexOf(r.state) >= 0 || (r.state === "FORMING" && r.forming_group === "maturing"); });
        else if (selected.indexOf("FORMING_") === 0) results = results.filter(function(r){ return r.state === "FORMING" && r.forming_group === selected.slice(8).toLowerCase(); });
        else if (selected !== "ALL") results = results.filter(function(r){ return r.state === selected; });
        dom.vcpMeta.textContent = "Run " + (data.run_id || "NOT_VERIFIED") + " · " + (results.length) + " shown / " + ((data.universe || {}).evaluated || 0) + " evaluated";
        renderVcpResults(results);
      })
      .catch(function(err) { hide(dom.vcpLoading); show(dom.vcpError); dom.vcpErrorMsg.textContent = "Unable to load VCP Finder: " + err.message; });
  }

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
  dom.vcpRetry.addEventListener("click", loadVcp);

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
  function updateMarginRates(surface) {
    marginRates = Array.from(document.querySelectorAll('.margin-rate-toggle[data-surface="' + surface + '"]:checked'))
      .map(function(input) { return Number(input.value); }).sort(function(a, b) { return a - b; });
    $$(".margin-rate-toggle").forEach(function(input) {
      input.checked = marginRates.indexOf(Number(input.value)) >= 0;
    });
    if (surface === "vcp") return;
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
    updateMarginRates("vcp");
  });
  if (dom.vcpMarginClear) dom.vcpMarginClear.addEventListener("click", function() {
    $$(".margin-rate-toggle[data-surface=\"vcp\"]").forEach(function(input){ input.checked = false; });
    updateMarginRates("vcp");
  });
  if (dom.vcpFilterApply) dom.vcpFilterApply.addEventListener("click", function() { loadVcp(); });
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
      chartTimeframe = btn.getAttribute("data-timeframe") || "1D";
      $$(".chart-timeframe").forEach(function(other) { other.classList.toggle("is-active", other === btn); });
      if (chartSymbol) {
        openDrawer({symbol: chartSymbol, name: chartSymbol}, chartSymbol);
      }
    });
  });
  $$(".chart-toggle").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var layer = btn.getAttribute("data-layer");
      chartLayers[layer] = !chartLayers[layer];
      btn.classList.toggle("is-active", chartLayers[layer]);
      if (window.__signalixLastChart) drawChart(window.__signalixLastChart);
    });
  });

  /* ── retry buttons ── */
  dom.slRetry.addEventListener("click", loadShortlist);
  dom.slStaleRetry.addEventListener("click", loadShortlist);
  dom.exRetry.addEventListener("click", function() { loadExplorer(explorerPage); });

  /* ── init ── */
  setFreshness("loading");
  loadDailyVcp();
})();