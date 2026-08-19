# test_fetch_set50.py
import psycopg2
from fetch_set50 import parse_set50_from_page, seed_index_membership

# Use clearly-fake, non-SET50 test symbols (5-char, never real constituents)
# so the idempotency test can never collide with — and corrupt — real rows.
TEST_SYMS = ["TESTA", "TESTB", "TESTC", "TESTD"]
TEST_SOURCE = "test-fetch-set50"

def test_parse_handles_real_sample():
    html = "<tr><td>AOT</td><td>Airports of Thailand</td></tr><tr><td>BBL</td><td>Bangkok Bank</td></tr>"
    syms = parse_set50_from_page(html)
    assert "AOT" in syms and "BBL" in syms

def test_seed_is_idempotent():
    seed_index_membership(TEST_SYMS, source=TEST_SOURCE)
    seed_index_membership(TEST_SYMS, source=TEST_SOURCE)  # re-run
    pg = psycopg2.connect(host="127.0.0.1", port=5432, user="signalix",
                          password="signalix_pass", dbname="signalix")
    try:
        cur = pg.cursor()
        # Idempotency check: the 4 test symbols must total exactly 4 rows
        # (double-seeding must NOT create duplicates).
        cur.execute(
            "SELECT COUNT(*) FROM index_membership "
            "WHERE symbol IN %s AND source=%s", (tuple(TEST_SYMS), TEST_SOURCE))
        assert cur.fetchone()[0] == 4
    finally:
        # Scoped cleanup: remove ONLY the test-source rows. This can never
        # touch real SET50 rows (source='set.or.th-2026H1'), even if a test
        # symbol happened to collide with a real ticker.
        cur = pg.cursor()
        cur.execute(
            "DELETE FROM index_membership WHERE source=%s", (TEST_SOURCE,))
        pg.commit()
        pg.close()
