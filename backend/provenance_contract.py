"""Centralized provenance/freshness contract for Signalix.

Single source of truth for provenance/freshness metadata fields:
- data_fetched_at  (ISO-8601 UTC, max candle/scan time actually fetched)
- market / market_session (TH vs US, open/closed/holiday/weekend)
- scan_timestamp / build_timestamp (when scan ran / when artifact was built)
- candle_timestamp / as_of (per-instrument price as-of date)
- source / data_freshness_source (where the price data came from)
- data_freshness_status (global contract: fresh/aging/stale/unknown)

Rules (P0 contract):
- INTRADAY_STALE_HOURS=1: a 60m candle >1h without a successful fetch is "stale".
- Global freshness is "fresh" when the last fetch is within the threshold;
  "stale" when past it; "unknown" when no fetch timestamp exists at all.
- On a market_closed session, global_status is still computed from the last
  successful fetch — candle age remains independently visible and auditable.
  The market_session block is interpretation context, not a freshness signal.
"""
import datetime as dt
from zoneinfo import ZoneInfo

# --- Constants (canonical across TH/US/API/UI/mobile) ---
INTRADAY_STALE_HOURS = 1
INTRADAY_FRESH_HOURS = 1

MARKET_DEFAULT_TZ = {
    "TH": "Asia/Bangkok",
    "US": "America/New_York",
}

# Canonical data_freshness_status values (the contract)
FRESH = "fresh"
AGING = "aging"
STALE = "stale"
UNKNOWN = "unknown"

# Canonical Daily decision-state values.
DECISION_STATE_PROVISIONAL = "provisional"
DECISION_STATE_OFFICIAL_DAILY = "official_daily"
DECISION_STATES = (DECISION_STATE_PROVISIONAL, DECISION_STATE_OFFICIAL_DAILY)


def resolve_decision_state(market_session=None, daily_as_of=None, last_valid_session=None):
    """Return official_daily only for a closed, aligned Daily EOD session."""
    if not daily_as_of:
        return DECISION_STATE_PROVISIONAL
    session = market_session or {}
    if session.get("status") != "market_closed":
        return DECISION_STATE_PROVISIONAL
    anchor = last_valid_session if last_valid_session is not None else session.get("last_valid_session")
    if anchor is None or str(daily_as_of) != str(anchor):
        return DECISION_STATE_PROVISIONAL
    return DECISION_STATE_OFFICIAL_DAILY


# Display strings the UI/mobile layer reference by exact match.
STATUS_DISPLAY = {
    FRESH: "Fresh",
    AGING: "Aging",
    STALE: "Stale",
    UNKNOWN: "Unknown / Stale",
}


def compute_freshness(data_fetched_at, now=None):
    """Deterministic freshness classification for any market.

    Returns one of FRESH / AGING / STALE / UNKNOWN.

    - data_fetched_at: ISO-8601 str or datetime (UTC). None => UNKNOWN.
    - now: optional datetime for deterministic tests (defaults to UTC now).
    """
    if data_fetched_at is None:
        return UNKNOWN
    now = now or dt.datetime.now(dt.timezone.utc)
    if isinstance(data_fetched_at, str):
        try:
            data_fetched_at = dt.datetime.fromisoformat(data_fetched_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return UNKNOWN
    if data_fetched_at.tzinfo is None:
        data_fetched_at = data_fetched_at.replace(tzinfo=dt.timezone.utc)
    age_hours = max(0.0, (now - data_fetched_at).total_seconds() / 3600.0)
    if age_hours < INTRADAY_STALE_HOURS:
        return FRESH
    if age_hours <= 72:
        return AGING
    return STALE


def display_fetched_at(data_fetched_at, tz_name="Asia/Bangkok"):
    """Format a fetch timestamp for display (BKK or any tz). None => 'Unknown / Stale'."""
    if data_fetched_at is None:
        return STATUS_DISPLAY[UNKNOWN]
    if isinstance(data_fetched_at, str):
        try:
            data_fetched_at = dt.datetime.fromisoformat(data_fetched_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return STATUS_DISPLAY[UNKNOWN]
    if data_fetched_at.tzinfo is None:
        data_fetched_at = data_fetched_at.replace(tzinfo=dt.timezone.utc)
    try:
        local = data_fetched_at.astimezone(ZoneInfo(tz_name))
    except Exception:
        local = data_fetched_at.astimezone(dt.timezone.utc)
    return local.strftime("%d %b %Y %H:%M ICT (Bangkok)") if tz_name == "Asia/Bangkok" else local.strftime("%Y-%m-%d %H:%M %Z")
