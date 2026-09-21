# Active-only route reachability ledger

> **STATUS: CURRENT CHECKOUT LEDGER** · Scope: Issue #72 / specification Issue
> #71 / parent cleanup direction #59. This is an evidence inventory, not a
> deletion, movement, deployment, restart, migration, or runtime-change
> authorization. Evidence timestamp: `2026-09-21T00:58:11+07:00` (ICT).

## Checkout and contract boundary

| Field | Evidence |
|---|---|
| Checkout | `ea323ee543e753ad1ccdb27b3a21a4db5e3ebaee` (`docs: finalize stable cleanup closeout`, `2026-09-20T20:25:47+07:00`) |
| Branch | `codex/t72-active-reachability-ledger` |
| Active routes | `/trend-map`, `/api/trend-map`, `/market-breadth`, `/api/market-breadth` |
| Envelope boundary | `status=PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`; deterministic, read-only, fail closed |
| Out of scope | `/mvp`, `/api/setup-candidates`, Team Facts, Elliott/Wave/VCP setup work, private signals, alerts, broker execution, and auto-trading |

The active-only contract freeze is the routing authority. The product strategy,
Execution Pipeline, Architecture, Components, Deployment, Documentation
Governance, pointer/artifact inventory, and active cleanup review were read for
this ledger. The dated inventory and cleanup review are evidence notes, not
fresh runtime proof. Historical material remains audit/recovery material and is
not promoted by this ledger.

## Verdicts are separate

| Verdict | Result | Basis and limit |
|---|---|---|
| SOURCE | **VERIFIED** | Checkout source, imports, dispatch, templates, publishers, operational references, and focused test names were inspected. No source was edited. |
| RUNTIME/API | **NOT VERIFIED / OWNER-DECISION** | No server, Compose stack, public ingress, database, timer, or service read-back was run in this ticket. Old notes and issue comments are not fresh served-route evidence. |
| DATA/POINTER | **REVISE** | Current Trend Map, intraday, and Market Breadth pointers and their targets exist in this checkout and were read-only inspected; the ignored chart current pointers/targets are absent from this checkout. The pointer inventory records earlier validation, but cannot substitute for current checkout/runtime proof. |
| BROWSER/UI | **NOT VERIFIED** | No desktop, 390px mobile, browser asset, chart-drawer, empty/error, or public URL probe was performed. |

## Reachability graph by active route

| Route | Static dispatch / handler | Frontend or static request | Read model / safety seam | Focused evidence |
|---|---|---|---|---|
| `/trend-map` | `backend/mvp_server.py:MVPHandler.do_GET` reads `backend/trend_map_template.html` | Template links to `/market-breadth`; includes `/styles.css`, `/canonical-client.js`, `/shared-drawer.js`; template requests `/api/trend-map` | `backend/trend_map.py:handle_trend_map_api` builds a compact public report and returns a visible `DATA_BLOCKED` envelope on exception; published source dynamically imports `read_current_trend_map_report` and overlays the intraday quote read model | `backend/test_mvp_server_transport.py`, `backend/test_trend_map.py`, `backend/test_active_chart_adapter.py` |
| `/api/trend-map` | Exact path dispatch in `backend/mvp_server.py` to `handle_trend_map_api` | Requested by `backend/trend_map_template.html`; drawer requests are separate retained APIs and are not one of the four ledger routes | `backend/trend_map_read_model_publisher.py` validates `current.json` plus its relative immutable artifact; `backend/intraday_quote_read_model.py` is a display-only sidecar; no request-path rescan/rebuild is intended | `backend/test_trend_map.py`, `backend/test_mvp_server_transport.py`, `backend/test_trend_map_read_model_publisher.py`, `backend/test_intraday_quote_read_model.py`, `backend/test_artifact_pointer_inventory.py` |
| `/market-breadth` | Exact path dispatch in `backend/mvp_server.py` reads `backend/market_breadth_template.html` | Template links back to `/trend-map` and dynamically fetches `/api/market-breadth?range=` for `20`, `60`, `260`, or `all` | `backend/market_breadth_artifact.py:load_market_breadth_artifact` reads and hash-validates `current.json` plus `versions/market-breadth-<hash>.json`; template blocks stale/unavailable data and exposes Retry | `backend/test_mvp_server_transport.py`, `backend/test_market_breadth_frontend_contract.py`, `backend/test_market_breadth_artifact.py` |
| `/api/market-breadth` | Exact path dispatch in `backend/mvp_server.py` to `handle_market_breadth_api` | Requested by `backend/market_breadth_template.html`; invalid ranges fail closed before loader use | `market_breadth_response` selects a prebuilt range from the validated immutable artifact; failures return `DATA_BLOCKED`/503; response preserves read-only envelope, provenance, quality, freshness, and active-ORD identity | `backend/test_market_breadth_artifact.py`, `backend/test_market_breadth_publisher.py`, `backend/test_mvp_server_transport.py`, `backend/test_artifact_pointer_inventory.py` |

### Static imports and dynamic loads

The dispatch module statically imports `trend_map`, `trend_route_api`, and
`market_breadth_artifact`, plus compatibility `mvp_routes`. `trend_map.py`
dynamically imports the Trend Map read-model reader and intraday quote reader
when the published/read-model path is selected. `update_data.py` dynamically
imports the Trend Map publisher in the EOD completion path. These dynamic loads
are source reachability only; they do not prove an installed service or served
process reached them.

The Trend Map template uses the active static assets registered in
`mvp_server.py`: `styles.css`, `canonical-client.js`, and `shared-drawer.js`.
The Market Breadth template has its page logic inline. Asset existence and
browser loading were not probed here.

## Publisher, pointer, and target ledger

| Family/path | Classification | Checkout evidence | Disposition |
|---|---|---|---|
| `backend/trend_map.py`, `daily_trend_mapping.py`, `main_trend_mapping.py`, `technical_indicators.py`, `active_universe.py`, `daily_history.py` | SOURCE | Active Trend Map builder, classification, provenance, indicators, and universe dependencies are imported or called by the active handler/publisher chain. | KEEP |
| `backend/trend_map_read_model_publisher.py` | SOURCE / DATA-POINTER | Publishes an immutable version under `backend/trend-map-read-model/versions/`, atomically writes `current.json`, and validates identity/hash/schema before reads. | KEEP |
| `backend/trend-map-read-model/current.json` and referenced immutable target `shadow-trend-map-quote-envelope-v2-2026-09-18-...-f3783cb9724c81a5.json` | DATA/POINTER / artifact | Both exist. Pointer says `as_of=2026-09-18`, schema `daily-trend-map-shadow-read-model-v2`, and target has `PRODUCTION_READ_ONLY`; the target is protected below. | KEEP |
| `backend/intraday_quote_read_model.py`, `backend/trend-map-read-model/intraday-quotes/current.json`, referenced immutable quote target | SOURCE / DATA-POINTER / artifact | Pointer and target exist; target generated at `2026-09-15T09:45:43.425426+00:00`, and the inventory records freshness as stale as of 2026-09-20. Freshness remains REVISE. | KEEP |
| `backend/market_breadth.py`, `backend/market_breadth_publisher.py`, `backend/market_breadth_artifact.py` | SOURCE / publisher | Builder resolves active ORD observations; publisher feeds the immutable v2 artifact writer; API reads only prebuilt ranges. | KEEP |
| `backend/market-breadth-read-model/current.json` and `versions/market-breadth-c19d4ed5...020d2.json` | DATA/POINTER / artifact | Both exist. Read-only inspection found `as_of=2026-09-18`, `status=PRODUCTION_READ_ONLY`, schema `signalix.market-breadth.schema.v2`; hash/path identity is encoded in the pointer and the target is protected below. | KEEP |
| `backend/artifact_pointer_inventory.py` and `backend/test_artifact_pointer_inventory.py` | SOURCE / focused validation | Read-only inventory checks pointer containment, target identity, schema, hash, and validation for Trend Map, intraday, Market Breadth, and chart roots. | KEEP |
| `backend/read-model/` (ignored/generated chart family), including chart `1D`, `60M`, `1W`, `1M` current pointers and targets | IGNORED/GENERATED artifact | `.gitignore` excludes the family. No chart files were present in this checkout. The pointer inventory records prior `VERIFIED` chart targets, but this checkout cannot re-read them. Do not delete, move, regenerate, or infer current reachability. | OWNER-DECISION |

No current pointer or validated target is a cleanup candidate. The older
immutable candidates described in the pointer inventory are historical cleanup
evidence, not a new deletion instruction for this ticket.

## Tests and documentation

| Family/path | Classification and evidence | Disposition |
|---|---|---|
| `backend/test_trend_map.py`, `test_trend_map_read_model_publisher.py`, `test_intraday_quote_read_model.py`, `test_mvp_server_transport.py` | Focused Trend Map route, envelope, UI markers, publisher, sidecar, and transport contracts. | KEEP |
| `backend/test_market_breadth.py`, `test_market_breadth_artifact.py`, `test_market_breadth_publisher.py`, `test_market_breadth_frontend_contract.py` | Focused breadth builder, immutable artifact, publisher, API, frontend, quality, freshness, and no-actionability contracts. | KEEP |
| `backend/test_active_chart_adapter.py`, `test_chart_read_model.py`, `test_provenance_contract.py`, `test_source_freshness.py`, `test_active_universe.py`, `test_freshness_assessment.py` | Shared evidence, chart, provenance, universe, and freshness seams; some are supporting or historical-compatible tests rather than direct four-route tests. Any later consolidation needs evidence. | KEEP |
| `docs/current/2026-09-20-active-only-contract-freeze.md` | Current contract authority; explicitly says runtime/browser/pointer read-back gates remain unresolved where not freshly checked. | KEEP |
| `docs/current/2026-09-20-pointer-artifact-inventory.md` | Current pointer/artifact evidence note; useful for identity and rollback context, but dated and not fresh served evidence. | KEEP |
| `docs/current/2026-09-20-active-cleanup-review.md` | Current cleanup review; source/release closeout only, with runtime/API/browser/deployment still separate. | KEEP |
| `vault/Product-Strategy-Market-to-Action.md`, `vault/Execution-Pipeline.md`, `vault/Architecture.md`, `vault/Components.md`, `vault/Deployment.md`, `vault/Documentation-Governance.md`, `vault/INDEX.md` | Current authority and routing documents read for scope, acceptance, component, deployment, and document status. | KEEP |
| Removed archive paths, old superpowers specs/plans, and setup/actionable-signal source families | HISTORICAL / DEFERRED references. Removed documents remain recoverable from Git history and are not active route evidence. | OWNER-DECISION |

## Compose, service, timer, and operational references

| Family/path | Evidence and classification | Disposition |
|---|---|---|
| `docker-compose.yml` `dashboard` service | Runs `python -u mvp_server.py`, exposes port `3001`, bind-mounts `./backend`, and healthchecks `/trend-map`. This is configuration reachability, not a live service read-back. | KEEP |
| `backend/update_data.py` | EOD path publishes Trend Map after successful bounded update; chart EOD hooks publish `1D/1W/1M`; intraday hooks publish quote sidecar and `60M`. Source references do not prove timer installation; operational evidence remains REVISE. | KEEP |
| `backend/update_data.service`, `backend/update_data.timer` | Host EOD service/timer references the updater and a retired verification command in `ExecStartPost`; installation and current schedule were not inspected. Do not alter in this ticket. | OWNER-DECISION |
| `backend/signalix-intraday.service`, `backend/signalix-monitor.service`, and corresponding timer files | Operational intraday paths reference `update_data.py`, `marginable_long`, `60m`, and no-scan behavior; active-route publication dependency is source-visible, timer/service reachability is unavailable. No timer changes. | OWNER-DECISION |
| `scripts/probe_shortlist.sh` | Contains a Trend Map URL probe but also retired VCP/setup probes and writes an output directory. It was not run because it is not a four-route-only, no-side-effect proof; do not treat it as current acceptance. | OWNER-DECISION |
| delivery/alerts services and private signal/action families | Historical/deferred and outside the active envelope. Do not start or re-enable. | OWNER-DECISION |

## Protected targets and semantics

Protect all of the following from cleanup or contract drift:

- The four exact active routes and their dispatch/handler identity.
- `PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`, visible
  `DATA_BLOCKED`/fail-closed behavior, and the absence of orders, alerts,
  broker actions, or automatic BUY semantics.
- `backend/trend-map-read-model/current.json` and its referenced immutable
  Trend Map artifact, including artifact ID, path, content/measurement/policy/
  universe identity, schema, and as-of fields.
- `backend/market-breadth-read-model/current.json` and its referenced immutable
  Market Breadth artifact, including content hash, active-ORD denominator,
  provenance, freshness, quality, prebuilt range identities, and SET-as-context
  boundary.
- The intraday quote current pointer/immutable target as a Trend Map display
  sidecar, while keeping its stale freshness explicit.
- Active Thai ORD and the published `marginable_long` scope, explicit missing /
  stale / invalid / blocked states, provenance, no-lookahead, and fail-closed
  semantics. Counts in dated documents are not fresh runtime proof.
- Chart drawer support only as shared read-only evidence review (`1D`, `60M`,
  `1W`, `1M`); absent ignored files require owner/runtime evidence before any
  cleanup decision.
- Git history, an approved tag/branch, or a new owner-approved external archive
  as the historical recovery boundary. No archive is created by this ledger.

## Contradictions, residuals, and disposition summary

| Residual | Status |
|---|---|
| Current checkout has no ignored `backend/read-model/charts/*`, while the dated pointer inventory records chart current pointers/targets as validated | **REVISE / OWNER-DECISION**; do not infer absence is safe cleanup or that prior validation is current |
| Trend Map and intraday pointers use `artifact_path`; Market Breadth uses `path`; this is an implementation distinction, not a license to normalize fields | **KEEP**; preserve exact identities |
| Trend Map/intraday/Market Breadth artifacts are dated 2026-09-18 or earlier; intraday freshness is explicitly stale | **REVISE** for freshness/runtime acceptance |
| Source and focused test references are present, but service installation, container state, public ingress, database state, timer state, and browser behavior were not probed | **NOT VERIFIED / OWNER-DECISION** |
| Historical active-looking names such as `shadow` remain in immutable artifact IDs and publisher compatibility code | **KEEP** for identity/audit; any rename or consolidation is OWNER-DECISION |

| Family | KEEP | CONSOLIDATE | DELETE | MOVE-OUT | OWNER-DECISION |
|---|---:|---:|---:|---:|---:|
| Active route source, handlers, templates, assets | ✓ |  |  |  |  |
| Current pointers and validated immutable targets | ✓ |  |  |  |  |
| Focused tests and evidence seams | ✓ |  |  |  |  |
| Ignored/generated chart artifacts absent from checkout |  |  |  |  | ✓ |
| Compose/services/timers/operational scripts | ✓ |  |  |  | ✓ |
| Current authority and evidence notes | ✓ |  |  |  |  |
| Historical/deferred setup and action families |  |  |  |  | ✓ |

`CONSOLIDATE`, `DELETE`, and `MOVE-OUT` are intentionally unused as
authorized actions here. No deletion or move is approved by this ledger; any
future use of those dispositions requires a separate owner-approved bounded
ticket and reference scan.

## Read-only commands and results

Commands used in this slice included:

```text
git status --short --branch
→ ## codex/t72-active-reachability-ledger (clean before this file)

git rev-parse HEAD && git log -1 --format='%H %cI %s'
→ ea323ee543e753ad1ccdb27b3a21a4db5e3ebaee; 2026-09-20T20:25:47+07:00; docs: finalize stable cleanup closeout

rg --files docs/current vault; rg -n ... active route/publisher/pointer/service references
→ current authority notes, source, tests, Compose, services, timers, and scripts identified; no secrets read

sed/read-only inspection of the active freeze, pointer inventory, cleanup review,
Product Strategy, Execution Pipeline, Architecture, Components, Deployment,
Documentation Governance, mvp_server.py, route/artifact modules, templates,
tests, Compose, services, and timers
→ source/document evidence recorded above; no runtime operation

git check-ignore -v ... && git ls-files ...
→ active Trend Map and Market Breadth pointers/targets tracked; chart read-model family ignored by .gitignore; chart files absent in checkout

python - <<'PY' ... read current.json, resolve referenced target, print status/as_of/schema ... PY
→ Trend Map target exists and is PRODUCTION_READ_ONLY; intraday target exists with generated_at 2026-09-15; Market Breadth target exists and is PRODUCTION_READ_ONLY; chart family unavailable
```

No database writes, server starts, HTTP requests, public probes, browser
automation, Compose commands, systemctl/timer commands, artifact generation,
pointer writes, deletion, move, cleanup, commit, push, deploy, restart, or
migration was performed.

## Handoff boundary

This ledger hands later tickets #73–#77 a checkout-pinned source and reference
map only. It does not create implementation/deletion tickets and does not
select a cleanup target. Before any later disposition changes, Lite must obtain
fresh runtime/API, pointer/freshness, browser/UI, deployment/timer, and
rollback evidence, resolve the missing-chart contradiction, preserve the
protected list above, and re-run a complete old-reference scan. The final
acceptance status for this ledger is **NOT VERIFIED** for runtime/API and
browser/UI, with **REVISE** required for current chart/data-pointer evidence.
