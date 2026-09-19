# Decide numeric readiness thresholds

- **Type:** `wayfinder:grilling`
- **Status:** `CLOSED — RESOLVED_BY_ARM`
- **blocked_by:** 03-policy-selection-and-robustness.md

## Resolution — 2026-09-06 ICT

These thresholds apply specifically to nomination for `SHADOW_READY`, not to every research candidate and not to production promotion:

- Minimum aggregate valid decided outcomes: **≥100**.
- Minimum valid decided outcomes per each of four stable symbol-fold cells: **≥10**.
- Positive-cell share at primary `3R / 50 bps`: **≥50%** (at least 2 of 4 cells).
- Aggregate holdout expectancy at primary `3R / 50 bps`: **≥+0.10R**.
- Maximum single-symbol concentration: **≤25%**.
- `TARGET_BELOW_ENTRY`, `AMBIGUOUS_SAME_BAR`, and `INSUFFICIENT_FUTURE_DATA`: no hard percentage floor yet; preserve and report each separately. `EXPIRED` remains a separate outcome category.
- Research candidates below these thresholds remain `RESEARCH_ONLY` / `INCONCLUSIVE`, not deleted.
- Production promotion requires additional cost-stressed portfolio replay, visual review, paper/shadow evidence, owner approval, and separate production gates.

**Decision status:** numeric shadow-readiness gate resolved by Arm. No production behavior changes.
