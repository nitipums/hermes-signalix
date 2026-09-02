# Unified VCP Decision Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 60m VCP Finder the single serving decision spine while exposing only `state`, `quality`, `decision`, and sufficient evidence to users.

**Architecture:** Preserve raw VCP, Daily, intraday, lifecycle, and shadow evidence. Add a pure projection boundary that maps the authoritative 60m VCP result plus supporting Daily context into one compact decision object. Migrate serving surfaces one at a time; legacy classifiers remain audit/compatibility inputs until each consumer is verified.

**Tech Stack:** Python 3.12, pandas, pytest, PostgreSQL adapters, existing JSON snapshot/API, Docker-served `/mvp` on port 3001 and backend readiness on port 8000.

**Spec:** `docs/superpowers/specs/2026-08-29-unified-vcp-decision-contract-design.md`

## Global Constraints

- `VCP Finder 60m` is authoritative for VCP morphology and setup state.
- Daily EOD is supporting context/lifecycle evidence and cannot promote a 60m result to `CONFIRMED`.
- Intraday observations cannot rewrite official Daily truth.
- `data_sufficient` is only `true|false`; stale, unverified, insufficient history, unavailable feed, and invalid OHLCV are one insufficient-data concept.
- Serving setup states are `FORMING`, `READY`, `CONFIRMED`, `EXTENDED`, `INVALIDATED`.
- Serving decisions are `REVIEW`, `WAIT`, `AVOID`; `EXTENDED` maps to `WAIT`.
- `quality=UNKNOWN` is reserved for insufficient data; `quality=FAIL` means evaluation completed and failed.
- No threshold changes, no LLM calculations, no alert changes, no auto-trading, no database migration, no deploy/restart in the pure-contract slice.
- Preserve full-universe retention, raw evidence, lifecycle history, removable filters, and rollback fields.
- Do not read, print, modify, stage, or commit secrets or the pre-existing `qa-artifacts/` directory.
- Lite owns final acceptance; worker PASS/self-report is not acceptance.

---

## File map and ownership

### Task 1 — Pure serving contract module

- **Create:** `backend/unified_vcp_decision.py`
- **Test:** `backend/test_unified_vcp_decision.py`
- Responsibility: no DB, no I/O, no mutation; map one VCP result and optional Daily context to the compact contract.

### Task 2 — Adapter at VCP projection boundary

- **Modify:** `backend/vcp_finder_db.py` at the result projection/serialization boundary (`_presentation_fields`, watchlist projection, and related helpers only)
- **Test:** `backend/test_vcp_finder_db.py` or a focused new adapter test
- Responsibility: attach the unified object while preserving current raw VCP fields and full-universe counts.

### Task 3 — API/snapshot contract propagation

- **Modify:** `backend/mvp_snapshot.py`, `backend/mvp_api.py`, `backend/mvp_routes.py` only where the canonical VCP payload is projected
- **Test:** `backend/test_vcp_finder_api.py`, `backend/test_mvp_snapshot.py`, `backend/test_mvp_artifact_contract.py`
- Responsibility: ensure Watchlist and Explorer consume the same decision object and filters remain presentation-only.

### Task 4 — UI primary vocabulary

- **Modify:** current VCP MVP template/static source identified by the served artifact path; do not touch retired Daily navigation except compatibility markers
- **Test:** existing frontend contract test plus a bounded rendered check
- Responsibility: show `STATE · DECISION` and concise trigger/invalidation evidence; remove competing primary labels without removing drawer/audit evidence.

### Task 5 — Legacy boundary/quarantine

- **Modify:** only verified serving call sites in `backend/daily_setup_state.py`, `backend/stage_classifier.py`, `backend/setup_state.py`, `backend/action_queue.py`, `backend/daily_shortlist.py`, or `backend/screening.py`; do not delete modules in this slice
- **Test:** focused regression tests for old consumers plus VCP API tests
- Responsibility: stop legacy systems from creating competing visible MVP decisions; retain compatibility fields and audit provenance.

### Task 6 — Runtime acceptance and documentation

- **Modify:** `vault/Execution-Pipeline.md`, `vault/VCP-Finder-MVP.md`, `vault/INDEX.md` only after live behavior is verified
- **Test/evidence:** public/served probes, API contract checks, desktop/mobile journey, error/insufficient-data path
- Responsibility: update current authority notes with actual evidence; explicitly report unverified paths.

---

## Task 1: Add the pure unified decision projection

**Interfaces:**

```python
def project_unified_vcp_decision(
    result: dict,
    daily_context: dict | None = None,
    *,
    data_sufficient: bool | None = None,
) -> dict:
    """Return one JSON-safe serving decision without mutating result."""
```

Produces exactly:

```python
{
    "state": str | None,
    "decision": str | None,
    "quality": "PASS" | "PARTIAL" | "FAIL" | "UNKNOWN",
    "data_sufficient": bool,
    "evidence": {
        "timeframe": "60m",
        "trigger": float | None,
        "invalidation": float | None,
        "distance_to_trigger_pct": float | None,
        "volume_confirmation": bool | None,
        "daily_context": dict,
    },
}
```

- [ ] **Step 1: Write failing pure mapping tests.** Cover `FORMING→WAIT`, `READY→WAIT`, `CONFIRMED→REVIEW`, `EXTENDED→WAIT`, `FAILED→AVOID`, and insufficient data producing `state=None`, `decision=None`, `quality=UNKNOWN`, `data_sufficient=False`.

```python
def test_extended_is_wait_not_avoid():
    result = project_unified_vcp_decision({
        "state": "EXTENDED",
        "data": {"freshness": "fresh", "feed_status": "ok"},
        "price": {"pivot_high": 10.0, "last_close": 11.0, "invalidation": 9.0},
        "evidence": {"prior_trend_pass": True, "price_contraction_pass": True,
                     "base_pass": True, "leg_volume_pass": True},
    })
    assert result["state"] == "EXTENDED"
    assert result["decision"] == "WAIT"
```

- [ ] **Step 2: Run the focused tests and confirm they fail because the module/function is absent.**

```bash
cd /root/signalix
pytest -q backend/test_unified_vcp_decision.py
```

Expected: collection/import failure for the new module.

- [ ] **Step 3: Implement the minimal pure mapper.** Use the existing VCP `state`, existing structural evidence, existing `price` fields, and explicit feed/freshness checks. Do not compute new indicators or mutate input. Treat any state in `{STALE, NOT_VERIFIED}` or missing usable data as insufficient and preserve raw reason only outside the compact decision object.

- [ ] **Step 4: Add quality tests.** Assert `PASS` requires existing 60m trend/morphology evidence; `PARTIAL` preserves event/partial morphology; `FAIL` means sufficient data plus failed structure; `UNKNOWN` means insufficient data. Assert Daily context never changes `CONFIRMED` to another state or promotes another state to `CONFIRMED`.

- [ ] **Step 5: Run focused tests and JSON smoke check.**

```bash
pytest -q backend/test_unified_vcp_decision.py
python - <<'PY'
import json, sys
sys.path.insert(0, 'backend')
from unified_vcp_decision import project_unified_vcp_decision
item = project_unified_vcp_decision({'state':'READY','data':{'freshness':'fresh','feed_status':'ok'},'price':{},'evidence':{}})
json.dumps(item)
print('json-safe')
PY
```

Expected: all focused tests pass and `json-safe` prints.

- [ ] **Step 6: Commit only Task 1 files.**

```bash
git add backend/unified_vcp_decision.py backend/test_unified_vcp_decision.py
git diff --cached --check
git commit -m "feat: add unified VCP decision projection"
```

## Task 2: Attach the contract without changing serving behavior

- [ ] **Step 1: Identify the exact VCP result projection boundary and current tests before editing.** Read `vcp_finder_db.py` around `_presentation_fields`, watchlist lane projection, and result serialization. Capture `git status --short` and do not normalize unrelated changes.
- [ ] **Step 2: Write adapter tests proving raw fields survive.** Feed representative VCP results for each state and assert `state`, `actionable`, `review_lane`, `pattern`, `breakout`, `provenance`, and existing lane fields remain unchanged while `decision` is added.
- [ ] **Step 3: Add the adapter call with explicit Daily context.** Use the already-loaded context only; do not add per-symbol DB fan-out. If context is absent, pass `{}` and preserve a neutral context object.
- [ ] **Step 4: Run focused VCP DB/projection tests and JSON serialization.**

```bash
pytest -q backend/test_unified_vcp_decision.py backend/test_vcp_finder_db.py backend/test_vcp_decision_policy.py
```

- [ ] **Step 5: Inspect the complete diff and commit the bounded adapter.**

## Task 3: Propagate one projection to API and snapshot surfaces

- [ ] **Step 1: Write contract tests for `/api/vcp-finder` projection helpers.** Assert Watchlist and Explorer use identical decision fields for the same result; state filters and presentation caps do not mutate the raw state.
- [ ] **Step 2: Add the smallest propagation change.** Do not re-run scans from an API request, do not change default filters, and do not expose `STALE`/`NOT_VERIFIED` as competing primary setup labels.
- [ ] **Step 3: Test full-universe retention.** Assert insufficient rows remain in audit/full result counts but are not review candidates; assert removable liquidity/margin/price filters affect visible output only.
- [ ] **Step 4: Run focused API/snapshot tests and `git diff --check`.**

```bash
pytest -q backend/test_vcp_finder_api.py backend/test_mvp_snapshot.py backend/test_mvp_artifact_contract.py
python -m py_compile backend/mvp_snapshot.py backend/mvp_api.py backend/mvp_routes.py
```

- [ ] **Step 5: Commit the API/snapshot slice.**

## Task 4: Replace primary UI vocabulary

- [ ] **Step 1: Inspect the actual current `/mvp` template/static path and existing frontend tests.** Do not assume the retired dashboard path is still served.
- [ ] **Step 2: Add source-level tests for primary copy.** Assert a representative card can render `FORMING · WAIT`, `READY · WAIT`, `CONFIRMED · REVIEW`, `EXTENDED · WAIT`, and `INVALIDATED · AVOID`; assert legacy labels are not primary card status.
- [ ] **Step 3: Implement the smallest rendering change.** Keep trigger, invalidation, provenance, raw drawer evidence, and current table contract. Do not remove evidence fields to simplify the visible label.
- [ ] **Step 4: Run frontend contract tests and served artifact checks.**
- [ ] **Step 5: Perform public-route desktop/mobile check.** Record URL, viewport metrics, screenshot, and one insufficient/error path. Localhost is diagnostic fallback only.
- [ ] **Step 6: Commit only the UI slice after Lite review.**

## Task 5: Quarantine competing legacy decisions

- [ ] **Step 1: Produce a call-site inventory before edits.** Search for all serving consumers of `trade_readiness.status`, `classify_daily_state`, `classify_stage`, `setup_proximity`, `assign_action_queue`, and old shortlist lane output.
- [ ] **Step 2: Add regression tests for one-symbol single-decision behavior.** A sufficient VCP item must expose one serving decision; legacy fields may remain under compatibility/audit keys but cannot override it.
- [ ] **Step 3: Remove only visible-serving conflicts.** Do not delete legacy modules, alter thresholds, or rewrite lifecycle history. Route the VCP MVP through the unified projection; leave non-MVP rollback/audit paths explicitly marked.
- [ ] **Step 4: Run affected unit tests and call-site consistency checks.**

```bash
pytest -q backend/test_vcp_finder.py backend/test_vcp_finder_db.py backend/test_vcp_finder_api.py backend/test_mvp_snapshot.py backend/test_mvp_frontend_contract.py backend/test_mvp_watch_lanes.py
```

- [ ] **Step 5: Commit the quarantine slice only after diff review.**

## Task 6: Runtime acceptance and current-doc update

- [ ] **Step 1: Verify source/compose topology and capture pre-change runtime evidence.** Do not restart or deploy until the exact scope is approved; distinguish source, container, DB, and served artifact.
- [ ] **Step 2: Run the canonical focused tests plus syntax checks.** If pytest has the temporary-directory failure, repair only the test environment or report the blocker; never claim green from deselection.
- [ ] **Step 3: Verify served public route first.** Check `/mvp`, `/api/vcp-finder?...daily_watchlist=true`, `/health/readiness`, full-universe metadata, state/decision uniqueness, filters, and an insufficient-data path.
- [ ] **Step 4: Verify desktop/mobile user journey and one failure/error state.** Capture actual rendered evidence; endpoint/source checks alone are not visual acceptance.
- [ ] **Step 5: Update `vault/Execution-Pipeline.md` and `vault/VCP-Finder-MVP.md` with only verified behavior.** Keep `Scan-Evaluation-Logic-Map-2026-08-29.md` as historical/review context unless the owner asks to promote it.
- [ ] **Step 6: Run final `git diff --check`, inspect complete diff, and report PASS/FAIL/NOT VERIFIED with exact evidence.**
