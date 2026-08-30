# Marginable Long Replay — Design

> **STATUS: PROPOSED — AWAITING OWNER REVIEW**
> **Owner:** Arm
> **Orchestrator/final gate:** Lite
> **Authority:** `vault/Execution-Pipeline.md`, `vault/Decisions.md`, and this owner-approved scope change

## Goal

Create a reversible, explicit `marginable_long` universe mode for the research replay so Signalix scans and replays only active Thai ORD symbols on the current owner-supplied marginable list with `can_buy=true`, reducing the operational universe from 931 to 237 symbols while preserving provenance for excluded symbols.

## Locked product boundary

```text
active Thai ORD symbol_master
→ current marginable dataset
→ instrument_type=ORD
→ can_buy=true
→ marginable_long universe
→ 60m VCP evaluation sampled once or twice per trading day
→ replay-only timeline and outcomes
```

- The 60m VCP finder remains the setup/morphology authority.
- Daily EOD remains supporting context and lifecycle evidence.
- Replay remains research-only and does not replace served v1.
- Low-Cheat remains non-promoting with `promotion_allowed=false`.
- No alerts, automatic orders, threshold changes, or v1 policy switch are included.

## Universe contract

The resolver must intersect three authoritative conditions:

1. `symbol_master.instrument_type = 'ORD'`;
2. `symbol_master.status IS NULL OR status = 'active'`;
3. `marginable_securities.json` record has `instrument_type='ORD'` and `can_buy=true`.

Current validated dataset:

- Marginable dataset: `signalix.marginable.v1`;
- source effective date: `2026-08-25`;
- active ORD universe: 931;
- eligible `marginable_long`: 237;
- excluded active ORD: 694;
- no current marginable ORD record falls outside active ORD.

The resolver must return a deterministic sorted list and a manifest containing:

```text
universe_filter = marginable_long
eligible_count = 237
base_active_ord_count = 931
excluded_count = 694
margin_schema_version = signalix.marginable.v1
margin_source_document
margin_effective_date
```

Excluded symbols are not scanner failures. They must be represented in the run summary/manifest as `excluded_by_universe_filter`; their exclusion must not silently mutate historical full-ORD records.

## Replay cadence

Support a daily-cadence mode over stored 60m bars:

- one snapshot per completed trading date at the latest available 60m timestamp; or
- two snapshots per completed trading date, selecting the latest available bar at or before Bangkok cutoffs of 12:30 and 16:45.

The two-snapshot mode is the pilot default because it exposes both intraday setup evolution and EOD state without the cost of every-60m replay. Snapshot selection must be deterministic, Asia/Bangkok date-aware, and reject an empty date/snapshot selection.

For every snapshot:

- finder input contains only bars with `ts <= as_of`;
- future outcome evaluation uses only bars with `ts > as_of` and `ts <= replay_end`;
- midday snapshots use the latest Daily context available before that snapshot;
- EOD snapshots may use the official Daily context available at that completed session boundary;
- open/provisional candle handling is explicit in provenance and never treated as a confirmed close.

## Persistence and result contract

Replay runs remain append-only and isolated from live VCP runs. Each replay run records:

- replay ID and prefix;
- window start/end and exact snapshot `as_of`;
- policy version and type-policy version;
- `universe_filter`, margin schema/source/effective date;
- base active ORD count, eligible count, excluded count, evaluated count;
- snapshot cadence and selected Bangkok dates.

Each evaluated symbol has one result per replay snapshot and retains:

- v1 VCP result;
- `decision_shadow_v2`;
- optional sequence-policy shadow fields;
- point-in-time Daily context/metrics;
- margin permissions;
- replay provenance;
- v1 and sequence-v2 evaluation fields when a valid plan exists.

No-data or insufficient evidence within the 237-symbol universe remains explicit and is not dropped.

## Timeline and outcome contract

The summary must report both per-snapshot state counts and symbol timelines:

```text
FORMING → READY / NEAR_TRIGGER → BREAKOUT_WATCH → CONFIRMED
        → EXTENDED / FAILED / INVALIDATED / OPEN
```

It must include first watch, first action review, entry activation, target/stop/open/ambiguous outcomes, time-to-entry, time-in-state, late/chase rate, pivot/invalidation distance, and v1-versus-sequence-v2 divergence.

Standard entries activate only when a future bar first trades at or above the required entry. Stops before activation are ignored. Same-bar target/stop is `ambiguous_same_bar`. Outcomes are descriptive and must not be labelled as a win rate.

## Rollout phases

### Phase A — five-trading-day pilot

- `marginable_long` universe;
- two snapshots per trading day;
- exact expected result count: `5 × 2 × 237 = 2,370` rows, unless a selected date has no eligible stored 60m timestamp, in which case the run fails closed before insert;
- validate coverage, provenance, no-lookahead, timeline transitions, and runtime/resource use.

### Phase B — two-month replay

- append-only continuation using a new explicit prefix;
- one or two snapshots per date, using the accepted pilot cadence;
- verify every snapshot has `eligible=evaluated=returned=237`;
- produce a bounded machine-readable summary and human-readable evidence report.

### Phase C — optional three-month extension

Run only if Phase B still lacks enough event/timeline sample and the owner approves the extension. Do not alter thresholds or promote a policy based on a larger sample automatically.

## Acceptance gates

1. Universe resolver returns exactly 237 current active ORD symbols with `can_buy=true`.
2. The run manifest accounts for all 931 active ORD: 237 eligible + 694 excluded by explicit filter.
3. Every selected snapshot evaluates exactly 237 unique symbols.
4. Every result has the replay ID, `as_of`, policy version, and margin source/effective date.
5. All finder input bars satisfy `bar.ts <= as_of`.
6. Future evaluation uses strictly later bars and respects entry activation.
7. Missing/short/error rows inside the eligible universe remain explicit.
8. Re-running the same prefix is idempotent and does not double-count results.
9. Served v1 payload and production scanner behavior remain unchanged.
10. Focused tests, relevant regression tests, and a pilot evidence artifact pass before the two-month run.

## Explicit non-goals

- Do not scan or replay non-marginable active ORD in this temporary mode.
- Do not delete or rewrite existing full-ORD historical observations.
- Do not change `symbol_master` statuses based on the broker list.
- Do not treat `can_short` as part of this long universe.
- Do not change VCP thresholds, pivot selection, entry definitions, or action lanes.
- Do not deploy a new serving policy, enable alerts, or generate orders.
- Do not claim statistical validity or a win rate from this replay alone.

## Expected implementation units

- `backend/marginable.py`: expose a provenance-safe eligible-symbol resolver or a small companion resolver that intersects active ORD with `can_buy=true` records.
- `backend/run_vcp_replay_1m.py`: add explicit universe mode, universe manifest, two-point daily snapshot selection, and run metadata while preserving existing daily/60m compatibility.
- `backend/analyze_vcp_shadow_replay.py`: summarize universe metadata, per-snapshot coverage, timelines, and v1/sequence-v2 outcomes without permissive zero fallbacks.
- Focused tests for dataset filtering, snapshot cutoffs, full accounting, no-lookahead, idempotency, and summary schema.
- A pilot evidence JSON/report outside source authority; no secrets or production dumps.

## Approval gate

This design intentionally changes the replay universe from full active ORD to `marginable_long` for the temporary research run. It does not authorize serving-policy changes. Implementation starts only after Arm confirms this spec and selects the execution mode.
