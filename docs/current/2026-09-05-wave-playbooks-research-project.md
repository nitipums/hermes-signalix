# Signalix Wave Playbooks Research Project

> **STATUS: CURRENT — RESEARCH PROJECT / PRODUCTION SEPARATE**
> **Date:** 2026-09-05 ICT
> **Owner/final gate:** Lite → Arm review
> **Index:** `../../vault/Research-Index.md`
> **Non-authority:** This project does not change the canonical product strategy, `/api/setup-candidates`, `/mvp`, published Wave states, alerts, auto-trading, or broker execution.

## Purpose

Create a durable research project for deterministic Daily playbooks and bounded AutoResearch so Signalix can compare structural setups without losing event definitions, universe scope, era/fold results, target semantics, or failed findings.

The research question is not “find a magical formula.” It is:

> Which deterministic playbook/event definitions remain useful across declared time eras, symbol-disjoint folds, target multiples, and cost stress, while preserving honest unknown/invalid/insufficient outcomes?

## Project boundaries

### Production boundary

- Research-only until a separate owner decision promotes a policy.
- Current product authority remains the Elliott/Trend/Trade-Setup spine.
- Wave labels remain machine-generated candidate/evidence for Arm review.
- Alerts, auto-trading, broker execution, and evaluator auto-caller remain OFF/PENDING.

### Universe scopes

Keep these scopes separate in every report:

1. `marginable_long_current_retrospective` — current 237 operational symbols replayed backward; useful for current workflow, but availability/survivorship biased.
2. `active_ord_current_retrospective` — current active ORD audit scope.
3. `historical_th_ord_data_available` — stored Thai ORD symbols available in the requested date window; broadens cross-sectional testing, but is not point-in-time exchange membership.

Never pool their counts or call one scope another.

### Time scopes

Use explicit era windows:

```text
1990–1994
1995–1999
2000–2004
2005–2009
2010–2015
2016–2020
2021–2026 (frozen as-of)
```

Use stable SHA-256 symbol folds, not process-randomized `hash()`.

## Sub-projects

### A. Wave-2 continuation

```text
confirmed pivot
→ post-pivot rebound
→ minor high
→ higher low
→ close above minor high
→ continuation entry
```

Entry-time R:R must be recalculated at the minor-high breakout. Pivot-day R:R must not be reused.

### B. 52W high breakout

Declare separately:

- prior 252/260 trading-day high excluding signal bar;
- close breakout rule;
- volume denominator/multiplier;
- same-day-close versus next-open entry;
- ATR/structural stop;
- gap and missing-next-open statuses.

Close-entry and next-open candidates are never pooled.

### C. Wave-1 pickup

Exploratory only:

```text
down-leg/base hypothesis
→ rebound minor high
→ higher low
→ close breakout
```

The “Wave 5 completed” interpretation is evidence only, never truth. Current baseline was cut from candidate production research after negative holdout evidence; preserve it as audit history.

### D. Wave-3 continuation

Exploratory:

```text
prior impulse
→ Wave-2-like retracement
→ pivot hold
→ higher low
→ close above impulse/internal continuation high
```

Structural and MACD/volume overrides must be explicitly implemented or marked `NOT_IMPLEMENTED`; never silently run a baseline under a tuned policy name.

### E. AutoResearch

Immutable harness:

- snapshot/data boundary;
- universe resolver;
- right-hand confirmation/no-lookahead;
- event labels and entry semantics;
- stop/target/outcome evaluator;
- same-bar ambiguity;
- 120-bar horizon;
- target axes `2.5, 3, 3.5, 4, 5R`;
- cost/slippage axes;
- train/validation/locked holdout.

Mutable policy JSON:

- pivot/structure thresholds;
- MA/RSI/MACD/volume filters;
- 52W lookback/volume/entry/stop parameters;
- declared playbook-specific policy fields.

Every run records policy JSON, policy hash, event-set hash, result signature, sample floors, and status.

### F. Portfolio replay

Next bounded sub-project. It must convert event evidence into an explicit 1R portfolio simulation with:

- non-overlap/cooldown rule;
- simultaneous position cap;
- equal-risk allocation;
- fees/slippage;
- target/stop execution;
- equity curve and geometric growth;
- max drawdown and losing streak;
- symbol/sector concentration;
- comparison of target multiples.

Until this exists, report expectancy in R and target-before-stop separately; do not call event metrics portfolio growth.

## Current evidence registry

Temporary evidence currently lives under `/tmp` and must be promoted to a durable research archive before any handoff/promotion:

- `/tmp/signalix_four_playbook_baseline_matrix.json`
- `/tmp/signalix_historical_1990_2026_robustness.json`
- `/tmp/signalix_production_readiness_campaign.json`
- `/tmp/signalix_playbook_tuning_15cycles.json`
- `/tmp/signalix_autoresearch_batch1_50.json`
- `/tmp/signalix_autoresearch_batch2_robust.json`
- `/tmp/signalix_autoresearch_time_symbol_matrix.json`
- `/tmp/codex_four_playbooks_review.md`
- `/tmp/codex_playbook_tuning_plan.md`
- `/tmp/codex_playbook_tuning_correction.md`

Visual review artifacts:

- `/tmp/signalix_wave2_chart_dashboard.html`
- `/tmp/signalix_wave2_recent_pivots.html`
- `/tmp/signalix_continuation_breakout_replay.html`

## Current findings snapshot

- Wave-1 pickup is `CUT_AUDIT_ONLY` under the current baseline because holdout expectancy was negative.
- 52W breakout is the strongest broad-universe baseline candidate, but remains research-only pending portfolio/cost/chart gates.
- Wave-2 and Wave-3 results differ materially between current 237 retrospective scope and broad historical scope; do not pool them.
- MA/RSI filters show regime-dependent evidence; no universal production champion exists.
- A validation winner that falls on holdout is recorded as an overfit finding, not a champion.
- Corrected tuning runner marked unsupported W2-C5/W3-C4/W3-C5 as `NOT_IMPLEMENTED` rather than presenting silent no-ops as results.

## Status and next resume sequence

Current project status:

```text
baseline replay: PASS
historical/time×symbol evidence: PASS
parameter tuning: PARTIAL / corrected runner evidence retained
portfolio replay: NOT STARTED
chart review of worst cells: PENDING
paper/shadow: PENDING
production promotion: HOLD
```

Next sequence:

1. Archive exact manifests/reports/checksums from `/tmp` into a durable research evidence area.
2. Finish corrected playbook-specific policy wiring and tests; keep unsupported cycles explicitly blocked.
3. Run portfolio replay for the best non-dominated candidates and all target axes.
4. Generate visual chart review for true/false/missed/pivot-fail and worst cells.
5. Run paper/shadow only after owner reviews evidence.
6. If a policy passes all gates, create a separate owner decision and production implementation task; do not modify production from this project note.
