# Signalix Research Index

> **STATUS: CURRENT** · Index/router for isolated Signalix research projects. This note is not a product, API, production, or trading-policy authority.
> **Last updated:** 2026-09-05 ICT
> **Authority boundary:** research artifacts support owner review; they do not change `/api/setup-candidates`, `/mvp`, Wave publication, alerts, auto-trading, or broker execution.
>
> Project map: `../docs/current/2026-09-05-wave-playbooks-research-project.md`

## Current delivery focus — 2026-09-12

Daily Trend Mapping via `/trend-map-shadow` and `/api/trend-map-shadow` is the
current Signalix delivery focus. It is public read-only, non-actionable
research evidence. The `/mvp` and `/api/setup-candidates` path is **DROPPED /
PAUSED** by owner decision; preserve source/history for retained audit/future
integration only and do not route work there until Arm explicitly resumes it.
Elliott/Wave research is deferred until separately resumed.

## Deferred research projects

### Wave Playbooks and AutoResearch

- **Research Bible:** `Research-Playbook-Bible.md` — current formula/evidence/promotion-gate authority for the four playbooks; research-only.
- **Latest session closeout:** `../docs/current/2026-09-08-0915-52w-research-session-closeout.md` — Cycle 1–3 evidence, potential `52W-C3_SUPPORTIVE_ONLY`, interrupted fold gate, and resume sequence.
- **Project:** `../docs/current/2026-09-05-wave-playbooks-research-project.md`
- **Session-start findings handoff:** `../docs/current/2026-09-05-wave-playbooks-research-findings-handoff.md`
- **Scope:** deterministic Daily research for Wave-2 continuation, 52W breakout, Wave-1 pickup, and Wave-3 continuation.
- **Current phase:** baseline replay + bounded parameter research; production promotion is `HOLD`.
- **Current universe scopes:**
  - `marginable_long_current_retrospective`: current 237-symbol operational research scope;
  - `historical_th_ord_data_available`: broad stored-data scope (not point-in-time membership; the 1990–2026 campaign observed 1,219 symbols, with explicit history status).
- **Current evidence:**
  - `/tmp/signalix_four_playbook_baseline_matrix.json`
  - `/tmp/signalix_historical_1990_2026_robustness.json`
  - `/tmp/signalix_production_readiness_campaign.json`
  - `/tmp/signalix_playbook_tuning_15cycles.json`
  - `/tmp/signalix_autoresearch_batch1_50.json`
  - `/tmp/signalix_autoresearch_batch2_robust.json`
  - `/tmp/signalix_autoresearch_time_symbol_matrix.json`
- **Visual artifacts:**
  - `/tmp/signalix_wave2_chart_dashboard.html`
  - `/tmp/signalix_wave2_recent_pivots.html`
  - `/tmp/signalix_continuation_breakout_replay.html`
- **Codex advisory artifacts:**
  - `/tmp/codex_four_playbooks_review.md`
  - `/tmp/codex_playbook_tuning_plan.md`
  - `/tmp/codex_playbook_tuning_correction.md`

## Sub-project registry

### 1. Wave-2 continuation

- **Question:** Does `pivot confirmed → higher low → minor-high close breakout` produce a repeatable continuation event?
- **Status:** Research evidence; current/broad scopes differ; no production promotion.
- **Primary evidence:** continuation replay, time×symbol matrix, Wave-2 chart dashboards.
- **Known finding:** current 237 and broad historical universe can produce different conclusions; preserve both scopes.

### 2. 52W high breakout

- **Question:** Does a prior 252/260-trading-day high close breakout with declared volume/entry semantics produce positive expectancy?
- **Status:** Promising research candidate; not production verified.
- **Primary evidence:** four-playbook baseline and 52W tuning cycles.
- **Required next gate:** exact 52W signal/entry separation, cost/fee model, portfolio replay, chart review.

### 3. Wave-1 pickup

- **Question:** Can a deterministic base/early-advance hypothesis identify a useful pickup before later continuation?
- **Status:** Cut from candidate production research; audit-only after negative holdout baseline.
- **Evidence retained:** four-playbook baseline report and event ledger.
- **Re-entry condition:** a separately justified structural definition, not threshold-only rescue.

### 4. Wave-3 continuation

- **Question:** Does an impulse/retracement/higher-low/close-above-impulse-high event generalize across eras?
- **Status:** Exploratory; current/broad holdout weak; structural policy wiring incomplete for some proposed cycles.
- **Required next gate:** implement structural overrides and MACD/volume policies explicitly; mark unsupported cycles `NOT_IMPLEMENTED`.

### 5. AutoResearch harness

- **Question:** Can policy parameters be searched without changing the evaluator or leaking holdout data?
- **Status:** Mechanical readiness established; long-run robustness campaign remains research-only.
- **Immutable boundary:** data window/universe resolver, no-lookahead, event labels, entry/outcome semantics, target/stop evaluator, same-bar handling, holdout lock.
- **Mutable boundary:** versioned policy JSON only; every run records policy hash and result manifest.

### 6. Portfolio replay and growth

- **Status:** Not started / next bounded sub-project.
- **Required:** 1R risk, target axes 2.5/3/3.5/4/5, overlap/cooldown, position cap, fees/slippage, equity curve, geometric growth, max drawdown, losing streak, symbol/sector concentration.
- **No-go:** do not call event-level target-before-stop a portfolio win rate or growth result.

## Research status taxonomy

- `RESEARCH_ONLY` — isolated evidence, no product change.
- `PROMISING` — evidence merits another bounded test; not a champion.
- `INCONCLUSIVE` — insufficient sample or unresolved semantics.
- `CUT_AUDIT_ONLY` — removed from candidate search but preserved for learning.
- `HOLD_PRODUCTION` — production promotion explicitly blocked pending gates.
- `OWNER_REVIEW_PENDING` — Lite has completed technical evidence; Arm decision remains.

## Production boundary

Research findings must not silently alter:

- canonical `/api/setup-candidates`;
- `/mvp` decision lanes or Wave publication;
- Daily/60m authority separation;
- current `marginable_long` operational scope;
- alerts, evaluator auto-caller, automatic trading, or broker execution.

Promotion requires a new owner-approved decision, source/tests/runtime/API/UI gates, chart review, paper/shadow evidence, rollback/disable path, and a documentation sync in the owning authority.

## Artifact retention note

Current `/tmp` paths are evidence locations for this session and may be cleaned by the environment. Before any future promotion or handoff, promote the exact manifest/report/chart artifacts into an approved durable research archive and add checksums; do not treat a temporary file as the sole authority.
