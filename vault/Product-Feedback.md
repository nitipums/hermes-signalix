# Signalix Product Feedback

Curated product/user-testing feedback for Signalix.

## Rules
- This file stores durable product feedback, not raw chat transcripts.
- Mali may write beginner/user-tester feedback here.
- Keep feedback actionable: what was confusing, why it matters, suggested fix.
- Do not store secrets, tokens, API keys, or `.env` contents.

## Feedback Log

## Intraday Dashboard User Feedback — 2026-08-13

### What Arm asked for
- Remove 15m; one 60m view should include the open/current candle and update during the session.
- Daily, weekly, and monthly charts should visibly roll a current provisional candle like TradingView.
- Cards should favor actionable liquid names: volume, trade value, cash/% change, same-time volume surge, and Top Gainers; default-filter low-value names.
- Detail must have company/business identity, core basics above setup metrics, 52W/ATH, MACD, one Fib 161 target, MA10/20/50/200, and a more readable `Why this?` explanation.
- Mobile typography/detail controls must be easy to read; chart should have a distinct volume pane.
- Dashboard needs visible frequent refresh/retry state instead of silently appearing frozen.

### Product lessons
1. Do not treat `>=5x` volume alone as meaningful: tiny prior-session denominator caused visual false positives. Require liquid value and meaningful current cumulative volume.
2. Distinguish chart timeframe from price source. A Daily chart can have a stored 60m current quote; provenance must remain visible.
3. Do not copy dense TradingView Fibonacci overlays. Keep Signalix chart hierarchy: price first, volume separate, then only decision-relevant Entry/Support/Risk/Resistance.
4. `ATH` must mean full available archive, while `52W` means 252 recent sessions; show history/provenance in a later polish pass.
5. UI acceptance cannot stop at API/backend success. Inspect served HTML/JS and use a true mobile visual test when browser infrastructure is repaired.

### Open tester checks
- Mobile: open detail → change 1M/1W/1D/60m → scroll detail → close; ensure sticky header and no clipped/overlapping company summary.
- Failure state: simulate chart 404/API snapshot timeout; verify clear error/retry copy and retained last-good cards.
- Filter: verify low-value toggle affects all cards and Top Gainers, without hiding Watchlist unexpectedly.
- Check profile fallback for symbols without cached metadata: must show `Company profile pending`, not blank/broken layout.

