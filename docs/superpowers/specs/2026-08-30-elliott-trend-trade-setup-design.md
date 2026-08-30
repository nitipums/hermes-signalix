# Signalix Elliott/Trend/Trade-Setup Decision Spine

> **STATUS: OWNER-APPROVED DESIGN — SPEC REVIEW PENDING**
> **Date:** 2026-08-30
> **Scope:** Thai ORD stock setup discovery and preparation
> **Product role:** Signalix finds and prepares candidate trade setups; Arm reviews the chart and makes the final trade decision.

## 1. Problem and rationale

The current serving path is VCP-first. That does not match Arm's actual stock-selection method. VCP is useful evidence, but it is not the main thesis being searched for.

The new primary thesis is:

```text
Strong big-picture trend
→ prior Wave 1 advance
→ Wave 2 pullback/correction
→ early Wave 3 confirmation or continuation
→ trigger + invalidation + Fib target + R:R
→ Arm review and decision
```

The redesign is a clean replacement of the decision spine, not a deletion of useful historical data. Existing OHLCV, Daily/60m data, MA, RS, volume, 52W/ATH, Fib, breakout, risk, and VCP evidence may be reused. Existing VCP serving logic is no longer the product authority.

## 2. Locked design decisions

### 2.1 Timeframe boundary

- **Daily** is authoritative for big-picture trend and Elliott structural candidates.
- **60m** is used for early Wave 3 confirmation, lower-timeframe structure, trigger, and entry timing.
- Daily and 60m evidence remain explicitly separated. A 60m series must not be labelled as Daily evidence.

### 2.2 Elliott state contract

`wave.state` represents structural position only:

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

`INVALIDATED` and `EXTENDED` are not Elliott states. They belong to the trade-setup/risk layer:

- `invalidation` records the price/condition that breaks the thesis.
- setup status may be `FORMING`, `READY`, `TRIGGERED`, `EXTENDED`, `INVALIDATED`, or `DATA_BLOCKED`.

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
minimum interesting: 1:3
preferred:           1:4–1:5
exceptional:         1:8–1:10
```

R:R alone does not make a setup valid. A setup also needs a coherent trigger, a technically meaningful invalidation, sufficient data, and a target derived from an explicit method.

### 2.7 User decision boundary

Signalix prepares a candidate and displays evidence. It does not issue an automatic BUY or create an executable order.

User-facing decision values:

```text
REVIEW
WAIT
AVOID
DATA_BLOCKED
```

`REVIEW` means worth chart review, not permission or a personalized recommendation.

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
  → 60m confirmation, trigger, entry, invalidation, target, R:R, setup status

setup_candidate_contract.py
  → stable API serialization, provenance, freshness, and decision projection
```

Existing risk/Fib utilities and validated data loaders may be adapted behind these boundaries. Legacy classifiers, queues, and VCP lanes must not silently create a second primary decision.

### 3.2 Data flow

```text
Thai ORD universe
  → verified Daily data
  → trend/strength + 52W/ATH + sector/peer context
  → Daily Elliott candidate evidence
  → verified 60m data
  → early-Wave-3 / continuation setup evidence
  → trigger + invalidation + Fib targets + R:R
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
  "decision": "REVIEW",
  "provenance": {}
}
```

### 4.1 Required semantics

- `trend` is primarily Daily evidence.
- `wave.timeframe` is `daily` for the big-picture candidate.
- `setup.timeframe` is `60m` when lower-timeframe data are available.
- `wave.state` uses only the structural Wave states listed above.
- `setup.state` may identify `EARLY_WAVE_3` or continuation setup; this is a setup interpretation, not a second Elliott authority.
- `setup.invalidation` is separate from `wave.state`.
- `bonus_evidence.vcp` is optional supporting evidence.
- `provenance` identifies policy version, source, as-of time/date, and freshness.
- Every numeric output crossing the API boundary must be JSON-safe plain numbers or null.

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
    "state": "WAVE_2_NEAR_COMPLETION",
    "confidence": "PARTIAL",
    "evidence": {
      "prior_advance": true,
      "pullback_depth_pct": 18.2,
      "pullback_duration_days": 27,
      "fib_zone": "0.5-0.618",
      "structure_intact": true
    }
  },
  "setup": {
    "timeframe": "60m",
    "state": "EARLY_WAVE_3",
    "status": "READY",
    "trigger": 12.5,
    "entry_zone": {"low": 12.4, "high": 12.6},
    "invalidation": 11.6,
    "targets": [15.2, 17.8],
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
  "decision": "REVIEW",
  "provenance": {
    "policy_version": "setup-candidates-v1",
    "daily_source": "...",
    "intraday_source": "..."
  }
}
```

The illustrative values are contract examples only, not live market output.

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

The migration must not silently delete historical data or alter old observations. Compatibility fields may remain for audit, but the new API and dashboard must expose one primary contract.

## 6. Testing and acceptance design

### Pure-function tests

- Trend state and strength evidence on rising, flat, falling, and new-high fixtures.
- 52W High and ATH detection, including near-high but not breakout.
- Daily Wave candidate fixtures for Wave 1, Wave 2, early Wave 3, Wave 4, and Wave 5.
- Wave state never emits `INVALIDATED` or `EXTENDED`.
- Setup status emits extension/invalidation separately.
- Sector/peer breadth handles missing peers and does not silently become a hard exclusion.
- Trigger, invalidation, Fib targets, and R:R are deterministic and JSON-safe.
- Insufficient/stale data produces `UNKNOWN`/`DATA_BLOCKED`, not a positive state.

### API tests

- `/api/setup-candidates` returns the complete contract and provenance.
- Daily and 60m evidence are separated by field and timeframe.
- No VCP-only hard gate removes a valid non-VCP candidate.
- Invalid/missing data is explicit.
- Legacy `/api/vcp-finder` is not used as the default `/mvp` data source.

### Served/UI acceptance

After implementation, verify the public route first, then the same user journey at desktop and 390px mobile:

- candidate list loads;
- grouping by Wave/setup lifecycle is understandable;
- card shows trend, rise/high evidence, Wave candidate, trigger, invalidation, targets, R:R, sector/peers, and VCP bonus;
- unknown/data-blocked state is visible and not misrepresented as a setup;
- an API/data failure state is exercised;
- `/mvp` and `/api/setup-candidates` agree on the primary contract.

Source tests alone are not UI acceptance.

## 7. Non-goals for this change

- No live or automatic order execution.
- No LLM-generated Elliott labels or authoritative calculations.
- No claim that an Elliott candidate is objectively confirmed.
- No fundamental/news scoring in the first implementation unless separately approved.
- No expansion beyond the current Thai ORD scope without a new design decision.
- No deletion of VCP data or historical observations.

## 8. Approval gate

This spec is ready for owner review. Implementation begins only after Arm approves this written spec. After approval, create a bounded implementation plan with explicit files, tests, runtime probes, deployment boundary, and rollback/retirement handling.
