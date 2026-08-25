"""Signalix Risk/Stop/Target Assistant — deterministic calculation module.

Read-only access to canonical data. No user input persistence.
All functions return NOT_VERIFIED for invalid/incomplete evidence.

CONTRACT ALIGNMENT (v0.2.0):
- Daily contract pulls from analyze_symbol_db_ranked() output:
    swing_low     = buy_zone.wave1_low           (22-day swing low)
    swing_high    = buy_zone.wave1_high          (22-day swing high)
    pullback_low  = buy_zone.fibs["50"]          (fib 50% retracement = entry ref)
    trigger       = trade_readiness.breakout_level_20d  (20-day breakout trigger)
    system_stop   = trade_readiness.stop_loss    (max(swing_low_90d, close*0.93))
    pivot_low     = trade_readiness.pre_break_pivot_low
    freshness     = last_date (daily EOD date)

- Intraday 60m contract pulls from load_symbol_intraday() DataFrame:
    swing_low     = 90-bar intraday low   (configurable lookback)
    swing_high    = 90-bar intraday high
    pullback_low  = fib_50 of the swing
    trigger       = latest close (intraday continuation trigger)
    system_stop   = min(low, close*0.93)   (tightest structural stop)
    freshness     = latest intraday timestamp

Fib extension method (single confirmed method per Arm's rule):
    Wave: swing_low → swing_high → pullback_low
    Extension = pullback_low + (swing_high - swing_low) * [1.272, 1.618]
"""
from __future__ import annotations

import math
from typing import Any

from provenance_contract import compute_freshness, FRESH


def _is_valid_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not math.isnan(v) and not math.isinf(v)


def _compute_warnings(planned_stop, system_stop):
    """Determine stop-related warnings when user overrides planned_stop."""
    warnings = []
    if planned_stop is not None and system_stop is not None:
        if planned_stop > system_stop:
            warnings.append("STOP ABOVE SYSTEM INVALIDATION")
        elif planned_stop < system_stop:
            warnings.append("WIDER STOP")
    return warnings


# ---------------------------------------------------------------------------
# Core deterministic calculations (pure math — no I/O, no DB)
# ---------------------------------------------------------------------------

def compute_fib_targets(
    swing_low: float | None,
    swing_high: float | None,
    pullback_low: float | None,
) -> dict[str, float | None]:
    """Fib 1.272 / 1.618 extensions from confirmed swing anchors.

    Method: swing_low → swing_high → pullback_low.
    Extension measured from pullback_low (the Fibonacci pullback-extension method).
    Returns NOT_VERIFIED when anchors are missing, inverted, or degenerate.
    """
    if not all(_is_valid_number(v) for v in (swing_low, swing_high, pullback_low)):
        return {"fib_1272": None, "fib_1618": None, "status": "NOT_VERIFIED"}

    if swing_high <= swing_low or pullback_low <= swing_low:
        return {"fib_1272": None, "fib_1618": None, "status": "NOT_VERIFIED"}

    wave_range = swing_high - swing_low
    if wave_range <= 0:
        return {"fib_1272": None, "fib_1618": None, "status": "NOT_VERIFIED"}

    fib_1272 = pullback_low + wave_range * 1.272
    fib_1618 = pullback_low + wave_range * 1.618
    return {"fib_1272": round(fib_1272, 4), "fib_1618": round(fib_1618, 4), "status": "OK"}


def compute_position_size(
    account_size: float | None,
    risk_percent: float | None,
    planned_entry: float | None,
    planned_stop: float | None,
) -> dict[str, float | None]:
    """risk_budget / risk_per_share. NOT_VERIFIED if invalid."""
    if not all(_is_valid_number(v) for v in (account_size, risk_percent, planned_entry, planned_stop)):
        return {
            "risk_budget": None,
            "risk_per_share": None,
            "shares": None,
            "status": "NOT_VERIFIED",
        }

    if account_size <= 0 or risk_percent <= 0 or risk_percent > 100:
        return {
            "risk_budget": None,
            "risk_per_share": None,
            "shares": None,
            "status": "NOT_VERIFIED",
        }

    risk_budget = account_size * (risk_percent / 100)
    risk_per_share = planned_entry - planned_stop

    if risk_per_share <= 0:
        return {
            "risk_budget": None,
            "risk_per_share": None,
            "shares": None,
            "status": "NOT_VERIFIED",
        }

    shares = math.floor(risk_budget / risk_per_share)
    return {
        "risk_budget": round(risk_budget, 2),
        "risk_per_share": round(risk_per_share, 4),
        "shares": shares,
        "status": "OK",
    }


# ---------------------------------------------------------------------------
# Contract adapters — map DB / scan output → risk_stop_target evidence dict
# ---------------------------------------------------------------------------

def _extract_daily_evidence(item: dict) -> dict:
    """Extract Daily contract evidence from analyze_symbol_db_ranked output.

    Expected item structure (subset):
      buy_zone: {wave1_low, wave1_high, fibs:{50,62,...}, monitor_support, stop_loss}
      trade_readiness: {breakout_level_20d, stop_loss, pre_break_pivot_low,
                        swing_low_90d, swing_high_90d, ...}
      last_date: "2026-08-14"
    """
    bz = item.get("buy_zone") or {}
    tr = item.get("trade_readiness") or {}

    # Fib 50% from buy_zone.fibs is the pullback_low (entry reference).
    fibs = bz.get("fibs") or {}
    pullback_low = fibs.get("50") or fibs.get("62")

    return {
        "trigger": tr.get("breakout_level_20d"),
        "system_stop": tr.get("stop_loss") or bz.get("stop_loss"),
        "pivot_low": tr.get("pre_break_pivot_low"),
        "swing_low": bz.get("wave1_low"),
        "swing_high": bz.get("wave1_high"),
        "pullback_low": pullback_low,
        "close": item.get("close"),
        "freshness": item.get("last_date"),  # daily EOD date string
    }


def _extract_intraday_evidence_from_df(df, lookback=90) -> dict:
    """Compute intraday 60m swing anchors from a 60m DataFrame.

    Returns evidence dict with swing_high/low and pullback (fib 50%) from the
    most recent `lookback` candles.  trigger defaults to latest close.
    """
    import pandas as pd  # local import — only needed for intraday path

    if df is None or len(df) == 0:
        return {
            "trigger": None, "system_stop": None, "pivot_low": None,
            "swing_low": None, "swing_high": None, "pullback_low": None,
            "close": None, "freshness": None,
        }

    recent = df.tail(lookback)
    swing_low = float(recent["Low"].min())
    swing_high = float(recent["High"].max())
    close = float(df["Close"].iloc[-1])

    # Fibonacci 50% retracement = pullback_low
    rng = swing_high - swing_low
    pullback_low = round(swing_low + rng * 0.5, 4) if rng > 0 else None

    # Hard stop: -7% from entry; structural stop: recent low
    hard_stop = close * 0.93
    system_stop = max(hard_stop, swing_low)

    # Freshness: latest candle timestamp
    ts = df.index[-1]
    if hasattr(ts, "isoformat"):
        freshness = ts.isoformat()
    else:
        freshness = str(ts)

    return {
        "trigger": close,
        "system_stop": round(system_stop, 2),
        "pivot_low": None,  # not computed for intraday MVP
        "swing_low": round(swing_low, 2),
        "swing_high": round(swing_high, 2),
        "pullback_low": pullback_low,
        "close": round(close, 2),
        "freshness": freshness,
    }


def _is_daily_fresh(date_str: str | None) -> bool:
    """Daily EOD is fresh if last_date is within a reasonable window."""
    if not date_str:
        return False
    import datetime as dt
    try:
        last = dt.date.fromisoformat(str(date_str))
        delta = (dt.date.today() - last).days
        return delta <= 10  # matches MAX_STALE_DAYS in screening.py
    except (ValueError, TypeError):
        return False


def _is_intraday_fresh(ts_str: str | None) -> bool:
    """60m quote is fresh if within the intraday stale threshold."""
    if not ts_str:
        return False
    from provenance_contract import INTRADAY_STALE_HOURS
    import datetime as dt
    try:
        ts = dt.datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        age_hours = (dt.datetime.now(dt.timezone.utc) - ts).total_seconds() / 3600
        return age_hours < INTRADAY_STALE_HOURS
    except (ValueError, TypeError):
        return False


def _is_fresh(contract: str, evidence: dict) -> bool:
    freshness = evidence.get("freshness")
    if contract == "daily":
        return _is_daily_fresh(freshness)
    elif contract == "intraday":
        return _is_intraday_fresh(freshness)
    return False


# ---------------------------------------------------------------------------
# Main entry point — dispatches to Daily or Intraday contract
# ---------------------------------------------------------------------------

def compute_risk_stop_target(
    contract: str,
    symbol: str,
    item: dict | None = None,
    intraday_df=None,
    user_inputs: dict | None = None,
) -> dict:
    """Main entry: dispatches to Daily or Intraday contract.

    Args:
        contract: "daily" or "intraday"
        symbol: ticker symbol
        item: serialized dashboard item from analyze_symbol_db_ranked (Daily only)
        intraday_df: optional 60m DataFrame for intraday contract
        user_inputs: optional {account_size, risk_percent, planned_entry, planned_stop}

    Returns:
        {symbol, contract, trigger, system_stop, pivot_low, planned_entry,
         planned_stop, fib_1272, fib_1618, freshness, sizing, warnings, status}
    """
    if contract == "daily":
        if item is None:
            return {"symbol": symbol, "contract": "daily",
                    "status": "NOT_VERIFIED", "reason": "no daily item provided"}
        evidence = _extract_daily_evidence(item)
    elif contract == "intraday":
        evidence = _extract_intraday_evidence_from_df(intraday_df)
    else:
        return {"symbol": symbol, "contract": contract,
                "status": "NOT_VERIFIED", "reason": f"unknown contract: {contract}"}

    fresh = _is_fresh(contract, evidence)
    if not fresh:
        return {
            "symbol": symbol,
            "contract": contract,
            "status": "NOT_VERIFIED",
            "reason": "stale or missing freshness evidence",
            "freshness": evidence.get("freshness"),
        }

    fib = compute_fib_targets(
        evidence.get("swing_low"),
        evidence.get("swing_high"),
        evidence.get("pullback_low"),
    )

    planned_entry = (user_inputs or {}).get("planned_entry") or evidence.get("trigger")
    planned_stop = (user_inputs or {}).get("planned_stop") or evidence.get("system_stop")

    sizing = compute_position_size(
        (user_inputs or {}).get("account_size"),
        (user_inputs or {}).get("risk_percent"),
        planned_entry,
        planned_stop,
    )

    warnings: list[str] = _compute_warnings(planned_stop, evidence.get("system_stop"))

    return {
        "symbol": symbol,
        "contract": contract,
        "trigger": evidence.get("trigger"),
        "system_stop": evidence.get("system_stop"),
        "pivot_low": evidence.get("pivot_low"),
        "swing_low": evidence.get("swing_low"),
        "swing_high": evidence.get("swing_high"),
        "planned_entry": planned_entry,
        "planned_stop": planned_stop,
        "fib_1272": fib.get("fib_1272"),
        "fib_1618": fib.get("fib_1618"),
        "freshness": evidence.get("freshness"),
        "sizing": sizing,
        "warnings": warnings,
        "status": "OK" if not warnings else "OK_WITH_WARNINGS",
    }
