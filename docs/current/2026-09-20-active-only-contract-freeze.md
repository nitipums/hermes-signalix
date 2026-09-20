# Active-only contract freeze — Issue #60

> **STATUS: CURRENT CONTRACT NOTE** · Documentation-only freeze; no runtime,
> source, artifact, timer, database, provider, delete, move, or deployment
> action is authorized by this note. Runtime/reachability statements below are
> contract boundaries, not fresh acceptance evidence.
> **As of:** 2026-09-20 ICT

## Active product spine

The active product is Daily Trend Mapping plus Market Breadth. The public
surfaces are deterministic, read-only, and non-actionable:

| Surface | Route | Contract |
|---|---|---|
| Daily Trend Map | `/trend-map` | Public read-only Daily evidence; `status=PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE` |
| Daily Trend Map API | `/api/trend-map` | Same envelope and safety boundary; fail closed for invalid or unavailable read-model state |
| Market Breadth | `/market-breadth` | Public read-only aggregate evidence; no setup, signal, alert, order, broker, or auto-trading semantics |
| Market Breadth API | `/api/market-breadth` | Deterministic validated breadth artifact contract; same non-actionable boundary |

`/mvp`, `/api/setup-candidates`, Team Facts, private signal/shadow services,
alerts, broker execution, and auto-trading are not active product targets.
Their history may be consulted for audit only and must not be promoted by this
ticket.

## Protected targets and artifact boundary

The following names are protected current targets for the active spine:

- `backend/trend-map-read-model/current.json` and its referenced immutable,
  validated Trend Map artifact;
- `backend/market-breadth-read-model/current.json` and its referenced
  immutable, validated Market Breadth artifact;
- the four active public routes listed above and their deterministic response
  envelopes.

Normal serving reads and validates only the current pointer plus its referenced
artifact. Generated artifacts are runtime inputs, not documentation authority,
and there is no current-plus-N retention contract. Do not add generated
artifacts or alter pointer/artifact identity in this ticket.

## Active universe semantics

- The active base is active Thai ORD. The current documented symbol-master
  count is 929 active ORD; missing, stale, invalid, or incomplete observations
  remain explicit blocked/quality states rather than being silently removed.
- Trend Map's published operational scope is `marginable_long`:
  active Thai ORD ∩ owner-supplied marginable list ∩ `can_buy=true`, currently
  documented as 237 eligible and 692 excluded. `can_buy` is universe
  membership, not a trading recommendation.
- Market Breadth uses the active-ORD denominator and reports observed/blocked
  coverage explicitly. SET is context only and does not change that denominator.
- No silent universe expansion, fallback to a retired universe, or reuse of
  historical counts is permitted. `active_ord` remains an explicit audit /
  rollback scope, not a substitute for the canonical product scope.

## Lean defaults

These are cleanup defaults, not runtime claims:

| Area | Frozen default |
|---|---|
| Team Facts | Historical/audit only; no active route, refresh, or reachability assumption |
| Chart drawer | Retain only as shared read-only evidence review reached from Trend Map; deterministic `1D`, `60M`, `1W`, and `1M` contract; no action semantics |
| Private services | OFF / out of active scope; do not start, re-enable, or infer reachability |
| Timers | No timer is part of this freeze; do not change or infer installed/scheduled ownership |
| Generated artifacts | Keep only the serving current pointer plus validated referenced artifact as the runtime model; no new retention/archive scheme |
| Historical recovery | Use Git history, an approved tag/branch, or an owner-approved external archive |

The active-only repository contract does not create or route work through an
`archive/`, `legacy/`, or `compatibility/` directory. This ticket authorizes
no deletion or movement of existing history; any future cleanup needs its own
owner-approved bounded decision and reference scan.

## Protected-authority residual

`AGENTS.md` and `vault/Product-Strategy-Market-to-Action.md` retain
incompatible legacy/current identity wording under owner-protected authority.
This is an explicit **OWNER-DECISION / NOT VERIFIED** residual: this freeze is
the canonical active-only boundary, but those two protected documents are not
rewritten by this reconciliation.

## Explicitly unresolved

The following remain `OWNER-DECISION / NOT VERIFIED` in this documentation-only
freeze: live public reachability of each route, current pointer/artifact
read-back, automated publisher/timer reachability, chart-drawer browser
acceptance, Team Facts reachability, private-service reachability, and any
historical recovery drill. No runtime, database, timer, provider, browser, or
deployment operation was performed to resolve them.

This note does not claim runtime, data, freshness, or browser acceptance.
