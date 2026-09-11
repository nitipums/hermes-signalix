# Signalix Private Actionable Signal Contract

> **STATUS: OWNER-APPROVED DIRECTION — PHASE 1 SOURCE IMPLEMENTED; RUNTIME/REPLAY NOT VERIFIED**
> **Approved:** 2026-09-11
> **Scope:** private, long-only Thai-equity market-buy shadow signals for Arm
> **Authority:** supersedes the prior rule that Signalix may never emit an actionable label; it does not authorize alerts, broker orders, or automatic execution.

## 1. Product decision

Signalix will become Arm's private buy/sell signal provider. The system may emit
explicit `BUY_NOW` and `SELL_NOW` decisions when a named deterministic policy
passes every required gate. The signal is a decision-support instruction for
Arm's own review and action, not a public recommendation, guarantee, or broker
order.

Phase 1 is a visible paper/shadow market-buy UI. It answers which symbols would
have received `BUY_NOW` during the trailing seven calendar days, without
requiring portfolio data, sending alerts, or submitting an order. Portfolio-aware
hold/reduce/sell decisions remain a later layer because they depend on actual
positions. Broker execution remains a separate future promotion.

## 2. Canonical signal states

```text
BUY_NOW
BUY_ON_TRIGGER
HOLD
REDUCE
SELL_NOW
WAIT
AVOID
DATA_BLOCKED
```

- `BUY_NOW`: no known open position; the completed 60m trigger is confirmed;
  Daily and 60m evidence are fresh; Wave/trend/setup/risk gates pass; current
  price remains in the entry zone; target-1 R:R is at least 2:1.
- `BUY_ON_TRIGGER`: the same thesis has a complete reviewable plan, but the
  completed 60m trigger is not confirmed yet.
- `HOLD`: a known long position exists and no deterministic exit rule fires.
- `REDUCE`: a known long position has reached target 1. Phase 1 does not infer a
  quantity to sell.
- `SELL_NOW`: a known long position has crossed a numeric trade stop or a
  supplied monotonic trailing stop. Phase 1 protective exits take precedence
  over profit-taking.
- `WAIT` / `AVOID`: no open position and the canonical setup layer is not ready
  or rejects a new entry.
- `DATA_BLOCKED`: required market or setup evidence is missing, stale,
  inconsistent, or outside the canonical signal universe.

Every state is informational until Arm acts. Phase 1 never emits order side,
quantity, order type, or an execution payload.

## 3. Inputs and timeframe boundaries

The Phase 1 market-buy policy rebuilds canonical setup candidates at each
completed market-session boundary in the trailing seven calendar days.

- Daily remains authoritative for trend, primary Wave, and thesis invalidation.
- Completed 60m remains authoritative for trigger confirmation and trade stop.
- Market-wide `BUY_NOW` discovery does not require portfolio state. It answers
  what passed the entry policy, not whether Arm should add exposure or position
  size in a specific account.
- Portfolio state is required only for later `HOLD`, `REDUCE`, and `SELL_NOW`
  decisions and must not block the market-buy shadow list.
- Numeric fields are never recovered from display strings. Invalid prices,
  stops, targets, entry zones, or R:R fail closed.

## 4. Confidence contract

Phase 1 confidence is an explainable evidence score, not a win probability.

```text
kind: EVIDENCE_SCORE
score: 0..100
label: HIGH | MEDIUM | LOW
calibration_status: NOT_CALIBRATED
calibrated_probability: null
policy_version: private-actionable-signals-v0.1-shadow
```

The score is composed from named observations: freshness, canonical lane,
trigger state, Wave confidence, trend state, target-1 R:R, and entry-zone
position. `BUY_NOW` requires all hard gates and an evidence score of at least
80. A high score cannot override any failed hard gate.

Historical no-lookahead replay and live shadow outcomes are required before a
later policy may expose a calibrated probability. LLM output cannot calculate,
promote, or override a signal or confidence value.

## 5. Later position-aware exit precedence

For a known long position:

```text
stale/missing evidence
→ DATA_BLOCKED
→ price <= trade_stop or trailing_stop
→ SELL_NOW
→ price >= target_1
→ REDUCE
→ HOLD
```

Daily thesis invalidation, target-2/full-exit rules, gap-through handling,
position sizing, fees/slippage, and structural trailing-stop generation remain
explicit next-policy decisions. They must not be hidden defaults in Phase 1.

## 6. Private shadow UI and compatibility

Phase 1 adds a visible `Shadow Buy Signals · 7D` tab under `/mvp`, backed by an
token-free, read-only replay endpoint:

```text
GET /api/shadow-buy-signals?days=7
```

The endpoint evaluates each completed Thai market session in the trailing seven
calendar days with explicit Daily and completed-60m as-of boundaries,
deduplicates repeated observations of the same setup plan, and returns only
`BUY_NOW` events. The UI shows signal dates, price, trigger, stop, target 1,
R:R, evidence confidence, evaluated coverage, and an honest empty/error state.

`/api/setup-candidates` remains unchanged. The new tab is an additive private
shadow surface and does not change candidate lanes or calculations.

## 7. Acceptance gates

Source acceptance requires tests proving:

- confirmed, fresh, coherent, non-extended setup -> `BUY_NOW`;
- pre-trigger setup -> `BUY_ON_TRIGGER`;
- stale or missing market inputs -> `DATA_BLOCKED`;
- the replay uses each session's point-in-time Daily/60m boundary with no
  lookahead and covers only the trailing seven calendar days;
- repeated daily observations of one unchanged plan are deduplicated while
  preserving first/latest signal timestamps;
- the shadow UI is visible, readable at 390px, and runs without a token;
- confidence states explicitly remain uncalibrated;
- no order, quantity, alert, Redis publish, or database write occurs.

Runtime, shadow-replay, browser, and outcome-calibration gates remain
`NOT VERIFIED` until separately executed and recorded.

## 8. Non-goals

- Public signal distribution or personalized advice for other users
- Automatic alerts or Telegram delivery
- Broker integration or order submission
- Short selling, TFEX, options, crypto, or non-Thai markets
- Position-aware hold/sell decisions, sizing, or portfolio allocation without
  an approved position/risk contract
- Claims of accuracy, certainty, expected return, or calibrated win rate
