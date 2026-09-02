/* Shared canonical setup-candidate client. Browser-native, dependency-free. */
(function (window) {
  "use strict";
  var DEFAULT_UNIVERSE = "marginable_long";
  function setupCandidatesUrl(page, pageSize, options) {
    var params = new URLSearchParams();
    params.set("universe", (options && options.universe) || DEFAULT_UNIVERSE);
    params.set("page", String(page)); params.set("page_size", String(pageSize));
    if (options && options.sector) params.set("sector", options.sector);
    return "/api/setup-candidates?" + params.toString();
  }
  function setupCandidatesRequestKey(page, pageSize, options) {
    return setupCandidatesUrl(page, pageSize, options);
  }
  function validatePage(data, page) {
    if (!data || !Array.isArray(data.items) || data.universe_filter !== DEFAULT_UNIVERSE) throw new Error("canonical universe contract mismatch");
    if (data.page !== page || !Number.isInteger(data.total_pages) || !Number.isInteger(data.total_items) || data.returned_count !== data.items.length) throw new Error("canonical pagination contract mismatch");
    return data;
  }
  async function fetchSetupCandidatesPage(page, pageSize, signal, options) {
    var response = await fetch(setupCandidatesUrl(page, pageSize, options), {signal: signal});
    if (!response.ok) throw new Error("HTTP " + response.status);
    return validatePage(await response.json(), page);
  }
  async function fetchAllCandidates(signal) {
    var page = 1, all = [], first = null, totalPages = 1;
    do { var data = await fetchSetupCandidatesPage(page, 100, signal); if (!first) first = data; totalPages = data.total_pages; all = all.concat(data.items); page += 1; } while (page <= totalPages);
    if (first && all.length !== first.total_items) throw new Error("incomplete full-universe pagination");
    return {items: all, meta: first};
  }
  function markers(item) {
    var wave = item && item.wave || {};
    return Array.isArray(wave.markers) ? wave.markers : Array.isArray(wave.evidence_markers) ? wave.evidence_markers : [];
  }
  function dailyMarkers(item) {
    var raw = markers(item);
    return raw.filter(function (marker) { return marker && marker.timeframe === "daily" && marker.timestamp != null && marker.price != null && Number.isFinite(Number(marker.price)); });
  }
  window.SignalixCanonicalClient = {setupCandidatesUrl: setupCandidatesUrl, setupCandidatesRequestKey: setupCandidatesRequestKey, fetchSetupCandidatesPage: fetchSetupCandidatesPage, fetchAllCandidates: fetchAllCandidates, markers: markers, dailyMarkers: dailyMarkers};
})(window);
