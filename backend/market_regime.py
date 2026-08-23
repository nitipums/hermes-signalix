"""Signalix — Deterministic Market Regime Classifier (Contract v0.2.0 §3).

Computes a single market-wide regime state per scan snapshot.
Four states with precedence: HIGH_VOLATILITY > LIQUIDITY_EVENT > LOW_SPREAD > NORMAL

Pure deterministic function, no LLM, no I/O.
All inputs from one pinned scan snapshot; missing inputs → NORMAL + REGIME_INPUT_MISSING.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


# ---- Versioned constants (no magic numbers in prose) ----
REGIME_POLICY_VERSION = "regime-v0.2.0"

# Thresholds
ATR_PCT_20D_HIGH_VOL_THRESHOLD = 4.0      # HIGH_VOLATILITY iff V >= 4.0
MEDIAN_SPREAD_BPS_LOW_SPREAD_THRESHOLD = 25.0  # LOW_SPREAD iff S <= 25.0

# Reason codes (persisted with regime snapshot)
REASON_REGIME_INPUT_MISSING = "REGIME_INPUT_MISSING"
REASON_INVALID_NEGATIVE_INPUT = "INVALID_NEGATIVE_INPUT"
REASON_INVALID_NONFINITE_INPUT = "INVALID_NONFINITE_INPUT"


@dataclass(frozen=True)
class RegimeInputs:
    """Required inputs for regime computation (all market-level aggregates)."""
    atr_pct_20d: float | None              # V: market volatility (ATR% 20d of SET)
    median_spread_bps: float | None        # S: median bid/ask spread in bps across active ORD
    liquidity_event_flag: bool | None      # L: market-wide liquidity event (halts, circuit breakers)
    breadth_pct_above_ma50: float | None   # B: % active ORD symbols with close > MA50 (context)
    benchmark_at_or_above_ma50: bool | None  # M: SET close >= SET MA50 (context)

    def to_dict(self) -> dict[str, Any]:
        return {
            "atr_pct_20d": self.atr_pct_20d,
            "median_spread_bps": self.median_spread_bps,
            "liquidity_event_flag": self.liquidity_event_flag,
            "breadth_pct_above_ma50": self.breadth_pct_above_ma50,
            "benchmark_at_or_above_ma50": self.benchmark_at_or_above_ma50,
        }


@dataclass(frozen=True)
class RegimeOutput:
    """Regime computation result with full provenance."""
    regime_state: str                      # HIGH_VOLATILITY | LIQUIDITY_EVENT | LOW_SPREAD | NORMAL
    reason_codes: list[str]                # e.g., ["REGIME_INPUT_MISSING"], []
    inputs: RegimeInputs                   # Echo of inputs for audit
    policy_version: str                    # REGIME_POLICY_VERSION
    data_timestamp_utc: str                # ISO-8601 UTC with Z suffix
    computed_at_utc: str                   # ISO-8601 UTC with Z suffix

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime_state": self.regime_state,
            "reason_codes": self.reason_codes,
            "inputs": self.inputs.to_dict(),
            "policy_version": self.policy_version,
            "data_timestamp_utc": self.data_timestamp_utc,
            "computed_at_utc": self.computed_at_utc,
        }


def _is_valid_finite(value: float | None) -> bool:
    """Check if value is a valid finite number (not None, NaN, Inf, -Inf)."""
    if value is None:
        return False
    return math.isfinite(value)


def _is_negative(value: float | None) -> bool:
    """Check if value is negative (and valid)."""
    return _is_valid_finite(value) and value < 0.0


def _validate_inputs(inputs: RegimeInputs) -> list[str]:
    """Validate inputs, return list of reason codes for invalid/missing values."""
    reasons = []

    # Check for missing required inputs
    if inputs.atr_pct_20d is None:
        reasons.append(REASON_REGIME_INPUT_MISSING)
    elif not _is_valid_finite(inputs.atr_pct_20d):
        reasons.append(REASON_INVALID_NONFINITE_INPUT)
    elif _is_negative(inputs.atr_pct_20d):
        reasons.append(REASON_INVALID_NEGATIVE_INPUT)

    if inputs.median_spread_bps is None:
        reasons.append(REASON_REGIME_INPUT_MISSING)
    elif not _is_valid_finite(inputs.median_spread_bps):
        reasons.append(REASON_INVALID_NONFINITE_INPUT)
    elif _is_negative(inputs.median_spread_bps):
        reasons.append(REASON_INVALID_NEGATIVE_INPUT)

    if inputs.liquidity_event_flag is None:
        reasons.append(REASON_REGIME_INPUT_MISSING)

    if inputs.breadth_pct_above_ma50 is None:
        reasons.append(REASON_REGIME_INPUT_MISSING)
    elif not _is_valid_finite(inputs.breadth_pct_above_ma50):
        reasons.append(REASON_INVALID_NONFINITE_INPUT)
    elif _is_negative(inputs.breadth_pct_above_ma50):
        reasons.append(REASON_INVALID_NEGATIVE_INPUT)

    if inputs.benchmark_at_or_above_ma50 is None:
        reasons.append(REASON_REGIME_INPUT_MISSING)

    # Deduplicate
    return list(dict.fromkeys(reasons))


def compute_regime(inputs: RegimeInputs) -> RegimeOutput:
    """
    Compute market regime per Contract v0.2.0 §3.2.

    Precedence: HIGH_VOLATILITY > LIQUIDITY_EVENT > LOW_SPREAD > NORMAL

    Let V = atr_pct_20d, S = median_spread_bps, L = liquidity_event_flag.

    - HIGH_VOLATILITY iff V IS NOT NULL AND V >= 4.0
    - Else LIQUIDITY_EVENT iff L = true
    - Else LOW_SPREAD iff S IS NOT NULL AND S <= 25.0
    - Else NORMAL

    Boundary behavior:
    - V = 4.0 → HIGH_VOLATILITY
    - S = 25.0 → LOW_SPREAD only when neither higher-precedence state applies
    - Negative V or S → invalid input → NORMAL + INVALID_NEGATIVE_INPUT
    - NaN, Infinity, non-finite → NORMAL + INVALID_NONFINITE_INPUT
    - Missing required input → NORMAL + REGIME_INPUT_MISSING (never guess)
    """
    now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    data_ts = now_utc  # Caller should override with actual data timestamp
    reasons = _validate_inputs(inputs)

    # If any critical input missing/invalid → NORMAL with reasons
    has_critical_issue = any(r in (REASON_REGIME_INPUT_MISSING, REASON_INVALID_NEGATIVE_INPUT, REASON_INVALID_NONFINITE_INPUT) for r in reasons)

    # V = atr_pct_20d
    V = inputs.atr_pct_20d
    # S = median_spread_bps
    S = inputs.median_spread_bps
    # L = liquidity_event_flag
    L = inputs.liquidity_event_flag

    regime = "NORMAL"

    if not has_critical_issue:
        # HIGH_VOLATILITY: V >= 4.0
        if V is not None and V >= ATR_PCT_20D_HIGH_VOL_THRESHOLD:
            regime = "HIGH_VOLATILITY"
        # LIQUIDITY_EVENT: L = true (only if not HIGH_VOLATILITY)
        elif L is True:
            regime = "LIQUIDITY_EVENT"
        # LOW_SPREAD: S <= 25.0 (only if neither above)
        elif S is not None and S <= MEDIAN_SPREAD_BPS_LOW_SPREAD_THRESHOLD:
            regime = "LOW_SPREAD"
        # NORMAL: fallback
        else:
            regime = "NORMAL"
    else:
        # Keep NORMAL with reason codes
        regime = "NORMAL"

    return RegimeOutput(
        regime_state=regime,
        reason_codes=reasons,
        inputs=inputs,
        policy_version=REGIME_POLICY_VERSION,
        data_timestamp_utc=data_ts,
        computed_at_utc=now_utc,
    )


# ---- Convenience function for pipeline integration ----
def compute_regime_from_snapshot(
    market_series,                    # DataFrame with SET daily bars (Close, High, Low)
    all_symbols_data: dict[str, Any], # symbol -> {close, ma50, spread_bps?, ...}
    liquidity_events: list[str] | None = None,  # symbols with halts/circuit breakers
    data_timestamp_utc: str | None = None,
) -> RegimeOutput:
    """
    Compute regime from raw scan snapshot data.

    Args:
        market_series: DataFrame with SET benchmark (index=Date, columns=Close,High,Low)
        all_symbols_data: dict of symbol -> latest evidence (from screening)
        liquidity_events: list of symbols with trading halts/circuit breakers
        data_timestamp_utc: ISO-8601 UTC timestamp of the scan data
    """
    # V: atr_pct_20d from SET benchmark
    atr_pct_20d = None
    if market_series is not None and len(market_series) >= 20:
        try:
            high = market_series["High"].tail(20)
            low = market_series["Low"].tail(20)
            close = market_series["Close"].tail(20)
            prev_close = close.shift(1)
            tr = pd.concat([
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs()
            ], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]
            current_close = close.iloc[-1]
            if current_close > 0:
                atr_pct_20d = float((atr / current_close) * 100)
        except Exception:
            atr_pct_20d = None

    # S: median_spread_bps across active ORD symbols
    median_spread_bps = None
    spreads = []
    for sym, data in all_symbols_data.items():
        spread = data.get("spread_bps") or data.get("bid_ask_spread_bps")
        if spread is not None and _is_valid_finite(spread) and spread >= 0:
            spreads.append(float(spread))
    if spreads:
        median_spread_bps = float(sorted(spreads)[len(spreads) // 2])

    # L: liquidity_event_flag
    liquidity_event_flag = bool(liquidity_events and len(liquidity_events) > 0)

    # B: breadth_pct_above_ma50
    breadth_pct_above_ma50 = None
    if all_symbols_data:
        above = 0
        total = 0
        for data in all_symbols_data.values():
            close = data.get("close")
            ma50 = data.get("ma50")
            if close is not None and ma50 is not None and _is_valid_finite(close) and _is_valid_finite(ma50):
                total += 1
                if close > ma50:
                    above += 1
        if total > 0:
            breadth_pct_above_ma50 = float((above / total) * 100)

    # M: benchmark_at_or_above_ma50
    benchmark_at_or_above_ma50 = None
    if market_series is not None and len(market_series) >= 50:
        try:
            ma50 = market_series["Close"].rolling(50).mean().iloc[-1]
            close = market_series["Close"].iloc[-1]
            if _is_valid_finite(ma50) and _is_valid_finite(close):
                benchmark_at_or_above_ma50 = bool(close >= ma50)
        except Exception:
            benchmark_at_or_above_ma50 = None

    inputs = RegimeInputs(
        atr_pct_20d=atr_pct_20d,
        median_spread_bps=median_spread_bps,
        liquidity_event_flag=liquidity_event_flag,
        breadth_pct_above_ma50=breadth_pct_above_ma50,
        benchmark_at_or_above_ma50=benchmark_at_or_above_ma50,
    )

    result = compute_regime(inputs)

    # Override data_timestamp_utc if provided
    if data_timestamp_utc:
        result = RegimeOutput(
            regime_state=result.regime_state,
            reason_codes=result.reason_codes,
            inputs=result.inputs,
            policy_version=result.policy_version,
            data_timestamp_utc=data_timestamp_utc,
            computed_at_utc=result.computed_at_utc,
        )

    return result


# Import pandas at module level for compute_regime_from_snapshot
try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore