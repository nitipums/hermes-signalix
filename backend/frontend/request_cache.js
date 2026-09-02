/* Small cache for fetch payloads.  Entries own their cleanup and generation. */
(function (root) {
  "use strict";

  root.SignalixRequestCache = function createRequestCache() {
    var cache = Object.create(null);
    var inFlight = Object.create(null);
    var generation = 0;

    function load(key, requestFactory, force) {
      if (!force && Object.prototype.hasOwnProperty.call(cache, key)) {
        return { cached: true, promise: Promise.resolve(cache[key]) };
      }
      if (!force && inFlight[key]) return { cached: false, pending: true, promise: inFlight[key].promise };

      if (inFlight[key]) inFlight[key].controller.abort();
      if (force) delete cache[key];
      var entry = { generation: ++generation, controller: new AbortController(), promise: null };
      inFlight[key] = entry;
      entry.promise = Promise.resolve().then(function () {
        return requestFactory(entry.controller.signal);
      }).then(function (data) {
        if (inFlight[key] === entry) cache[key] = data;
        return data;
      }).finally(function () {
        if (inFlight[key] === entry) delete inFlight[key];
      });
      return { cached: false, promise: entry.promise, entry: entry };
    }

    return {
      load: load,
      has: function (key) { return Object.prototype.hasOwnProperty.call(cache, key); },
      clear: function (key) { delete cache[key]; }
    };
  };
})(window);
