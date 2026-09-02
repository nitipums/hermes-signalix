# 04: Visual Wave context dashboard

**What to build:** Keep `/mvp` as the Classic Review surface and add a dedicated `/wave-context` chart-first surface using the same canonical API/engine/decision lanes. The new route shows the complete Wave context in a readable chart-first experience: Daily price line/high-low, exact Wave markers, legend, context/secondary labels, transition detail, and review-lane status. Wave 1/3/5 actionability must visibly remain dependent on setup/risk/60m gates; Wave 2/4 remain non-filter context.

**Blocked by:** 02: Wave 1/3/5 review gating; 03: Full-universe replay + coverage parity

**Status:** DONE (source/test) — runtime/public browser NOT VERIFIED; implementation commit pending promotion

- [x] Chart uses authoritative Daily source and exact `as_of`/close marker coordinates; source timeframe is explicit.
- [x] Wave 1/2/3/4/5/unknown and `WAVE_3_EXTENDED` secondary marker have distinct readable colors/labels.
- [x] Selecting a stock exposes final state/context, confidence, first/last context dates, all transitions, and supporting/contradicting/missing evidence.
- [x] Wave 1/3/5 review eligibility and Wave 2/4 non-actionability are visible and cannot be inferred from color alone.
- [x] Desktop and 390px mobile layout have no horizontal overflow; labels/legend/table remain inspectable.
- [ ] Happy path, drawer/chart path, stale/blocked/unknown path, and browser console/page-error checks pass on the actual served route. (NOT VERIFIED pending promotion)
- [x] No generated artifact is hand-edited; runtime/API/UI verdicts are recorded separately from source/test PASS.

**Authority:** `docs/superpowers/specs/2026-09-02-wave-context-coverage-design.md`, `vault/Browser-and-Freshness-Verification.md`, current UI validation specs.
