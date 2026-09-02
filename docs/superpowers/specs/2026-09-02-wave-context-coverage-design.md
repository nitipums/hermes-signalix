# Signalix Wave Context Coverage and Review Gating

> **STATUS: DRAFT FOR OWNER REVIEW** · 2026-09-02 ICT
> This draft follows the owner-approved Wave context prototype/replay and is not a production contract yet.

## Problem Statement

The current Signalix surface is useful for Wave 3 candidates but does not make the broader rising structure legible. A stock may be rising while the engine's current candidate is Wave 1, Wave 3 continuation/extended, or Wave 5. Without those context groups, the review surface can look incomplete and the owner cannot distinguish an early rise, a late rise, a correction, or a sideways phase from the chart itself.

## Solution

Extend the candidate evidence and review surface so the owner can see the complete Daily structural context while preserving conservative actionability. The canonical structural state remains Wave 1–5 plus `UNKNOWN`. A display/context layer records the mapped context and supporting/contradicting/missing evidence. `WAVE_3_EXTENDED` remains a secondary marker, not a structural enum value.

Wave 1, Wave 3, and Wave 5 are coverage candidates. Any of them may reach `REVIEW_NOW` only when the existing deterministic setup, risk, freshness, and completed-60m confirmation gates pass. Wave 2 and Wave 4 remain visible context but cannot create actionability. Context never overrides data blocking, structural invalidation, risk incoherence, or owner review.

The review UI uses the owner-approved visual format: real Daily price chart, exact date/close markers, transition details, per-symbol selection, and explicit filter/lane status. It is evidence for Arm, not objective Elliott truth or an order instruction.

## User Stories

1. As Arm, I want to see Wave 1 rising stocks, so that early advances are not invisible merely because they are not Wave 3.
2. As Arm, I want to see Wave 2 pullbacks, so that a rising thesis can be reviewed near a possible continuation without treating the pullback as actionable.
3. As Arm, I want to see Wave 3 early and continuation candidates, so that the existing primary review workflow remains visible.
4. As Arm, I want extended continuation marked separately, so that late/extended price action can be reviewed with do-not-chase and risk context.
5. As Arm, I want Wave 4 sideways/correction context, so that stalled or corrective stocks are distinguishable from missing data.
6. As Arm, I want Wave 5 rising context, so that late-cycle advances are visible but not confused with a fresh Wave 3.
7. As Arm, I want ambiguous or insufficient cases to fail closed, so that additional labels do not create false precision.
8. As Arm, I want the chart to place each marker on the exact Daily date and close that produced the observation, so that I can compare the label with the price action.
9. As Arm, I want every chart marker to expose the underlying transition, confidence, and missing/contradicting evidence, so that I can challenge the machine interpretation.
10. As Arm, I want Wave 1/3/5 actionability to remain dependent on setup, risk, freshness, and completed 60m gates, so that context coverage does not weaken trade safety.
11. As Arm, I want the dashboard to state the replay window, policy version, universe, and no-lookahead boundary, so that chart evidence is reproducible.
12. As an operator, I want the existing 237-symbol marginable universe and full-universe accounting preserved, so that coverage expansion does not silently drop symbols.

## Implementation Decisions

- Use one primary seam at the canonical candidate builder/projection decision boundary.
- Preserve the existing structural Wave state vocabulary. Do not add `WAVE_3_EXTENDED` to the structural enum.
- Add a nested/contextual evidence representation for mapped display context, secondary markers, and rationale. The exact canonical field name is to be chosen during implementation against the current envelope authority; no competing top-level primary state is allowed.
- Keep the existing `decision_lane` vocabulary. Wave 1/3/5 can qualify for `REVIEW_NOW` only after the existing setup/risk/60m gates; Wave 2/4 and `UNKNOWN` cannot qualify from context alone.
- Wave 5 must be supported by the engine's ordered prior structure and exhaustion/late-cycle evidence. It must never be inferred from price being high, a 52W/ATH breakout, or a single strong candle.
- Extended continuation is a secondary risk/context marker over canonical Wave 3 continuation. It must remain separate from structural state and must not bypass freshness, risk, or do-not-chase checks.
- Daily remains the source of Wave context. 60m remains separate confirmation/entry timing evidence; no cross-timeframe wave count is implied.
- The chart review artifact must use actual Daily OHLC rows and exact `as_of`/close marker coordinates. Stable-run markers may reduce visual clutter, while a detail table retains every transition.
- Replay must remain point-in-time (`date <= as_of`), read-only, append-free, and report universe/evaluated/coverage counts and rule version.
- The accepted visual dashboard format is a required acceptance artifact for replay review, not merely a convenience report.

A decision-rich prototype rule remains exploratory until promoted:

```text
structural_state = canonical Wave 1–5 | UNKNOWN
context = mapped display marker
review_now = structural_state in {Wave 1, Wave 3, Wave 5}
             AND setup/risk/freshness/completed-60m gates pass
             AND data is not blocked or materially ambiguous
```

## Testing Decisions

- Test external behavior at the candidate builder/projection seam and the served UI contract, not internal helper implementation details.
- Add contract tests for context preservation, no competing primary state, Wave 3 extended as secondary only, Wave 1/3/5 lane gating, Wave 2/4 non-actionability, and fail-closed ambiguity/data blocking.
- Add replay tests using the existing SELECT-only loader with exact prefix boundaries, expected universe metadata, deterministic rule version, stable ordering, and no-lookahead assertions.
- Add representative fixture tests for Wave 1, Wave 2, Wave 3 early/continuation/extended, Wave 4 sideways/correction, Wave 5, and UNKNOWN.
- Add rendered chart acceptance for exact marker date/close, source timeframe labels, readable legends, transition details, desktop/mobile containment, and the real card/chart review journey.
- Re-run full relevant backend/frontend suites and separate source, runtime/API, and browser verdicts. Existing replay/chart results are evidence inputs, not proof of production readiness.

## Out of Scope

- Automatic trading, broker orders, alerts, evaluator auto-caller, or policy auto-tuning.
- Replacing the existing Wave engine with a new independent classifier during this slice.
- Treating Wave labels as objective truth or personalized investment advice.
- Making Wave 2 or Wave 4 actionable from context alone.
- Deleting VCP compatibility/audit routes or historical artifacts.
- Production deployment, database migration, or runtime restart before implementation and acceptance gates are complete.

## Further Notes

- Owner-labelled examples from the replay are validation inputs, not hard-coded expected truth.
- The prototype/replay currently shows useful Wave 1 and Wave 5 populations but also meaningful UNKNOWN and transition churn; threshold tightening or hysteresis changes require a new bounded replay and owner chart review.
- The current prototype branch and `/tmp` replay/dashboard artifacts remain historical evidence until the spec is approved and implementation is independently accepted.
