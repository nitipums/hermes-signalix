# Signalix Research Playbook Bible

> **STATUS: CURRENT RESEARCH AUTHORITY — PRODUCTION SEPARATE**
> **Last updated:** 2026-09-06 ICT
> **Owner/final gate:** Arm → Lite final quality gate
> **Index:** `Research-Index.md`
> **Scope:** deterministic Daily playbooks, AutoResearch, replay, portfolio evidence, and promotion gates.
>
> This bible records the current research formulas and their evidence status. It does **not** change `/api/setup-candidates`, `/mvp`, published Wave states, alerts, evaluator auto-caller, auto-trading, or broker execution.

## 1. Core research principle

The goal is not to find one universal formula. The goal is to identify playbook-specific deterministic policies that remain useful across declared eras, symbol folds, holdout, cost stress, portfolio replay, and chart review.

```text
Market data snapshot
→ immutable event/evaluator contract
→ playbook-specific policy
→ train/validation selection
→ locked holdout
→ portfolio replay
→ visual chart review
→ SHADOW_READY gate
→ Arm promotion decision
```

Wave labels and playbook outputs are machine-generated candidate/evidence for Arm review. They are not Elliott truth, personalized advice, or executable orders.

## 2. Non-negotiable boundaries

- Daily OHLCV is the research timeframe for these playbooks.
- Confirmed pivots require right-hand confirmation; no look-ahead.
- Entry, stop, target, outcome ordering, same-bar ambiguity, and 120-bar horizon are evaluator semantics, not tuning knobs.
- `TARGET_BELOW_ENTRY`, `AMBIGUOUS_SAME_BAR`, `EXPIRED`, and `INSUFFICIENT_FUTURE_DATA` remain separate statuses.
- Valid decided outcomes for expectancy/win rate are `TARGET` and `STOP` only.
- Cost axes are evaluator axes; targets are evaluation axes only:
  - costs: `0 / 25 / 50 bps`;
  - target multiples: `2.5 / 3 / 3.5 / 4 / 5R`.
- Holdout cannot rank, tune, threshold-select, or mutate a policy.
- Current 237 retrospective, active ORD audit, and broad historical data-available scopes must never be pooled.
- Research evidence is not production evidence until portfolio, cost, chart, shadow, and owner gates pass.

## 3. Playbook formula bible

### 3.1 `WAVE2_CONTINUATION`

#### Event definition

```text
Confirmed Wave-2 pivot
→ pivot survives
→ post-pivot rebound
→ minor high
→ higher low
→ close breakout above minor high
→ continuation entry
```

Entry-time R:R is recalculated at the minor-high breakout. Pivot-day R:R must not be reused.

#### Best current research candidate

```text
Structural event: WAVE2_CONTINUATION
Filters:
  MA20 > MA50
  MA20 slope >= 0
  RSI14 >= 65
Policy name: marsi_65_0
```

Time×symbol evidence:

```text
accepted events:       733
median stress-50 rate: 55.84%
positive cells:        10 / 12
worst cell:            40.00%
top-symbol share:       1.77%
```

#### Status

`PROMISING / RESEARCH_ONLY`.

`marsi_65_-0.1` had the strongest validation result in one campaign (`56.06%`) but fell to `47.66%` on holdout and `44.17%` at 50 bps stress. Treat it as an overfit finding, not the champion.

#### Required next work

- Wire and test structural policy overrides before additional tuning.
- Preserve the immutable baseline and prior-best comparator.
- Run corrected 5/10-cycle policy replay with locked train/validation/holdout.
- Run portfolio replay, cost stress, and event chart review.

### 3.2 `52W_HIGH_BREAKOUT`

#### Event definition

```text
Close > prior 252/260 trading-day high
+ declared volume rule
+ declared entry semantics
+ ATR14/structural stop
```

Signal bar and execution bar remain separate. Same-day-close and next-day-open populations are never pooled.

#### Best current research candidate

```text
Lookback:              252 trading days
Breakout volume:       >= 1.25 × prior 20-day average
Entry:                 same-day close
ATR period:            14
ATR stop buffer:       1.00
Policy name:           52W-C2
```

#### Status

`PROMISING / RESEARCH_ONLY`; strongest broad-universe baseline candidate so far.

The current 237 replay run was a **baseline** 52W replay, not a verified `52W-C2` tuned replay. Do not attribute the baseline result to C2.

#### Required next work

- Implement and verify the corrected 52W policy schema.
- Keep 252/260, same-close/next-open, signal/entry dates, ATR14, and stop geometry auditable.
- Run C2 on current 237 and broad scopes separately.
- Add fees/slippage, portfolio replay, and visual chart review.

### 3.3 `WAVE1_PICKUP`

#### Event hypothesis

```text
a down-leg/base
→ rebound high
→ higher low
→ close breakout
```

The “Wave 5 completed” interpretation is evidence only, never truth.

#### Status

`CUT / AUDIT_ONLY`.

The baseline showed negative holdout expectancy across target axes. Do not rescue it with arbitrary threshold search. Re-entry requires a separately justified structural definition and a new pre-registered hypothesis.

### 3.4 `WAVE3_CONTINUATION`

#### Event hypothesis

```text
Prior impulse
→ Wave-2-like retracement
→ pivot hold
→ higher low
→ close above impulse/internal continuation high
```

#### Best current research candidate

```text
Structural event: WAVE3_CONTINUATION
Filters:
  MA20 > MA50
  MA20 slope >= 0
  RSI14 >= 65
Policy name: marsi_65_0
```

Time×symbol evidence is directionally promising but not a promotion result:

```text
accepted events:       733
median stress-50 rate: 55.84%
positive cells:        10 / 12
worst cell:            40.00%
top-symbol share:       1.77%
```

#### Status

`EXPLORATORY / RESEARCH_ONLY`.

Structural overrides and MACD/volume cycles must be explicitly implemented or marked `NOT_IMPLEMENTED`. The previous runner contained silent no-ops, so prior tuned W3 claims are not valid until corrected.

## 4. Current ranking of research candidates

This is a research queue, not a production ranking:

1. `52W-C2` — strongest broad candidate; exact corrected replay still required.
2. `WAVE2_CONTINUATION / marsi_65_0` — strongest Wave-2 robustness direction; structural wiring and current-scope replay required.
3. `WAVE3_CONTINUATION / marsi_65_0` — exploratory continuation candidate; structural/MACD/volume implementation incomplete.
4. `WAVE1_PICKUP` — cut/audit-only; no active rescue search.

## 5. SHADOW_READY gate

A policy may be nominated for isolated shadow/evidence review only when all of these are satisfied:

```text
valid decided outcomes total       >= 100
valid decided outcomes per 4 cells >= 10
positive cells at 3R / 50 bps      >= 50% (at least 2/4)
holdout expectancy at 3R / 50 bps  >= +0.10R
single-symbol concentration        <= 25%
```

Invalid/undecided statuses have no hard percentage floor yet, but each must be reported separately. A policy below the gate remains `RESEARCH_ONLY / INCONCLUSIVE`.

`SHADOW_READY` does not mean production-ready. Production consideration additionally requires cost-stressed portfolio replay, capacity analysis, representative chart review, paper/shadow evidence, expiry/disable/rollback path, owner approval, source/tests/runtime/API/UI/data-lineage gates, and a documentation sync.

## 6. Current next sequence

### Phase A — corrected policy evidence

1. Correct the immutable AutoResearch runner and tests.
2. Mark unsupported structural/MACD/volume cycles `NOT_IMPLEMENTED`.
3. Re-run `52W-C2`, W2 `marsi_65_0`, and W3 `marsi_65_0` with policy/event/result hashes.
4. Preserve locked holdout and separate current-237 versus broad scopes.

### Phase B — portfolio evidence

1. Run the initial gross/no-cost unconstrained diagnostic.
2. Run the same candidates with 25/50 bps cost stress.
3. Add capacity-constrained comparison after the diagnostic.
4. Report equity curve, geometric growth, max drawdown, losing streak, turnover, overlap/capital demand, and concentration.

### Phase C — visual review

For each nominated policy, review:

- true positives;
- false positives;
- missed events;
- pivot failures;
- worst era/fold/cost cells;
- current-scope representatives.

The review page must show playbook, policy, symbol, buy point, stop, target, R:R, outcome, source/as-of, and evidence status without pooling playbooks.

### Phase D — shadow decision

Only after A–C pass, evaluate `SHADOW_READY`. Arm then decides whether to implement an isolated shadow/evidence surface. No production surface changes are implied.

## 7. Evidence registry

Primary temporary evidence currently includes:

- `/tmp/signalix_four_playbook_baseline_matrix.json`
- `/tmp/signalix_historical_1990_2026_robustness.json`
- `/tmp/signalix_production_readiness_campaign.json`
- `/tmp/signalix_playbook_tuning_15cycles.json`
- `/tmp/signalix_autoresearch_batch1_50.json`
- `/tmp/signalix_autoresearch_batch2_robust.json`
- `/tmp/signalix_autoresearch_time_symbol_matrix.json`
- `/tmp/codex_playbook_tuning_correction.md`
- `/tmp/signalix_current_set_playbook_buy_data.json`

Temporary files are evidence, not the sole authority. Before promotion, preserve exact manifests/reports/charts in a durable research archive with checksums.

## 8. Cycle 1 — current-237 52W deep research

Manifest: `/tmp/signalix_52w_current237_deep_research.json`.

Scope and data lineage:

```text
scope: marginable_long_current_retrospective
 declared symbols: 237
 data-blocked: 3BBIF, COM7, PR9
 holdout used for ranking: false
 target axis: 3R
 cost axis: 50 bps
```

Validation-only selection order:

```text
52W-C2 → 52W-C5 → baseline → 52W-C1 → 52W-C4 → 52W-C3
```

Current-237 holdout expectancy at `3R / 50 bps`:

```text
baseline:  -0.0803R
52W-C1:    -0.0884R
52W-C2:    -0.0608R
52W-C3:    +0.0177R
52W-C4:    -0.0709R
52W-C5:    -0.0534R
```

Interpretation:

- `52W-C2` remains the validation-selected candidate but fails current-237 holdout and is not a champion.
- `52W-C3` (next-day-open) is the only positive current-237 holdout candidate in this cycle, but `+0.0177R` is far below the `SHADOW_READY` floor of `+0.10R`.
- All same-day-close policies were negative on current-237 holdout at this axis/cost.
- Mean MFE/MAE was computed, but MFE is a research label only and was not used to construct targets or rank holdout.
- Market regime was `NOT_VERIFIED` in this runner because SET-index context was not wired into the campaign; no regime conclusion is allowed.
- No policy passes `SHADOW_READY`; this cycle is a useful failure/diagnostic result, not a promotion.

Cycle verdict:

```text
source/tests: PASS
current-237 campaign: PASS / RESEARCH_ONLY
holdout robustness: FAIL for promotion
market-regime context: NOT VERIFIED
portfolio cost/capacity: PENDING
chart review: PENDING
production: HOLD
```

## 9. Cycle 2 — retest entry and SET regime evidence

Manifest: `/tmp/signalix_52w_cycle2_current237.json`.

Two pre-registered retest policies were tested against the six existing comparators:

```text
52W-R1_RETEST_CLOSE:
  breakout → first retest near prior high → close holds → enter

52W-R2_RETEST_HIGH_CONFIRM:
  breakout → retest → later close above retest high → enter
```

Current-237 holdout expectancy at `3R / 50 bps`:

```text
52W-C2:                    -0.0608R
52W-C3 next-day-open:      +0.0177R
52W-R1 retest-close:       -0.0980R
52W-R2 retest-high-confirm:-0.1161R
```

Risk-compression evidence:

```text
C2 mean MAE:  5.68R
R1 mean MAE:  3.25R
R2 mean MAE:  1.97R
```

The retest entries reduced measured adverse excursion, but the tested definitions did not improve current-237 holdout expectancy. They are not promotion candidates.

SET regime mapping is now available through exact entry-date matching. Aggregate regime evidence across the campaign suggests supportive regimes have stronger expectancy than neutral/defensive regimes, but this output is not yet a holdout-by-regime promotion test. The next gate must report regime splits separately inside train, validation, and locked holdout before any no-trade rule is selected.

Cycle verdict:

```text
source/tests: PASS
current-237 Cycle 2: PASS / RESEARCH_ONLY
retest hypothesis: FAIL for promotion under these definitions
SET regime context: source PASS; holdout-by-regime gate pending
SHADOW_READY: NOT VERIFIED
production: HOLD
```

## 10. Cycle 3 — regime-aware candidate and 2026 visual review

Manifest: `/tmp/signalix_52w_cycle3_current237.json`.
Visual dashboard: `/tmp/signalix_52w_2026_event_dashboard.html`.

Cycle 3 added two pre-registered regime-aware candidates:

```text
52W-C2_SUPPORTIVE_ONLY
52W-C3_SUPPORTIVE_ONLY
```

They inherit C2/C3 event definitions and accept entries only when SET regime is `SUPPORTIVE` at the exact entry date. No regime threshold was tuned from holdout.

Current-237 holdout expectancy at `3R / 50 bps`:

```text
52W-C2_SUPPORTIVE_ONLY: +0.0805R
52W-C3_SUPPORTIVE_ONLY: +0.2209R
```

The current research leader is therefore:

```text
52W-C3_SUPPORTIVE_ONLY
= 252-day breakout family
+ next-day-open entry
+ SET SUPPORTIVE regime at entry
```

This is a **potential best candidate**, not yet `SHADOW_READY`. It still requires fold/sample checks, monthly stability review, cost/portfolio evidence, and chart review. The 2026 dashboard provides filters for policy, regime, outcome, month, and symbol, plus clickable Daily event charts and monthly summaries.

2026 ledger scope:

```text
current symbols: 237
2026 event rows: 2,566
replay as-of: 2026-09-04
```

Interpretation boundary:

- `SUPPORTIVE_ONLY` is a research filter, not a production market gate yet.
- Monthly summaries are descriptive evidence; they cannot be used to cherry-pick months after seeing outcomes.
- `HIT TARGET`/`HIT STOP` are historical replay outcomes, not current buy instructions.
- No production API/UI surface changed.

Cycle verdict:

```text
source/tests: PASS
current-237 campaign: PASS / RESEARCH_ONLY
2026 visual dashboard: PASS static; browser acceptance NOT VERIFIED
potential candidate: 52W-C3_SUPPORTIVE_ONLY
SHADOW_READY: NOT VERIFIED
production: HOLD
```

## 11. Final status

```text
Bible/documentation: CURRENT
Research formulas recorded: PASS
AutoResearch contract: PASS for bounded contract slice
52W current-237 deep cycle 1: PASS / RESEARCH_ONLY; no promotion candidate
52W current-237 deep cycle 2: PASS / RESEARCH_ONLY; retest definitions failed promotion
52W current-237 deep cycle 3: PASS / RESEARCH_ONLY; C3 supportive-only is potential leader
Portfolio replay: gross diagnostic PASS; cost/capacity gates pending
Market-regime context: source PASS; supportive-only candidate pending gates
2026 visual dashboard: static PASS; browser NOT VERIFIED
SHADOW_READY: NOT VERIFIED
Production promotion: HOLD
Alerts/auto-trading/broker execution: OFF/PENDING
```
