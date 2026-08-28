"""Regression tests for the /screen Daily-vs-current-price contract."""

from provenance_contract import screen_price_provenance


def test_screen_never_presents_daily_eod_as_current_quote():
    value = screen_price_provenance(
        last_date="2026-08-25",
        scan_time="2026-08-27T04:00:00+00:00",
    )

    assert value == {
        "quote_source": "unavailable",
        "quote_timestamp": None,
        "market_status": "unknown",
        "quote_is_provisional": False,
        "confirmed_close_date": "2026-08-25",
        "analysis_last_date": "2026-08-25",
        "analysis_scan_time": "2026-08-27T04:00:00+00:00",
        "freshness_verdict": "NOT VERIFIED",
    }


def test_screen_provenance_preserves_explicit_nulls_for_missing_analysis_time():
    value = screen_price_provenance(last_date=None, scan_time=None)
    assert value["quote_source"] == "unavailable"
    assert value["quote_timestamp"] is None
    assert value["confirmed_close_date"] is None
    assert value["analysis_last_date"] is None
    assert value["analysis_scan_time"] is None
    assert value["freshness_verdict"] == "NOT VERIFIED"
