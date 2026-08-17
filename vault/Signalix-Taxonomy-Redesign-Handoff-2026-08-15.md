# Signalix Taxonomy Redesign Handoff — 2026-08-15

## Outcome
Completed a full-universe review and presentation redesign for all 718 active TH ORD symbols.

## Review loop
- Mali: read-only user/product semantics review, 718/718 rows.
- Ploy: read-only market-structure/taxonomy review, 718/718 rows.
- Nida: read-only state-contract/canonical-lineage audit, 718/718 rows.
- Khim: implementation owner; reconciled symbol-by-symbol and implemented the presentation projection.
- Bee: synthesis, routing, verification, and final quality gate.

## Reconciled primary groups
- pre_break: 349
- no_long_setup: 200
- base: 113
- pullback_holding: 28
- pullback_under_reference: 5
- fresh: 9
- extended: 9
- failed_setup_no_event: 5
- Total: 718, exactly once

Fresh and extended are separate. No-long setup is distinct from failed setup without event. Pullback holding is distinct from under-reference. Quality, freshness, lifecycle, and confidence are independent badges rather than primary groups.

## Badge counts
- low_quality: 611
- stale: 29
- confidence: high 350, medium 339, low 29
- current confirmed_failure: 0

## User-facing/operational fixes
- Card and detail now show the same quality/freshness/lifecycle/confidence badges.
- Stale provenance shows source, as-of date, freshness status, and reason; AMARIN was verified.
- Mobile detail modal overflow fixed: viewport 390px had body/document width 390 and modal width 388, with no horizontal overflow.
- Backend readiness separated from the large snapshot endpoint using `/health/readiness`; two workers and gzip keep readiness responsive. Docker services were healthy at final check.

## Verification
- Final container unittest: 96 passed.
- `/health` and `/health/readiness`: HTTP 200, DB/Redis up.
- `/dashboard/snapshot`: HTTP 200, 718 items, projection `reconciled-taxonomy-v1`.
- 1D chart: HTTP 200; retired 15m chart: HTTP 400.
- Desktop/mobile browser checks passed for primary groups, RCL, AMARIN, and responsive modal.
- Raw/canonical history was not changed; prior invariants remained: raw runs 196, canonical runs 108, events 420, event observations 5,587, with canonical mismatch/orphan checks clean.

## Stop/close procedure
Before closing this session, stop the temporary browser processes, Signalix containers, Hermes profile gateways, and pause scheduled jobs. Do not modify system daemons.

## Durable lessons
1. Use one authoritative primary group per symbol and orthogonal badges.
2. Historical events provide context only; they must not override current producer state.
3. `confirmed_failure` requires a current persisted failed event.
4. Never claim UI readiness from static/API evidence alone; verify rendered desktop and mobile journeys.
5. A large dashboard snapshot must not be used as the container readiness probe.

Level 2 raw session state is retained automatically by Hermes; this note is the curated Level 4 handoff.

## Pending follow-up — IN PROGRESS (resumed 2026-08-15)
Arm approved the follow-up taxonomy repair; rescope after Mali read-only review (2026-08-15):
- Exclude index/benchmark symbols from stock lifecycle: explicit allowlist `SET`, `SETCLMV`, `SET50`, `SET100`, `sSET`, plus any `instrument_type='INDEX'`. They must never render as `pre_break`/`base`/`breakout_setup`; retain as benchmark only.
- Base fallback guard: when `conditions_met`/RS fail floors, or `rsi_daily` <= invalidation, or `close` <= failure/invalidation level, map to `no_long_setup`/`down_or_broken`, not `base`. Verify JAS, AAV, CPAXT, LH, M, MAJOR.
- Corrected finding: BH (close 195 vs trigger 194, +0.51%) and SC (close 2.06 = trigger 2.06, +0.00%) are BELOW the `>=1.01x + vol>=1.2x` fresh gate, so their `PRE-BREAK`/`breakout_setup` is deterministic-correct — do NOT force them to fresh.
- Served pipeline must apply `active_breakout_events()` (so SC/LH reflect historical events) exactly like backfill run `02fccb74`; served run `54350e24` currently omits events. Events stay immutable; never infer failure without `close < failure_level`.
- Clarify user-facing wording: `pullback_under_reference` ("trading below its pullback reference; only a defended hold + 1H higher low re-qualifies") and `no_long_setup` ("no qualified long setup active; do not force a trade — wait for a new structure or a confirmed breakout after failure").

Ownership: Khim implements/tests/deploys; Nida and Mali review read-only; Bee is final quality gate. Status: Mali review done; Khim implementing.
