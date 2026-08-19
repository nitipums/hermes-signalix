import json
from pathlib import Path

from fetch_fundamentals_subagent import parse_factsheet, scrape, source_urls

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
