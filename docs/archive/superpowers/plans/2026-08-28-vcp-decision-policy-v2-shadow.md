# Signalix VCP Decision Policy v2 Shadow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct VCP data/replay contracts and add a non-serving three-lane v2 shadow projection without changing served v1 behavior.

**Architecture:** Extract deterministic Daily series assembly and point-in-time projection inputs, correct entry-aware replay evaluation, expose candidate pivot-sequence diagnostics, then project existing finder results through a pure versioned shadow policy. Persist shadow fields only inside replay result JSON and optional analysis output; do not alter the live v1 API response contract or deployment.

**Tech Stack:** Python 3.12, pandas, psycopg2, pytest-style tests executed through a disposable venv, PostgreSQL 16.

**Spec:** `docs/superpowers/specs/2026-08-28-vcp-decision-policy-v2-shadow-design.md`

## Global Constraints

- Work only on `release/signalix-mvp-stable`; inspect worktree before each commit.
- Preserve one result per active Thai ORD symbol and all append-only run lineage.
- No Docker rebuild/deploy, no alert changes, no mutation of served v1 policy.
- Deterministic code owns state, evidence, projection, and outcomes; no LLM calculation.
- Point-in-time reads must use rows at or before `as_of`.
- Missing data remains explicit; no guessed fundamentals, targets, or ratios.
- Use TDD and focused tests before regression tests.

---

### Task 1: Deterministic Daily Context and Metrics

**Files:**
- Modify: `backend/vcp_finder_db.py:82-131`
- Modify: `backend/test_vcp_finder_db.py`

**Interfaces:**
- Produces: `_daily_context_from_rows(rows: list[dict]) -> dict` and `_daily_metrics_from_rows(rows: list[dict]) -> dict`.
- `load_daily_trend_context()` and `load_daily_metrics()` consume rows ordered by `symbol, date ASC` and delegate to these pure functions.

- [ ] **Step 1: Write failing tests**

Add tests that pass deliberately shuffled rows and assert chronological output:

```python
def test_daily_metrics_latest_close_is_newest_independent_of_input_order():
    rows = [
        {"date": date(2026, 8, 27), "close": 47.0, "volume": 10},
        {"date": date(2026, 8, 25), "close": 45.5, "volume": 20},
        {"date": date(2026, 8, 26), "close": 46.0, "volume": 30},
    ]
    out = _daily_metrics_from_rows(rows)
    assert out["latest_daily_close"] == 47.0
    assert out["as_of"] == "2026-08-27"
    assert out["avg_trade_value_20"] == (470 + 910 + 1380) / 3
```

Add a 40-row shuffled fixture and assert `return_20d_pct`, recent/prior averages, pass state, and `as_of` match a manually ordered calculation.

- [ ] **Step 2: Run tests and verify RED**

Run: `.analysis-venv/bin/python -m pytest -q backend/test_vcp_finder_db.py`
Expected: import failure for the new pure functions.

- [ ] **Step 3: Implement deterministic assembly**

Sort rows by `date`, keep the newest configured lookback, calculate metrics from ascending chronological values, and add SQL `ORDER BY symbol, date ASC` after the ranked subquery. Return `as_of` explicitly.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Task 1 test file and assert HANA/KCE helper output uses 2026-08-27 closes 47.0/56.75 against read-only DB fixtures or a read-only verification script.

- [ ] **Step 5: Commit**

```bash
git add backend/vcp_finder_db.py backend/test_vcp_finder_db.py
git commit -m "fix: make VCP daily context ordering deterministic"
```

### Task 2: Entry-Aware Replay and Live-Policy Inputs

**Files:**
- Modify: `backend/run_vcp_replay_1m.py`
- Modify: `backend/test_vcp_replay.py`

**Interfaces:**
- Produces: `evaluate_trade(plan: dict, future_rows: list[dict]) -> dict` with `entry_activated`, `entry_ts`, `pre_entry_bars`, and post-entry-only outcome metrics.
- Replay consumes `load_daily_trend_context(pg, symbols, as_of)` and `load_daily_metrics(pg, symbols, as_of)` for every snapshot.

- [ ] **Step 1: Write failing tests**

```python
def test_standard_plan_ignores_stop_before_entry_activation():
    plan = {"base_type": "standard_vcp", "entry": 102.0, "stop": 96.0, "target": 120.0}
    rows = [
        {"ts": "a", "high": 101.0, "low": 95.0},
        {"ts": "b", "high": 103.0, "low": 100.0},
        {"ts": "c", "high": 121.0, "low": 105.0},
    ]
    out = evaluate_trade(plan, rows)
    assert out["entry_activated"] is True
    assert out["entry_ts"] == "b"
    assert out["pre_entry_bars"] == 1
    assert out["outcome"] == "target_hit"
```

Add no-entry and Low-Cheat-immediate-entry cases. Add a replay wiring test using mocks to assert `daily_context` is passed to `find_vcp_60m()` at each `as_of` and point-in-time Daily metrics are attached.

- [ ] **Step 2: Run tests and verify RED**

Run: `.analysis-venv/bin/python -m pytest -q backend/test_vcp_replay.py`
Expected: stop-before-entry test fails and wiring helper is absent.

- [ ] **Step 3: Implement entry activation and replay context**

For `standard_vcp`, skip rows until `high >= entry`; begin stop/target/MFE/MAE evaluation on the activation bar conservatively. For `low_cheat_vcp`, activate at detection. Load Daily context/metrics with `as_of`, pass context into finder, attach metrics, then classify types.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run Task 2 tests. Do not run a full replay yet.

- [ ] **Step 5: Commit**

```bash
git add backend/run_vcp_replay_1m.py backend/test_vcp_replay.py
git commit -m "fix: make VCP replay entry-aware and policy-complete"
```

### Task 3: Candidate Pivot-Sequence Diagnostics

**Files:**
- Modify: `backend/vcp_finder.py:139-180,263-340`
- Modify: `backend/test_vcp_finder.py`

**Interfaces:**
- Produces: `_sequences(pivots: list[dict]) -> list[list[dict]]`.
- Adds `pattern.sequence_diagnostics` with `candidate_count`, `v1_selection_rule`, `v2_shadow_selection_rule`, `v1_final_pivot_ts`, `v2_final_pivot_ts`, and `v2_final_pivot_age_hours`.
- v1 lifecycle calculations continue to consume the first sequence.

- [ ] **Step 1: Write failing tests**

Create pivots containing two valid overlapping H-L-H-L-H windows. Assert `_sequences()` returns both in deterministic order and shadow selection chooses the most recent sequence whose invalidation has not broken. Assert v1 output state/pivot remains unchanged.

- [ ] **Step 2: Run tests and verify RED**

Run: `.analysis-venv/bin/python -m pytest -q backend/test_vcp_finder.py`
Expected: `_sequences` import failure.

- [ ] **Step 3: Implement diagnostics without v1 promotion**

Enumerate every five-pivot alternating window, retain `_sequence()` as the first-window compatibility wrapper, calculate v2 diagnostic selection from the latest non-broken window, and serialize native JSON values only.

- [ ] **Step 4: Run focused tests and verify GREEN**

Assert no-lookahead pivot tests and existing v1 state fixtures remain green.

- [ ] **Step 5: Commit**

```bash
git add backend/vcp_finder.py backend/test_vcp_finder.py
git commit -m "feat: expose VCP pivot sequence diagnostics"
```

### Task 4: Pure Decision Policy v2 Shadow Projection

**Files:**
- Create: `backend/vcp_decision_policy.py`
- Create: `backend/test_vcp_decision_policy.py`
- Modify: `backend/run_vcp_replay_1m.py`

**Interfaces:**
- Produces: `project_vcp_decision_shadow(result: dict) -> dict`.
- Produces constants `POLICY_VERSION = "signalix/vcp-decision-shadow-v2"` and lane/actionability enums.
- Replay stores output at `result["decision_shadow_v2"]`; live v1 API remains unchanged.

- [ ] **Step 1: Write table-driven failing tests**

Fixtures must cover READY valid morphology, NEAR_TRIGGER, confirmed close+volume, each review lane with incomplete structure, EXTENDED, FAILED, STALE, NOT_VERIFIED, late-watch, low liquidity, non-marginable, sub-0.60 price, missing invalidation, and duplicate/conflicting source booleans.

Assertions:

```python
assert project_vcp_decision_shadow(extended)["decision_lane"] == "DO_NOT_CHASE"
assert project_vcp_decision_shadow(event_only)["actionability"] == "WATCH_ONLY"
assert project_vcp_decision_shadow(low_liquidity_ready)["decision_lane"] == "REVIEW_NOW"
assert project_vcp_decision_shadow(low_liquidity_ready)["tradability"]["passes_default_filters"] is False
```

Also assert every fixture has exactly one lane, one actionability value, stable sort fields, no `rr`, and explicit reason codes.

- [ ] **Step 2: Run tests and verify RED**

Run: `.analysis-venv/bin/python -m pytest -q backend/test_vcp_decision_policy.py`
Expected: module import failure.

- [ ] **Step 3: Implement minimal pure policy**

Implement helpers for freshness, structural evidence, invalidation coherence, event evidence, tradability, context, lane assignment, and deterministic sort fields. Fundamental fields are copied as context only when present. Never mutate the input result.

- [ ] **Step 4: Wire only into replay/shadow output**

Call the projection after type classification and store it under `decision_shadow_v2`. Do not modify `load_latest_vcp_run()` or `project_daily_vcp_watchlist()`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run Task 4, replay, finder, DB, and API test files.

- [ ] **Step 6: Commit**

```bash
git add backend/vcp_decision_policy.py backend/test_vcp_decision_policy.py backend/run_vcp_replay_1m.py
git commit -m "feat: add non-serving VCP decision policy v2 shadow"
```

### Task 5: Shadow Replay Evidence and Final Gate

**Files:**
- Create: `backend/analyze_vcp_shadow_replay.py`
- Create: `backend/test_analyze_vcp_shadow_replay.py`
- Create: `vault/VCP-Decision-Shadow-v2-Review-2026-08-28.md`

**Interfaces:**
- `summarize_shadow(records: Iterable[dict]) -> dict` returns universe retention, lane counts, contradictions, tradability breakdown, state→lane matrix, event follow-through descriptors, and missing-evidence counts.

- [ ] **Step 1: Write failing summary tests**

Use small records with known lanes and assert exact counts, zero double counting, and explicit `NOT_VERIFIED` metrics when future data are absent.

- [ ] **Step 2: Implement the pure summarizer and read-only CLI**

The CLI reads replay JSONB only, accepts `--replay-prefix`, emits JSON to stdout, and performs no updates/deletes.

- [ ] **Step 3: Run all focused tests in a disposable venv**

```bash
python3 -m venv .analysis-venv
.analysis-venv/bin/pip install -q pytest -r backend/requirements.txt
.analysis-venv/bin/python -m pytest -q \
  backend/test_vcp_finder.py \
  backend/test_vcp_finder_db.py \
  backend/test_vcp_finder_api.py \
  backend/test_vcp_replay.py \
  backend/test_vcp_decision_policy.py \
  backend/test_analyze_vcp_shadow_replay.py
```

- [ ] **Step 4: Run a bounded read-only/shadow replay**

Use a new isolated replay ID prefix and one trading day first. Verify eligible=evaluated=returned and every result includes `decision_shadow_v2`. If green, expand to the existing 11-day every-60m window without mutating live VCP tables.

- [ ] **Step 5: Write evidence note**

Record exact policy versions, as-of range, universe, coverage, lane matrix, contradictions, replay limitations, and an explicit `NOT DEPLOYED` statement. Do not label proxies as win rate.

- [ ] **Step 6: Verify served v1 unchanged**

Probe:

```bash
curl -fsS http://127.0.0.1:3001/mvp
curl -fsS 'http://127.0.0.1:3001/api/vcp-finder?market=TH&daily_watchlist=true'
curl -fsS http://127.0.0.1:8000/health/readiness
```

Assert `/dashboard.html` remains 404 and compare live policy/run shape before/after. No Docker rebuild is authorized.

- [ ] **Step 7: Commit evidence**

```bash
git add backend/analyze_vcp_shadow_replay.py backend/test_analyze_vcp_shadow_replay.py vault/VCP-Decision-Shadow-v2-Review-2026-08-28.md docs/superpowers/specs/2026-08-28-vcp-decision-policy-v2-shadow-design.md docs/superpowers/plans/2026-08-28-vcp-decision-policy-v2-shadow.md
git commit -m "test: record VCP decision shadow replay evidence"
```
