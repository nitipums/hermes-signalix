# Elliott/Trend/Trade-Setup Decision Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the VCP-first serving decision with a deterministic Trend + Elliott-candidate + Trade-Setup contract served by `/api/setup-candidates` and rendered by `/mvp`.

**Architecture:** Add focused pure-function engines for Daily trend/strength, conservative Elliott structural candidates, and 60m trade setups. Compose them into one versioned candidate contract; retain VCP as bonus evidence and leave `/api/vcp-finder` as legacy/audit only. Preserve raw observations and provenance while removing competing legacy labels from the primary surface.

**Tech Stack:** Python 3.12, pandas, existing stdlib HTTP/FastAPI-compatible MVP route layer, pytest/unittest, vanilla HTML/CSS/JavaScript frontend, existing Signalix PostgreSQL/data loaders.

**Spec:** `docs/superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md`

## Global Constraints

- Daily is authoritative for big-picture trend and Elliott structural candidates.
- 60m is used for early Wave 3 confirmation, lower-timeframe structure, trigger, and entry timing.
- `wave.state` may contain only `WAVE_1_ADVANCE`, `WAVE_2_FORMING`, `WAVE_2_NEAR_COMPLETION`, `EARLY_WAVE_3`, `WAVE_3_CONTINUATION`, `WAVE_4_CORRECTION`, `WAVE_5_ADVANCE`, or `UNKNOWN`.
- `INVALIDATED` and `EXTENDED` are setup/risk statuses, not Elliott states.
- Elliott v1 uses conservative observable proxy evidence and never claims an objective Elliott count.
- Trend/strength must expose rise, RS, 52W High, and ATH evidence explicitly.
- Sector/industry peer context is evidence/ranking context, not an automatic exclusion gate.
- VCP is bonus evidence and must not be a hard candidate gate.
- User-facing decisions are `REVIEW`, `WAIT`, `AVOID`, and `DATA_BLOCKED`; no automatic BUY or executable order.
- Missing, stale, invalid, or insufficient data must fail closed into explicit unknown/blocked evidence.
- Deterministic code owns calculations, states, risk, stops, targets, R:R, and provenance; LLMs are not used for these values.
- Preserve existing raw data and historical observations; do not delete or rewrite legacy observations.
- Work only in the Signalix checkout; never touch the pre-existing untracked `Trade Reference ` directory.
- No Docker restart, database migration/write, deploy, push, or live-order action is part of the implementation tasks without separate explicit scope.

---

### Task 1: Build the pure Trend/Strength and Elliott candidate engines

**Files:**
- Create: `backend/trend_strength_engine.py`
- Create: `backend/elliott_structure_engine.py`
- Create: `backend/test_elliott_setup_engine.py`
- Reference: `backend/signal_core.py`, `backend/screening.py`, `backend/stage_classifier.py`

**Interfaces:**
- Consumes: Daily OHLCV pandas DataFrame and existing calculated trend/RS/52W/ATH evidence where available.
- Produces: JSON-safe dictionaries with `trend` and `wave` groups used by later tasks.

- [ ] **Step 1: Write failing tests for observable trend evidence.**

Add fixtures covering rising, flat, falling, near-52W-high, 52W-high breakout, ATH breakout, and insufficient history. Assert that output contains explicit `state`, `rise_20d_pct`, `rise_60d_pct`, `relative_strength`, `near_52w_high`, `is_52w_high_breakout`, and `is_ath_breakout`; do not assert an invented hard threshold for “strong” unless it already exists in the canonical source.

```python
def test_trend_exposes_high_and_strength_evidence():
    result = compute_trend_strength(rising_daily_frame(), relative_strength=91.0)
    assert result["state"] in {"uptrend", "emerging_uptrend"}
    assert result["relative_strength"] == 91.0
    assert "near_52w_high" in result
    assert "is_52w_high_breakout" in result
    assert "is_ath_breakout" in result
```

- [ ] **Step 2: Run the focused test and verify RED.**

Run: `cd /root/signalix/backend && pytest -q test_elliott_setup_engine.py -k trend`

Expected: FAIL because the new module/functions do not exist.

- [ ] **Step 3: Implement the minimum trend/strength functions.**

Implement:

```python
def compute_trend_strength(
    daily_df: pd.DataFrame,
    relative_strength: float | None = None,
    prior_ath: float | None = None,
) -> dict:
    """Return Daily trend/strength evidence; never silently drop unknown inputs."""
```

Reuse existing Daily calculations rather than duplicating formulas. Calculate 20/60-session percentage changes only when enough rows exist; return `None` for unavailable metrics. Compare the latest close with the rolling 52-week high and all-time high using explicit booleans. Return plain Python numbers.

- [ ] **Step 4: Write failing tests for Wave 1–5 candidate states.**

Use deterministic synthetic Daily fixtures with explicit prior advance, pullback, duration, confirmed swing anchors, Fib zone, and intact/broken structure. Assert Wave 1, Wave 2, Early Wave 3, Wave 3 continuation, Wave 4, and Wave 5 candidates. Assert that no result has `wave["state"]` equal to `INVALIDATED` or `EXTENDED`; those words may occur only in separate setup fields in later tasks.

```python
def test_wave_candidate_is_structural_only():
    result = classify_wave_candidate(wave_two_fixture())
    assert result["state"] in {
        "WAVE_2_FORMING", "WAVE_2_NEAR_COMPLETION", "EARLY_WAVE_3"
    }
    assert result["state"] not in {"INVALIDATED", "EXTENDED"}
    assert "evidence" in result
```

- [ ] **Step 5: Run the Wave tests and verify RED.**

Run: `cd /root/signalix/backend && pytest -q test_elliott_setup_engine.py -k wave`

Expected: FAIL because `classify_wave_candidate` does not exist.

- [ ] **Step 6: Implement conservative observable Wave classification.**

Implement:

```python
def classify_wave_candidate(
    daily_df: pd.DataFrame,
    swing_evidence: dict | None = None,
) -> dict:
    """Return a cautious structural candidate, never an authoritative wave count."""
```

Use confirmed observable swing/advance/pullback evidence and Fib/duration fields. Do not introduce a hidden score or a new hard filter. When evidence is incomplete, return `UNKNOWN` with explicit missing evidence. Keep all evidence in the returned dictionary so Arm can review the chart.

- [ ] **Step 7: Run all Task 1 tests and commit.**

Run: `cd /root/signalix/backend && pytest -q test_elliott_setup_engine.py`

Expected: PASS.

```bash
git add backend/trend_strength_engine.py backend/elliott_structure_engine.py backend/test_elliott_setup_engine.py
git commit -m "feat: add trend and Elliott candidate engines"
```

---

### Task 2: Build the 60m trade-setup and risk contract adapter

**Files:**
- Create: `backend/trade_setup_engine.py`
- Modify: `backend/risk_stop_target.py` only where a compatible adapter is required
- Create/Modify: `backend/test_elliott_setup_engine.py`
- Reference: `backend/risk_stop_target.py`

**Interfaces:**
- Consumes: Daily wave evidence, 60m OHLCV, and existing deterministic Fib/risk helpers.
- Produces: `setup` dictionary with trigger, entry zone, invalidation, targets, R:R, status, and 60m provenance.

- [ ] **Step 1: Write failing tests for Early Wave 3 setup preparation.**

```python
def test_early_wave_three_setup_has_trigger_stop_targets_and_rr():
    result = build_trade_setup(daily_wave_two_evidence(), rising_60m_frame())
    assert result["timeframe"] == "60m"
    assert result["state"] == "EARLY_WAVE_3"
    assert result["trigger"] is not None
    assert result["invalidation"] is not None
    assert result["targets"]
    assert result["rr"]["to_target_1"] >= 0
```

Add tests for Wave-2 waiting setup, Wave-3 continuation, extended price, invalidation breach, missing 60m data, and JSON serialization. Assert `EXTENDED` and `INVALIDATED` occur in `setup["status"]`, never in `wave["state"]`.

- [ ] **Step 2: Run focused tests and verify RED.**

Run: `cd /root/signalix/backend && pytest -q test_elliott_setup_engine.py -k setup`

Expected: FAIL because `build_trade_setup` does not exist.

- [ ] **Step 3: Implement the setup builder.**

Implement:

```python
def build_trade_setup(
    daily_wave: dict,
    intraday_df: pd.DataFrame | None,
    *,
    risk_helper=risk_stop_target,
) -> dict:
    """Prepare, but never authorize, a 60m trade setup."""
```

Use existing `risk_stop_target.compute_fib_targets` and compatible stop logic instead of creating a second Fib formula. Derive trigger from the lower-timeframe structural breakout evidence, invalidation from the relevant structural low, and targets from explicit Fib anchors. Calculate R:R as reward divided by positive risk; return `None`/`DATA_BLOCKED` when anchors are invalid. Use the agreed bands only for display metadata: minimum interesting 1:3, preferred 1:4–1:5, exceptional 1:8–1:10.

- [ ] **Step 4: Add setup status and decision mapping tests.**

```python
def test_extended_is_setup_status_not_wave_state():
    result = build_trade_setup(daily_wave_two_evidence(), extended_60m_frame())
    assert result["status"] == "EXTENDED"
    assert result["state"] != "EXTENDED"
```

- [ ] **Step 5: Run risk regression tests and focused tests.**

Run: `cd /root/signalix/backend && pytest -q test_risk_stop_target.py test_elliott_setup_engine.py`

Expected: all existing risk tests and new setup tests PASS.

- [ ] **Step 6: Commit the setup engine.**

```bash
git add backend/trade_setup_engine.py backend/risk_stop_target.py backend/test_elliott_setup_engine.py
git commit -m "feat: prepare Elliott trade setups with risk evidence"
```

---

### Task 3: Compose the canonical candidate contract and peer context

**Files:**
- Create: `backend/setup_candidate_contract.py`
- Create: `backend/test_setup_candidate_contract.py`
- Modify: `backend/screening.py` only to expose a bounded adapter for existing data loading
- Reference: `backend/vcp_finder_db.py`, `backend/mvp_api.py`, `backend/risk_stop_target.py`

**Interfaces:**
- Consumes: trend output, wave output, setup output, sector/industry peer data, VCP evidence, and provenance.
- Produces: one JSON-safe item matching the approved spec and one list-level projection.

- [ ] **Step 1: Write failing contract tests.**

Assert top-level keys `symbol`, `as_of`, `data_status`, `trend`, `wave`, `setup`, `context`, `bonus_evidence`, `decision`, and `provenance`. Assert Daily/60m timeframes are explicit, VCP is nested under bonus evidence, and all numeric values are plain `int`/`float`/`None`.

```python
def test_candidate_contract_keeps_layers_separate():
    item = build_setup_candidate(**sample_inputs())
    assert set(("trend", "wave", "setup", "context", "bonus_evidence")) <= item.keys()
    assert item["wave"]["timeframe"] == "daily"
    assert item["setup"]["timeframe"] == "60m"
    json.dumps(item)
```

- [ ] **Step 2: Add peer-context tests.**

Test sector/industry, peer breadth, breakout count, leader/laggard, and missing-peer behavior. Assert missing peer data is represented explicitly and never excludes the symbol.

- [ ] **Step 3: Implement the contract builder.**

Implement:

```python
def build_setup_candidate(
    symbol: str,
    as_of: str,
    data_status: dict,
    trend: dict,
    wave: dict,
    setup: dict,
    context: dict,
    bonus_evidence: dict,
    provenance: dict,
) -> dict:
    """Build the single canonical setup-candidate item."""
```

Map decision deterministically: insufficient/stale/invalid evidence to `DATA_BLOCKED`; valid but not ready to `WAIT`; valid review-worthy setup to `REVIEW`; explicit failed structure or unacceptable risk to `AVOID`. Do not use VCP presence as the decision gate.

- [ ] **Step 4: Add bounded universe adapter tests.**

Verify the adapter preserves every evaluated Thai ORD row, including unknown/insufficient rows, and does not apply VCP-only filtering. Use mocks for DB access; do not write production data.

- [ ] **Step 5: Run focused contract and existing screening tests.**

Run: `cd /root/signalix/backend && pytest -q test_setup_candidate_contract.py test_screening.py -m 'not integration'`

Expected: PASS for pure/contract tests; integration tests remain separately labelled.

- [ ] **Step 6: Commit the canonical contract.**

```bash
git add backend/setup_candidate_contract.py backend/test_setup_candidate_contract.py backend/screening.py
git commit -m "feat: define canonical setup candidate contract"
```

---

### Task 4: Serve `/api/setup-candidates` and make `/mvp` use it

**Files:**
- Modify: `backend/mvp_routes.py`
- Modify: `backend/mvp_api.py`
- Create: `backend/test_setup_candidates_api.py`
- Modify: `backend/frontend/app.js`
- Modify: `backend/frontend/index.html`
- Modify: `backend/frontend/styles.css`
- Modify: `backend/test_mvp_frontend_contract.py`

**Interfaces:**
- Consumes: canonical candidate list from Task 3.
- Produces: HTTP JSON route `/api/setup-candidates` and primary `/mvp` candidate view; legacy VCP route remains callable only for audit.

- [ ] **Step 1: Write failing API and frontend contract tests.**

Test route shape, explicit data-blocked behavior, no VCP-only filtering, and that the primary frontend requests `/api/setup-candidates` rather than `/api/vcp-finder`.

```python
def test_setup_candidates_route_returns_canonical_items(client):
    response = client.get("/api/setup-candidates")
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["trend"]
    assert payload["items"][0]["wave"]
    assert payload["items"][0]["setup"]
```

- [ ] **Step 2: Run tests and verify RED.**

Run: `cd /root/signalix/backend && pytest -q test_setup_candidates_api.py test_mvp_frontend_contract.py`

Expected: FAIL because the new route and frontend request do not exist.

- [ ] **Step 3: Implement the route with explicit filters.**

Add `/api/setup-candidates` to the existing route dispatcher. Accept only presentation filters that do not alter backend coverage: lifecycle/state, sector, search, and pagination. Return metadata for `as_of`, policy version, universe, counts, and freshness. Keep `/api/vcp-finder` unchanged as an audit route and do not call it from the default MVP path.

- [ ] **Step 4: Implement the MVP data request and card rendering.**

Replace the primary request path in `app.js` with `/api/setup-candidates`. Render:

```text
Trend + strength + 52W/ATH
Wave candidate + evidence
Setup state + trigger + invalidation
Targets + R:R
Market + sector/peer context
VCP bonus evidence
Review/Wait/Avoid/Data blocked
```

Keep unknown, empty-success, and transport-error states distinct. Preserve chart/drill-down behavior through the new symbol contract.

- [ ] **Step 5: Add responsive and failure-state assertions.**

Update frontend tests for the new endpoint and vocabulary. Ensure cards remain usable at 390px, and the failure message does not present an unavailable API as an empty candidate list.

- [ ] **Step 6: Run focused API/frontend tests.**

Run: `cd /root/signalix/backend && pytest -q test_setup_candidates_api.py test_mvp_frontend_contract.py test_mvp_artifact_contract.py`

Expected: PASS.

- [ ] **Step 7: Commit the serving slice.**

```bash
git add backend/mvp_routes.py backend/mvp_api.py backend/test_setup_candidates_api.py backend/frontend/app.js backend/frontend/index.html backend/frontend/styles.css backend/test_mvp_frontend_contract.py
git commit -m "feat: serve Elliott setup candidates in MVP"
```

---

### Task 5: Retire competing primary labels and preserve legacy audit data

**Files:**
- Modify: `backend/mvp_snapshot.py`
- Modify: `backend/reconciled_projection.py` only if the new contract is stripped
- Modify: `backend/test_signalix_contracts.py`
- Modify: `backend/test_mvp_artifact_contract.py`
- Modify: `vault/Execution-Pipeline.md` only after runtime behavior is verified
- Modify: `vault/Scan-Evaluation-Logic-Map-2026-08-29.md` only after runtime behavior is verified

**Interfaces:**
- Consumes: the canonical setup-candidate item.
- Produces: one primary visible contract without silently deleting legacy/raw evidence.

- [ ] **Step 1: Write failing migration-boundary tests.**

Assert `/mvp` primary items contain no competing VCP lane/legacy action as the primary decision; assert raw VCP evidence is nested under `bonus_evidence`; assert historical/raw fields remain available to audit code.

- [ ] **Step 2: Implement projection boundary.**

Make snapshot/projection pass through the new contract without introducing a second label. Keep legacy route and raw evidence readable, but exclude legacy state from primary card decision rendering. Do not delete database rows or rewrite prior observations.

- [ ] **Step 3: Run contract regressions.**

Run: `cd /root/signalix/backend && pytest -q test_signalix_contracts.py test_mvp_artifact_contract.py test_setup_candidate_contract.py`

Expected: PASS.

- [ ] **Step 4: Commit the boundary cleanup.**

```bash
git add backend/mvp_snapshot.py backend/reconciled_projection.py backend/test_signalix_contracts.py backend/test_mvp_artifact_contract.py vault/Execution-Pipeline.md vault/Scan-Evaluation-Logic-Map-2026-08-29.md
git commit -m "refactor: make setup candidate the primary decision contract"
```

---

### Task 6: Run full verification and public-surface acceptance

**Files:**
- No source changes unless a focused test exposes a defect; any fix gets its own commit.
- Evidence artifacts: `/tmp` or an explicitly approved Signalix artifact path, never secrets.

- [ ] **Step 1: Run focused pure-function and contract tests.**

```bash
cd /root/signalix/backend
pytest -q test_elliott_setup_engine.py test_risk_stop_target.py test_setup_candidate_contract.py test_setup_candidates_api.py
```

- [ ] **Step 2: Run relevant regression tests.**

```bash
cd /root/signalix/backend
pytest -q test_screening.py test_signalix_contracts.py test_mvp_artifact_contract.py test_mvp_frontend_contract.py
```

- [ ] **Step 3: Run syntax and diff checks.**

```bash
python3 -m py_compile trend_strength_engine.py elliott_structure_engine.py trade_setup_engine.py setup_candidate_contract.py mvp_routes.py mvp_api.py
cd /root/signalix
git diff --check
git status --short --branch
```

Confirm the pre-existing `Trade Reference ` directory remains untouched.

- [ ] **Step 4: Verify the served API and readiness route.**

Probe the public/approved Signalix route, not only source code:

```bash
curl -fsS http://127.0.0.1:8000/health/readiness
curl -fsS 'http://127.0.0.1:3001/api/setup-candidates'
curl -fsS http://127.0.0.1:3001/mvp
```

Record HTTP status, item counts, policy version, and whether the served source matches the release checkout. Do not claim PASS if the runtime is stale or unavailable.

- [ ] **Step 5: Verify desktop, mobile, and failure journey.**

Use the browser/public URL acceptance flow to verify:

1. candidate list loads;
2. Trend/strength/52W/ATH evidence is visible;
3. Wave candidate and evidence are visible;
4. trigger/invalidation/targets/R:R are visible;
5. sector/peer context and VCP bonus are distinguishable;
6. `DATA_BLOCKED` and empty-success states are distinct;
7. transport/API failure state is exercised;
8. layout has no horizontal overflow at 390px.

- [ ] **Step 6: Final review and status.**

Inspect the complete diff, verify no unrelated changes, report exact commands/results, runtime/deployment status, remaining `NOT VERIFIED` items, and final `PASS`/`FAIL`/`NOT VERIFIED`. Do not call the work complete from unit tests alone.
