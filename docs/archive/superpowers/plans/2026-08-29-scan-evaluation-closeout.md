# Signalix Scan & Evaluation Closeout Workplan

> **STATUS: HISTORICAL / SUPERSEDED 2026-09-01** · Retained audit evidence; the Elliott/Trend/Trade-Setup plan is the current implementation authority.
> **Orchestrator/final gate:** Lite
> **Trader/product challenger:** Ploy
> **Started:** 2026-08-29
> **Authority:** `vault/Execution-Pipeline.md`, `vault/Decisions.md`, and `vault/Scan-Evaluation-Logic-Map-2026-08-29.md`

## Purpose

Working checklist for closing the owner-approved Scan/Evaluation direction without reopening the serving-spine decision.

## Chosen serving spine — locked

```text
60m VCP = setup/morphology authority
Daily EOD = supporting context + cross-day lifecycle evidence
Intraday = observation overlay; never overwrites Daily truth
→ one unified serving decision contract
Shadow/replay = non-serving until a separate promotion gate
```

## Completed and verified

- [x] Unified VCP decision object and canonical UI state/decision labels.
- [x] Canonical decision filters and `state · decision` grouping on Daily/All VCP.
- [x] Active ORD instrument master quality contract.
- [x] VCP run provenance validation and fail-closed serving predicate.
- [x] Daily-vs-60m boundary: Daily scan no longer uses 60m fallback.
- [x] Daily full-universe source moved to active `symbol_master`.
- [x] Missing/short/error Daily rows are explicit `INSUFFICIENT_HISTORY` or `NOT_VERIFIED` observations.
- [x] Required snapshot `analysis_date` uses official scan boundary for no-data/error rows; analytical values remain null.
- [x] Policy registry separates `daily_eod` and `vcp_60m` ownership/version/thresholds.
- [x] Canonical Daily ranking adapter: hard gates first, deterministic ordering, authoritative R/R only.
- [x] Completed-session scan: run `3c344183-563e-408f-b069-d73140d29c88`, 931/931 observations, 53 `INSUFFICIENT_HISTORY`.
- [x] Public UI/API/runtime gate: `/mvp` 200, VCP 931 evaluated, canonical cards visible, 390px width has no horizontal overflow.
- [x] Logic Map reconciled to `CURRENT_WITH_REMAINING_GAPS`.

## Remaining work

### R1 — Shadow replay promotion gate

**Status:** `REVISE/BLOCKED` for promotion; replay evidence itself is complete for the bounded daily-cadence run.

Completed evidence run:

- Prefix: `vcp-shadow-multiweek-daily-20260829`
- Window: 2026-08-17 through 2026-08-28 Bangkok trading dates
- Cadence: daily snapshot at 10 completed dates
- Coverage: 10 × 931 = 9,310 persisted rows
- Every snapshot: `eligible=evaluated=931`
- Every row: `decision_shadow_v2` present
- Target: `R/R=3.0`
- Descriptive outcomes: standard VCP target 2, stop 19, no activation 30, open 33, ambiguous 2

Ploy challenge:

- `REPLAY COMPLETE`.
- `PROMOTION REVISE/BLOCKED`.
- Do not switch v1, promote shadow lanes, or enable alerts.
- Actionable evidence is too thin and no sufficient target/stop edge is demonstrated.
- Keep `shadow_only` and `promotion_allowed=false`.

### R2 — Optional stronger every-60m replay evidence

The first every-60m attempt was too slow on the VPS and was stopped after partial persisted rows. The runner was then bounded with deterministic Bangkok-date selection, `--max-snapshots`, no-lookahead validation, required shadow validation, and bounded diagnostics (`30d3ba3`).

Next bounded experiment, only if Arm wants stronger promotion evidence:

1. Benchmark one representative day and record runtime/resource use.
2. Optimize repeated Daily context/metrics reads without changing point-in-time semantics.
3. Run 10 completed trading dates at 60m with an explicit snapshot cap.
4. Require 931/931 coverage per snapshot, shadow presence, no-lookahead, and persisted `replay_evaluation`.
5. Ask Ploy to review the resulting state/action/outcome distribution.
6. Keep promotion blocked unless evidence materially improves and Arm approves.

This is a research gate, not a production deployment task.

## Hard no-go boundaries

- No v1 VCP threshold change from this replay.
- No shadow policy promotion without Arm approval.
- No alert reactivation.
- No automatic trading or order generation.
- No mixing Daily EOD truth with 60m/intraday evidence.
- No calling descriptive outcomes a win rate.

## Acceptance checklist for the next session

- [ ] Read this workplan and current `Execution-Pipeline.md` before work.
- [ ] Inspect git status/worktree before any change.
- [ ] If replay runner changes, run focused tests + full relevant suite.
- [ ] Verify replay date range and exact snapshot count before writing rows.
- [ ] Verify `eligible=evaluated=returned=931` per snapshot.
- [ ] Verify `bar.ts <= as_of` and explicit open/provisional handling.
- [ ] Verify every row has `decision_shadow_v2` and required provenance.
- [ ] Obtain Ploy challenge.
- [ ] Lite issues final `PASS`, `REVISE`, or `NOT VERIFIED`.

## Evidence links

- [[../../vault/Execution-Pipeline]]
- [[../../vault/Scan-Evaluation-Logic-Map-2026-08-29]]
- [[../../vault/VCP-Decision-Shadow-v2-Multi-Day-Replay-2026-08-28]]
- [[../../vault/Decisions]]
