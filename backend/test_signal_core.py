def test_signal_core_exposes_scanner_math_contract():
    import signal_core
    for name in (
        "compute_rs_rating", "compute_rs_percentile", "detect_vcp",
        "trend_template", "position_sizing", "buy_zone", "trade_readiness",
        "MIN_DAYS", "VCP_PERIOD", "RS_THRESHOLD", "RS_LOOKBACK",
    ):
        assert hasattr(signal_core, name), name


def test_screening_uses_signal_core_not_scanner():
    import screening
    assert screening.compute_rs_rating.__module__ == "signal_core"
    assert screening.detect_vcp.__module__ == "signal_core"
