# 03: Full-universe replay + coverage parity

**What to build:** Validate the Wave context and review-gating change across the complete `marginable_long` universe, preserving explicit coverage for all 237 eligible symbols and distinguishing no data, insufficient evidence, ambiguity, and non-actionable context. Demonstrate point-in-time parity and identify false positives, missed candidates, and marker churn before promotion.

**Blocked by:** 01: Wave context contract + evidence; 02: Wave 1/3/5 review gating

**Status:** ready-for-agent

- [ ] Replay resolves active Thai ORD → owner marginable → `can_buy=true` and reports base, eligible, excluded, evaluated, and returned counts.
- [ ] Every eligible symbol is retained in accounting; missing/invalid/insufficient rows have explicit status/reason and are not silently dropped.
- [ ] Daily replay enforces `date <= as_of`, deterministic ordering, exact policy/rule version, and no lookahead.
- [ ] Compare old/current behavior against owner-labelled examples and report Wave 1/2/3/4/5/unknown counts, transitions, ambiguity, and extension evidence.
- [ ] Generate the visual HTML replay dashboard with real-price charts and exact date/close markers; preserve raw JSON manifest under `/tmp`.
- [ ] Full replay acceptance remains separate from production promotion; no production DB writes or policy tuning from one sample.

**Authority:** `docs/superpowers/specs/2026-09-02-wave-context-coverage-design.md`, `finance:signalix-screening-replay`, current universe/acceptance notes.
