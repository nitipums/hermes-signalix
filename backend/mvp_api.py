"""MVP API projection module — deterministic read-only transforms.

Converts dashboard_snapshot.json serialized cards into the frontend
API contract shapes for:

  GET /api/daily-shortlist  → project_shortlist_response(snapshot)
  GET /api/explorer         → project_explorer_response(items, page, page_size, search, stage)
  GET /api/symbol/{symbol}  → project_symbol_detail(items, symbol)

Uses existing daily_shortlist module for eligibility/ranking.
Never queries DB, never rescans, never mutates data.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Any

from daily_shortlist import project_shortlist, project_shortlist_lanes
from provenance_contract import (
    DECISION_STATE_OFFICIAL_DAILY,
    DECISION_STATE_PROVISIONAL,
    resolve_decision_state,
    compute_freshness,
)
from marginable import (
    enrich_item,
    filter_items,
    metadata as marginable_metadata,
    normalize_filter,
    normalize_rates,
)


def _number(value, default=None):
    """Safe float coercion; returns default on None/non-numeric."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_name(item: dict) -> str | None:
    """Best-effort company name from serialized card."""
    return (
        item.get("companyName")
        or item.get("name")
        or item.get("company_name")
    )


def _resolve_market_cap(item: dict) -> float | None:
    """Market cap from independence block or direct field."""
    ind = item.get("independence") or {}
    return _number(ind.get("market_cap") or item.get("market_cap") or item.get("marketCap"))


def _resolve_index_membership(item: dict) -> list[str]:
    """Index membership: is_set50 flag → SET50/SET100."""
    ind = item.get("independence") or {}
    result = []
    if bool(ind.get("is_set50")):
        result.append("SET50")
    if result and "SET50" in result:
        result.append("SET100")  # SET50 is subset of SET100
    return result


def _resolve_provenance(item: dict, scan_time: str | None, scan_run_id: str | None) -> dict:
    """Provenance block per frontend contract."""
    return {
        "scan_run_id": scan_run_id or "",
        "scan_time": scan_time or "",
    }


def _resolve_trigger(item: dict) -> str | None:
    """Explainable trigger label — only when real evidence exists.

    Returns None when no authoritative trigger source is present.
    Never synthesises "Near pivot" or "No explicit trigger" as if facts.
    """
    t = item.get("trigger")
    if t and str(t).strip():
        return str(t).strip()
    # breakoutEvidence.trigger is a real data field
    bev = item.get("breakoutEvidence") or {}
    if bev.get("trigger"):
        return f"Break above {bev['trigger']}"
    # NOT_VERIFIED: no authoritative trigger evidence exists
    return None


def _resolve_invalidation(item: dict) -> str | None:
    """Explainable invalidation/system-stop boundary — only when real evidence exists.

    Returns None when no authoritative invalidation source is present.
    Never synthesises "No invalidation level defined" as if a fact.
    """
    inv = item.get("invalidation")
    if inv and str(inv).strip():
        return str(inv).strip()
    stop = _number(item.get("riskStop") or item.get("stop"))
    if stop is not None:
        return f"Close <= {stop:.2f}"
    # NOT_VERIFIED: no authoritative invalidation evidence exists
    return None


def _resolve_rr(item: dict) -> float | None:
    """Risk/reward ratio from target vs risk_stop."""
    target = _number(item.get("t161") or item.get("t127") or item.get("target"))
    stop = _number(item.get("riskStop") or item.get("stop"))
    close = _number(item.get("close"))
    if not target or not stop or not close or stop >= close:
        return None
    risk = close - stop
    if risk <= 0:
        return None
    reward = max(0, target - close)
    if reward <= 0:
        return None
    return round(reward / risk, 2)


def _resolve_target(item: dict) -> float | None:
    """Price target from fib extensions or explicit target."""
    return (
        _number(item.get("target"))
        or _number(item.get("t161"))
        or _number(item.get("t127"))
    )


def _resolve_change_pct(item: dict) -> float | None:
    """Change percent from serialized card."""
    val = _number(item.get("changePct") or item.get("change"))
    return round(val, 2) if val is not None else None


def _resolve_change_amount(item: dict) -> float | None:
    """Change amount — only from a directly serialized source field.

    Returns None when changeAmount is not present in the source data.
    Does NOT approximate from changePct × close.
    """
    val = _number(item.get("changeAmount"))
    if val is not None:
        return round(val, 2)
    # NOT_VERIFIED: no direct changeAmount source; do not approximate
    return None


def _resolve_description(item: dict) -> str | None:
    """Business description."""
    desc = item.get("businessSummary")
    if desc and str(desc).strip():
        return str(desc).strip()
    return item.get("description")


def _card_to_shortlist_item(item: dict, scan_time: str | None, scan_run_id: str | None) -> dict:
    """Map one serialized card to the frontend shortlist item contract."""
    item = enrich_item(item)
    sp = item.get("setup_proximity") or {}
    sq = item.get("setup_quality") or {}
    daily_fresh = item.get("daily_eod_freshness") or {}
    daily_eod = item.get("dailyEodDecision") or {}
    daily_eod_is_official = (
        daily_eod.get("source") == "Daily EOD"
        and daily_eod.get("as_of")
        and (
            item.get("dataFreshness") == "fresh"
            or daily_fresh.get("status") == "fresh"
        )
    )
    return {
        "symbol": item.get("symbol"),
        "name": _resolve_name(item),
        "sector": item.get("sector"),
        "industry": item.get("industry"),
        "description": _resolve_description(item),
        "market_cap": _resolve_market_cap(item),
        "trade_value": _number(item.get("tradeValue") or item.get("turnover")),
        "index_membership": _resolve_index_membership(item),
        "margin_pct": _number(item.get("margin_pct") or item.get("marginPct")),
        "margin_rate_pct": _number(item.get("margin_rate_pct")),
        "margin_marker": item.get("margin_marker"),
        "margin_can_buy": item.get("margin_can_buy"),
        "margin_can_add_collateral": item.get("margin_can_add_collateral"),
        "margin_can_short": item.get("margin_can_short"),
        "marginable": dict(item.get("marginable") or {}),
        "target": _resolve_target(item),
        "rr": _resolve_rr(item),
        "high52": _number(item.get("high52")),
        "low52": _number(item.get("low52")),
        "ath_high": _number(item.get("athHigh")),
        "ath_low": _number(item.get("athLow")),
        "stage": item.get("stage"),
        "phase": item.get("phase"),
        "decision_state": item.get("decision_state")
            or item.get("decisionState")
            or (DECISION_STATE_OFFICIAL_DAILY if daily_eod_is_official else DECISION_STATE_PROVISIONAL),
        "action": item.get("action"),
        "action_queue": item.get("action_queue"),
        "close": _number(item.get("close")),
        "change_pct": _resolve_change_pct(item),
        "change_amount": _resolve_change_amount(item),
        "volume": _number(item.get("volume"), 0),
        "avgDailyValue20": _number(item.get("avgDailyValue20"), 0),
        "setup_quality": {
            "pass": bool(sq.get("pass")),
            "score": _number(sq.get("score")),
            "reasons": sq.get("reasons") or [],
        },
        "setup_proximity": {
            "state": sp.get("state"),
            "pivot": _number(sp.get("pivot")),
            "distance_pct": _number(sp.get("distance_pct")),
            "zone": sp.get("zone"),
        },
        "trigger": _resolve_trigger(item),
        "invalidation": _resolve_invalidation(item),
        "risk_stop": _number(item.get("riskStop") or item.get("stop")),
        "risk_pct": _number(item.get("riskStopPct") or item.get("riskPct")),
        "rs": _number(item.get("rs"), 0),
        "source": item.get("priceSource") or item.get("source") or "Daily EOD",
        "data_freshness": item.get("dataFreshness")
            or item.get("data_freshness")
            or (daily_fresh.get("status")),
        "provenance": _resolve_provenance(item, scan_time, scan_run_id),
    }


def _resolve_decision_state(items: list[dict]) -> str:
    """Determine decision_state from items' availability.

    When any item has official_daily decision_state, return official_daily.
    Otherwise provisional.
    """
    for item in items:
        ds = item.get("decision_state") or item.get("decisionState")
        if ds == DECISION_STATE_OFFICIAL_DAILY:
            return DECISION_STATE_OFFICIAL_DAILY
    return DECISION_STATE_PROVISIONAL


def _watch_lane_projection(items: list[dict], *, excluded_symbols: set[str],
                           scan_time: str | None, scan_run_id: str | None) -> tuple[list[dict], list[dict]]:
    """Project price movers separately from actionable Daily Shortlist lanes.

    These are context/watch-only lanes. They never receive shortlist rank,
    READY/PRE_READY state, or a positive entry directive.
    """
    rising, caution = [], []
    for raw in items:
        symbol = str(raw.get("symbol", "")).upper()
        if not symbol or symbol in excluded_symbols:
            continue
        daily = raw.get("daily_eod_freshness") or {}
        if daily.get("status") != "latest_available" or raw.get("dataFreshness") in ("stale", "unknown"):
            continue
        change = _resolve_change_pct(raw)
        if change is None or change < 5.0:
            continue
        stage = raw.get("stage")
        phase = raw.get("phase")
        quality = raw.get("setup_quality") or {}
        reasons = list(quality.get("reasons") or [])
        volume_ratio = _number(
            raw.get("volumeRatio50")
            or raw.get("volume_ratio_50")
            or quality.get("vol_ratio_50")
        )
        has_volume_evidence = bool(raw.get("volumeSurge")) or (volume_ratio is not None and volume_ratio >= 2.0)
        if not has_volume_evidence:
            continue
        card = _card_to_shortlist_item(raw, scan_time, scan_run_id)
        card.update({
            "publication_state": "WATCH_ONLY",
            "watch_state": "RISING_MOVERS",
            "watch_change_pct": change,
            "watch_volume_ratio": volume_ratio,
            "action": "WATCH ONLY",
            "action_queue": "rising_movers_watch",
            "rank_components": {},
            "total_score": None,
            "policy_version": None,
        })
        if stage in {"S1_basing", "S2_uptrend"} and phase not in {"broken", "declining"}:
            card["watch_reason"] = "Price/volume surge, but Daily setup is not confirmed"
            rising.append(card)
        elif stage in {"S3_distributing", "S4_down"} or phase in {"topping", "breakout_extended", "declining", "broken"} or "extended" in reasons:
            card["watch_state"] = "CAUTION"
            card["action"] = "DO NOT CHASE"
            card["action_queue"] = "caution_watch"
            card["watch_reason"] = "Price/volume surge in weak, topping, or extended structure"
            caution.append(card)
    rising.sort(key=lambda x: (-float(x.get("watch_change_pct") or 0), str(x.get("symbol"))))
    caution.sort(key=lambda x: (-float(x.get("watch_change_pct") or 0), str(x.get("symbol"))))
    return rising, caution


def _daily_eod_status(as_of: str | None, now: datetime | None = None) -> str | None:
    """Classify today's Daily EOD as market-closed, not stale intraday data."""
    if not as_of:
        return None
    now = now or datetime.now(timezone(timedelta(hours=7)))
    if str(as_of)[:10] == now.astimezone(timezone(timedelta(hours=7))).date().isoformat():
        return "market_closed"
    return None


def _resolve_freshness(items: list[dict]) -> dict:
    """Build freshness block from items' timestamps.

    Returns {status, source, as_of, data_fetched_at}.
    Uses the latest daily_as_of across items as the authoritative as_of.
    """
    latest_as_of = None
    latest_source = None
    for item in items:
        daily = item.get("daily_eod_freshness") or {}
        as_of = daily.get("as_of") or item.get("daily_as_of") or item.get("date")
        if as_of:
            if latest_as_of is None or str(as_of) > str(latest_as_of):
                latest_as_of = str(as_of)
                latest_source = daily.get("source") or item.get("priceSource") or "Daily EOD"

    status = "unknown"
    if latest_as_of:
        try:
            dt_obj = datetime.fromisoformat(latest_as_of.replace("Z", "+00:00")
                                            if isinstance(latest_as_of, str) else
                                            latest_as_of)
            # Try to parse date-only vs datetime
            found_ts = dt_obj if dt_obj.tzinfo else dt_obj
            # For date-only, treat as end of day in Bangkok
            if len(str(latest_as_of)) <= 10:  # date only
                found_ts = dt_obj.replace(
                    hour=16, minute=30, tzinfo=timezone(timedelta(hours=7))
                )
            status = compute_freshness(latest_as_of)
            status = _daily_eod_status(latest_as_of) or status
            if status == "unknown":
                status = "fresh"  # have data, treat optimistically
        except (ValueError, TypeError):
            status = "fresh"  # have a string, treat as having data

    return {
        "status": status,
        "source": latest_source or "Daily EOD",
        "as_of": latest_as_of,
        "data_fetched_at": latest_as_of,
    }


def _find_item_by_symbol(items: list[dict], symbol: str) -> dict | None:
    """Case-insensitive symbol lookup."""
    upper = symbol.upper()
    for item in items:
        if str(item.get("symbol", "")).upper() == upper:
            return item
    return None


# ── Public API ────────────────────────────────────────────────────────

def project_shortlist_response(items: list[dict], snapshot_meta: dict | None = None,
                               marginable_filter: str = "krungsri",
                               margin_rates=None) -> dict:
    """Build the GET /api/daily-shortlist response from serialized cards.

    Uses daily_shortlist.project_shortlist() for eligibility/ranking,
    then maps to frontend contract shape. The default surface is the
    owner-selected Krungsri Credit Balance marginable list.
    """
    marginable_filter = normalize_filter(marginable_filter)
    margin_rates = normalize_rates(margin_rates)
    items = filter_items(items, marginable_filter, margin_rates)
    margin_meta = marginable_metadata()
    if not items:
        return {
            "decision_state": DECISION_STATE_PROVISIONAL,
            "freshness": {
                "status": "unknown",
                "source": "none",
                "as_of": None,
                "data_fetched_at": None,
            },
            "ready": [],
            "pre_ready": [],
            "rising_movers": [],
            "caution": [],
            "scan_time": None,
            "scan_run_id": None,
            "marginable_filter": marginable_filter,
            "marginable_filter_label": marginable_filter.replace("_", " ").title(),
            "margin_rates": margin_rates,
            "marginable_source": margin_meta,
        }

    # Normalize the explicit Daily EOD contract before classification. The
    # shortlist gate runs before card mapping, so deriving official_daily only
    # inside _card_to_shortlist_item is too late.
    normalized_items = []
    for raw in items:
        item = dict(raw)
        daily_eod = item.get("dailyEodDecision") or {}
        daily_fresh = item.get("daily_eod_freshness") or {}
        if (
            not item.get("decision_state")
            and not item.get("decisionState")
            and daily_eod.get("source") == "Daily EOD"
            and daily_eod.get("as_of")
            and (
                item.get("dataFreshness") == "fresh"
                or daily_fresh.get("status") == "fresh"
            )
        ):
            item["decision_state"] = DECISION_STATE_OFFICIAL_DAILY
        normalized_items.append(item)

    candidates = project_shortlist(normalized_items)

    ready = [c for c in candidates if c.get("publication_state") == "READY"]
    pre_ready = [c for c in candidates if c.get("publication_state") == "PRE_READY"]

    # Find the full serialized cards for each candidate
    items_by_symbol = {}
    for it in items:
        sym = str(it.get("symbol", "")).upper()
        if sym:
            items_by_symbol[sym] = it

    # Derive scan metadata from items (use the latest as_of)
    scan_time = None
    for it in items:
        ts = it.get("daily_eod_freshness", {}).get("as_of") or it.get("date")
        if ts and (scan_time is None or str(ts) > str(scan_time)):
            scan_time = str(ts)
    scan_run_id = items[0].get("provenance", {}).get("scan_run_id") if items else None

    def enrich(cand):
        sym = str(cand.get("symbol", "")).upper()
        card = items_by_symbol.get(sym, {})
        result = _card_to_shortlist_item(card, scan_time, scan_run_id)
        # Override action with the shortlist-normalized action
        result["action"] = cand.get("action") or result["action"]
        result["action_queue"] = cand.get("action_queue") or result.get("action_queue")
        result["decision_state"] = DECISION_STATE_OFFICIAL_DAILY  # shortlist = official daily
        result["trigger"] = cand.get("trigger") or result["trigger"]
        result["invalidation"] = cand.get("invalidation") or result["invalidation"]
        return result

    ready_items = [enrich(r) for r in ready]
    pre_items = [enrich(p) for p in pre_ready]
    rising_items, caution_items = _watch_lane_projection(
        normalized_items,
        excluded_symbols={str(x.get("symbol", "")).upper() for x in candidates},
        scan_time=scan_time,
        scan_run_id=scan_run_id,
    )

    # Prefer canonical MVP root metadata; item-derived fallback is transitional.
    freshness = (snapshot_meta or {}).get("freshness") or _resolve_freshness(items)
    root_run_id = (snapshot_meta or {}).get("run_id")

    return {
        "decision_state": DECISION_STATE_OFFICIAL_DAILY if (ready or pre_ready) else DECISION_STATE_PROVISIONAL,
        "freshness": freshness,
        "ready": ready_items,
        "pre_ready": pre_items,
        "rising_movers": rising_items,
        "caution": caution_items,
        "scan_time": scan_time,
        "scan_run_id": root_run_id or scan_run_id or "",
        "marginable_filter": marginable_filter,
        "marginable_filter_label": marginable_filter.replace("_", " ").title(),
        "margin_rates": margin_rates,
        "marginable_source": margin_meta,
    }


def project_explorer_response(
    items: list[dict],
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    stage: str | None = None,
    snapshot_meta: dict | None = None,
    marginable_filter: str = "krungsri",
    margin_rates=None,
) -> dict:
    """Build the GET /api/explorer response from serialized cards.

    Returns paginated, filterable list of all symbols in research-only format.
    The default view is limited to the owner-selected Krungsri list.
    """
    marginable_filter = normalize_filter(marginable_filter)
    margin_rates = normalize_rates(margin_rates)
    items = filter_items(items, marginable_filter, margin_rates)
    margin_meta = marginable_metadata()
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    if not items:
        return {
            "decision_state": DECISION_STATE_PROVISIONAL,
            "freshness": {
                "status": "unknown",
                "source": "none",
                "as_of": None,
                "data_fetched_at": None,
            },
            "items": [],
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "total_items": 0,
            "scan_time": None,
            "scan_run_id": None,
            "marginable_filter": marginable_filter,
            "marginable_filter_label": marginable_filter.replace("_", " ").title(),
            "margin_rates": margin_rates,
            "marginable_source": margin_meta,
        }

    # Filter
    filtered = list(items)
    if stage:
        filtered = [it for it in filtered if it.get("stage") == stage]
    if search:
        q = search.strip().upper()
        filtered = [
            it for it in filtered
            if q in str(it.get("symbol", "")).upper()
            or q in str(_resolve_name(it) or "").upper()
        ]

    total_items = len(filtered)
    total_pages = max(1, math.ceil(total_items / page_size)) if total_items > 0 else 0
    page = min(page, total_pages) if total_pages > 0 else 1
    start = (page - 1) * page_size
    page_items = filtered[start:start + page_size]

    scan_time = None
    for it in items:
        ts = it.get("daily_eod_freshness", {}).get("as_of") or it.get("date")
        if ts and (scan_time is None or str(ts) > str(scan_time)):
            scan_time = str(ts)
    scan_run_id = items[0].get("provenance", {}).get("scan_run_id") if items else None

    def to_explorer_item(item: dict) -> dict:
        daily_fresh = item.get("daily_eod_freshness") or {}
        return {
            "symbol": item.get("symbol"),
            "name": _resolve_name(item) or "",
            "stage": item.get("stage"),
            "close": _number(item.get("close")),
            "change_pct": _resolve_change_pct(item),
            "phase": item.get("phase"),
            "volume": _number(item.get("volume"), 0),
            "avgDailyValue20": _number(item.get("avgDailyValue20"), 0),
            "rs": _number(item.get("rs"), 0),
            "source": item.get("priceSource") or "Daily EOD",
            "data_freshness": item.get("dataFreshness")
                or daily_fresh.get("status"),
            "decision_state": item.get("decision_state")
                or DECISION_STATE_PROVISIONAL,
            "margin_pct": _number(item.get("margin_pct")),
            "margin_rate_pct": _number(item.get("margin_rate_pct")),
            "margin_marker": item.get("margin_marker"),
            "marginable": dict(item.get("marginable") or {}),
        }

    result_items = [to_explorer_item(it) for it in page_items]
    root_run_id = (snapshot_meta or {}).get("run_id")

    return {
        "decision_state": (snapshot_meta or {}).get("decision_state") or _resolve_decision_state(items),
        "freshness": (snapshot_meta or {}).get("freshness") or _resolve_freshness(items),
        "items": result_items,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "total_items": total_items,
        "scan_time": scan_time,
        "scan_run_id": root_run_id or scan_run_id or "",
        "marginable_filter": marginable_filter,
        "marginable_filter_label": marginable_filter.replace("_", " ").title(),
        "margin_rates": margin_rates,
        "marginable_source": margin_meta,
    }


def project_symbol_detail(items: list[dict], symbol: str) -> dict | None:
    """Build the GET /api/symbol/{symbol} drawer detail response."""
    item = _find_item_by_symbol(items, symbol)
    if item is None:
        return None

    scan_time = None
    for it in items:
        provenance_ts = (it.get("provenance") or {}).get("scan_time")
        ts = provenance_ts or it.get("daily_eod_freshness", {}).get("as_of") or it.get("date")
        if ts and (scan_time is None or str(ts) > str(scan_time)):
            scan_time = str(ts)
    scan_run_id = items[0].get("provenance", {}).get("scan_run_id") if items else None

    detail = _card_to_shortlist_item(item, scan_time, scan_run_id)
    # Drawer must use the same shortlist projection as the card; otherwise raw
    # producer action can disagree with the publication/action queue shown in
    # Daily Shortlist.
    projected = project_shortlist_response(items, marginable_filter="all")
    projected_by_symbol = {
        entry.get("symbol"): entry
        for lane in ("ready", "pre_ready")
        for entry in projected.get(lane, [])
    }
    shortlist_item = projected_by_symbol.get(symbol.upper())
    if shortlist_item:
        detail["action"] = shortlist_item.get("action") or detail.get("action")
        detail["action_queue"] = shortlist_item.get("action_queue") or detail.get("action_queue")
    return detail