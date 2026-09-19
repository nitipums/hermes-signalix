# Deployment

> **STATUS: CURRENT** · `CANONICAL_FOR: deployment/runbook/timer ownership`.
> **Reconciled:** 2026-09-17 ICT · canonical product line is Daily Trend Mapping at `/trend-map` and `/api/trend-map`; Trend Route artifact `trend-route-cc791d2d85645bce9b5347b8` is served at `/api/trend-map/{symbol}/route`; final stable closeout is recorded in the Git release branch. The automated EOD publication hook and Trend Route rollback drill remain `NOT VERIFIED`. The former shadow naming is retired. `/mvp` and `/api/setup-candidates` are historical/audit only.

## Dashboard canonical-mount repair — 2026-09-16 20:20 ICT

- Root cause: `signalix_dashboard` had been recreated from `/root/signalix/.worktrees/trend-route-task1/backend`, while the EOD updater and backend publisher write to `/root/signalix/backend`; the public pointer therefore remained on the 2026-09-15 artifact despite a successful 2026-09-16 EOD run.
- Authorized action: from `/root/signalix`, `docker compose up -d --force-recreate dashboard`; PostgreSQL, Redis, and backend were not restarted or written.
- Read-back: dashboard bind mount is `/root/signalix/backend -> /app`; container pointer and public `/api/trend-map` now report artifact `shadow-trend-map-quote-envelope-v2-2026-09-16-87dce5718dd0784a-e76ebcbf1637fac9-bff84361c2fcd4f4-9b4d0a5b86167135`, `as_of=2026-09-16`, `verification_status=VERIFIED`, and `237` rows.
- Public browser `/trend-map` read-back shows `Data date 2026-09-16`, `Status Current`, and `Showing 237 of 237` symbols.
- **Wave 1 Market Breadth companion promotion — 2026-09-19:** Source commits through the final stable closeout are on `release/signalix-mvp-stable` from `/root/signalix`. The companion read-only page is `/market-breadth` with `/api/market-breadth`; top navigation links it with `/trend-map` in both directions. The generated artifact was rebuilt from the production PostgreSQL source with `PYTHONPATH=backend python -m market_breadth_publisher --read-only --root backend/market-breadth-read-model` and validated as `signalix.market-breadth.artifact.v2`, hash `c19d4ed5a7db3e522ea3f5e0ff4f151643895bdcb47eaf4d9d4de8dcdcf020d`, `as_of=2026-09-18`, `929` active symbols, `841` observed, `88` blocked, `quality=PARTIAL`, `freshness=AVAILABLE`, `260` report sessions. `docker compose up -d --force-recreate dashboard` was run from `/root/signalix`; Compose recreated `signalix_backend` and `signalix_dashboard`, while PostgreSQL and Redis remained running. Readiness returned `{"status":"ok","db":"up","redis":"up"}`. Local and public Market Breadth API returned HTTP 200, `PRODUCTION_READ_ONLY`, `PARTIAL`, and the same coverage; public 390px browser read-back verified both navigation links, active state, no overflow, as-of/quality/coverage, and `range=20` loading. Trend Map freshness remediation is recorded in the following section and is not part of the Market Breadth artifact contract. Git source is on the final stable closeout branch; generated Market Breadth artifacts remain untracked runtime inputs; no push performed.
- Operational safeguard: production Compose commands must run from `/root/signalix` so the canonical `/root/signalix/backend` bind mount and generated artifacts align. The Wave 1 Market Breadth read-back above verified the served artifact and retains `quality=PARTIAL` for `841/929` observed active-ORD coverage. The Trend Map freshness remediation evidence remains recorded below; no deployment or runtime action is part of this documentation reconciliation.
## Trend Map freshness remediation — 2026-09-19

- The canonical pointer had remained on the 2026-09-15 artifact and correctly failed closed at the public API with `DATA_BLOCKED`, `verification_status=NOT_VERIFIED`, and `freshness=STALE` after the 172800-second freshness window. From `/root/signalix`, the SELECT-only publisher `PYTHONPATH=backend python -m shadow_read_model_publisher --root backend/shadow-read-model` generated immutable artifact `shadow-trend-map-quote-envelope-v2-2026-09-18-87dce5718dd0784a-e76ebcbf1637fac9-f34bcb3ad1244662-f3783cb9724c81a5`, `as_of=2026-09-18`, `237/237` declared/evaluated/returned, `blocked=0`, published at `2026-09-19T06:29:46.448688+00:00`. Pointer/artifact validation passed. The dashboard was recreated from `/root/signalix`; readiness returned `{"status":"ok","db":"up","redis":"up"}`. Local and public `/api/trend-map` returned HTTP 200, `PRODUCTION_READ_ONLY`, `VERIFIED`, `FRESH`, `237` rows. Public 390px browser showed `Data date 2026-09-18`, `Status Current`, `Showing 237 of 237`, no overflow, and navigation to `/market-breadth`; no PostgreSQL/Redis write or migration occurred. The immutable version and tracked `current.json` pointer require the remediation commit; generated Market Breadth artifacts remain runtime inputs.

## Trend Route production read-back — 2026-09-17

- Source: scoped feature commit `3733c4d` on `release/signalix-mvp-stable`; no database migration or PostgreSQL/Redis restart.
- Publisher: optimized deterministic replay computes aligned Daily indicators once per symbol; benchmark `237 × 260 sessions` completed in `18.718s` on the publication host. Real SELECT-only replay completed with one market-wide cutoff `2026-09-17`.
- Artifact: `trend-route-cc791d2d85645bce9b5347b8`, pointer `backend/trend-route-read-model/current.json`, `237/237` resolved/published routes, `229 FULL`, `8 PARTIAL`; partial reasons are explicit: limited history for `3BBIF`, `COM7`, `PR9`, `MRDIYT`, `TURBO`, `WASH`, and true missing-session evidence for `BANPU`, `PROUD`.
- API: local/public `GET /api/trend-map/TEAM/route` returned HTTP 200, `PRODUCTION_READ_ONLY`, `VERIFIED`, `FULL`, `260` sessions; unknown `ZZZ` returned HTTP 404. Public API reads the validated artifact and does not replay/query raw history.
- Runtime: dashboard recreated from `/root/signalix`; readiness remained healthy; PostgreSQL and Redis were not restarted.
- Browser: public `/trend-map` drawer rendered the route graph and segment detail at desktop and 390px; mobile `scrollWidth=390`, `bodyScrollWidth=390`, graph width `366px`; no action/order semantics were added.
- Rollback: prior Trend Route artifact remains immutable in the isolated source history; explicit source-plus-artifact rollback drill is `NOT VERIFIED` for this new feature.

## Stable release

```text
branch: release/signalix-mvp-stable
source: /root/signalix
MVP server: mvp_server.py
legacy routes: quarantined/404
```

## Runtime reload read-back — 2026-09-14 11:35 ICT

- Authorized action: `docker compose up -d --force-recreate dashboard`; PostgreSQL and Redis were not restarted, migrated, or written.
- Container: `signalix_dashboard` running and healthy after recreate.
- Readiness: `GET http://127.0.0.1:8000/health/readiness` returned `{"status":"ok","db":"up","redis":"up"}`.
- Public HTML: `/trend-map` returned HTTP 200; browser rendered 237 rows at desktop and mobile 390px.
- Public API: `/api/trend-map` returned HTTP 200 with `status=PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`, `verification_status=VERIFIED`, and 237 rows.
- Retired route read-back: `/trend-map-shadow` and `/api/trend-map-shadow` returned HTTP 404.
- Browser metrics: desktop `scrollWidth=485`/`clientWidth=485`; mobile `scrollWidth=390`/`clientWidth=390`; `shadow` was absent from visible DOM copy.

## Historical-invalid quality-window fix — 2026-09-16

- Root cause: six old OHLC-incoherent rows across five symbols (`BTS`, `CPN`,
  `SABINA`, `SC`, `SIRI`) were outside the newest 430-row analytical window,
  but the producer's quality aggregate scanned all history and blocked the
  current classification.
- Settrade Open API manual read-only check returned 430 clean Daily rows for
  each affected symbol through `2026-09-15`; the API did not return replacement
  values for the 2011–2013 source rows, so historical DB rows were not mutated.
- Fix: quality gating now uses the same newest `RETRIEVAL_CAP=430` rows used for
  classification. Invalid rows inside that window remain fail-closed; older
  invalid rows remain untouched/audit evidence and do not block current output.
- Commit: `2d83f9f77b72fa4feb32053f1bc2342b08fabece`.
- Runtime/API read-back: `237/237` returned, `AVAILABLE=237`,
  `INVALID_DATA=0`, `DATA_BLOCKED=0`, `verification_status=VERIFIED`; dashboard
  and backend healthy. No PostgreSQL write or migration was performed.

## Current delivery focus — 2026-09-12

The primary workstream is the production-served, public, read-only Daily Trend Mapping surface. Its active bounded promotion/closeout contract is GitHub Issue [#17 — Daily Trend Map: public read-only delivery closeout](https://github.com/nitipums/hermes-signalix/issues/17):

### Intraday display quote overlay — runtime read-back PASS

- The Trend Map scan/classification remains EOD-only and immutable. A bounded
  read-only API overlay now uses the latest completed `intraday_price_data`
  60m bar for display-only `quote.price`, `quote.change_amount`, and
  `quote.change_pct`; the change basis is the immediately prior completed Daily
  close. `main_trend`, scan status, classifier evidence, and EOD `as_of` remain
  unchanged. Missing, stale, future, malformed, or unusable intraday data falls
  back to the immutable EOD quote with explicit provenance.
- Source/tests: `PASS` — `pytest -q backend/test_read_model_publisher.py backend/test_shadow_trend_map.py -rA` returned `73 passed, 1 skipped`; compile and `git diff --check` passed.
- Authorized runtime action: `docker compose restart dashboard`; PostgreSQL and
  Redis were not restarted, migrated, or written.
- Readiness: `{"status":"ok","db":"up","redis":"up"}`; dashboard health
  `healthy`.
- Public `/api/trend-map`: HTTP 200, `PRODUCTION_READ_ONLY`, `VERIFIED`,
  `237` rows; intraday overlay `AVAILABLE`, `236` rows applied, `1` row
  (`PTL`) explicitly fell back to EOD quote.
- Public browser: `TEAM` displayed `5.75`, `-0.05`, `-0.86%`, and
  `Quote · 60m provisional`; drawer chart rendered with a `461x360` canvas,
  no page overflow (`bodyScrollWidth=500`, `clientWidth=500`).
- No database write, migration, commit, or push was performed.

### Full Trend Map UX remediation — browser read-back PASS

- Scope: drawer failure recovery, chart retry control, EOD-versus-intraday
  provenance, official-versus-derived Daily labels, keyboard focus handling,
  blocked-row filter/reason affordance, stale-drawer invalidation, and mobile
  full-value affordance. Scan/classifier semantics and the immutable artifact
  were unchanged.
- Source/tests: `pytest -q backend/test_shadow_trend_map.py` returned `51
  passed`; Trend Map UX contract selection
  `pytest -q backend/test_mvp_frontend_contract.py -k 'trend_map_'` returned
  `5 passed`; JavaScript syntax, Python compile, and `git diff --check` passed.
- Public desktop browser: `237` rows; provenance line visible; `Not verified /
  blocked` filter visible; drawer opened with focus on `drawer-close`; quote
  label showed `Quote · 60m provisional (intraday_price_data)`; chart canvas
  rendered `461x360`; page width remained contained.
- Public 390px browser: `237` rows; drawer opened with chart canvas `366x360`;
  document/body width remained `390`; closing restored focus to the triggering
  `AKR` row.
- The broader retained `/mvp` frontend contract suite still has unrelated
  historical failures and is not used as Trend Map acceptance evidence.
- Post-review remediation: hidden controls are excluded from the focus trap and pending drawer opens are cleared on filter/reload invalidation; focused contract selection reran with `6 passed`.
- No database write, migration, commit, or push was performed.

### Prebuilt intraday quote read model — runtime performance PASS

- Intraday display quotes are now prebuilt after the intraday ingestion commit
  into a compact validated artifact; `/api/trend-map` reads the artifact and
  no longer opens PostgreSQL for each page request. EOD scan/classification
  remains immutable and separate.
- Artifact read-back: schema `signalix.intraday-quote-read-model.v1`, canonical
  `marginable_long`, `237` symbols, artifact generated
  `2026-09-15T07:43:40.964764+00:00`.
- Public API before optimization: approximately `3.2–3.8s` per request.
  After reload: local/public API `0.11–0.21s` in bounded repeated probes,
  HTTP public `TTFB=0.105s`, `total=0.108s`, with `237/237` intraday quotes and
  `query_mode=PREBUILT_READ_MODEL`.
- Public browser after reload: `/api/trend-map` resource approximately
  `217ms`, `237` rows, no page overflow; drawer still renders the provisional
  intraday quote and chart. Chart request remains a separate optimization
  target (`~1.37s` in the measured browser run) because it reads historical
  OHLC/indicator data rather than the compact quote model.
- Source/tests: `76 passed, 1 skipped` across the prebuilt quote, Trend Map, and
  intraday resilience focused suites; Python compile and `git diff --check`
  passed. No database write or migration was performed; the artifact write and
  dashboard restart were explicitly authorized runtime actions.

### Prebuilt drawer chart read model — runtime performance PASS

- Compact validated chart artifacts are now built for `1D`, `60M`, `1W`, and `1M`
  after the relevant EOD/intraday publication boundaries. The chart route reads
  the artifact before DB fallback; fallback is explicit `DB_FALLBACK` only when
  an artifact is unavailable or stale.
- Startup prewarming validates all four chart artifact identities into the
  process cache. A validated pointer change invalidates only the affected
  timeframe; stale/missing/corrupt artifacts still fall back safely.
- Public API after reload: first requests for all four timeframes were below
  `50ms` after startup prewarm; subsequent requests remained below `30ms`,
  versus the prior `~1.4–2.5s` cold chart path.
- Public browser drawer: 1W and 1M controls requested their exact timeframe
  routes and rendered the canvas; quote remained `60m provisional`, `237` rows
  remained visible, and page overflow stayed contained.
- Drawer chart projection now serializes only renderer-required aligned series
  (`ma`, `macd.line/signal/histogram`, `rsi`) while preserving candles,
  indicators.latest/window summaries, provenance, and default full-chart
  contract. The measured 1D chart body fell from approximately `274KB` to
  `44KB`; browser chart request remained approximately `18ms` and rendered.
- Source/tests: all-timeframe chart read-model, Trend Map, and technical-indicator
  focused tests passed; Python compile, JavaScript syntax, and `git diff --check`
  passed. No database write or migration was performed; chart artifacts and
  dashboard restart were explicitly authorized runtime actions.

### Compact public Trend Map projection — runtime performance PASS

- The public `/api/trend-map` now projects a compact copy of each validated row:
  it preserves quote, Main Trend display fields, status/quality, concise
  provenance, no-lookahead, and fallback evidence while removing raw selected
  lineage arrays, diagnostic traces, retrieval selection, and audit-only evidence
  from the first-screen payload. The immutable artifact remains unchanged.
- Public body size in the measured route fell from approximately `1.34MB` to
  `410KB` uncompressed (`237` rows preserved); compressed transfer remained
  small. The public browser still rendered `237` rows and opened the drawer/chart.
- Source/tests: compact projection and API contract tests passed; runtime API and
  browser read-back passed. No actionability, scan, or classifier semantics
  changed.
- Drawer chart now fails closed when usable OHLC history has fewer than two
  candles: the canvas is hidden and the user sees `Chart unavailable:
  insufficient candle history` instead of a blank graph.

### Main Trend 1–4 UI promotion — 2026-09-13

- Owner-authorized bounded promotion for Issue #32: deterministic `main_trend` evidence was published into the immutable Trend Map artifact. The public table and Trend Map drawer now use Main Trend 1–4 as the only visible primary taxonomy; legacy machine-lane/sub-trend presentation is not shown on the public surface. No setup/action/order semantics changed.
- Artifact: `shadow-trend-map-quote-envelope-v2-2026-09-11-87dce5718dd0784a-e76ebcbf1637fac9-22539233599029de-29081b4b1ba2f3bb`; `237/237` declared/evaluated/returned; `45 Main 1 / 19 Main 2 / 58 Main 3 / 110 Main 4 / 5 blocked`; `226 FULL / 6 PARTIAL` among classified rows. Main Trend policy is `main-trend-ma-calibration-v6`; chart policy is `technical-indicators-v2` with MA5/10/20/50/100/200 and separate 260-candle coverage.
- Runtime: backend recreated, dashboard started/recreated; readiness returned `status=ok`, `db=up`, `redis=up`. No migration or database write was performed.
- Public API: HTTP 200, `PRODUCTION_READ_ONLY`, `verification_status=VERIFIED`, freshness `FRESH`, `actionability=NONE`; local/public artifact identity matched.
- Public browser at 390px: `237` rendered rows; visible Main Trend-only grouping/filter/table; sample values `1 · FULL` / `3 · FULL` / `4 · FULL`; legacy machine-lane labels are absent; `scrollWidth=390`, `bodyScrollWidth=390`.
- Status: source/tests/runtime/API/browser `PASS`; commit/push not performed; working-tree artifact/source changes remain uncommitted.

### Main Trend display suffix promotion — 2026-09-14 08:23 ICT

- Owner-authorized bounded promotion adds deterministic display-only suffixes over the canonical numeric Main Trend: `1++`, `1+`, `1`, `2`, `3`, `3-`, `3--`, `4`. `1++`/`3--` are strict; `1+`/`3-` are broad-only; ordinary values remain unsuffixed. This is visual evidence only; `actionability=NONE` and the numeric `main_trend` remain unchanged.
- Source/tests: focused Main Trend, Trend Map, and shared-drawer suites passed (`65 passed`); Python compile, JavaScript syntax, and `git diff --check` passed.
- Immutable artifact: `shadow-trend-map-quote-envelope-v2-2026-09-11-87dce5718dd0784a-e76ebcbf1637fac9-1a9d7d18a342e6bd-b049c7d5dd8f590b`; `237/237` declared/evaluated/returned; display distribution `33 Main 1 / 4 1+ / 8 1++ / 19 Main 2 / 39 Main 3 / 10 3- / 9 3-- / 110 Main 4 / 5 blocked`.
- Runtime/API: backend and dashboard recreated; readiness returned `status=ok`, `db=up`, `redis=up`; local and public API returned HTTP 200, `PRODUCTION_READ_ONLY`, `verification_status=VERIFIED`, freshness `FRESH`, and the new display field.
- Public browser: `http://91.98.72.120:3001/trend-map` verified at desktop `1280px` and mobile `390px`; representative rows showed `AKR 1++`, `AAI 1+`, `LHFG 3--`, `AOT 3-`; AKR drawer showed `Main Trend 1++ · FULL`; mobile `scrollWidth=390` and `bodyScrollWidth=390`.
- Follow-up presentation ordering: within Main Trend 1, rows render `1++ → 1+ → 1`; within Main Trend 3, rows render `3-- → 3- → 3`. Quote change descending and symbol ascending remain secondary tie-breaks. Public mobile and desktop read-back passed; opening AKR then Next moved to GFPT (`1++`) in the rendered order.
- Mobile table containment: at `390px`, the five-column table rendered at `366px` with `document.scrollWidth=390`, `body.scrollWidth=390`, all primary columns visible, and `1++ · FULL` intact; desktop table rendered at `924px` inside a `960px` main container.
- Boundary: no database migration/write, alert, broker, order, or auto-trading action. Commit and push were not performed; pre-existing untracked version artifacts remain preserved.

### Signal Accordion visual redesign — 2026-09-15 21:22 ICT

- Scope: `backend/shadow_trend_map_template.html` plus focused contract coverage; API, immutable read model, classifier semantics, and shared drawer source were unchanged.
- UI: production `/trend-map` now groups Main Trend 1–4 and blocked evidence into closed-by-default accordion sections. Per-symbol table rows are created only when a section opens; one section stays open at a time. Search/filter/retry and lazy drawer behavior remain read-only.
- Branding/theme: Signalix wordmark/mark, editorial hierarchy, semantic trend colors, and persisted dark-default/light theme were added without external assets or additional network requests.
- Source/test: `pytest -q backend/test_shadow_trend_map.py -rA` returned `58 passed`; Python compile, inline JavaScript syntax, and `git diff --check` passed.
- Served browser: public `http://91.98.72.120:3001/trend-map` rendered the new accordion/theme markers, 237 rows, and FRESH data. At 390px, opening Main Trend 1 rendered 44 rows, opening BJC opened the real drawer/chart, and `scrollWidth=390` / `bodyScrollWidth=390`. Desktop 500px also remained contained.
- Performance boundary: only the existing `/api/trend-map` request was observed for the page; accordion expansion performs client-side projection only. No database write, migration, restart, commit, or push was performed.

### Trend Map drawer theme inheritance — 2026-09-15

- Light theme now bridges the Trend Map palette into the shared drawer surface without changing drawer JavaScript, chart requests, or data semantics.
- Public browser read-back: persisted `theme-light` rendered drawer panel/header `#fffdf8`, chart shell `#f4f1ea`, text `#1d2733`; drawer opened normally and `scrollWidth=500` / `bodyScrollWidth=500`.
- Source/test/runtime boundary: focused Trend Map tests, compile, inline JS syntax, and `git diff --check` passed; no database write, migration, restart, commit, or push was performed.

### Adversarial UX refinement — 2026-09-15

- Persona feedback added one concise first-screen explanation: `Main Trend shows the Daily direction. Open a group to see its evidence.` Accordion controls now expose visible and accessible `Open evidence` / `Close evidence` states.
- Adversarial browser regression found and fixed deferred-DOM retention: closing a group now clears its symbol rows from the hidden panel; public 390px read-back showed `44 rows → 0 rows on close → 44 rows on reopen`, with no overflow (`375/375`).
- Source/test: focused Trend Map tests, Python compile, inline JavaScript syntax, and `git diff --check` passed. No API/data/drawer logic or database behavior changed.

### Plain-language Trend Map refinement — 2026-09-15

- First-screen copy now uses `Data date`, `Status · Current`, `Scope · Thai listed universe`, `Showing`, and `Total`; the raw classifier policy id and technical freshness/status values moved under collapsed `Technical details`.
- Provenance copy explicitly explains that Daily direction is classified from end-of-day data and the 60-minute price is display-only; this preserves the EOD/intraday boundary without requiring users to know `provisional` or `Thai ORD` terminology.
- Public 390px browser read-back: helper copy, plain labels, accordion/drawer, light drawer palette, no overflow (`375/375` page and `390/390` drawer), and `DATA_BLOCKED → Retry → Showing 237 of 237 symbols` recovery all passed.
- Source/test/runtime boundary: no API/data/read-model changes, database write, migration, restart, commit, or push.

### Commit/push closeout — 2026-09-16 07:33 ICT

- Scoped implementation commit: `4eb33a6f80122287cf99593d2ff6ba7c205f83c1` (`feat(trend-map): refine accordion evidence UX`).
- Documentation closeout commit: `396f2f5` (`docs(deployment): record trend-map closeout`).
- Published branch: `release/signalix-mvp-stable`; final remote `origin/release/signalix-mvp-stable` is verified at the documentation closeout commit above.
- Implementation scope: `backend/shadow_trend_map_template.html` and `backend/test_shadow_trend_map.py`; the deployment authority was updated in the closeout commits. No unrelated dirty files remained after the closeout.

### Trend Map drawer navigation remediation — 2026-09-13 16:34 ICT

- Scope: `backend/frontend/shared-drawer.js` plus `backend/test_mvp_ui_feedback_contract.py`; no data, API, calculation, alert, order, broker, or auto-trading behavior changed.
- Root cause: drawer navigation retained the first symbol's `chartUrl`, so the header/position advanced while the chart fetched the old symbol; the shared drawer also had no touch gesture handlers.
- Fix: Trend Map navigation now derives the chart request from the current symbol; the drawer body supports horizontal touch swipe (50px threshold), rejects predominantly vertical movement, and ignores controls/links.
- Source/tests: the regression test was RED before the fix and GREEN after it. `pytest -q backend/test_mvp_ui_feedback_contract.py backend/test_shadow_trend_map.py -rA` returned `51 passed`; `node --check backend/frontend/shared-drawer.js` and `git diff --check` passed.
- Served browser read-back through `http://91.98.72.120:3001/trend-map` at 390px: `TEAM` → `RJH` (`2 of 237`) → `KCG` (`3 of 237`); observed chart requests changed respectively to `/api/chart-db/TEAM?timeframe=1D`, `/api/chart-db/RJH?timeframe=1D`, and `/api/chart-db/KCG?timeframe=1D`. Synthetic touch swipe was also verified.
- Runtime boundary: no restart, migration, database write, commit, or push was performed. The served JS matched the current dirty worktree; release promotion remains pending scoped closeout.

### Fresh promotion read-back — 2026-09-13

- Prior source/runtime baseline for the promotion evidence below was commit `45095b320fba6bde72ff3af553ffdaa366426bac`; the Issue #22 implementation baseline is `f99becb5d5d50a49331419bb8d878ae6b9f6d979`. The bounded drawer working-tree verification is recorded above; no new release promotion is claimed here.
- Reload: `docker compose up -d --force-recreate backend dashboard`; PostgreSQL and Redis were left running, with no migration or schema change.
- Readiness: `GET http://127.0.0.1:8000/health/readiness` returned `{"status":"ok","db":"up","redis":"up"}`.
- Publication: bounded publisher created a new immutable artifact with `as_of=2026-09-11`, `237/237` declared/evaluated/returned, and publication time `2026-09-13T03:57:47.890717+00:00`.
- Local/public API: `PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`, `verification_status=VERIFIED`, freshness `FRESH`; quality `229 AVAILABLE / 5 INVALID_DATA / 3 NO_DATA`; public ingress HTTP 200.
- Browser: desktop 237 rows and drawer/chart passed; 390px mobile `scrollWidth=390`, failure showed Retry/zero rows, recovery returned 237 rows. Hermes `browser_exec` was also repaired by restoring the managed Python Browser Use CLI path; helper syntax was verified against the live route.
- Rollback: `PASS`; isolated source-plus-artifact pairing read back both the pre-promotion `6095346` + legacy artifact (`READ_ONLY_SHADOW`, `VERIFIED`, 237 rows) and the promoted source + artifact (`PRODUCTION_READ_ONLY`, `VERIFIED`, 237 rows). No production traffic was switched during the drill.

```text
/trend-map
/api/trend-map
```

This surface is production-served public read-only Daily evidence
(`status=PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`)
and is non-actionable. `/mvp` and
`/api/setup-candidates` are **DROPPED / PAUSED** by owner decision;
their source/history remains retained for audit/future integration only.
Do not route work there until Arm explicitly resumes it; Elliott Wave work is deferred. Any future Trend Mapping to `BUY_NOW` path must
be separately approved and gated.

### Derived Daily fallback runtime read-back — 2026-09-13

- Issue [#22 — bounded derived-Daily fallback and lineage](https://github.com/nitipums/hermes-signalix/issues/22) is committed in `f99becb5d5d50a49331419bb8d878ae6b9f6d979`, pushed, and served in the EOD scan path.
- The writer calls Settrade 60m only for symbols missing the current official Daily session, requests a bounded 8-bar current-session window, requires complete 09:00–16:00 ICT coverage, and upserts only `derived_daily_price_data` with `is_official=false`.
- Live run at cutoff `2026-09-11T17:00:00+07:00`: `3/3` affected symbols, `3` rows written, source run `ef90959e53d24e638fbd67d08d5ab256`; no official `price_data` rows were mutated.
- Publisher/API after backend/dashboard recreate: `237/237`, `232 AVAILABLE`, `5 INVALID_DATA`, `0 NO_DATA`; 3 derived rows expose source run, source timestamps, 60m timeframe, bar count 8, and derivation method.
- Final served artifact: `shadow-trend-map-quote-envelope-v2-2026-09-11-2851c3f13cbd8e39-e76ebcbf1637fac9-7427d84d9c0d5d3e-1782d7eac5ca2ecd`, published `2026-09-13T06:27:49.583069+00:00`.
- Migration smoke: `docker exec -i signalix_postgres psql -U signalix -d signalix < backend/migrations/008_derived_daily_from_intraday.sql` applied twice successfully; read-back confirmed `186/186` derived rows have `source_completion_cutoff`, canonical derivation method, and `is_official=false`, while official `price_data` remains empty for the three fallback symbols.
- Final source/runtime reload: `docker compose up -d --force-recreate backend dashboard`; readiness and public API read-back after the completion-cutoff remediation are recorded in the current acceptance evidence.

## Historical runtime scope — 2026-09-02

At that 2026-09-02 baseline, the promoted Elliott/Trend/Trade-Setup spine was the product surface. `signalix_backend`, `signalix_dashboard`, PostgreSQL, and Redis were healthy at rebaseline; `/mvp` returned 200, `/api/setup-candidates` returned the live DB-built contract, `/health/readiness` was on backend `:8000`, and retired `/dashboard.html` returned 404. The public 390px failure→Retry→recovery journey was verified. The UI showed `60m fetched` separately from `latest completed 60m candle`; session evidence was verified after runtime reload. Alerts, auto-trading, and broker execution remained off.

`marginable_long` is 237 eligible symbols; 929 active ORD is explicit audit/rollback coverage. VCP routes/artifacts remain compatibility/audit only.

### Current Team Facts policy and runtime — 2026-09-10

Owner decision: Team Facts is a public, unauthenticated, read-only facts feed. It does not expose setup, Wave, lane, trigger, risk, target, alert, order, or broker execution semantics. `/api/setup-candidates` remains the separate canonical setup surface.

Historical Team Facts read-back from release `28f7947` (2026-09-10) returned `base_active_ord_count=932`, `eligible_count=237`, `excluded_count=695`; this predates the current symbol-master count (`929/237/692`) and is retained as historical evidence only.

The implementation uses bounded read-only queries and preserves Daily/60m source separation. Rate limiting and HTTPS/TLS remain separate hardening items. Alerts, auto-trading, broker execution, and evaluator auto-caller remain OFF/PENDING.

The Daily Trend Map route is permanently production-served public read-only by
owner decision and requires no authentication. It has no setup,
recommendation, alert, order, broker, BUY, or other action semantics. This is
separate from `/mvp`, which remains governed by its owner-only/private signal
policy. No credential or secret is recorded here.

### Chart fallback and mobile RSI read-back — 2026-09-13 18:23 ICT

- Owner-authorized runtime action: `docker compose restart dashboard`; no
  migration, database write, commit, or push was performed.
- Dashboard health transitioned from `starting` to `healthy`; readiness returned
  `{"status":"ok","db":"up","redis":"up"}`.
- Public `/api/chart-db/PR9?timeframe=1D` returned HTTP 200 with 62 candles,
  `source=derived_daily_price_data`, `as_of=2026-09-11`, RSI `66.177`, and
  complete derived lineage including source run/timestamps, cutoff, timeframe,
  bar count, and derivation method.
- Public `/api/chart-db/3BBIF?timeframe=1D` returned HTTP 200 with 62 candles,
  `source=derived_daily_price_data`, `as_of=2026-09-11`, RSI `47.6568`, and
  the same complete lineage fields.
- Public 500px browser read-back opened both PR9 and 3BBIF at the Trend Map
  drawer. Each showed the Daily chart, RSI summary/panel, 62 candles, derived
  source, and canvas `461x360`; page `bodyScrollWidth=500` matched
  `clientWidth=500`.
- Source/tests remain separate: focused chart/UI/fallback suite passed, JS
  syntax and Python compile passed, and `git diff --check` passed. The source
  changes remain uncommitted; release promotion is not claimed here.

### Drawer timeframe routing read-back — 2026-09-13 18:34 ICT

- Public diagnosis measured TEAM chart responses at approximately 604KB/184ms
  for 1D, 589KB/104ms for 60M, 652KB/204ms for 1W, and 760KB/379ms for 1M.
  The main switching defect was stale URL routing, not a proven backend latency
  regression.
- Owner-authorized source change makes custom `chartUrl` valid only for the
  initial 1D request; 60M/1W/1M construct the same-origin chart-db URL for the
  selected timeframe. Trend Map now passes `chartUrl:null`.
- Public browser read-back at the Trend Map drawer for TEAM verified:
  `1D → 60M` requested `/api/chart-db/TEAM?timeframe=60M` and rendered
  `chart.timeframe=60M`; `60M → 1W` requested
  `/api/chart-db/TEAM?timeframe=1W` and rendered `chart.timeframe=1W`.
- Focused URL-selection, UI feedback, and Trend Map tests passed; `node
  --check backend/frontend/shared-drawer.js` and `git diff --check` passed.
  No additional restart was required after the earlier dashboard restart;
  source changes remain uncommitted and release promotion is not claimed.

### Compact chart payload optimization read-back — 2026-09-13 18:48 ICT

- Added explicit `view=chart` for the drawer only. The default chart API
  contract remains full-size and unchanged for existing callers.
- Compact responses preserve `indicators.latest`, window summaries, aligned
  indicator series, candle source/provenance, derived lineage, provisional
  flags, and read-only semantics while trimming display arrays to 120 candles.
- Public TEAM measurements after dashboard reload:
  `1D` compact `280,326` bytes vs default `603,857`; `60M` compact `270,769`;
  `1W` compact `302,229`; `1M` compact `353,230`. These are payload-size and
  request measurements, not a universal latency claim.
- Public mobile browser verified `TEAM` initial `1D`, then `60M`, then `1W`:
  each request included `view=chart`, rendered the requested timeframe, used
  120 candles, and kept `bodyScrollWidth=500` equal to `clientWidth=500`.
- Screenshot inspection verified PRICE/VOL/MACD/RSI panels and the RSI line
  remain visible inside the compact chart without clipping.
- Focused compact/default/route/timeframe tests passed; Python compile,
  `node --check`, and `git diff --check` passed. Legacy `/mvp` frontend
  contract failures remain pre-existing and outside this Trend Map slice.
- Source changes remain uncommitted; no commit, push, or release promotion is
  claimed.

### Historical deployment evidence — 2026-09-12 (superseded; not current runtime)

The bounded publisher, artifact/failure-sidecar validation, EOD hook, and
fail-closed SQL guard were deployed and publicly read back. The public
`GET /api/trend-map` returned HTTP 200 with 237 rows: `229 AVAILABLE`,
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
- `signalix-update.timer` — weekday EOD ingestion + Daily scan at 17:00 Bangkok. Its canonical source is `/root/signalix/backend/update_data.service`; the deployed unit must be byte-identical. Daily path does **not** run full intraday; `signalix-intraday.service` owns 60m fetching. `ExecStartPost` runs `verify_mvp_only.py` against the canonical MVP artifact and latest Daily run.
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
- Shared drawer DOM mapping regression (2026-09-12): explicit mappings align `renderSharedDetail` with shared markup IDs (`drawer-provenance`, `drawer-52w`, `drawer-ath`). After dashboard recreate, public `/trend-map` and `/mvp` returned HTTP 200; served `shared-drawer.js` contains one `openSharedDrawer` and one `drawChart`; real headless click test opened shadow drawer for `ADVICE` and reached `Chart status: Confirmed candle · 2026-09-11`. No API, database, ingestion, publisher, `/mvp` semantics, alerts, or broker behavior changed.
- Shared drawer OHLCV table overflow fix (2026-09-12): the seven-column `OHLCV Window Summary` is now inside `.rolling-high-low__table-wrap`, which owns horizontal scrolling while the inner table keeps a readable minimum width; page-level horizontal overflow remains hidden. `/mvp` and shadow usage and product semantics are unchanged. Deployed and browser-verified at 390px: `innerWidth=390`, `bodyScrollWidth=390`, drawer visible, wrapper `clientWidth=348`, `scrollWidth=980`, `overflow-x=auto`.
- Closeout release (2026-09-12): commits `f18e48f` and `15701ef` are pushed to `release/signalix-mvp-stable`; remote SHA is `15701effad9d6549687740bf65af422a909d38af`. Dashboard was recreated from the release source and is healthy; public `/trend-map`, `/api/trend-map`, and `/mvp` read-back passed. Browser verification at 390px confirmed drawer/chart, bounded OHLCV scrolling, and MA control computed height `44px`; error→Retry→recovery returned 237 rows. The next scheduled EOD freshness/read-back after this release remains `NOT VERIFIED` and is not claimed here.
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
