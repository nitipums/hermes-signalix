# Chart Latency and 60m Feed Stabilization — 2026-08-25

> **STATUS: HISTORICAL** · Prior stable-candidate evidence; superseded as source authority by `Canonical-Source-of-Truth-2026-08-25.md`

## Chart latency

### Root cause

`mvp_chart_db.py` queried `price_data` with `UPPER(symbol)` but PostgreSQL had no matching functional index:

```text
before: Parallel Seq Scan
rows filtered: ~1.57M
DB execution: ~2.05s
API first request: ~3–5s
```

### Fix

Added migration:

```text
backend/migrations/005_price_data_chart_index.sql
price_data_th_ord_upper_symbol_date_idx
(market, instrument_type, upper(symbol), date DESC)
```

Also added a bounded process-local PostgreSQL connection pool for chart requests.

### Verification

```text
EXPLAIN: Index Scan
DB execution: ~6ms
live chart API: ~0.47–0.63s first request
candles: 250
```

Browser drawer:

```text
canvas: visible
placeholder: hidden
console errors: 0
```

## 60m feed policy

### Root cause

Settrade returned empty responses for a persistent tail. The old policy waited for three failures and could re-attempt symbols repeatedly; successful-symbol reset logic could also clear cooldown state.

### Owner policy applied

```text
Settrade empty response
→ status=unavailable
→ cooldown=24h
→ do not retry next run
→ keep symbol in Daily/EOD universe
→ 60m remains NOT_VERIFIED for that symbol
```

Confirmed empty symbols: 18

```text
ACAP BLISS CIMBT CV GLAND GSTEEL KKC KWI LRH NFC NWR PICO ROH TAPAC TR TSR TTCL WELL
```

### Verification

```text
active ORD master: 931
60m eligible after cooldown: 913
latest run status: full_success
attempted: 913
succeeded: 913
failed: 0
```

## Evaluator legacy dependency fix

`intraday_evaluator.py` previously read `scan_results.json`. It now reads the latest canonical `daily_scan_observations.raw_payload` for exactly one latest production Daily run.

```text
evaluator rows: 904
priced: 889
legacy scan_results dependency: removed
```

## Runtime

```text
dashboard: healthy
backend: healthy
postgres: healthy
redis: healthy
delivery: healthy
MVP API: HTTP 200
```

## MVP follow-up acceptance — `595eb49`

- Explorer Stage/Search filters apply immediately; no Apply button remains.
- Chart controls and indicator values moved below the plot so they do not cover candles.
- `1D` Daily, `1W` aggregate Daily, and `60M` stored intraday chart responses return HTTP 200 with candles; retired `15M` returns HTTP 400.
- Mobile drawer browser review passed with candlestick, volume, MA, RSI, scroll, and no horizontal overflow.
- Rapid Day→Week→Hour→Day chart switching passed with final-state request guard; no stale response overwrote the selected timeframe.
- During a timeframe request, the last-good chart remains visible until the new response arrives; unavailable 60m then transitions to explicit state.
- Unavailable 60m feed returns explicit `60m unavailable · Daily EOD remains the decision source`; it does not silently blank the chart.
- Mobile chart/filter controls are 44px touch targets.
- Full release-candidate suite: 249 passed.

No Daily symbols or historical data were deleted. Only feed-status cooldown rows and the chart index were changed.
