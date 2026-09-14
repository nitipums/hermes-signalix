# Decide policy selection across time and universe

- **Type:** `wayfinder:research`
- **Status:** `CLOSED — RESOLVED_BY_LITE`
- **blocked_by:** 01-user-value-scorecard.md, 02-immutable-research-contract.md

## Resolution — 2026-09-06 ICT

- Policy selection may read train and validation only. Locked holdout results cannot rank, tune, threshold-select, or mutate a policy.
- Every policy is compared within its own playbook and declared entry semantics. W2/W3/52W are never pooled into one champion score.
- Every report keeps these scopes separate: current 237 retrospective, active ORD audit, and broad historical data-available universe. No cross-scope pooled verdict.
- Robustness is reported across explicit eras and stable SHA-256 symbol-disjoint folds, plus cost axes. A validation winner that degrades on holdout is an overfit finding, not a champion.
- Candidate selection should use non-dominated evidence across expectancy, cost stress, coverage, cell consistency, concentration, and outcome completeness rather than a single validation rank.
- Policies with unsupported fields, duplicate policy/event/result signatures, insufficient evidence, or invalid outcome accounting are rejected or marked `NOT_IMPLEMENTED` / `INCONCLUSIVE`.
- The existing evidence supports further bounded research but does not establish a production champion: `marsi_65_-0.1` holdout was 47.66% valid decided rate versus 56.06% validation; `marsi_60_0` holdout was 51.48% and 48.43% under 50 bps stress.

### Newly surfaced decision

Numeric readiness/promotion thresholds remain owner decisions and must be specified before a policy can enter the shadow lane. This is graduated to `Decide numeric readiness thresholds`.
