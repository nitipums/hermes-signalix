# Signalix Layer 2 (Grouping) + Independence Filter + UI Redesign — Design Spec

**Date:** 2026-08-17
**Author:** บี (Bee) for พี่อาร์ม / Arm (Nitipum.s)
**Status:** Approved (design v2 — added UI redesign + live SET50 fetch)

## 1. Goal

Extend the Signalix screening with two non-scoring layers that help group and
filter the full ORD universe (Layer 1 stage scan already runs on every symbol),
plus a dashboard UI refresh that exposes those layers.

- **Layer 2 — short-term momentum grouping** (60m window): classify each symbol
  into a short-term momentum group using 3 indicators computed on 60m bars.
  **No scoring in this round** — grouping + signals only.
- **Independence Filter** (separate axis, not a stage): metadata used by the UI
  to filter on liquidity / index membership / price band. Does NOT remove
  symbols from the scan (Layer 1 must still see every ORD).
- **UI Redesign (additive):** keep the existing stage-first (S1–S4) layout; add a
  **filter bar** (SET50 / value / price band) and **colored L2-group badges** on
  cards. No full re-architecture of the dashboard.

Layer 3 (qualifiers: breakout volume, 52wk break, ATH break) is left as an
empty placeholder slot for a future round.

## 2. Non-goals (explicitly out of scope this round)

- Any composite / weighted score, tier (A/B/C), or "cream of cream" ranking.
- Layer 3 qualifier logic (slots only).
- Live/recurring SET50 refresh — fetch is a **one-shot** seed only.
- Full dashboard re-architecture (new route/views). We keep stage-first.

## 3. Architecture

### 3.1 New DB table `index_membership`

```sql
CREATE TABLE IF NOT EXISTS index_membership (
    symbol         TEXT PRIMARY KEY,
    index_name     TEXT NOT NULL,          -- 'SET50', 'SET100', ...
    is_set50       BOOLEAN NOT NULL DEFAULT FALSE,
    effective_from DATE,
    source         TEXT,
    fetched_at     TIMESTAMPTZ DEFAULT NOW()
);
```

Seeded by a **one-shot** script (see 3.5). No daily cron.

### 3.2 `screening.py` additions

`compute_layer2(symbol, df_60m) -> dict`
- Input: 60m OHLCV DataFrame (from `load_symbol_intraday(symbol, interval='60m')`).
- Returns:
  ```python
  {
    "signals": {
        "mini_trend": "up" | "down" | "flat",   # 60m close vs MA50_60m + slope
        "macd": "bullish" | "bearish" | "cross", # MACD(12,26,9) on 60m
        "rsi": float,                             # RSI(14) on 60m, 0-100
    },
    "group": "momentum_up" | "momentum_strong" | "neutral"
            | "momentum_down" | "overbought" | "oversold",
  }
  ```
- `mini_trend`: up if close > MA50_60m and MA50 slope > 0; down if close < MA50
  and slope < 0; else flat.
- `macd`: standard MACD on 60m; bullish = macd > signal & > 0; bearish = opposite;
  cross = sign change of (macd - signal) on the last bar.
- `rsi`: standard RSI(14) on 60m close.
- `group` mapping (deterministic):
  - rsi >= 70 -> "overbought"
  - rsi <= 30 -> "oversold"
  - mini_trend up & macd bullish -> "momentum_strong"
  - mini_trend up -> "momentum_up"
  - mini_trend down -> "momentum_down"
  - else -> "neutral"

`universe_layer2(pg, symbols) -> dict[str, dict]`
- Batch: for each symbol load 60m df, call `compute_layer2`, return map.
- Symbols lacking 60m data -> skipped (absent from map; UI shows "—").

`load_index_membership(pg) -> set[str]`
- Reads `index_membership` where `is_set50 = TRUE`. Returns the SET50 symbol set.

### 3.3 `build_dashboard.py` changes

`serialize(...)` adds to each card item:
```python
"layer1_stage": stage or "S1_basing",          # alias of existing stage
"layer2_signals": layer2.get("signals", {}),     # {} if absent
"layer2_group": layer2.get("group"),            # None if absent
"independence": {
    "is_set50": bool,
    "avgTradeValue20": number(snapshot.get("avgDailyValue20"), 0),
    "priceBand": "low" | "mid" | "high" | None,  # close<2 low, 2-10 mid, >10 high
    "passesValueFilter": bool,                   # avgTradeValue20 >= 5_000_000
},
"layer3_qualifiers": {},                          # placeholder, empty this round
```

`build(scanned)`:
- After `snapshots(...)`, call `universe_layer2(pg, [symbols])` and
  `load_index_membership(pg)`.
- Compute `layer2` + `independence` per symbol, pass into `serialize`.
- **Secondary sort:** within each stage section, sort by `layer2_group` priority
  (momentum_strong > momentum_up > neutral > momentum_down > overbought/oversold)
  then by existing `rs` descending (tiebreak, preserves current order).
  Replaces the prior "sort by rs only" inside groups.

### 3.4 UI Redesign (additive, stage-first preserved)

`dashboard_template.html` changes:
1. **Filter bar** (top, above stage sections): three controls, all client-side
   over the already-loaded `ITEMS__` JSON:
   - **SET50 toggle**: show SET50 only.
   - **Value filter**: dropdown `All / >=5M / >=10M / >=20M` on `avgTradeValue20`.
   - **Price band**: `All / low(<2) / mid(2-10) / high(>10)`.
   - Filtering recomputes visible cards without a server round-trip.
2. **L2 badge** on each card: colored pill showing `layer2_group`
   (green=momentum_strong/up, grey=neutral, red=momentum_down/oversold,
   orange=overbought). Badge hidden when `layer2_group` is null.
3. **Card sub-line**: `S2 · L2: momentum_strong` reuses the existing
   `stage_phase` label area; no new layout columns.

No modal/chart changes (those are stable per signalix-stage-first-dashboard).

### 3.5 SET50 one-shot fetch

`fetch_set50.py` (run once at deploy, never scheduled):
- Fetches the official SET50 constituents page
  (`https://www.set.or.th/en/market/information/securities-list/constituents-list-set50-set100`)
  and parses the 50 symbols (browser or curl; fall back to the 48-dir list under
  `/root/set50_financials/` if the page is unparseable).
- Upserts rows into `index_membership` with `index_name='SET50'`,
  `is_set50=TRUE`, `source='set.or.th-2026H1'`, `effective_from=<run date>`.
- Idempotent: re-running just refreshes the set (no dupes, no daily loop).
- **Owner rule:** only re-run manually when SET revises the index (≈ semi-annual).

## 4. Data flow

```
[deploy once] fetch_set50.py -> index_membership (SET50 set)
/scan -> screening.scan_universe -> analyze_symbol_db (L1 stage) -> group_scan_results
build(scanned):
  snapshots(pg)             # EOD + 60m overlay (existing)
  universe_layer2(pg, syms) # NEW 60m indicators
  load_index_membership(pg) # NEW SET50 set
  serialize(..., layer2, indep)  # NEW fields
  sort by (stage, layer2_group, rs)
  apply_projection -> dashboard_snapshot.json + dashboard.html (NEW filter bar + L2 badge)
```

## 5. Error handling

- Missing 60m data -> `layer2` absent, badge "—", no crash.
- `index_membership` empty -> `is_set50` always False; fetch script logs a warn
  and the 48-dir fallback seeds what it can.
- SET50 page unparseable -> fallback to local `/root/set50_financials` dirs.
- All new code path-wrapped so a Layer 2 failure never blocks the L1 dashboard.

## 6. Testing

- `test_layer2_grouping.py`:
  - `compute_layer2` on a known 60m df yields valid signals + group in enum.
  - `group` enum stays within the 6 allowed values.
  - `universe_layer2` skips symbols without 60m (no KeyError).
- `test_independence_filter.py`:
  - `load_index_membership` returns the seeded SET50 set after `fetch_set50.py`.
  - `passesValueFilter` True/False at the 5M boundary.
  - `priceBand` thresholds (<2 / 2-10 / >10).
- `test_fetch_set50.py`: script populates `index_membership` with ~50 rows;
  idempotent re-run does not duplicate.
- `build()` smoke test: serialized items contain `layer2_group`, `independence`,
  `layer3_qualifiers`; secondary sort order verified on a tiny fixture;
  `dashboard_template.html` still contains required Modal CSS (`.modal-bg.open`).

## 7. Files touched

- `backend/screening.py` — `compute_layer2`, `universe_layer2`, `load_index_membership`
- `backend/build_dashboard.py` — `serialize` (new fields), `build` (batch + sort)
- `backend/fetch_set50.py` (new, one-shot)
- `backend/migrations/002_index_membership.sql` — table + (empty; seeded by script)
- `backend/dashboard_template.html` — filter bar + L2 badge (additive)
- `backend/test_layer2_grouping.py` (new)
- `backend/test_independence_filter.py` (new)
- `backend/test_fetch_set50.py` (new)

## 8. Deployment

1. Apply migration (create table).
2. Run `fetch_set50.py` once (seeds SET50).
3. `docker compose up -d --force-recreate backend`.
4. Trigger `/scan?push=false`, verify snapshot items carry the new fields and
   excluded (delisted/inactive) symbols remain absent (280 excluded).
5. Browser: open dashboard, confirm filter bar works (SET50/value/price) and L2
   badges render with correct colors.

## 9. Open questions for future rounds

- Layer 3 qualifier logic (breakout volume / 52wk break / ATH break).
- Independence filter UI controls persistence / saved views.
- Composite scoring once L2/L3 are stable.
