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

    // shortlist states
    slLoading:     $("#shortlist-loading"),
    slError:       $("#shortlist-error"),
    slErrorMsg:    $("#shortlist-error-msg"),
    slRetry:       $("#shortlist-retry"),
    slEmpty:       $("#shortlist-empty"),
    slStale:       $("#shortlist-stale"),
    slStaleTime:   $("#shortlist-stale-time"),
    slStaleRetry:  $("#shortlist-stale-retry"),
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

    // drawer
    drawer:        $("#drawer"),
    drawerOverlay: $("#drawer-overlay"),
    drawerClose:   $("#drawer-close"),
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
    drawerRR:       $("#drawer-rr"),
    drawerMembership: $("#drawer-membership"),
    drawerMargin:   $("#drawer-margin"),
    drawer52W:      $("#drawer-52w"),
    drawerATH:      $("#drawer-ath"),
    drawerProv:     $("#drawer-provenance"),
  };

  /* ── state ── */
  let currentTab = "shortlist";
  let explorerPage = 1;
  let explorerTotalPages = 1;
  let shortlistData = null;

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
      var d = new Date(iso);
      return d.toLocaleDateString("en-GB", {day:"2-digit", month:"short", year:"2-digit", timeZone:"Asia/Bangkok"})
        .replace(/,/g, "") + "T" + d.toLocaleTimeString("en-GB", {hour:"2-digit", minute:"2-digit", hour12:false, timeZone:"Asia/Bangkok"});
    } catch (e) { return "–"; }
  }

  function displayValue(value) {
    return value == null || value === "" ? "NOT_VERIFIED" : value;
  }

  function formatRange(high, low) {
    if (high == null && low == null) return "NOT_VERIFIED";
    return (high == null ? "–" : Number(high).toFixed(2)) + " / " + (low == null ? "–" : Number(low).toFixed(2));
  }

  /* ── freshness ── */
  function setFreshness(status, asOf) {
    dom.freshnessDot.className = "freshness-dot freshness-dot--" + status;
    dom.freshnessLabel.textContent = status === "loading" ? "Loading…"
      : status === "fresh" ? "Fresh · " + timeAgo(asOf)
      : status === "market_closed" ? "Market closed · Daily EOD"
      : status === "stale" ? "Stale · " + timeAgo(asOf)
      : "Error";
  }

  /* ── render card ── */
  function buildDecisionCard(item) {
    var chg = fmtChange(item.change_pct);
    var changeAmount = fmtChangeAmount(item.change_amount);
    var action = shortAction(item.action || item.phase || "");
    var stage = shortStage(item.stage);
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
          '<span class="decision-card__stage">' + escapeHTML(stage) + '</span>' +
          '<span class="decision-card__action">' + escapeHTML(action) + '</span>' +
        '</div>' +
        '<div class="decision-card__meta">' +
          '<span>Stop ' + (item.risk_stop != null ? item.risk_stop.toFixed(2) : "–") + '</span>' +
          '<span>RS ' + (item.rs != null ? Math.round(item.rs) : "–") + '</span>' +
          '<span>Vol ' + fmtNum(item.avgDailyValue20) + '</span>' +
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
          '<span class="explorer-card__stage">' + escapeHTML(item.stage || "–") + '</span>' +
          '<span class="explorer-card__price ' + (chg[1] !== "flat" ? "decision-card__change--" + chg[1] : "") + '">' +
            (item.close != null ? item.close.toFixed(2) : "–") +
          '</span>' +
        '</div>' +
      '</div>';
  }

  /* ── detail drawer ── */
  function renderDrawerDetail(item) {
    dom.drawerSymbol.textContent = item.symbol;
    dom.drawerSymbol.href = "https://www.tradingview.com/symbols/" + encodeURIComponent(item.symbol) + "/?exchange=SET";
    dom.drawerName.textContent = item.name || "–";
    dom.drawerTrend.textContent = shortStage(item.stage);
    dom.drawerAction.textContent = shortAction(item.action || item.phase);
    dom.drawerSector.textContent = item.sector || "Sector –";
    dom.drawerIndustry.textContent = item.industry || "Industry –";
    dom.drawerMarketCap.textContent = "Market cap " + fmtNum(item.market_cap);
    dom.drawerTradeValue.textContent = "Trade value " + fmtNum(item.trade_value || item.avgDailyValue20);
    dom.drawerDescription.textContent = displayValue(item.description);
    dom.drawerPrice.textContent = item.close != null ? Number(item.close).toFixed(2) : "–";
    var drawerChg = fmtChange(item.change_pct);
    dom.drawerChange.textContent = drawerChg[0] + " (" + fmtChangeAmount(item.change_amount) + ")";
    dom.drawerTarget.textContent = displayValue(item.target != null ? Number(item.target).toFixed(2) : null);
    dom.drawerRR.textContent = displayValue(item.rr != null ? Number(item.rr).toFixed(2) + "R" : null);
    dom.drawerMembership.textContent = displayValue((item.index_membership || []).join(" · "));
    dom.drawerMargin.textContent = displayValue(item.margin_pct != null ? Number(item.margin_pct).toFixed(0) + "%" : null);
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

    if (chart.candles && chart.candles.length > 0) {
      // A real OHLCV series is present — draw it (basic canvas line render).
      dom.drawerChartPH.style.display = "none";
      if (dom.drawerCanvas) {
        dom.drawerCanvas.style.display = "block";
        drawCandles(chart.candles);
      }
    } else {
      // No candle series available — keep placeholder honest.
      dom.drawerChartPH.style.display = "block";
      dom.drawerChartPH.textContent = "No chart data available (candles NOT_VERIFIED)";
      if (dom.drawerCanvas) dom.drawerCanvas.style.display = "none";
    }
  }

  function drawCandles(candles) {
    var canvas = dom.drawerCanvas;
    if (!canvas) return;
    var ctx = canvas.getContext("2d");
    var w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    var closes = candles.map(function(c) { return Number(c.close); }).filter(function(n) { return !isNaN(n); });
    if (closes.length < 2) return;
    var min = Math.min.apply(null, closes);
    var max = Math.max.apply(null, closes);
    var range = (max - min) || 1;
    var pad = 8;
    ctx.strokeStyle = "#c9a84c";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (var i = 0; i < closes.length; i++) {
      var x = pad + (i / (closes.length - 1)) * (w - pad * 2);
      var y = h - pad - ((closes[i] - min) / range) * (h - pad * 2);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  function openDrawer(item, symbol) {
    // Immediate render from local card data (fast path).
    renderDrawerDetail(item);

    // Reset overlay legend to loading placeholder.
    dom.indMa20.textContent = "…"; dom.indMa50.textContent = "…";
    dom.indMa200.textContent = "…"; dom.indMacd.textContent = "…";
    dom.indRsi.textContent = "…"; dom.indTrigger.textContent = "…";
    dom.indStop.textContent = "…"; dom.indTarget.textContent = "…";
    dom.drawerChartPH.style.display = "block";
    dom.drawerChartPH.textContent = "Chart loading…";
    if (dom.drawerCanvas) dom.drawerCanvas.style.display = "none";

    dom.drawer.classList.remove("drawer--hidden");
    document.body.style.overflow = "hidden";

    // Fetch authoritative symbol detail from the served API.
    fetch("/api/symbol/" + encodeURIComponent(symbol))
      .then(function(res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function(fresh) {
        if (fresh && fresh.symbol) renderDrawerDetail(fresh);
      })
      .catch(function() { /* keep card-local detail on failure */ });

    // Fetch DB-backed candles first; snapshot overlay is fallback only.
    fetch("/api/chart-db/" + encodeURIComponent(symbol))
      .then(function(res) {
        if (!res.ok) throw new Error("DB chart HTTP " + res.status);
        return res.json();
      })
      .catch(function() {
        return fetch("/api/chart/" + encodeURIComponent(symbol)).then(function(res) {
          if (!res.ok) throw new Error("snapshot chart HTTP " + res.status);
          return res.json();
        });
      })
      .then(function(chart) {
        if (chart && chart.symbol) renderDrawerChart(chart);
      })
      .catch(function() {
        dom.drawerChartPH.style.display = "block";
        dom.drawerChartPH.textContent = "Chart data unavailable";
      });
  }

  function closeDrawer() {
    dom.drawer.classList.add("drawer--hidden");
    document.body.style.overflow = "";
  }

  /* ── card click delegation ── */
  document.addEventListener("click", function(e) {
    var card = e.target.closest(".decision-card, .explorer-card");
    if (!card) return;
    var symbol = card.getAttribute("data-symbol");
    if (!symbol) return;

    // Find local item for immediate fast-path render (may be partial for
    // explorer cards); authoritative detail is fetched from /api/symbol/.
    var item = null;
    if (shortlistData) {
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
    openDrawer(item, symbol);
  });

  /* ── close drawer ── */
  dom.drawerClose.addEventListener("click", closeDrawer);
  dom.drawerOverlay.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", function(e) {
    if (e.key === "Escape" && !dom.drawer.classList.contains("drawer--hidden")) closeDrawer();
  });

  /* ── tab switching ── */
  function switchTab(tab) {
    currentTab = tab;
    dom.tabShortlist.classList.toggle("nav-tab--active", tab === "shortlist");
    dom.tabShortlist.setAttribute("aria-selected", tab === "shortlist");
    dom.tabExplorer.classList.toggle("nav-tab--active", tab === "explorer");
    dom.tabExplorer.setAttribute("aria-selected", tab === "explorer");

    dom.panelShortlist.classList.toggle("panel--active", tab === "shortlist");
    dom.panelShortlist.classList.toggle("panel--hidden", tab !== "shortlist");
    dom.panelExplorer.classList.toggle("panel--active", tab === "explorer");
    dom.panelExplorer.classList.toggle("panel--hidden", tab !== "explorer");

    if (tab === "explorer") loadExplorer(1);
  }

  dom.tabShortlist.addEventListener("click", function() { switchTab("shortlist"); });
  dom.tabExplorer.addEventListener("click", function() { switchTab("explorer"); });

  /* ── fetch shortlist ── */
  function loadShortlist() {
    setFreshness("loading");
    hideAll(".shortlist-section");
    hide(dom.slError);
    hide(dom.slEmpty);
    hide(dom.slStale);
    show(dom.slLoading);

    fetch("/api/daily-shortlist")
      .then(function(res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function(data) {
        shortlistData = data;
        hide(dom.slLoading);

        var freshness = data.freshness || {};
        var fStatus = (freshness.status === "stale") ? "stale"
          : (freshness.status === "market_closed") ? "market_closed"
          : (freshness.status === "fresh" || freshness.status === "latest_available") ? "fresh"
          : "stale";
        setFreshness(fStatus, freshness.as_of || freshness.data_fetched_at);

        // stale state
        if (fStatus === "stale") {
          show(dom.slStale);
          dom.slStaleTime.textContent = freshness.as_of || freshness.data_fetched_at || "–";
        } else {
          hide(dom.slStale);
        }

        var ready = data.ready || [];
        var preReady = data.pre_ready || [];

        if (ready.length === 0 && preReady.length === 0) {
          show(dom.slEmpty);
          return;
        }
        hide(dom.slEmpty);

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
        // fallback: try fixture
        tryFixtureShortlist();
      });
  }

  /* ── fixture fallback for development ── */
  function tryFixtureShortlist() {
    fetch("fixtures/daily_shortlist.json?v=mvp4")
      .then(function(res) { return res.ok ? res.json() : Promise.reject("no fixture"); })
      .then(function(data) {
        shortlistData = data;
        hide(dom.slLoading);
        hide(dom.slError);
        hide(dom.slEmpty);
        setFreshness("fresh", data.freshness.as_of);

        var ready = data.ready || [];
        var preReady = data.pre_ready || [];

        if (ready.length > 0) {
          show($("#shortlist-ready"));
          dom.slReadyCards.innerHTML = "";
          ready.forEach(function(item) {
            dom.slReadyCards.insertAdjacentHTML("beforeend", buildDecisionCard(item));
          });
        }
        if (preReady.length > 0) {
          show($("#shortlist-pre-ready"));
          dom.slPreCards.innerHTML = "";
          preReady.forEach(function(item) {
            dom.slPreCards.insertAdjacentHTML("beforeend", buildDecisionCard(item));
          });
        }
      })
      .catch(function() { /* fixture also failed, error state prevails */ });
  }

  /* ── fetch explorer ── */
  function loadExplorer(page) {
    page = page || 1;
    explorerPage = page;
    show(dom.exLoading);
    hide(dom.exError);
    hide(dom.exEmpty);
    hide($("#explorer-content"));

    fetch("/api/explorer?page=" + page + "&page_size=20")
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
        // fallback to fixture
        tryFixtureExplorer(page);
      });
  }

  function tryFixtureExplorer(page) {
    fetch("fixtures/explorer_page1.json")
      .then(function(res) { return res.ok ? res.json() : Promise.reject("no fixture"); })
      .then(function(data) {
        hide(dom.exLoading);
        hide(dom.exError);
        show($("#explorer-content"));

        var items = data.items || [];
        dom.exCards.innerHTML = "";
        items.forEach(function(item) {
          dom.exCards.insertAdjacentHTML("beforeend", buildExplorerCard(item));
        });

        explorerTotalPages = data.total_pages || 1;
        dom.exPageInfo.textContent = "Page " + page + " of " + explorerTotalPages;
        dom.exPrev.disabled = page <= 1;
        dom.exNext.disabled = page >= explorerTotalPages;
      })
      .catch(function() { /* fixture also failed */ });
  }

  /* ── pagination controls ── */
  dom.exPrev.addEventListener("click", function() {
    if (explorerPage > 1) loadExplorer(explorerPage - 1);
  });
  dom.exNext.addEventListener("click", function() {
    if (explorerPage < explorerTotalPages) loadExplorer(explorerPage + 1);
  });

  /* ── retry buttons ── */
  dom.slRetry.addEventListener("click", loadShortlist);
  dom.slStaleRetry.addEventListener("click", loadShortlist);
  dom.exRetry.addEventListener("click", function() { loadExplorer(explorerPage); });

  /* ── init ── */
  setFreshness("loading");
  loadShortlist();
})();