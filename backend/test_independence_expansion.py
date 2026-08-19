import psycopg2
import pytest

from build_dashboard import serialize, snapshots


pytestmark = pytest.mark.integration


def test_serialize_includes_all_new_fields():
    row = {
        "symbol": "TEST",
        "trade_readiness": {},
        "trend_template": {},
        "daily_state": {"stage": "S2_uptrend", "phase": "uptrend_pullback"},
    }
    snapshot = {
        "avgDailyValue20": 10_000_000,
        "close": 10,
        "high52": 12,
        "athHigh": 15,
        "volume": 1_000_000,
    }
    layer2 = {
        "structural": {"signals": {}, "group": "up_leg"},
        "momentum": {"signals": {}, "group": "strong"},
    }
    layer3 = {"score": 3, "flags": {"vol": True, "wk52": True, "ath": True}}
    item = serialize(
        "breakout_new", row, snapshot, {}, layer2, {"TEST"},
        layer3=layer3, sector="Technology", industry="Software",
        market_cap=1_000_000_000, free_float_pct=45.5,
        foreign_limit_pct=49.0,
    )

    assert item["layer2_structural"]["group"] == "up_leg"
    assert item["layer2_momentum"]["group"] == "strong"
    assert item["layer3_qualifier"]["score"] == 3
    assert item["independence"]["sector"] == "Technology"
    assert item["independence"]["industry"] == "Software"
    assert item["independence"]["market_cap"] == 1_000_000_000
    assert item["independence"]["free_float_pct"] == 45.5
    assert item["independence"]["foreign_limit_pct"] == 49.0


def pg_connect():
    return psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        user="signalix",
        password="signalix_pass",
        dbname="signalix",
    )


def test_snapshots_includes_sector_industry():
    pg = pg_connect()
    try:
        cur = pg.cursor()
        cur.execute("SELECT symbol FROM company_profiles WHERE sector IS NOT NULL LIMIT 5")
        profiled_symbols = [row[0] for row in cur.fetchall()]
        cur.execute(
            """SELECT DISTINCT pd.symbol
               FROM price_data pd
               LEFT JOIN company_profiles cp ON cp.symbol = pd.symbol
               WHERE pd.market = 'TH' AND cp.symbol IS NULL
               LIMIT 1"""
        )
        unprofiled_symbols = [row[0] for row in cur.fetchall()]
        cur.close()

        symbols = profiled_symbols + unprofiled_symbols
        out = snapshots(pg, symbols)

        for symbol in profiled_symbols:
            assert symbol in out
            assert out[symbol]["sector"] is not None
            assert out[symbol]["industry"] is not None

        for symbol in unprofiled_symbols:
            assert symbol in out
            assert out[symbol]["sector"] is None
            assert out[symbol]["industry"] is None
    finally:
        pg.close()
