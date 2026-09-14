# Daily Shortlist + All Stocks Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a fast default Daily Shortlist of trustworthy Thai Daily swing setups while retaining the full-ORD stage-first dashboard as a clearly labelled All Stocks Explorer.

**Architecture:** Keep FULL ORD scanning and `dashboard_snapshot.json` as the complete append-only research artifact. Add a pure deterministic shortlist projection over already serialized Daily cards, then expose a compact `/dashboard/shortlist` API that never fetches chart/history data. The new default UI consumes only that endpoint; the existing stage-first route remains a secondary Explorer and retains its research filters.

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL-backed scan inputs, static HTML/vanilla JavaScript, pytest/unittest, Docker Compose, Chrome/agent-browser for rendered evidence.

**Spec:** `docs/superpowers/specs/2026-08-23-daily-shortlist-explorer-design.md`

## Global Constraints

- Preserve FULL active Thai ORD scan coverage; shortlist/explorer presentation must never delete or silently filter scanner records.
- Daily Shortlist is Daily EOD swing-trade only; intraday events cannot create or upgrade a published candidate.
- Publication states are exactly `READY` and `PRE_READY`; `DEVELOPING`, broken, invalidated, extended/`DO NOT CHASE`, stale, insufficient-history, and low-liquidity rows are excluded.
- Liquidity hard gate: `avgDailyValue20 >= 10_000_000` THB. Missing liquidity is not eligible.
- Rank deterministic components: structure 40%, entry readiness 30%, risk/reward 20%; liquidity is gate + deterministic tie-breaker. Market regime is context only and is absent from gating and ranking.
- Every published card includes trigger/confirmation, invalidation, freshness/provenance, gate reasons, rank components, policy version, and stable total ordering.
- English UI labels; no horizontal scrolling at 512px. No LLM-derived calculations or automatic trading language.
- Preserve pre-existing dirty files. Do not stage `.venv`, logs, generated snapshots, legacy deletions, or current risk-plan work.

---

## File structure and responsibilities

- Create: `backend/daily_shortlist.py` — pure eligibility, state, deterministic component scoring, and projection functions.
- Create: `backend/test_daily_shortlist.py` — fixture-driven contract tests for exclusions, state, rank determinism, and field completeness.
- Modify: `backend/build_dashboard.py` — serialize the explicit raw evidence needed by shortlist; do not change full-universe retention or the existing action-queue semantics.
- Modify: `backend/app.py` — cached, bounded `/dashboard/shortlist` API and no-rescan failure behavior.
- Modify: `backend/dashboard_template.html` — default Daily Shortlist route/view plus secondary All Stocks Explorer navigation and research-only copy.
- Create: `backend/test_daily_shortlist_api.py` — endpoint contract, payload size, stale/empty/error fixture tests.
- Modify: `backend/test_dashboard_responsive.py` and create `backend/test_daily_shortlist_browser.py` — source markers plus real desktop/mobile/empty/error browser acceptance.
- Modify: `vault/Execution-Pipeline.md` only after verified release evidence; do not mark the row done merely from tests.

### Task 1: Protect the contaminated worktree and establish a clean execution lane

**Files:**
- Create: isolated worktree outside `/root/signalix`, on a branch rooted at commit `a6fdb85` after safely reconciling current upstream `origin/master`.
- Do not modify: current `/root/signalix` dirty checkout.

**Interfaces:**
- Consumes: repository `git status`, `git fetch origin master`, and the approved spec.
- Produces: a verified clean worktree path and a baseline manifest for later commits.

- [ ] **Step 1: Capture baseline and refuse unsafe checkout operations**

Run:
```bash
git -C /root/signalix status --short
git -C /root/signalix fetch origin master
git -C /root/signalix rev-list --left-right --count origin/master...master
```
Expected: record all pre-existing dirty paths and remote divergence; do not reset, stash, clean, merge, rebase, or force-push in the dirty checkout.

- [ ] **Step 2: Create a separate clean worktree only after choosing a safe base**

Use `superpowers:using-git-worktrees`. The implementation branch must be based on a reviewed commit that contains the approved design commit `a6fdb85` and reconciled `origin/master`; if that reconciliation is non-fast-forward, stop and request/perform a dedicated integration step before coding.

- [ ] **Step 3: Verify isolation before any code/test change**

Run:
```bash
git -C <worktree> status --short
git -C <worktree> log -1 --oneline
git -C <worktree> diff --name-only
```
Expected: clean worktree; no `.venv`, log, generated-artifact, or risk-plan paths are present.

- [ ] **Step 4: Commit**

No code commit in this task. Record the safe worktree base and baseline only in the task report, not in product source.

### Task 2: Implement pure Daily Shortlist eligibility and ranking

**Files:**
- Create: `backend/daily_shortlist.py`
- Create: `backend/test_daily_shortlist.py`

**Interfaces:**
- Consumes: a serialized `build_dashboard.serialize()` card with `stage`, `phase`, `action_queue`, `setup_quality`, `setup_proximity`, `avgDailyValue20`, `breakoutLevel`, `stop`/`riskStop`, `dataFreshness`, and Daily EOD provenance.
- Produces:
```python
def classify_shortlist(item: dict) -> dict:
    # {eligible: bool, publication_state: "READY"|"PRE_READY"|None,
    #  exclusion_reasons: list[str], rank_components: dict[str, float],
    #  total_score: float|None, policy_version: str}

def project_shortlist(items: list[dict]) -> list[dict]:
    # eligible records only, ordered deterministically
```

- [ ] **Step 1: Write failing eligibility/ranking fixtures**

Create tests covering this exact matrix:
```python
assert classify_shortlist(card(avgDailyValue20=9_999_999))["eligible"] is False
assert "LIQUIDITY_BELOW_20D_THB_10M" in classify_shortlist(card(avgDailyValue20=9_999_999))["exclusion_reasons"]
assert classify_shortlist(card(avgDailyValue20=None))["eligible"] is False
assert classify_shortlist(card(phase="breakout_extended", action="DO NOT CHASE"))["eligible"] is False
assert classify_shortlist(card(stage="S4_down"))["eligible"] is False
assert classify_shortlist(card(dataFreshness="stale"))["eligible"] is False
assert classify_shortlist(card(action_queue="fresh_breakout", avgDailyValue20=20_000_000))["publication_state"] == "READY"
assert classify_shortlist(card(action_queue="pre_breakout", avgDailyValue20=20_000_000))["publication_state"] == "PRE_READY"
```
Also assert `project_shortlist` returns no developing/base/monitor/avoid/intraday candidate; each result has `rank_components`, `policy_version`, trigger, invalidation, source and as-of fields; identical input order changes do not change output order.

- [ ] **Step 2: Run the focused test and prove RED**

Run:
```bash
cd <worktree>/backend && /root/.venv_img/bin/python -m pytest test_daily_shortlist.py -v
```
Expected: FAIL because `daily_shortlist` does not exist.

- [ ] **Step 3: Implement the minimal pure module**

Use immutable input access; never query DB or current time. Map only Daily queues:
```python
READY_QUEUES = {"fresh_breakout", "qualified_pullback", "retest_watch"}
PRE_READY_QUEUES = {"pre_breakout"}
MIN_AVG_DAILY_VALUE_20 = 10_000_000
POLICY_VERSION = "daily-shortlist-v1"
```
Require non-stale Daily EOD provenance, non-null trigger and invalidation. Compute bounded component values from already deterministic evidence; expose exact missing/failed gate reason codes. Use `(-total_score, -avgDailyValue20, symbol)` as the final stable sort key. Do not include `market_regime` in the module inputs or score.

- [ ] **Step 4: Run GREEN and regression tests**

Run:
```bash
cd <worktree>/backend && /root/.venv_img/bin/python -m pytest test_daily_shortlist.py test_action_queue.py test_setup_state.py -v
```
Expected: all pass; existing 7-queue full-coverage contract remains unchanged.

- [ ] **Step 5: Commit**

```bash
git -C <worktree> add backend/daily_shortlist.py backend/test_daily_shortlist.py
git -C <worktree> diff --cached --check
git -C <worktree> commit -m "feat: add deterministic daily shortlist policy"
```

### Task 3: Wire explicit evidence and a compact cached shortlist API

**Files:**
- Modify: `backend/build_dashboard.py:822-1150`
- Modify: `backend/app.py:766-896`
- Create: `backend/test_daily_shortlist_api.py`
- Modify: `backend/test_compact_cards.py`

**Interfaces:**
- Consumes: `daily_shortlist.project_shortlist(payload["items"])`.
- Produces:
```python
GET /dashboard/shortlist
# 200: {scan_time, data_fetched_at, data_freshness_status, market_session,
#        policy_version, total, candidates: [...]}
# 503: cached source unavailable/invalid; never rescans or returns false READY
```

- [ ] **Step 1: Write failing API and serializer tests**

Test a snapshot fixture with eligible Ready, eligible Pre-ready, low-liquidity, stale, extended, developing, and S4 cards. Assert endpoint returns only the two eligible cards, Ready before Pre-ready, exact root freshness fields, no `market_regime` rank field, and JSON payload remains under 150 KB for 100 candidates. Assert a missing/corrupt cache returns HTTP 503 and does not call scan/build functions.

- [ ] **Step 2: Run RED**

Run:
```bash
cd <worktree>/backend && /root/.venv_img/bin/python -m pytest test_daily_shortlist_api.py -v
```
Expected: FAIL because `/dashboard/shortlist` and required contract fields do not exist.

- [ ] **Step 3: Extend serializer without changing full-universe behavior**

In `serialize()`, preserve all existing fields and add explicit raw fields only where absent: `daily_as_of`, `daily_source`, `avgDailyValue20`, trigger, invalidation, `setup_quality`, `setup_proximity`, `action_queue`, `dataFreshness`, and source freshness. Do not make `lowValue` remove a card, do not alter `build(scanned=...)`, and do not add a `scan_results.json` fallback.

- [ ] **Step 4: Add cached endpoint**

Implement `dashboard_shortlist()` beside `/dashboard/cards/compact`. It must call `_load_dashboard_cache()` then `project_shortlist`; it must not call `/scan`, DB queries, chart/history fetches, or mutate snapshot data. Return exact freshness and `market_session` root fields. The response must contain an explicit empty candidates array when no item qualifies.

- [ ] **Step 5: Run GREEN and affected regression suite**

Run:
```bash
cd <worktree>/backend && /root/.venv_img/bin/python -m pytest \
  test_daily_shortlist_api.py test_daily_shortlist.py test_compact_cards.py \
  test_setup_serialize.py test_provenance_contract.py test_dashboard_api.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git -C <worktree> add backend/build_dashboard.py backend/app.py backend/test_daily_shortlist_api.py backend/test_compact_cards.py
git -C <worktree> diff --cached --check
git -C <worktree> commit -m "feat: expose compact daily shortlist API"
```

### Task 4: Build the default shortlist surface and retain Explorer

**Files:**
- Modify: `backend/dashboard_template.html`
- Modify/Create: `backend/test_dashboard_responsive.py`, `backend/test_daily_shortlist_browser.py`

**Interfaces:**
- Consumes: `GET /dashboard/shortlist` for default view; existing compact/cards and chart endpoints only after user navigates to Explorer/detail.
- Produces: default `/dashboard.html` Daily Shortlist and an explicit All Stocks Explorer navigation/view.

- [ ] **Step 1: Write failing rendered/UI contract tests**

Add source assertions for `daily-shortlist`, `READY`, `PRE-READY`, `All Stocks Explorer`, `Research universe — not a list of trade suggestions`, explicit empty/stale/error panels, and mobile no-horizontal-scroll CSS. Browser test fixtures must verify: successful shortlist render, empty eligible set, 503 error retaining an honest error state, card-open chart/evidence action, Explorer navigation, 1280px desktop, and 512px mobile.

- [ ] **Step 2: Run RED**

Run:
```bash
cd <worktree>/backend && /root/.venv_img/bin/python -m pytest test_dashboard_responsive.py test_daily_shortlist_browser.py -v
```
Expected: FAIL because default page still loads full snapshot/stage filter wall rather than `/dashboard/shortlist`.

- [ ] **Step 3: Implement thin default UI**

Make first paint request `/dashboard/shortlist`; render freshness first, `READY` then `PRE-READY`, and each card’s symbol, score explanation, why-now/why-not, trigger, invalidation, liquidity evidence, and source/as-of. Load chart/detail only after card click. Do not render full-universe cards, base-building, portfolio controls, or filter wall in default view.

Add a secondary **All Stocks Explorer** navigation target that retains existing research controls and cards, adds exact research-only copy, and never labels an Explorer-only row `READY`, `BUY ZONE`, or a suggestion.

- [ ] **Step 4: Rebuild only through the supported pipeline**

Use a fresh scan threaded into `build_dashboard.build(scanned=...)`; do not call `build()` without `scanned` and do not reintroduce stale-file fallback. Verify the built `dashboard.html` is newer than its template before container recreation.

- [ ] **Step 5: Run automated and real browser acceptance**

Run focused tests, then recreate `backend` and `dashboard` from the clean checkout only. Verify `/health`, `/dashboard/shortlist`, served `:3001/dashboard.html`, and real desktop/mobile journeys. Capture screenshots for loaded, empty, stale, and API-error states; inspect them with vision. A 200 API or static grep alone is not UI acceptance.

- [ ] **Step 6: Commit**

```bash
git -C <worktree> add backend/dashboard_template.html backend/test_dashboard_responsive.py backend/test_daily_shortlist_browser.py
git -C <worktree> diff --cached --check
git -C <worktree> commit -m "feat: make daily shortlist the default dashboard"
```

### Task 5: Final evidence gate and controlled documentation closeout

**Files:**
- Modify only after evidence: `vault/Execution-Pipeline.md`
- Do not modify: historical handoffs, generated files, `.venv`, or unrelated dirty work.

**Interfaces:**
- Consumes: deployed endpoints, snapshot/DB coverage evidence, test results, browser screenshots.
- Produces: Lite final verdict: PASS / FAIL / NOT VERIFIED.

- [ ] **Step 1: Run full acceptance evidence**

Verify separately: source→full scan coverage, full scan→shortlist exclusions, API fields/size, stale/empty/error behavior, served HTML, desktop/mobile user journeys, and Explorer boundary copy. Query the newest scan run and compare full evaluated count with snapshot/shortlist counts; shortlist count must be a documented eligibility subset, not a scan loss.

- [ ] **Step 2: Verify failure cases are honest**

Use fixtures or controlled cache copies to prove stale data yields no false `READY`, empty result renders an empty state, and cache/API failure renders a clear error without falling back to a prior full-universe suggestion list.

- [ ] **Step 3: Review commit scope and deploy provenance**

For each implementation commit, inspect `git diff --cached --name-only`, `git diff --cached --check`, and final `git status --short`. Confirm no unrelated pre-existing dirty files entered the branch. Record exact deployed image/container revision and URL evidence.

- [ ] **Step 4: Update pipeline only if all gates pass**

Append concise evidence to `vault/Execution-Pipeline.md`: files changed, exact test command/results, source/freshness impact, deployment status, desktop/mobile screenshot evidence, and Lite verdict. If any part is missing, record `NOT VERIFIED`; do not call the product ready.

- [ ] **Step 5: Commit documentation evidence separately**

```bash
git -C <worktree> add vault/Execution-Pipeline.md
git -C <worktree> diff --cached --check
git -C <worktree> commit -m "docs: record daily shortlist acceptance evidence"
```

## Plan self-review

- Spec coverage: Tasks 2–3 implement deterministic states, gate, rank, provenance, compact payload, and full-ORD preservation; Task 4 implements default/Explorer UI and error journeys; Task 5 provides evidence-gated release.
- No required spec feature is assigned to market-regime scoring, portfolio behavior, intraday-first signals, LLM computation, or deleting Explorer.
- Naming consistency: API is `/dashboard/shortlist`; pure module functions are `classify_shortlist` and `project_shortlist`; states are `READY` and `PRE_READY`.
- Execution must stop at Task 1 if dirty-checkout/upstream reconciliation has not produced an isolated clean base.
