# Signalix Layer 2 (Grouping) + Independence Filter — Design Spec

**Date:** 2026-08-17
**Author:** บี (Bee) for พี่อาร์ม / Arm (Nitipum.s)
**Status:** Approved (design), pending implementation plan

## 1. Goal

Extend the Signalix screening with two non-scoring layers that help group and
filter the full ORD universe (Layer 1 stage scan already runs on every symbol):

- **Layer 2 — short-term momentum grouping** (60m window): classify each symbol
  into a short-term momentum group using 3 indicators computed on 60m bars.
  **No scoring in this round** — grouping + signals only.
- **Independence Filter** (separate axis, not a stage): metadata used by the UI
  to filter on liquidity / index membership / price band. Does NOT remove
  symbols from the scan (Layer 1 must still see every ORD).

Layer 3 (qualifiers: breakout volume, 52wk break, ATH break) is left as an
empty placeholder slot for a future round.

## 2. Non-goals (explicitly out of scope this round)

- Any composite / weighted score, tier (A/B/C), or "cream of cream" ranking.
- Layer 3 qualifier logic (slots only).
- UI redesign — only new JSON fields + a small text badge in existing cards.
- SET50 fetched live from the web (hardcoded list in a new table instead).

## 3. Architecture

### 3.1 New DB table `index_membership`

```sql
CREATE TABLE IF NOT EXISTS index_membership (
    symbol      TEXT PRIMARY KEY,
    index_name  TEXT NOT NULL,          -- 'SET50', 'SET100', ...
    is_set50    BOOLEAN NOT NULL DEFAULT FALSE,
    effective_from DATE,
    source      TEXT,
    fetched_at  TIMESTAMPTZ DEFAULT NOW()
);
```

Seed: hardcoded SET50 (50 symbols, H1-2026 review) inserted via an idempotent
upsert. Source field = 'hardcoded-2026H1'. This table is the single source of
truth for `is_set50`; no web fetch this round.

### 3.2 `screening.py` additions

`compute_layer2(symbol, df_60m) -> dict`
- Input: 60m OHLCV DataFrame (from `load_symbol_intraday(symbol, interval='60m')`).
- Returns:
  ```python
  {
    "signals": {
        "mini_trend": "up" | "down" | "flat",   # 60m close vs MA20/MA50 slope
        "macd": "bullish" | "bearish" | "cross", # MACD(12,26,9) on 60m
        "rsi": float,                             # RSI(14) on 60m, 0-100
    },
    "group": "momentum_up" | "momentum_strong" | "neutral"
            | "momentum_down" | "overbought" | "oversold",
  }
  ```
- `mini_trend`: up if close > MA50_60m and MA50 slope > 0; down if close < MA50
  and slope < 0; else flat. (Reuses the existing MA logic, 60m bars.)
- `macd`: standard MACD on 60m; bullish = macd > signal & > 0; bearish = opposite;
  cross = macd crossed signal recently (sign change).
- `rsi`: standard RSI(14) on 60m close.
- `group` mapping (illustrative, deterministic):
  - rsi >= 70 -> "overbought"
  - rsi <= 30 -> "oversold"
  - mini_trend up & macd bullish -> "momentum_strong"
  - mini_trend up -> "momentum_up"
  - mini_trend down -> "momentum_down"
  - else -> "neutral"

`universe_layer2(pg, symbols) -> dict[str, dict]`
- Batch: for each symbol load 60m df, call `compute_layer2`, return map.
- Symbols lacking 60m data -> skipped (absent from map; UI shows "—").

`is_set50(symbol, pg) -> bool` / `load_index_membership(pg) -> set[str]`
- Reads `index_membership` where `is_set50 = TRUE`.

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
- Compute `layer2` + `independence` per symbol and pass into `serialize`.
- **Secondary sort:** within each stage section, sort by `layer2_group` priority
  (momentum_strong > momentum_up > neutral > momentum_down > overbought/oversold)
  then by existing `rs` descending (preserves current order as tiebreak).
  This replaces the prior "sort by rs only" inside groups.

### 3.4 UI text badge (no redesign)

Card shows: `S2 · L2: momentum_strong` when `layer2_group` present, using the
existing `stage_phase` label area. No new layout, no new columns.

## 4. Data flow

```
/scan -> screening.scan_universe -> analyze_symbol_db (L1 stage) -> group_scan_results
build(scanned):
  snapshots(pg)            # EOD + 60m overlay (existing)
  universe_layer2(pg, syms)# NEW 60m indicators
  load_index_membership(pg)# NEW SET50 set
  serialize(..., layer2, indep)  # NEW fields
  sort by (stage, layer2_group, rs)
  apply_projection -> dashboard_snapshot.json + dashboard.html
```

## 5. Error handling

- Missing 60m data for a symbol -> `layer2` absent, badge shows "—", no crash.
- `index_membership` empty -> `is_set50` always False (seed idempotent on deploy).
- All new code path-wrapped so a Layer 2 failure never blocks the L1 dashboard.

## 6. Testing

- `test_layer2_grouping.py`:
  - `compute_layer2` on a known 60m df yields valid signals + group in enum.
  - `group` enum stays within the 6 allowed values.
  - `universe_layer2` skips symbols without 60m (no KeyError).
  - `load_index_membership` returns the seeded SET50 set after seed.
- `test_independence_filter.py`:
  - `is_set50` True for a seeded symbol, False otherwise.
  - `passesValueFilter` True/False at the 5M boundary.
  - `priceBand` thresholds (<2 / 2-10 / >10).
- Extend `build()` smoke test: serialized items contain `layer2_group`,
  `independence`, `layer3_qualifiers` keys; secondary sort order verified on a
  tiny fixture.

## 7. Files touched

- `backend/screening.py` — `compute_layer2`, `universe_layer2`, `load_index_membership`
- `backend/build_dashboard.py` — `serialize` (new fields), `build` (batch + sort)
- `backend/migrations/002_index_membership.sql` — table + SET50 seed
- `backend/test_layer2_grouping.py` (new)
- `backend/test_independence_filter.py` (new)

## 8. Deployment

1. Apply migration (create table + seed SET50).
2. `docker compose up -d --force-recreate backend`.
3. Trigger `/scan?push=false`, verify snapshot items carry the new fields and
   excluded (delisted/inactive) symbols remain absent (280 excluded).

## 9. Open questions for future rounds

- Layer 3 qualifier logic (breakout volume / 52wk break / ATH break).
- Independence filter UI controls (toggle SET50-only, value slider).
- Composite scoring once L2/L3 are stable.
