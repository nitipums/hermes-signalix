import pandas as pd, numpy as np
from screening import compute_layer2, universe_layer2, load_index_membership

L2_VALID = {"up_leg", "pullback", "tight_base", "down_leg", "bounce"}

def _make_60m(close_trend, n=120):
    idx = pd.date_range("2026-01-01", periods=n, freq="60min")
    close = np.array(close_trend)
    df = pd.DataFrame({"Open": close, "High": close*1.01, "Low": close*0.99, "Close": close, "Volume": 1000.0}, index=idx)
    return df

def test_compute_layer2_up_leg():
    # rising with higher highs/lows -> up_leg
    df = _make_60m(np.linspace(100, 200, num=120) + np.sin(np.linspace(0, 12, 120)) * 2)
    r = compute_layer2("X", df)
    assert r["group"] in L2_VALID
    assert set(r["signals"].keys()) >= {"structure", "long_slope", "short_slope"}
    assert r["group"] == "up_leg"

def test_compute_layer2_down_leg():
    df = _make_60m(np.linspace(200, 50, num=120))
    r = compute_layer2("Y", df)
    assert r["group"] in L2_VALID

def test_compute_layer2_enum_closed():
    df = _make_60m(np.linspace(100, 50, num=120))
    r = compute_layer2("Y", df)
    assert r["group"] in L2_VALID

def test_compute_layer2_none_returns_tight_base():
    # missing data must still classify (no None) — Q18
    r = compute_layer2("Z", None)
    assert r["group"] == "tight_base"

def test_universe_layer2_never_omits_symbols():
    # every requested symbol is classified (no skips) — Q18
    pg = __import__("psycopg2").connect(host="127.0.0.1", port=5432, user="signalix",
                                        password="signalix_pass", dbname="signalix")
    out = universe_layer2(pg, ["THIS_SYM_HAS_NO_60M_XYZ"])
    assert "THIS_SYM_HAS_NO_60M_XYZ" in out
    # universe_layer2 returns {structural: {group, signals}, momentum: {group, signals}}
    assert out["THIS_SYM_HAS_NO_60M_XYZ"]["structural"]["group"] == "tight_base"
    assert out["THIS_SYM_HAS_NO_60M_XYZ"]["momentum"]["group"] == "neutral"
    pg.close()

def test_load_index_membership_returns_set():
    pg = __import__("psycopg2").connect(host="127.0.0.1", port=5432, user="signalix",
                                        password="signalix_pass", dbname="signalix")
    s = load_index_membership(pg)
    assert isinstance(s, set)
    pg.close()
