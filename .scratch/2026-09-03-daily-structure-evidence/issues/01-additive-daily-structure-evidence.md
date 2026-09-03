# 01: Additive Daily structural evidence in the canonical MVP

**What to build:** Restore useful Daily Wave 1/2/4/5 structural visibility on the canonical `/mvp` review surface without creating a second decision authority. Each candidate keeps its existing canonical W3/NOT_VERIFIABLE primary state and decision lane, while the detail view exposes a clearly labelled non-actionable Daily structural phase with dated anchors, confidence, retracement, source/as-of, and missing/contradicting evidence.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Every evaluated `marginable_long` row retains exactly one canonical `wave.primary_state` and existing decision lane.
- [ ] An additive `wave.daily_structure` object exposes one Daily phase from the approved Wave 1–5/UNKNOWN vocabulary with explicit `actionability=NONE`.
- [ ] The phase is produced from Daily evidence only; 60m setup cannot overwrite it.
- [ ] Existing W3 raw finite `r<=0.60` publication gate remains unchanged; CRC/BGRIM remain fail-closed.
- [ ] Full-detail canonical API exposes phase/evidence with explicit source timeframe and snapshot/as-of identity; list projection remains backward-compatible.
- [ ] `/mvp` drawer shows `Daily structural context` separately from `Primary Daily Wave`, setup, and decision lane; no phase creates `REVIEW_NOW` or `AVOID`.
- [ ] Tests cover primary/phase divergence, missing/unknown evidence, Daily-vs-60m separation, lane invariance, and API list/detail parity.
- [ ] Public API and `/mvp` are rechecked after runtime reload with expected/evaluated/returned counts preserved.
