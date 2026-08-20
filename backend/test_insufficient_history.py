import pandas as pd

from screening import insufficient_history_row


def test_short_history_is_kept_as_explicit_non_signal_row():
    idx = pd.date_range('2026-08-01', periods=4, freq='D')
    df = pd.DataFrame({
        'Open': [10, 10, 10, 10],
        'High': [10.2, 10.2, 10.2, 10.2],
        'Low': [9.8, 9.8, 9.8, 9.8],
        'Close': [10, 10.1, 10.2, 10.3],
        'Volume': [1000, 1000, 1000, 1000],
    }, index=idx)
    row = insufficient_history_row('SHORT', df, rs_rating=0.0)
    assert row['symbol'] == 'SHORT'
    assert row['analysis_status'] == 'INSUFFICIENT_HISTORY'
    assert row['trend_template']['conditions_met'] == 0
    assert row['trade_readiness']['status'] == 'INSUFFICIENT_HISTORY'
    assert row['daily_state']['setup_quality']['pass'] is False
    assert row['daily_state']['setup_proximity']['state'] is None
