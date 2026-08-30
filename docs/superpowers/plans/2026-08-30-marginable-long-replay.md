# Marginable Long Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit `marginable_long` replay mode containing the 237 active Thai ORD symbols whose current marginable record has `can_buy=true`, with deterministic twice-daily snapshots and auditable exclusion metadata.

**Architecture:** Keep the live scanner and served VCP v1 unchanged. Add a provenance-safe universe resolver at the marginable boundary, pass the selected symbol set into the existing isolated replay runner, and extend replay metadata/summary so excluded active ORD symbols are accounted for without inserting fake result rows. Daily-cadence replay samples stored 60m bars at Bangkok 12:30 and 16:45 cutoffs and preserves existing point-in-time outcome semantics.

**Tech Stack:** Python 3.12, PostgreSQL/psycopg2, pandas, pytest, existing `marginable.py`, `run_vcp_replay_1m.py`, and `analyze_vcp_shadow_replay.py`.

**Spec:** `docs/superpowers/specs/2026-08-30-marginable-long-replay-design.md`

## Global Constraints

- `marginable_long` is the intersection of active Thai ORD `symbol_master` rows and `signalix.marginable.v1` records with `instrument_type='ORD'` and `can_buy=true`.
- Current expected counts are active ORD 931, eligible 237, excluded 694; the margin dataset effective date is `2026-08-25`.
- Replay remains research-only; do not change served v1, VCP thresholds, alerts, symbol_master statuses, or production scanner behavior.
- Every selected snapshot must evaluate 237 unique symbols and retain `decision_shadow_v2` plus replay provenance.
- Finder inputs use only bars `ts <= as_of`; future evaluation uses only bars `ts > as_of` and `ts <= replay_end`.
- Standard entries activate only after a future bar trades at/above entry; pre-entry stops are ignored and same-bar target/stop is `ambiguous_same_bar`.
- Low-Cheat remains non-promoting with `promotion_allowed=false`.
- Do not call descriptive replay outcomes a win rate.
- Do not read, print, modify, or commit secrets or production dumps.

---

### Task 1: Add the explicit marginable-long universe resolver

**Files:**
- Modify: `backend/marginable.py`
- Test: `backend/test_marginable.py`

**Interfaces:**
- Produces `eligible_symbols(active_symbols, filter_value="marginable_long") -> tuple[list[str], dict]`.
- The returned list is uppercase, duplicate-free, sorted, and contains only active symbols present in the current margin dataset with `instrument_type == "ORD"` and `can_buy is True`.
- The returned manifest includes `universe_filter`, `base_active_ord_count`, `eligible_count`, `excluded_count`, `excluded_reason`, `schema_version`, `source_document`, and `effective_date`.

- [ ] **Step 1: Write the failing tests**

Add tests to `backend/test_marginable.py` that load the real dataset and assert:

```python
def test_marginable_long_resolver_returns_only_buyable_active_ord():
    active = {"ADVANC", "INET", "AIE", "ZZZ_NOT_IN_LIST"}
    symbols, manifest = eligible_symbols(active)
    assert symbols == ["ADVANC", "AIE"]
    assert manifest["universe_filter"] == "marginable_long"
    assert manifest["base_active_ord_count"] == 4
    assert manifest["eligible_count"] == 2
    assert manifest["excluded_count"] == 2
    assert manifest["excluded_reason"] == "not_marginable_long"


def test_marginable_long_rejects_non_ord_and_cannot_buy_records():
    active = {"INET", "OSP", "ADVANC"}
    symbols, _ = eligible_symbols(active)
    assert "INET" not in symbols
    assert "OSP" not in symbols
    assert symbols == ["ADVANC"]
```

Use the existing real dataset records: `ADVANC` is buyable; `INET` and `OSP` are on the ORD list but have `can_buy=False`.

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```bash
pytest -q backend/test_marginable.py -k 'resolver or marginable_long'
```

Expected: FAIL because `eligible_symbols` does not exist.

- [ ] **Step 3: Implement the smallest resolver**

In `backend/marginable.py`, add `eligible_symbols` after `lookup` or beside the other dataset-boundary helpers. Use `load_marginable_data()["securities"]`, normalize symbols through the existing loader, filter records by exact `instrument_type == "ORD"` and `can_buy is True`, intersect with `active_symbols`, and return a sorted list plus the manifest. Do not change `filter_items`, `matches`, or existing UI filter semantics.

- [ ] **Step 4: Run the focused tests and the existing marginable suite**

Run:

```bash
pytest -q backend/test_marginable.py
```

Expected: all existing and new tests pass.

- [ ] **Step 5: Commit the bounded task**

```bash
git add backend/marginable.py backend/test_marginable.py
git commit -m "feat: add marginable long replay universe resolver"
```

### Task 2: Wire twice-daily marginable-long replay and manifest persistence

**Files:**
- Modify: `backend/run_vcp_replay_1m.py`
- Test: `backend/test_vcp_replay.py`
- Test: `backend/test_analyze_vcp_shadow_replay.py` only if shared summary fixtures require it

**Interfaces:**
- Add CLI option `--universe` with choices `active_ord` and `marginable_long`; preserve current default behavior for existing callers.
- Add CLI option `--snapshots-per-day` with choices `1` and `2`; `2` selects the latest available stored 60m timestamp at or before Bangkok cutoffs `12:30` and `16:45`.
- `select_replay_snapshots(..., cadence="daily", snapshots_per_day=1)` returns deterministic snapshots and selected Bangkok dates; existing `cadence="60m"` behavior remains compatible.
- Replay run metadata records the universe manifest, cadence, and snapshots-per-day. The result validator enforces the selected eligible count, not hard-coded 931.

- [ ] **Step 1: Write failing unit tests for cutoff selection**

Add deterministic tests using UTC timestamps that map to Bangkok dates and verify:

```python
def test_select_replay_snapshots_two_points_per_bangkok_day():
    selected = select_replay_snapshots(
        timestamps=[
            "2026-08-03T05:00:00+00:00",  # 12:00 BKK, before midday cutoff
            "2026-08-03T05:30:00+00:00",  # 12:30 BKK, midday point
            "2026-08-03T09:00:00+00:00",  # 16:00 BKK, before EOD cutoff
            "2026-08-03T09:45:00+00:00",  # 16:45 BKK, EOD point
        ],
        end="2026-08-03T10:00:00+00:00",
        cadence="daily",
        snapshots_per_day=2,
    )
    assert [x.isoformat() for x in selected["snapshots"]] == [
        "2026-08-03T05:30:00+00:00",
        "2026-08-03T09:45:00+00:00",
    ]
```

Add a resolver integration fixture that monkeypatches `active_ord_symbols` and `eligible_symbols`, then asserts `marginable_long` passes exactly the returned 237-style selected list into the SQL `symbol=ANY(...)` query and `validate_replay_results` accepts 237, not 931.

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```bash
pytest -q backend/test_vcp_replay.py -k 'snapshot or universe'
```

Expected: FAIL because `snapshots_per_day` and `--universe` are not implemented.

- [ ] **Step 3: Implement universe selection and snapshot selection**

Import `eligible_symbols` from `marginable`. Resolve `active_symbols = sorted(set(active_ord_symbols(pg)))`. For `--universe marginable_long`, call `eligible_symbols(active_symbols)` and use its selected list for all replay SQL and per-symbol loops; keep the manifest for persistence and summary. For `active_ord`, retain the current active-symbol path and create an equivalent manifest with `universe_filter="active_ord"`.

Extend `select_replay_snapshots` with `snapshots_per_day=1`. For daily mode, group timestamps by Bangkok date; for each date choose the latest timestamp at or before 12:30 BKK and 16:45 BKK when `snapshots_per_day=2`, deduplicate timestamps, and raise `ValueError` if no cutoff point exists for a selected date. Keep one-point daily mode as the latest timestamp of each date and keep every-60m mode unchanged.

- [ ] **Step 4: Add explicit replay run metadata without breaking old tables**

Extend the runner DDL with nullable JSON/text columns only if the current table lacks them, or persist the manifest in the JSON result envelope when schema migration is not needed. The stored run/result contract must include `universe_filter`, `base_active_ord_count`, `eligible_count`, `excluded_count`, margin schema/source/effective date, cadence, and `snapshots_per_day`. Do not delete or rewrite existing replay rows.

- [ ] **Step 5: Run focused and regression tests**

Run:

```bash
pytest -q backend/test_vcp_replay.py backend/test_marginable.py
pytest -q backend/test_analyze_vcp_shadow_replay.py
```

Expected: all pass, including existing daily/60m compatibility tests.

- [ ] **Step 6: Commit the bounded task**

```bash
git add backend/run_vcp_replay_1m.py backend/test_vcp_replay.py backend/test_analyze_vcp_shadow_replay.py
git commit -m "feat: add marginable long daily replay mode"
```

### Task 3: Add fail-closed summary and pilot verification artifact

**Files:**
- Modify: `backend/analyze_vcp_shadow_replay.py`
- Test: `backend/test_analyze_vcp_shadow_replay.py`
- Create: `.superpowers/sdd/2026-08-30-marginable-long-replay/pilot-command.txt` only if the executor needs a recorded command; do not commit runtime output

**Interfaces:**
- `summarize_shadow(records)` retains its existing keys and adds universe/cadence fields when supplied by the replay envelope.
- Add a pure `summarize_timeline(records)` helper returning per-symbol ordered state transitions, first watch, first action lane, and outcome counts.
- Summary must fail closed when the expected result collection is missing or has an unexpected type; never convert missing data to zero.

- [ ] **Step 1: Write failing summary tests**

Add tests for:

```python
def test_summarize_timeline_orders_states_and_counts_transitions():
    records = [
        {"symbol": "AAA", "as_of": "2026-08-01T05:30:00+00:00", "state": "FORMING", "decision_shadow_v2": {"decision_lane": "RESEARCH", "actionability": "NO_ACTION"}},
        {"symbol": "AAA", "as_of": "2026-08-01T09:45:00+00:00", "state": "READY", "decision_shadow_v2": {"decision_lane": "PREPARE", "actionability": "ACTIONABLE_REVIEW"}},
    ]
    out = summarize_timeline(records)
    assert out["AAA"]["states"] == ["FORMING", "READY"]
    assert out["AAA"]["transition_count"] == 1
    assert out["AAA"]["first_action_lane"] == "PREPARE"
```

Also assert that a summary with `expected_count=237` raises `ValueError` for 236 records and that a missing `decision_shadow_v2` is counted as a validation failure rather than zero results.

- [ ] **Step 2: Run focused tests and confirm they fail**

```bash
pytest -q backend/test_analyze_vcp_shadow_replay.py -k 'timeline or expected_count'
```

Expected: FAIL because `summarize_timeline` and the fail-closed expected-count check do not exist.

- [ ] **Step 3: Implement timeline and summary metadata**

Implement deterministic sorting by `(symbol, as_of)`, preserve all existing lane/state/outcome summaries, and add `timeline_count`, `transition_count`, and per-symbol first-event fields. Validate the selected universe count before reporting a completed snapshot. Keep diagnostic lists bounded while retaining exact aggregate counts.

- [ ] **Step 4: Run the full relevant suite and syntax checks**

```bash
pytest -q backend/test_analyze_vcp_shadow_replay.py backend/test_vcp_replay.py backend/test_marginable.py
python3 -m py_compile backend/marginable.py backend/run_vcp_replay_1m.py backend/analyze_vcp_shadow_replay.py
```

- [ ] **Step 5: Commit the bounded task**

```bash
git add backend/analyze_vcp_shadow_replay.py backend/test_analyze_vcp_shadow_replay.py
git commit -m "feat: summarize marginable replay timelines safely"
```

### Task 4: Run the five-day pilot and prepare evidence (Lite-owned runtime gate)

**Files:**
- Read-only source/runtime: `backend/run_vcp_replay_1m.py`, PostgreSQL replay tables, current served `/mvp` and `/api/vcp-finder`
- Create untracked evidence under the plan workspace, not source authority: `.superpowers/sdd/2026-08-30-marginable-long-replay/pilot-evidence.json`

- [ ] **Step 1: Verify clean scope and test baseline**

Run `git status --short --branch`, inspect the complete branch diff, and rerun Tasks 1–3 tests. Do not restart production services or alter served v1.

- [ ] **Step 2: Run the bounded pilot**

Use a new explicit prefix and five completed Bangkok trading dates with two points per date:

```bash
docker exec signalix_backend python /app/run_vcp_replay_1m.py \
  --universe marginable_long \
  --cadence daily \
  --snapshots-per-day 2 \
  --trading-days 5 \
  --max-snapshots 10 \
  --id-prefix vcp-marginable-long-pilot-20260830
```

If the runner requires a fixed historical end timestamp for determinism, set `--end` to the verified latest completed replay boundary rather than wall-clock now.

- [ ] **Step 3: Verify the pilot evidence**

Require exactly 10 snapshots and 2,370 evaluated result rows, 237 unique symbols per snapshot, complete `decision_shadow_v2`, explicit margin source/effective date, no-lookahead, and no duplicate `(replay_id, symbol)` keys. Record excluded active ORD count 694 and keep `promotion_allowed=false`.

- [ ] **Step 4: Probe serving remains unchanged**

Verify `/mvp` is 200, `/api/vcp-finder` remains 200 with its existing full-success serving run, and no new `sequence_policy_shadow_v2` field appears in the served v1 payload. Do not deploy the replay artifact to serving.

- [ ] **Step 5: Produce final evidence report**

Write a bounded JSON summary and Thai handoff with scope, exact commands, counts, date/time boundaries, outcomes, limitations, and separate verdicts for code, replay data, runtime, and promotion. The pilot may authorize the two-month replay only if all gates pass; it never authorizes a serving-policy switch.

---

## Final review checklist

- [ ] All task commits contain only intended files and `git diff --check` passes.
- [ ] Task reviews find no open Critical/Important issue; any parked finding has a written ruling.
- [ ] Pilot has `eligible=evaluated=returned=237` for every snapshot.
- [ ] Existing full-ORD historical observations remain unchanged.
- [ ] Served v1/API/UI behavior remains unchanged.
- [ ] Promotion remains `REVISE/BLOCKED` until the separate owner decision gate passes.
