# Signalix VCP Decision Policy v2 Shadow — Design

> **STATUS: APPROVED FOR IMPLEMENTATION** · Owner approval: 2026-08-28
>
> **Scope:** Correctness, replay parity, and a non-serving shadow decision projection. Served v1 remains unchanged until acceptance passes.

## Goal

Separate VCP evidence discovery, setup quality, entry readiness, tradability, and presentation so useful events are retained without creating false confirmation.

## Current defects

1. Daily metrics are loaded without deterministic outer ordering; `latest_daily_close` can be the oldest selected row.
2. Replay omits Daily context and therefore does not exercise the same policy as the served Daily VCP Watchlist.
3. Standard replay outcomes can count a stop before the breakout entry was triggered.
4. The finder selects the first confirmed H-L-H-L-H sequence and exposes no candidate-sequence or active-sequence age evidence.
5. Daily Watchlist projection ignores `review_lane` evidence and applies liquidity as an irreversible backend eligibility gate although the product contract calls it removable.
6. `state`, `actionable`, `reviewable`, review lane, and extended semantics can contradict each other.
7. Ranking repeats hard-gated dimensions, while the existing risk/reward component uses pivot distance as reward without an authoritative target.

## Architecture

Keep `signalix/vcp-finder-60m-v1` and the served Daily VCP Watchlist intact. Add focused pure functions for deterministic Daily context/metrics, replay outcome evaluation, pivot-sequence evidence, and a versioned `signalix/vcp-decision-shadow-v2` projection. The shadow projection consumes existing result records and never mutates lifecycle state, persistence, or served v1 output.

## Decision dimensions

Every v2 shadow record has separate fields:

- `lifecycle_state`: existing VCP finder state.
- `decision_lane`: `REVIEW_NOW`, `PREPARE`, `EVENT_WATCH`, `RESEARCH`, `DO_NOT_CHASE`, or `DATA_BLOCKED`.
- `actionability`: `ACTIONABLE_REVIEW`, `WATCH_ONLY`, or `NO_ACTION`.
- `quality`: structural pass count and missing/failing evidence.
- `entry`: pivot distance, close/volume confirmation, invalidation coherence.
- `tradability`: average Daily value, marginable, price threshold, and explicit pass/fail reasons.
- `context`: Daily trend and fundamental fields as context only; neither promotes lifecycle state.
- `sort`: deterministic lane-local tuple; no synthetic risk/reward score.

## Lane contract

### REVIEW_NOW

Requires fresh usable data, non-extended/non-failed state, coherent invalidation, complete structural morphology, and either confirmed close+volume or an existing near-trigger/ready state close enough to its pivot. Tradability is reported separately and defaults may filter the served view later, but it does not erase the shadow candidate.

### PREPARE

Requires usable data and coherent risk with valid morphology or strong partial structure, but an entry confirmation remains missing. The record lists the exact missing evidence.

### EVENT_WATCH

Retains price/volume breakout, pivot-touch volume, close-breakout-volume-pending, and Daily-context watch evidence when morphology is incomplete. It is always `WATCH_ONLY` and never promotes `state` or `actionable`.

### Exclusions

- `EXTENDED` or `late_watch` → `DO_NOT_CHASE`.
- `FAILED` → `DO_NOT_CHASE` with invalidation reason.
- `STALE`/`NOT_VERIFIED` → `DATA_BLOCKED`.
- Remaining `FORMING` → `RESEARCH`.

## Tradability

`avg_trade_value_20 >= THB 10,000,000`, marginable membership, and `last_close > THB 0.60` are explicit independent fields. The v2 shadow pool retains failures. Any future API filter must apply explicit query parameters before lane caps so UI controls are genuinely removable.

## Sequence selection evidence

Enumerate every confirmed H-L-H-L-H window in the trailing pattern bars. For v2 diagnostics, choose the most recent non-broken sequence by final pivot index; expose candidate count, active pivot timestamps, final-pivot age, and selection rule. Do not replace v1 sequence selection until replay comparison passes.

## Replay parity

Replay must load point-in-time Daily trend context and Daily metrics, apply the same pure projection used by shadow/live policy, and persist policy versions. Standard-entry evaluation remains pending until a future bar first trades at or above entry; stops before entry are ignored. Low-Cheat keeps detection-close entry semantics. Outcomes are descriptive, not win rates.

## Ranking

Do not calculate an R/R value without an authoritative target. Sort within each lane by:

1. entry confirmation/proximity;
2. structural evidence completeness;
3. active-sequence recency;
4. liquidity as tie-breaker;
5. symbol as stable final tie-breaker.

## Acceptance

- Existing v1 focused tests remain green and served v1 payload remains contract-compatible.
- Daily loaders return latest close and chronological context deterministically.
- Replay and shadow use the same projection function and policy version.
- A Standard plan cannot stop or target before entry activation.
- Every shadow result has exactly one lane and one actionability value.
- `EXTENDED`, `FAILED`, `STALE`, and `NOT_VERIFIED` never enter `REVIEW_NOW` or `PREPARE`.
- Event lanes never become actionable solely from review evidence.
- Tradability failures remain present in shadow output.
- Full universe retention remains one result per eligible ORD symbol.
- No deployment or served-v1 switch occurs in this implementation slice.

## Non-goals

- No threshold optimization from a single sample.
- No fundamental hard gate.
- No alert delivery changes.
- No Docker deployment or production state mutation.
- No replacement of v1 until a separately approved acceptance decision.
