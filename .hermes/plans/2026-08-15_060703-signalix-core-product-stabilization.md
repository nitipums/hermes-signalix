# Signalix Core Product Stabilization Implementation Plan

> **For Hermes:** Execute one task at a time; Bee performs the final evidence gate after each completed slice.

**Goal:** Make Signalix’s public Thai/US scanner a fast, trustworthy setup-to-decision workflow before adding post generation, fundamentals/news, portfolio expansion, or broad market-portal features.

**Architecture:** Keep the persisted Daily scan artifact as the first-paint source. Use small market-scoped metadata endpoints for freshness and lazy per-symbol APIs for chart/detail. Extend compact card fields from deterministic scan output rather than reintroducing per-symbol history/profile queries across the market.

**Tech stack:** Python/FastAPI, PostgreSQL, static HTML/JavaScript dashboard, Docker Compose, pytest, browser verification.

---

## Scope and constraints

- Product contract: **Verified data → Daily official setup state → trigger/invalidation/proof → review or alert → outcome evidence**.
- Daily EOD owns official state; intraday creates append-only emerging events only.
- Thai and US share the scanner contract but remain market-scoped for data and charts.
- No P1 Post Draft Generator, fundamental/news ingestion, broad content hub, paper portfolio work, live execution, or public/private portfolio mixing.
- A page must show persisted cards immediately if background refresh fails.
- Do not treat missing deferred enrichment as zero, low liquidity, or a false signal.

## Task 1: Lock the compact overview contract

**Objective:** Define the minimum deterministic fields required for a useful first paint without DB fan-out.

**Files:**
- Modify: `backend/build_dashboard.py`
- Modify: `backend/app.py`
- Create/modify: `backend/test_progressive_dashboard.py`

**Steps:**
1. Write RED tests for a persisted Daily card containing symbol, market, state, EOD close/date, trigger/reference, invalidation/failure level, scan time, data source/freshness state, and explicit unknown optional fields.
2. Run `docker exec signalix_backend python -m pytest -q test_progressive_dashboard.py`; observe failure.
3. Serialize only deterministic fields already present in `scan_results.json`; do not query chart/profile/history for all symbols.
4. Keep liquidity as `unknown` when absent rather than filtering a card out. Show unknown honestly in the UI.
5. Run the focused test and existing dashboard/screening regressions.

**Acceptance:** Browser first paint renders cards; `/dashboard/snapshot` remains bounded and metadata-only; an unknown liquidity field cannot hide all cards.

## Task 2: Make provenance and freshness unambiguous

**Objective:** Separate `data_fetched_at`, market/as-of date, scan time, and page build time throughout the public path.

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/build_dashboard.py`
- Test: `backend/test_progressive_dashboard.py` and relevant contract tests

**Steps:**
1. Write fixtures where a candle date is older than a successful fetch timestamp.
2. Assert the UI/header uses the successful fetch timestamp only for “latest fetched”; candle/as-of date is labelled separately.
3. Return `unknown`/`stale` instead of silently substituting another timestamp.
4. Verify Thai and US show market-specific source-quality labels.

**Acceptance:** One canonical freshness meaning per response; no duplicate/conflicting fetch timestamps; mobile UI labels the value and Bangkok timezone clearly.

## Task 3: Active ORD instrument master discovery and contract

**Objective:** Establish authoritative active Thai ordinary-share metadata without guessed coverage.

**Files:**
- Create/modify: `backend/instruments.py` or a narrowly scoped equivalent
- Create: `backend/test_instruments.py`
- Add schema/migration only after backup and an explicit reviewable migration plan

**Steps:**
1. Identify the authoritative source and fields; record source/fetch timestamp/status.
2. Write RED contract tests for active status, symbol, venue, asset class, currency, timezone, session, and source provenance.
3. Implement a rerun-safe refresh path limited to active `ORD` instruments.
4. Verify missing/failed metadata stays unknown and does not enter deterministic signal calculations.

**Acceptance:** No hidden 7,000-symbol metadata fan-out; cards/detail can show identity/context when available with an honest pending state otherwise.

## Task 4: Persist intraday emerging-event ledger

**Objective:** Stop any conceptual or data-level overwrite of official Daily state.

**Files:**
- Modify: `backend/intraday_evaluator.py` and persistence layer after inspection
- Create: `backend/test_intraday_event_ledger.py`
- Modify: `backend/app.py` only for a read-only event endpoint if needed

**Steps:**
1. Write RED test showing an intraday break creates an event tied to its latest Daily scan baseline but cannot mutate that Daily snapshot.
2. Persist timestamp, observed price/candle, trigger, invalidation reference, data freshness, reason, confidence, and baseline scan identity.
3. Record false/emerging breaks as events, not confirmed Daily breakouts.
4. Run the intraday and scan-history suite.

**Acceptance:** Raw Daily scan remains immutable; intraday evidence is queryable and explicitly lower confidence until EOD reconciliation.

## Task 5: EOD reconciliation and three-dimensional criteria

**Objective:** Make action eligibility explainable and independent from generic display groups.

**Files:**
- Modify: `backend/screening.py`
- Create/modify: `backend/test_universal_scanning.py`, `backend/test_scan_history_integration.py`, new focused criteria tests

**Steps:**
1. Write RED fixtures for a CBG-style emerging move, a HANA-style fresh confirmation, a valid retest, and a low-quality/monitor case.
2. Add deterministic dimensions: `setup_quality`, `event_timing`, and `entry_action`.
3. Make full EOD scan reconcile earlier intraday events as confirmed, expired, invalidated, or not confirmed.
4. Persist criteria inputs/version/reasons alongside the immutable observation.

**Acceptance:** Monitor/recovery/weak/low-entry-quality names cannot dominate an actionable queue; UI work begins only after data contracts pass.

## Verification checklist after each task

1. Run focused RED → GREEN tests and relevant regressions in `signalix_backend`.
2. Measure overview API separately from one chart/detail call.
3. Rebuild `dashboard.html`; inspect served browser UI on mobile-sized viewport.
4. Confirm Thai/English labels, source/freshness, retained cards on error, and lazy chart behavior.
5. Record exact files, commands/output, deployment status, limitations, and Bee final-gate verdict in [[Execution-Pipeline]].
