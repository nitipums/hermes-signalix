"""Deterministic market-buy signal projection for the private shadow UI.

This policy consumes canonical setup-candidate evidence only. It is shadow-only:
it never reads a portfolio, writes, publishes, sizes, or submits an order. Scores
are evidence completeness/strength, not win probabilities.
"""
from __future__ import annotations

from typing import Any


POLICY_VERSION = "private-actionable-signals-v0.1-shadow"
BUY_NOW_MIN_SCORE = 80


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _token(value: Any) -> str:
    return str(value or "").strip().upper()


def _current_price(candidate: dict) -> float | None:
    quote = candidate.get("quote") if isinstance(candidate.get("quote"), dict) else {}
    setup = candidate.get("setup") if isinstance(candidate.get("setup"), dict) else {}
    price = _number(quote.get("price"))
    if price is None:
        price = _number(setup.get("close"))
    return price if price is not None and price > 0 else None


def _target_1(setup: dict) -> float | None:
    direct = _number(setup.get("target_1"))
    if direct is not None:
        return direct
    targets = setup.get("targets")
    if not isinstance(targets, (list, tuple)) or not targets:
        return None
    first = targets[0]
    return _number(first.get("price")) if isinstance(first, dict) else _number(first)


def _fresh_market(candidate: dict) -> bool:
    status = candidate.get("data_status")
    if not isinstance(status, dict) or status.get("sufficient") is not True:
        return False
    daily = _token(status.get("daily_freshness"))
    intraday = _token(status.get("intraday_60m_freshness"))
    return daily in {"FRESH", "CURRENT"} and intraday in {"FRESH", "CURRENT"}


def _plan(candidate: dict) -> dict:
    setup = candidate.get("setup") if isinstance(candidate.get("setup"), dict) else {}
    entry = setup.get("entry_zone") if isinstance(setup.get("entry_zone"), dict) else {}
    return {
        "trigger": _number(setup.get("trigger")),
        "entry_low": _number(entry.get("low")),
        "entry_high": _number(entry.get("high")),
        "trade_stop": _number(setup.get("trade_stop") if setup.get("trade_stop") is not None
                              else setup.get("invalidation")),
        "target_1": _target_1(setup),
        "rr_to_target_1": _number((setup.get("rr") or {}).get("to_target_1")),
    }


def _coherent_plan(plan: dict) -> bool:
    trigger = plan["trigger"]
    low = plan["entry_low"]
    high = plan["entry_high"]
    stop = plan["trade_stop"]
    target = plan["target_1"]
    rr = plan["rr_to_target_1"]
    return all(value is not None for value in (trigger, low, high, stop, target, rr)) \
        and all(value > 0 for value in (trigger, low, high, stop, target)) \
        and stop < trigger < target and low <= high and rr >= 2


def _confidence(candidate: dict, price: float | None, plan: dict) -> dict:
    setup = candidate.get("setup") if isinstance(candidate.get("setup"), dict) else {}
    wave = candidate.get("wave") if isinstance(candidate.get("wave"), dict) else {}
    trend = candidate.get("trend") if isinstance(candidate.get("trend"), dict) else {}
    lane = _token(candidate.get("decision_lane"))
    setup_status = _token(setup.get("status"))
    wave_confidence = _token(wave.get("confidence"))
    trend_state = str(trend.get("state") or "").strip().lower()
    rr = plan["rr_to_target_1"]
    in_entry_zone = (price is not None and plan["entry_low"] is not None
                     and plan["entry_high"] is not None
                     and plan["entry_low"] <= price <= plan["entry_high"])

    components = {
        "fresh_daily_and_60m": 20 if _fresh_market(candidate) else 0,
        "canonical_review_lane": 15 if lane == "REVIEW_NOW" else 0,
        "completed_60m_trigger": 20 if setup_status == "TRIGGERED" else
                                 12 if setup_status in {"PRE_TRIGGER", "TESTED_TRIGGER"} else 0,
        "daily_wave_confidence": 15 if wave_confidence == "HIGH" else
                                 10 if wave_confidence == "MEDIUM" else 0,
        "daily_trend": 10 if trend_state == "uptrend" else
                       7 if trend_state == "emerging_uptrend" else 0,
        "target_1_rr": 10 if rr is not None and rr >= 4 else
                       7 if rr is not None and rr >= 2 else 0,
        "price_in_entry_zone": 10 if in_entry_zone else 0,
    }
    score = min(100, sum(components.values()))
    label = "HIGH" if score >= 80 else "MEDIUM" if score >= 60 else "LOW"
    return {
        "kind": "EVIDENCE_SCORE",
        "score": score,
        "label": label,
        "components": components,
        "calibration_status": "NOT_CALIBRATED",
        "calibrated_probability": None,
        "policy_version": POLICY_VERSION,
    }


def project_market_buy_signal(candidate: dict) -> dict:
    """Project one market-only entry signal without portfolio state."""
    symbol = str(candidate.get("symbol") or "").strip().upper()
    setup = candidate.get("setup") if isinstance(candidate.get("setup"), dict) else {}
    lane = _token(candidate.get("decision_lane"))
    setup_status = _token(setup.get("status"))
    price = _current_price(candidate)
    plan = _plan(candidate)
    confidence = _confidence(candidate, price, plan)
    if not _fresh_market(candidate) or price is None:
        signal = "DATA_BLOCKED"
        reasons = ["MARKET_EVIDENCE_NOT_FRESH_OR_COMPLETE"]
    elif lane == "REVIEW_NOW" and setup_status == "TRIGGERED" \
            and _coherent_plan(plan) \
            and plan["entry_low"] <= price <= plan["entry_high"] \
            and confidence["score"] >= BUY_NOW_MIN_SCORE:
        signal = "BUY_NOW"
        reasons = ["ALL_BUY_NOW_GATES_PASSED"]
    elif lane == "REVIEW_NOW" and setup_status in {"PRE_TRIGGER", "TESTED_TRIGGER"} \
            and _coherent_plan(plan):
        signal = "BUY_ON_TRIGGER"
        reasons = ["WAITING_FOR_COMPLETED_60M_TRIGGER"]
    elif lane == "AVOID":
        signal = "AVOID"
        reasons = ["CANONICAL_SETUP_AVOID"]
    else:
        signal = "WAIT"
        reasons = ["BUY_NOW_GATES_NOT_MET"]

    return {
        "symbol": symbol,
        "signal": signal,
        "mode": "PAPER_SHADOW",
        "scope": "MARKET_BUY_SCAN",
        "as_of": candidate.get("as_of"),
        "current_price": price,
        "plan": plan,
        "confidence": confidence,
        "reason_codes": reasons,
        "source_decision_lane": lane or "DATA_BLOCKED",
        "source_setup_status": setup_status or "UNKNOWN",
        "execution": {"authorized": False, "order_payload": None},
        "policy_version": POLICY_VERSION,
    }
