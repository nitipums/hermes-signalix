"""Parity tests for the shared Daily freshness assessment seam."""

from datetime import datetime, timezone

import canonical_setup_projection
import mvp_api
from freshness_assessment import assess_projection_freshness, daily_eod_status


NOW = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)


def item(as_of=None, source=None):
    daily = {}
    if as_of is not None:
        daily["as_of"] = as_of
    if source is not None:
        daily["source"] = source
    return {"daily_eod_freshness": daily}


def test_same_day_daily_eod_is_market_closed_without_wall_clock_staleness():
    row = item("2026-09-02", "Settrade Daily")

    assert daily_eod_status("2026-09-02", now=NOW) == "market_closed"
    assert assess_projection_freshness([row], now=NOW) == {
        "status": "market_closed",
        "source": "Settrade Daily",
        "as_of": "2026-09-02",
        "data_fetched_at": "2026-09-02",
    }


def test_latest_prior_day_preserves_aging_and_stale_calculation():
    aging = assess_projection_freshness(
        [item("2026-09-01T09:30:00+00:00")], now=NOW
    )
    stale = assess_projection_freshness(
        [item("2026-08-29T09:30:00+00:00")], now=NOW
    )

    assert aging["status"] == "aging"
    assert stale["status"] == "stale"
    assert aging["as_of"] == aging["data_fetched_at"] == "2026-09-01T09:30:00+00:00"


def test_missing_and_invalid_timestamps_keep_existing_fail_safe_shapes():
    assert assess_projection_freshness([]) == {
        "status": "unknown", "source": "Daily EOD", "as_of": None,
        "data_fetched_at": None,
    }
    assert assess_projection_freshness([item("not-a-timestamp")])["status"] == "fresh"


def test_mvp_and_canonical_projection_call_paths_are_identical():
    rows = [item("2026-09-01T09:30:00+00:00", "Daily source"), item("2026-08-31")]

    assert mvp_api._resolve_freshness(rows, now=NOW) == canonical_setup_projection._resolve_freshness(
        rows, now=NOW
    ) == assess_projection_freshness(rows, now=NOW)
