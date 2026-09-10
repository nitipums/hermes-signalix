# Wayfinder Map — Signalix Research to Promotion

## Destination

A durable, evidence-gated Research-to-Promotion system that identifies playbook-specific deterministic policies with real user value, tests them across declared time/universe/fold/cost conditions, validates them through portfolio replay and visual review, and exposes a winning policy first in an isolated shadow/evidence lane for Arm approval before any production promotion.

## Notes

- Domain: Signalix deterministic research, AutoResearch, replay, user-value evaluation, and controlled promotion.
- Planning only: this map does not authorize code changes, production changes, `/api/setup-candidates` changes, alerts, auto-trading, broker execution, or evaluator auto-caller wiring.
- Research authority: `/root/signalix/vault/Research-Index.md` and linked current research handoff/project documents.
- Product authority remains `vault/Product-Strategy-Market-to-Action.md`, `vault/Decisions.md`, and the current Elliott/Trend/Trade-Setup spec.
- Skills: wayfinder, grilling, domain-modeling, Signalix acceptance/data-lineage rules.
- Owner: พี่อาร์ม decides product scope and promotion; Lite is final quality gate.
- Local tracker: child tickets are in `tickets/`; `blocked_by` in ticket bodies represents dependencies because no native issue tracker is configured.

## Decisions so far

- **Destination definition**: optimize for a Research-to-Promotion system, not a single maximum-backtest formula.
- **User-value definition**: prioritize setup quality usable for Arm review, measured across multiple dimensions rather than return alone.
- **First promotion surface**: isolated shadow/evidence lane; canonical production spine remains unchanged until a later explicit approval.
- **Policy unit**: keep formulas/playbooks separate (`WAVE2_CONTINUATION`, `52W_HIGH_BREAKOUT`, `WAVE1_PICKUP`, `WAVE3_CONTINUATION`); do not force one universal formula.
- **User-value scorecard**: primary metric is expectancy per 1R after explicit cost/slippage; quality and coverage are separate dimensions; no fixed numeric sample floor is locked yet.
- **Outcome denominator**: use valid decided outcomes only for expectancy/win rate; report `TARGET_BELOW_ENTRY`, `AMBIGUOUS_SAME_BAR`, `INSUFFICIENT_FUTURE_DATA`, and `EXPIRED` separately according to their meanings.
- **Policy selection protocol**: read train/validation only; lock holdout from ranking and mutation; compare within playbook and declared entry semantics; preserve separate 237/active-ORD/broad scopes; use era and stable SHA-256 symbol folds, cost stress, non-dominated evidence, concentration, and outcome completeness. Holdout deterioration is an overfit finding.
- **Portfolio replay contract**: initial run is gross/no-cost, unconstrained all-signal diagnostic mode with equal 1R risk; report overlap, capital demand, equity curve, geometric growth, drawdown, losing streak, turnover, and concentration. Cost-stressed rerun remains mandatory before shadow/promotion. Joint entry/exit optimization is a separate policy family with fixed-exit baseline comparator.
- **Numeric `SHADOW_READY` gate**: aggregate valid decided outcomes ≥100; every four symbol-fold cells ≥10; ≥50% positive cells (≥2/4) at 3R/50 bps; aggregate holdout expectancy ≥+0.10R at 3R/50 bps; top-symbol concentration ≤25%; invalid/undecided statuses reported separately with no hard percentage floor yet. Below gate remains research-only.
- **Visual evidence + shadow contract**: approved hierarchy shows policy identity/hashes, valid outcomes plus exclusions, R expectancy/cost/coverage/fold/concentration, explicit PASS/FAIL/NOT VERIFIED gates, true/false/missed/pivot-fail/worst-cell charts, research-vs-shadow-vs-production distinction, expiry/disable/rollback. Shadow remains isolated and cannot mutate production surfaces.
- **Production boundary**: Wave remains machine-generated candidate/evidence; alerts, auto-trading, broker execution, and evaluator auto-caller remain OFF/PENDING.
- **Existing evidence boundary**: broad baseline is research PASS, tuning is PARTIAL, 52W is promising, Wave-1 is audit-only, Wave-2/Wave-3 are scope-dependent, and portfolio replay is not started.

## Not yet specified

- Exact bounded search space and mutation rules for the new joint entry/exit policy family.
- Capacity-constrained portfolio view after the initial unconstrained diagnostic replay.
- Exact chart sampling algorithm and durable artifact archive/checksum location.
- Shadow observation window, review cadence, expiry/disable mechanics, and owner operating workflow.
- Production promotion checklist details after shadow evidence exists; this remains a new owner decision, not implied by `SHADOW_READY`.

## Next execution boundary

The decision route is clear. The next work is implementation/research execution, not another product-direction decision:

1. Correct and test the immutable AutoResearch runner; unsupported cycles remain `NOT_IMPLEMENTED`.
2. Run the initial gross/no-cost unconstrained portfolio diagnostic for the strongest non-dominated playbook candidates.
3. Add the mandatory 25/50 bps cost-stressed replay and capacity-constrained comparison.
4. Generate the approved visual evidence package from real replay outputs.
5. Evaluate `SHADOW_READY`; only then ask Arm for a separate shadow implementation decision.

These are not authorized by this map itself. They require separate bounded execution scopes and remain outside production.

## Out of scope

- Immediate changes to `/api/setup-candidates`, `/mvp`, or published Wave states.
- Live alerts, automatic trading, broker execution, or portfolio action.
- A universal formula or LLM-generated executable signal/order.
- Treating event-level target-before-stop as portfolio growth.
- Pooling current 237 retrospective results with broad historical 1,219-symbol results.

## Open tickets

See child tickets in `tickets/`. Work one decision at a time after dependencies are resolved.
