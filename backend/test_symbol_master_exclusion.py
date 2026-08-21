"""Tests: symbol_master exclusion (delisted/inactive) is respected by scan + dashboard."""
import os
import sys
import unittest

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if os.getenv("POSTGRES_HOST", "postgres") == "postgres":
    os.environ["POSTGRES_HOST"] = "127.0.0.1"

import screening
import psycopg2


pytestmark = pytest.mark.integration


def pg_connect():
    return psycopg2.connect(host="127.0.0.1", port=5432, user="signalix",
                            password="signalix_pass", dbname="signalix")


class TestSymbolMasterExclusion(unittest.TestCase):
    def test_symbol_master_exists_and_counts(self):
        excluded = screening.excluded_symbols()
        # 263 delisted + 17 inactive marked by the 60m backfill run.
        self.assertGreaterEqual(len(excluded), 260)
        self.assertTrue(any(s in excluded for s in ("ABC", "BIGC", "INTUCH")))

    def test_active_scan_symbols_skips_excluded(self):
        pg = pg_connect()
        try:
            syms = screening._active_scan_symbols(pg, instrument_types=("ORD",))
        finally:
            pg.close()
        self.assertNotIn("ABC", syms)
        self.assertNotIn("BIGC", syms)
        self.assertNotIn("INTUCH", syms)
        # active names still present
        self.assertIn("KBANK", syms)
        self.assertIn("PTT", syms)
        # Scan universe = active ORD symbols present in price_data (no staleness
        # pre-filter) minus excluded master symbols. Bind to live DB state, not
        # a stale hardcode.
        pg2 = pg_connect()
        try:
            cur = pg2.cursor()
            cur.execute("SELECT count(DISTINCT symbol) FROM price_data "
                        "WHERE market='TH' AND instrument_type='ORD'")
            present = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM symbol_master WHERE status IN "
                        "('inactive','delisted','excluded')")
            excluded_master = cur.fetchone()[0]
        finally:
            pg2.close()
        self.assertEqual(len(syms), present - excluded_master)

    def test_scan_universe_excludes_delisted(self):
        cands, near = screening.scan_universe(min_conditions=8, limit=None)
        all_syms = [r["symbol"] for r in cands] + [r["symbol"] for r in near]
        excluded = screening.excluded_symbols()
        overlap = set(all_syms) & excluded
        self.assertEqual(overlap, set(),
                         f"scan leaked excluded symbols: {sorted(overlap)[:10]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
