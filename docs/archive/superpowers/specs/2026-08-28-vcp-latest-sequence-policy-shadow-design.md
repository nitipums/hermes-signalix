# Signalix VCP Latest-Sequence Policy Shadow — Design

> **STATUS: APPROVED FOR IMPLEMENTATION** · Owner approval: 2026-08-28
> **Boundary:** replay-only shadow. Served `signalix/vcp-finder-60m-v1` remains unchanged.

## Goal

Recompute VCP morphology, pivot, invalidation, entry, state, and future outcomes from the latest non-broken confirmed H-L-H-L-H sequence, then compare it point-in-time with the legacy first-sequence v1 policy.

## Evidence motivating the change

The 38-snapshot replay `vcp-shadow-v2-multi-day-20260828` retained 35,378 full-universe rows. Among rows with a latest-non-broken sequence, v1 and latest-sequence final pivots differed in 29,108/29,309 cases (99.31%). The existing diagnostic does not recompute state or outcomes, so it cannot authorize a v1 switch.

## Architecture

Keep the existing v1 calculations byte-for-byte compatible. Extend `find_vcp_60m()` with an optional `include_sequence_policy_shadow=False` argument. Only replay sets it to true. When enabled, a pure helper evaluates the latest non-broken candidate sequence using the same point-in-time `work` bars, 60m trend evidence, ATR, volume, and thresholds already available to v1.

The result is stored at `sequence_policy_shadow_v2` and never replaces top-level v1 fields. Replay creates and evaluates a separate standard-entry trade plan under `sequence_v2_trade_plan` and `sequence_v2_replay_evaluation`.

## Selection rule

1. Enumerate every confirmed five-pivot H-L-H-L-H window from trailing pattern bars.
2. Reject a candidate if current point-in-time close is below its second pullback low (`seq[3].price`).
3. Select the surviving candidate with the greatest final-pivot index.
4. If no candidate survives, emit `NO_ACTIVE_SEQUENCE`; do not fall back to v1.

Pivots remain confirmed with existing `pivot_left=2`, `pivot_right=2`; no future bars beyond `as_of` may enter the frame.

## Recomputed evidence

For the selected sequence, recompute independently:

- two pullback depths and contraction ratio;
- base start/end, base high/low, and base depth;
- latest contraction;
- pullback-leg average volumes and non-increasing-volume pass;
- recent volume dry-up;
- pivot, structural invalidation, distance to pivot, required breakout close;
- close confirmation and breakout-volume confirmation;
- complete morphology (`trend + contraction + base + leg volume`);
- lifecycle state using the existing thresholds: FAILED, CONFIRMED, EXTENDED, NEAR_TRIGGER, READY, FORMING, STALE;
- review lane and explicit reason codes.

## Type and entry boundary

- A complete morphology is tagged `standard_vcp`; standard entry is the required breakout close and stop is structural invalidation.
- Low-Cheat remains blocked from promotion in this slice. The shadow may report whether numeric Low-Cheat conditions are observed, but it must set `promotion_allowed=false` and must not create a Low-Cheat trade plan.
- Standard future evaluation begins only after a bar trades at or above entry. Stops before activation are ignored; same-bar stop/target remains ambiguous.

## A/B result contract

Each replay result may contain:

```text
sequence_policy_shadow_v2
  policy_version
  selection
  state
  morphology
  price
  pattern
  volume
  breakout
  reason_codes
  standard_entry_eligible
sequence_v2_trade_plan
sequence_v2_replay_evaluation
```

A/B summaries report v1 and sequence-v2 independently:

- first event count by symbol/policy;
- entry activated/not activated;
- target/stop/open/ambiguous;
- time/bars to entry;
- state and pivot divergence;
- invalidation/entry distance;
- sequence age;
- full-universe retention and no-lookahead coverage.

These are descriptive outcomes, never called a win rate.

## Acceptance

- Served v1/API payload contains no `sequence_policy_shadow_v2` field.
- Existing v1 focused and full backend tests remain green.
- With the optional flag off, `find_vcp_60m()` output remains unchanged except no new fields.
- With the flag on, selected sequence is latest non-broken and all v2 fields are JSON-safe.
- v2 pivot/state/invalidation are calculated from the selected sequence, not copied from v1.
- Low-Cheat never creates a sequence-v2 trade plan.
- Replay persists separate v1 and v2 outcomes without double counting.
- One-day replay passes before expanding to the existing 38-snapshot window.
- No deploy or served-policy switch occurs without a separate owner decision.
