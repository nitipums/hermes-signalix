"""Krungsri Credit Balance marginable-security contract.

The source is a monthly/periodic owner-provided PDF snapshot. This module is
presentation metadata only: it never changes scan eligibility or Daily state.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).with_name("marginable_securities.json")
DEFAULT_FILTER = "krungsri"
FILTERS = frozenset({"krungsri", "all", "non_marginable"})


@lru_cache(maxsize=1)
def load_marginable_data() -> dict:
    with DATA_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("schema_version") != "signalix.marginable.v1":
        raise ValueError("invalid marginable dataset schema")
    securities = payload.get("securities")
    if not isinstance(securities, list):
        raise ValueError("marginable dataset requires securities list")
    by_symbol = {}
    for record in securities:
        symbol = str(record.get("symbol", "")).strip().upper()
        if not symbol or symbol in by_symbol:
            raise ValueError(f"invalid/duplicate marginable symbol: {symbol}")
        by_symbol[symbol] = dict(record)
    return {**payload, "by_symbol": by_symbol}


def normalize_filter(value: str | None) -> str:
    value = str(value or DEFAULT_FILTER).strip().lower()
    return value if value in FILTERS else DEFAULT_FILTER


def normalize_rates(values) -> list[int]:
    """Normalize multi-select initial-margin rates; empty means all rates."""
    if values is None or values == "":
        return []
    if isinstance(values, str):
        values = values.split(",")
    result = []
    for value in values:
        try:
            rate = int(str(value).strip().rstrip("%"))
        except (TypeError, ValueError):
            continue
        if rate in {50, 60, 70, 80, 100} and rate not in result:
            result.append(rate)
    return sorted(result)


def metadata() -> dict:
    data = load_marginable_data()
    securities = data["securities"]
    return {
        "source": data.get("source"),
        "source_document": data.get("source_document"),
        "effective_date": data.get("effective_date"),
        "review_note": data.get("issuer_review_note"),
        "total": len(data["by_symbol"]),
        "ord_total": sum(r.get("instrument_type") == "ORD" for r in securities),
        "dr_total": sum(r.get("instrument_type") == "DR" for r in securities),
    }


def lookup(symbol: str | None) -> dict | None:
    if not symbol:
        return None
    record = load_marginable_data()["by_symbol"].get(str(symbol).strip().upper())
    return dict(record) if record else None


def enrich_item(item: dict) -> dict:
    """Add margin metadata without changing scan/group/lifecycle fields."""
    out = dict(item)
    record = lookup(item.get("symbol"))
    meta = metadata()
    if record:
        out["marginable"] = {
            "is_marginable": True,
            "instrument_type": record.get("instrument_type"),
            "margin_rate_pct": record.get("margin_rate_pct"),
            "marker": record.get("marker"),
            "can_buy": record.get("can_buy"),
            "can_add_collateral": record.get("can_add_collateral"),
            "can_short": record.get("can_short"),
            "source": meta["source"],
            "source_document": meta["source_document"],
            "effective_date": meta["effective_date"],
        }
        # Keep the existing frontend field name as a compatibility alias.
        out["margin_pct"] = record.get("margin_rate_pct")
        out["margin_rate_pct"] = record.get("margin_rate_pct")
        out["margin_marker"] = record.get("marker")
        out["margin_can_buy"] = record.get("can_buy")
        out["margin_can_add_collateral"] = record.get("can_add_collateral")
        out["margin_can_short"] = record.get("can_short")
    else:
        out["marginable"] = {
            "is_marginable": False,
            "instrument_type": None,
            "margin_rate_pct": None,
            "marker": None,
            "can_buy": None,
            "can_add_collateral": None,
            "can_short": None,
            "source": meta["source"],
            "source_document": meta["source_document"],
            "effective_date": meta["effective_date"],
        }
        out["margin_pct"] = None
        out["margin_rate_pct"] = None
        out["margin_marker"] = None
        out["margin_can_buy"] = None
        out["margin_can_add_collateral"] = None
        out["margin_can_short"] = None
    return out


def matches(record_or_item: dict, filter_value: str | None) -> bool:
    mode = normalize_filter(filter_value)
    is_marginable = bool((record_or_item.get("marginable") or {}).get("is_marginable"))
    if "marginable" not in record_or_item:
        is_marginable = lookup(record_or_item.get("symbol")) is not None
    if mode == "all":
        return True
    if mode == "non_marginable":
        return not is_marginable
    return is_marginable


def filter_items(items: list[dict], filter_value: str | None,
                 margin_rates=None) -> list[dict]:
    rates = set(normalize_rates(margin_rates))
    result = []
    for item in items:
        enriched = enrich_item(item)
        if not matches(enriched, filter_value):
            continue
        rate = (enriched.get("marginable") or {}).get("margin_rate_pct")
        if rates and rate not in rates:
            continue
        result.append(enriched)
    return result
