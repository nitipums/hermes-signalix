# Signalix — Stage-First Scan Classification (Consolidation Spec)

**Status:** Draft for Khim review — NOT merged into prod. Do not import from
`backend/` yet. Bee prepared this; Arm approved the direction 2026-08-17.
**Rule honored:** Bee does not edit Signalix prod code; this is a draft for Khim
to review, test, and deploy.

## Problem (root cause of inconsistency)

A single symbol was being assigned **three parallel label systems**:

1. `scanner.trade_readiness.status` → `BUY / HOLD / OVERBOUGHT / BREAK / WAIT`
2. `daily_setup_state.classify_daily_state().primary_state` →
   `fresh_breakout / breakout_setup / trend_pullback / base_forming / no_long_setup`
3. `screening.group_scan_results()` (v2) →
   `breakout_new / uptrend_pullback / waiting_breakout / base / down_or_broken`

Worse:
- `screening.group_scan_results` is **defined twice** in the same module
  (legacy 9-group at line 348, v2 6-group at line 405). Python silently keeps
  the second; the first is dead code but still referenced by tests.
- `build_dashboard.determine_action` switches on the **dead legacy group names**
  (`ready_validate`, `retest_watch`, `avoid`, ...). Those names come from the
  first (overwritten) function, so every v2 group falls through to `WAIT`.
- The dashboard renders THREE badges at once: `group`, `baseGroup`, `status`
  (trade_readiness). For one symbol the user sees three contradictory labels.

## Approved direction (Arm, 2026-08-17)

> Trend is the first priority — Minervini Stage Analysis (Stan Weinstein style):
> - **Stage 1** — Basing (after a down move, building a base)
> - **Stage 2** — Uptrend (the only stage to be long)
> - **Stage 3** — Distributing (topping / rolling over)
> - **Stage 4** — Down (declining)
>
> Other factors (breakout, pullback, readiness) support the trade — they do NOT
> pick the primary bucket.

## Target state (one canonical classifier)

Replace the 3-system tangle with **ONE** classifier returning `stage` + `phase`:

### Layer 1 — `stage` (the primary bucket, Minervini/Weinstein)
Computed from price vs MA50/MA150/MA200 and MA200 slope (all already in
`trend_template`/`trade_readiness`).

| stage | definition (deterministic) |
|---|---|
| `S1_basing` | price NOT clearly above a rising MA200; range-bound / early repair (MA200 flat or still falling) |
| `S2_uptrend` | price > MA200 AND MA200 slope positive (>= 1mo) |
| `S3_distributing` | price still >= MA200 but MA200 slope turning flat/down OR price stalling near highs after long run |
| `S4_down` | price < MA200 (or MA200 falling and price below) |

### Layer 2 — `phase` (actionable sub-state within a stage)
| stage | allowed phases |
|---|---|
| S1_basing | `base_early`, `base_tight` (VCP complete → launch candidate) |
| S2_uptrend | `breakout_new`, `breakout_extended`, `uptrend_pullback`, `waiting_breakout` |
| S3_distributing | `topping` |
| S4_down | `declining`, `broken` (false-breakout / structure failure) |

### Layer 3 — `evidence` (raw inputs, NOT a label)
`trigger_level`, `fib_zones`, `rsi_daily`, `volume_ratio_50`, `liquidity`,
`dataFreshness`, `trend_template.conditions_met`. `trade_readiness.status`
is demoted to a presentation hint only — never a grouping key.

## Code changes (draft, for Khim)

1. **New** `drafts/stage_classifier/stage_classifier.py`
   - `classify_stage(evidence: dict, event: dict | None = None) -> dict`
     returns `{stage, phase, stage_label, phase_label, evidence, ...}`.
   - Single precedence order, versioned constants (no magic numbers in prose).
   - Reuses existing inputs from `trend_template` + `trade_readiness`
     (price, ma50/150/200, ma200 slope, range_20d_pct, breakout, fib, rsi,
     volume). No new data source needed.

2. **`screening.group_scan_results`**
   - Delete the legacy duplicate (line 348) entirely.
   - The remaining function maps `(stage, phase)` → ONE dashboard group:
     `breakout_new`, `uptrend_pullback`, `waiting_breakout`, `base`,
     `down_or_broken` (unchanged keys — keeps `app.py` / `serialize` working).
   - Each row stores `daily_state = classify_stage(...)` (keyed `stage`/`phase`).

3. **`build_dashboard.determine_action` + `plan`**
   - Switch on `phase` (canonical), not dead legacy group names.
   - `trade_readiness.status` used only as a supportive hint in evidence.

4. **`build_dashboard.serialize`**
   - `lifecycle` badge uses `stage` + `phase` as the primary label;
     `status` (trade_readiness) shown only as a secondary hint.

## Tests (draft)
- `drafts/stage_classifier/test_stage_classifier.py`
  - covers each stage×phase via synthetic evidence dicts (no DB needed).
  - asserts single group per symbol, no overlap, deterministic on same input.
- Update `backend/test_action_dashboard.py` and `test_daily_setup_state.py`
  to reference `phase` instead of dead `primary_state` names (Khim to port).
- Keep `verify_scan_dashboard` consistency check (group counts match scan).

## Out of scope
- Data source (SET EOD vs yfinance) — separate issue.
- Intraday engine — stays a separate observation layer, must not overwrite stage.
- Pivot/scan history schema migration — `scan_history` stores `scan_group` text;
  new `stage`/`phase` can be added additively.

## Open question for Khim
S3 vs S4 boundary uses MA200 slope sign + price-vs-MA200. The exact slope
threshold (e.g. 1-mo MA200 change < 0 vs < -X%) should be a versioned constant.
Confirm threshold with Arm before deploy.
