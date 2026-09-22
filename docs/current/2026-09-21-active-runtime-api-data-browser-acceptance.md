# Active runtime/API/data/browser acceptance — Issue #77

> **STATUS: CURRENT ACCEPTANCE WITH DATA RESIDUALS** · Fresh read-only acceptance evidence for
> specification Issue #71, following evidence through commit `426dd6f`.
> This record authorizes no cleanup, artifact generation, pointer change,
> deployment, restart, timer change, database action, or GitHub change.

## Scope and review time

Public ingress was probed first:

```text
Base URL: http://91.98.72.120:3001
Review timestamp: 2026-09-21T08:01:00+07:00 (ICT)
Checkout: /tmp/signalix-t77
Branch: codex/t77-runtime-browser-acceptance
HEAD: 426dd6fe443cd9603b02faf7541afd98c851717b
```

The active contract is Daily Trend Mapping and Market Breadth only. The
required safety envelope is `status=PRODUCTION_READ_ONLY`,
`research_only=false`, and `actionability=NONE`; active Thai ORD and
`marginable_long` membership, provenance, freshness, no-lookahead, partial
coverage, and fail-closed behavior remain protected.

## Public HTTP acceptance

Command run first against the public URL:

```bash
date --iso-8601=seconds
for path in /trend-map /api/trend-map /market-breadth /api/market-breadth \
  /mvp /api/setup-candidates; do
  curl -sS --connect-timeout 5 --max-time 20 -D - \
    -o /tmp/sx_accept_body "http://91.98.72.120:3001$path"
done
```

Lite re-read at `2026-09-21T08:01:00+07:00` returned HTTP 200 for all four
active routes. The retired routes returned HTTP 410. This supersedes the
earlier transient connection-refused observation in the Codex draft; the
transient failure remains preserved in the transcript, not used as the final
runtime verdict.

| Public route | HTTP result | Acceptance result |
|---|---|---|
| `/trend-map` | HTTP 200; public page rendered | **PASS** |
| `/api/trend-map` | HTTP 200; `PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`, `VERIFIED`, `237` rows | **PASS** |
| `/market-breadth` | HTTP 200; public page rendered with `PARTIAL` coverage | **PASS with DATA REVISE** |
| `/api/market-breadth` | HTTP 200; `PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`, `PARTIAL`, `929 declared / 841 observed / 88 blocked` | **PASS with DATA REVISE** |
| `/mvp` (retired) | HTTP 410 | **PASS** for retired behavior |
| `/api/setup-candidates` (retired) | HTTP 410 | **PASS** for retired behavior |

Lite API contract read-back:

```text
/api/trend-map: as_of=2026-09-18, freshness=FRESH, verification_status=VERIFIED, rows=237
/api/market-breadth: as_of=2026-09-18, freshness=AVAILABLE, quality=PARTIAL,
                    929 declared / 841 observed / 88 blocked
```

## Checkout-only source and artifact evidence

This section is explicitly not served-runtime evidence.

| Item | Read-only checkout result | Boundary |
|---|---|---|
| Source/release identity | HEAD `426dd6fe443cd9603b02faf7541afd98c851717b`; recent history includes #76 `426dd6f`, #75 `6479c3a`, #74 `bc4d579`, #73 `cb05501`, and #72 `54919d3` | **VERIFIED** for this checkout only |
| Trend Map pointer | `backend/trend-map-read-model/current.json` points to `shadow-trend-map-quote-envelope-v2-2026-09-18-87dce5718dd0784a-e76ebcbf1637fac9-f34bcb3ad1244662-f3783cb9724c81a5`; pointer/target identity, schema, and content validation returned `VERIFIED` | Source/runtime-input only; not public read-back |
| Trend Map artifact | `status=PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`, `as_of=2026-09-18`, 237 rows; universe base 929 active ORD, scope `marginable_long`, eligible 237, excluded 692; provenance says `SELECT_ONLY`, `price_data+derived_daily_price_data`, timeframe `1D`, point-in-time filter `date <= as_of` | **REVISE / do not promote freshness**; inventory reports freshness `NOT_VERIFIED` |
| Market Breadth pointer | `backend/market-breadth-read-model/current.json` points to `market-breadth-c19d4ed5a7db3e522ea3f5e0ff4f151643895bdcb47eaf4d9d4de8dcdcf020d2.json`; pointer/target identity, schema, and content validation returned `VERIFIED` | Source/runtime-input only; not public read-back |
| Market Breadth artifact | `status=PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`, `as_of=2026-09-18`, active ORD count 929, observed 841, blocked 88, `quality=PARTIAL`, freshness field `AVAILABLE`; provenance is `SELECT_ONLY` with official/derived source and explicit lineage | **REVISE / do not treat as fresh served evidence**; partial coverage must remain visible |
| Intraday sidecar | Pointer/target integrity `VERIFIED`; freshness `STALE` in the read-only inventory | **REVISE**; stale data is not promoted |
| Chart read models | `backend/read-model/charts/current-1D.json`, `current-60M.json`, `current-1W.json`, and `current-1M.json` are absent in this checkout | **NOT VERIFIED**; prior dated evidence does not substitute for current runtime evidence |

Read-only pointer validation command:

```bash
PYTHONPATH=backend python -c \
  'from artifact_pointer_inventory import inventory_active_read_models; \
   print(inventory_active_read_models())'
```

Result: Trend Map and Market Breadth pointer status `VERIFIED`; Trend Map and
Market Breadth freshness `NOT_VERIFIED`; intraday status `VERIFIED` with
freshness `STALE`; chart pointers `NOT_VERIFIED` with
`current_pointer_missing_blocked`.

## Runtime/container/readiness

Safe read-only checks were attempted at `2026-09-21T07:44+07:00` ICT:

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
```

Lite read-only recheck returned:

```text
signalix_dashboard  Up 14 hours (healthy)  0.0.0.0:3001->3001/tcp
signalix_backend    Up 14 hours (healthy)  127.0.0.1:8000->8000/tcp
signalix_postgres  Up 2 weeks (healthy)
signalix_redis     Up 2 weeks (healthy)
GET http://127.0.0.1:8000/health/readiness → HTTP 200
```

No service was started, restarted, inspected through Compose, or otherwise
changed. Runtime/container/readiness: **PASS** for observed read-only state.

## Browser acceptance

Lite Browser Use rechecked the public route with a 500px viewport and with
CDP device metrics overridden to 390px:

```bash
browser_exec → public http://91.98.72.120:3001/trend-map and /market-breadth
desktop-ish 500px: both pages rendered; scrollWidth=485, clientWidth=485
390px: both pages rendered; scrollWidth=390, clientWidth=390,
        bodyScrollWidth=390
```

Visible public copy included Trend Map `Data date 2026-09-18`, `Showing 237 of
237`, and Market Breadth `841 observed · 88 blocked · 929 declared`,
`QUALITY PARTIAL`. Browser layout/navigation smoke: **PASS**. A complete
drawer interaction and failure/retry journey were not exercised in this
acceptance, so those subpaths remain **NOT VERIFIED**.

## Deployment and rollback boundary

No deployment, restart, Compose action, timer action, database action, artifact
generation, pointer write, or production-data change was performed. Served
state cannot be inferred from this checkout. Rollback remains the protected
Git/source and immutable-artifact history boundary; a source-plus-artifact
rollback drill was not performed. Deployment and rollback: **NOT VERIFIED**.

## Verdict and handoff

| Gate | Result |
|---|---|
| Source/release identity | **PASS** — checkout identity only |
| Public active API/page reachability | **PASS** — all four active routes HTTP 200 |
| Retired route behavior | **PASS** — `/mvp` and `/api/setup-candidates` HTTP 410 |
| Runtime/container/readiness | **PASS** — healthy containers and readiness HTTP 200 |
| Data freshness/provenance/pointer identity | **REVISE** — Trend Map is FRESH as of 2026-09-18, intraday sidecar is stale, Market Breadth is PARTIAL, and chart pointer availability remains unresolved |
| Desktop/390px browser | **PASS** for page/layout smoke; drawer/failure journey **NOT VERIFIED** |
| Deployment/rollback | **NOT VERIFIED** — no deployment or rollback drill authorized/performed |

Overall Issue #77 acceptance: **PASS for runtime/API/container/browser layout
sub-gates; REVISE for data/chart freshness residuals**. The stale/partial
evidence is preserved as such and does not promote data or actionability.
There is no evidence of orders, alerts, broker actions, automatic BUY, or any
other actionability; the active contract remains fail-closed and read-only.

Handoff to Issue #78: retry public API/page and retired-route checks from a
runtime with ingress reachability, then obtain desktop and 390px browser
evidence including active navigation/chart and failure-state behavior. Re-read
served pointer/artifact identity and freshness at the same acceptance time;
keep `marginable_long`, active-ORD denominator, no-lookahead, partial/blocked,
and `actionability=NONE` semantics explicit. Lite must review and commit; this
worktree has no commit from this task.

## Exact no-side-effect verification

```bash
git status --short --branch
```

Result before documentation edit: clean branch
`codex/t77-runtime-browser-acceptance`; no pre-existing changes were present.
Only this Markdown file is in scope. No source, test, authority document,
artifact, pointer, timer, database, service, deployment, or GitHub file was
changed.
