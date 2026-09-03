# Signalix Daily Structural Evidence Integration

> **STATUS: CURRENT — OWNER APPROVED DESIGN FRONTIER** · 2026-09-03
> **Owner:** Arm · **Final gate:** Lite
> **Scope:** restore useful Daily Wave 1/2/4/5 visibility without weakening the canonical Wave-3 publication contract.
> **Authority:** this focused spec extends `docs/superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md`; it does not replace it.

## Problem

The current canonical `/mvp` surface publishes only `EARLY_WAVE_3`, `WAVE_3_CONTINUATION`, and `NOT_VERIFIABLE`. The prior full-wave engine still computes broader structural evidence, but it is retained under compatibility/context fields and is not exposed as a clean, useful Daily structural view. Wave 1/2/4/5 evidence therefore appears to have disappeared even though the underlying data and legacy observations remain.

## Owner-approved solution

Keep one canonical decision spine:

```text
wave.primary_state → setup → decision_lane
```

Add one explicitly non-actionable Daily evidence object:

```json
{
  "wave": {
    "primary_state": "NOT_VERIFIABLE",
    "daily_structure": {
      "phase": "WAVE_4_CORRECTION",
      "confidence": "MEDIUM",
      "actionability": "NONE",
      "source_timeframe": "daily",
      "policy_version": "daily-structure-evidence-v1",
      "as_of": "2026-09-02",
      "anchors": {},
      "retracement": null,
      "supporting_evidence": [],
      "contradicting_evidence": [],
      "missing_evidence": [],
      "alternative_phases": []
    }
  }
}
```

`wave.primary_state` remains the sole canonical wave/decision field. `daily_structure.phase` is explanatory structural evidence and has `actionability=NONE`; it cannot create `REVIEW_NOW`, change setup validity, or override the W3 retracement gate.

## State policy

- `EARLY_WAVE_3` and `WAVE_3_CONTINUATION` remain canonical primary states under the existing W3 contract.
- `WAVE_1_ADVANCE`, `WAVE_2_FORMING`, and `WAVE_2_NEAR_COMPLETION` return as `daily_structure.phase` evidence first. Their separate policy/replay gate comes later; `WAVE_2_NEAR_COMPLETION` is the next candidate for a bounded candidate-lane experiment.
- `WAVE_4_CORRECTION` returns as Daily risk/context evidence only. It never maps directly to `AVOID`.
- `WAVE_5_ADVANCE` returns as evidence only until confirmed progression and late-cycle behavior pass replay; do not reactivate the legacy alternating-leg label as a primary state.
- `UNKNOWN` remains explicit evidence with missing/invalid reasons. Canonical primary remains `NOT_VERIFIABLE` when the narrow W3 contract cannot publish.

## Evidence and timeframe rules

- Daily structural evidence uses Daily OHLCV only and carries `source_timeframe=daily`.
- 60m remains setup/minor-structure evidence and never overwrites Daily primary or Daily structural phase.
- Ordered anchors, right-hand pivot confirmation, no-lookahead, as-of identity, and raw evidence must be preserved.
- Keep anchor admissibility `0.236 <= r <= 0.786` separate from W3 publication eligibility `r <= 0.60`. The W3 gate applies only to publishing W3 states; it must not erase valid Wave-2 evidence.
- Preserve raw candidate state/evidence when canonical primary is `NOT_VERIFIABLE`; do not force labels to match owner examples or fabricate transition dates.

## API and UI contract

- Add `wave.daily_structure` as an additive nested field in the full canonical detail contract; include a bounded representation in list items only when required for a visible filter/summary.
- Keep legacy `wave.context.mapped_state` as compatibility/audit input during migration; do not use it as primary.
- `/mvp` cards show only `Primary Daily Wave` from `wave.primary_state` and the existing decision lane.
- The drawer shows `Daily structural context` with phase, confidence, anchors, retracement, source/as-of, and missing/rejection evidence. Label it explicitly non-actionable.
- Phase filters, if added, are presentation-only and must not change server-side evaluated universe or decision lanes.
- No automatic trading, alerts, broker execution, evaluator auto-caller, or new database schema is in scope.

## Bounded implementation slice

The first slice is additive evidence only:

1. Reconcile the existing dirty `setup_candidate_contract.py` and `wave-context.js` owner changes before overlapping edits.
2. Build a single adapter/module seam that projects the already-computed full Daily structural result into `wave.daily_structure` without invoking a second detector or using 60m data.
3. Preserve existing canonical W3 primary, setup, lane, freshness, and pagination behavior.
4. Add full-detail API projection and a drawer section showing the phase as non-actionable context.
5. Do not promote W1/W2/W4/W5 to primary or alter lane mapping in this slice.

### Source implementation status — 2026-09-03

The bounded source slice is implemented in the canonical engine/contract/API
projection and `/mvp` drawer seams. `wave.daily_structure` is projected from
the existing full-wave Daily result, validated as an additive exact nested
envelope, and carried through list/detail parity with `actionability=NONE`.
Focused source and contract tests pass; runtime reload/public API and browser
evidence remain Lite acceptance work.

## Acceptance criteria

- [x] Every evaluated eligible row retains one canonical `wave.primary_state` and existing decision lane.
- [x] `wave.daily_structure.phase` is one Daily phase from the approved Wave 1–5/UNKNOWN vocabulary with explicit `actionability=NONE`.
- [x] The phase is produced from Daily evidence only; 60m setup cannot overwrite it.
- [x] Existing W3 raw finite `r<=0.60` publication gate remains unchanged; CRC/BGRIM remain fail-closed.
- [x] Full-detail canonical API exposes phase/evidence with explicit source timeframe and snapshot/as-of identity; list projection remains backward-compatible.
- [x] `/mvp` drawer shows `Daily structural context` separately from `Primary Daily Wave`, setup, and decision lane; no phase creates `REVIEW_NOW` or `AVOID`.
- [x] Tests cover primary/phase divergence, missing/unknown evidence, Daily-vs-60m separation, lane invariance, and API list/detail parity.
- [x] Public API and `/mvp` were rechecked after runtime reload; full universe remains `expected=evaluated=237` with pagination accounted for.

## Deferred

- Canonical promotion of W1/W2 states.
- Automatic phase-to-lane mapping.
- W4/W5 primary publication.
- Full historical fixture re-derivation and accuracy claims.
- Alerts, broker, auto-trading, evaluator auto-caller, and migrations.

## Required review evidence

Before implementation is promoted, Lite must separate source/tests, runtime/API, rendered UI, data coverage, and semantic/owner validation. A green additive test or an external model recommendation is not production acceptance. The next bounded decision after this slice is whether `WAVE_2_NEAR_COMPLETION` can enter `DAILY_CANDIDATE` under its own 30–60%, duration, and W1-low-hold contract.
