"""Pure Daily freshness assessment shared by projection boundaries.

This module owns the Daily EOD portion of projection metadata only. Intraday
fetch lineage and session scheduling remain separate concerns.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from provenance_contract import compute_freshness


_BANGKOK = timezone(timedelta(hours=7))


def daily_eod_status(as_of: str | None, now: datetime | None = None) -> str | None:
    """Return ``market_closed`` when a Daily EOD belongs to today's session."""
    if not as_of:
        return None
    current = now or datetime.now(_BANGKOK)
    if str(as_of)[:10] == current.astimezone(_BANGKOK).date().isoformat():
        return "market_closed"
    return None


def assess_projection_freshness(items: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    """Build the shared Daily freshness block for projection responses.

    The latest Daily ``as_of`` is authoritative for ``as_of`` and
    ``data_fetched_at``. Missing timestamps remain ``unknown``. Non-empty but
    invalid timestamp strings retain the existing optimistic ``fresh`` behavior.
    """
    latest_as_of = None
    latest_source = None
    for item in items:
        daily = item.get("daily_eod_freshness") or {}
        as_of = daily.get("as_of") or item.get("daily_as_of") or item.get("date")
        if as_of and (latest_as_of is None or str(as_of) > str(latest_as_of)):
            latest_as_of = str(as_of)
            latest_source = daily.get("source") or item.get("priceSource") or "Daily EOD"

    status = "unknown"
    if latest_as_of:
        try:
            datetime.fromisoformat(latest_as_of.replace("Z", "+00:00"))
            status = compute_freshness(latest_as_of)
            status = daily_eod_status(latest_as_of, now=now) or status
            if status == "unknown":
                status = "fresh"
        except (ValueError, TypeError):
            status = "fresh"

    return {
        "status": status,
        "source": latest_source or "Daily EOD",
        "as_of": latest_as_of,
        "data_fetched_at": latest_as_of,
    }
