# Serve Decision v2 on Marginable Long Dashboard — Implementation Plan

> **STATUS: COMPLETE WITH PERFORMANCE FOLLOW-UP** · Closeout: `vault/2026-08-30-Signalix-V2-Marginable-Serving-Closeout.md`

> **Owner approval:** Arm, 2026-08-30. This plan changes the current served dashboard decision contract and default operational universe.

**Goal:** Serve the v2 decision projection on the real MVP dashboard with `marginable_long` (237 `can_buy=true` active Thai ORD symbols) as the default universe, without enabling alerts or auto-trading.

**Architecture:** The live 60m VCP run remains the source of observed morphology and raw lifecycle evidence. The pure `signalix/vcp-decision-shadow-v2` projection is applied at the serving boundary to each selected live result; replay history is never served as current data. The API reports the selected universe/filter and margin provenance, while an explicit `active_ord` mode remains available for audit/rollback.

**Spec:** `docs/superpowers/specs/2026-08-30-marginable-long-replay-design.md` plus owner decision in chat.

## Global constraints

- Default served universe is active Thai ORD ∩ `signalix.marginable.v1` ∩ `can_buy=true` = 237.
- Current margin dataset effective date is 2026-08-25; active ORD base count is 931 and excluded count is 694.
- v2 policy version is `signalix/vcp-decision-shadow-v2`; it must be applied from live VCP results, not historical replay rows.
- Preserve v1 raw morphology fields for audit; v2 decision/lane/actionability is the decision-facing projection.
- Daily context cannot promote 60m lifecycle state; `BREAKOUT_WATCH` remains watch-only; Low-Cheat remains non-promoting.
- No alerts, automatic orders, threshold changes, replay expansion, or symbol_master status mutation.
- Every unknown/stale/unavailable state remains explicit; no permissive zero fallback.

### Task 1: Backend serving projection and universe boundary

**Files:** `backend/vcp_finder_db.py`, `backend/mvp_routes.py`, focused VCP DB/API tests.

- Add an explicit `universe` query mode with default `marginable_long` and audit override `active_ord`; reject unknown modes.
- Resolve selected symbols using `eligible_symbols(active_ord_symbols(pg), "marginable_long")` and filter the live run result set by that explicit list before presentation enrichment.
- Apply `project_vcp_decision_shadow` to live results after required Daily metrics and margin permissions are present; retain raw v1 fields and add `decision_shadow_v2`, `policy_version`, lane, and actionability fields without silently replacing evidence.
- Return `universe_filter`, `base_active_ord_count`, `eligible_count`, `excluded_count`, margin schema/source/effective date, and decision policy version in the response.
- Set returned/evaluated counts to the selected scope (237 by default); keep `active_ord` explicit for rollback/audit.
- Add tests for default 237 filtering, active_ord override, invalid mode, v2 projection, provenance, and no replay-row serving.

### Task 2: Frontend contract

**Files:** `backend/frontend/app.js`, `backend/frontend/index.html`, `backend/frontend/styles.css`, frontend contract tests.

- Label the dashboard as the current marginable-long operational universe and show selected count/filter/source effective date.
- Ensure watchlist and All VCP requests use the default marginable-long mode and render v2 lane/actionability labels.
- Preserve explicit empty/error states and do not hide data as if the universe were empty.
- Add source/contract tests for request query, v2 fields, scope metadata, and mobile layout markers.

### Task 3: Runtime verification and handoff

- Run focused and relevant regression tests, compile checks, and diff checks.
- Recreate/reload only the affected serving containers using the approved Compose path; do not restart delivery/alerts.
- Verify `/mvp`, `/api/vcp-finder`, `/api/vcp-finder?daily_watchlist=true`, readiness, and retired route behavior.
- Verify default API counts are 237 and `active_ord` audit mode remains 931 where applicable.
- Exercise dashboard happy path, empty/error path, and 390px layout via the real served route; collect exact evidence for Lite final gate.

## Acceptance

- [x] Default served API/UI uses `marginable_long`, 237 eligible symbols, and v2 decision policy.
- [x] Live `full_success` run provenance is preserved; replay rows are not served as current data.
- [x] V2 lane/actionability is visible and consistent with raw evidence; Daily context cannot promote 60m state.
- [x] Explicit `active_ord` audit mode works and is not the default.
- [x] Alerts remain paused and no auto-trade path changes.
- [x] Focused/full relevant tests pass; served API/UI and failure state are verified.
- [x] Ploy challenge is recorded after live dashboard verification; Lite final gate is PASS with cold API latency follow-up.
