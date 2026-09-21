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
**MOVE-OUT**, and **OWNER-DECISION**. Because the evidence gaps below prevent
safe inference about reachability, rollback, or reference completeness, every
historical family receives **OWNER-DECISION**. No `DELETE`, `MOVE-OUT`, or
`CONSOLIDATE` action is selected in this record.

## Cross-family verdicts

| Evidence dimension | Result | What it proves / does not prove |
|---|---|---|
| **SOURCE** | **VERIFIED for classification** | The checkout contains dispatch, imports, callers, publishers, tests, units, templates, historical docs, and compatibility references identified below. Source reachability is not served reachability. |
| **RUNTIME/API** | **NOT VERIFIED / OWNER-DECISION** | No server, Compose, HTTP/public ingress, database, systemd, timer, service, or live publisher read-back was run in this issue. |
| **DATA/POINTER** | **REVISE / OWNER-DECISION** | Tracked Trend Map, intraday, and Market Breadth pointers/targets are protected by #72–#74; chart pointers/targets were absent in that checkout. Dated identity is not fresh runtime or freshness proof. |
| **BROWSER/UI** | **NOT VERIFIED / OWNER-DECISION** | No desktop, 390px mobile, asset-load, chart-drawer, empty/error, or public URL journey was run. #77 remains the browser/UI handoff. |

## Family review

### 1. MVP/setup and setup candidate

- **Current route reachability:** Source-visible through historical
  `backend/mvp_server.py`/`backend/mvp_routes.py`, `/mvp`, and
  `/api/setup-candidates`; `backend/test_legacy_routes.py` verifies explicit
  retirement behavior. It is not an active route. The active dispatcher still
  imports compatibility `mvp_routes`, so source reachability is not zero.
- **Publisher/test/operational references:** `mvp_api.py`, `mvp_snapshot.py`,
  `setup_candidate_contract.py`, `read_model_publisher.py`,
  `verify_mvp_only.py`, setup/MVP tests, `update_data.service`'s
  `ExecStartPost`, `scripts/browser_failure_retry_harness.sh`, and
  `scripts/probe_shortlist.sh`. #75 records the `verify_mvp_only.py` post-step
  as a contradiction, not as active ownership.
- **Authority role:** Historical setup/API contract and audit evidence only;
  the active-only freeze, Product Strategy, Execution Pipeline, and #72–#75
  route records supersede it for current product scope.
- **Rollback/audit value:** High. It preserves prior setup schemas, retirement
  responses, source lineage, replay comparison, and recovery context.
- **Contradictions:** Historical tests and scripts still name live-looking
  setup/VCP paths; the EOD unit names a retired verification command; old
  Product Strategy sections describe `/mvp` as a former product while its
  current header marks it deferred. Runtime reachability is unknown.
- **Disposition:** **OWNER-DECISION**. Do not delete, move, consolidate,
  start, or route active evidence through this family.

### 2. Elliott/Wave

- **Current route reachability:** Source/test reachability exists through
  `elliott_structure_engine.py`, `elliott_variant_*.py`,
  `wave3_candidate_engine.py`, `trade_setup_engine.py`, `mvp_api.py`,
  `trend_route_api.py`, and the historical setup/detail branches. The active
  Trend Map row/drawer contract explicitly suppresses Wave/setup semantics.
  No served or browser reachability was verified.
- **Publisher/test/operational references:** Wave fixtures and replay scripts;
  `test_elliott_*`, `test_wave3_candidate_engine.py`, `test_trade_setup_engine.py`,
  `test_wave_context_frontend_contract.py`, `scripts/wave3_production_replay.py`,
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

### 3. VCP

- **Current route reachability:** Source-visible via `vcp_finder.py`,
  `unified_vcp_decision.py`, `vcp_decision_policy.py`, `mvp_routes.py`, and
  `/api/vcp-finder` compatibility handling. It is not one of the four active
  routes. No current served reachability was verified.
- **Publisher/test/operational references:** `run_vcp_finder.py`,
  `run_vcp_replay_1m.py`, `analyze_vcp_shadow_replay.py`, VCP DB/policy tests,
  `scripts/probe_shortlist.sh`, `update_data.py`/intraday VCP hooks, and VCP
  replay/decision notes. These are audit/replay references, not active
  publication proof.
- **Authority role:** Compatibility, audit, and replay history. `vault/VCP-
  Finder-MVP.md` and related replay records do not override the active-only
  freeze; VCP is not a current candidate gate.
- **Rollback/audit value:** High for replay baselines, bonus-evidence lineage,
  policy comparisons, and explaining historical setup outputs.
- **Contradictions:** “Canonical VCP” and shadow route names remain in scripts,
  tests, and old docs while current routes prohibit setup/action semantics;
  the probe script mixes retired VCP/setup requests with a Trend Map probe and
  writes evidence output.
- **Disposition:** **OWNER-DECISION**. Keep available for audit; do not run,
  promote, or remove it under Issue #76.

### 4. Shadow/private-signal/actionable signal

- **Current route reachability:** Source-visible in `shadow_signal_replay.py`,
  `actionable_signal_policy.py`, `action_queue.py`, private-signal specs, and
  historical UI/detail paths. The active Trend Map envelope explicitly sets
  `actionability=NONE`; no private signal or shadow-service runtime/API
  reachability was checked.
- **Publisher/test/operational references:** Actionable-signal and shadow
  replay tests, private signal design, delivery/Redis references, and old
  `BUY_NOW`/paper/shadow material. #75 identifies the delivery profile as
  source-present but deferred; installed/profile-selected state is unknown.
- **Authority role:** Historical/deferred policy and audit material only.
  Current Product Strategy and the active-only freeze explicitly turn this
  family off and require a new owner decision before resumption.
- **Rollback/audit value:** High for policy/version, replay, and safety-boundary
  history; it demonstrates why active pages must not serialize action fields.
- **Contradictions:** Old private-signal specs and Product Strategy sections
  describe a future/previous shadow product; source names and tests can look
  active; any `BUY_NOW`, alert, or execution semantics would contradict the
  current envelope.
- **Disposition:** **OWNER-DECISION**. No signal publication, re-enable, or
  cleanup is authorized.

### 5. Delivery/alerts/broker/portfolio

- **Current route reachability:** Source/configuration reachability exists in
  `delivery.py`, `delivery_consumer.py`, `portfolio.py`, portfolio routes,
  `docker-compose.yml`'s disabled/profiled `delivery` service, and Wayfinder
  future tickets. No active route reaches this family under the current
  contract, and no runtime/profile or broker reachability was verified.
- **Publisher/test/operational references:** Delivery, signal, portfolio,
  broker-adapter, risk, and portfolio tests; Redis `signals` subscription;
  Compose profile and historical alert/action docs. These references do not
  establish an installed consumer, credentials, broker session, or order path.
- **Authority role:** Future/deferred planning and safety/audit boundary;
  alerts, broker execution, and auto-trading remain OFF and separately gated.
- **Rollback/audit value:** High for proving no-actionability boundaries,
  simulated-vs-real separation, idempotency/risk requirements, and historical
  recovery planning.
- **Contradictions:** Compose makes delivery operationally present in source
  while the active product forbids alerts/orders; Product Strategy describes
  future proposal/execution phases; “active” names in old evaluator paths do
  not promote this family.
- **Disposition:** **OWNER-DECISION**. Do not enable, connect, publish, or
  clean up this family in this record.

### 6. Lifecycle/Team Facts

- **Current route reachability:** Source/tests exist in `lifecycle_routes.py`,
  `lifecycle_persistence.py`, `lifecycle_repository.py`, migration `007`,
  `team_facts_api.py`, and their route tests. Team Facts and lifecycle APIs
  are not part of the four active routes; current runtime, DB state, and
  evaluator caller reachability were not checked.
- **Publisher/test/operational references:** Lifecycle contract, PostgreSQL,
  persistence, route, and deferred-runtime tests; `run_intraday_evaluation`
  and the opt-in persistence hook; Team Facts API tests and old runtime
  handoffs. The lifecycle tests record that automatic evaluator persistence is
  not wired; #75 separately says `ExecStopPost` evaluation is not publication.
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
- **Disposition:** **OWNER-DECISION**. Preserve schemas/tests/history; no DB,
  route, refresh, or evaluator change is authorized.

### 7. Prototypes and old frontend

- **Current route reachability:** Historical frontend files include
  `backend/frontend/index.html`, `app.js`, `wave-context.*`, legacy client
  exports, and prototype/research paths. The active Trend Map template
  allowlists `styles.css`, `canonical-client.js`, and `shared-drawer.js`; the
  shared drawer has an active read-only path and legacy branches. Active page
  source reachability is verified by #73; browser reachability is not.
- **Publisher/test/operational references:** Frontend contract/UI tests,
  `test_dashboard_*`, `test_wave_context_frontend_contract.py`, request-cache
  tests, `test_legacy_routes.py`, old browser harnesses, and active template
  tests. No browser journey or asset-load probe was run in #72–#75.
- **Authority role:** The active template/drawer subset supports read-only
  evidence review; prototypes and old dashboard branches are historical or
  compatibility material, not route authority.
- **Rollback/audit value:** Medium-to-high for UI regression comparison,
  responsive/failure-state evidence, and recovering the active drawer seam.
- **Contradictions:** `canonical-client.js` still builds/fetches
  `/api/setup-candidates`; shared drawer retains canonical-MVP detail code;
  old harnesses target `/mvp`. #73 assigns these unresolved branches to owner
  review rather than removal.
- **Disposition:** **OWNER-DECISION**. Protect the active read-only assets and
  drawer contract; do not remove or consolidate legacy branches here.

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
