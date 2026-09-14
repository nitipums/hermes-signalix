# Signalix Main Trend Taxonomy — Daily Multiple-MA Calibration

> **STATUS: OWNER-APPROVED SPEC** · 2026-09-13 ICT
> **Owner:** Arm · **Final gate:** Lite
> **Scope:** deterministic Daily Main Trend 1–4 classification from multiple moving averages.
> **Calculation authority:** `../current/2026-09-13-main-trend-calculation-contract.md` owns exact formulas, predicates, precedence, and verification semantics.
> **Product boundary:** current Trend Map remains public, read-only, and non-actionable.

## Problem Statement

The current Trend Map machine lanes (`S1_1`, `S1_2`, `S2_2`, `S3_3`, `S4_1`) do not match Arm's visual reading of the Daily chart. The current classifier relies too heavily on MA20/MA60, RSI, support, and a legacy lane graph, so visually different structures are assigned to the same lane. Examples include symbols Arm identifies as Main Trend 1, 3, or 4 while the served artifact assigns `S4_1` or `S2_2`.

The first correction is to establish four broad visual Main Trends from deterministic multiple-MA evidence before introducing any subtype such as `1.1`, `1.2`, `2.1`, `2.2`, `4.1`, or `4.2`.

## Owner-Confirmed Main Trend Model

Main Trend is a visual evidence taxonomy, not Elliott truth and not an order instruction.

```text
Main 1 → base / weak / damaged; no reliable bullish multi-MA alignment
Main 2 → recovery through bullish advance; includes former 1.2, 2.1, and 2.2
Main 3 → pullback / weakening / distribution while long-term structure is not broken; includes former 4.1
Main 4 → genuine continuous bearish deterioration / breakdown; similar to former 4.2
```

Interpretation for overlapping cases:

- Recovery or starting to move upward belongs to Main 2.
- Pullback or distribution inside an intact long-term structure belongs to Main 3.
- Main 4 is reserved for sustained structural deterioration, not a single close below MA20.
- Main 1 has no `1.2` subtype in this phase.

## Inputs and Determinism

- Input timeframe: completed Daily candles only.
- Primary input values: Daily Close and deterministic SMA5, SMA10, SMA20, SMA50, SMA100, and SMA200.
- MA values are produced by the existing deterministic technical-indicator source/code. The browser and LLM do not calculate or infer financial values.
- MA relationship uses both relative ordering and slope.
- Slope measurement uses the change over 20 completed Daily bars.
- SMA50 is the medium structure; SMA100 and SMA200 are the long regime. A
  separate 260-candle Daily OHLCV window may provide 52-week coverage, but is
  never an MA and is not mixed into Main Trend.
- Pullback, extension, break, entry, target, and exit price-action semantics
  remain separate evidence and are outside this MA-only trend explanation.
- If one or more MA values are unavailable, classification may use the available values but must expose `evidence_quality=PARTIAL`; it must not claim full MA alignment.
- Numeric boundaries for ordering tolerance, slope tolerance, distance, and continuity remain calibration-open and must be established from the owner-labelled diagnostic matrix. No arbitrary threshold is promoted by this spec.

## Output Contract

- Each symbol receives one Main Trend value: `1`, `2`, `3`, or `4`.
- The result includes deterministic supporting MA evidence, used periods, slope window, evidence quality (`FULL` or `PARTIAL`), as-of, source timeframe, and policy version.
- This phase replaces the legacy machine lane as the main trend classification only after implementation and acceptance. It does not create an action lane.
- Current Trend Map remains `PRODUCTION_READ_ONLY`, `research_only=false`, and `actionability=NONE`.
- No `BUY_NOW`, `SELL_NOW`, `REVIEW_NOW`, order, broker, alert, portfolio, or auto-trading semantics are part of this spec.

## Initial Owner-Labelled Examples

These examples are chart-review labels used to build and validate the diagnostic matrix; they are not truth claims about Elliott waves.

```text
Main 1:
  MASTER, AURA

Main 1.1 history to be subsumed/validated under Main 1 or Main 2:
  SISB, CKP, DOHOME, HENG, M, MC, ORI, PM

Main 1.2 history to be subsumed under Main 2:
  RJH, KCG, DELTA, CPI, BTG, ERW, FUTURERT

Main 2 visual examples:
  SSP, KCE, TPIPL, SPCG, HANA, KSL, AKR, TC, GFPT,
  PR9, CPF, AMATA, CRC, EKH, PTT, TOP

Main 3:
  MAJOR, SPREME, TFM, CPAXT, SAT, PRM, DRT, PTL, TTB,
  KKP, BA

Main 4:
  BEM, MRDIYT, TURBO

Main 4.1 history to be subsumed under Main 3:
  EPG, AEONTS, SCB, KBANK, INSET, FORTH, GULF, JAS
```

The labels above are a bounded starting set. Unreviewed symbols remain unlabeled in the diagnostic output rather than being assigned from legacy lanes by assumption.

## Testing Decisions

The primary test seam is the deterministic classifier/builder that accepts Daily Close plus MA evidence and returns one Main Trend plus evidence metadata. Tests must use literal expected labels from owner-reviewed examples and must not derive expectations from implementation constants.

Required behavior coverage:

1. Main 1 base/weak/damaged examples.
2. Main 2 recovery and bullish-advance examples, including former 1.2/2.1/2.2 groups.
3. Main 3 intact-long-term pullback/distribution examples, including former 4.1.
4. Main 4 continuous deterioration/breakdown examples, including former 4.2.
5. Partial MA input returns `PARTIAL` evidence quality and never claims full alignment.
6. Twenty-completed-Daily-bar slope semantics and no-lookahead behavior.
7. One-symbol/one-main-trend output and deterministic repeatability.
8. Explicit preservation of read-only/non-actionable Trend Map semantics at the API/UI acceptance seam after implementation.

Diagnostic evidence must compare the legacy served lane, owner Main Trend label, MA ordering, Close-vs-MA position, 20-bar slopes, missing periods, and unresolved/ambiguous reason. The diagnostic matrix is not a forward win-rate or production performance claim.

## Out of Scope

- Main Trend subtypes (`1.1`, `2.1`, `2.2`, `4.1`, `4.2`).
- Action lanes, `BUY_NOW`, `SELL_NOW`, `WATCH`, `HOLD`, or `REVIEW_NOW`.
- Elliott/Wave truth, setup candidates, `/mvp`, or `/api/setup-candidates`.
- RSI, MACD, volume, support, fundamentals, and automatic parameter search in the first MA-only calibration slice.
- PR9/3BBIF chart fallback and mobile RSI rendering; those are separate bounded chart issues already parked in the worktree.
- Deployment, restart, migration, database writes, commit, push, alerts, broker execution, and auto-trading.

## Current implemented calibration — v6 · 2026-09-13

Exact formulas, predicates, precedence, and verification semantics are owned by `../current/2026-09-13-main-trend-calculation-contract.md`. The current implementation uses the canonical MA5/10/20/50/100/200 set, 20 completed Daily bars for slope, MA50 as medium structure, and MA100/MA200 as long regime. It preserves `FULL/PARTIAL` evidence and the public read-only/non-actionable boundary. Historical v2 calibration notes below are retained as implementation history only.

## Acceptance Boundary

This spec is complete only when the owner accepts the Main Trend examples and the deterministic input/output contract. Implementation requires a separate bounded ticket with test-first evidence. Production promotion requires separate source, API, data, browser, and non-actionable safety gates. A diagnostic or replay PASS does not by itself promote the new taxonomy to the served production artifact.
