# Signalix Product Feedback

Curated product/user-testing feedback for Signalix.

## Rules
- This file stores durable product feedback, not raw chat transcripts.
- Retired profile `mali` no longer writes here. Keep existing observations as curated historical feedback.
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

### Resolved MVP checks — stable candidate `595eb49`
- Mobile detail: verified real drawer scroll, no horizontal overflow/overlap; timeframe controls are below the plot.
- Chart timeframes: `1D`, `1W`, and `60M` return real candles; retired `15M` returns HTTP 400.
- Explorer Stage/Search: filters apply immediately without an Apply button.
- Failure state: simulated shortlist API outage keeps the explicit error + Retry state and does not fall back to fixtures.

### Remaining tester checks
- Profile fallback for symbols without cached metadata: must show `Company profile pending`, not blank/broken layout.
- Verify 1M UI control when the owner wants monthly exposure; the MVP API already supports `1M` aggregation.

## User Validation Feedback — 2026-09-01 — TASCO / current release

### Arm's observations

- Top overview filters are not relevant to the review flow and consume too much vertical space; redesign the control area to be compact and smoother.
- The page appears to refresh by itself; investigate and avoid silent replacement of the user's current review set.
- Card hierarchy is weak; important decision evidence should be prominent and the card should be more compact with purposeful color.
- Target, R/R, sector, peers, and VCP should be available rather than blank; richer detail can remain in the drawer, but R/R should be visible on the card.
- Wave information is useful and should be more prominent. Explain `structure unknown` in user-facing language.
- Show RS with two digits.
- Make 52W high, all-time high, and breakout labels understandable.
- Observed semantic examples: KCE/IRPC/BCP appear Wave 3 continuation; RCL appears Wave 2 forming; BBGI appears tested/touching but not yet breaking through.
- A fresh/current intraday update can still produce `DATA_BLOCKED`; revisit the distinction between missing data and incomplete setup.
- Wave identification is difficult to follow; expose mapped evidence on 60m and Week where the mapping is explicit.
- Chart consistency needs a clear policy for an unclosed/current candle: if current data is shown, label it provisional and use the same as-of boundary across Day/Week/60m so the user does not see unexplained direction conflicts.

### Lite live probe

On 2026-09-01 at 18:12 Asia/Bangkok, the public canonical API returned TASCO with `daily_available=true`, `intraday_60m_available=true`, `intraday_60m_freshness=fresh`, but `daily_final_session_available=false`, `daily_freshness=stale`, `reason_code=STALE_DAILY_DATA`, and `decision_lane=DATA_BLOCKED`. The canonical validator treats `daily_final_session_available=false` as fail-closed `DATA_BLOCKED`; this is a contract decision to revisit, not proof that all underlying data is unavailable.

### Current gate

- UI usability feedback: **OPEN — needs compact overview/card redesign and refresh policy decision**.
- Data semantics: **REVISE — separate official Daily EOD availability from current-session provisional 60m data and setup readiness**.
- Wave semantics: **OWNER REVIEW REQUIRED — Arm's TASCO examples are validation evidence; do not change deterministic labels until the concept contract is agreed**.

