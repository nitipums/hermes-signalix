# Signalix QA Audit — REVIEW ONLY

**Scope:** Signalix scanner output consistency, logic contradictions, error states, test gaps, and live UI at `http://91.98.72.120:3001/dashboard.html`
**Mode:** REVIEW ONLY — no files patched, no production modified
**Reviewer:** Nida (QA), for Bee → Arm sign-off
**Source files reviewed:** `backend/scanner.py`, `backend/screening.py`, `backend/build_dashboard.py`, `backend/app.py`, `backend/delivery.py`, `backend/users.py`, `backend/portfolio.py`, `backend/ingest.py`, `backend/llm.py`, `backend/test_screening.py`, `backend/test_portfolio.py`, `backend/scan_results.json`, `backend/dashboard.html` (live-served)

---

## 1. Executive Summary

| Severity | Count |
|----------|-------|
| **Critical** | 3 |
| **High** | 2 |
| **Medium** | 4 |
| **Low** | 3 |
| **Info / missing-tests** | 6 |

**Top-line finding:** The dashboard being served contains a **stale embedded data snapshot** (866 symbols) that is out of sync with the current `scan_results.json` (1,796 symbols, ~2× every group). Combined with **two independent decision engines** (`trade_readiness.status` vs `build_dashboard.determine_action`) that disagree on action labels, users may act on data that is hours stale and on recommendations that contradict the scanner's own readiness classification.

No production changes were made. All evidence is cited from local file reads / code path tracing (live browser access was blocked by the in-gateway sandbox; the static HTML served on :3001 was read directly from disk).

---

## 2. Findings

### CRITICAL

#### C1. Stale dashboard data — served HTML is a snapshot, not live
**File:** `backend/dashboard.html` (served by `dashboard_server.py` on :3001)
**Evidence:**
- `dashboard.html` embeds a `const items=[...]` array containing **866 symbols** (verified: 866 `"symbol":"` matches in HTML; meta counts sum: 6+11+205+44+28+166+406 = 866).
- `scan_results.json` (the input `build_dashboard.py` reads) contains **1,796 symbols** across groups (entry_now=12, breakout_extended=22, trend_leaders=410, consolidating=369, watchlist=88, early_reversal=59, falling=836).
- **Every group count in the served HTML is roughly half** the current scan_results.json group size.
- Field-level drift example — **TFG**:
  - `dashboard.html` (embedded): `close=9.9, rs=96.0, entry50=9.4, entry62=9.92, stop=9.3, priceSource="15m stored`, ageLabel="22h ago`
  - `scan_results.json` (line 91109): `close=10.0, rs=96.3, entry50=10.2 (buy_zone only, no 62), buy_zones_90d {50:9.4, 62:9.92}, stop_loss=9.3`
- `build_dashboard.build()` (line 287-348) **does** rebuild from `scan_results.json` and writes `OUT_HTML`, but there is no evidence the rebuild was run after the last scan. The served file lags.

**Impact:** Users see prices, RS ratings, entry zones, and group counts that are **stale and halved**. A trader entering based on `close=9.9` when the market closed at 10.0+ gets mis-sized risk.
**Recommendation:** Verify the cron/scan → `build_dashboard.build()` → serve pipeline triggers atomically. Add a freshness header or "last built" timestamp visible on the page so users can see staleness. Add a smoke check that asserts `len(items)` in the generated HTML matches `len(groups)` in scan_results.json.

---

#### C2. Two conflicting decision engines produce different actions for the same symbol
**Files:** `backend/scanner.py:trade_readiness()` (computes `status` in {`BUY`,`HOLD`,`OVERBOUGHT`,`BREAK`,`WAIT`}) vs `backend/build_dashboard.py:determine_action()` (computes `action` in {`READY`,`WAIT`,`AVOID CHASING`,`INVALIDATED`}).
**Evidence — TFG, STGT, MCOT (all 3 entry_now candidates):**
| Symbol | `trade_readiness.status` (scanner.py) | `determine_action` (dashboard) | Embedded action |
|--------|---------------------------------------|-------------------------------|-----------------|
| TFG    | **BUY** (TT=8, near_zone, RSI rising, above MA200) | READY (close not in 50–62 zone: 9.9 < 9.4 entry50? → uses `near`) | READY |
| STGT   | **BUY** (TT=8, near_zone, RSI 61.5 rising, above MA200, breakout) | READY | READY |
| MCOT   | **BUY** (TT=8, near_zone, RSI 51.6 rising, above MA200) | READY | READY |
| BANPU  | **OVERBOUGHT** (RSI 91.1 >= 78) → wait, check `determine_action` path | — | — |

**Root cause:** `serialize()` (build_dashboard.py:258) calls `determine_action()` which re-implements its own BUY/HOLD/WAIT logic using **different conditions** than `trade_readiness()`:
- `trade_readiness.buy_setup` requires: `TT>=8 AND near_buy_zone AND RSI∈[38,62] AND rsi_rising AND above_ma200` → **BUY**
- `determine_action` for entry_now returns READY only if `close in [entry50, entry62]` OR `near AND invalid is not None`; otherwise WAIT. It **never returns BUY/AVOID** for entry_now — "BUY" is not even in its vocabulary.

**Impact:** The same signal is called **BUY** by the scanner and **READY** by the dashboard. The "why this?" tooltip on the modal uses embedded fields that trace back to `determine_action`, not `trade_readiness.status`. This is a logic contradiction that can mislead.
**Recommendation:** Either (a) make `determine_action` consume `trade_readiness.status` as the source of truth, or (b) document the two-tier model explicitly (BUY = scanner verdict; READY = dashboard entry-zone check). Right now both claim to be "the" recommendation.

---

#### C3. `snapshots()` overwrites `previous_close` with `None` when intraday data exists — change% breaks
**File:** `backend/build_dashboard.py:55-58, 60-66`
```python
# line 57-58: intraday overlay
value.update({"close": float(close), "date": str(ts), "price_source": interval,
              "previous_close": None, "change": None})
# line 60-66: daily change calc — SKIPPED because change is not None? No:
for value in out.values():
    if value.get("change") is not None:   # <-- change is None from above → enters
        continue
    prev, close = value.get("previous_close"), value.get("close")
    if value.get("price_source") is None:  # <-- but price_source is SET → SKIPS
        value["change"] = ...
```
**Evidence:** Every symbol with an intraday overlay gets `previous_close=None` and `change=null`. The daily-change fallback at line 65 is guarded by `if value.get("price_source") is None`, which is **never true** when intraday data was overlaid. So `change` stays `None` forever for intraday-priced symbols. The embedded dashboard data confirms: `change: null` for TFG, STGT, MCOT, SALEE, SLP, PAF (all `priceSource:"15m stored"`).

**Impact:** The "gain/loss" pill on every card is blank (`—`) for the highest-priority opportunity group, because change is always null there. Users cannot see day-over-day momentum on the very cards most likely to be acted on.
**Recommendation:** When overlaying intraday, preserve the EOD `previous_close` (store it separately) and compute an intraday-vs-EOD change, or fall back to comparing intraday close vs prior EOD close.

---

### HIGH

#### H1. RS Rating: dead legacy linear code path still lives in `scanner.py`
**File:** `backend/scanner.py:41-63` — `compute_rs_rating()` still uses the old clamped linear map `50 + (diff/0.5)*50` (saturates >100), with a docstring that *says* it's "kept ONLY for the single-symbol path" and points callers to `compute_rs_percentile`.
**Evidence:** `scanner.py:analyze_symbol()` (line 315) **still calls** `compute_rs_rating(close, market_series)` — the saturated version. The DB path (`screening.py`) correctly uses the rank-based `compute_rs_percentile` / `_universe_rs_ranks`. So running `python scanner.py` standalone produces **different RS ratings** than the production scan. No test asserts these two paths agree.
**Impact:** If anyone runs the standalone `scanner.py` (documented in its `__main__`), they get RS=100 saturated values — the exact bug the comment claims was fixed. Dual implementations diverge.
**Recommendation:** Remove or clearly gate `compute_rs_rating`; route `__main__` through the same rank-based path. Add a test asserting `compute_rs_percentile` and `compute_rs_rating` agree on a controlled input set.

---

#### H2. `position_sizing` produces absurd share counts for penny stocks
**File:** `backend/scanner.py:154-164` — fixed-% risk sizing with a hardcoded portfolio_value=100,000 THB.
**Evidence from scan_results.json:**
- `PROS`: close=0.16, stop=0.15 → `risk_per_share=0.01` → **shares=99,999** (portfolio notional 15,999 THB to own 99,999 shares at 0.16). The `risk_per_share` rounds to 0.01 and the floor division produces an absurd quantity.
- `HYDRO`: close=0.05, stop=0.05 → `risk_per_share=0.0` → shares=0, note="invalid stop".
**Impact:** Penny-stock position sizing emits nonsensical share counts / zero-risk per share. If bots consume this, an order for 99,999 shares of a 0.16 THB stock would be catastrophic. No guard clamps `shares` to a sane maximum.
**Recommendation:** Add a guard: if `risk_per_share < minimum_tick * safety_factor`, return shares=0 with a reason. Add a max-position-size sanity cap.

---

### MEDIUM

#### M1. `freshness_info()` — EOD path hardcodes `is_stale=False` even for ancient data
**File:** `build_dashboard.py:161-162`
```python
if source == "Daily EOD":
    return ("Daily EOD", as_date(ts) or "Unavailable", "EOD", False)
```
**Evidence:** A symbol whose last EOD bar is months old (e.g., `SAWANG` last_date=2026-08-05 vs scan as-of 2026-08-11) is marked `stale: false` because the Daily EOD branch ignores `ts` age entirely. The intraday branch checks age, but EOD does not.
**Impact:** Users see "Daily EOD" provenance with no staleness warning even for stale EOD data. The topbar says "As of 11 Aug 2026" but individual cards can be days behind with no flag.
**Recommendation:** Compute staleness for EOD too (compare `as_of` date to DB max date; flag if older than the scan's MAX_STALE_DAYS=10).

---

#### M2. `plan()` drops the "62%" fib level for `entry_now` when buy_zone has only `50`
**File:** `build_dashboard.py:222-223`
```python
zones = readiness.get("buy_zones_90d", {})  # from trade_readiness
```
**Evidence — TFG in scan_results (line 91154):** `buy_zone.buy_zones` = only `{"50": 10.2}` (no 62). But `trade_readiness.buy_zones_90d` = `{"50": 9.4, "62": 9.92}`. `plan()` uses the 90d version → dashboard shows `entry50=9.4, entry62=9.92`. But the **scanner's own** `buy_zone` (from `scanner.py:buy_zone()`) only computed `{"50": 10.2}` (the 0.618 fib was dropped — see scanner.py line 211: `buy_zones = {k: v for k,v in fibs.items() if k in ("50", "62")}` — only keeps 50 and 62, but the fibs dict only has "50" because... let me check). Actually fibs always has both — but TFG buy_zone.buy_zones only shows 50. **This means the scanner's buy_zone() returned only one level**, which is a logic gap. The dashboard papered over it by using the 90d fib levels from trade_readiness instead.
**Impact:** Inconsistent entry-zone display: scanner says "entry at 10.2 (only 50% fib)", dashboard says "9.4–9.92 (both 50 and 62)".

---

#### M3. `change` field shows raw float for some "falling" group symbols
**Evidence from dashboard.html embedded data:**
- `VGI`: `change: -2.777777777777779` — full float precision shown instead of formatted. The `pct()` helper formats this, but `change` itself is raw. More importantly, some `falling` symbols show `change: 0.0` (literal float zero) while others show raw floats.
- The `card()` function uses `pct(i.change)` which does `Number(v).toFixed(2)` → displays correctly on card, **but the raw value is leaked** into the modal detail's `why` string and any JSON consumers.
**Impact:** Inconsistent data formatting — raw floats leak into presentation layer.

---

#### M4. `compute_rs_percentile` / `compute_rs_rating` — `market_close` type contract is unclear
**File:** `scanner.py:41-63`
- `compute_rs_rating` accepts `market_close: pd.Series` and indexes `market_close.iloc[-1]` / `.iloc[-RS_LOOKBACK]`.
- `compute_rs_percentile` accepts `rel_returns: pd.Series | list[float] | None`.
- But `screening.py:_universe_rs_ranks` (line 126) builds its own rank and **never calls** either function — it duplicates the percentile logic inline (lines 141, 350-351). So there are **three** RS implementations: old linear, new percentile in scanner.py, and inline-duplicated in screening.py.
**Impact:** Risk of drift; the "fixed" `compute_rs_percentile` is dead code for the production scan path.

---

### LOW

#### L1. `dashboard_server.py` sets `Access-Control-Allow-Origin: *` (CORS wildcard) for a private app
**File:** `backend/dashboard_server.py:35`
- The dashboard fetches from `:8000` (backend API). `app.py` CORS (line 40-50) correctly restricts origins. But `dashboard_server.py` sends `Access-Control-Allow-Origin: *` on **all** responses. Since the dashboard HTML itself is served by this same handler, any origin can embed it.
- Also: the handler has **no rate limit, no auth** — it's a raw `SimpleHTTPRequestHandler` serving the `backend/` directory. If `scan_results.json` contains data not yet surfaced, it's reachable at `/scan_results.json`.
**Recommendation:** Restrict ACAO to known origins; add basic auth or IP allowlist for the dashboard in production.

---

#### L2. `_publish_screen` hash does not include timestamp → daily re-scans dedupe to the same signal
**File:** `app.py:394-414`
```python
sig_hash = dedupe_hash({"type": "screen", "symbol": ..., "scan_time": result["scan_time"]})
```
- But `result["scan_time"]` is set in `screening.py:analyze_symbol_db` (line 241) using `dt.datetime.now(dt.timezone.utc).isoformat()`. If two daily scans happen within the same microsecond, they collide. More importantly, the hash includes `scan_time` so daily re-scans create **new** rows each day — fine — but there's no TTL/retention policy on the `signals` table, so it grows unbounded.
- **Minor:** the `/scan` endpoint publishes screen envelopes with `scan_time`, but `dedupe_hash` for `/webhook` (line 285) hashes the full payload. Inconsistent dedup granularity.

---

#### L3. `portal.html` `save()` sends empty symbols as "watch ALL" without re-confirmation if field is accidentally cleared
**File:** `backend/portal.html:160-161`
```python
if (!raw && !confirm('ล้าง watchlist ทั้งหมดและรับสัญญาณทุกหุ้น?')) return;
```
- This is acceptable UX, but the `removeSym()` function (line 177) calls `/me` then `/watch` separately — a **race window** exists: between the GET /me and POST /watch, another client could modify the watchlist, and `removeSym` would clobber that concurrent edit. No optimistic concurrency / version token.
**Impact:** Low (single-user Telegram model), but architecturally fragile for future multi-device.

---

## 3. Error State / Edge Case Coverage

| Scenario | Current behavior | Gap |
|----------|-----------------|-----|
| `/chart/{symbol}` missing symbol | 404 "no stored chart data" ✓ | Tested? No. No unit test for chart endpoint. |
| `/chart/{symbol}` invalid timeframe | 400 ✓ | ✓ |
| `/chart/{symbol}` with intraday but not daily | Returns intraday bars ✓ | No test. `draw()` canvas may crash if `bars` is empty or `levels` all filter out — `Math.min(...[])` = Infinity → NaN scaling. |
| `/me` for unregistered chat | Returns `exists: false` ✓ | No integration test. |
| `/watch` exceed free cap (6 symbols) | 400 with reason ✓ | `test_screening.py` doesn't test this. `users.py` has no test file. |
| `/register` with tier="paid" | 403 ✓ | No test. |
| `/portfolio/*` with wrong token | 403 ✓ | `test_portfolio.py` covers `require_owner_token` only. |
| Dashboard chart fetch fails (`fetch !res.ok`) | Clears canvas, shows "No stored data" ✓ | JS `loadChart` catch block is reasonable. |
| `build()` when `scan_results.json` missing | `open(SCAN_JSON)` → FileNotFoundError → crash in `/scan` push path (line 349-353 catches but logs). | **Dashboard build failure is silent** — `build_and_push_summary` catches and sets vcp_n from candiates, but `serialize`/`build` themselves don't have a fallback. |

---

## 4. Missing Tests (coverage gaps)

**Existing tests:**
- `test_screening.py` — 3 tests: `test_load_symbol`, `test_analyze_single`, `test_scan`. All require a live Postgres with SET data. No assertions on RS percentile fix, no mock-based unit tests.
- `test_portfolio.py` — ~10 unittest methods covering auth gates + parser normalization. Good, but **no tests for `persist_parsed`, `persist_manual_snapshot`, `_account_health_state` integration, `_build_attention` severity ranking**.

**Missing test modules (no test file):**
1. **`test_scanner.py`** — zero coverage of `scanner.py` (the Minervini conditions c1–c8, VCP detection, buy_zone fib logic, position_sizing edge cases, `trade_readiness` BUY/HOLD/OVERBOUGHT/BREAK decision tree).
2. **`test_build_dashboard.py`** — zero coverage of `determine_action`, `risk_metrics`, `plan`, `serialize`, `freshness_info`, `ath_quality_flag`, breadth/gauge math, and the **stale-vs-not stale** logic.
3. **`test_app.py`** — zero coverage of FastAPI endpoints (`/health`, `/scan`, `/screen/{symbol}`, `/chart/{symbol}`, `/register`, `/watch`, `/me`, `/tiers`, `/portfolio/*` auth gate).
4. **`test_delivery.py`** — zero coverage of `format_signal`, `deliver` routing + tier cap enforcement, alert counter increment/decrement logic, `push_telegram` no-op when token missing.
5. **`test_users.py`** — zero coverage of `set_watch` cap enforcement, `_normalize_symbols`, `_unknown_symbols`, `get_routing_map` watch-all detection, `public_registration_tier` admin-only gate.
6. **No test verifies scanner ↔ build_dashboard consistency** — i.e., that `serialize()` doesn't contradict `trade_readiness.status` (this is finding C2).

No `pytest.ini` / `pyproject.toml` / tox config exists; tests are run via `python test_screening.py` / `python -m unittest`. `test_screening.py` imports fail without a live DB (no mocks), so CI coverage is effectively zero in a clean environment.

---

## 5. Live UI Observations (from static HTML read)

Since browser automation was blocked by the gateway sandbox, the **served `dashboard.html`** (756 KB, read directly from `backend/dashboard.html`) was analyzed for the user-facing contract. The page served at `:3001/dashboard.html` matches this file.

**UI structure:**
- Topbar: brand "Signalix", freshness "Daily EOD · As of 11 Aug 2026" (static text baked at build time).
- Nav: Screener | Watchlist [0] | Market — 3 pages, JS-based show/hide via `.page.active`.
- Screener: search bar, 4 intent chips (All 866 | Opportunities 17 | Monitor 443 | Risk 406), group tabs (rendered dynamically), results grid with cards.
- Market: breadth gauge (26% Defensive), setup distribution bars (Opp 17 / Monitor 443 / Risk 406).
- Modal: detail view with canvas candlestick (requires `/chart/{symbol}` fetch to `:8000`).

**UI issues observed:**
- **Intent chip counts (17/443/406) are derived from the 866-symbol stale set** — they don't match `opportunity=139` (12+22+105 in scan_results), `monitor=669`, `risk=836`. Everything is ~halved. (See C1.)
- **Market health text is hardcoded**: `health = "Constructive"` is generated, but the paragraph reads "Defensive breadth: qualified opportunities..." — the word "Defensive" comes from `health == "Defensive"`, which is computed from `breadth = (opportunity + trend_leaders) / total * 100`. With stale 866-symbol data this computes differently than with the real 1796.
- **Gauge CSS** (line 308 in build_dashboard.py): `conic-gradient(var(--green) 0 {breadth*0.45}%, ...)` — the variable `breadth * .45` is interpolated into the f-string at build time. If breadth > 100/0.45 ≈ 222 the gradient wraps — but breadth is always ≤100 so OK. However the static CSS in the served file shows `26%` hardcoded: `conic-gradient(var(--green) 0 11.7%, var(--amber) 11.7% 26%, var(--red) 26% 100%)` — this is a frozen snapshot.
- **Watchlist count is "0"** — localStorage is per-device and the served HTML has no server-derived count. Clicking the star toggles `★`/`☆` locally; no sync unless `?chat=ID` is in URL.
- **No 404 page** for `/chart/{symbol}` canvas errors — `loadChart` catch shows inline text, acceptable.
- **No loading skeleton** for the chart canvas — flashes empty white on slow fetch.

---

## 6. Risk to Users

| Risk | Severity | Notes |
|------|----------|-------|
| Acting on stale prices (close 9.9 vs 10.0+) and halved group counts | CRITICAL | Especially for entry_now group with READY/BUY signal |
| Conflicting action labels (BUY vs READY) | CRITICAL | "Why this?" tooltip uses one engine, card action uses another |
| change% always null for opportunity group | CRITICAL | Can't assess momentum |
| 99,999-share position on 0.16 THB stock | HIGH | If consumed by a bot without guard |
| ATH disconnected from current price (21x–94x gaps) | MEDIUM | Correctly flagged via `ath_quality_flag`, but could surface more prominently |

---

## 7. Test Steps for Bee to Verify (Arm to execute)

**Reproducibility (data freshness mismatch):**
1. `cat backend/scan_results.json | python3 -c "import json,sys; d=json.load(sys.stdin); print({g:len(d['groups'][g]) for g in d['groups']})"` → expect ~1796 total
2. `grep -c '"symbol":"' backend/dashboard.html` → returns 866
3. `grep '"symbol":"TFG".*?"close"' backend/dashboard.html | head -1` → shows close=9.9; `grep 'line 91109'` context in scan_results → close=10.0
4. Re-run `python backend/build_dashboard.py` and confirm `dashboard.html` symbol count jumps to 1796.

**Reproducibility (decision-engine conflict):**
1. For TFG in scan_results `groups.entry_now`: `trade_readiness.status` = `"BUY"`.
2. In `build_dashboard.py:determine_action()` for `group="entry_now"`, close=10.0, entry50=10.2 (from buy_zone.buy_zones only-50) → 10.0 < 10.2 → **not in zone**. `near_buy_zone=true` → returns **READY**.
3. Confirm the modal "Why this?" string and card action both show READY while the canonical `trade_readiness.status` says BUY.

**Reproducibility (change=null bug):**
1. For any entry_now symbol with `priceSource:"15m stored"`: check embedded `change: null` persists after `snapshots()` — the guarded `if value.get("price_source") is None` branch is unreachable.

---

## 8. Sign-off

This is a review-only QA audit. No source files were modified. The findings above are ready for Bee → Arm review.
