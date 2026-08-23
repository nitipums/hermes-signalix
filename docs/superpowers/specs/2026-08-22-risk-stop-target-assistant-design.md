# Signalix Risk/Stop/Target Assistant — Design Spec

**Date:** 2026-08-22
**Status:** Approved by Arm for specification; implementation remains parked in P1 Scheduled.
**Owner:** Signalix product lead (Bee)

## Goal

Give a trader a transparent, deterministic way to inspect entry reference, invalidation, Fibonacci targets, risk per share, and manual position size without turning Signalix into an order-execution system or allowing an LLM to invent numbers.

## Scope

The same assistant UI supports two explicitly separate calculation contracts:

1. **Daily Setup Contract** — official Daily setup state and Daily chart levels.
2. **Intraday 60m Contract** — emerging Intraday event state and 60m chart levels.

Daily and Intraday values must never be mixed. A Daily chart renders Daily levels; a 60m chart renders Intraday 60m levels.

## Calculation contracts

### Common inputs

- `trigger_price`: canonical event/setup trigger; default planned entry.
- `planned_entry`: user-editable entry; defaults to `trigger_price`.
- `system_stop`: canonical `failure_level`, read-only.
- `pivot_low`: verified structural reference when available.
- `planned_stop`: user-selected stop; defaults to `system_stop` and becomes user-specific after editing or selecting Pivot Low.
- `account_size`: manual input only; must not read the private Portfolio module in MVP.
- `risk_percent`: editable manual input, default `1%`.
- confirmed swing anchors: `swing_low`, `swing_high`, `pullback_low` from the contract timeframe.

### Fibonacci target

Use one method for both contracts to avoid multiple confusing patterns:

```text
swing low → swing high → pullback low
```

Calculate and display:

```text
Fib 1.272 extension
Fib 1.618 extension
```

The exact extension calculation must be deterministic and documented in the implementation tests. Only confirmed, closed candles are eligible as anchors. If anchors are incomplete, stale, unavailable, or not tied to a valid scan/event lineage, return `NOT_VERIFIED` and do not draw fabricated levels.

### Stop logic

```text
system_stop = canonical failure_level
planned_stop = system_stop by default
```

`System Stop` is read-only and preserves the canonical lifecycle contract. `Pivot Low` is shown as a structural reference and can be selected as `Planned Stop`.

When the planned stop differs from system stop, show an explicit warning, especially when it creates wider risk:

- `WIDER STOP`
- `STOP ABOVE SYSTEM INVALIDATION`
- `NOT VERIFIED` when the selected level is stale or incomplete.

### Position sizing

```text
risk_budget = account_size × (risk_percent / 100)
risk_per_share = planned_entry − planned_stop
shares = floor(risk_budget / risk_per_share)
```

Reject or mark `NOT_VERIFIED` when entry/stop are missing, risk per share is zero/negative, prices are stale, or account/risk input is invalid. Do not add max-position-value or portfolio policy in MVP.

## Contract-specific behavior

### Daily Setup Contract

- Read Daily trigger, Daily failure level, Daily pivot reference, and Daily Fibonacci anchors.
- Render values only on the Daily card/modal and Daily chart.
- Label: `Daily Setup`.
- Do not substitute 60m anchors when Daily anchors are missing.

### Intraday 60m Contract

- Read the active 60m event trigger, event failure level, event pivot reference, and 60m Fibonacci anchors.
- Use only confirmed 60m candles and current freshness/source/baseline evidence.
- Render values on the stock card and Intraday event modal.
- Label: `Intraday 60m`.
- Do not modify Daily official state and do not use Daily anchors as a fallback.
- New confirmed swings may update the target, but the displayed anchor timestamps and event/run lineage must update together.

## UI contract

### Stock card

Show a compact, decision-first summary:

- `Daily` or `Intraday 60m` badge.
- Entry reference / trigger.
- System stop.
- Fib 1.272 and 1.618 summary.
- Risk status and freshness.
- `NOT_VERIFIED` instead of empty numbers when evidence is insufficient.

### Detail modal

Show full transparent calculation context:

- timeframe and source/freshness
- trigger and planned entry
- System Stop
- Pivot Low
- Planned Stop
- Fib anchor low/high/pullback low
- Fib 1.272 / 1.618 values
- account size and risk budget inputs
- risk per share and calculated position size
- warning states
- anchor/event/scan timestamps and lineage
- disclaimer: calculation aid, not an order or investment recommendation

Manual account/risk inputs are not persisted to public Signalix data and are not read from Portfolio in MVP.

## Chart overlay contract

### Default overlays

```text
Trigger          visible
System Stop      visible as primary stop line
Fib 1.272        visible
Fib 1.618        visible
```

### Conditional overlays

```text
Planned Entry    visible after user edits/enters it
Planned Stop     visible after user edits/selects it
Pivot Low        available in Show Details / optional reference
```

Use distinct line styles/colors and labels at the chart edge. Planned levels must not appear as user-specific values before the user sets them.

- Daily chart → Daily overlays only.
- 60m chart → Intraday 60m overlays only.
- Missing/stale/unverified levels → no misleading line; show `NOT_VERIFIED`.
- Provide legend/toggles if overlays become visually dense.
- Chart must remain readable at desktop and 512px mobile widths.

## Determinism and safety

- All numeric calculations run in deterministic code; LLM may summarize only already-computed fields.
- No buy/sell order, broker integration, trailing stop, ATR stop, or automatic execution in MVP.
- Preserve canonical trigger/failure/event lineage; do not overwrite immutable history.
- Never use current price silently as entry when the trigger is available; current price may be shown as context and chase warning.
- If current price exceeds the setup window, show `AVOID CHASING` rather than silently recalculating the setup.

## Acceptance criteria

1. Daily and Intraday 60m contracts are separate in source, payload, UI labels, and chart overlays.
2. Trigger defaults to planned entry; planned entry remains user-editable.
3. System Stop is canonical/read-only; Pivot Low can be selected as Planned Stop with warnings.
4. Fib 1.272/1.618 targets use one confirmed pullback-extension method and expose all anchors.
5. Missing/stale/incomplete data returns `NOT_VERIFIED`, never fabricated numeric levels.
6. Risk budget defaults to editable 1%; position size uses planned entry and planned stop deterministically.
7. Card and modal show the appropriate contract; no Daily/60m cross-contamination.
8. Chart overlays show default trigger/system stop/Fib targets and conditional planned levels as specified.
9. Desktop and 512px mobile chart/modal remain readable with no page-level horizontal overflow.
10. Focused unit/source tests cover formulas, invalid inputs, stale/missing anchors, contract separation, warnings, and overlay payloads.
11. Real browser tests cover card → modal → input planned stop/entry → overlay update, Daily/60m switching, missing-data state, and mobile layout.
12. Independent Nida QA and Bee final gate verify live contract, served artifact, and rendered user journey before P1 completion.

## Non-goals

- No Portfolio data access or persistence.
- No max-position-value policy in MVP.
- No automatic orders or broker execution.
- No LLM-generated calculations.
- No multiple competing stop/target patterns.
