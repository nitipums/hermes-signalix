# test_fetch_set50.py
import os, psycopg2
from fetch_set50 import parse_set50_from_page, seed_index_membership

def test_parse_handles_real_sample():
    html = "<tr><td>AOT</td><td>Airports of Thailand</td></tr><tr><td>BBL</td><td>Bangkok Bank</td></tr>"
    syms = parse_set50_from_page(html)
    assert "AOT" in syms and "BBL" in syms

def test_seed_is_idempotent():
    syms = ["AOT", "BBL", "PTT", "KBANK"]
    seed_index_membership(syms, source="test")
    seed_index_membership(syms, source="test")  # re-run
    pg = psycopg2.connect(host="127.0.0.1", port=5432, user="signalix",
                          password="signalix_pass", dbname="signalix")
    cur = pg.cursor()
    cur.execute("SELECT COUNT(*) FROM index_membership WHERE is_set50=TRUE")
    assert cur.fetchone()[0] == 4
    cur.execute("DELETE FROM index_membership")
    pg.commit(); pg.close()
