# 01: Wave context contract + evidence

**What to build:** Extend the canonical setup-candidate evidence so Arm can see the broader Daily structural context—Wave 1, Wave 2, Wave 3 early/continuation, Wave 4, Wave 5, and explicit unknown—without creating a competing primary decision label. Preserve the current structural Wave vocabulary and represent `WAVE_3_EXTENDED` only as a secondary context/risk marker.

**Blocked by:** None (can start immediately)

**Status:** DONE (source/test) — runtime/API/UI NOT VERIFIED; implementation commit pending promotion

- [x] Current engine structural output remains canonical and invalid values fail closed to `UNKNOWN`.
- [x] Context/secondary evidence preserves supporting, contradicting, missing, confidence, source timeframe, and rule version.
- [x] `WAVE_3_EXTENDED` never appears as a structural state or primary decision label.
- [x] Wave 1/2/3/4/5/unknown fixtures cover valid, insufficient, ambiguous, and contradictory evidence.
- [x] Candidate builder/projection and canonical validator agree on the exact envelope; no legacy competing primary field is introduced.
- [x] Focused tests and `git diff --check` pass; no DB/deploy/runtime side effects.

**Authority:** `docs/superpowers/specs/2026-09-02-wave-context-coverage-design.md` (draft approved by Arm), current Elliott design, `AGENTS.md`.
