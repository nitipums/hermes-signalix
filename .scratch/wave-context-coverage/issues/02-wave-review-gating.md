# 02: Wave 1/3/5 review gating

**What to build:** Make Wave 1, Wave 3, and Wave 5 coverage candidates eligible for `REVIEW_NOW` only when the existing deterministic setup, risk, freshness, and completed-60m confirmation gates pass. Keep Wave 2, Wave 4, and unknown context visible but non-actionable.

**Blocked by:** 01: Wave context contract + evidence

**Status:** DONE (source/test) — runtime/API/UI NOT VERIFIED; implementation commit pending promotion

- [x] Wave 1/3/5 can reach `REVIEW_NOW` only through the same setup/risk/freshness/60m gates used by the canonical decision flow.
- [x] Wave 2 and Wave 4 context cannot create `REVIEW_NOW` or any executable/actionable recommendation.
- [x] Data blocked, stale, invalid, incoherent-risk, insufficient, and materially ambiguous rows fail closed regardless of Wave context.
- [x] Extended Wave 3 remains secondary and applies explicit do-not-chase/risk evidence; it does not bypass gates.
- [x] Regression tests cover each Wave group, gate failure, stale/blocked data, and a successful Wave 1/3/5 review path.
- [x] Existing decision lanes and lifecycle boundaries remain compatible; alerts, auto-trading, and broker execution stay off.

**Authority:** `docs/superpowers/specs/2026-09-02-wave-context-coverage-design.md`, current setup-candidate design, `vault/Execution-Pipeline.md`.
