"use strict";

const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");

const context = { window: {}, AbortController };
vm.runInNewContext(fs.readFileSync(__dirname + "/frontend/request_cache.js", "utf8"), context);

function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return {promise, resolve, reject};
}

async function main() {
  const cache = context.window.SignalixRequestCache();
  const first = deferred();
  const firstRequest = cache.load("vcp", () => first.promise, false);
  first.resolve({run_id: "old"});
  await firstRequest.promise;
  assert.equal(cache.has("vcp"), true);

  const forced = deferred();
  const forcedRequest = cache.load("vcp", signal => {
    assert.equal(signal.aborted, false);
    return forced.promise;
  }, true);
  assert.equal(cache.has("vcp"), false, "force refresh must evict old data immediately");
  forced.resolve({run_id: "new"});
  assert.deepEqual(await forcedRequest.promise, {run_id: "new"});

  const retry = cache.load("vcp", () => Promise.reject(new Error("offline")), true);
  await assert.rejects(retry.promise, /offline/);
  assert.equal(cache.has("vcp"), false, "failed forced refresh must not restore stale data");

  const old = deferred();
  let oldSignal;
  const oldRequest = cache.load("race", signal => {
    oldSignal = signal;
    return old.promise;
  }, false);
  await Promise.resolve();
  const newer = deferred();
  const newRequest = cache.load("race", signal => {
    assert.equal(signal.aborted, false);
    return newer.promise;
  }, true);
  assert.equal(oldSignal.aborted, true, "superseding request must abort the older owner");
  newer.resolve({run_id: "newer"});
  assert.deepEqual(await newRequest.promise, {run_id: "newer"});
  old.resolve({run_id: "old"});
  await oldRequest.promise.catch(() => {});
  assert.equal(cache.has("race"), true, "older cleanup must not delete newer entry/cache");
  const pending = cache.load("race", () => Promise.resolve({}), false);
  assert.equal(pending.cached, true);
}

main().catch(error => { console.error(error); process.exitCode = 1; });
