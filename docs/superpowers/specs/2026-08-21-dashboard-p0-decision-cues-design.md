# Signalix Dashboard P0 Decision Cues

## Goal
Improve the first-viewport decision speed for Radar and the screener without adding new scan logic or changing the full ORD universe contract.

## Scope
1. Add a compact Market Posture card to the top of the screener control area.
2. Add trigger distance to the stock card when a valid breakout trigger exists.
3. Improve Radar and screener empty states so zero results is distinct from a data/load failure.
4. Add focused source-contract tests and verify the served generated dashboard at desktop and 512px mobile widths.

Out of scope: pattern classifiers (VCP/Cup & Handle), volume-dry-up classification, account watchlist sync, alerts, risk-sizing assistant, and skeleton-loader redesign.

## Market Posture contract

The posture is context, not a trade instruction. It uses only fields already present in the serialized snapshot:

- Stage breadth: `S1_basing + S2_uptrend` versus `S3_distributing + S4_down`.
- MA200 breadth: percentage of items with numeric `close` and positive numeric `ma200` where `close > ma200`.

Eligibility is explicit. If no valid MA200 values exist, the UI must show `MA200 breadth unavailable` and must not invent a posture from that missing metric.

Posture thresholds (both conditions must hold):

- `Favorable`: constructive stage breadth >= 55% and MA200 breadth >= 50%.
- `Defensive`: constructive stage breadth < 40% or MA200 breadth < 35%.
- `Mixed`: all other cases.

When MA200 breadth is unavailable, posture is `Mixed` with an unavailable metric note. The card shows the two component percentages and a short methodology label.

## Trigger distance contract

For each card, when `breakoutEvidence.trigger` and `close` are finite and trigger > 0:

`distance_pct = (close - trigger) / trigger * 100`

Display a compact line:

- `Trigger ฿X · -Y.Y%` when below trigger.
- `Trigger ฿X · +Y.Y%` when at/above trigger.

Use the existing `breakoutEvidence` object; do not infer or invent a trigger. If unavailable, omit the line. On Radar, this line is especially important and remains compact enough for 512px screens.

## Empty/error contract

- Zero eligible cards after a valid render: show an explanatory empty state with the active context and a reset/action hint where applicable.
- Snapshot/API load failure: preserve the existing error state and retry action; never replace it with a market-condition explanation.
- Existing subgroup reset controls remain available when a subgroup is empty.

## Compatibility and safety

- Preserve Stage-first navigation, Radar page, proximity filters, watchlist LocalStorage behavior, modal/chart behavior, and all existing fields.
- UI-only implementation is preferred because the required snapshot fields already exist. No changes to `app.py` or `build_dashboard.py` unless verification proves a missing contract.
- Do not modify or stage pre-existing dirty files unrelated to this task.

## Acceptance tests

- Template tests cover posture IDs, threshold logic, MA200-unavailable handling, trigger-distance formatting, and empty/error markers.
- Existing dashboard responsive and browser acceptance tests pass (or failures are labeled pre-existing/unrelated).
- Generated `dashboard.html` is newer than the template and served content contains the new markers.
- Desktop and 512px mobile render without page-level horizontal overflow.
- Radar card visibly shows Trigger distance for cards with valid evidence.
