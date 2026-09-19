# Signalix Main Trend — Deterministic Calculation Contract

> **STATUS: CURRENT** · `CANONICAL_FOR: Main Trend calculation semantics`
> **Owner:** Arm · **Final gate:** Lite
> **Policy:** `main-trend-ma-calibration-v6`
> **Scope:** Daily Main Trend evidence only; not an order or action instruction.

## 1. Product boundary

Main Trend is a deterministic visual-evidence taxonomy for explaining a stock's Daily trend. It is machine-generated candidate/evidence, not truth, Elliott/Wave confirmation, a buy/sell signal, or an order.

The current production surface remains public, read-only, and non-actionable:

```text
status=PRODUCTION_READ_ONLY
research_only=false
actionability=NONE
```

This document defines the formula and decision precedence. Price action such as pullback, extension, breakout, trigger, target, and exit is a separate contract and is not calculated here.

## 2. Canonical inputs

Input timeframe: completed Daily candles only.

Canonical moving averages:

```text
MA5, MA10, MA20, MA50, MA100, MA200
```

Roles:

```text
short:  MA5, MA10, MA20
medium: MA50
long:   MA100, MA200
```

The classifier does not use MA60, MA120, or MA240. A `260`-candle Daily window is separate 52-week OHLCV coverage; it is not an MA and is not an input to Main Trend classification.

## 3. Exact calculations

### 3.1 Simple moving average

For period `P` at completed Daily index `t`:

```text
SMA_P(t) = (Close[t-P+1] + ... + Close[t]) / P
```

The result is unavailable until `P` completed Daily closes exist. Values are aligned to the ending candle and use no future candle.

### 3.2 Twenty-Daily-bar slope

For every canonical MA period `P`:

```text
slope_P_20d_pct = (SMA_P(t) / SMA_P(t-20) - 1) * 100
```

The prior point is exactly 20 completed Daily bars before the current point. A zero/missing/non-finite prior or current MA makes the slope unavailable.

### 3.3 Close position

For each MA:

```text
ABOVE  when Close[t] > SMA_P(t)
BELOW  when Close[t] < SMA_P(t)
UNAVAILABLE when either value is unavailable
```

Equality is not treated as `ABOVE`.

### 3.4 MA ordering

Short-to-long ordering is evaluated from the numeric MA values:

```text
bullish_order = MA5 > MA10 > MA20 > MA50 > MA100 > MA200
bearish_order = MA5 < MA10 < MA20 < MA50 < MA100 < MA200
long_intact   = MA100 > MA200
```

Complete six-MA ordering is supporting evidence. Main2 does not require complete bullish ordering when the Close and slopes satisfy its explicit gates.

### 3.5 Long-distance features

For `P ∈ {100, 200}`:

```text
long_distance_P_pct = (SMA_P(t) - Close[t]) / SMA_P(t) * 100
```

Positive means the Close is below the MA; negative means the Close is above the MA.

```text
long_distance_median_pct = median(long_distance_100_pct, long_distance_200_pct)
long_distance_max_pct    = max(long_distance_100_pct, long_distance_200_pct)
```

### 3.6 Short-stack features

```text
short_stack_median = median(MA5, MA10, MA20)
short_stack_vs_ma50_pct = (short_stack_median / MA50 - 1) * 100
short_negative_count = count(slope_5_20d_pct < 0,
                             slope_10_20d_pct < 0,
                             slope_20_20d_pct < 0)
```

## 4. Evidence quality

```text
FULL    = all six MA values and all six 20D slopes are available
PARTIAL = one or more MA values or slopes are unavailable
```

`PARTIAL` may still produce a Main Trend value from available evidence, but it must never claim full MA alignment. Missing MA100/MA200 slope is not treated as a bearish slope; it remains `PARTIAL` and reviewable.

## 5. Decision predicates

The predicates are evaluated in the precedence in Section 6.

### 5.1 Main4 severe deterioration

`main4_severe` is true if either condition is true.

**Full bearish severity:**

```text
Close < MA100 and Close < MA200
negative_slope_count >= 4 of 6 MAs
long_negative_slope_count >= 2 of {MA100, MA200}
long_distance_median_pct >= 3.5
```

**Short/medium severity:**

```text
Close < MA10 and Close < MA20
slope(MA5), slope(MA10), slope(MA20) are all negative
long_negative_slope_count >= 1
long_distance_max_pct >= 3.5
```

### 5.2 Main4 short-stack deterioration

```text
short_stack_vs_ma50_pct < 0
short_negative_count >= 2
long_intact is true
short_pullback_in_bullish_long_regime is false
```

This captures a short MA stack below the medium MA while the long structure does not provide a valid bullish-pullback exception.

### 5.3 Main2 bullish advance

```text
Close > MA10, MA20, MA50, MA100, and MA200
all six 20D MA slopes are positive
slope(MA100) >= 0.5%
slope(MA200) >= 0.5%
long_advance_slowdown is false
```

MA5 may lag; it does not by itself disqualify a bullish Main2 classification.

### 5.4 Main3 short pullback inside bullish long regime

```text
Close > MA100 and Close > MA200
slope(MA100) > 0
slope(MA200) > 0
short_stack_vs_ma50_pct <= -2.0
-17.0 < long_distance_200_pct <= -10.0
short_negative_count >= 2
```

### 5.5 Main3 short stack above medium MA with pressure

```text
short_stack_vs_ma50_pct > 0
Close > MA100 and Close > MA200
Close < MA10 or Close < MA20
```

### 5.6 Main3 short stack above medium MA with non-bullish pressure

```text
short_stack_vs_ma50_pct > 0
not all six 20D MA slopes are positive
```

### 5.7 Main3 long-intact weakening fallback

```text
long_intact is true
and at least one short weakening condition is true:
  MA5 < MA10
  or slope(MA5) < 0
  or Close < MA20
```

### 5.8 Main1 fallback

If no higher-precedence Main2/Main3/Main4 predicate wins:

```text
Main1 = no reliable bullish multi-MA alignment
```

## 6. Exact precedence

The implementation applies the following order:

```text
1. medium-term recovery override → Main3
2. severe Main4 predicate → Main4
3. short-stack Main4 predicate → Main4
4. Main2 bullish advance predicate → Main2
5. long-advance slowdown → Main3
6. isolated long-MA inversion without severity → Main1
7. short pullback inside bullish MA100/MA200 regime → Main3
8. short stack above MA50 with medium pressure → Main3
9. short stack above MA50 with non-bullish pressure → Main3
10. long-intact weakening fallback → Main3
11. otherwise → Main1
12. post-classification long-slope gate:
    if result is Main3 and both MA100/MA200 slopes are available
    but either is < 0.5%, demote to Main1
```

The post-classification gate does not demote a Main3 result when the long slopes are missing; missing remains `PARTIAL`.

## 7. Output contract

Every result contains one value:

```text
main_trend: 1 | 2 | 3 | 4
```

Every result also contains deterministic display-only evidence:
`main_trend_display: 1++ | 1+ | 1 | 2 | 3 | 3- | 3-- | 4`. It is derived
after numeric classification and is never an action lane. `PARTIAL` evidence
always receives the unsuffixed numeric display value. For Main 1, strict
bullish evidence (`FULL`, Close above MA10 and MA20, and all short slopes
positive) takes precedence over broad bullish evidence (Close above MA20 and
all short slopes positive). For Main 3, strict bearish evidence (`FULL`, all
short slopes negative, and Close below MA10 or MA20) takes precedence over
broad bearish evidence (`short_negative_count >= 2` with the same Close
condition).

Supporting deterministic evidence includes:

```text
moving_averages
close_position
ma_ordering
slopes_20d_pct
normalized_long_term_distance_pct
long_term_distance_median_pct
long_term_distance_max_pct
short_stack_median
short_stack_vs_ma50_pct
short_negative_count
evidence_quality
missing_periods
missing_slope_periods
reason
as_of
source_timeframe
policy_version
actionability=NONE
```

## 8. Interpretation guide

```text
Main1 = base / weak / damaged; long trend is not sufficiently confirmed
Main2 = recovery / bullish advance with confirmed medium and long slopes
Main3 = pullback / weakening / distribution without confirmed breakdown
Main4 = sustained deterioration / breakdown
```

These labels describe evidence, not certainty. Arm reviews the chart and makes the final decision.

## 9. Verification requirements

A change to this contract requires all of the following as separate evidence:

- deterministic source/test verification;
- canonical chart API MA keys and provenance;
- immutable Trend Map artifact rebuild/read-back;
- public API status, freshness, coverage, and actionability read-back;
- desktop/mobile browser verification of chart controls and drawer;
- documentation synchronization.

A green unit test or a generated artifact alone does not prove production acceptance.
