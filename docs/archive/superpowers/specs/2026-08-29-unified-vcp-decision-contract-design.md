# Unified VCP Decision Contract — Design

> **STATUS: APPROVED FOR SPEC REVIEW** · Owner approval: 2026-08-29
> **Scope:** simplify the serving decision spine around the current VCP Finder 60m MVP.
> **Non-goal:** this document does not authorize implementation, deployment, threshold optimization, or removal of audit data yet.

## 1. Problem

Signalix currently has multiple reachable decision vocabularies and two serving analysis paths:

- Daily Trend Template / legacy Daily VCP / Daily readiness
- Stage + Phase + setup quality/proximity + action queue
- isolated 60m VCP Finder with its own state and review lanes
- intraday overlay and replay/shadow policies

These layers contain useful evidence but make the user translate several labels that answer similar questions. The current MVP is VCP-first: `Daily VCP Watchlist` is the fast review surface and `All VCP · 60m` is the full-universe/audit surface.

## 2. Design goal

Create one simple serving decision spine:

```text
Full active ORD
→ sufficient data gate
→ 60m VCP evaluator
→ VCP state + quality
→ Daily context enrichment
→ one decision
→ Daily VCP Watchlist / All VCP · 60m
```

The backend may preserve detailed evidence and compatibility fields. The user-facing contract must answer only:

1. What state is the VCP setup in?
2. What should I do now?
3. What evidence supports that decision?

## 3. Core authority boundaries

### 3.1 VCP 60m is the setup authority

`vcp_finder.py` and its DB adapter remain authoritative for VCP morphology and the setup lifecycle. A VCP state is created from stored 60m evidence, not from an LLM and not from Daily labels.

A 60m `CONFIRMED` result requires the existing 60m gates: sufficient/fresh usable data, 60m trend gate (`trend_pass_60m`), valid VCP structure, close breakout buffer, breakout volume, and intact invalidation. Daily trend must not promote a 60m result to `CONFIRMED`.

### 3.2 Daily is context and lifecycle evidence

Daily EOD contributes supporting context such as trend/MA structure, RS, market regime, liquidity, risk references, and official cross-day event reconciliation. It can explain, warn, or affect presentation priority, but it cannot independently create or promote a 60m VCP state.

### 3.3 Intraday is observation evidence

The latest stored 60m bar and intraday event ledger may enrich current evidence and show an emerging event. They must not rewrite the official Daily EOD record. A closed 60m bar may confirm the VCP entry event; Daily EOD later confirms cross-day lifecycle persistence/reconciliation. These are distinct evidence timestamps, not competing setup classifiers.

### 3.4 Shadow is not serving authority

Sequence-policy shadow and decision-policy shadow remain replay-only until a separately approved promotion decision. They may produce diagnostics but must not create a second user-facing decision.

## 4. Simplified serving contract

### 4.1 Data gate

Use one conceptual field:

```text
data_sufficient: true | false
```

`false` combines stale, not verified, insufficient history, unavailable feed, invalid OHLCV, and other cases where the current evidence cannot support a decision. The raw reason and provenance remain in backend/audit records but are not separate primary user-facing states.

When `data_sufficient=false`, the evaluator must not guess a VCP state or call the setup invalid. The primary Watchlist should not publish it as a review candidate. The Explorer/audit surface may retain the row with neutral/blank setup output and, if needed, one compact `ข้อมูลไม่พอ` indication; it must not expose implementation-specific stale/error taxonomy in the primary contract.

### 4.2 State

The serving VCP state has five setup states:

```text
FORMING       VCP structure is developing; confirmation is absent.
READY         VCP structure is sufficiently formed; breakout confirmation is absent.
CONFIRMED     Closed 60m breakout confirmation passed the required gates.
EXTENDED      Setup may remain valid, but price is too far from the reference for a fresh review.
INVALIDATED   The setup/risk boundary is broken; this setup is no longer valid.
```

No-data is not a sixth setup state. It is `data_sufficient=false`.

### 4.3 Decision

The user-facing decision has three values:

```text
REVIEW   Open/review this setup; evidence is sufficiently actionable to inspect.
WAIT     Do not enter now; a condition, reset, confirmation, or fresh data is pending.
AVOID    Do not use this setup; it is invalidated or structurally/risk-wise broken.
```

Mapping:

| Data/setup condition | State | Decision |
|---|---|---|
| insufficient evidence | blank/neutral | not published as review candidate |
| forming | `FORMING` | `WAIT` |
| formed, breakout absent | `READY` | `WAIT` |
| closed 60m confirmation passed | `CONFIRMED` | `REVIEW` |
| too far above reference / late | `EXTENDED` | `WAIT` |
| failure/invalidation boundary broken | `INVALIDATED` | `AVOID` |

`WAIT` means the thesis is still potentially valid but the entry condition is incomplete. `AVOID` means the thesis/risk boundary has failed. `EXTENDED` always maps to `WAIT`, not `AVOID`.

### 4.4 Quality

Quality is a compact summary of 60m VCP morphology, not a blended score with Daily trend or liquidity:

```text
PASS       60m trend + VCP morphology + contraction/volume structure pass.
PARTIAL    Some structure/event evidence exists, but one or more required gates are incomplete.
FAIL       Evidence is sufficient and the required structure does not pass, or invalidation is broken.
UNKNOWN    data_sufficient=false; cannot evaluate.
```

The underlying evidence remains explicit:

- 60m trend gate (`trend_pass_60m`)
- H-L-H-L-H pivot structure
- contraction ratio and latest contraction depth
- base depth
- leg-volume contraction and volume dry-up
- breakout close/volume confirmation
- pivot, invalidation, and risk coherence

Daily trend, RS, liquidity, marginable, price band, and market regime are separate `daily_context`/`tradability` evidence. They may create warnings or presentation filters but do not silently mutate VCP morphology quality.

### 4.5 Evidence payload

The serving item should expose one compact decision object and preserve detailed evidence separately:

```json
{
  "decision": {
    "state": "READY",
    "decision": "WAIT",
    "quality": "PASS",
    "data_sufficient": true
  },
  "evidence": {
    "timeframe": "60m",
    "trigger": 12.50,
    "invalidation": 11.70,
    "distance_to_trigger_pct": 1.8,
    "volume_confirmation": false,
    "daily_context": {
      "trend": "S2_UPTREND",
      "rs": 82.0
    },
    "provenance": {
      "as_of": "...",
      "source": "intraday_price_data"
    }
  }
}
```

The exact existing field names must be mapped deliberately during implementation; do not add aliases blindly or delete raw evidence.

## 5. User-facing vocabulary

Primary card format:

```text
READY · WAIT
รอ breakout เหนือ 12.50
invalid เมื่อหลุด 11.70
```

```text
CONFIRMED · REVIEW
breakout + volume ผ่านบนแท่ง 60m ปิด
```

```text
EXTENDED · WAIT
รอ reset/retest ก่อน ไม่ไล่ราคา
```

```text
INVALIDATED · AVOID
หลุดระดับ invalidation แล้ว
```

Do not expose these as competing primary labels on the card:

- `BUY/HOLD/OVERBOUGHT/BREAK/WAIT`
- legacy `primary_state`
- `Stage + Phase` as an action lane
- `setup_proximity` as a second decision
- `action_queue` and VCP `review_lane` as competing states
- shadow policy lanes

They may remain in audit/debug payloads or be rendered as secondary evidence only where needed.

## 6. Serving surfaces

### Daily VCP Watchlist

- Uses the unified VCP decision projection.
- Shows review candidates and `WAIT` watch candidates according to current removable presentation filters.
- Does not alter full-universe eligibility when filters are applied.
- Does not publish `AVOID`/insufficient rows as actionable review candidates.

### All VCP · 60m / Explorer

- Uses the same decision projection and same state/quality semantics.
- Retains full evaluated-universe coverage and forming/invalidated/audit evidence.
- Search/filter/sort are presentation operations, not alternate truth creation.

### Legacy Daily surfaces

Former Daily Shortlist/All Stocks Explorer serving labels remain compatibility/rollback paths only. They must not compete with the visible VCP MVP or create a second user-facing decision contract.

## 7. Migration boundary

Implementation must proceed in bounded slices:

1. Add pure contract mapping and tests without changing serving output.
2. Attach Daily context and data sufficiency through explicit fields.
3. Switch the VCP Watchlist/Explorer projection to the unified decision object.
4. Verify full-universe retention, lane/filter behavior, and card/detail parity.
5. Quarantine legacy action/queue labels from visible MVP output while preserving audit/rollback fields.
6. Leave shadow/replay non-serving until a separate promotion review.

No slice may silently change VCP thresholds, run a DB migration, deploy, restart services, or delete legacy evidence unless explicitly scoped and accepted.

## 8. Acceptance criteria

### Contract

- Every sufficient-data serving VCP item has exactly one `state`, one `quality`, and one `decision`.
- `EXTENDED` maps to `WAIT`.
- `INVALIDATED` maps to `AVOID`.
- `CONFIRMED` can only come from closed 60m evidence passing the 60m gates.
- Daily trend/context cannot promote `READY` or `CONFIRMED`.
- Insufficient/stale/unverified evidence is combined under `data_sufficient=false` and does not become `INVALIDATED`.
- `UNKNOWN` quality is reserved for insufficient data; `FAIL` means evaluation completed and failed.

### Evidence and lifecycle

- Trigger and invalidation are present when the state claims they exist.
- Daily EOD and 60m timestamps/source remain distinguishable in provenance.
- Intraday observations do not mutate official Daily truth.
- Existing append-only lifecycle and replay evidence remain intact.

### Product/UI

- Watchlist and Explorer consume the same decision projection.
- Primary cards show state + decision + concise trigger/invalidation reason.
- Legacy labels and shadow lanes do not compete as primary user-facing status.
- Presentation filters do not silently reduce backend/full-universe persistence.
- Insufficient data is not shown with stale/not-verified implementation details in the primary card.

### Verification

- Pure contract tests cover every state/data mapping and contradictory input combination.
- Existing VCP Finder tests remain green.
- Full-universe retention and filter/cap behavior are tested.
- Served `/mvp` and `/api/vcp-finder` are checked after implementation.
- Desktop/mobile user journey and at least one error/insufficient-data path are checked before final PASS.

## 9. Non-goals

- No threshold tuning or strategy optimization.
- No new composite score.
- No LLM-generated calculations or decisions.
- No automatic trading or executable order generation.
- No removal of raw evidence, lifecycle history, or rollback code in the first migration.
- No promotion of shadow-v2 policies in this contract.
- No alert-delivery change.

## 10. Open implementation questions

These are implementation details to resolve in the plan without changing the approved product intent:

1. Which existing serialized fields become the canonical `decision` object and which remain compatibility fields?
2. Where should the one neutral insufficient-data representation live in Explorer while keeping the primary Watchlist clean?
3. Which existing VCP review overlays remain visible as secondary evidence, and how are they prevented from looking like state?
4. How will the unified projection preserve current removable Watchlist filters and full-universe counts?

## 11. Source references

- `vault/VCP-Finder-MVP.md`
- `vault/Execution-Pipeline.md`
- `backend/vcp_finder.py`
- `backend/vcp_finder_db.py`
- `backend/vcp_decision_policy.py`
- `backend/mvp_routes.py`
- `backend/mvp_api.py`
- `backend/mvp_snapshot.py`
- `backend/reconciled_projection.py`
- `backend/scan_history.py`
