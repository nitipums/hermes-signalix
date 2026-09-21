# Publisher pointer/artifact ownership — Issue #74

> **STATUS: CURRENT CHECKOUT EVIDENCE DECISION RECORD** · Spec: Issue #71.
> Prior evidence: Issue #72, commit `54919d3`; Issue #73, commit `cb05501`.
> Evidence timestamp: `2026-09-21T07:29:56+07:00` ICT. Checkout SHA:
> `cb055016fef6936e4a3adcb53dc9f9f7e68a5ae5` on
> `codex/t74-publisher-artifact-ownership`.
>
> This record authorizes no deletion, regeneration, movement, pointer write,
> source/test change, database/runtime operation, timer installation, deploy,
> or GitHub change. It protects current pointers and their referenced targets.
> The only file changed by this issue is this Markdown file.

## Scope and authority

The active product boundary is the deterministic, read-only Daily Trend Map
and Market Breadth surfaces: `/trend-map`, `/api/trend-map`,
`/market-breadth`, and `/api/market-breadth`. The required envelope remains
`PRODUCTION_READ_ONLY`, `research_only=false`, and `actionability=NONE`.
`/mvp`, `/api/setup-candidates`, setup/actionable-signal families, alerts,
broker actions, and auto-trading remain historical/deferred.

Read first: `AGENTS.md`,
`docs/current/2026-09-20-active-only-contract-freeze.md`,
`docs/current/2026-09-20-pointer-artifact-inventory.md`,
`docs/current/2026-09-20-active-cleanup-review.md`, and the current source and
focused tests named below. These authorities remain unchanged. This record is
evidence and ownership routing, not cleanup authorization.

## Separate verdicts

| Concern | Verdict | Boundary |
|---|---|---|
| SOURCE | **REVISE** | Publisher entry points, hooks, validation seams, and operational modes are traceable. The #73 publisher/readback contract mismatch is unresolved. |
| RUNTIME/API | **NOT VERIFIED** | No HTTP, browser, Compose, systemd, database, service, timer, deployment, or public-ingress operation was run. Source reachability is not served reachability. |
| DATA/POINTER | **REVISE / NOT VERIFIED** | Trend Map, intraday, and Market Breadth current pointers and targets validate in this checkout. Active chart pointer/target files are absent here; chart artifact ownership is therefore not currently verified. Intraday integrity is separate from stale freshness. |
| BROWSER/UI | **NOT VERIFIED** | No browser, desktop/mobile, chart-drawer, or public URL evidence was collected. |

## Ownership decision vocabulary

The bounded dispositions in this record are only **KEEP**, **CONSOLIDATE**,
**DELETE**, **MOVE-OUT**, and **OWNER-DECISION**. No disposition below grants
permission to execute it. No `CONSOLIDATE`, `DELETE`, or `MOVE-OUT` is proposed
for a protected pointer or target.

## Publisher entry points and publication hooks

| Evidence family | Entry point / hook | Ownership evidence | Disposition |
|---|---|---|---|
| Daily Trend Map | `backend/trend_map_read_model_publisher.py:publish_trend_map_read_model` and CLI `main`; `backend/update_data.py` invokes it after the EOD ingestion boundary | Builds and validates the read-only report, writes an immutable `versions/` artifact, then atomically writes `current.json`. Failure handling preserves the prior pointer. | **KEEP** |
| Intraday quote sidecar | `backend/intraday_quote_read_model.py:publish`; `backend/update_data.py:publish_intraday_quote_read_model_after_commit` after the committed intraday summary | Display-only quote artifact for `marginable_long`; source run identity and content hash are bound into the artifact/pointer. A sidecar failure preserves the prior valid pointer and does not fail ingestion. | **KEEP** |
| Market Breadth | `backend/market_breadth_publisher.py:publish_market_breadth_replay` → `market_breadth_artifact.publish_market_breadth_artifact`; CLI requires `--read-only` | Uses a SELECT-only/read-only source boundary, builds bounded history, validates the artifact, writes an immutable content-addressed target, then atomically writes `current.json`. | **KEEP** |
| Active chart read model | `backend/chart_read_model.py:publish`; `backend/update_data.py:publish_chart_read_model_after_commit`; EOD hook publishes `1D`, `1W`, `1M`, intraday hook publishes `60M` | Loads the canonical read model, projects compact chart entries, validates timeframe/source/freshness/read-only provenance, writes an immutable artifact, then writes `current-{timeframe}.json`. Existing source/test ownership is clear; current checkout files are absent. | **KEEP**; artifact availability **OWNER-DECISION** |

The update hooks are source-level operational modes only. `update_data.py`
supports EOD and `--intraday-only --no-scan`; `signalix-intraday.service`
contains a configured Bangkok time window and marginable-long 60M command;
`signalix-intraday.timer` and watchdog timer files exist in source. This does
not claim that any timer is installed, enabled, reachable, or currently
running. Installation/reachability is handed off separately.

## Current pointers and protected immutable targets

The following exact values were read from the checkout. Hashes in this table
are SHA-256 of the target file bytes, where noted; they are evidence only.

| Family | Pointer | Referenced target / identity | Checkout state |
|---|---|---|---|
| Trend Map | `backend/trend-map-read-model/current.json`; schema `daily-trend-map-shadow-read-model-v2`; `artifact_id=shadow-trend-map-quote-envelope-v2-2026-09-18-87dce5718dd0784a-e76ebcbf1637fac9-f34bcb3ad1244662-f3783cb9724c81a5`; `as_of=2026-09-18`; `published_at=2026-09-19T06:29:46.448688+00:00`; content `f34bcb3ad1244662`, measurement `f3783cb9724c81a5` | `versions/shadow-trend-map-quote-envelope-v2-2026-09-18-87dce5718dd0784a-e76ebcbf1637fac9-f34bcb3ad1244662-f3783cb9724c81a5.json`; 1,216,362 bytes; SHA-256 `8876cf984465a515c1c954a191d2d9ccff44012a1a9ae27cafefe5234d18d7ed`; 237 declared/evaluated/returned, 0 blocked | **VERIFIED / KEEP** |
| Intraday quote sidecar | `backend/trend-map-read-model/intraday-quotes/current.json`; schema `signalix.intraday-quote-read-model.v1`; `artifact_id=intraday-quotes-02f113b87e784369bd3807099bda46fa-36ffbec7a6be76099883b2b2`; `generated_at=2026-09-15T09:45:43.425426+00:00`; content hash `36ffbec7a6be76099883b2b272769fdddf207187dba7033f3e77aa12da604c10` | `versions/intraday-quotes-02f113b87e784369bd3807099bda46fa-36ffbec7a6be76099883b2b2.json`; 74,756 bytes; SHA-256 `49e64381448654d660d0017e9b7940c2d92c68be4c62438b0e8ebde1f861a463`; run `02f113b87e784369bd3807099bda46fa`; 237 quotes; `full_success` | **INTEGRITY VERIFIED / FRESHNESS REVISE: STALE / KEEP** |
| Market Breadth | `backend/market-breadth-read-model/current.json`; artifact version `signalix.market-breadth.artifact.v2`; content hash `c19d4ed5a7db3e522ea3f5e0ff4f151643895bdcb47eaf4d9d4de8dcdcf020d2` | `versions/market-breadth-c19d4ed5a7db3e522ea3f5e0ff4f151643895bdcb47eaf4d9d4de8dcdcf020d2.json`; 2,385,581 bytes; SHA-256 equals the content hash; `as_of=2026-09-18`; active ORD; counts official 838, derived 3, blocked 88, invalid 0 | **VERIFIED / KEEP** |
| Active chart read model | Expected pointers `backend/read-model/charts/current-1D.json`, `current-60M.json`, `current-1W.json`, `current-1M.json` and `versions/` targets | None of these files/directories exists in this checkout. Source contracts identify `signalix.chart-read-model.v1`, timeframes `1D/60M/1W/1M`, and per-timeframe freshness/source policies; no pointer identity or target hash can be claimed. | **NOT VERIFIED / OWNER-DECISION**; protect absence as evidence, do not regenerate |

All present protected pointer and target files above are tracked. The chart
root is absent, so no chart pointer/target is classified as tracked or ignored
in this checkout. The prior inventory records ignored chart candidates removed
in an owner-authorized historical cleanup; that history does not authorize
recreation, deletion, or movement here.

## Validation and ownership boundary

The read-only inventory seam in `backend/artifact_pointer_inventory.py` checks
pointer containment and target existence, then delegates family validation:

- Trend Map checks relative target containment, schema, artifact identity,
  policy/universe/representation identity, publication time, content hash,
  measurement hash, read-only report contract, and timing metadata.
- Intraday checks schema, relative `versions/` containment, artifact identity,
  canonical content hash, and artifact validation. Inventory reports
  `freshness_status` independently; it must not turn stale integrity into a
  fresh claim.
- Market Breadth checks exact `versions/` target identity, byte hash,
  canonical JSON bytes, artifact schema, active-ORD identity, range identities,
  quality/freshness/provenance, and the read-only envelope.
- Charts, when present, check timeframe-specific pointer schema/identity,
  relative `versions/` containment, artifact identity, schema, read-only
  SELECT-only provenance, source, symbol counts, and freshness. Here this is
  **NOT VERIFIED** because the current pointers and targets are unavailable.

Integrity, freshness, provenance, and retention/recoverability are different
properties. Present Trend Map and Market Breadth targets have integrity
evidence, and their payloads carry provenance/freshness fields; that is not a
fresh served API result. Intraday integrity is verified but its recorded
freshness is stale. There is no current-plus-N retention contract. Immutable
targets and tracked history are protected; recovery remains Git history,
approved tags/branches, or an owner-approved external archive. No retention,
archive, deletion, or regeneration action is authorized.

## #73 publisher/test contract mismatch

The focused publisher run reproduces **5 failures** in
`backend/test_trend_map_read_model_publisher.py`:

- `test_repeated_publish_with_new_measurement_does_not_collide` expects
  readback `timing`;
- `test_pointer_readback_missing_corrupt_and_mismatched_are_blocked` expects
  top-level readback `artifact_id`;
- `test_pointer_change_is_observed_without_process_restart` expects top-level
  readback `artifact_id`;
- `test_publisher_reports_timing_metrics` expects readback `timing`;
- `test_api_default_path_never_invokes_classifier_or_history` expects
  readback `counts`.

The implementation currently returns publisher-result `timing`/`counts`, and
its successful readback places pointer identity under `artifact` while the
artifact itself contains timing/counts. The failures therefore establish a
publisher/readback source-contract versus test-contract mismatch, not an
artifact-integrity failure. This record does not decide whether the source
contract is wrong, the tests are stale, or an OWNER-DECISION is required;
**OWNER-DECISION** is the disposition for #75. No patch is made here.

## Disposition summary

| Subject | Disposition | Reason |
|---|---|---|
| Current Trend Map, intraday, and Market Breadth pointers/targets | **KEEP** | Protected active read-only evidence; do not alter identity or actionability semantics. |
| Publisher hooks and read-only validation seams | **KEEP** | Source ownership is explicit and failure paths preserve prior pointers. |
| Active chart source publisher and four timeframe ownership | **KEEP** | Source ownership is explicit; missing checkout artifacts remain unresolved evidence. |
| Existing historical/ignored candidates | **KEEP** | No deletion or movement is authorized by this evidence record. |
| #73 `timing` / `artifact_id` / `counts` mismatch | **OWNER-DECISION** | Follow up in #75; do not patch in #74. |
| Installed timer/runtime reachability | **OWNER-DECISION** | Follow up in #76; source files do not prove installation or reachability. |
| Chart pointer/target availability in this checkout | **OWNER-DECISION** | Follow up in #76 under explicit artifact/runtime scope; do not regenerate here. |

No item is authorized for `CONSOLIDATE`, `DELETE`, or `MOVE-OUT`.

## Handoff to #75–#77

- **#75 — publisher contract:** decide and reconcile the source/readback
  contract for `timing`, `artifact_id`, and `counts`; rerun the focused suite;
  preserve pointer identity and the read-only/no-actionability envelope.
- **#76 — runtime and artifact evidence:** separately verify served API,
  pointer/freshness/provenance, chart artifact availability, and installed
  publisher modes/timers. Do not infer reachability from this source record.
- **#77 — browser/UI evidence:** verify Trend Map and Market Breadth at desktop
  and 390px mobile, including chart drawer and failure/blocked states; keep
  browser verdict separate from source and pointer integrity.

## Exact read-only commands and results

Commands were run from `/tmp/signalix-t74`. No HTTP/browser/Compose/systemctl/
database operation was run.

```text
git status --short --branch
=> ## codex/t74-publisher-artifact-ownership
git rev-parse HEAD
=> cb055016fef6936e4a3adcb53dc9f9f7e68a5ae5
date --iso-8601=seconds
=> 2026-09-21T07:29:56+07:00
git show --stat --oneline 54919d3 cb05501
=> prior docs-only evidence commits #72 and #73
sed -n '1,240p' docs/current/2026-09-20-active-only-contract-freeze.md
sed -n '1,280p' docs/current/2026-09-20-pointer-artifact-inventory.md
sed -n '1,260p' docs/current/2026-09-20-active-cleanup-review.md
=> current scope, protected targets, and no-cleanup boundaries read
rg -n "publish|publisher|current\.json|artifact_id|timing|counts" backend --glob '*.py'
rg --files backend docs/current | rg '(publish|pointer|read.model|trend.map|market.breadth|chart|intraday|test_)'
=> publisher/hooks, validation seams, tests, timers, and chart source located
python read-only pointer/target inspection script
=> Trend Map target present; intraday target present; Market Breadth target present;
   chart current pointers/targets absent; exact pointer identities and target
   byte SHA-256 values recorded in this document
git ls-files / git check-ignore over active artifact paths
=> present Trend Map/intraday/Market Breadth pointers and targets TRACKED;
   chart root absent (no tracked or ignored chart file in this checkout)
rg -n "ArgumentParser|add_argument|timer|ExecStart|publish_(trend|market|chart|intraday)|--intraday-only|no-scan" backend/...
=> operational publisher modes and service/timer declarations located; no
   installed-runtime claim made
TMPDIR=/tmp PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider \
  backend/test_artifact_pointer_inventory.py \
  backend/test_trend_map_read_model_publisher.py \
  backend/test_intraday_quote_read_model.py \
  backend/test_market_breadth_artifact.py \
  backend/test_chart_read_model.py
=> 75 collected: 70 passed, 5 failed; all 5 failures were the #73 Trend Map
   publisher/readback KeyError expectations for timing, artifact_id, or counts
   (no source/test files changed)
git diff --check
=> PASS before this file was created; rerun after creation is required below
```

## Self-check

The intended final self-check is limited to this new file: `git status --short`,
`git diff --name-status`, `git diff --check`, and a no-index whitespace check.
No commit is created; Lite reviews and commits this documentation slice.
