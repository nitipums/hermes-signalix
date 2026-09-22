# Historical Signalix family disposition — Issue #76

> **STATUS: CURRENT DISPOSITION RECORD** · Spec: Issue #71. Prior evidence:
> Issues #72–#75, ending at commit
> `6479c3ac7a8f304dd59990a30319dabd9b6b2daa`. Evidence timestamp for this
> record: `2026-09-21T07:39:29+07:00` ICT. This is a read-only review of
> repository evidence. It authorizes no execution, alert, signal, broker,
> portfolio, timer, runtime, database, artifact, deletion, move, cleanup,
> consolidation, deployment, or GitHub action.

## Decision boundary

The active product remains deterministic, read-only Daily Trend Mapping and
Market Breadth:

| Active route | Protected contract |
|---|---|
| `/trend-map`, `/api/trend-map` | `status=PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`; fail closed for unavailable/invalid evidence |
| `/market-breadth`, `/api/market-breadth` | validated deterministic aggregate evidence with the same non-actionable boundary |

`/mvp`, `/api/setup-candidates`, Team Facts, Elliott/Wave/VCP setup work,
private signals, alerts, broker execution, and auto-trading are
`HISTORICAL / DEFERRED`. A disposition below is a classification for owner
review, not permission to resume or remove a family.

The family disposition vocabulary is **KEEP**, **CONSOLIDATE**, **DELETE**,
**MOVE-OUT**, and **OWNER-DECISION**. The original Issue #76 review assigned
**OWNER-DECISION** because its evidence did not authorize cleanup. Subsequent
owner-approved Waves B/C1/C2/C3a/C3b are reconciled in the family sections
below; no broader deletion, move, or consolidation is inferred from them.

## Cross-family verdicts

| Evidence dimension | Result | What it proves / does not prove |
|---|---|---|
| **SOURCE** | **VERIFIED for classification** | The checkout contains dispatch, imports, callers, publishers, tests, units, templates, historical docs, and compatibility references identified below. Source reachability is not served reachability. |
| **RUNTIME/API** | **NOT VERIFIED / OWNER-DECISION** | No server, Compose, HTTP/public ingress, database, systemd, timer, service, or live publisher read-back was run in this issue. |
| **DATA/POINTER** | **REVISE / OWNER-DECISION** | Tracked Trend Map, intraday, and Market Breadth pointers/targets are protected by #72–#74; chart pointers/targets were absent in that checkout. Dated identity is not fresh runtime or freshness proof. |
| **BROWSER/UI** | **NOT VERIFIED / OWNER-DECISION** | No desktop, 390px mobile, asset-load, chart-drawer, empty/error, or public URL journey was run. #77 remains the browser/UI handoff. |

## Family review

### 1. MVP/setup and setup candidate

> **Wave C3b owner disposition applied 2026-09-22:** **MOVE-OUT** removed the
> caller-free duplicate `backend/mvp_server.py`, the isolated historical
> `backend/frontend/{index.html,app.js,request_cache.js}` cluster, its two
> request-cache tests, the stale `backend/test_signalix_contracts.py` live
> script, and `scripts/browser_failure_retry_harness.sh`. Git history is the
> recovery authority. `test_mvp_ui_feedback_contract.py` was narrowed to its
> still-active shared-drawer assertions rather than deleted.
>
> The active transport retains explicit 410 responses for `/mvp` and
> `/api/setup-candidates`. Compatibility and publisher callers require
> `mvp_api.py`, `mvp_routes.py`, `mvp_snapshot.py`, `mvp_chart.py`,
> `mvp_chart_db.py`, `chart_read_model.py`, `setup_candidate_contract.py`,
> `setup_state.py`, lifecycle/Team Facts, and chart Wave evidence to remain
> **OWNER-DECISION**. C3b does not refactor those seams.

- **Current route reachability:** `backend/active_transport.py` owns the four
  active routes and explicit retired-route responses without importing the
  historical MVP dispatcher. `backend/test_mvp_server_transport.py` verifies
  the 410 boundary. Retained `mvp_routes.py` still has compatibility and shared
  helper callers, but it is not the active transport.
- **Publisher/test/operational references:** `mvp_api.py`, `mvp_snapshot.py`,
  `setup_candidate_contract.py`, `read_model_publisher.py`,
  `verify_mvp_only.py`, setup/MVP tests, and `update_data.service`'s
  `ExecStartPost`. #75 records the `verify_mvp_only.py` post-step as a
  contradiction, not as active ownership.
- **Authority role:** Historical setup/API contract and audit evidence only;
  the active-only freeze, Product Strategy, Execution Pipeline, and #72–#75
  route records supersede it for current product scope.
- **Rollback/audit value:** High. It preserves prior setup schemas, retirement
  responses, source lineage, replay comparison, and recovery context.
- **Contradictions:** Historical tests and scripts still name live-looking
  setup/VCP paths; the EOD unit names a retired verification command; old
  Product Strategy sections describe `/mvp` as a former product while its
  current header marks it deferred. Runtime reachability is unknown.
- **Disposition:** **MOVE-OUT** for the exact caller-free C3b manifest;
  **OWNER-DECISION / RETAINED** for the compatibility/publisher seams above.
  Do not start or route active evidence through the retained historical family.

#### Wave C3b exact caller and disposition manifest

| Path/family | Direct/dynamic caller evidence before removal | Result |
|---|---|---|
| `backend/mvp_server.py` | No Python import, Compose command, service, timer, publisher, readiness, or active test caller; Compose runs `active_transport.py`. Current docs were the only non-historical references. | MOVE-OUT |
| `backend/frontend/index.html`, `app.js`, `request_cache.js` | The three files called only one another and the dedicated historical UI/cache tests; `active_transport.py` allowlists only `styles.css`, `canonical-client.js`, and `shared-drawer.js`. | MOVE-OUT |
| `backend/test_request_cache_behavior.{py,js}` | Python wrapper invoked only the paired Node test; no retained suite imports either file. | MOVE-OUT |
| `backend/test_signalix_contracts.py` | No caller; its live script expected the retired `/mvp` surface and old VCP markers. Focused snapshot and retirement behavior remain covered elsewhere. | MOVE-OUT |
| `scripts/browser_failure_retry_harness.sh` | No caller; targeted `/mvp` and `/api/setup-candidates`, which now return 410. | MOVE-OUT |
| `backend/test_mvp_ui_feedback_contract.py` | Mixed file: old frontend assertions were caller-free, but shared-drawer assertions protect the active Trend Map drawer. | KEEP, narrow old-only assertions |
| `backend/test_vcp_finder_db.py` | The file protects `vcp_finder_db.py`, which remains called by `update_data.py`; one isolated inventory test read `frontend/app.js` only to assert retired MVP VCP rendering. | KEEP, remove that old-only test |
| `backend/mvp_chart.py` | Dynamically imported by `mvp_routes.py` for retained `/api/chart/{symbol}` audit compatibility; explicitly exercised by `test_legacy_routes.py`. | OWNER-DECISION / KEEP |
| `backend/chart_read_model.py` | Called by `active_chart_routes.py`, `active_transport.py` startup warming, `artifact_pointer_inventory.py`, `update_data.py` publication, and retained compatibility/tests. | KEEP |
| Protected MVP/setup family | `mvp_api.py` is called by `update_data.py`, `mvp_routes.py`, and `vcp_finder_db.py`; `mvp_routes.py` supplies SELECT-only DSN helpers to Trend Map/Market Breadth publisher plus compatibility routes; `mvp_snapshot.py` is called by the compatibility builder/dispatcher; `mvp_chart_db.py` is called by chart publication/tests; setup contracts/state have current builder/screening callers. | OWNER-DECISION / KEEP |
| Lifecycle/Team Facts/chart Wave evidence | Caller evidence is recorded in C3a/C2 below; no C3b caller was removed from these chains. | OWNER-DECISION / KEEP |

The deleted manifest contained **8 tracked files / 2,234 LOC** before C3b and
**0 files / 0 LOC** afterward. Narrowing the two retained mixed tests removed
another **77 net test LOC**. Repository-wide tracked file/LOC totals are
recorded in the final C3b verification block after documentation sync.

#### Wave C3b source verification and evidence boundary

- **Checkout:** clean start at `c0be6c1502a6ed404393896b87230060185317d1`
  on `codex/sol-wave-c-source-retirement`; no commit, push, deployment,
  restart, database, timer, pointer, artifact, or browser operation.
- **Tracked inventory:** before C3b, **328 files / 76,075 LOC**. After the
  final source and current-ledger sync, **320 files / 73,848 LOC**. The net
  repository delta is **8 files / 2,227 LOC removed**, including the three
  updated evidence documents.
- **Focused active/compatibility gate:** 277 tests collected; **276 passed,
  1 skipped** across active transport/chart, artifact/pointer, Trend Map,
  Market Breadth, intraday, retirement/legacy, and retained drawer coverage.
- **All retained backend tests:** 994 tests collected; **982 passed,
  12 skipped**. The first run identified the old-only VCP/frontend inventory
  assertion; the post-removal rerun exited 0. The only warnings were the two
  existing FastAPI `on_event` deprecations.
- **Syntax/whitespace:** `compileall` used an external `/tmp` bytecode root;
  `node --check` passed for both retained JavaScript assets; `git diff --check`
  passed.
- **Residual scan:** no remaining source/config/service/timer/publisher caller
  names a deleted file. `test_mvp_server_transport.py` intentionally retains
  `/frontend/app.js` and `/request_cache.js` as 404 rejection inputs. Current
  evidence docs name deleted paths only in the MOVE-OUT manifest; historical
  docs and root audit manifests are intentionally untouched.
- **Runtime/deployment:** **NOT VERIFIED**. Source/tests do not establish the
  served container, public API, freshness, browser, installed timer, or
  deployment state.

### 2. Elliott/Wave

> **Wave C2 owner disposition applied 2026-09-22:** **MOVE-OUT** removed the
> caller-free standalone variants `backend/elliott_variant_B.py` and
> `backend/elliott_variant_C.py`, `scripts/wave3_production_replay.py`, the
> retired standalone `backend/frontend/wave-context.{html,css,js}` surface and
> its dedicated test, and the isolated `prototypes/wave-context-groups/`
> research/replay family. Git history is the recovery authority.
>
> The active chart chain still calls `backend/chart_wave_evidence.py` from
> `backend/mvp_chart_db.py`; that module imports
> `backend/elliott_structure_engine.py`, which imports
> `backend/wave3_candidate_engine.py`. Those three modules, their focused tests
> and Elliott fixtures are therefore retained as **OWNER-DECISION** without
> publisher refactoring. `prototypes/elliott-state-replay/replay_lab.py` is
> also retained because the current Elliott decision record explicitly names
> it as a prototype asset. C2 does not change lifecycle, MVP/setup, VCP core,
> publishers, routes, schema, runtime, timers, or generated artifacts.

- **Current route reachability:** Source/test reachability exists through
  `elliott_structure_engine.py`, `wave3_candidate_engine.py`,
  `trade_setup_engine.py`, `mvp_api.py`,
  `trend_route_api.py`, and the historical setup/detail branches. The active
  Trend Map row/drawer contract explicitly suppresses Wave/setup semantics.
  No served or browser reachability was verified.
- **Publisher/test/operational references:** Retained Wave fixtures and replay evidence;
  `test_elliott_*`, `test_wave3_candidate_engine.py`, `test_trade_setup_engine.py`,
  historical intraday evaluation hooks, and Wave research/spec/handoff notes.
- **Authority role:** Historical/deferred research and former setup decision
  evidence. `docs/current/2026-08-31-elliott-grill-decision-record.md` records
  owner inputs, not a current promotion decision.
- **Rollback/audit value:** High for deterministic formula comparison, owner
  validation history, fixtures, lineage, and future reactivation review.
- **Contradictions:** Wave labels and “active” evaluator/unit terminology can
  be mistaken for active product authority; active Trend Map must remain
  classification/evidence only and cannot emit setup or action decisions.
- **Disposition:** **OWNER-DECISION**. Preserve the evidence; no promotion or
  cleanup follows from this record.

### 3. VCP — owner MOVE-OUT disposition partially applied in Wave C1

- **Current route reachability:** `/api/vcp-finder` compatibility handling was
  removed from `mvp_routes.py`; the active transport already rejected that
  route. Runtime/public removal remains unverified.
- **Publisher/test/operational references:** The standalone finder/replay
  commands, replay analyzer, mixed shortlist probe, and their focused tests
  were deleted. `update_data.py` still contains an intraday VCP hook and
  directly imports `vcp_finder_db.py`; C1 did not alter intraday/current
  publisher code, so the DB adapter and its transitive finder/policy/decision
  modules and focused tests remain pending a separately authorized removal.
- **Authority role:** Compatibility, audit, and replay history. `vault/VCP-
  Finder-MVP.md` and related replay records do not override the active-only
  freeze; VCP is not a current candidate gate.
- **Rollback/audit value:** Git history is the owner-selected recovery
  authority for deleted VCP source and tests; decision records remain.
- **Disposition:** **MOVE-OUT**, owner-approved after Issue #76. Wave C1 is
  partial because the explicit intraday/current-publisher no-go boundary
  retains the directly reachable core cluster as **OWNER-DECISION**.

### 4. Shadow/private-signal/actionable signal — owner disposition applied

- **Current route reachability:** None in source after cleanup Wave B. The
  active Trend Map envelope remains `actionability=NONE`; runtime/API removal
  is not verified in the worktree.
- **Publisher/test/operational references:** The implementation and focused
  tests were deleted. The private-signal design and old `BUY_NOW`/paper/shadow
  prose remain historical decision evidence only.
- **Authority role:** Historical/deferred policy and audit material only.
  Current Product Strategy and the active-only freeze explicitly turn this
  family off and require a new owner decision before resumption.
- **Rollback/audit value:** High for policy/version, replay, and safety-boundary
  history; it demonstrates why active pages must not serialize action fields.
- **Contradictions:** Old private-signal specs and Product Strategy sections
  describe a previous shadow product; they do not imply source reachability.
- **Disposition:** **DELETE**, applied in cleanup Wave B. Policy/replay source,
  tests, and the MVP route/UI were removed; Git history is rollback authority.

### 5. Delivery/alerts/broker/portfolio — owner disposition applied

- **Current route reachability:** None in source after cleanup Wave B. Runtime
  removal and installed Compose state are not verified in the worktree.
- **Publisher/test/operational references:** Portfolio and delivery source and
  focused tests were deleted. Historical alert/action and future Wayfinder
  prose remains decision evidence only.
- **Authority role:** Future/deferred planning and safety/audit boundary;
  alerts, broker execution, and auto-trading remain OFF and separately gated.
- **Rollback/audit value:** High for proving no-actionability boundaries,
  simulated-vs-real separation, idempotency/risk requirements, and historical
  recovery planning.
- **Contradictions:** Product Strategy and Wayfinder may describe future
  proposal/execution phases; they do not restore the deleted implementation.
- **Disposition:** **DELETE**, applied in cleanup Wave B. The portfolio
  module/routes/tests, delivery source, and disabled Compose alerts profile
  were removed. Runtime removal is not verified in the worktree.

### 6. Lifecycle/Team Facts

> **Wave C3a owner disposition review 2026-09-22:** The requested disposition
> is **DELETE**, but the exact caller scan found current or retained
> compatibility callers for every candidate source family. C3a therefore
> deletes **zero files / zero LOC** and records the unresolved seams as
> **OWNER-DECISION**. No speculative extraction or broad MVP refactor was used
> to manufacture dead code.

- **Exact source manifest and direct callers:**

  | Candidate | Direct caller / bootstrap evidence | C3a disposition |
  |---|---|---|
  | `backend/lifecycle_contract.py` | imported by `lifecycle_persistence.py` | Retain — lifecycle compatibility chain |
  | `backend/lifecycle_persistence.py` | imported by mounted `lifecycle_routes.py`; opt-in hook in `mvp_api.py` | Retain — route and MVP compatibility callers |
  | `backend/lifecycle_repository.py` | imported by `lifecycle_routes.py` and lazy read helpers in `lifecycle_persistence.py` | Retain — lifecycle compatibility chain |
  | `backend/lifecycle_routes.py` | imported and mounted by `app.py` with `app.include_router(...)` | Retain — source-reachable route |
  | `backend/team_facts_api.py` | active `trend_map.py` imports `_is_completed`; `mvp_routes.py` imports list/history builders | Retain — active helper plus historical compatibility routes |
  | `backend/setup_state.py` | imported by `app.py` and `screening.py` | Retain — not lifecycle-only |
  | `backend/migrations/007_lifecycle_persistence.sql` | loaded as `MIGRATION_SQL` by `lifecycle_persistence.py`; executed by `init_lifecycle_schema()` tests | Retain — referenced schema bootstrap |
  | `backend/owner_auth.py` | imported by retained `lifecycle_routes.py` | Retain — fail-closed route dependency |

- **Dedicated test disposition:** `test_lifecycle_contract.py`,
  `test_lifecycle_persistence.py`, `test_lifecycle_postgres.py`, and
  `test_lifecycle_routes.py` directly exercise retained lifecycle modules;
  `test_team_scan_api.py` directly imports Team Facts and exercises the
  retained MVP compatibility routes. They are retained. The separately named
  `test_breakout_lifecycle.py` exercises `scan_history` breakout history, not
  the candidate lifecycle modules above, and is outside this deletion family.
- **Before/after tracked source+dedicated-test inventory:** 11 files / 2,527
  LOC before; 11 files / 2,527 LOC after. Deletion delta: 0 files / 0 LOC.
  (`setup_state.py` and `owner_auth.py` add 141 retained dependency LOC but are
  not dedicated lifecycle/Team Facts files.)
- **Current route reachability:** Team Facts and lifecycle APIs are not among
  the four active product routes. Nevertheless, lifecycle routes remain
  mounted in source; Team Facts remains reachable from retained MVP
  compatibility routes; and active Trend Map shares a completed-bar helper
  from Team Facts. Runtime/public reachability and DB state were not checked.
- **Publisher/test/operational references:** Lifecycle contract, PostgreSQL,
  persistence, route, and deferred-runtime tests; the opt-in persistence hook;
  Team Facts API tests and retained compatibility route tests. The lifecycle
  tests record that automatic evaluator persistence is not wired; #75
  separately says `ExecStopPost` evaluation is not publication.
- **Authority role:** Historical/audit evidence and pending owner-review
  contract. The active-only freeze gives Team Facts no active route or
  refresh assumption.
- **Rollback/audit value:** High for immutable candidate/snapshot/review
  lineage, owner review history, and distinguishing evidence persistence from
  execution.
- **Contradictions:** Historical Execution Pipeline text contains prior Team
  Facts runtime evidence and current counts, while the active freeze marks it
  historical/deferred; lifecycle database schemas exist without proof of live
  use; “active” evaluator wording can be confused with active product scope.
- **Disposition:** Owner requested **DELETE**, but C3a result is
  **OWNER-DECISION / RETAINED** at the proven caller seams above. Preserve
  source, schema, tests, and history until a separately authorized route/MVP
  compatibility decision removes or replaces those callers. No DB, route,
  refresh, evaluator, publisher, pointer, timer, or runtime change is
  authorized here.

### 7. Prototypes and old frontend

- **Current route reachability:** Wave C2 removed `wave-context.*`; Wave C3b
  removed the caller-free `backend/frontend/index.html`, `app.js`, and
  `request_cache.js`. The active Trend Map template allowlists `styles.css`,
  `canonical-client.js`, and `shared-drawer.js`; the shared drawer has an
  active read-only path and legacy branches. Active page source reachability
  is verified; browser reachability is not.
- **Publisher/test/operational references:** The retained shared-drawer portion
  of `test_mvp_ui_feedback_contract.py`, `test_dashboard_*` compatibility
  builder tests, `test_legacy_routes.py`, and active template tests remain.
  The standalone Wave Context and request-cache tests and old browser harness
  were removed in C2/C3b. No browser journey or asset-load probe was run here.
- **Authority role:** The active template/drawer subset supports read-only
  evidence review; prototypes and old dashboard branches are historical or
  compatibility material, not route authority.
- **Rollback/audit value:** Medium-to-high for UI regression comparison,
  responsive/failure-state evidence, and recovering the active drawer seam.
- **Contradictions:** `canonical-client.js` still builds/fetches
  `/api/setup-candidates`; shared drawer retains canonical-MVP detail code.
  These unresolved branches remain owner decisions because the same assets
  have active callers.
- **Disposition:** **MOVE-OUT** for the isolated old frontend cluster;
  **OWNER-DECISION / KEEP** for the active read-only assets, shared drawer,
  legacy branches inside retained assets, and named prototype assets.

### 8. `docs/archive`, `vault/archive`, old plans/specs/handoffs

- **Current route reachability:** None is a runtime route or publisher. These
  documents are reachable as repository references and may describe old routes,
  policies, timers, or browser evidence; that does not make them current
  authority.
- **Publisher/test/operational references:** Archived superpowers specs/plans,
  reviews, postmortems, vault handoffs, replay notes, and old operational
  procedures. They contain reference targets and recovery context but no fresh
  installed/runtime proof.
- **Authority role:** Historical/audit/recovery material. `vault/INDEX.md` and
  Documentation Governance route current decisions to concern-specific
  authorities; archive material does not supersede the active-only freeze.
- **Rollback/audit value:** High: chronology, prior acceptance evidence,
  owner decisions, incident context, and Git/reference recovery. Git history,
  approved tags/branches, or a later owner-approved archive remain the recovery
  boundary.
- **Contradictions:** Some archived prose says setup/shadow/VCP is current or
  planned, while current headers say historical/deferred; a reference scan has
  not been authorized as a cleanup action and old documents may still be
  linked by audit material.
- **Disposition:** **OWNER-DECISION**. No archive deletion, movement, rewrite,
  or reclassification occurs in Issue #76.

### 9. Compatibility adapters and historical tests

- **Current route reachability:** `mvp_routes.py`, `trend_route_api.py`,
  `canonical_setup_projection.py`, `canonical_freshness_lineage.py`, chart
  adapters, legacy dispatch, and compatibility APIs are source-visible. Some
  active drawer/detail calls reach retained compatibility seams; historical
  setup/VCP branches do not become active by import. Runtime/API and browser
  reachability were not verified.
- **Publisher/test/operational references:** `artifact_pointer_inventory.py`,
  read-model/publisher modules, chart/intraday adapters, legacy/setup/VCP/
  lifecycle tests, and operational `update_data` hooks. #73–#74 record focused
  source/test evidence, five Trend Map publisher/readback test failures, and
  absent chart pointers/targets in the inspected checkout.
- **Authority role:** Active compatibility seam where explicitly called by the
  four-route read-only path; otherwise historical/audit test coverage. Tests
  are evidence, not authority, and old tests do not authorize route revival.
- **Rollback/audit value:** High for contract regression detection, pointer
  identity/hash validation, fail-closed behavior, and historical comparison.
- **Contradictions:** Active dispatch imports compatibility modules; legacy
  exports still name setup candidates; `shadow` remains in immutable artifact
  identifiers; publisher/readback field expectations are unresolved; chart
  artifacts are absent from the checkout despite prior dated evidence.
- **Disposition:** **OWNER-DECISION**. Keep the active pointer/read-only
  compatibility seams and tests intact pending a bounded owner decision; do
  not normalize, delete, move, or rewrite them here.

## Protected invariants and unresolved choices

Preserve without reinterpretation:

- The four active routes and their deterministic read-only envelope:
  `PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`.
- Active Thai ORD / `marginable_long` universe identity, provenance, timezone,
  freshness, lineage, no-lookahead, missing/stale/invalid/blocked states, and
  fail-closed semantics.
- `backend/trend-map-read-model/current.json`, its validated immutable target,
  `backend/market-breadth-read-model/current.json`, its validated immutable
  target, and the intraday display-only sidecar. Preserve exact pointer field
  names, artifact IDs, hashes, paths, schema, as-of, and policy values.
- Active Trend Map row/drawer support only as read-only evidence review
  (`1D`, `60M`, `1W`, `1M`); absent chart artifacts remain unresolved evidence,
  not a deletion signal.
- Git history/approved recovery references as historical rollback value. No
  current-plus-N retention, archive creation, or cleanup scheme is introduced.

Owner choices still open:

1. Whether any historical family should later be kept in place, consolidated,
   moved to an approved archive, or deleted after a complete reference and
   rollback review.
2. Whether and how to resolve the `verify_mvp_only.py` EOD post-step,
   compatibility publisher/readback mismatches, and old frontend exports.
3. Whether Team Facts/lifecycle, chart artifacts, timers, private services,
   delivery, or any setup/Wave/VCP family has a future owner-approved scope.
4. Whether the absent chart pointers/targets are runtime/environment state or
   an artifact evidence gap. Do not regenerate or infer either answer.

## Exact read-only commands and evidence

Commands used in this slice, from `/tmp/signalix-t76`:

```text
git status --short --branch
=> ## codex/t76-historical-disposition (clean before this file)

git rev-parse HEAD && git log -1 --format='%H%n%cI%n%s'
=> 6479c3ac7a8f304dd59990a30319dabd9b6b2daa
   2026-09-21T07:37:37+07:00
   docs(t75): record Compose and timer ownership

date --iso-8601=seconds
=> 2026-09-21T07:39:29+07:00

rg --files -g 'AGENTS.md' -g 'docs/current/**' -g 'vault/**'
rg -n -i '#(72|73|74|75|76|77|78)|owner.?decision|disposition' docs/current vault docs/archive vault/archive --glob '*.md'
rg --files backend docs vault scripts | rg -i '(mvp|setup|elliott|wave|vcp|shadow|signal|action|alert|broker|portfolio|delivery|lifecycle|fact|prototype|frontend|compat|legacy|archive|test)'
rg -n -i '/mvp|api/setup-candidates|trend-map|market-breadth|publish_|publisher|timer|service|delivery|shadow|vcp|wave|lifecycle|team facts|setup' backend docker-compose.yml scripts --glob '!*.pyc'
sed -n '1,260p' docs/current/2026-09-20-active-only-contract-freeze.md
sed -n '1,260p' docs/current/2026-09-20-active-only-reachability-ledger.md
sed -n '1,260p' docs/current/2026-09-21-active-backend-route-test-closure.md
sed -n '1,240p' docs/current/2026-09-21-publisher-pointer-artifact-ownership.md
sed -n '1,240p' docs/current/2026-09-21-compose-timer-service-ownership.md
sed -n '1,220p' vault/Execution-Pipeline.md
sed -n '1,220p' vault/Product-Strategy-Market-to-Action.md
sed -n '1,180p' vault/INDEX.md
=> read-only inspection of current authority, #72–#75 evidence, source,
   tests, publishers, operational references, and historical references;
   no secrets, runtime, database, timer, browser, or public endpoint was read.
```

The review did not run tests, start services, invoke Compose/systemd, make HTTP
requests, access a database, inspect installed timers, generate artifacts, or
perform browser automation. Those omissions are intentional and leave the
runtime/API, freshness, and browser verdicts above unresolved.

## Handoff

- **#77:** independently verify desktop and 390px browser/UI journeys for the
  four active routes, including chart drawer and blocked/error/retry states;
  keep browser verdict separate from this source/history disposition.
- **#78:** after owner review of #72–#77, propose any bounded implementation or
  cleanup decision with exact paths, reference scan, rollback plan, and a new
  authority update. No #78 action is authorized by this record.

## Self-check boundary

Only the new Markdown file and repository metadata are in scope for self-check:
`git diff --name-status`, `git diff --check`, and a no-index whitespace check.
No commit is created; Lite reviews and commits this documentation slice.
