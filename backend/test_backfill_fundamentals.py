from pathlib import Path
import sys

import openpyxl

sys.path.insert(0, str(Path(__file__).parent))
from backfill_fundamentals import (  # noqa: E402
    extract_optional_percentages,
    extract_shares_outstanding,
    process_symbol,
    run,
)


def workbook_with_rows(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "arbitrary sheet"
    for row in rows:
        ws.append(row)
    return wb


def test_discovers_paid_shares_without_fixed_sheet_or_column():
    wb = workbook_with_rows(
        [
            ["ทุนจดทะเบียน"],
            ["หุ้นสามัญ 9,999,999 หุ้น"],
            ["ทุนที่ออกและชำระแล้ว"],
            ["หุ้นสามัญ : 1,234,567 หุ้น", 1234567],
        ]
    )
    assert extract_shares_outstanding(wb) == 1_234_567


def test_rejects_authorized_shares_and_keeps_optional_values_null():
    wb = workbook_with_rows(
        [
            ["ทุนจดทะเบียน หุ้นสามัญ 99,999,999 หุ้น"],
            ["ทุนที่ออกและชำระแล้ว"],
            ["หุ้นสามัญ 12,345,678 หุ้น"],
        ]
    )
    assert extract_shares_outstanding(wb) == 12_345_678
    assert extract_optional_percentages(wb) == (None, None)


def test_explicit_optional_percentages_are_parsed():
    wb = workbook_with_rows([["Free Float", "42.50%"], ["Foreign ownership limit: 49%"]])
    assert extract_optional_percentages(wb) == (42.5, 49.0)


def test_process_symbol_calculates_market_cap_and_missing_close_is_null(tmp_path):
    path = tmp_path / "ABC" / "year2568"
    path.mkdir(parents=True)
    wb = workbook_with_rows([["ทุนที่ออกและชำระแล้ว"], ["หุ้นสามัญ 2,000 หุ้น"]])
    wb.save(path / "financial_statements.xlsx")
    assert process_symbol("ABC", 12.5, tmp_path)["market_cap"] == 25_000
    assert process_symbol("ABC", None, tmp_path)["market_cap"] is None


class FakeCursor:
    def __init__(self):
        self.rows = [("ABC", 12.5)]
        self.upserts = []

    def execute(self, sql, params=None):
        if params is not None:
            self.upserts.append(params)

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.cur = FakeCursor()

    def cursor(self):
        return self.cur

    def commit(self):
        pass


def test_run_upserts_profile_and_does_not_filter_symbol_universe(tmp_path):
    for symbol, shares in (("ABC", 2000), ("XYZ", 3000)):
        path = tmp_path / symbol / "year2568"
        path.mkdir(parents=True)
        wb = workbook_with_rows([["ทุนที่ออกและชำระแล้ว"], [f"หุ้นสามัญ {shares:,} หุ้น"]])
        wb.save(path / "FINANCIAL_STATEMENTS.XLSX")
    conn = FakeConnection()
    report = run(tmp_path, conn)
    assert report["symbols"] == 2
    assert report["rows_upserted"] == 2
    assert report["parsed_shares"] == 2
    assert len(conn.cur.upserts) == 2


def test_share_units_are_normalized():
    wb = workbook_with_rows([["ทุนที่ออกและชำระแล้ว"], ["หุ้นสามัญจำนวน 8,983 ล้านหุ้น"]])
    assert extract_shares_outstanding(wb) == 8_983_000_000
