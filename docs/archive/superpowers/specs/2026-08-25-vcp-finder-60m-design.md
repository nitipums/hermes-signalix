# Signalix VCP Finder 60m Design

**Status:** Approved by Arm for implementation

## Goal
Add an isolated deterministic 60-minute VCP candidate finder that scans every eligible Thai ORD symbol without changing the existing Daily scanner, stage/phase, or intraday evaluator.

## Boundaries
- Input: `intraday_price_data`, interval `60m`; no Daily fallback.
- Universe: `price_data.market='TH'`, eligible ORD instrument types, inactive/delisted `symbol_master` excluded; all remaining symbols return one result, including no-data/stale/insufficient symbols.
- Isolation: do not call `scanner.detect_vcp`, `screening.scan_universe`, Daily Trend Template/RS/MA200/readiness, or `intraday_evaluator.classify`.
- API: read-only `/api/vcp-finder?interval=60m&market=TH`; no writes to daily scan rows or `intraday_state`.
- Version: `signalix/vcp-finder-60m-v1`.

## Deterministic algorithm
1. Normalize UTC-aware timestamps, sort, deduplicate by timestamp keeping latest row, reject invalid OHLCV rows, exclude the latest possible in-progress bar from breakout confirmation, and expose data-quality evidence.
2. Require 80 valid bars. Use trailing 60 bars for structure, confirmed 2-left/2-right pivots, and Wilder ATR14.
3. Require prior local trend: close above EMA20, positive EMA20 slope, positive pre-base net return, and no recent structural breakdown.
4. Require alternating confirmed pivots `H0-L1-H1-L2-H2` minimum. Pullback depths must reduce by `<= previous * 0.85` at least twice; base depth 5%-35%; latest contraction `<=12%`; latest structural low must hold.
5. Volume is evidence, never a replacement for price structure. Leg average volumes must be non-increasing. Recent 5-bar average / previous 15-bar average `<=0.80` is dry-up. Missing/zero baseline is not verified. Breakout requires closed-bar close above `pivot*(1+max(0.5%,0.10*ATR/pivot))` and volume ratio `>=1.50`.
6. User-facing states: `NOT_VERIFIED`, `FORMING`, `NEAR_TRIGGER`, `READY`, `CONFIRMED`, `EXTENDED`, `FAILED`, `STALE`; `READY` is not a buy instruction.

## Contract
Top-level includes schema version, finder, interval, market, run_id, policy_version, as_of, universe counts, and results. Each result includes symbol, state, actionable, reason codes, bar/freshness/data-quality evidence, trend evidence, pivot/base/contraction evidence, volume evidence, breakout/invalidation levels, and provenance. All numeric values must be native JSON-safe Python types.

## Tests
Cover insufficient/no/stale data, invalid/duplicate rows, downtrend shrinking candles, flat range, lower highs, arbitrary equal-window false positive, wick-heavy bars, gaps, in-progress breakout, missing volume, breakout without volume, failed breakout, extended breakout, exact threshold boundaries, no-lookahead pivots, full-universe retention, deterministic replay, JSON serialization, and legacy isolation.
