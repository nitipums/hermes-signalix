# VCP-First Surface and Cadence Implementation Plan

> **For agentic workers:** Implement task-by-task with focused tests and review.

**Goal:** Make VCP Finder the primary Signalix surface, run it after successful/partial 60m ingestion, and present full-universe results through deterministic forming lanes and ordering.

**Architecture:** Preserve Daily Shortlist and Explorer as secondary routes; change only visible navigation/default landing. Extend the isolated VCP run contract with ingestion lineage and presentation fields. Use one explicit orchestration owner after ingestion commit; never trigger VCP from `ExecStopPost`.

**Tech Stack:** Python, psycopg2, PostgreSQL, systemd, vanilla JavaScript/CSS, pytest, browser CDP.

**Spec:** `docs/superpowers/specs/2026-08-25-vcp-finder-60m-design.md` plus approved 2026-08-26 VCP-first design in session.

## Global Constraints
- Full eligible TH ORD universe remains evaluated and retained.
- VCP uses completed/normalized 60m data only and never changes Daily state/evaluator.
- `READY` means wait for breakout, never buy; `EXTENDED` means DO NOT CHASE.
- Failed/skip ingestion must not create a new VCP run from stale rows.
- Existing Shortlist/Explorer routes remain available as secondary/audit surfaces.

### Task 1: VCP presentation contract
**Files:** Modify `backend/vcp_finder.py`, `backend/vcp_finder_db.py`; test `backend/test_vcp_finder.py` and `backend/test_vcp_finder_db.py`.
- Add deterministic `forming_group`: `maturing`, `early`, or `needs_work` from explicit trend/base/contraction/volume evidence.
- Add stable `state_rank`, `forming_rank`, `review_rank`, and `latest_closed_bar` fields.
- Add `ingestion_run_id`, `ingestion_status`, and `fetch_completed_at` to VCP run/result provenance.
- Sort persisted results by `(state_rank, forming_rank, freshness, distance policy, contraction quality, breakout volume, symbol)` while preserving full-universe counts.
- Test forming boundaries, stable tie-breaks, full retention, and JSON serialization.

### Task 2: Ingestion-to-VCP orchestration
**Files:** Create `backend/run_intraday_vcp_pipeline.py`; modify `backend/signalix-intraday.service`; tests `backend/test_vcp_orchestration.py`.
- Orchestrator calls the existing ingestion function, observes committed `full_success`/`partial_success`, then calls `find_vcp_universe_60m` with `as_of=fetch_completed_at` and persists the VCP run linked to the exact ingestion `run_id`.
- Run existing evaluator only after VCP persistence; rebuild existing Daily dashboard afterward.
- Do not run VCP on failed or outside-session skip; preserve prior latest valid VCP run.
- Add a lock preventing overlapping VCP runs.
- Replace the current service’s release-candidate path with `/root/signalix` and invoke the orchestrator after a successful/partial fetch, not via unconditional `ExecStopPost`.
- Tests cover full success, partial success, failed fetch, skip, lineage, lock, and no Daily mutation.

### Task 3: VCP-first navigation and cards
**Files:** Modify `backend/frontend/index.html`, `backend/frontend/app.js`, `backend/frontend/styles.css`; tests `backend/test_mvp_frontend_contract.py`.
- Make VCP the default active panel and first navigation tab.
- Keep Daily Shortlist as `Daily Setups` secondary and Explorer as `Research / Full Universe` secondary; preserve routes/API.
- Render VCP cards with shortlist-like decision hierarchy: identity, state/action, price/pivot/distance/invalidation, contractions, volume, freshness, feed, margin, drawer affordance.
- Add sections with counts: Confirmed, Near Trigger, Ready, Forming Maturing, Forming Early, Needs Work, Extended, Failed, Not Verified/Stale.
- Default view shows actionable + maturing/near candidates; collapsed lower-risk lanes remain reachable and full-universe count stays visible.
- Ensure cards use shared drawer and filtered Prev/Next; keep mobile single-column and no horizontal overflow.

### Task 4: Regression and served verification
**Files:** no additional production files unless a focused fix is required.
- Run focused VCP/frontend tests, full backend suite, JS syntax, and diff checks.
- Trigger one real orchestrator run or verify the latest linked run in PostgreSQL; reconcile ingestion→VCP row counts and lineage.
- Verify `/api/vcp-finder` default/filters and served public page.
- Browser test desktop and mobile: VCP first, forming sections, filters, card drawer, Prev/Next, error/empty/data-unavailable states, and no horizontal overflow.
- Run Ploy/Khim final review; remediate HIGH findings; commit only intended scope and report any stale unrelated tests separately.
