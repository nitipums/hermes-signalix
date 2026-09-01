# Signalix — Independent Team Review

> **STATUS: HISTORICAL REVIEW PACKET — SUPERSEDED BY 2026-09-01 SESSION CLOSEOUT**
> **Owner decisions Q1–Q15:** approved/refined 2026-09-01. Spec and local ticket drafts are ready; Kanban publish/dispatch and implementation are intentionally deferred to the next session.
> **Scope:** `/root/signalix`, `release/signalix-mvp-stable`, canonical `/api/setup-candidates` → `/mvp`, `marginable_long`.
> **No code/runtime changes were made for this review.**
> **Historical boundary:** This packet records the pre-implementation review state. Later T1–T9 promotion and the isolated 390px failure→Retry→recovery browser proof are recorded in `vault/2026-09-01-Current-Session-Handoff.md`.

## 1. Owner concerns

Arm's review comments:

1. Too many `DATA_BLOCKED` results are unacceptable.
2. The product is still slow.
3. The UI does not show how Elliott waves were identified; can the chart show the identification points?
4. There is too much legacy; remove it.

## 2. Current evidence baseline

| Check | Result | Evidence |
|---|---|---|
| Release checkout | PASS | historical review observed `release/signalix-mvp-stable`, HEAD `2535dac`; later promotion/current HEAD is recorded in the session closeout |
| Containers | PASS | `signalix_backend`, `signalix_dashboard`, PostgreSQL, Redis healthy at review start |
| `/mvp` | PASS transport | localhost `:3001/mvp` HTTP 200; public browser acceptance remains separate |
| `/api/setup-candidates` | PASS transport / REVISE semantics | `:3001` HTTP 200; canonical payload returned |
| `/health/readiness` | PASS | backend `:8000` HTTP 200 |
| Full-universe request | REVISE | `page_size=237` returned `total_items=237` but `returned_count=100`; endpoint imposes a 100-row page ceiling |
| Cold latency | REVISE | full request took approximately 23.52s during this review; earlier warm requests were approximately 0.57–0.64s |
| Full lane distribution | REVISE | across all 237 (Ploy page aggregation): `DATA_BLOCKED=227`, `AVOID=10`, no `REVIEW_NOW`/`SETUP_FORMING`/`DAILY_CANDIDATE`/`WAIT` |
| Blocked reason distribution | REVISE | first 100-page sample had 90 `insufficient recent 60m structural anchors`; Ploy found 227 blocked overall, most with fresh 60m and named Daily wave states |
| Public desktop/mobile/error journey | NOT VERIFIED | not exercised in this review |
| Code changes | PASS | independent Codex review was read-only; existing worktree changes preserved |

## 3. Lite independent review

### 3.1 `DATA_BLOCKED` — HIGH / REVISE

The current output is not acceptable as a user-facing diagnosis. The 90 blocked rows are not primarily missing data: their `data_status.sufficient=true`, Daily and 60m data are available/fresh, and the setup reason is `insufficient recent 60m structural anchors`.

Source evidence:

- `backend/mvp_api.py:559-588` builds Daily/60m data and evaluates freshness.
- `backend/mvp_api.py:607-608` overwrites setup status to `DATA_BLOCKED` whenever the current 60m interval gate fails.
- `backend/trade_setup_engine.py:197-204` uses the same `DATA_BLOCKED` state for missing/invalid OHLCV and insufficient structural anchors.
- `backend/trade_setup_engine.py:230-234` uses `DATA_BLOCKED` for invalid Fib/risk anchors.
- `backend/setup_candidate_contract.py:159-176` maps unknown/stale/insufficient evidence into blocked output.

Product/engineering implication:

- Separate `DATA_BLOCKED` (cannot evaluate honestly) from `SETUP_FORMING`/`DAILY_CANDIDATE` (Daily thesis valid, 60m setup not yet formed).
- Add deterministic reason codes and a user-readable explanation. At minimum: `DAILY_MISSING`, `DAILY_STALE`, `INTRADAY_60M_MISSING`, `INTRADAY_60M_STALE`, `INTRADAY_60M_INVALID`, `INTRADAY_60M_INSUFFICIENT_ANCHORS`, `INVALID_RISK_ANCHORS`.
- Keep structural insufficiency visible as “no qualifying 60m setup yet”, not “data unavailable”, unless the owner explicitly decides that no setup anchors should be blocked.
- Produce an aggregate report across all 237 rows, not only the first page, with lane × reason × data availability counts.

Acceptance required before fixing is accepted:

- Every row has machine-readable `blocked_reason_code`/`setup_unready_reason` where applicable.
- Daily-valid/60m-incomplete fixtures map to the owner-approved lane, not generic blocked.
- Missing, stale, invalid OHLCV, insufficient anchors, and invalid risk/Fib anchors are distinct in tests and API.
- Full 237-row distribution is visible in response metadata/UI.

### 3.2 Slowness — HIGH / REVISE

The cold path is too slow for an interactive product. Warm cache is fast, but does not hide the cold-build problem.

Evidence:

- Full `page_size=237` call took approximately 23.52s; repeated default calls were 0.57–0.64s after cache.
- `backend/mvp_api.py:562-573` performs Daily and 60m loading inside a loop over symbols.
- `backend/mvp_api.py:565` computes RS ranks, while the per-symbol path still loads symbol data separately.
- `backend/mvp_routes.py:27-31` uses a 300-second process-local cache; cache starts only after the serial build completes.
- The response is approximately 1.34MB for the first 50 items and 100 is the current page ceiling; large evidence blobs are sent with list rows.

Recommended bounded fix sequence:

1. Instrument cold build duration by stage and count DB queries/rows/bytes.
2. Batch-load Daily and 60m data for the 237 symbols, and compute RS from the same batch.
3. Split list projection from heavy evidence: list rows contain compact reason/evidence summaries; detail/chart fetches load the full trace.
4. Build or refresh the canonical artifact during ingestion/EOD rather than blocking the first browser request.
5. Keep single-flight concurrency, but make cache freshness depend on run identity/as-of, not only a fixed TTL.
6. Remove legacy snapshot parsing from the normal canonical path after a verified artifact migration; do not hand-edit or delete history prematurely.

Acceptance required:

- Cold/warm/post-ingestion measurements at page sizes 20, 50, 100, and full-universe metadata.
- Query count, serialized bytes, and stage timings recorded.
- Concurrent cold requests produce one build, not N builds.
- Owner approves the latency target before implementation is called complete.

### 3.3 Elliott traceability and chart identification points — HIGH / REVISE

The engine already records meaningful evidence, but the user cannot follow the chain on the chart.

Evidence:

- `backend/elliott_structure_engine.py:620-687` records OHLC swing legs, close-based legs, significant legs, volume flags, and variant configuration.
- `backend/elliott_structure_engine.py:834-858` records Wave 1 anchors, retracement, duration, Wave 1 high/low, close gate, and breakout/volume evidence.
- `backend/elliott_structure_engine.py:909-945` applies deterministic state gates, including the Daily Close-above-Wave-1-high gate.
- `backend/elliott_structure_engine.py:1164-1204` exposes primary/alternative state, confidence, supporting/contradicting/missing evidence, raw evidence, and policy.
- `backend/mvp_chart_db.py:239-358` returns candles/indicators but no Elliott marker contract.
- `backend/frontend/app.js:512-588` renders candles, MA/RSI, trigger/stop/target lines; no wave-point marker layer.
- Existing wave legs are positional indices/engine records, not normalized chart marker objects with timestamp + price.

Recommended product contract:

- Add `wave_markers[]` or `evidence_points[]` with:
  `id`, `kind`, `timeframe`, `timestamp`, `price`, `label`, `wave_role`, `source`, `confidence`, and `evidence_refs[]`.
- Convert engine indices to exact Daily candle timestamps and OHLC prices before API serialization.
- Mark the actual Wave 1 low/high, Wave 2 pullback low, Wave 3 close confirmation, and alternative/contradicting points where applicable.
- Keep large-degree Daily markers separate from small-degree evidence-only markers.
- Show a “How this wave was identified” drawer/section linking each marker to the deterministic rule and policy version.
- Do not project Daily markers onto a 60m chart without explicit mapping; show a clear unavailable/not-mapped state instead.

Acceptance required:

- CRC, BGRIM, and AWC fixture tests assert exact marker timestamp/price alignment.
- Markers remain aligned after chart truncation/windowing.
- Daily marker layer is visible on Daily chart and absent/explicitly unavailable on 60m unless mapped.
- Browser journey proves marker → evidence explanation → state uses the same snapshot identity.

### 3.4 Legacy removal — HIGH / REVISE, staged not blind deletion

Arm is right that legacy is still active in the call graph. “Remove it” must mean remove competing product authority and runtime paths in bounded stages, not delete audit evidence first.

Evidence:

- `backend/mvp_routes.py:218-255` still supports canonical setup candidates with snapshot fallback to the DB builder.
- `backend/mvp_routes.py:311-325` retains legacy chart fallback.
- `backend/app.py:892-990` retains old dashboard shortlist/snapshot routes.
- `backend/app.py:1017-1045` retains intraday transition/event compatibility routes.
- `backend/app.py:1130-1256` retains old scan/build-dashboard execution paths.
- `backend/mvp_projection.py`, `backend/build_dashboard.py`, `backend/daily_shortlist.py`, and `backend/stage_classifier.py` remain in active imports/call paths.
- `/api/vcp-finder`, VCP replay tables/scripts, and historical artifacts remain valid audit/rollback evidence.

Recommended staged retirement:

1. **Inventory:** classify every route/module/artifact as `CANONICAL`, `COMPATIBILITY`, `AUDIT`, or `REMOVE-CANDIDATE`; include callers, tests, timers, and rollback dependency.
2. **Stop competing authority:** `/api/setup-candidates` and `/mvp` must never consume legacy decision labels or legacy-shaped snapshots as canonical output.
3. **Quarantine:** move old route/module imports behind explicit compatibility boundaries and add deprecation/retirement dates; preserve replay data and audit read paths.
4. **Prove unused:** import-graph and route tests show remove-candidates are unreachable from canonical routes and active timers.
5. **Delete only after owner approval:** remove code/artifacts in bounded cards, one class at a time, with rollback evidence.

Do not remove:

- raw VCP/replay data required for audit;
- the legacy route until its consumers/rollback need are checked;
- old worktree files with uncommitted changes;
- generated artifacts by hand as a shortcut.

Acceptance required:

- route/import matrix committed to a current review/plan document;
- canonical API has no legacy primary labels;
- compatibility routes are explicitly labelled and tested;
- remove-candidates have zero canonical callers and a documented rollback boundary;
- served route checks and public UI checks pass after each retirement batch.

## 4. Codex independent engineering review

Codex reviewed read-only with explicit `gpt-5.6-luna`; no files/runtime state changed. Its findings are advisory and independently reconciled above.

### Codex conclusions

- **DATA_BLOCKED — HIGH / REVISE:** current code conflates missing/stale 60m, insufficient anchors, and invalid risk/Fib; add reason codes and preserve `SETUP_FORMING`/`DAILY_CANDIDATE` for valid Daily evidence with unfinished 60m setup. It also flagged suspicious age logic in `backend/trade_setup_engine.py:258-261` that compares the frame's timestamp to itself.
- **Slowness — HIGH / REVISE:** serial per-symbol Daily/60m queries, repeated RS work, synchronous cold build, large legacy snapshot validation, and fixed-TTL cache. Batch or prebuild; measure query count and payload; coalesce cold requests.
- **Traceability — MEDIUM-HIGH / REVISE:** engine evidence exists, but chart API/UI exposes no timestamp/value Elliott marker contract. Add chart-ready marker objects and browser tests.
- **Legacy — MEDIUM / REVISE:** old app routes, VCP route, chart fallback, snapshot adapter, and scan/build modules remain reachable. Inventory and quarantine first; retain VCP/replay audit paths.

## 5. Ploy independent trader/product/risk review

Ploy reviewed the same release, docs, local runtime, and UI read-only. No files/runtime state were changed.

### Ploy conclusions

- **DATA_BLOCKED — P0/P1 / REVISE:** all 237 aggregated pages show `227 DATA_BLOCKED`, `10 AVOID`, and zero review/forming/candidate/wait lanes. Most blocked rows still have fresh 60m and named Daily wave states. This makes the product look empty/broken and destroys trust. Decide and enforce: true unavailable/stale/invalid data → `DATA_BLOCKED`; valid Daily thesis with incomplete 60m setup → `DAILY_CANDIDATE`/`SETUP_FORMING`; evaluated failed risk/structure → `AVOID`.
- **Speed/pagination — P1 / REVISE:** live API is large (Ploy measured roughly 2.62MB/2.61MB/0.90MB across pages), while UI fetches only page 1 at 100 rows. The UI says 237 evaluated but exposes only 100. Use compact ranked list + detail evidence or a separate audit explorer; add explicit pagination and measure FCP/render time, bytes, and cold/warm latency.
- **Wave explainability — P1 / REVISE:** the API contains useful wave evidence, but served JS/card/chart does not show the identification points. Add minimum marker contract for Wave 1 low/high, retracement endpoints, structure break, tested-high/breakout, detection/as-of, alternative state, and missing evidence. Add a toggleable “Wave evidence” chart layer and drawer explanation.
- **Legacy — P1 / REVISE:** primary tab is correctly named but VCP UI/routes/compatibility paths remain visible and reachable. Use four stages: primary migration → audit-only quarantine → deprecation window → removal/410 after usage and rollback sign-off. Keep raw VCP/replay evidence immutable.

Ploy also flagged documentation drift that must be corrected before askmatt: older sections claim `all 237 DATA_BLOCKED`/promotion blocked, while later closeout sections claim T1–T9 promoted/partially served; older architecture wording reports 222 blocked while current aggregated evidence reports 227. Current review status must be stated once, with historical checkpoints explicitly labelled.

## 6. Reconciled pre-askmatt decision frontier

**Arm decisions recorded:** Q1–Q15 approved/refined. Q15 is delegated technical design: Arm does not need to choose internal module seams. Lite + Codex will use the smallest safe seams (candidate contract, chart evidence contract, migration boundary). Before `to-tickets`, the proposed ticket breakdown is:


1. **Blocked reason contract:** exact API field names and whether `NO_DAILY_DATA`, `NO_60M_DATA`, `NO_SETUP_DETECTED`, and `RISK_INVALID` live under `data_status`, `setup`, or both.
2. **Performance contract:** confirm list page size 50, full metadata counts, and detail endpoint boundaries under the approved latency targets.
3. **Chart contract:** confirm marker IDs, snapshot identity, click behavior, and Daily/60m visibility rules.
4. **Legacy one-day plan:** define the exact first-day route/UI hiding, one-day audit-only behavior, reuse audit, and removal/410 acceptance.
5. **Kanban implementation contract:** define card bodies, dependency edges, assignees, artifacts, and which cards require Ploy review versus Lite-only engineering review.
6. **Codex flow:** Codex remains the bounded worker using explicit `gpt-5.6-luna`; no code worker may bypass Matt spec/tickets, Kanban dependencies, or Lite final gate.

## 7. Owner-approved performance acceptance adjustment — 2026-09-01

Arm approved a pragmatic release target after fresh runtime measurements showed the full 237-symbol cold build is dominated by candidate evaluation rather than pagination or serialization:

- release cold request target: `<=15s`;
- release warm request target: `<=1s`;
- preserve `237/237` evaluated coverage, deterministic ordering, honest lane/page metadata, and single-flight behavior;
- strict cold `<=3s` remains a future optimization target, not a blocker for this release;
- never improve the number by dropping symbols, hiding blocked/avoid rows, or claiming warm-cache timing as cold performance.

This is an owner-approved acceptance threshold, not proof that the current runtime meets it. The final gate must record fresh cold/warm/post-invalidation/concurrent measurements separately.

## 8. Current verdict

| Gate | Verdict |
|---|---|
| Independent review completeness | `PASS` — Lite + Codex + Ploy completed |
| Code/source diagnosis | `REVISE` |
| Runtime transport | `PASS` |
| User-facing data semantics | `REVISE` |
| Cold performance | `REVISE` |
| Wave traceability UX | `REVISE` |
| Legacy migration | `REVISE — staged quarantine required` |
| Ready to askmatt | `READY` — review findings and decision frontier are documented |
| Ready to implement | `HOLD until askmatt + Arm scope decision` |

No code fix, deletion, deployment, restart, migration, or Kanban dispatch is authorized by this review record alone.
