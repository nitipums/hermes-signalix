# Signalix Wave Playbooks Research — Findings and Session Handoff

> **STATUS: CURRENT RESEARCH HANDOFF — PRODUCTION SEPARATE**
> **Date:** 2026-09-05 ICT
> **Owner/final gate:** Lite → Arm review
> **Project index:** `vault/Research-Index.md`
> **Product authority:** `vault/Product-Strategy-Market-to-Action.md`, `vault/Decisions.md`, and the current Elliott/Trend/Trade-Setup spec remain authoritative. This note is research evidence/navigation, not a production contract.

## 0. Session-start summary

The research discovered a stronger decomposition than a generic breakout finder:

```text
Wave-1 / prior impulse
→ Wave-2 pullback/pivot candidate
→ pivot survival
→ post-pivot rebound
→ minor high
→ higher low
→ close above minor high
→ continuation entry
→ structural stop / target / R:R / outcome
```

The key product insight is:

```text
PIVOT_CONFIRMED ≠ BUY
```

A pivot can continue falling. The preferred buyable research event is a **post-pivot continuation breakout** after a higher low and minor-high close breakout. Wave evidence remains machine-generated candidate/evidence for Arm review; it is not Elliott truth and does not authorize execution.

Current status:

- Structural pivot/continuation research: **PASS as isolated prototype evidence**.
- Four-playbook broad replay: **PASS as baseline research; production not verified**.
- Best broad candidate so far: **52W breakout family**, but still requires portfolio replay, realistic costs, chart review, paper/shadow, and owner approval.
- Wave-2/Wave-3 results are **scope-dependent**: current 237-symbol retrospective and broad historical 1,219-symbol data are not interchangeable.
- Wave-1 pickup is **CUT / AUDIT ONLY** under the current baseline because current/broad holdout expectancy was negative.
- Production promotion: **HOLD**. `/api/setup-candidates` and `/mvp` were not changed.

## 1. Product/research boundary

Signalix production remains:

```text
Daily trend / Wave evidence
→ 60m setup and confirmation
→ trigger / stop / target / R:R
→ Arm chart review and decision
```

Research playbooks are isolated. They must not silently change:

- `/api/setup-candidates`;
- `/mvp` lanes or published Wave states;
- Daily versus 60m evidence authority;
- current `marginable_long` operational scope;
- alerts, evaluator auto-caller, auto-trading, or broker execution.

Research output is evidence, not a signal truth or order instruction.

## 2. Universe scopes

Keep these scopes separate in every report:

### A. Current `marginable_long` retrospective

- Current operational universe: **237 symbols**.
- Useful for: “Does this help the current tradable workflow?”
- Bias: current-universe/survivorship/availability bias when replayed backward.
- It is not an unbiased historical Thai market universe.

### B. Current active ORD retrospective/audit

- Current active Thai ORD scope is approximately **931 symbols**.
- Useful for audit comparison, not the current default product scope.

### C. Historical broad stored-data universe

- Stored Thai ORD symbols with data in the broad 1990–2026 window: **1,219**.
- History status in the historical campaign: **1,172 OK**, **47 insufficient-history**.
- Verified 1990–2015 slice: **741 symbols**, approximately **1,977,045 rows**.
- This is a data-availability universe, not point-in-time listing membership.

Never pool counts or call scope C equivalent to current 237.

## 3. Data/replay contract

Baseline research contract:

- Daily OHLCV.
- `Asia/Bangkok`/SET session semantics where applicable.
- Confirmed pivots require right-hand confirmation bars.
- Inputs at `as_of` contain only bars available through `as_of`.
- Entry and future outcomes are separated.
- Outcome horizon: **120 Daily bars** for the long-run baseline.
- `TARGET`, `STOP`, `AMBIGUOUS`, `EXPIRED`, `INSUFFICIENT_FUTURE_DATA`, and `TARGET_BELOW_ENTRY` remain separate.
- `EXPIRED` means a complete 120-bar horizon elapsed without target/stop.
- `INSUFFICIENT_FUTURE_DATA` means the dataset ended before a complete horizon.
- Same-bar target/stop is ambiguous; never choose the favorable side.
- `TARGET_BELOW_ENTRY` is not a win or loss; that target is not a valid forward target for that entry.
- Costs/slippage must be explicit. Early baselines used zero cost plus later 25/50 bps stress; this is not a production fee model.

R:R is calculated, not manufactured:

```text
risk   = entry - stop
reward = target - entry
R:R    = reward / risk
```

For target axes, the research uses `1R` risk and evaluates target multiples:

```text
1:2.5, 1:3, 1:3.5, 1:4, 1:5
```

Target multiples are evaluation axes only. They must not be used to move a target until a policy wins.

## 4. Wave-2 pivot findings

The first generic HH/HL post-breakout finder was the wrong abstraction. It produced many broad events and attempted to judge R:R after breakout.

The corrected methodology is pivot-first:

```text
Adaptive/multi-scale pivot evidence
→ macro impulse
→ large pullback
→ Wave-2 candidate/pivot zone
→ pivot confirmation
→ post-pivot continuation
```

A pivot is not defined only by a fixed 2–3 bar window. The research model needs:

- candidate versus confirmed pivot;
- macro/intermediate/internal swing levels;
- price excursion/volatility significance;
- parent `PULLBACK_ACTIVE` / `PULLBACK_REBOUND` state;
- pivot zones when Fib/support/structure cluster;
- internal 5-leg/3-leg structures as hypotheses only.

For KTC, the stored Daily replay produced a structure consistent with the owner-labelled chart:

```text
W1 low:       28.50
W1 high:      41.25
W2 low:       36.25
pivot:        2026-08-26
entry ref:    38.00
stop:         35.83
prior high:   41.25
W3 1.272:     44.72
W3 1.618:     49.13
```

The chart dashboard showed:

```text
Target 1 R:R:     1:1.50
W3 1.272 R:R:     1:3.10
W3 1.618 R:R:     1:5.13
```

This matched the owner methodology better than a generic breakout finder: buy near a Wave-2 pivot/reclaim and use Wave-3 extensions for later targets. The latest KTC event had only seven future bars at the cutoff, so its outcome was correctly `INSUFFICIENT_FUTURE_DATA`, not `EXPIRED`.

## 5. Post-pivot continuation finding

The owner’s BGRIM example established the preferred buy sequence:

```text
PIVOT_CONFIRMED
→ POST_PIVOT_REBOUND
→ MINOR_HIGH_FORMED
→ MINOR_PULLBACK
→ HIGHER_LOW_CONFIRMED
→ BREAKOUT_CONFIRMED / CONTINUATION_BREAKOUT_ENTRY
```

Failure/wait states:

```text
PIVOT_FAILED
PIVOT_WAITING_OR_NO_MINOR_BREAKOUT
FAILED_BREAKOUT
EXTENDED / DO_NOT_CHASE
```

The later breakout is a new execution event. Recalculate entry, stop, targets, and R:R at breakout; never reuse pivot-day R:R.

Broad continuation replay baseline:

- Pivot events: **2,961**.
- Pivot failed: **1,164**.
- Continuation breakout entries: **1,669**.
- Waiting/no minor breakout: **128**.

For the broad baseline, Wave-3 1.272 target-before-stop was approximately:

- Full 15-year: **51.23%** of decided outcomes.
- Holdout 2022–2026: **45.15%**.

The prior current-universe candidate showed stronger results than broad history; this is a scope/regime difference, not a contradiction to hide.

## 6. Four playbooks

The research project contains four distinct playbooks; do not pool them into one signal score until each has its own event and outcome evidence.

### 6.1 `WAVE2_CONTINUATION`

```text
Wave-2 pivot
→ pivot survives
→ rebound
→ minor high
→ higher low
→ close above minor high
```

Current status: promising in current-scope experiments, weak in some broad/current holdouts. Requires exact structural policy wiring before more tuning.

### 6.2 `52W_HIGH_BREAKOUT`

Baseline:

```text
close > prior 252/260 trading-day high
+ declared volume rule
+ declared same-close/next-open entry
```

Broad baseline event count: **11,961**.

The best early candidate was around `52W-C2`:

```text
252-day lookback
volume >= 1.25 × prior 20-day average
same-day close entry
ATR stop buffer 1.0
```

It showed small positive holdout expectancy across target axes in the broad baseline, but remains research-only and requires exact next-open/close semantics, fees, portfolio replay, and chart review.

### 6.3 `WAVE1_PICKUP`

Exploratory hypothesis:

```text
down-leg/base
→ rebound high
→ higher low
→ close breakout
```

Broad baseline event count: **5,138**.

Current finding: negative holdout expectancy across target axes. Status:

```text
CUT / AUDIT ONLY
```

Do not rescue it with arbitrary threshold search. Re-entry requires a separately justified structure definition and a new pre-registered hypothesis.

### 6.4 `WAVE3_CONTINUATION`

Exploratory hypothesis:

```text
prior impulse
→ Wave-2-like retracement
→ pivot hold
→ higher low
→ close above impulse/internal continuation high
```

Broad baseline event count: **16,599**.

Current holdout was weakly positive/near zero depending on target and scope, but structural policy wiring and indicator cycles were incomplete. Status: exploratory, not production.

## 7. Indicator findings

Technical indicators are deterministic supporting evidence, not Wave authority.

Tested families:

- RSI14;
- MACD EMA12/26 with EMA9 signal;
- SMA20/SMA50/SMA200 and slope;
- pre-break volume behavior and breakout volume.

Findings:

- MA alignment generally helped more consistently than RSI/MACD alone.
- Composite policies sometimes improved validation but could fall on holdout.
- Volume dry-up filters were often too restrictive and reduced coverage sharply.
- A validation winner with a small sample was repeatedly exposed as overfit on holdout.
- Current 237 and broad 1,219 scopes produced different results.

Indicators must be tested through ablation:

```text
structure only
→ RSI/MACD
→ MA
→ volume
→ controlled combinations
→ time×symbol/cost robustness
```

No indicator may create, relabel, or rescue a Wave structure.

## 8. AutoResearch findings

### Mechanical readiness

The isolated harness/policy boundary is mechanically ready in principle:

- immutable replay/evaluator boundary;
- mutable policy JSON;
- policy hashes;
- train/validation/holdout separation;
- repeatability/no-lookahead checks;
- time×symbol matrix;
- cost stress.

### Campaign results

Batch 1: 50 indicator policies.

- Top validation policy overfit relative to holdout.
- This was a useful overfit finding, not a champion.

Batch 2: robust sample-floor campaign.

- `marsi_60_0` and `marsi_65_0` were promising candidates.
- Worst cells remained weak under cost stress.
- No production champion.

Time×symbol matrix:

- `marsi_65_0` had strong positive-cell share in one matrix and low symbol concentration.
- Worst cells remained below production comfort thresholds.
- This supports further research, not promotion.

Historical 1990–2026 campaign:

- MA + RSI65 produced >55% in several older eras.
- 2016–2026 was materially weaker.
- This indicates regime dependence, not a universal formula.

## 9. Codex involvement and corrections

Codex review artifacts:

```text
/tmp/codex_four_playbooks_review.md
/tmp/codex_playbook_tuning_plan.md
/tmp/codex_playbook_tuning_correction.md
```

Codex recommended staging: shared immutable harness first, Playbooks 1–2 first, then exploratory Playbooks 3–4.

Codex correction identified real runner issues:

- W2/W3 structural overrides were silent no-ops;
- MACD/volume cycle fields were not applied;
- 52W signal/entry schema needed separation;
- missing date matches must fail closed, not map to index zero;
- prior W2 best candidate must remain an immutable comparator;
- holdout lock and duplicate policy/event signatures were missing.

Corrected runner explicitly marked unsupported cycles `NOT_IMPLEMENTED` rather than presenting them as results.

Codex CLI evidence:

- Default Codex lane completed the design/review artifacts.
- Explicit `gpt-5.6` lane was rejected by the ChatGPT account as unsupported; no source/production changes were made by that failed lane.

## 10. What is cut, what remains

### Cut from candidate production research

- Wave-1 pickup baseline: audit-only.
- Any policy with insufficient holdout/fold sample.
- Any policy whose validation win collapses on holdout.
- Any policy with unacceptable symbol/year concentration.
- Any policy with target semantics hidden by `TARGET_BELOW_ENTRY`.

### Remains for next session

- Correctly wire W2/W3 structural overrides and MACD/volume policies.
- Preserve the earlier current-237 W2 candidate as immutable baseline.
- Run corrected 5–10 cycle tuning only after event-set/hash and policy field tests pass.
- Build portfolio replay with 1R risk and target axes 2.5/3/3.5/4/5.
- Report equity growth, max drawdown, losing streak, overlap/cap behavior, and cost stress.
- Create visual chart review of true/false/missed/pivot-fail and worst cells.
- Keep 52W as a separate playbook; do not force Wave2/Wave3 filters onto it.

## 11. Session-start checklist

Start the next session here:

1. Read this document and `vault/Research-Index.md`.
2. Read Codex correction: `/tmp/codex_playbook_tuning_correction.md`.
3. Treat `/tmp` reports as session evidence; verify they still exist/checksum before relying on them.
4. Reconcile baseline counts before tuning:

```text
Universe broad: 1,219
52W: 11,961
Wave1 audit: 5,138
Wave2: 10,169
Wave3: 16,599
```

5. Confirm current product scope remains 237 and production remains unchanged.
6. Fix/verify policy field wiring before any new long run.
7. Run portfolio replay only after event/evaluator correctness passes.
8. Report separate verdicts: research evidence, runtime/data, chart review, paper/shadow, production readiness.

## 12. Final status

```text
Research project/index: CURRENT
Baseline replay: PASS
Four-playbook baseline: PASS / RESEARCH_ONLY
Historical/time×symbol robustness: PASS / mixed findings
AutoResearch mechanical harness: PASS
Parameter tuning: PARTIAL; corrected runner required
Portfolio growth replay: NOT STARTED
Paper/shadow: PENDING
Production promotion: HOLD
Alerts/auto-trading/broker execution: OFF/PENDING
```
