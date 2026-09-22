# Compose and timer service ownership — Issue #75

> **STATUS: CURRENT DECISION RECORD** · Spec: Issue #71. Prior evidence:
> Issues #72–#74, with the immediately prior publisher record at commit
> `bc4d579b91130bf2990739c25e8763ebeab13fdd`. Evidence timestamp:
> `2026-09-21T07:35:26+07:00` ICT. Checkout:
> `/tmp/signalix-t75`, branch `codex/t75-ops-ownership`.
>
> This is a source-ownership classification only. It authorizes no timer,
> service, Compose, deployment, database, artifact, pointer, deletion,
> movement, cleanup, alert, private-signal, or GitHub action. Installed,
> enabled, running, served, and current runtime state are **NOT VERIFIED**
> unless explicitly identified as read-only evidence below.

## Decision boundary

The active product remains deterministic, read-only Daily Trend Mapping and
Market Breadth:

| Active route | Protected contract |
|---|---|
| `/trend-map` and `/api/trend-map` | `status=PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE` |
| `/market-breadth` and `/api/market-breadth` | deterministic validated read-only breadth evidence; no setup, signal, alert, order, broker, or auto-trading semantics |

The repository-defined ownership split is:

1. Compose owns the long-running serving/dependency boundary: PostgreSQL,
   Redis, backend API, and dashboard. The dashboard/backend bind mount exposes
   the checkout's source and protected read-model pointers/artifacts to the
   serving processes.
2. Host systemd units are the source-defined owner for scheduled ingestion and
   read-model publication. Compose has no timer declaration and must not be
   treated as a second publisher merely because it mounts `./backend`.
3. A timer or service declaration is source intent, not evidence that the unit
   is installed, enabled, scheduled, running, or currently writing.
4. A publisher may write only its defined immutable artifact and current
   pointer through its validated, atomic, fail-closed seam. This record does
   not authorize a write or choose a retention policy.

## Allowed disposition vocabulary

The only dispositions in this record are **KEEP**, **CONSOLIDATE**,
**DELETE**, **MOVE-OUT**, and **OWNER-DECISION**. A disposition is not an
execution permission. No protected active pointer or referenced immutable
artifact receives `DELETE`, `MOVE-OUT`, or `CONSOLIDATE` here.

## SOURCE — source-defined intended ownership

| Source family | Repository evidence | Disposition | Boundary / contradiction |
|---|---|---|---|
| Compose `postgres`, `redis`, `backend`, `dashboard` | `docker-compose.yml`; dependency healthchecks, host-only backend port, dashboard port `3001`, and `./backend:/app` bind mounts | **KEEP** | Serving/dependency owner only. No publisher timer is declared. Compose/container running state is **NOT VERIFIED**. |
| Compose delivery/alerts | Removed in cleanup Wave B; Git history is rollback authority | **DELETE** | No active or retained compatibility caller required the disabled profile or consumer. Runtime removal/read-back remains **NOT VERIFIED** until Lite deploys. |
| EOD publisher path | `backend/update_data.service` → `update_data.py --source settrade --scan`; #74 records Trend Map, chart `1D/1W/1M`, and related read-model hooks at the EOD boundary | **KEEP** | Source-defined scheduled publisher owner for active artifacts, subject to the unresolved `ExecStartPost=.../verify_mvp_only.py` contradiction below. |
| Intraday publisher path | `backend/signalix-intraday.service` → `update_data.py --intraday-only ... --intraday-universe marginable_long --intraday-interval 60m --no-scan`; `signalix-intraday.timer` | **KEEP** | Source-defined owner for the active display-only 60M/intraday publication path. `ExecStopPost` is a separate evaluation family and is not active-route ownership. |
| Intraday watchdog | `signalix-intraday-watchdog.timer` → `intraday_healthcheck.py`, with a Bangkok session guard | **KEEP** | Observability/freshness owner only; it must not publish signals or change actionability. Installed/current state is **NOT VERIFIED**. |
| EOD healthcheck | `signalix-eod-healthcheck.timer` → `eod_healthcheck.py` | **OWNER-DECISION** | Source description says freshness and scan watchdog; active read-only ownership is not established from the unit alone. Resolve its scope separately before enabling or changing it. |
| Monitor/tier3 refresh | `signalix-monitor.timer` → `signalix-monitor.service` → `update_data.py --intraday-mode tier3 ... --no-scan` | **OWNER-DECISION** | Overlaps the active intraday timer's source/update path and carries historical shortlist terminology. It is not an active route publisher by inference. |
| `update_data.service` `ExecStartPost` | `verify_mvp_only.py` | **OWNER-DECISION** | Direct contradiction with the active-only freeze retiring `/mvp` and `/api/setup-candidates`; do not run, remove, or replace it in #75. |
| Intraday `ExecStopPost` | `python -m backend.run_intraday_evaluation --mode active --interval 60m` | **OWNER-DECISION** | Evaluation is not publication and may belong to deferred setup/evaluation history. Do not infer that “active” means active product. |
| Settrade master and SET index sync | `signalix-settrade-master.timer/service`, `signalix-set-index.timer/service` | **KEEP** | Upstream universe/context maintenance is source-defined support for deterministic evidence. Current installation and data freshness are **NOT VERIFIED**. |
| Profile/factsheet refresh | `signalix-profile-refresh.*`, `signalix-factsheet-refresh.*` | **OWNER-DECISION** | Auxiliary metadata jobs are not required by the four-route ownership evidence in this record; do not promote them or delete their history. |

No source-defined timer is assigned to Compose. No source-defined delivery,
alert, private-signal, broker, or auto-trading family is active. Historical
files remain evidence and are not cleanup candidates under this issue.

## RUNTIME/API — explicitly separate from SOURCE

**NOT VERIFIED.** No `docker compose`, `systemctl`, `journalctl`, HTTP,
database, service restart, timer installation, deployment, or browser command
was run. The following are therefore unknown:

- which Compose project, profiles, containers, bind mounts, healthchecks, or
  image/source checkout are currently running;
- whether any systemd unit is installed, enabled, scheduled, failed, or
  currently executing;
- whether more than one publisher is currently writing, or whether a publisher
  is absent;
- whether `/trend-map`, `/api/trend-map`, `/market-breadth`, or
  `/api/market-breadth` is currently served with the protected envelope.

The repository contains historical runtime logs and prior deployment notes,
but those do not establish current installed state at this checkout/time and
are not substituted for a fresh runtime check.

## DATA/POINTER — protected and separate

Keep the active pointer/artifact boundary unchanged:

- `backend/trend-map-read-model/current.json` and its referenced immutable
  validated artifact;
- `backend/market-breadth-read-model/current.json` and its referenced immutable
  validated artifact;
- the intraday quote sidecar and chart pointers/artifacts when present and
  validated by their family-specific seams.

Publisher ownership must preserve pointer containment, artifact identity,
content/measurement hashes, provenance, freshness fields, no-lookahead
boundaries, prior-pointer preservation on failure, and fail-closed invalid or
stale behavior. There is no current-plus-N retention contract here. No pointer
or artifact is selected for `DELETE`, `MOVE-OUT`, or `CONSOLIDATE`.

The #74 checkout evidence recorded Trend Map, intraday, and Market Breadth
integrity separately from freshness and identified missing chart artifacts in
that checkout as **NOT VERIFIED / OWNER-DECISION**. This note neither
regenerates nor reclassifies those files.

## BROWSER/UI — separate

**NOT VERIFIED.** No desktop, 390px mobile, chart-drawer, empty, error, or
data-blocked browser evidence was collected. Source ownership does not prove
that either active page is reachable, readable, or using the intended pointer.

## Protected operational families

The following are protected from promotion by inference and from cleanup by
this issue:

- active read-only route serving and its backend/dashboard dependency chain;
- Trend Map, Market Breadth, intraday display-only, and chart read-model
  provenance/freshness/fail-closed semantics;
- active Thai ORD / `marginable_long` universe identities and explicit blocked
  coverage;
- historical setup/API, Team Facts, Elliott/Wave/VCP, private signal/shadow,
  alert, broker, delivery, and auto-trading evidence as audit/deferred
  families. They remain outside the active line and are not silently deleted
  or moved.

## Contradictions requiring bounded follow-up

1. Compose bind-mounts the same `backend` tree that host systemd publishers
   read and write, but source does not enforce a single host checkout, a
   writer lock, or an installed-service-to-checkout mapping. This is a
   source-level collision risk, not proof of duplicate runtime writers.
2. The EOD unit's `ExecStartPost=verify_mvp_only.py` names a retired route while
   its `ExecStart` is the apparent owner of active EOD publication.
3. The intraday service publishes display data but its `ExecStopPost` runs a
   separate evaluation module; the word `active` in that command does not
   override the active-only product freeze.
4. The tier3 monitor and intraday timer both invoke `update_data.py` with
   different modes. The source does not prove whether both are installed or
   whether their outputs are compatible with the active artifact contract.
5. Resolved by cleanup Wave B: the Compose alerts profile and delivery consumer
   are absent from source. Runtime removal remains **NOT VERIFIED**.

## Exact read-only evidence commands

Commands used from `/tmp/signalix-t75`; no command below changes runtime state:

```text
git status --short --branch
git rev-parse HEAD
date --iso-8601=seconds
rg --files | rg '(docker-compose|compose|\.service$|\.timer$|update_data|publisher|alert|signal|delivery|legacy)'
sed -n '1,280p' docker-compose.yml
sed -n '1,220p' backend/update_data.service
sed -n '1,180p' backend/update_data.timer
sed -n '1,240p' backend/signalix-intraday.service
sed -n '1,180p' backend/signalix-intraday.timer
sed -n '1,180p' backend/signalix-intraday-watchdog.service
sed -n '1,180p' backend/signalix-intraday-watchdog.timer
for f in backend/*.service backend/*.timer backend/*.service.d/*.conf; do
  rg -n '^(Description|After|Requires|ExecCondition|ExecStart|ExecStartPost|ExecStopPost|OnCalendar|Unit=|WantedBy|Environment(File)?|WorkingDirectory|Type=)' "$f"
done
rg -n -C 3 'def (run|publish|main)|intraday-only|no-scan|publish_(trend|market|chart|intraday)|read_model|signals|setup' backend/update_data.py backend/active_transport.py backend/*publisher.py
```

Results: checkout was clean before this file, `HEAD` was
`bc4d579b91130bf2990739c25e8763ebeab13fdd`, and the source declarations
listed above were present. No installed-state command was used; installed
state remains **NOT VERIFIED**.

## Handoff

- **#76 — runtime and artifact evidence:** perform only separately authorized,
  read-only checks of Compose project/container/profile state, systemd unit
  installation/enabled state, served APIs, pointer/artifact availability,
  freshness, provenance, and actual publisher/timer reachability. Do not
  restart, install, enable, disable, publish, or clean up as part of evidence.
- **#77 — browser/UI evidence:** verify the four active route journeys at
  desktop and 390px mobile, including chart drawer and failure/blocked paths;
  keep browser verdict separate from source, runtime, and pointer integrity.
- **#78 — bounded implementation/cleanup decision:** only after owner review
  of #75–#77 should any source/unit/Compose contract change be proposed. A
  later issue must name exact files and disposition; no `CONSOLIDATE`,
  `DELETE`, or `MOVE-OUT` is authorized here.

## Self-check

The intended self-check is limited to this new Markdown file and repository
metadata: `git diff --name-status`, `git diff --check`, and a whitespace scan.
No commit is created; Lite reviews and commits this documentation slice.
