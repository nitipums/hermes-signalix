from datetime import date, datetime, timezone
import json

from eod_healthcheck import expected_market_date, render_payload


def test_before_eod_cutoff_expects_previous_completed_market_day():
    now = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)  # 14:00 ICT
    assert expected_market_date(now).isoformat() == "2026-08-26"


def test_after_eod_cutoff_expects_current_market_day():
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)  # 19:00 ICT
    assert expected_market_date(now).isoformat() == "2026-08-27"


def test_weekend_before_eod_cutoff_keeps_last_completed_trading_day():
    now = datetime(2026, 8, 29, 7, 0, tzinfo=timezone.utc)  # Sat 14:00 ICT
    assert expected_market_date(now).isoformat() == "2026-08-28"


def test_health_payload_reports_data_completeness_separately_from_process_health():
    coverage = {
        "active_ord": 931,
        "current_session": 846,
        "stale_history": 58,
        "no_history": 27,
        "scan_evaluated": 904,
        "status": "PARTIAL",
    }
    payload = json.loads(render_payload(
        alerts=[],
        expected_date=date(2026, 8, 28),
        eod_date=date(2026, 8, 28),
        scan_date=date(2026, 8, 28),
        now=datetime(2026, 8, 28, 13, 2, tzinfo=timezone.utc),
        coverage=coverage,
    ))

    assert payload["level"] == "HEALTHY"
    assert payload["data_completeness"] == "PARTIAL"
    assert payload["coverage"] == coverage
