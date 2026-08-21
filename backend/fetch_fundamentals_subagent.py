"""Resumable SET factsheet scraper for company profile fundamentals.

Primary source: SET's public factsheet, read through Jina Reader because direct
SET requests commonly return 403 in server environments.  The scraper is
bounded by an explicit symbol limit/sample and writes JSONL progress after every
symbol.  It does not create or commit cache data.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SET_FACTSHEET = "https://www.set.or.th/en/market/product/stock/quote/{symbol}/factsheet"
JINA_FACTSHEET = "https://r.jina.ai/" + SET_FACTSHEET
_PERCENT = r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%"
_M_BAHT = re.compile(r"Market\s+Cap\.?\s*\(\s*M\.?\s*Baht\s*\)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", re.I)
_FOREIGN = re.compile(r"Foreign\s+Shareholders\s+" + _PERCENT + r"\s*(?:\(as of ([^)]+)\))?", re.I)
_LIMIT = re.compile(r"Foreign\s+Limit\s+" + _PERCENT + r"\s*(?:\(as of ([^)]+)\))?", re.I)
# SET labels the percentage associated with the preceding holder count as
# "% Shareholders"; this avoids confusing it with other percentages on page.
_FREE_FLOAT = re.compile(r"Free\s+Float\s+[0-9][0-9,]*\s*(?:\(as of [^)]+\))?\s+%\s*Shareholders\s+" + _PERCENT + r"\s*(?:\(as of ([^)]+)\))?", re.I)


def source_urls(symbol: str) -> tuple[str, str]:
    symbol = symbol.upper().strip()
    return SET_FACTSHEET.format(symbol=symbol), JINA_FACTSHEET.format(symbol=symbol)


def _number(value: str) -> float:
    return float(value.replace(",", ""))


def _as_of(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return dt.datetime.strptime(value.strip(), "%d %b %Y").date().isoformat()
    except ValueError:
        return value.strip()


def _latest(matches: Iterable[re.Match[str]]) -> tuple[float | None, str | None]:
    """Return the first/current occurrence; SET renders current before history."""
    match = next(iter(matches), None)
    if not match:
        return None, None
    return _number(match.group(1)), _as_of(match.group(2))


def parse_factsheet(text: str, symbol: str, fetched_at: str | None = None) -> dict[str, Any]:
    """Parse only unambiguous factsheet labels; missing values stay None."""
    market = _M_BAHT.search(text)
    free, free_date = _latest(_FREE_FLOAT.finditer(text))
    foreign, foreign_date = _latest(_FOREIGN.finditer(text))
    limit, limit_date = _latest(_LIMIT.finditer(text))
    evidence_dates = [d for d in (free_date, foreign_date, limit_date) if d and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)]
    return {
        "symbol": symbol.upper().strip(),
        "market_cap": int(round(_number(market.group(1)) * 1_000_000)) if market else None,
        "free_float_pct": free,
        "foreign_limit_pct": limit,
        "foreign_shareholders_pct": foreign,
        "evidence_date": max(evidence_dates) if evidence_dates else None,
        "fetched_at": fetched_at or dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def fetch_text(symbol: str, timeout: float = 30.0, opener: Callable[..., Any] = urlopen) -> tuple[str, str, str]:
    set_url, jina_url = source_urls(symbol)
    request = Request(jina_url, headers={"User-Agent": "Signalix factsheet backfill/1.0", "Accept": "text/plain"})
    with opener(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
    return body, set_url, jina_url


def _read_existing(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if row.get("symbol"):
                rows[row["symbol"].upper()] = row
        except json.JSONDecodeError:
            continue
    return rows


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def scrape(symbols: Iterable[str], output: Path, sleep: float = 1.0, timeout: float = 30.0, refresh: bool = False, fetcher: Callable[[str, float], tuple[str, str, str]] = fetch_text) -> dict[str, Any]:
    symbols = [s.upper().strip() for s in symbols if s.strip()]
    existing = _read_existing(output)
    report: dict[str, Any] = {"requested": len(symbols), "fetched": 0, "skipped_cached": 0, "parsed_market_cap": 0, "parsed_free_float": 0, "parsed_foreign_limit": 0, "errors": [], "source_urls": []}
    for index, symbol in enumerate(symbols):
        if symbol in existing and not refresh:
            report["skipped_cached"] += 1
            continue
        try:
            text, set_url, jina_url = fetcher(symbol, timeout)
            row = parse_factsheet(text, symbol)
            row.update({"source_url": set_url, "reader_url": jina_url})
            _append(output, row)
            existing[symbol] = row
            report["fetched"] += 1
            report["parsed_market_cap"] += row["market_cap"] is not None
            report["parsed_free_float"] += row["free_float_pct"] is not None
            report["parsed_foreign_limit"] += row["foreign_limit_pct"] is not None
            report["source_urls"].append(set_url)
        except (HTTPError, URLError, OSError, TimeoutError, ValueError) as exc:
            report["errors"].append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
        if index < len(symbols) - 1 and sleep > 0:
            time.sleep(sleep)
    return report


def symbols_from_db(cur: Any) -> list[str]:
    """Prefer the canonical active ORD universe, with safe legacy fallback."""
    cur.execute("SELECT to_regclass('public.symbol_master')")
    if cur.fetchone()[0]:
        cur.execute(
            """SELECT sm.symbol FROM symbol_master sm
               LEFT JOIN company_profiles cp ON cp.symbol = sm.symbol
               WHERE sm.instrument_type = 'ORD'
                 AND (sm.status IS NULL OR sm.status = 'active')
                 AND COALESCE(cp.source, '') <> 'set_factsheet'
               ORDER BY sm.symbol"""
        )
    else:
        cur.execute("SELECT DISTINCT symbol FROM price_data WHERE instrument_type = 'ORD' ORDER BY symbol")
    return [row[0] for row in cur.fetchall()]


def upsert_profile(cur: Any, row: dict[str, Any]) -> None:
    """Fill missing fields only; never overwrite existing XLSX evidence by default."""
    cur.execute(
        """INSERT INTO company_profiles (symbol, source, fetched_at, market_cap, free_float_pct, foreign_limit_pct)
           VALUES (%s, 'set_factsheet', %s, %s, %s, %s)
           ON CONFLICT (symbol) DO UPDATE SET
             market_cap = COALESCE(company_profiles.market_cap, EXCLUDED.market_cap),
             free_float_pct = COALESCE(company_profiles.free_float_pct, EXCLUDED.free_float_pct),
             foreign_limit_pct = COALESCE(company_profiles.foreign_limit_pct, EXCLUDED.foreign_limit_pct),
             source = CASE WHEN company_profiles.market_cap IS NULL OR company_profiles.free_float_pct IS NULL OR company_profiles.foreign_limit_pct IS NULL THEN 'set_factsheet' ELSE company_profiles.source END,
             fetched_at = CASE WHEN company_profiles.market_cap IS NULL OR company_profiles.free_float_pct IS NULL OR company_profiles.foreign_limit_pct IS NULL THEN EXCLUDED.fetched_at ELSE company_profiles.fetched_at END""",
        (row["symbol"], row.get("fetched_at"), row.get("market_cap"), row.get("free_float_pct"), row.get("foreign_limit_pct")),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="*", help="Explicit symbols; otherwise read active ORD universe from PostgreSQL")
    parser.add_argument("--limit", type=int, default=0, help="Hard bound on symbols fetched")
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=Path("fundamentals_scraped.jsonl"))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--no-upsert", action="store_true")
    args = parser.parse_args(argv)
    symbols = [s.upper() for s in args.symbols]
    connection = None
    if not args.no_upsert:
        import psycopg2
        connection = psycopg2.connect(host=os.getenv("POSTGRES_HOST", "127.0.0.1"), port=os.getenv("POSTGRES_PORT", "5432"), user=os.getenv("POSTGRES_USER", "signalix"), password=os.getenv("POSTGRES_PASSWORD", "signalix_pass"), dbname=os.getenv("POSTGRES_DB", "signalix"))
        cur = connection.cursor()
        if not symbols:
            symbols = symbols_from_db(cur)
    elif not symbols:
        raise SystemExit("explicit symbols are required with --no-upsert")
    if args.limit:
        symbols = symbols[:args.limit]
    report = scrape(symbols, args.output, sleep=args.sleep, refresh=args.refresh)
    if connection and not args.no_upsert:
        cur = connection.cursor()
        for row in _read_existing(args.output).values():
            if row["symbol"] in symbols:
                upsert_profile(cur, row)
        connection.commit()
        connection.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
