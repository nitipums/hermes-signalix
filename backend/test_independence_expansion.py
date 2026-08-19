import psycopg2
import pytest

from build_dashboard import snapshots


pytestmark = pytest.mark.integration


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
