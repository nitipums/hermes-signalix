"""One-shot SET50 membership seeder. Run manually; never scheduled."""
import os, re, sys, datetime as dt
import psycopg2

PAGE_URL = "https://www.set.or.th/en/market/information/securities-list/constituents-list-set50-set100"
FALLBACK_DIR = "/root/set50_financials"
PG = dict(host="127.0.0.1", port=5432,
          user="signalix", password="signalix_pass", dbname="signalix")

def parse_set50_from_page(html: str) -> list[str]:
    """Extract 1-4 letter ticker symbols from the SET50 constituents HTML."""
    cands = re.findall(r">\s*([A-Z]{1,4})\s*<", html)
    seen = []
    for c in cands:
        if c not in seen:
            seen.append(c)
    return seen

def _fallback_from_dir() -> list[str]:
    if not os.path.isdir(FALLBACK_DIR):
        return []
    return sorted(d for d in os.listdir(FALLBACK_DIR)
                  if os.path.isdir(os.path.join(FALLBACK_DIR, d)))

def fetch_symbols() -> list[str]:
    try:
        import urllib.request
        with urllib.request.urlopen(PAGE_URL, timeout=20) as r:
            html = r.read().decode("utf-8", "ignore")
        syms = parse_set50_from_page(html)
        if len(syms) >= 40:
            return syms
    except Exception as e:
        print(f"[fetch_set50] page fetch failed: {e}", file=sys.stderr)
    fb = _fallback_from_dir()
    print(f"[fetch_set50] using fallback dir: {len(fb)} symbols")
    return fb

def seed_index_membership(symbols: list[str], source: str = "set.or.th-2026H1") -> int:
    today = dt.date.today().isoformat()
    pg = psycopg2.connect(**PG)
    try:
        cur = pg.cursor()
        cur.execute("SELECT to_regclass('public.index_membership')")
        if not cur.fetchone()[0]:
            raise RuntimeError("index_membership table missing — apply migration 002 first")
        for sym in symbols:
            cur.execute(
                """INSERT INTO index_membership(symbol,index_name,is_set50,effective_from,source)
                   VALUES(%s,'SET50',TRUE,%s,%s)
                   ON CONFLICT (symbol) DO UPDATE SET is_set50=EXCLUDED.is_set50,
                     effective_from=EXCLUDED.effective_from, source=EXCLUDED.source""",
                (sym, today, source))
        pg.commit()
        return len(symbols)
    finally:
        pg.close()

if __name__ == "__main__":
    syms = fetch_symbols()
    n = seed_index_membership(syms)
    print(f"Seeded {n} SET50 symbols")
