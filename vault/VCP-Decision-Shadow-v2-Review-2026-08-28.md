# VCP Decision Shadow v2 — Review Evidence

> **Date:** 2026-08-28
> **Verdict:** PASS for non-serving shadow implementation; NOT APPROVED for replacing served v1.
> **Deployment boundary updated 2026-08-30:** Historical shadow replay remains non-serving; the owner-approved v2 decision projection is now served on live VCP results under `marginable_long`. Raw VCP source policy remains v1; Low-Cheat/sequence-policy promotion remains blocked.

## Scope

Implemented and exercised:

- deterministic Daily context/metrics ordering;
- entry-aware Standard VCP replay outcomes;
- point-in-time Daily context/metrics parity;
- explicit replay ID prefixes and resume checkpoints;
- marginable parity with the live projection inputs;
- candidate pivot-sequence diagnostics while retaining v1 selection;
- pure `signalix/vcp-decision-shadow-v2` projection;
- read-only persisted replay summarizer.

Served `signalix/vcp-finder-60m-v1`, Daily VCP Watchlist, API routes, UI, and Docker services were not changed or rebuilt.

## Tests

Disposable worktree venv:

```text
53 focused tests passed
```

Covered:

- VCP finder and sequence diagnostics;
- deterministic Daily loaders;
- v1 API contract;
- entry-aware replay and resume IDs;
- v2 lane/actionability/tradability policy;
- replay summary and contradiction detection.

Python compile check passed for all changed modules.

## Replay runs

### r1 — retained failed-parity evidence

Prefix: `vcp-shadow-v2-one-day-20260828-*`

- 6 snapshots, 5,586 rows, 931 rows per snapshot.
- All rows had shadow output.
- Marginable context was absent, causing `default_pass=0` for tradability.
- Verdict: **FAIL parity**; preserved rather than rewritten.

### r2 — corrected one-day every-60m shadow

Prefix: `vcp-shadow-v2-one-day-20260828-r2-*`

- Window: 2026-08-28 02:00–07:00 UTC.
- 6 snapshots.
- 931 eligible/evaluated/returned per snapshot.
- 5,586 persisted results.
- Shadow output present: 5,586/5,586.
- Marginable records: 1,938/5,586.
- Default tradability pass: 1,020/5,586.
- Missing shadow: 0.

Aggregate lanes:

| Lane | Rows |
|---|---:|
| REVIEW_NOW | 32 |
| PREPARE | 205 |
| EVENT_WATCH | 1,298 |
| RESEARCH | 1,761 |
| DO_NOT_CHASE | 1,692 |
| DATA_BLOCKED | 598 |

Contradictions:

| Check | Count |
|---|---:|
| EXTENDED in REVIEW_NOW/PREPARE | 0 |
| FAILED in REVIEW_NOW/PREPARE | 0 |
| EVENT_WATCH actionable | 0 |
| DATA_BLOCKED actionable/watch-only | 0 |

Final r2 snapshot at 07:00 UTC:

| Lane | Total | Pass default tradability |
|---|---:|---:|
| REVIEW_NOW | 3 | 2 |
| PREPARE | 36 | 5 |
| EVENT_WATCH | 202 | 34 |
| RESEARCH | 304 | 53 |
| DO_NOT_CHASE | 286 | 76 |
| DATA_BLOCKED | 100 | 0 |

Final state→lane evidence included:

- `NEAR_TRIGGER → REVIEW_NOW`: 2
- `READY → REVIEW_NOW`: 1
- `READY → RESEARCH`: 1 due unmet shadow decision evidence
- `FORMING → PREPARE`: 36
- `FORMING → EVENT_WATCH`: 196
- `BREAKOUT_WATCH → EVENT_WATCH`: 6
- `EXTENDED → DO_NOT_CHASE`: 1
- `FAILED → DO_NOT_CHASE`: 285
- `STALE/NOT_VERIFIED → DATA_BLOCKED`: 100

## Entry-aware outcome evidence

The bounded r2 process emitted first-event descriptive outcomes:

```text
standard_vcp: target_hit 5
standard_vcp: entry_not_activated 15
standard_vcp: open_at_replay_end 10
standard_vcp: stop_hit 1
low_cheat_vcp: open_at_replay_end 1
low_cheat_vcp: ambiguous_same_bar 1
low_cheat_vcp: insufficient_future_data 1
```

These are not win rates. The window is one partial trading day and many events have insufficient future bars. r2 ran before the final persistence helper was added, so its JSONB outcome field remains `NOT_VERIFIED`; the subsequent unit-tested helper now persists `replay_evaluation` for future runs.

## Served-v1 verification

After shadow replay:

```text
GET :3001/mvp                          200
GET :3001/dashboard.html               404
GET :8000/health/readiness             200
GET :3001/api/vcp-finder?...           200
```

Observed live v1 remained full-universe (931 evaluated) and continued to publish only its existing three Daily Watchlist lanes. No shadow field or lane was served.

## Limitations / next gate

- Only one trading day was replayed with the corrected full policy inputs.
- Existing 11-day every-60m rows predate shadow outcome persistence and do not constitute v2 acceptance.
- Fundamental evidence remains context-only and was not present in this replay.
- v1 still selects the first confirmed pivot sequence; v2 only records latest-non-broken diagnostics.
- No threshold tuning, served-policy switch, UI work, or deployment is authorized by this evidence.

Before replacing v1, run a longer isolated v2 replay with persisted outcomes, compare first-vs-latest sequence policy, inspect real candidate timelines, and obtain an explicit owner acceptance decision.
