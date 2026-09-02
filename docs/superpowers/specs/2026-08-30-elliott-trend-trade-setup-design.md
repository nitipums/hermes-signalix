# Signalix Elliott/Trend/Trade-Setup Decision Spine

> **STATUS: OWNER-APPROVED DESIGN — T1–T9 SOURCE IMPLEMENTED + PROMOTED; ACCEPTANCE SPLIT**
> **Reconciled:** 2026-09-02 · `/api/setup-candidates` and `/mvp` are the canonical promoted surface; the narrow public 390px failure→Retry→recovery journey is PASS. Broader desktop/drawer/chart semantic acceptance and evaluator auto-caller remain separate/not verified.
> **Date:** 2026-08-30 · **Implementation:** 2026-08-31 (T1–T9 source) · **Promotion:** 2026-08-31 (release branch)
> **Scope:** `marginable_long` stock setup discovery and preparation — active Thai ORD ∩ owner-supplied marginable list ∩ `can_buy=true` (currently 237 symbols)
> **Product role:** Signalix finds and prepares candidate trade setups; Arm reviews the chart and makes the final trade decision.

## 1. Problem and rationale

The current serving path is VCP-first. That does not match Arm's actual stock-selection method. VCP is useful evidence, but it is not the main thesis being searched for.

The new primary thesis is:

```text
Strong big-picture trend
→ observable Daily Wave 1–5 structural interpretation
→ prepare Wave 1, Wave 2→3, continuation, and Wave 4→5 opportunities
→ 60m minor structure and pre-trigger plan
→ trigger + trade stop + thesis invalidation + Fib targets + R:R
→ Arm review and decision
```

The redesign is a clean replacement of the decision spine, not a deletion of useful historical data. Existing OHLCV, Daily/60m data, MA, RS, volume, 52W/ATH, Fib, breakout, risk, and VCP evidence may be reused. Existing VCP serving logic is no longer the product authority.

## 2. Locked design decisions

### 2.0 Owner decisions confirmed during design grilling

- `marginable_long` is the real product universe. Active ORD outside it remains explicit audit/rollback coverage and is not part of setup-candidate serving.
- The product separates `DAILY_CANDIDATE` → `SETUP_FORMING` → `REVIEW_NOW`. A valid Daily candidate whose 60m setup is unfinished is not `DATA_BLOCKED`; it is presented as `NO_SETUP_DETECTED` when required Daily/60m data are available but qualifying anchors do not exist.
- Elliott v1 covers observable Wave 1 through Wave 5 structural states, while retaining `UNKNOWN` and explicit uncertainty.
- Wave 1 is a preparation state as well as a structural observation; the system does not wait for Wave 2 before preparing a valid lower-timeframe setup.
- `REVIEW_NOW` is intentionally pre-break: it prepares a complete plan before the trigger. `PRE_TRIGGER` and `TRIGGERED` remain distinct setup states.
- Minimum R:R for `REVIEW_NOW` is 2:1. R:R never overrides structure, freshness, trigger, invalidation, or target-quality gates.
- `WAVE_1_ADVANCE` may reach `REVIEW_NOW` when a fresh 60m base or pullback provides a complete pre-trigger plan with R:R at least 2:1 and price is not extended.
- Both `UPTREND` and `EMERGING_UPTREND` may enter `DAILY_CANDIDATE`; established uptrends rank higher while an emerging trend exposes its missing confirmation evidence.

### 2.1 Timeframe boundary

- **Daily** is authoritative for big-picture trend and Elliott structural candidates.
- **60m** is used for early Wave 3 confirmation, lower-timeframe structure, trigger, and entry timing.
- Daily and 60m evidence remain explicitly separated. A 60m series must not be labelled as Daily evidence.
- Daily exposes one `primary_state` for the medium-to-large Elliott structure. Higher-timeframe context may support it but does not create a competing primary state.
- 60m exposes only `minor_structure` for setup preparation and entry confirmation; it cannot overwrite the Daily primary state.

### 2.2 Elliott state contract

`wave.primary_state` represents the authoritative structural position; `wave.alternative_state` uses the same enum for the next plausible interpretation:

```text
WAVE_1_ADVANCE
WAVE_2_FORMING
WAVE_2_NEAR_COMPLETION
EARLY_WAVE_3
WAVE_3_CONTINUATION
WAVE_4_CORRECTION
WAVE_5_ADVANCE
UNKNOWN
```

The system emits a machine-generated candidate/evidence interpretation, not an unquestionable Elliott count.

Every non-`UNKNOWN` interpretation exposes:

```text
primary_state
confidence: LOW | MEDIUM | HIGH
alternative_state
supporting_evidence[]
contradicting_evidence[]
missing_evidence[]
```

Only `MEDIUM` or `HIGH` confidence may reach `REVIEW_NOW`. `LOW` confidence remains `DAILY_CANDIDATE` or `SETUP_FORMING`.

`INVALIDATED` and `EXTENDED` are not Elliott states. They belong to the trade-setup/risk layer. Setup status is `FORMING`, `PRE_TRIGGER`, `TESTED_TRIGGER`, `TRIGGERED`, `EXTENDED`, `STOPPED`, `INVALIDATED`, `EXPIRED`, or `DATA_BLOCKED`; `trade_stop` and `thesis_invalidation` remain separate. `STOPPED` closes one Setup Attempt while its Candidate Thesis may remain valid; `INVALIDATED` means the larger thesis or required setup structure failed.

### 2.3 Trend and strength are first-class inputs

The primary scan must surface:

- uptrend or emerging uptrend;
- 20-day and 60-day advance/strength;
- relative strength;
- distance to 52W High;
- 52W High breakout;
- ATH breakout;
- distance from the breakout/high reference.

52W High/ATH is strong evidence and ranking input, but not an unconditional hard filter. A stock in a valid Wave 2 pullback may not yet be at a new high.

The prior 52W/ATH reference is derived from historical `High`, not historical `Close`. A current session that trades through the reference but does not close above it is `TESTED_HIGH`; `BREAKOUT` requires the current `Close` to finish above the prior reference.

### 2.4 Sector and peer context

Context includes same-sector/industry peers:

```text
sector
industry
peer_symbols
sector_trend
peer_trend_breadth
peer_breakout_count
sector_leader_or_laggard
relative_strength_vs_sector
```

Peer context is initially evidence and ranking context, not an automatic exclusion gate. A sector warning may reduce priority or appear as risk context without silently removing the strongest leader.

### 2.5 VCP role

VCP, contraction, and breakout-volume evidence are retained as `bonus_evidence`. VCP must not be a hard gate that removes a candidate which otherwise fits Trend + Elliott candidate + Trade Setup.

### 2.6 R:R contract

The deterministic risk engine supplies trigger/entry, invalidation/stop, targets, risk, reward, and R:R.

Initial display bands:

```text
minimum review:      1:2
lower priority:      1:2–<1:4
preferred:           1:4–<1:8
exceptional:         1:8+
```

R:R alone does not make a setup valid. A setup also needs a coherent trigger, a technically meaningful invalidation, sufficient data, and a target derived from an explicit method.

Risk and thesis invalidation remain separate:

- `trade_stop` is the 60m structural level used for trade risk and R:R.
- `thesis_invalidation` is the Daily structural level or condition that breaks the larger trend/Elliott interpretation.
- A stopped setup is immutable. If the Daily thesis remains valid, a later opportunity creates a new setup instance rather than rewriting the stopped one.

Targets are ordered by technical proximity:

- `target_1` is the nearest technically valid target and alone determines whether minimum R:R is at least 2:1.
- `target_2` is a Daily structural/Fib projection.
- `target_3` is an extended Wave projection when supported.

A distant target cannot compensate for `target_1` failing the minimum R:R gate.

### 2.7 Elliott v1 detection policy

Elliott v1 uses a conservative observable proxy. It derives candidates only from measurable prior advance, retracement/Fib zone, correction duration, confirmed swing structure, structure integrity, and 60m breakout/confirmation evidence. It must not claim that a wave count is objectively confirmed.

Owner-tuned 2026-09-01 Wave-3 publication boundary:
- The canonical detector publishes only `EARLY_WAVE_3`, `WAVE_3_CONTINUATION`, or fail-closed `NOT_VERIFIABLE`. Wave 1/2 anchors are prerequisites/evidence, not public primary states. The prior full-wave interpretation may remain only in an explicit audit/compatibility namespace.
- Required Daily structure is strictly ordered `W1 low -> W1 high -> W2 low`, with `W1_low < W2_low < W1_high`, a significant advance, and a 23.6%–78.6% retracement. Centred pivots are usable only after their right-hand confirmation bars exist.
- `EARLY_WAVE_3` requires a valid W1/W2 sequence approaching/testing the W1 high without sustained confirmation. `WAVE_3_CONTINUATION` requires final Daily closes above W1 high with follow-through. A wick never confirms.
- A confirmed post-impulse correction is excluded as `NOT_VERIFIABLE`; it must not remain Wave 3 continuation. MA and volume affect confidence only and never create state.

Owner-tuned 2026-08-31:
- Wave 1: `measurable_advance` from confirmed swing engine (no fixed % threshold; C) — engine must not require `prior_advance + confirmed_swing_anchors + structure_intact` simultaneously to reach MEDIUM.
- Wave 2 `NEAR_COMPLETION`: retracement 30-60% of Wave 1 (Fib 0.382-0.618), duration 5-25 days, low holds above Wave 1 swing low; <30% = `WAVE_2_FORMING`, >60% or break of Wave 1 low = `WAVE_4_CORRECTION`/`UNKNOWN`.
- Early Wave 3 / Continuation: Daily `Close` above Wave 1 high (High wick alone = `TESTED_HIGH`), with breakout volume >20-day average as supporting evidence. Broad discovery or owner-specific Elliott thresholds beyond this require a later, separately approved policy change.

### 2.8 User decision boundary

Signalix prepares a candidate and displays evidence. It does not issue an automatic BUY or create an executable order.

User-facing decision values:

```text
REVIEW_NOW
SETUP_FORMING
DAILY_CANDIDATE
WAIT
AVOID
DATA_BLOCKED
```

`REVIEW_NOW` means worth chart review, not permission or a personalized recommendation.

### 2.9 Session-aware freshness

Freshness follows the exchange session calendar rather than raw wall-clock age:

- Daily evidence is current when it contains official EOD truth for the latest completed trading day.
- During an open session, 60m evidence must contain the latest completed interval required by the fetch cadence.
- After market close, the final-session observation is required.
- Through weekends and exchange holidays, the final observation from the latest completed trading day remains current.
- Missing required data that should exist for the completed session produces an explicit data reason (`NO_DAILY_DATA`, `NO_60M_DATA`, `DAILY_STALE`, `60M_STALE`, or `60M_INVALID`) and `DATA_BLOCKED`; an exchange closure alone is not stale data.
- Available Daily/60m data without qualifying 60m anchors produces `NO_SETUP_DETECTED` and maps to `SETUP_FORMING` or `DAILY_CANDIDATE`, not generic `DATA_BLOCKED`.
- Invalid Fib/risk inputs that prevent a safe plan produce `RISK_INVALID`; they must never silently become a valid setup or use a legacy fallback.

### 2.10 Trigger, entry zone, and extension

- `trigger` is a 60m structural pivot or resistance level.
- `TESTED_TRIGGER` means price traded above the trigger before a completed 60m candle closed above it.
- `TRIGGERED` requires a completed 60m candle to close above the trigger.
- Volume is supporting evidence and never a standalone hard gate.
- Define `1R = trigger - trade_stop` for a long setup.
- The valid post-trigger entry zone ends at `trigger + 0.5R`, while R:R to `target_1` remains at least 2:1.
- Price beyond `trigger + 0.5R`, or R:R to `target_1` below 2:1, produces `EXTENDED` / `DO_NOT_CHASE`.

### 2.11 Decision-first projection and market context

The primary presentation order is:

```text
REVIEW_NOW · PRE_TRIGGER
REVIEW_NOW · TRIGGERED
SETUP_FORMING
DAILY_CANDIDATE
DATA_BLOCKED / AVOID
```

Within a lane, use explainable lexicographic ordering rather than one opaque score: Elliott confidence → established/emerging trend → trigger proximity → target-1 R:R → trend strength/RS/52W-ATH → sector/peer context → VCP bonus.

The compact card projection follows the same hierarchy: show only symbol, canonical
decision lane, setup/trigger readiness, and the essential plan (R:R, target 1,
trade stop). Full Daily trend/Elliott evidence, market and peer context, bonus
evidence, provenance, and unavailable detail remain in the drawer. Missing values
use explicit `Unavailable`/`NOT_VERIFIED` states; the card never infers them.

Market regime changes warnings, ordering, and confirmation strictness. It never removes a valid `DAILY_CANDIDATE` or blanket-blocks `REVIEW_NOW`; individual leaders can remain reviewable in a defensive regime. Only invalid market data, a market halt, or another explicit inability to evaluate produces `DATA_BLOCKED`.

### 2.12 Candidate, setup, and owner-review lifecycle

Separate the long-lived Daily thesis from each entry attempt:

```text
candidate_id = one Daily trend/Elliott thesis
setup_id     = one immutable entry attempt under that thesis
```

- A Candidate Thesis has no fixed-day expiry. It remains while its trend/structure is valid and receives a ranking decay when structural progress stalls.
- Every pre-trigger setup is revalidated on each completed 60m interval.
- A setup expires when its trigger/stop/target structure changes materially, the thesis is invalidated, required data becomes non-current, or R:R to `target_1` falls below 2:1.
- Changed levels close the old setup and create a new `setup_id`; stopped, expired, and invalidated attempts remain immutable.
- All machine snapshots and lifecycle events are append-only.

Arm review is a separate append-only event attached to the exact machine snapshot:

```text
AGREE | WATCH | DISAGREE_WAVE | REJECT_SETUP | MISSED_CANDIDATE | NOTE
```

The event records review time, machine snapshot identity, Arm's selected interpretation when applicable, and reason/note. Owner feedback may inform a later policy version but never rewrites the historical machine result.

## 3. Canonical serving architecture

The new canonical API is:

```text
/api/setup-candidates
```

The `/mvp` dashboard will consume this contract. The existing `/api/vcp-finder` route remains available only as a legacy/audit surface during migration and is not the default decision authority.

### 3.1 Engine boundaries

```text
trend_strength_engine.py
  → Daily trend, rise, RS, 52W/ATH, sector/peer context

elliott_structure_engine.py
  → Daily Wave 1–5 candidate/evidence

trade_setup_engine.py
  → 60m minor structure, trigger, entry zone, trade stop, targets, R:R, setup status

setup_candidate_contract.py
  → stable API serialization, provenance, freshness, and decision projection
```

Existing risk/Fib utilities and validated data loaders may be adapted behind these boundaries. Legacy classifiers, queues, and VCP lanes must not silently create a second primary decision.

### 3.2 Data flow

```text
marginable_long universe (237)
  → verified Daily data
  → trend/strength + 52W/ATH + sector/peer context
  → Daily Wave 1–5 primary/alternative Elliott evidence
  → verified 60m data
  → minor structure and pre-trigger setup evidence
  → trigger + trade stop + thesis invalidation + Fib targets + R:R
  → VCP bonus enrichment
  → one setup-candidate contract
  → /api/setup-candidates
  → /mvp + Arm review
```

Official Daily EOD truth and current 60m observations remain separate. Missing, stale, invalid, or insufficient data must produce an explicit blocked/unknown result rather than a positive candidate.

## 4. API contract

Each item contains these top-level groups:

```json
{
  "symbol": "ABC",
  "as_of": "2026-08-30",
  "data_status": {},
  "trend": {},
  "wave": {},
  "setup": {},
  "context": {},
  "bonus_evidence": {},
  "decision_lane": "REVIEW_NOW",
  "provenance": {}
}
```

### 4.1 Required semantics

- `trend` is primarily Daily evidence.
- `wave.timeframe` is `daily` for the big-picture candidate.
- `setup.timeframe` is `60m` when lower-timeframe data are available.
- `wave.primary_state` and `wave.alternative_state` use only the structural Wave states listed above.
- `wave.primary_state` is the Daily authority; `wave.alternative_state` is explicitly non-authoritative.
- `setup.minor_structure` is lower-degree 60m evidence and cannot replace `wave.primary_state`.
- `setup.trade_stop` and `setup.thesis_invalidation` are separate from `wave.primary_state`.
- `bonus_evidence.vcp` is optional supporting evidence.
- `provenance` identifies policy version, source, as-of time/date, and freshness.
- `data_status` carries a deterministic `reason_code` for data availability/freshness: `NO_DAILY_DATA`, `NO_60M_DATA`, `DAILY_STALE`, `60M_STALE`, `60M_INVALID`, or `NONE` when required inputs are available.
- `setup` carries a deterministic `reason_code` for setup readiness/risk: `NO_SETUP_DETECTED`, `RISK_INVALID`, or another explicit setup reason; `NONE` means no blocking setup reason.
- `NO_SETUP_DETECTED` is user-facing “No setup detected yet” and maps to `SETUP_FORMING`/`DAILY_CANDIDATE` when Daily evidence is valid. `RISK_INVALID` is user-facing “Risk invalid” and remains non-actionable.
- `DATA_BLOCKED` is reserved for unavailable, stale, invalid, or incoherent required evidence. It must not be used as a generic synonym for “no qualifying setup.”
- The canonical route has **no fallback** to legacy snapshots, legacy projections, or legacy decision fields. If the canonical builder/artifact is unavailable, return an explicit transport/build error; never relabel legacy output as setup candidates.
- List requests default to `page_size=50`; response metadata always preserves full `eligible_count`, `evaluated_count`, `total_items`, lane counts, and returned page count. Heavy wave evidence is loaded through detail/chart paths.

Illustrative item:

```json
{
  "symbol": "ABC",
  "as_of": "2026-08-30",
  "data_status": {
    "sufficient": true,
    "freshness": "fresh",
    "source": "daily_eod+60m"
  },
  "trend": {
    "state": "uptrend",
    "rise_20d_pct": 18.4,
    "rise_60d_pct": 42.1,
    "relative_strength": 91,
    "near_52w_high": true,
    "is_52w_high_breakout": false,
    "is_ath_breakout": false
  },
  "wave": {
    "timeframe": "daily",
    "primary_state": "WAVE_2_NEAR_COMPLETION",
    "alternative_state": "WAVE_4_CORRECTION",
    "confidence": "MEDIUM",
    "supporting_evidence": ["prior_advance", "fib_retracement", "structure_intact"],
    "contradicting_evidence": [],
    "missing_evidence": []
  },
  "setup": {
    "timeframe": "60m",
    "minor_structure": "PULLBACK_BASE",
    "status": "PRE_TRIGGER",
    "trigger": 12.5,
    "entry_zone": {"low": 12.5, "high": 12.95},
    "trade_stop": 11.6,
    "thesis_invalidation": 10.8,
    "targets": [
      {"name": "target_1", "price": 15.2, "method": "nearest_structure"},
      {"name": "target_2", "price": 17.8, "method": "daily_fib_projection"}
    ],
    "rr": {"to_target_1": 3.0, "to_target_2": 5.9}
  },
  "context": {
    "market_regime": "NEUTRAL",
    "sector": "Electronic Components",
    "industry": "...",
    "peer_trend_breadth": "6/10",
    "sector_leadership": "LEADER"
  },
  "bonus_evidence": {
    "vcp": {"present": true, "quality": "PARTIAL"},
    "breakout_volume": "PENDING"
  },
  "decision_lane": "REVIEW_NOW",
  "provenance": {
    "policy_version": "setup-candidates-v1",
    "daily_source": "...",
    "intraday_source": "..."
  }
}
```

### 4.2 Chart-ready Elliott evidence contract

Every candidate may expose `wave_markers[]` as normalized chart evidence produced by the same Daily wave snapshot:

```json
{
  "id": "wave1_low",
  "kind": "STRUCTURAL_ANCHOR",
  "timeframe": "1D",
  "timestamp": "2026-08-01T00:00:00+07:00",
  "price": 16.5,
  "label": "Wave 1 low",
  "wave_role": "WAVE_1",
  "source": "elliott_structure_engine",
  "confidence": "MEDIUM",
  "evidence_refs": ["measurable_advance", "structure_intact"],
  "snapshot_id": "..."
}
```

The first implementation must support markers for Wave 1 low/high, Wave 2 pullback low, Wave 3 close confirmation, tested-high/structure-break, trigger, trade stop, and thesis invalidation. Each marker uses an exact candle timestamp and price; positional indices alone are not a sufficient API contract. The UI provides a toggleable Wave Evidence layer and click-to-explain content showing the rule, evidence, alternative state, missing evidence, policy/variant, and snapshot identity. Daily markers appear only on compatible Daily charts; 60m markers require explicit mapping and otherwise show not-mapped/unavailable.


## 5. Migration and retirement boundary

### Retain/reuse

- instrument/universe and market scope;
- Daily and 60m OHLCV ingestion and freshness/provenance;
- MA, RS, rise, volume, 52W/ATH, breakout evidence;
- Fib, risk, stop, target, and R:R math;
- sector/industry membership where authoritative;
- VCP calculations as supporting evidence;
- append-only observations and lifecycle/outcome foundations.

### Replace or quarantine from primary serving

- VCP-first default selection;
- VCP state/lane as the main user decision;
- legacy Stage/Phase, Daily primary state, setup proximity, action queue, and multiple ranking formulas when they compete as visible truth;
- any route that silently filters out non-VCP candidates;
- any Daily-labelled metric calculated from 60m fallback data.

The migration must not silently delete historical data or alter old observations. Compatibility fields may remain for audit, but the new API and dashboard must expose one primary contract. The canonical route has no fallback to legacy snapshots, legacy projections, or legacy decision fields. If the canonical builder/artifact is unavailable, return an explicit transport/build error; never relabel legacy output as setup candidates.

### 5.1 One-day legacy retirement boundary

- Hide the VCP tab from primary navigation immediately.
- Keep `/api/vcp-finder` audit-only for one day with explicit deprecation status.
- During the one-day window, run route/import/timer/consumer reuse audit, including accidental reuse of old functions by canonical paths.
- After the window, remove or return 410 only for paths with zero canonical consumers and documented rollback/audit retention, after Arm sign-off.

## 6. Testing and acceptance design

Acceptance proceeds through three evidence layers before production implementation is accepted:

1. **Deterministic fixtures:** Wave 1–5, ambiguous/invalid evidence, stale/session-closed/holiday cases, tested breakout, pre-trigger, triggered, and extended behavior.
2. **Historical replay:** all 237 `marginable_long` symbols across multiple market regimes with strict no-lookahead and explicit inclusion/exclusion reasons.
3. **Owner chart review:** representative Wave 1–5, `REVIEW_NOW`, `SETUP_FORMING`, false-positive, missed-candidate, and `DATA_BLOCKED` cases labelled with Arm review events.

Algorithmic swing, confidence, and threshold questions that cannot be settled from documents alone must pass a read-only throwaway prototype/replay before production code is rewritten.

### 6.1 Served performance and pagination acceptance

- Release warm canonical API target: ≤1s.
- Release cold canonical API target: ≤15s; strict cold ≤3s remains a future optimization target.
- First meaningful UI target: ≤2s.
- Default list page size: 50; pagination must make all 237 eligible rows reachable while preserving full-universe metadata.
- List payload target: roughly ≤200–300KB; heavy `wave.evidence` and chart markers load on detail/chart interaction.
- Measure cold/warm/post-ingestion latency, payload bytes, DB query count, build stage timings, and concurrent single-flight behavior separately.

### Pure-function tests

- Trend state and strength evidence on rising, flat, falling, and new-high fixtures.
- 52W High and ATH detection, including near-high but not breakout.
- Daily Wave candidate fixtures for Wave 1, Wave 2, early Wave 3, Wave 4, and Wave 5.
- Wave state never emits `INVALIDATED` or `EXTENDED`.
- Setup status emits extension/invalidation separately.
- Sector/peer breadth handles missing peers and does not silently become a hard exclusion.
- Trigger, invalidation, Fib targets, and R:R are deterministic and JSON-safe.
- Insufficient/stale data produces explicit reason codes and `UNKNOWN`/`DATA_BLOCKED`; `NO_SETUP_DETECTED` remains non-blocked when required evidence is available.
- Invalid Fib/risk inputs produce `RISK_INVALID` and never use a legacy fallback.

### API tests

- `/api/setup-candidates` returns the complete contract and provenance.
- Daily and 60m evidence are separated by field and timeframe.
- `data_status.reason_code` distinguishes `NO_DAILY_DATA`, `NO_60M_DATA`, `DAILY_STALE`, `60M_STALE`, `60M_INVALID`, and `NONE`.
- `setup.reason_code` distinguishes `NO_SETUP_DETECTED` and `RISK_INVALID`; valid Daily/60m data without anchors never becomes generic `DATA_BLOCKED`.
- Canonical route has no legacy snapshot/projection fallback and returns explicit build/transport error when unavailable.
- Pagination defaults to 50 and full metadata preserves all 237 evaluated rows and lane counts.
- No VCP-only hard gate removes a valid non-VCP candidate.
- Invalid/missing data is explicit.
- Legacy `/api/vcp-finder` is not used as the default `/mvp` data source.

### Served/UI acceptance

After implementation, verify the public route first, then the same user journey at desktop and 390px mobile:

- candidate list loads;
- default page shows 50 rows with reachable pagination and full-universe metadata;
- grouping by Wave/setup lifecycle is understandable;
- card shows trend, rise/high evidence, Wave candidate, trigger, invalidation, targets, R:R, sector/peers, and VCP bonus;
- Wave Evidence toggle shows timestamp/value markers and click-to-explain rule/evidence/snapshot;
- unknown/data-blocked, `NO_SETUP_DETECTED`, and `RISK_INVALID` states are visible and not misrepresented as a setup;
- an API/data failure state is exercised;
- `/mvp` and `/api/setup-candidates` agree on the primary contract;
- VCP tab is absent from primary navigation after migration card A.

Source tests alone are not UI acceptance.

## 7. Non-goals for this change

- No live or automatic order execution.
- No LLM-generated Elliott labels or authoritative calculations.
- No claim that an Elliott candidate is objectively confirmed.
- No fundamental/news scoring in the first implementation unless separately approved.
- No expansion beyond the current Thai ORD scope without a new design decision.
- No deletion of VCP data or historical observations.

### First-release boundary

The first release includes the decision-first dashboard, candidate evidence/detail, Daily plus 60m chart context, owner review events, saved/watch candidates, and historical machine snapshots. Notifications/alerts, automatic policy tuning, broker/order execution, and public multi-user SaaS remain out of scope.

## 8. Approval and implementation gate

This spec was owner-approved for refinement on 2026-09-01 after independent Lite/Ploy/Codex review. Q1–Q14 are settled at product-intent level; Lite + Codex own technical field/enum details. Before implementation, publish bounded tickets with real blocking edges and have Lite manage Kanban. Codex implements only the current ticket with explicit `-m gpt-5.6-luna`, TDD, and no deploy/restart/DB write unless separately approved. Lite independently reviews source, tests, runtime, API, browser, mobile, and failure state; Ploy challenges trader/risk semantics where relevant.

The implementation cards must be sequenced after `to-tickets`, not inferred from this spec alone. No code fix, deletion, fallback removal, deployment, or migration is authorized by the spec until the ticket is dispatched through the Lite-managed Kanban flow.
