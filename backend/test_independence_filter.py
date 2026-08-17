from build_dashboard import _price_band, _passes_value


def test_price_band_thresholds():
    assert _price_band(1.5) == "low"
    assert _price_band(5.0) == "mid"
    assert _price_band(15.0) == "high"
    assert _price_band(None) is None


def test_passes_value_boundary():
    assert _passes_value(5_000_000) is True
    assert _passes_value(4_999_999) is False
    assert _passes_value(None) is False
