# Daily Setup State Contract Implementation Plan

> **For Hermes:** Implement only after Bee's contract approval. Use TDD and preserve daily scan history as immutable evidence.

**Goal:** Replace overlapping Daily-screener groups with one deterministic trade-story state per symbol, while recording the original breakout event needed to distinguish fresh breaks, retests, and extended moves.

**Architecture:** The scanner remains the sole owner of deterministic Daily classification. Every symbol receives (1) a mutually exclusive `primary_state`, (2) independent `origin` and `stage` attributes, and (3) machine-readable reference, failure, and proof fields. `daily_scan_runs` and `daily_scan_observations` already provide append-only scan evidence; a new append-only breakout lifecycle table records the first qualified event and subsequent state transitions without rewriting past observations.

**Tech Stack:** Python 3.12, PostgreSQL 16, existing `screening.py`/`scanner.py`, FastAPI/dashboard artifact, pytest.

---

## 1. Product contract — plain language

### The rule
A card must answer one question first: **what should the trader wait for now?**

It must not use one label to mix origin, timing, and action. The user sees:

```text
Primary state | Origin | Stage
Reference level | Failure level | Proof needed
```

### User-facing primary states

| Key | Thai / English | Meaning | Required next proof |
|---|---|---|---|
| `breakout_setup` | เตรียมเบรก / Breakout Setup | Price remains below resistance; no qualified Daily breakout event. | Daily close through trigger with required volume. |
| `fresh_breakout` | เบรกใหม่ / Fresh Breakout | First qualified close above the stored trigger; not yet a retest. | Hold above trigger or form a 1H higher low. |
| `breakout_retest` | ย่อทดสอบแนวเบรก / Breakout Retest | After a qualified break, price returns within retest tolerance of the original trigger and has not failed it. | Defended level plus 1H higher low. |
| `breakout_extended` | เบรกยืด รอพัก / Extended Breakout | Qualified break is too far from original trigger or is momentum-extended. | New base or controlled reset; no new chase entry. |
| `trend_pullback` | ย่อในขาขึ้น / Trend Pullback | Qualified trend pulls back to Fib/MA support, but not to the original breakout trigger. | Support defense plus 1H higher low. |
| `base_forming` | สร้างฐาน / Base Forming | Constructive base, but not within the breakout-setup window. | A setup window or a qualified breakout. |
| `no_long_setup` | โครงสร้างไม่ผ่าน / No Long Setup | False break, broken support, invalidation, or no qualified structure. | Reason-specific recovery condition. |

### Independent attributes (never groups)

| Attribute | Values | Purpose |
|---|---|---|
| `origin` | `base`, `continuation`, `reversal`, `unknown` | Where the trade story started. CBG is `reversal`; it is not a duplicate primary group. |
| `stage` | `pre_break`, `fresh`, `retest`, `extended`, `failed`, `none` | Lifecycle maturity. |
| `failure_reason` | `false_breakout`, `broken_support`, `weak_volume_break`, `no_qualified_structure`, `pre_screen_excluded` | Allows a terminal state without hiding why it failed. |
| `proof_needed` | structured `type`, `timeframe`, `level`, and text | Ensures each card states exactly what evidence is missing. |

### State precedence — one state only

Evaluate in this order; first match wins:

```text
pre-screen exclusion (stored separately; not main universe)
→ failed / invalidated / false break → no_long_setup
→ active qualified breakout lifecycle:
   fresh → retest → extended
→ breakout_setup
→ trend_pullback
→ base_forming
→ no_long_setup
```

`origin` is calculated alongside the primary state and never overrides precedence. A reversal-origin stock may therefore be `fresh_breakout`, `breakout_retest`, or `breakout_extended`; its card makes the lower long-term quality explicit.

---

## 2. Deterministic definitions to calibrate by backtest

Use named configuration constants and record their values in the scanner version/source lineage. Initial values are candidates only; do not hard-code a product claim before validation against historic immutable observations.

| Rule | Candidate formula | Purpose |
|---|---|---|
| Qualified fresh break | `close >= original_trigger * (1 + FRESH_CLOSE_BUFFER_PCT)` AND `volume_ratio_50 >= MIN_BREAKOUT_VOLUME_RATIO` | A touch of trigger is not a break. |
| Setup proximity | `0 < (trigger-close)/close <= SETUP_PROXIMITY_PCT` | Shows near/far as a badge inside one setup group. |
| Retest band | `abs(close-original_trigger)/original_trigger <= RETEST_TOLERANCE_PCT` after a qualified event | Retest is explicitly tied to original trigger. |
| Retest failure | Daily close below `original_trigger * (1-RETEST_FAILURE_PCT)` | Reason `false_breakout` or `broken_support`. |
| Extended | Distance from original trigger >= `EXTENDED_FROM_TRIGGER_PCT` OR `RSI >= EXTENDED_RSI` | Stops KCE/RCL-like names being presented as fresh/retest automatically. |
| Trend pullback | Qualified trend and near Fib50/Fib61.8/MA support, but outside retest band | Keeps SRICHA-like pullback distinct from a retest. |
| Base | Range/contraction qualifies but outside setup proximity and has no active event | Prevents TFFIF/SCCC-like near-trigger names being called base. |

The calibration dataset must use complete historical daily scan runs and must report counts/outcomes by threshold set. Do not optimize from a single date.

---

## 3. Current-system gap and required persistence

### Existing evidence

`backend/scan_history.py` already writes immutable full-universe `daily_scan_runs` and `daily_scan_observations`, including the raw scanner payload. This is the correct audit foundation.

### Gap

`backend/scanner.py` currently calculates `breakout_level_20d` as a rolling prior-20-session high. Tomorrow's level can differ from the original break. Therefore it cannot reliably answer:

- when the break first qualified;
- what original level was broken;
- whether price is retesting that level;
- whether the move is extended from that level.

### New append-only lifecycle evidence

Create `daily_breakout_events` with immutable event rows:

```text
id UUID primary key
symbol TEXT not null
origin TEXT not null
trigger_price NUMERIC(18,4) not null  # canonical stored price; never FLOAT
qualified_on DATE not null
qualification_close DOUBLE PRECISION not null
qualification_volume_ratio DOUBLE PRECISION
pre_break_pivot_low NUMERIC(18,4) not null
failure_level NUMERIC(18,4) not null
trend_template_conditions INTEGER
rs_rating DOUBLE PRECISION
scan_run_id UUID references daily_scan_runs(id)
scanner_version TEXT not null
created_at TIMESTAMPTZ not null default now()
unique(symbol, qualified_on, trigger_price, scanner_version)
```

Create `daily_breakout_event_observations` append-only rows for each later daily scan that evaluates an active event:

```text
event_id UUID references daily_breakout_events(id)
scan_run_id UUID references daily_scan_runs(id)
observed_on DATE not null
stage TEXT not null
close DOUBLE PRECISION not null
distance_from_trigger_pct DOUBLE PRECISION
rsi_daily DOUBLE PRECISION
volume_ratio_50 DOUBLE PRECISION
failure_reason TEXT
raw_evidence JSONB not null
unique(event_id, scan_run_id)
```

Use the same mutation-rejection trigger pattern as `scan_history.py`.

---

## 4. Borderline acceptance examples

| Case | Expected primary state | Non-negotiable reason |
|---|---|---|
| AJ closes exactly at trigger | `breakout_setup` | A trigger touch is not a qualified close. |
| TEAM closes above trigger but volume fails threshold | `breakout_setup` | `weak_volume_break` is visible; no fresh break. |
| CBG first qualifies above trigger with high volume, TT incomplete | `fresh_breakout`, `origin=reversal` | Transition quality is visible without suppressing the event. |
| A later CBG close returns to original trigger and holds | `breakout_retest`, `origin=reversal` | Retest is against stored original trigger. |
| RCL is beyond extension threshold / RSI threshold | `breakout_extended` | Prevents chase framing. |
| Fib/MA pullback remains outside original-trigger band | `trend_pullback` | It is not a retest. |
| Close below retest failure band | `no_long_setup`, `failure_reason=false_breakout` | Failure is explicit and auditable. |
| Narrow range but > setup distance | `base_forming` | Base is not used as a near-breakout catch-all. |

---

## 5. Implementation tasks (after Bee approval)

### Task 1: Add pure state-contract tests

**Files:**
- Modify: `backend/test_action_dashboard.py`
- Create: `backend/test_daily_setup_state.py`

**TDD cases:** the eight borderline examples above plus exactly-one-primary-state property test.

**Run:**
```bash
docker compose exec -T backend python -m pytest -q test_daily_setup_state.py test_action_dashboard.py
```

### Task 2: Produce classification evidence in `scanner.py`

**Files:**
- Modify: `backend/scanner.py`
- Test: `backend/test_daily_setup_state.py`

Add deterministic computed evidence, not dashboard labels: trigger, distance to trigger, volume ratio, RSI, Fib/MA references, and structural failure levels. Do not let UI recompute market logic.

### Task 3: Add immutable breakout event persistence

**Files:**
- Modify: `backend/scan_history.py`
- Modify: `backend/app.py` at the existing daily scan persistence path
- Create: `backend/test_breakout_event_history.py`

Write failures first: event insertion, no mutation, transition observation append, and duplicate-event idempotency per scan run. Link every event/observation to the existing immutable scan run.

### Task 4: Replace `group_scan_results` with the contract classifier

**Files:**
- Modify: `backend/screening.py`
- Test: `backend/test_daily_setup_state.py`

Implement precedence in one pure classifier function. Preserve legacy group keys only through an explicit compatibility mapping during UI migration; do not have two competing classifiers.

### Task 5: Update intraday overlay safely

**Files:**
- Modify: `backend/intraday_evaluator.py`
- Test: dedicated classifier tests

Daily owns primary state. Intraday may only update the `proof_needed` status / effective action from stored 60m prices; it must never rewrite the Daily event or origin.

### Task 6: Update dashboard presentation

**Files:**
- Modify: `backend/build_dashboard.py`
- Test: `backend/test_action_dashboard.py`

Render `primary_state`, `origin`, `stage`, `reference_level`, `failure_level`, `proof_needed`, event date, and distance from original trigger. Keep Thai/English labels from the current language dictionary. Do not combine origin and stage into one status label.

### Task 7: Rebuild and live-evidence review

**Files:** generated `backend/scan_results.json`, `backend/dashboard.html` only through supported rebuild.

Run a no-notification scan, persist a full immutable snapshot, rebuild dashboard, then inspect representative CBG / TEAM / AJ / KCE / RCL / SRICHA rows. Verify that no excluded symbol is loaded in the main dashboard.

---

## 6. Validation and non-goals

### Required validation

1. Focused classifier and persistence tests pass.
2. Existing broader suite passes except explicitly documented environment-only tests.
3. Exactly one primary state per evaluated, pre-screen-eligible symbol.
4. Every `fresh_breakout`, `breakout_retest`, and `breakout_extended` cites an immutable event ID and original trigger.
5. Browser verification in Thai and English: primary state, origin, stage, reference, failure, proof are visible and non-overlapping.
6. Backtest report compares outcome distributions by primary state and version; no automatic parameter optimization or execution.

### Non-goals

- No live auto-trading.
- No LLM-generated trading calculation.
- No use of astrology in deterministic state classification.
- No removal of the THB 0.60 / THB 15M pre-screen rules.
- No rewriting historical scan observations or event records.

## Risks and open decisions

- Threshold values must be selected from historical scan evidence, not intuition.
- A rolling 20D trigger can produce overlapping candidate events; event de-duplication and re-arm logic must be explicit.
- Corporate-action anomalies need a source-quality flag and cannot be treated as a technical event without review.

---

## 7. Bee-gate revision — v1 deterministic parameters and lifecycle

These v1 settings are **locked for the first backtest**. They are not claims of optimum values. Any future change requires a new scanner-version string and a separate outcome comparison.

### 7.1 Constants

```python
FRESH_CLOSE_BUFFER_PCT = 0.010        # close must be >= 1.0% above trigger
MIN_BREAKOUT_VOLUME_RATIO = 1.20      # daily volume / 50D average
SETUP_PROXIMITY_PCT = 0.050           # eligible setup window: <=5% below trigger
SETUP_NEAR_BADGE_PCT = 0.030          # visual priority badge inside the setup window
RETEST_TOLERANCE_PCT = 0.030          # ±3.0% around original trigger
MAX_BREAKOUT_RISK_PCT = 0.040          # hard risk cap below original trigger
EXTENDED_FROM_TRIGGER_PCT = 0.080     # >=8.0% over original trigger
EXTENDED_RSI = 75.0                   # daily RSI extension alternative
PULLBACK_FIB_TOLERANCE_PCT = 0.040    # existing 4% observation tolerance
BASE_MAX_RANGE_20D_PCT = 12.0
```

`close`, `trigger`, daily volume, RSI, and Fib levels must come from the same `last_market_date`. The daily scanner evaluates only the most recent committed Daily EOD bar; stored 60m data may change action/proof presentation but cannot create, age, or invalidate a Daily event.

### 7.2 Exact classification and tie-breaks

Pre-screen exclusions (`close < 0.60` or Daily trade value `< 15M`) remain separate, lazy-loaded audit outcomes. They never receive a main-dashboard primary state.

For every remaining symbol, calculate the following values first:

```text
close_buffer = close / rolling_20d_trigger - 1
trigger_distance = close / original_event_trigger - 1  (only with active event)
within_retest_band = abs(close / original_event_trigger - 1) <= 0.03
pre_break_pivot_low = minimum Daily low in the five exchange sessions immediately before the original breakout day (event-time cutoff; no look-ahead)
structural_failure_level = pre_break_pivot_low
risk_cap_level = original_event_trigger * (1 - 0.04)
failure_level = max(structural_failure_level, risk_cap_level)
failed_event = close < failure_level
qualified_break = close_buffer >= 0.01 AND volume_ratio_50 >= 1.20
```

The single-state precedence is exactly:

1. **`no_long_setup`** when an active event is `failed_event`; reason `false_breakout`. It wins over every other condition.
2. **`breakout_extended`** when an active event is not failed and (`trigger_distance >= 0.08` OR `rsi_daily >= 75`). It wins over retest/fresh so RCL-like hot moves cannot appear actionable.
3. **`breakout_retest`** when an active event is not failed, event age is at least one completed Daily session, and `within_retest_band` is true.
4. **`fresh_breakout`** when a new qualifying event was created on this Daily bar, or the active event age is 0–2 completed Daily sessions and it is neither extended nor in the retest band.
5. **`breakout_setup`** when no active event exists and the rolling trigger is available. Add `distance_badge=near` at 0–3% below trigger and `distance_badge=watch` at >3–5% below trigger; a touch or an unconfirmed/low-volume close remains this state with `failure_reason=weak_volume_break` if applicable.
6. **`trend_pullback`** when no active event exists, Trend Template is qualified (8/8), and price is within 4% of Fib50/Fib61.8 or MA20; it must be outside any stored-event retest band by construction.
7. **`base_forming`** when no active event exists, 20D range is <=12%, and the stock is outside the setup window.
8. **`no_long_setup`** in all other cases; reason is `no_qualified_structure` or `broken_support` as applicable.

A same-bar candidate cannot be both `fresh_breakout` and `trend_pullback`: qualified break wins only after it passes both close-buffer and volume requirements. A close that merely reaches a trigger is setup, not fresh.

### 7.3 Event identity, immutability, and re-arm rules

An event ID is a UUID. Its idempotency key uses a **canonical SQL `NUMERIC(18,4)` trigger**, never a binary floating-point value:

```text
(symbol, qualified_on, canonical_trigger_price, scanner_version)
```

Before insert or lookup, the Python classifier quantizes the calculated trigger to four decimal places using Decimal and `ROUND_HALF_UP`. The exact same quantized value is used for event insertion, active-event lookup, and idempotency tests. `daily_breakout_events` must enforce `UNIQUE(symbol, qualified_on, trigger_price, scanner_version)`.

- `daily_breakout_events` is inserted only after `qualified_break` is true.
- A scan retry for the same `scan_run_id` must not insert a second event or observation.
- Every event carries the triggering immutable `scan_run_id`; every later observation carries its own immutable `scan_run_id`.
- An active event is the latest event for a symbol whose latest observation does not have `stage=failed`.
- A later rolling-20D high does **not** supersede an active event. This preserves the original breakout reference for Fresh / Retest / Extended.
- A new event may be created only after the prior active event has an append-only `stage=failed` observation. This is the v1 re-arm rule; it deliberately favors auditability over frequent reclassification.
- No event or observation is updated or deleted. Later knowledge is represented by a new observation row.

### 7.4 Origin is fixed at event creation

Set `origin` once on event insert; it is immutable metadata:

```text
reversal:  Trend Template conditions 4–7 at qualified break
base:      conditions 8 AND 20D range <=12% at qualified break
continuation: conditions 8 AND not base
unknown:   otherwise
```

This makes CBG-style cases representable as:

```text
primary_state=fresh_breakout
origin=reversal
stage=fresh
trend_template_conditions=5
proof_needed=retest_and_1h_higher_low
```

It does not create a special group and does not pre-exclude price below MA200.

### 7.5 State transitions

```text
breakout_setup --qualified_break--> fresh_breakout
fresh_breakout --within retest band after >=1 completed Daily session--> breakout_retest
fresh_breakout/retest --extension condition--> breakout_extended
fresh_breakout/retest/extended --failure condition--> no_long_setup(false_breakout)
breakout_retest --support defense + separate intraday proof--> retains Daily retest; UI action may upgrade only
no_long_setup(false_breakout) --later qualified break--> fresh_breakout with a new event UUID
```

The Daily state does not infer that a retest succeeded solely from a 60m candle. Intraday may record a separate proof/action overlay with full timestamp and source.
- Bee must approve the state contract and threshold-calibration protocol before implementation starts.
