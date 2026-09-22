# Active backend route and test closure — Issue #73

> **STATUS: CURRENT CHECKOUT EVIDENCE RECORD** · Spec: Issue #71. Previous
> ledger: Issue #72, commit `54919d35f34a6b2460b94818696d8625975ac8e1`.
> Evidence timestamp: `2026-09-21T07:25:46+07:00` (ICT). This is a read-only
> evidence decision record. It authorizes no deletion, move, consolidation,
> runtime change, deployment, artifact generation, or authority rewrite.

## Checkout and boundary

| Field | Evidence |
|---|---|
| Checkout SHA | `54919d35f34a6b2460b94818696d8625975ac8e1` |
| Branch | `codex/t73-active-closure` |
| Active product | Daily Trend Map and Market Breadth, deterministic/read-only |
| Active routes | `/trend-map`, `/api/trend-map`, `/market-breadth`, `/api/market-breadth` |
| Safety envelope | `status=PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE` |
| Out of scope | `/mvp`, `/api/setup-candidates`, Team Facts, setup/actionable-signal families, alerts, broker execution, auto-trading |

The authority read for scope was `docs/current/2026-09-20-active-only-contract-freeze.md`.
The prior protected-target and reachability evidence was
`docs/current/2026-09-20-active-only-reachability-ledger.md` (Issue #72),
with supporting context from `docs/current/2026-09-20-pointer-artifact-inventory.md`,
`docs/current/2026-09-20-active-cleanup-review.md`, and the relevant vault
architecture, components, execution-pipeline, product-strategy, deployment,
governance, and index notes. Those documents remain unchanged.

> **Wave C3b reconciliation — 2026-09-22:** `active_transport.py` is now the
> sole dashboard transport. The caller-free duplicate `mvp_server.py` and
> isolated historical `/mvp` frontend/test/harness cluster were moved out.
> The explicit retired-route 410 behavior and active chart/drawer seams remain
> protected and tested. The original #73 runtime/browser verdict is unchanged.

## Separate verdicts

| Verdict | Result | Evidence boundary |
|---|---|---|
| SOURCE | **VERIFIED** | Checkout-pinned dispatch, handlers, templates, static assets, dynamic loads, callers, retirement paths, pointers, and tests were inspected. |
| RUNTIME/API | **NOT VERIFIED** | No server, Compose stack, HTTP/public ingress probe, service read-back, database, timer, or deployment operation was run. |
| DATA/POINTER | **REVISE / NOT VERIFIED for freshness** | Protected tracked pointers and referenced immutable targets are present in this checkout; dated artifact identity is not fresh served read-back, and the intraday evidence remains stale in #72. |
| BROWSER/UI | **NOT VERIFIED** | No browser automation, desktop/390px check, asset-load check, chart interaction, or public URL probe was run. |

## Route trace

### `/trend-map`

- **Dispatch/handler:** `backend/active_transport.py:ActiveTransportHandler.do_GET` has an
  exact `/trend-map` branch and reads `backend/trend_map_template.html`.
  Missing template handling is deterministic `404`. The handler statically
  imports `active_chart_routes`, `trend_map`, `trend_route_api`, and
  `market_breadth_artifact`; it does not import historical MVP dispatch.
- **Static assets:** the template references `/styles.css` and
  `/canonical-client.js`; it dynamically loads `/shared-drawer.js` only when
  a symbol row is opened. `ActiveTransportHandler` serves these three assets through its
  explicit allowlist; unknown assets are `404`.
- **Frontend request:** inline page code requests `/api/trend-map` with
  `cache=no-store`, requires the read-only envelope, `verification_status=VERIFIED`,
  and fresh data, and renders a visible `DATA_BLOCKED`/retry state otherwise.
- **Chart/detail callers reached from the active page:** clicking a row opens
  the shared drawer with `source="trend-map"`, `actionability="NONE"`, and no
  legacy detail/chart URL. The dynamically loaded drawer requests
  `/api/trend-map/{symbol}/route`; its chart request is
  `/api/chart-db/{symbol}?timeframe={1D|60M|1W|1M}&view=chart`.
  `1D` starts selected; timeframe controls reach the same chart compatibility
  seam. The drawer route and chart calls are separate from the four exact
  public page/API routes.
- **Backend read path:** `trend_map.handle_trend_map_api` builds/compacts the
  report and fails closed to an HTTP-200 visible `DATA_BLOCKED` envelope on
  exception. The current read-model path dynamically loads the read-model and
  intraday quote readers through the Trend Map implementation/publisher seam;
  source reachability does not prove a running process reached them.

**Disposition by family/path:** `backend/active_transport.py`,
`backend/trend_map.py`, `backend/trend_map_template.html`, and the three
allowlisted active assets — **KEEP**. Active Trend Map row/drawer route and
chart compatibility handlers — **KEEP** pending a separate owner review;
they are reached by active UI evidence review but are not one of the four
closure routes. The unused legacy API exports in `backend/frontend/canonical-client.js`
— **OWNER-DECISION**; do not remove or rewrite here.

### `/api/trend-map`

- **Dispatch/handler:** exact dispatch from `ActiveTransportHandler.do_GET` to
  `trend_map.handle_trend_map_api`; query variants still match by parsed path.
- **Read model:** the Trend Map publisher/readback seam validates the current
  pointer and relative immutable target; the handler does not authorize a
  request-path rebuild. `backend/intraday_quote_read_model.py` is a display-only
  sidecar, not a classification input according to the page contract.
- **Response contract:** source and tests preserve
  `PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`, and
  fail-closed `DATA_BLOCKED` behavior.
- **Tests:** direct handler, transport, HTML marker, publisher, pointer, and
  sidecar tests are listed below. Current served response and freshness remain
  unverified.

**Disposition by family/path:** Trend Map handler, publisher, pointer, target,
and sidecar — **KEEP**. The `shadow` spelling in report/schema/immutable
artifact identifiers — **KEEP** for identity and audit; a rename is an
owner decision, not a cleanup inference.

### `/market-breadth`

- **Dispatch/handler:** exact `ActiveTransportHandler.do_GET` branch reads
  `backend/market_breadth_template.html`; missing template is `404`.
- **Static/frontend behavior:** page navigation links to `/trend-map`; inline
  page logic fetches `/api/market-breadth?range=` for `20`, `60`, `260`, or
  `all`, with `cache=no-store`. It requires the read-only envelope, freshness,
  `history`, and `current`; invalid/stale/unavailable data is withheld as
  `DATA_BLOCKED`/error with Retry.
- **Chart/detail callers:** the page renders aggregate SVG/chart views in
  inline code from the selected breadth response. It has no symbol drawer or
  separate detail request. The Trend Map link is the only cross-page caller.
- **Backend read path:** `market_breadth_artifact.load_market_breadth_artifact`
  reads `current.json`, constrains the target to `versions/`, validates the
  content hash/canonical bytes/schema, and returns a prebuilt range. The API
  rejects invalid ranges with `400` and returns `DATA_BLOCKED`/`503` when the
  validated artifact is unavailable.

**Disposition by family/path:** `backend/market_breadth_artifact.py`,
`backend/market_breadth.py`, `backend/market_breadth_publisher.py`, and the
Market Breadth template — **KEEP**. Inline aggregate chart rendering —
**KEEP** as active read-only UI; browser acceptance remains unverified.

### `/api/market-breadth`

- **Dispatch/handler:** exact dispatch from `ActiveTransportHandler.do_GET` to
  `handle_market_breadth_api`; the handler preserves the query string for
  range validation.
- **Response contract:** validated prebuilt ranges are projected with the
  read-only envelope, provenance, freshness, quality, lineage/counts, active
  ORD identity, and content/range identity. No request-path calculation or
  database read is implied by the source contract.
- **Failure behavior:** invalid range is `400 DATA_BLOCKED`; loader/hash/
  validation failure is `503 DATA_BLOCKED`. The page separately blocks stale,
  unknown, or missing data.
- **Tests:** artifact response/range/failure tests, publisher tests, frontend
  contract tests, transport tests, and pointer inventory tests protect the
  source contract; served API behavior is not freshly checked.

**Disposition by family/path:** breadth handler, immutable publisher/readback,
current pointer, referenced target, and focused tests — **KEEP**.

## Static imports, dynamic loads, and compatibility seams

| Path/family | Evidence | Disposition |
|---|---|---|
| `backend/active_transport.py` imports `active_chart_routes`, `trend_map`, `trend_route_api`, `market_breadth_artifact` | The isolated dispatcher owns active routes, the retained read-only chart route, and explicit retired compatibility responses without importing MVP/setup dispatch. | **KEEP** |
| `backend/frontend/canonical-client.js` | Served by the active allowlist and statically loaded by Trend Map, but its exported functions still build/fetch `/api/setup-candidates`; no active Trend Map page call invokes those exports. | **OWNER-DECISION** |
| `backend/frontend/shared-drawer.js` | Dynamically loaded from Trend Map; active `trend-map` mode requests route history and chart-db data. Canonical-MVP detail merge code remains in the same shared module but is not selected by the active page envelope. | **KEEP** for active drawer; legacy branches **OWNER-DECISION** |
| `/api/trend-map/{symbol}/route` and `/api/chart-db/{symbol}` | Reachable from active Trend Map row interaction and explicitly allowlisted/retained by the dispatcher; they are compatibility seams outside the four exact closure paths. | **OWNER-DECISION** |
| `backend/frontend/index.html`, `app.js`, `request_cache.js` | Removed by owner-approved Wave C3b with their isolated tests/harness; no current transport, publisher, timer, active asset, or retained compatibility caller remained. | **MOVE-OUT** |
| Trend Map replay adapter dynamic import and publisher dynamic import from update path | Source-level research/publish compatibility; no service/timer execution was checked. | **KEEP**; operational reachability **OWNER-DECISION** |

Wave C3b applies the later owner-approved MOVE-OUT only to the exact caller-free
manifest in the current historical-family disposition. No broader
`CONSOLIDATE`, `DELETE`, or compatibility refactor is authorized here.

## Retirement and fallthrough behavior

`ActiveTransportHandler` has explicit behavior and focused tests for the boundary:

- `/mvp` and `/api/setup-candidates` return `410` with a retired payload;
- `/wave-context` and `/dashboard.html` return `404`;
- unknown API routes and unknown static assets return `404`;
- `/`, `/index`, and `/index.html` redirect to `/trend-map`;
- malformed retained route/chart shapes fall through deterministically to
  `404`.

These are compatibility/retirement protections, not evidence that old source
families are safe to delete. The active `canonical-client.js` legacy fetch
seam and the retained chart/detail APIs remain unresolved owner decisions.

## Tests and their status

### Active-contract protection

| Test family | What it protects | Disposition |
|---|---|---|
| `backend/test_mvp_server_transport.py` | Four active dispatches, asset allowlist, redirects, retired `410`/`404`, retained route/chart shapes, and deterministic fallthrough. | **KEEP** |
| `backend/test_trend_map.py` | Trend Map report/envelope, page markers, active drawer markers, `DATA_BLOCKED`, freshness/actionability, and handler behavior. | **KEEP** |
| `backend/test_market_breadth_artifact.py` | Range validation, immutable artifact response, envelope, hash/read failures, and API handler. | **KEEP** |
| `backend/test_market_breadth_frontend_contract.py` | Active page links, fetch shape, ranges, rendering, quality/freshness blocking, and no-actionability markers. | **KEEP** |
| `backend/test_artifact_pointer_inventory.py` | Pointer containment, target identity/hash/schema, and protected active read-model inventory. | **KEEP** |
| `backend/test_active_chart_adapter.py` | Read-only chart adapter envelope and active-route classification boundary. | **KEEP** |
| `backend/test_legacy_routes.py` | Explicit retirement/audit-only behavior and no fallback to setup candidates. | **KEEP** |

The focused command collected **140 tests**, with **138 passed, 1 skipped,
0 failed**. The skip is an existing test-level skip in the selected suite.
Warnings included the existing FastAPI `on_event` deprecation; no runtime was
started.

### Historical-only or supporting tests

Wave C3b removed `backend/test_signalix_contracts.py`, the stale live-service
contract script for the old `:8000`/`:3001/mvp` surfaces. The mixed
`test_mvp_ui_feedback_contract.py` remains after its old frontend assertions
were removed because it still protects the active shared drawer.
`test_team_scan_api.py`, retained VCP/setup, dashboard, and lifecycle test
families remain audit/supporting coverage because their source still has
publisher, compatibility, or protected dependency callers. Their existence is
not a product reactivation instruction.

A separate focused run including `backend/test_trend_map_read_model_publisher.py`
collected **160 tests** and returned **5 failed, 154 passed, 1 skipped**.
All five failures are in the publisher test module and are `KeyError` failures
for `timing`, `artifact_id`, or `counts` on the current readback shape. This is
source/test-contract evidence requiring follow-up, not a reason to alter the
active route or its protected pointer in this ticket.

## Protected #72 targets

Keep unchanged and protected:

- the four exact active routes and their deterministic envelope;
- `backend/trend-map-read-model/current.json` and its referenced immutable
  target;
- `backend/market-breadth-read-model/current.json` and its referenced
  immutable target;
- the intraday quote pointer/target as a Trend Map display sidecar;
- active Thai ORD / published `marginable_long` semantics, provenance,
  freshness, blocked states, and no-lookahead boundaries;
- chart drawer evidence only as shared read-only review (`1D`, `60M`, `1W`,
  `1M`), subject to fresh runtime/browser evidence;
- Git history or owner-approved recovery as the historical boundary.

The current checkout contains the tracked Trend Map and Market Breadth pointers
and referenced targets. The ignored chart read-model family is absent from this
checkout as recorded by #72; that absence is unresolved evidence, not a cleanup
candidate.

## Unresolved ambiguity and owner decisions

1. Decide whether the served `canonical-client.js` legacy setup-candidate
   exports should remain as compatibility source while unused, or be handled by
   a separately authorized migration. No action is taken here.
2. Decide the long-term ownership of active-page chart/detail compatibility
   APIs (`/api/trend-map/{symbol}/route`, `/api/chart-db/{symbol}`) and their
   historical branches in the shared drawer.
3. Reconcile the publisher readback test failures (`timing`, `artifact_id`,
   `counts`) against the current implementation before using those tests as a
   publisher-closure gate.
4. Obtain fresh runtime/API, pointer/freshness, browser/UI, service/timer, and
   public-ingress evidence before any `CONSOLIDATE`, `DELETE`, or `MOVE-OUT`
   disposition.

## Handoff to #74–#77

- **#74:** resolve the source compatibility seam and define the exact active
  backend/static ownership boundary; preserve the protected targets.
- **#75:** reconcile publisher/readback implementation versus its five failing
  tests; keep route acceptance separate from this contract mismatch.
- **#76:** perform the separately authorized runtime/API and pointer/freshness
  verification, including the ignored-chart ambiguity; do not infer served
  state from this source record.
- **#77:** perform browser/UI acceptance at desktop and 390px mobile, including
  Trend Map drawer/chart/error states and Market Breadth range/error states;
  record public URL evidence separately.

## Exact read-only commands

Commands run in `/tmp/signalix-t73`; no secrets, `.env*`, credentials, or
private keys were read:

```text
git status --short --branch
git rev-parse HEAD
git log -1 --format='%H%n%cI%n%s'
date --iso-8601=seconds
rg --files docs/current vault | rg '2026-09-20|2026-09-21|Execution-Pipeline|Product-Strategy|Architecture|Components|INDEX' | sort | head -80
rg -n "trend-map|market-breadth|setup-candidates|/mvp|410|404|styles\.css|canonical-client|shared-drawer|fetch\(|import_module|importlib" backend --glob '*.py' --glob '*.html' --glob '*.js' --glob '*.css' | head -260
sed -n '1,220p' backend/active_transport.py
sed -n '1,130p' backend/trend_map.py
sed -n '950,1040p' backend/trend_map.py
sed -n '1,330p' backend/market_breadth_artifact.py
sed -n '1,90p' backend/trend_map_template.html
sed -n '1,180p' backend/frontend/shared-drawer.js
sed -n '1,80p' backend/frontend/canonical-client.js
rg -n "fetch\(" backend/frontend backend/trend_map_template.html backend/market_breadth_template.html
git ls-files backend/trend-map-read-model backend/market-breadth-read-model backend/read-model/charts
git check-ignore -v backend/read-model/charts/current-1D.json backend/read-model/charts/versions/x.json
PYTHONPATH=backend pytest --collect-only -q -p no:cacheprovider \
  backend/test_mvp_server_transport.py backend/test_trend_map.py \
  backend/test_market_breadth_artifact.py \
  backend/test_market_breadth_frontend_contract.py \
  backend/test_artifact_pointer_inventory.py \
  backend/test_active_chart_adapter.py backend/test_legacy_routes.py
PYTHONPATH=backend pytest -q -p no:cacheprovider \
  backend/test_mvp_server_transport.py backend/test_trend_map.py \
  backend/test_market_breadth_artifact.py \
  backend/test_market_breadth_frontend_contract.py \
  backend/test_artifact_pointer_inventory.py \
  backend/test_active_chart_adapter.py backend/test_legacy_routes.py
PYTHONPATH=backend pytest -q -p no:cacheprovider \
  backend/test_mvp_server_transport.py backend/test_trend_map.py \
  backend/test_market_breadth_artifact.py \
  backend/test_market_breadth_frontend_contract.py \
  backend/test_trend_map_read_model_publisher.py \
  backend/test_artifact_pointer_inventory.py \
  backend/test_active_chart_adapter.py backend/test_legacy_routes.py
git diff --check
git diff --no-index --check /dev/null docs/current/2026-09-21-active-backend-route-test-closure.md
git diff --no-index --numstat /dev/null docs/current/2026-09-21-active-backend-route-test-closure.md
git status --short
```

`git diff --check` passed. The no-index whitespace check emitted no whitespace
diagnostics and returned exit `1` because `/dev/null` and the new file differ,
which is the expected no-index diff status. The final status contained exactly
one untracked path: this new Markdown file.

No server start, HTTP/public probe, browser automation, Compose/systemctl or
timer command, database operation, artifact generation, pointer write,
deletion, move, cleanup, commit, push, deploy, restart, or migration was run.

## Final decision

**SOURCE: VERIFIED.** The four active routes and their source-level callers,
retirement handling, protected targets, and tests are traced. **RUNTIME/API:
NOT VERIFIED. DATA/POINTER: REVISE / NOT VERIFIED for freshness. BROWSER/UI:
NOT VERIFIED.** No cleanup action is authorized; the only unresolved changes
are owner decisions listed above.
