import pandas as pd, numpy as np
from screening import compute_layer2, universe_layer2, load_index_membership

def _make_60m(close_trend, n=120):
    idx = pd.date_range("2026-01-01", periods=n, freq="60min")
    close = np.array(close_trend)
    df = pd.DataFrame({"Open":close,"High":close*1.01,"Low":close*0.99,"Close":close,"Volume":1000.0}, index=idx)
    return df

def test_compute_layer2_up_strong():
    df = _make_60m(np.linspace(100,200,num=120))
    r = compute_layer2("X", df)
    assert r["group"] in {"momentum_up","momentum_strong","overbought"}
    assert set(r["signals"].keys()) == {"mini_trend","macd","rsi"}
    assert isinstance(r["signals"]["rsi"], (int,float))

def test_compute_layer2_enum_closed():
    df = _make_60m(np.linspace(100,50,num=120))
    r = compute_layer2("Y", df)
    assert r["group"] in {"momentum_up","momentum_strong","neutral",
                          "momentum_down","overbought","oversold"}

def test_universe_layer2_skips_missing():
    pg = __import__("psycopg2").connect(host="127.0.0.1",port=5432,user="signalix",
                                        password="signalix_pass",dbname="signalix")
    out = universe_layer2(pg, ["THIS_SYM_HAS_NO_60M_XYZ"])
    assert "THIS_SYM_HAS_NO_60M_XYZ" not in out
    pg.close()

def test_load_index_membership_returns_set():
    pg = __import__("psycopg2").connect(host="127.0.0.1",port=5432,user="signalix",
                                        password="signalix_pass",dbname="signalix")
    s = load_index_membership(pg)
    assert isinstance(s, set)
    pg.close()
