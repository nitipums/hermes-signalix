# Deployment

> **STATUS: CURRENT** · `CANONICAL_FOR: deployment/runbook/timer ownership`.
> **Reconciled:** 2026-09-13 · current production is `release/signalix-mvp-stable`; Trend Map production-served read-only closeout is complete; evaluator auto-caller remains separate.

## Stable release

```text
branch: release/signalix-mvp-stable
source: /root/signalix
MVP server: mvp_server.py
legacy routes: quarantined/404
```

## Current delivery focus — 2026-09-12

The primary workstream is the production-served, public, read-only Daily Trend Mapping surface. Its active bounded promotion/closeout contract is GitHub Issue [#17 — Daily Trend Map: public read-only delivery closeout](https://github.com/nitipums/hermes-signalix/issues/17):

### Fresh promotion read-back — 2026-09-13

- Source: implementation commit `db481af` and artifact commit `159655d` are included in the release branch; local/remote branch equality was verified at final closeout and the working tree was clean.
- Reload: `docker compose up -d --force-recreate backend dashboard`; PostgreSQL and Redis were left running, with no migration or schema change.
- Readiness: `GET http://127.0.0.1:8000/health/readiness` returned `{"status":"ok","db":"up","redis":"up"}`.
- Publication: bounded publisher created a new immutable artifact with `as_of=2026-09-11`, `237/237` declared/evaluated/returned, and publication time `2026-09-13T03:57:47.890717+00:00`.
- Local/public API: `PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`, `verification_status=VERIFIED`, freshness `FRESH`; quality `229 AVAILABLE / 5 INVALID_DATA / 3 NO_DATA`; public ingress HTTP 200.
- Browser: desktop 237 rows and drawer/chart passed; 390px mobile `scrollWidth=390`, failure showed Retry/zero rows, recovery returned 237 rows. Hermes `browser_exec` was also repaired by restoring the managed Python Browser Use CLI path; helper syntax was verified against the live route.
- Rollback: `PASS`; isolated source-plus-artifact pairing read back both the pre-promotion `6095346` + legacy artifact (`READ_ONLY_SHADOW`, `VERIFIED`, 237 rows) and the promoted source + artifact (`PRODUCTION_READ_ONLY`, `VERIFIED`, 237 rows). No production traffic was switched during the drill.

```text
/trend-map-shadow
/api/trend-map-shadow
```

This surface is production-served public read-only Daily evidence
(`status=PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`)
and is non-actionable. `/mvp` and
`/api/setup-candidates` remain retained trial/future-integration surfaces;
Elliott Wave work is deferred. Any future Trend Mapping to `BUY_NOW` path must
be separately approved and gated.

## Historical runtime scope — 2026-09-02

At that 2026-09-02 baseline, the promoted Elliott/Trend/Trade-Setup spine was the product surface. `signalix_backend`, `signalix_dashboard`, PostgreSQL, and Redis were healthy at rebaseline; `/mvp` returned 200, `/api/setup-candidates` returned the live DB-built contract, `/health/readiness` was on backend `:8000`, and retired `/dashboard.html` returned 404. The public 390px failure→Retry→recovery journey was verified. The UI showed `60m fetched` separately from `latest completed 60m candle`; session evidence was verified after runtime reload. Alerts, auto-trading, and broker execution remained off.

`marginable_long` is 237 eligible symbols; 931 active ORD is explicit audit/rollback coverage. VCP routes/artifacts remain compatibility/audit only.

### Current Team Facts policy and runtime — 2026-09-10

Owner decision: Team Facts is a public, unauthenticated, read-only facts feed. It does not expose setup, Wave, lane, trigger, risk, target, alert, order, or broker execution semantics. `/api/setup-candidates` remains the separate canonical setup surface.

Release `28f7947` removed only the dedicated Team Facts API-key guard; protected routes were not changed. After `docker compose up -d --force-recreate backend dashboard`, readiness returned `status=ok`, `db=up`, `redis=up`. Public `GET /api/team/setup-candidates` returned `team-facts-v1`, `marginable_long`, `base_active_ord_count=932`, `eligible_count=237`, `excluded_count=695`, and views `momentum=16`, `near_high=13`, `pullback=58`. Freshness was `partial` because `3BBIF`, `COM7`, and `PR9` lacked Daily baselines; intraday freshness was `fresh`. This is explicit data completeness, not a trading signal.

The implementation uses bounded read-only queries and preserves Daily/60m source separation. Rate limiting and HTTPS/TLS remain separate hardening items. Alerts, auto-trading, broker execution, and evaluator auto-caller remain OFF/PENDING.

The Daily Trend Map route is permanently production-served public read-only by
owner decision and requires no authentication. It has no setup,
recommendation, alert, order, broker, BUY, or other action semantics. This is
separate from `/mvp`, which remains governed by its owner-only/private signal
policy. No credential or secret is recorded here.

### Historical deployment evidence — 2026-09-12 (superseded; not current runtime)

The bounded publisher, artifact/failure-sidecar validation, EOD hook, and
fail-closed SQL guard were deployed and publicly read back. The public
`GET /api/trend-map-shadow` returned HTTP 200 with 237 rows: `229 AVAILABLE`,
`5 INVALID_DATA`, and `3 NO_DATA`; freshness was `FRESH`. Public `/mvp` also
returned HTTP 200. The verified pointer targeted artifact
- **Historical artifact identity (superseded; not current pointer):** `shadow-trend-map-quote-envelope-v2-2026-09-11-2851c3f13cbd8e39-e76ebcbf1637fac9-02bd1d0dee037566-0988111049785ae5` with content hash `02bd1d0dee037566` and measurement hash `0988111049785ae5`.

Generated `backend/shadow-read-model/` artifacts are intentionally tracked
runtime inputs in commit `f18e48f`, not untracked research artifacts.
Untracked `research/`, `docs/current/`, and `docs/agents/` remain preserved
owner/research artifacts outside that commit. The next scheduled EOD freshness
evidence remains ongoing; no post-commit EOD run is claimed here.

The shadow route remains permanently production-served public read-only Daily evidence. It has no setup, recommendation, alert, order, broker, BUY, or other action semantics; this does not change `/mvp`'s separate owner-only/private signal policy. The unused `map_daily_trend` compatibility alias remains preserved because removing it would require editing outside this bounded file scope; no caller or test currently uses it.

### 2026-09-02 promotion evidence

- Source/release: `/root/signalix`, branch `release/signalix-mvp-stable`, local and remote SHA `5bf3d9ac3e77b9f139ce2f84e0d6e27546a95fa4`.
- Promotion: installed `backend/signalix-intraday.service` and `.timer` into `/etc/systemd/system/`, ran `systemctl daemon-reload`, restarted the timer, and verified byte parity plus `systemd-analyze verify`.
- Runtime reload: `docker compose up -d --force-recreate backend dashboard`; `signalix_backend` and `signalix_dashboard` healthy; `/health/readiness` returned DB/Redis `ok`.
- Public read-back: `/mvp`, `/api/setup-candidates`, and `/api/chart-db/BBL?timeframe=1D|1W` returned HTTP 200. Day last candle was provisional `2026-09-02`; Week candles were ascending with `latest_time=2026-09-02T05:00:00+00:00`.
- Review boundary: code/tests/runtime/browser are PASS for this slice. Remaining `REVISE` follow-up: bound request-time intraday metadata overlay and persist explicit fetch-universe identity for audit runs.

### W3 publication-gate milestone — 2026-09-03

Stable local commit `807cdde` promoted the Codex-implemented W3 publication gate from candidate `717b7c7`. After `docker restart signalix_dashboard`, the canonical read model was republished as `read-model-7db1dfb3e7cf3f9e` with `count=237`. Loopback and public `/api/setup-candidates` returned HTTP 200 with `evaluated=237`; CRC and BGRIM were `NOT_VERIFIABLE` with `retracement_gate_exceeded`; AWC remained blocked by post-impulse correction. Public `/mvp` smoke at 390px showed `237 evaluated` and `scrollWidth=375` under `innerWidth=390`. The local branch is one commit ahead of origin; no push was performed.

The narrow canonical detector intentionally publishes only `EARLY_WAVE_3`, `WAVE_3_CONTINUATION`, and `NOT_VERIFIABLE`; Wave 1/2/4/5 visibility is the next bounded product/contract tuning decision, not a runtime data-loss claim.

### Main `/mvp` Daily phase grouping milestone — 2026-09-03

Stable commit `9669e2e` groups main-list cards by `wave.daily_structure.phase` inside each existing decision lane and makes the phase filter presentation-only across all lanes. Public `/mvp` browser verification passed with W1/W2/W4/W5 phase headings visible, primary/lane separation intact, and 390px no-overflow. No read-model republish was needed because the backend contract was unchanged; dashboard reload served the new frontend.

### Daily structure label separation fix — 2026-09-11 08:04 ICT

Owner-authorized local promotion `a78f7a0` (Codex slice commit `d4b8b30`) removes the competing user-facing `Primary Daily Structure` label contract. The card now keeps `Primary Daily Wave` separate from the exact visible `Daily structure · <phase>` label; non-actionable semantics remain in `aria-label` and `data-actionability="NONE"`. No Daily/60m calculation, decision lane, read-model, database, or ingestion behavior changed.

Evidence after `docker restart signalix_dashboard`:

- `signalix_dashboard`: healthy;
- local and public `/mvp`: HTTP 200, 17,327 bytes;
- local and public `app.js`: HTTP 200, 121,342 bytes; contains `Primary Daily Wave`, `Daily structure ·`, and `data-actionability="NONE"`; contains no `Primary Daily Structure`;
- local and public `/api/setup-candidates`: HTTP 200, 184,122 bytes, 50 returned items from 237 evaluated;
- real public 390px rendered journey via `agent-browser`: visible separate labels on IRPC/SSP cards, no old label, no obvious horizontal overflow; screenshot `/tmp/sx_mvp_390.png`;
- source and focused contract/API tests passed independently; broader browser/served acceptance outside this label slice remains governed by the existing dashboard gates.

### Daily Wave marker drawer promotion — 2026-09-11 08:43 ICT

Owner-authorized local promotion `1ed784b` (Codex Sol slice `ea9919d`) fixes the drawer merge path that replaced populated `/api/chart-db/{symbol}?timeframe=1D` marker evidence with an empty compact-item projection. The drawer now preserves exact API `timestamp`/`price` coordinates for Daily Wave markers, renders readable source-linked labels, and keeps Daily markers 1D-only. No Elliott calculation, marker coordinate, decision lane, setup/risk math, database, ingestion, or read-model behavior changed.

Evidence after `docker restart signalix_dashboard`:

- `signalix_dashboard`: `running healthy`;
- public `app.js`: HTTP 200, 124,346 bytes, includes the chart evidence selection/presentation helpers;
- public IRPC Daily chart API: HTTP 200, 574,821 bytes, 4 markers: W1 low, W1 high, W2 pullback low, W3 close confirmation;
- public 390px IRPC drawer: rendered Daily chart and legend `markers (4)`; screenshot `/tmp/sx_irpc_wavefix_390.png` inspected with no obvious clipping/overflow;
- switching drawer to 60m: legend `markers (Day only)` and source `intraday_price_data`; Daily Wave markers are not projected onto 60m;
- local focused frontend/chart/Wave tests: PASS; `node --check`: PASS; `git diff --check`: PASS; no console errors reported by the browser check.

### Deep-pullback W3 shadow evidence promotion — 2026-09-11 13:06 ICT

Owner-authorized promotion `3443621` adds the canonical source-generated `wave.deep_pullback_evidence` envelope for raw W3 candidates in the shadow band `0.60 < retracement <= 0.786` when the existing publication rejection is `retracement_gate_exceeded`. Release metadata revision `163a192` bumped the immutable read-model representation to `9`; no publication gate, primary state, lane, setup/risk math, chart marker, database schema, or ingestion behavior changed.

Evidence after `docker compose up -d --force-recreate backend dashboard` and canonical read-model republish:

- backend/dashboard: healthy;
- `READ_MODEL_PUBLISHED`, count `237`, source version `read-model-7a93ecdbd615fea7`;
- public `/api/setup-candidates`: HTTP 200, `237/237` evaluated/returned;
- public ERW read-back: `primary_state=NOT_VERIFIABLE`, `decision_lane=WAIT`; `deep_pullback_evidence.status=DEEP_PULLBACK_W3_EVIDENCE`, retracement `0.7538461538461539`, actionability `NONE`, Daily source, exact W1/W2 anchors;
- public 390px ERW drawer: visible `Primary Daily Wave · Wave · Not verified` plus separate `DEEP_PULLBACK_W3_EVIDENCE · 75.3846%` / `Non-actionable · Daily evidence`; exact anchors visible; `scrollWidth=390`, `clientWidth=390`; screenshot `/tmp/erw_deep_pullback_390.png`;
- focused backend/frontend tests, Python compile, JS syntax, and diff checks: PASS; one pre-existing unrelated mobile test excluded as documented by the Codex/Lite run.

### Primary-wave UI, server-side lane filtering, and responsive drawer closeout — 2026-09-11 18:25 ICT

Owner-authorized UI/API presentation changes were reloaded with `docker compose up -d --force-recreate backend dashboard`. The canonical setup-candidate contract remains unchanged; `decision_lane` is now applied server-side before pagination, while the `/mvp` surface keeps `Primary Daily Wave` as the visible Wave hierarchy and hides `Daily structure` presentation fields.

Evidence after reload:

- `signalix_backend`, `signalix_dashboard`, PostgreSQL, and Redis healthy; backend `/health` returned `status=ok`, `db=up`, `redis=up`.
- Public `/mvp`: HTTP 200; served `app.js` contains the in-place refresh marker and server-side lane request path; Daily structure control is absent.
- Public `/api/setup-candidates?universe=marginable_long&page=1&page_size=50&decision_lane=AVOID`: HTTP 200, `total_items=31`, `total_pages=1`, `returned_count=31`, every returned item `decision_lane=AVOID`, while `evaluated_count=237` remains explicit.
- Public desktop browser at `1440×1000`: drawer panel `960px` wide, centered at `left=240px`, body scroll is independent, body text `15px`, chart CSS/backing size `902×560`.
- Public mobile browser at `390×844`: drawer `390×743`, chart `366×360`, `scrollWidth=390`, `bodyScrollWidth=390`; no horizontal overflow.
- Focused frontend/ranking tests: PASS; `node --check backend/frontend/app.js`: PASS; `git diff --check`: PASS. No database migration or read-model republish was required.

The drawer is a review surface for machine-generated evidence only; it is not an automatic trading signal or order interface. Search remains a client-side filter and is intentionally a separate follow-up for server-side pagination semantics.

## Daily structural evidence integration milestone — 2026-09-03

Stable local commit `9ec9e20` adds `wave.daily_structure` as an additive non-actionable Daily evidence object projected from the existing full-wave result. After dashboard reload and republish, `read-model-fb71255aa17e8e3b` served `237` rows; every row contained `actionability=NONE`. Primary W3/NOT_VERIFIABLE distribution remained unchanged while Daily phase evidence exposed W1/W2/W4/W5. Public `/mvp` drawer and 390px containment were verified. W2 lane promotion and W4/W5 primary promotion remain deferred.

### Team Facts API production promotion — 2026-09-03 19:38 ICT

Owner-authorized promotion of the read-only Team Facts API was applied to the
canonical dashboard service. `TEAM_SCAN_API_KEY` was provisioned in
`/root/signalix/.env` without recording its value in documentation, and
`docker compose up -d --force-recreate dashboard` recreated the dependent
backend/dashboard services. Production services were healthy after recreate.

Public verification via `http://91.98.72.120:3001`:

- no/invalid `X-Signalix-Team-Key` → HTTP 401;
- authenticated `GET /api/team/setup-candidates` → HTTP 200, compact response
  66,666 bytes, views `momentum=11`, `near_high=6`, `pullback=44`;
- authenticated Daily history detail for `IRPC`, limit 5 → HTTP 200, 5
  `price_data` / `1D` candles;
- authenticated 60m history detail for `IRPC`, limit 5 → HTTP 200, 5
  completed `intraday_price_data` / `60m` candles;
- unknown symbol → HTTP 404; invalid timeframe/limit → HTTP 400;
- backend, dashboard, PostgreSQL, and Redis containers healthy;
- container confirmed `TEAM_SCAN_API_KEY` loaded.

Ploy production read-only challenge returned `REVISE`: facts-only contract,
auth, source/timeframe separation, thresholds, and volume-ratio exclusion of
the current bar passed. Remaining blockers are (a) aggregate freshness showing
`stale` while Daily/60m components are fresh with 3 unavailable symbols, (b)
threshold metadata not being directly exposed for independent reproduction, and
(c) public HTTPS/TLS not configured (`https` probe failed; HTTP remains the live
route). This is usable as a controlled HTTP team feed, not a production-ready
secure external integration. Alerts, auto-trading, and broker execution remain
OFF/PENDING.

### Team Facts API remediation promotion — 2026-09-03 20:23 ICT

The owner-authorized Ploy feedback remediation was promoted from the current
canonical bind-mounted source with `docker compose up -d --force-recreate dashboard`; no ingestion, migration, or database write was performed. The
Dashboard and backend services are healthy after promotion.

Public read-back via `http://91.98.72.120:3001`:

- unauthenticated Team Facts list → HTTP 401;
- authenticated list → HTTP 200, `team-facts-list-v1`, 96,509 bytes;
- views: `momentum=11`, `near_high=6`, `pullback=44`;
- freshness: `overall_status=partial`, `daily_status=partial`,
  `intraday_status=fresh`, 3 unavailable Daily symbols;
- `filter_version=team-facts-filters-v1` and thresholds for all views present;
- authenticated IRPC 60m history → HTTP 200, 5 completed candles plus
  Daily-baseline metadata-only;
- `/mvp` → HTTP 200; `/health/readiness` → HTTP 200;
- all Compose services healthy and Team API key loaded in dashboard.

Ploy A2A re-review after this source remediation: contract items passed in
principle, but production authenticated validation remains `NOT VERIFIED` from
Ploy's environment because the production key was deliberately not sent over
A2A. HTTPS/TLS remains a separate hardening blocker; the current controlled
feed is HTTP only. Alerts, auto-trading, and broker execution remain OFF/PENDING.

### Team Facts public no-auth promotion — 2026-09-03 20:43 ICT

Per Arm's decision, `TEAM_SCAN_API_KEY` was removed from `/root/signalix/.env`
and the dashboard was recreated with `docker compose up -d --force-recreate dashboard`. Team Facts list/history routes are now public read-only routes;
other protected routes remain unchanged.

Public read-back:

- Team Facts list without headers → HTTP 200, `team-facts-list-v1`, 96,509 bytes;
- views: `momentum=11`, `near_high=6`, `pullback=44`;
- 60m IRPC history without headers → HTTP 200, 5 completed candles plus
  Daily-baseline metadata-only;
- dashboard container has no `TEAM_SCAN_API_KEY` loaded;
- `/webhook` without its secret remains HTTP 401;
- all Compose services healthy, `/mvp` HTTP 200, readiness HTTP 200.

Ploy's final A2A handoff/read-back task `task-51ca73d65f974fa8` confirmed public
route, facts-only boundary, thresholds, history limits, and volume-ratio basis.
Ploy still reports `REVISE / NOT VERIFIED` for freshness propagation: the
aggregate/source status and symbol/facts status can disagree (for example
`source_status=stale` while a component says fresh). This remains an explicit
contract hardening item; the feed is usable for public read-only facts, but
freshness must be interpreted carefully and is not a buy signal.

### Team Facts final freshness re-gate — 2026-09-03 21:02 ICT

Ploy's final A2A re-review after the source-metadata remediation returned
`PASS` for the public facts-only feed. Production read-back confirmed
`overall_status=partial`, `daily_status=partial`, and `intraday_status=fresh`,
with exactly 3 missing Daily symbols explicitly reported; symbol-level list and
history freshness for IRPC matched (`fresh`) across list item, facts, Daily
baseline, and history run. Source producer values are retained only under
`source_metadata.scope=published_read_model_report`, `authoritative=false`,
`reported`, so they cannot override the Team Facts freshness envelope.

Ploy also confirmed public list/detail routes, facts-only boundary, thresholds,
completed-bar/timeframe separation, and previous-20 volume-ratio basis. Final
status for the intended use is `PASS — public facts-only scan feed for 3–4
rounds/day`, not a buy or trading-action API. The three Daily-missing symbols
remain explicit partial coverage and must not be treated as full 237-symbol
Daily coverage.

### Deferred features — 2026-09-01

- Alerts/delivery: `PENDING / FUTURE FEATURE`, OFF.
- Automatic trading/broker execution: `PENDING / FUTURE FEATURE`, OFF and not authorized.
- Evaluator auto-caller: `PENDING / OWNER DECISION`; if approved later, it will append lifecycle evaluation evidence only, not submit orders.

The paused delivery container, Telegram credentials, and alert source are retained for reversible rollback. No secrets are stored in this note.

### Quote-complete read-model republish (after promotion)

After the code promotion/reload is approved, Lite runs the publisher in-process
inside the backend container; this does not run ingestion or write PostgreSQL:

```bash
docker exec signalix_backend python -c 'import update_data; update_data.publish_canonical_read_model()'
```

Expected success output includes one line beginning
`READ_MODEL_PUBLISHED ` with JSON containing `count: 237`, a new
`source_version` beginning `read-model-`, and the versioned artifact path.
The publisher first builds the quote-bearing model, writes the new immutable
`backend/read-model/versions/<source_version>.json`, then atomically moves
`backend/read-model/current.json`. A `READ_MODEL_SKIP` line means the
republish did not complete and must not be treated as acceptance evidence.

`/root/signalix` is the canonical production bind mount. Session closeout 2026-09-02 archived the stale R4/R5 Kanban graph; many historical/feature worktrees remain on disk and must be inspected before removal. `signalix_backend` and `signalix_dashboard` mount `/root/signalix/backend`; no retired path is treated as current source.


## Reload after edits (CRITICAL)
For this bind-mounted stable worktree, a dashboard-only Python/UI change is
reloaded with:
```bash
docker restart signalix_dashboard
```
Use `docker compose up -d --force-recreate` only when compose configuration,
image dependencies, or environment wiring changes. Verify the served endpoint
after the restart; a successful restart alone is not acceptance evidence.

## Environment (`/root/signalix/.env`)
| Var | Purpose |
|-----|---------|
| `POSTGRES_*` | DB credentials (values kept in host/service environment; never store here) |
| `REDIS_URL` | `redis://redis:6379/0` (docker net name) |
| `REDIS_CHANNEL` | `signals` |
| `TELEGRAM_BOT_TOKEN` | from `/root/.hermes/.env` (reuse, don't regenerate) |
| `TELEGRAM_CHAT_ID` | `7295704669` |
| `DASHBOARD_PUBLIC_URL` | public base for alert links |
| `WEBHOOK_SECRET` | shared secret for `/webhook` (agent-generated) |
| `LLM_API_URL` / `LLM_API_KEY` | Phase 3 (currently empty) |
| `SETTRADE_*` | Settrade Open API creds (in `settradeupdated.env`) |

## systemd timers (host, not docker)
- `signalix-update.timer` — weekday EOD ingestion + Daily scan at 18:30 Bangkok. Its canonical source is `/root/signalix/backend/update_data.service`; the deployed unit must be byte-identical. Daily path does **not** run full intraday; `signalix-intraday.service` owns 60m fetching. `ExecStartPost` runs `verify_mvp_only.py` against the canonical MVP artifact and latest Daily run.
- `signalix-eod-healthcheck.timer` — weekday EOD freshness watchdog at 20:00 Bangkok. It checks the latest `price_data` date, latest Daily scan date, service result, and writes durable JSONL/state evidence to `/root/signalix/eod_healthcheck_log.jsonl` and `/root/signalix/eod_healthcheck_observations.json`.
- `signalix-intraday.timer` — 13 weekday rounds in Bangkok: `10:00, 10:30, 11:00, 11:30, 12:00, 12:30, 14:00, 14:30, 15:00, 15:30, 16:00, 16:30, 16:45`. The service guard is `10:00–16:45`; the default fetch scope is canonical `marginable_long`, with explicit `active_ord` retained for audit/rollback runs. It runs with `--no-scan`: each round fetches/evaluates stored 60m data and does not invoke the expensive Daily scan, avoiding overlap. Failed/skipped fetches do not advance VCP.
- `signalix-intraday-watchdog.timer` — independent freshness monitor. It tolerates expected `partial_success`, checks `intraday_price_data` at a cadence-aware 90-minute threshold, checks evaluator state at 30 minutes, and writes structured JSONL evidence.
- `signalix-profile-refresh.timer` — low-frequency weekday Yahoo fallback metadata cache refresh; `refresh_company_profiles.py` is constrained to active `ORD` rows and records failures/backoff in PostgreSQL. It is context-only and must not feed signal calculations.
- `signalix-factsheet-refresh.timer` — bounded weekday SET factsheet refresh, active ORD only, 20 symbols per run, persisted JSONL progress, upserts `set_factsheet` fields without overwriting stronger existing evidence. It is the authoritative profile-source refresh; Yahoo remains fallback.
- MVP chart contract — `GET /api/chart-db/{symbol}?timeframe=1D|1W|60M|1M`; `1D` reads Daily OHLCV with a same-day provisional 60m replacement when available, `1W`/`1M` aggregate those Day bars, and `60M` reads stored intraday 60m bars. Unsupported `15M` returns HTTP 400.
- MVP freshness contract — the header reports `Daily EOD` from the canonical Daily run and `60m updated` from the latest completed `intraday_ingestion_runs` row. A successful intraday fetch/evaluator must advance the latter without changing Daily decision provenance.
- Intraday metadata seam — after a committed successful `marginable_long` ingestion run, the updater atomically publishes `intraday-latest.json` beside the canonical read model. `/api/setup-candidates` and symbol detail read this bounded sidecar without request-time PostgreSQL acquisition; absent, malformed, stale, `active_ord`, or legacy/null identity falls back to embedded read-model metadata. `intraday_ingestion_runs.fetch_universe` is added idempotently by `ensure_intraday_table`; `active_ord` remains audit/rollback-only and is never canonical product metadata.
- MVP timestamp display — the setup-candidate metadata line reports both `60m fetched` from `intraday_ingestion_runs.fetch_completed_at` and `latest completed 60m candle` from the per-item stored candle timestamp; these must not be conflated.
- MVP chart safety — timeframe requests are abortable/generation-guarded; unavailable 60m feeds show an explicit `60m unavailable · Daily EOD remains the decision source` state. Mobile chart/filter controls are at least 44px.
- Historical Daily Trend Map read model (superseded; current identity is in the fresh promotion section above) — `backend/shadow_read_model_publisher.py` writes immutable versioned JSON under `backend/shadow-read-model/` and atomically replaces `current.json`; the API reads only that pointer/artifact. The existing EOD updater invokes it after a successful `--scan` Daily update, while intraday-only runs do not. The 2026-09-12 read-back verified `229 AVAILABLE / 5 INVALID_DATA / 3 NO_DATA`, 237 declared rows, `FRESH`, and the historical artifact hashes recorded in the dated evidence above.
- Shadow hardening source contract: publisher retrieval is capped at 430 rows/symbol with explicit `cap_reached`/`cap` provenance. The single read-only batch query returns newest capped rows plus per-symbol `quality_scan`, `quality_established`, and exact `_valid`-equivalent `invalid_count` metadata over filtered Daily source rows; no unbounded history is transferred or claimed. A cap-hit `AVAILABLE` row is valid only with established quality and zero invalid rows; invalid rows remain `INVALID_DATA`, and unestablished quality is `DATA_BLOCKED`. Non-cap-hit rows retain max400/min30/prior10 behavior. Immutable artifacts persist numeric DB-read, classification, serialization/write-preparation, and total publisher timings with `measurement_scope=pre_immutable_write`; HTTP exposes separate read-path latency and validates the pointer/artifact on every request. Version identity includes content and measurement fingerprints, so changed measurement metadata cannot overwrite or falsely collide with an immutable artifact. HTTP returns read-path latency plus `published_at`, `age_seconds`, and configurable stale status; stale/corrupt/missing artifacts are visible `DATA_BLOCKED`/`NOT_VERIFIED` with zero rows. EOD publish exceptions emit structured failure events and preserve the prior pointer. The production Trend Map route is permanently public read-only with no authentication; it is non-actionable Daily evidence and separate from `/mvp`'s owner-only/private signal policy.
- The current SQL guard is source-only and fail-closed: only one `SELECT`/read-only `WITH` is admitted; mutating verbs (`INSERT`, `UPDATE`, `DELETE`, `MERGE`, `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `GRANT`, `REVOKE`) anywhere in the statement, including data-modifying CTEs, are rejected. The database read-only transaction remains defense-in-depth. The public shadow route requires no credential or secret and has no action/order semantics.
- Shadow quote-column source change (2026-09-12): the isolated table reads persisted `quote.price`, `quote.change_amount`, and `quote.change_pct` from the immutable Daily artifact, with `previous_daily_close` basis and explicit quote provenance. The quote representation revision is part of artifact and pointer identity, so an older same-as-of/policy/universe artifact without quote fields remains untouched and cannot be overwritten. Deployed/public read-back: HTTP 200, artifact `quote-envelope-v2`, 237 rows, sample quote `4.08`, `-0.04`, `-0.97%`, basis `previous_daily_close`; no `/mvp` frontend behavior or canonical read model changed.
- Shared drawer DOM mapping regression (2026-09-12): explicit mappings align `renderSharedDetail` with shared markup IDs (`drawer-provenance`, `drawer-52w`, `drawer-ath`). After dashboard recreate, public `/trend-map-shadow` and `/mvp` returned HTTP 200; served `shared-drawer.js` contains one `openSharedDrawer` and one `drawChart`; real headless click test opened shadow drawer for `ADVICE` and reached `Chart status: Confirmed candle · 2026-09-11`. No API, database, ingestion, publisher, `/mvp` semantics, alerts, or broker behavior changed.
- Shared drawer OHLCV table overflow fix (2026-09-12): the seven-column `OHLCV Window Summary` is now inside `.rolling-high-low__table-wrap`, which owns horizontal scrolling while the inner table keeps a readable minimum width; page-level horizontal overflow remains hidden. `/mvp` and shadow usage and product semantics are unchanged. Deployed and browser-verified at 390px: `innerWidth=390`, `bodyScrollWidth=390`, drawer visible, wrapper `clientWidth=348`, `scrollWidth=980`, `overflow-x=auto`.
- Closeout release (2026-09-12): commits `f18e48f` and `15701ef` are pushed to `release/signalix-mvp-stable`; remote SHA is `15701effad9d6549687740bf65af422a909d38af`. Dashboard was recreated from the release source and is healthy; public `/trend-map-shadow`, `/api/trend-map-shadow`, and `/mvp` read-back passed. Browser verification at 390px confirmed drawer/chart, bounded OHLCV scrolling, and MA control computed height `44px`; error→Retry→recovery returned 237 rows. The next scheduled EOD freshness/read-back after this release remains `NOT VERIFIED` and is not claimed here.
- Worktree note: generated `backend/shadow-read-model/` artifacts are intentionally tracked runtime inputs in commit `f18e48f`, not untracked research artifacts. Untracked `research/`, `docs/current/`, and `docs/agents/` QA/session notes remain preserved owner/research artifacts outside that commit and must not be cleaned or treated as deployment evidence.
- `signalix_delivery` was briefly a host unit; **superseded** by the docker `delivery` service.

## Verify realtime push
```bash
docker exec -t signalix_redis redis-cli pubsub numsub signals   # >=1
docker exec -t signalix_delivery python -c "import os;print(bool(os.getenv('TELEGRAM_BOT_TOKEN')))"
# live send test:
docker exec -t signalix_delivery python -c "import os,requests;r=requests.post(f'https://api.telegram.org/bot{os.getenv(\"TELEGRAM_BOT_TOKEN\")}/sendMessage',json={'chat_id':os.getenv('TELEGRAM_CHAT_ID'),'text':'test'},timeout=10);print(r.status_code,r.json().get('ok'))"
```

## Pitfalls
- **Host consumer fails** (no `redis` in host venv; `redis://redis` unresolvable off docker net).
- **Block-buffered logs** — use `python -u` in the delivery command.
- **Intraday evaluator import** — do not execute `backend/run_intraday_evaluation.py` as a standalone script; `intraday_evaluator.py` uses package-relative imports. Use the module form from `/root/signalix`.
- **LINE** — `notify-api.line.me` is DNS-blocked on this VPS; dropped per user.
- Plain `restart` leaves stale env/code running — always `force-recreate`.

See skill `signalix-delivery-ops` for the ops playbook.
