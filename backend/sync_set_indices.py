#!/usr/bin/env python3
"""Synchronize SET50/SET100 membership from SET's official PDF.

The landing page is checked monthly, but the database changes only when the
published PDF URL/effective period or membership content changes.  The PDF is
also the source for SET's sector label at the time of the index review; this
script stores index membership only, while company profiles remain separate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
from dataclasses import dataclass
from urllib.parse import unquote

import requests

LANDING_URL = "https://www.set.or.th/en/market/information/securities-list/constituents-list-set50-set100"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/151 Safari/537.36"

@dataclass(frozen=True)
class IndexSnapshot:
    source_url: str
    effective_from: dt.date
    effective_to: dt.date
    set50: tuple[str, ...]
    set100: tuple[str, ...]


def latest_pdf_url(html: str) -> str:
    urls = re.findall(r"https://media\.set\.or\.th/set/Documents/[^\"'<> ]+\.pdf", html, re.I)
    urls = [unquote(x).replace("&amp;", "&") for x in urls if "SET50" in x.upper() or "SET100" in x.upper()]
    if not urls:
        raise ValueError("official SET landing page contains no SET50/SET100 PDF")
    # Page order is newest first. Preserve order but deduplicate query variants.
    return next(iter(dict.fromkeys(urls)))


def effective_period(source_url: str) -> tuple[dt.date, dt.date]:
    name = source_url.rsplit("/", 1)[-1].upper()
    m = re.search(r"(?:H|_H)([12])[_-](20\d{2})", name)
    if not m:
        # Known official naming variant: SET50-SET100-H2-2026.pdf
        m = re.search(r"H([12])[-_](20\d{2})", name)
    if not m:
        raise ValueError(f"cannot determine H1/H2 period from {source_url}")
    half, year = int(m.group(1)), int(m.group(2))
    start = dt.date(year, 1 if half == 1 else 7, 1)
    end = dt.date(year, 6, 30) if half == 1 else dt.date(year, 12, 31)
    return start, end


def _page_texts(pdf_bytes: bytes) -> list[str]:
    try:
        import fitz  # PyMuPDF, already a backend dependency
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required to parse official SET index PDFs") from exc
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return [page.get_text("text") for page in doc]


def _symbols_from_page(text: str, max_no: int) -> dict[int, str]:
    """Read rows from SET's repeated No/Symbol/Company Name/Sector table."""
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    out: dict[int, str] = {}
    for i, line in enumerate(lines[:-1]):
        if not line.isdigit() or not 1 <= int(line) <= max_no:
            continue
        symbol = re.sub(r"[^A-Z0-9.&-]", "", lines[i + 1].upper())
        if re.fullmatch(r"[A-Z][A-Z0-9.&-]{0,9}", symbol):
            out.setdefault(int(line), symbol)
    return out


def parse_pdf_text(pages: list[str], source_url: str) -> IndexSnapshot:
    start, end = effective_period(source_url)
    # Official layout: pages 1-2 contain SET50 inclusion rows 1..50;
    # pages 3+ contain SET100 inclusion rows 1..100. Exclusion tables after
    # each inclusion table are intentionally ignored by the row-number bounds.
    set50: dict[int, str] = {}
    set100: dict[int, str] = {}
    for page_no, text in enumerate(pages):
        rows = _symbols_from_page(text, 100)
        if page_no < 2:
            for n, symbol in rows.items():
                if n <= 50 and n not in set50:
                    set50[n] = symbol
        elif page_no >= 2:
            for n, symbol in rows.items():
                if n not in set100:
                    set100[n] = symbol
    if len(set50) != 50:
        raise ValueError(f"expected 50 SET50 rows, got {len(set50)}")
    if len(set100) != 100:
        raise ValueError(f"expected 100 SET100 rows, got {len(set100)}")
    return IndexSnapshot(source_url, start, end,
                         tuple(set50[n] for n in range(1, 51)),
                         tuple(set100[n] for n in range(1, 101)))


def fetch_snapshot() -> IndexSnapshot:
    session = requests.Session()
    response = session.get(LANDING_URL, headers={"User-Agent": UA}, timeout=30)
    response.raise_for_status()
    url = latest_pdf_url(response.text)
    pdf = session.get(url, headers={"User-Agent": UA, "Referer": LANDING_URL}, timeout=30)
    pdf.raise_for_status()
    return parse_pdf_text(_page_texts(pdf.content), url)


def sync_db(snapshot: IndexSnapshot, dry_run: bool = False) -> dict:
    import os
    import psycopg2
    pg = psycopg2.connect(host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
                          port=os.getenv("POSTGRES_PORT", "5432"),
                          user=os.getenv("POSTGRES_USER", "signalix"),
                          password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"),
                          dbname=os.getenv("POSTGRES_DB", "signalix"))
    try:
        cur = pg.cursor()
        cur.execute("""SELECT index_name, symbol FROM index_memberships
                       WHERE effective_from=%s AND effective_to=%s AND source=%s""",
                    (snapshot.effective_from, snapshot.effective_to, snapshot.source_url))
        existing = {(name, symbol) for name, symbol in cur.fetchall()}
        expected = {("SET50", s) for s in snapshot.set50} | {("SET100", s) for s in snapshot.set100}
        if existing == expected:
            return {"status": "unchanged", "set50": 50, "set100": 100,
                    "effective_from": snapshot.effective_from.isoformat(), "source": snapshot.source_url}
        if dry_run:
            return {"status": "would_sync", "set50": 50, "set100": 100,
                    "effective_from": snapshot.effective_from.isoformat(), "source": snapshot.source_url,
                    "existing_rows": len(existing)}
        cur.execute("""UPDATE index_memberships SET effective_to=%s
                       WHERE effective_to IS NULL AND effective_from < %s
                         AND index_name IN ('SET50','SET100')""",
                    (snapshot.effective_from - dt.timedelta(days=1), snapshot.effective_from))
        for name, symbols in (("SET50", snapshot.set50), ("SET100", snapshot.set100)):
            for symbol in symbols:
                cur.execute("""INSERT INTO index_memberships
                    (symbol,index_name,effective_from,effective_to,source)
                    VALUES(%s,%s,%s,%s,%s)
                    ON CONFLICT (symbol,index_name,effective_from) DO UPDATE SET
                      effective_to=EXCLUDED.effective_to, source=EXCLUDED.source,
                      fetched_at=NOW()""",
                    (symbol, name, snapshot.effective_from, snapshot.effective_to, snapshot.source_url))
        pg.commit()
        return {"status": "synced", "set50": 50, "set100": 100,
                "effective_from": snapshot.effective_from.isoformat(), "source": snapshot.source_url}
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    snapshot = fetch_snapshot()
    print(sync_db(snapshot, dry_run=args.dry_run))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
