# Decide portfolio replay semantics

- **Type:** `wayfinder:research`
- **Status:** `CLOSED — RESOLVED_BY_ARM`
- **blocked_by:** 01-user-value-scorecard.md, 02-immutable-research-contract.md, 03-policy-selection-and-robustness.md

## Resolution — 2026-09-06 ICT

- Initial portfolio replay is an **unconstrained event-portfolio diagnostic mode**: accept every signal, including overlapping positions and multiple positions per symbol. It must report concurrent positions, capital/risk demand, overlap, and concentration; it must not be called deployable portfolio capacity.
- Each accepted trade uses equal 1R risk. Results are first reported in R units and are not connected to real money, broker accounts, or execution.
- Entry, stop, and target evaluation uses the declared event semantics and strictly later bars. No hindsight fills or Daily intrabar interpolation. 52W same-day-close and next-day-open remain separate populations.
- The first replay run uses **no cost** (`gross diagnostic mode`) by owner decision. It is not sufficient for shadow or promotion. Later readiness must rerun the same portfolio contract with explicit fee/slippage stress, including the existing 25/50 bps axes, without changing event construction.
- AutoResearch may optimize entry and exit jointly as a **separate exit-policy family**. The fixed structural stop/fixed target-axis baseline remains an immutable comparator; joint entry/exit results must not be pooled with the baseline or use realized outcomes to alter target axes.
- Portfolio outputs include equity curve, geometric growth, max drawdown, losing streak, turnover, overlap/capital demand, cost scenarios when enabled, and symbol/sector concentration. Event-level target/stop rates remain separate and are never labelled portfolio returns.

**Decision status:** portfolio replay contract resolved for the initial gross diagnostic mode; cost-stressed replay, capacity-constrained mode, and joint entry/exit research remain later gates. No production change.
