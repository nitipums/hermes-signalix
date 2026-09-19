# Decide user-value scorecard and sample floors

- **Type:** `wayfinder:grilling`
- **Status:** `CLOSED — RESOLVED_BY_ARM`
- **blocked_by:** none

## Question

What measurable definition of setup quality makes AutoResearch useful to Signalix users and Arm review? Decide the primary and guardrail metrics, minimum event/fold/symbol samples, acceptable coverage, false-positive burden, freshness requirements, and how metrics are reported without collapsing them into one misleading score.

## Resolution — 2026-09-06 ICT

- Primary user-value metric: expectancy per 1R after explicit cost/slippage.
- Sample floor: no fixed numeric floor yet; sample sufficiency remains an explicit warning/decision dimension rather than a hard number at this stage.
- Coverage: report quality and coverage separately; do not prefer signal count or pool low-coverage/high-quality policies with high-coverage policies.
- Denominator: calculate expectancy/win rate only from valid decided outcomes. `TARGET_BELOW_ENTRY`, `AMBIGUOUS_SAME_BAR`, and `INSUFFICIENT_FUTURE_DATA` are excluded from the denominator and reported separately. `EXPIRED` remains a separate outcome category.
- Owner decision: Arm approved option A for the denominator rule.
