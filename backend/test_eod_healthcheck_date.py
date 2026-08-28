from datetime import datetime, timezone

from eod_healthcheck import expected_market_date


def test_before_eod_cutoff_expects_previous_completed_market_day():
    now = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)  # 14:00 ICT
    assert expected_market_date(now).isoformat() == "2026-08-26"


def test_after_eod_cutoff_expects_current_market_day():
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)  # 19:00 ICT
    assert expected_market_date(now).isoformat() == "2026-08-27"


def test_weekend_before_eod_cutoff_keeps_last_completed_trading_day():
    now = datetime(2026, 8, 29, 7, 0, tzinfo=timezone.utc)  # Sat 14:00 ICT
    assert expected_market_date(now).isoformat() == "2026-08-28"
