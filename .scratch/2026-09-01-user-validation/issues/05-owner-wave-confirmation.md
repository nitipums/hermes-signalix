# 05: Owner Wave-Identification Confirmation

**What to build:** Close the human semantic validation gate after Arm reviews representative charts and confirms or disputes the machine-generated Wave evidence. This is a review/decision ticket, not permission to tune labels ad hoc.

**Blocked by:** 04 — Multi-Timeframe Wave Evidence and Provisional Candles

**Status:** pending-owner-review

## Acceptance criteria

- [ ] Arm reviews representative KCE, IRPC, BCP, RCL, BBGI, and TASCO charts across relevant timeframes.
- [ ] Each example records the system interpretation, Arm's interpretation, exact evidence/snapshot identity, and agreement/disagreement.
- [ ] Disagreements are classified as data, mapping/presentation, or deterministic rule issues.
- [ ] No production Wave threshold or label is changed solely from a single subjective example.
- [ ] If a rule change is needed, open a new bounded grill/spec/ticket decision before implementation.
- [ ] Owner confirmation or unresolved disagreements are recorded in the current handoff and Product Feedback note.
