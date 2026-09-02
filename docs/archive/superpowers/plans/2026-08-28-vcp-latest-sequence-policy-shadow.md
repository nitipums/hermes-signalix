# VCP Latest-Sequence Policy Shadow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a replay-only latest-non-broken sequence evaluator and point-in-time A/B outcomes against legacy v1 without changing served v1 behavior.

**Architecture:** Preserve the v1 path and add an optional shadow calculation in `vcp_finder.py`. Replay explicitly enables the shadow, builds a separate standard-entry plan, persists a separate evaluation, and summarizes A/B evidence through pure functions.

**Tech Stack:** Python 3.12, pandas, psycopg2, PostgreSQL 16, pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-vcp-latest-sequence-policy-shadow-design.md`

## Global Constraints

- Work in an isolated `.worktrees/` checkout from `release/signalix-mvp-stable`.
- Lite implements inline; do not dispatch workers.
- TDD: each production behavior must have a failing test first.
- Preserve full active TH ORD retention and append-only replay tables.
- No API/UI/Docker/deployment changes.
- Low-Cheat remains non-promoting and creates no sequence-v2 trade plan.
- Do not call descriptive outcomes a win rate.

---

### Task 1: Pure Latest-Sequence Evaluator

**Files:**
- Modify: `backend/vcp_finder.py`
- Modify: `backend/test_vcp_finder.py`

**Interfaces:**
- Produces `_evaluate_sequence_policy_shadow(work, sequences, *, cfg, trend_pass, last_close, atr, freshness, observed_as_of) -> dict`.
- Extends `find_vcp_60m(..., include_sequence_policy_shadow=False)`.

- [ ] Write failing tests with two confirmed sequences where the latest sequence has a different pivot/invalidation/state from v1, and a case where the latest candidate is broken so the prior surviving candidate is selected.
- [ ] Run `pytest -q backend/test_vcp_finder.py` and verify RED from missing argument/helper.
- [ ] Implement latest-non-broken selection and independent morphology/state calculations. Serialize all numbers/timestamps to native JSON-safe values.
- [ ] Assert flag-off output has no shadow key; flag-on output includes policy `signalix/vcp-sequence-policy-shadow-v2` and v1 top-level pivot remains first-sequence.
- [ ] Run focused tests GREEN and commit `feat: add latest-sequence VCP policy shadow`.

### Task 2: Separate Sequence-v2 Trade Plan and Evaluation

**Files:**
- Modify: `backend/run_vcp_replay_1m.py`
- Modify: `backend/test_vcp_replay.py`

**Interfaces:**
- Produces `sequence_v2_trade_plan(result) -> dict | None`.
- Produces `attach_sequence_v2_evaluation(result, future_rows) -> dict | None`.
- Replay output keys: `sequence_v2_trade_plan`, `sequence_v2_replay_evaluation`.

- [ ] Write failing tests proving complete latest-sequence morphology creates a standard-entry plan from v2 required close/invalidation, incomplete morphology creates no plan, and observed Low-Cheat conditions never create a plan.
- [ ] Write a failing wiring test proving replay calls finder with `include_sequence_policy_shadow=True`.
- [ ] Implement the minimal plan/evaluation helpers using the existing entry-aware `evaluate_trade()`.
- [ ] Maintain independent first-event maps for v1 `(symbol, base_type)` and sequence-v2 `(symbol, "standard_vcp")`; attach v2 evaluation only to its first event.
- [ ] Run finder/replay tests GREEN and commit `feat: persist latest-sequence replay outcomes`.

### Task 3: Pure A/B Replay Summary

**Files:**
- Modify: `backend/analyze_vcp_shadow_replay.py`
- Modify: `backend/test_analyze_vcp_shadow_replay.py`

**Interfaces:**
- Produces `summarize_sequence_ab(records: Iterable[dict]) -> dict`.

- [ ] Write table-driven failing tests with known v1/v2 pivots, states, plans, and outcomes.
- [ ] Implement counts for coverage, shadow presence, pivot/state divergence, entry activation, outcomes, bars-to-entry, and Low-Cheat promotion violations.
- [ ] Extend CLI JSON output with `sequence_ab` while preserving existing summary fields.
- [ ] Run analyzer tests GREEN and commit `feat: summarize VCP sequence policy A/B evidence`.

### Task 4: Replay and Acceptance Evidence

**Files:**
- Create: `vault/VCP-Latest-Sequence-Shadow-Review-2026-08-28.md`
- Modify: `vault/INDEX.md`

- [ ] Run the complete focused VCP suite.
- [ ] Run an isolated one-day every-60m replay with a new prefix. Verify 931 results per snapshot, shadow presence, no Low-Cheat plans, separate persisted evaluations, and served v1 unchanged.
- [ ] If one-day gates pass, run/resume the 38-snapshot 5-day window with another new prefix using background process notification. If monitoring is needed, use recurring `every 15m` and `deliver=origin`; remove it after terminal completion.
- [ ] Generate A/B summary JSON and write the evidence note with exact prefix/window/policies/coverage/outcomes/limitations and `NOT DEPLOYED`.
- [ ] Run full backend suite, probe `/mvp`, VCP API, readiness, and retired `/dashboard.html` contract.
- [ ] Commit explicit files, push feature branch, create PR, fast-forward merge after verification, push release, and clean the verified worktree.
