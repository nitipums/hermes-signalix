# Decide visual review and shadow-lane promotion gate

- **Type:** `wayfinder:prototype`
- **Status:** `CLOSED — APPROVED_BY_ARM`
- **blocked_by:** 03-policy-selection-and-robustness.md, 04-portfolio-replay-contract.md

## Prototype artifact — 2026-09-06 ICT

- Current SET buy-event v2: `/tmp/signalix_current_set_buy_event_review_v2.html` with separate `/tmp/signalix_current_set_buy_event_data.json`; 237 symbols and 2,961 historical buy-point events, filterable by `HIT TARGET`, `HIT STOP`, and other outcome statuses. Bars are stored once per symbol to keep HTML lightweight.
- Prototype behavior: policy selector, summary cards, fold/cell readiness view, evidence interpretation, and required chart-review placeholders.
- Honest states: missing portfolio expectancy and exact four-cell floor data render as `NOT VERIFIED`; no policy is labelled production-ready.
- Static verification: one inline script extracted; `node --check` passed; required labels and policy data present.
- Browser verification: `NOT VERIFIED` — browser harness CLI returned usage/error during two attempts, so DOM smoke and responsive browser acceptance were not completed.

## Resolution — 2026-09-06 ICT

Arm approved the evidence hierarchy shown by the throwaway dashboard.

A nominated policy's shadow evidence package must show:

- policy identity, playbook, policy hash, event-set hash, evaluator version, and declared scope;
- accepted events and valid decided outcomes, with all excluded/undecided statuses visible;
- expectancy in R, target-axis and cost-stress results, coverage, four-cell evidence, and symbol/sector concentration;
- explicit `PASS` / `FAIL` / `NOT VERIFIED` for every readiness gate;
- chart review for true positives, false positives, missed events, pivot failures, and worst cells;
- a clear distinction between research candidate, `SHADOW_READY`, and production status;
- expiry/disable and rollback metadata before any shadow exposure.

The first shadow surface remains isolated evidence only. It must not mutate `/api/setup-candidates`, `/mvp`, published Wave states, alerts, evaluator auto-caller, auto-trading, or broker execution. Production consideration requires a later owner decision and full source/tests/runtime/API/UI/data-lineage gates.

Prototype artifact: `/tmp/signalix_research_shadow_dashboard.html`.
Static/HTTP verification passed; browser smoke remained `NOT VERIFIED` because the browser harness returned a CLI usage error twice. This does not block approval of the information hierarchy, but it blocks claiming browser acceptance of the prototype.

**Decision status:** visual evidence hierarchy and shadow-lane boundary approved; implementation/integration remains not authorized.
