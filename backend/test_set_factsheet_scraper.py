import json
import sys
import types
from pathlib import Path

import fetch_fundamentals_subagent as scraper
from fetch_fundamentals_subagent import (
    main,
    parse_factsheet,
    scrape,
    source_urls,
    symbols_from_db,
    upsert_profile,
)

FIXTURE = Path(__file__).parent / "tests" / "fixtures" / "set_ptt_factsheet.txt"


def test_parse_set_factsheet_units_dates_and_current_values():
    row = parse_factsheet(FIXTURE.read_text(), "ptt", fetched_at="2026-08-19T00:00:00+00:00")
    assert row["symbol"] == "PTT"
    assert row["market_cap"] == 1_156_801_350_000
    assert row["free_float_pct"] == 48.04
    assert row["foreign_shareholders_pct"] == 8.39
    assert row["foreign_limit_pct"] == 30.0
    assert row["evidence_date"] == "2026-08-18"


def test_missing_labels_are_null_not_guessed():
    row = parse_factsheet("Market Cap (M.Baht) 12.5\nForeign Limit n/a", "XYZ")
    assert row["market_cap"] == 12_500_000
    assert row["free_float_pct"] is None
    assert row["foreign_shareholders_pct"] is None
    assert row["foreign_limit_pct"] is None


def test_scrape_is_resumable_and_records_exact_urls(tmp_path):
    output = tmp_path / "facts.jsonl"
    calls = []

    def fake_fetch(symbol, timeout):
        calls.append((symbol, timeout))
        return FIXTURE.read_text(), *source_urls(symbol)

    first = scrape(["PTT", "AOT"], output, sleep=0, timeout=7, fetcher=fake_fetch)
    second = scrape(["PTT", "AOT"], output, sleep=0, timeout=7, fetcher=fake_fetch)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert first["fetched"] == 2
    assert second["skipped_cached"] == 2
    assert len(calls) == 2
    assert rows[0]["source_url"] == "https://www.set.or.th/en/market/product/stock/quote/PTT/factsheet"
    assert rows[1]["reader_url"] == "https://r.jina.ai/https://www.set.or.th/en/market/product/stock/quote/AOT/factsheet"


class RecordingCursor:
    def __init__(self, fetchone_result=("symbol_master",), rows=(("A",), ("B",))):
        self.fetchone_result = fetchone_result
        self.rows = rows
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.rows


def test_symbols_from_db_uses_only_active_ord_universe():
    cur = RecordingCursor()
    assert symbols_from_db(cur) == ["A", "B"]
    assert "instrument_type = 'ORD'" in cur.calls[1][0]
    assert "'COMMON'" not in cur.calls[1][0]
    assert "status = 'active'" in cur.calls[1][0]
    assert "COALESCE(cp.source, '') <> 'set_factsheet'" in cur.calls[1][0]


def test_symbols_from_db_legacy_fallback_stays_ord_only():
    cur = RecordingCursor(fetchone_result=(None,))
    symbols_from_db(cur)
    assert cur.calls[1][0] == "SELECT DISTINCT symbol FROM price_data WHERE instrument_type = 'ORD' ORDER BY symbol"


def test_upsert_profile_coalesces_existing_xlsx_evidence():
    cur = RecordingCursor()
    upsert_profile(cur, {"symbol": "PTT", "fetched_at": "now", "market_cap": 1, "free_float_pct": 2, "foreign_limit_pct": 3})
    sql, params = cur.calls[0]
    assert "COALESCE(company_profiles.market_cap, EXCLUDED.market_cap)" in sql
    assert "COALESCE(company_profiles.free_float_pct, EXCLUDED.free_float_pct)" in sql
    assert "COALESCE(company_profiles.foreign_limit_pct, EXCLUDED.foreign_limit_pct)" in sql
    assert params == ("PTT", "now", 1, 2, 3)


def test_explicit_symbols_connect_for_upsert_by_default(tmp_path, monkeypatch):
    output = tmp_path / "facts.jsonl"
    output.write_text(json.dumps({"symbol": "PTT", "fetched_at": "now", "market_cap": 1}) + "\n")
    cursor = RecordingCursor()

    class Connection:
        def cursor(self):
            return cursor

        def commit(self):
            self.committed = True

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=lambda **_: connection))
    monkeypatch.setattr(scraper, "scrape", lambda *args, **kwargs: {"errors": []})

    assert main(["PTT", "--output", str(output), "--sleep", "0"]) == 0
    assert connection.committed is True
    assert connection.closed is True
    assert cursor.calls and "INSERT INTO company_profiles" in cursor.calls[0][0]
