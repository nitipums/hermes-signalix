# VCP Decision Shadow v2 — Multi-Day Every-60m Replay

> **STATUS: CURRENT EVIDENCE** · 2026-08-28
> **Verdict:** `REVISE` — v2 lane integrity passes; v1 sequence policy and Low-Cheat entry profile are not accepted for a served-policy switch.
> **Deployment boundary updated 2026-08-30:** Historical replay/shadow fields remain non-serving. The owner-approved `decision_shadow_v2` projection is now applied to live VCP results under `marginable_long`; raw morphology/source policy remains `signalix/vcp-finder-60m-v1`.

## Replay identity and no-lookahead boundary

- Prefix: `vcp-shadow-v2-multi-day-20260828`
- Policy: finder `signalix/vcp-finder-60m-v1`; shadow `signalix/vcp-decision-shadow-v2`
- Window: 2026-08-23T07:02:07Z through 2026-08-28T07:02:07Z
- Snapshots: 38 every-60m `as_of` points, 2026-08-24 02:00Z through 2026-08-28 07:00Z.
- Universe: 931 active TH ORD each snapshot; 35,378 persisted rows (`38 × 931`).
- Coverage at replay end: 904 symbols had stored rows; 842 had at least 80 bars.
- Input rule: every finder input used only bars `ts <= as_of`; Daily trend context, Daily metrics, and marginable context were loaded point-in-time before projection.
- Standard VCP stop/target outcomes start only after a future bar trades at/above entry. Low-Cheat entry starts at detection close. These are descriptive replay outcomes, not trade recommendations or win rates.

## v2 lane integrity — PASS

| Lane | Rows |
|---|---:|
| REVIEW_NOW | 306 |
| PREPARE | 1,285 |
| EVENT_WATCH | 8,862 |
| RESEARCH | 11,250 |
| DO_NOT_CHASE | 9,696 |
| DATA_BLOCKED | 3,979 |

Actionability: `ACTIONABLE_REVIEW=306`, `WATCH_ONLY=10,147`, `NO_ACTION=24,925`.

Contradiction audit:

| Rule | Count | Verdict |
|---|---:|---|
| EXTENDED in REVIEW_NOW/PREPARE | 0 | PASS |
| FAILED in REVIEW_NOW/PREPARE | 0 | PASS |
| EVENT_WATCH marked ACTIONABLE_REVIEW | 0 | PASS |
| DATA_BLOCKED marked actionable/watch-only | 0 | PASS |

Shadow was present in all rows (`missing_shadow=0`). Default tradability passed for 6,492 rows and failed for 28,886 rows; failure remains visible evidence and did not delete candidates.

## Entry-aware first-event outcomes — descriptive only

First events are deduplicated by `(symbol, base_type)` for the replay run: 178 total.

| Base type | Target | Stop | Entry not activated | Open at end | Ambiguous |
|---|---:|---:|---:|---:|---:|
| standard_vcp | 31 | 18 | 51 | 44 | 0 |
| low_cheat_vcp | 0 | 28 | 0 | 5 | 1 |

Interpretation limits:

- Standard `target_hit` versus `stop_hit` among the 49 resolved activated events is 31 versus 18 (63.27% target side); 51 additional standards never activated and 44 remained open at the replay boundary. This is not a win rate.
- Low-Cheat had 34 first events: 28 stop hits, 5 open, and 1 ambiguous same-bar case; no target hit in this window. This is sufficient to block promotion of Low-Cheat as a fast/early action lane pending a broader controlled review.

## First vs latest sequence diagnostic — FAIL v1 policy acceptance

For rows that had a latest-non-broken v2 sequence:

- more than one valid H-L-H-L-H candidate sequence: 29,309 rows;
- v1 first-sequence final pivot differed from v2 latest-non-broken final pivot: 29,108 rows (**99.31%**);
- v2 final-pivot age: median 24 hours, mean 44.56 hours, maximum 672 hours.

The diagnostic proves that `v1 first_confirmed_sequence` is not a stable proxy for the active base in this data. It is retained for backward compatibility only. Do not switch it directly: build a dedicated sequence-policy A/B shadow that recalculates state/entry/invalidation from the v2 sequence and evaluates resulting events point-in-time.

## Final replay snapshot (2026-08-28 07:00Z)

| Lane | Count | Pass default tradability |
|---|---:|---:|
| REVIEW_NOW | 3 | 1 |
| PREPARE | 34 | 6 |
| EVENT_WATCH | 213 | 34 |
| RESEARCH | 297 | 54 |
| DO_NOT_CHASE | 284 | 75 |
| DATA_BLOCKED | 100 | 0 |

This supports the intended separation: broad evidence is retained while only a small, explicitly tradable subset is eligible for fast review. It does not authorize a UI/served-v1 change until the next acceptance gate.

## Required next gate

1. Add a `latest_non_broken` sequence-policy shadow that recomputes VCP morphology, pivot, invalidation, entry, and state — diagnostics alone do not alter v1.
2. Keep Low-Cheat non-promoting. Define a separately approved early-entry hypothesis and evaluate it over a longer independent replay period with explicit risk/entry assumptions.
3. Re-run at least a multi-week every-60m replay after the sequence-policy shadow exists; retain append-only IDs and `replay_evaluation` records.
4. Compare v1 vs sequence-v2 by event count, entry activation, target/stop/open/ambiguous outcomes, time-to-entry, late/chase rate, and state/lane contradictions. Do not call the result a win rate.
5. Obtain owner approval and update `vault/Decisions.md` before serving any v2 lane or replacing v1 pivot selection.
