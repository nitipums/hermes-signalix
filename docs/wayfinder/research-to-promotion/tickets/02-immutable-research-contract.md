# Decide immutable evaluator and policy boundary

- **Type:** `wayfinder:research`
- **Status:** `CLOSED — RESOLVED_BY_LITE`
- **blocked_by:** none

## Resolution — 2026-09-06 ICT

### Immutable harness boundary

- Data snapshot/window and universe resolver.
- Strict no-lookahead and right-hand pivot confirmation.
- Event labels, entry semantics, signal/entry bar separation, and event identity.
- Stop/target/outcome evaluator, including same-bar ambiguity and 120-bar horizon.
- `TARGET_BELOW_ENTRY`, `AMBIGUOUS_SAME_BAR`, `EXPIRED`, `INSUFFICIENT_FUTURE_DATA`, `TARGET`, and `STOP` status semantics.
- Cost axes `0/25/50 bps` and target axes `[2.5, 3, 3.5, 4, 5]R`; axes cannot alter event construction or policy selection.
- Locked train/validation/holdout manifest and holdout lock assertions.

### Mutable policy boundary

- Versioned, complete, hashed playbook-specific policy JSON only.
- Explicit structural, indicator, volume, entry, lookback, ATR, stop, and cooldown overrides allowed by playbook.
- Unsupported or unwired overrides are an error / `NOT_IMPLEMENTED`, never a silent no-op.
- Every run records policy hash, event-set hash, result signature, evaluator version, scope, folds, and status.

### Required separation

Detector materializes and hashes the immutable event population first; policy filters operate afterward. W2, W3, and 52W event sets remain separate. The prior W2 candidate `marsi_65_-0.1` remains an immutable comparator. For 52W, same-day-close and next-day-open populations retain separate signal/entry indices and reports.

### Evidence basis

The Codex correction brief identified silent W2/W3 structural and MACD/volume no-ops, missing date matches mapping to index zero, incomplete 52W signal/entry schema, incomplete outcome accounting, duplicate signatures, and implicit holdout locking. These are contract failures that block any claim of a valid tuning winner until corrected.

**Decision status:** contract resolved; implementation and long-run rerun remain `NOT STARTED / RESEARCH_ONLY`.
