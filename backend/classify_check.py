"""
Dry-run classification check (NO DB writes) to verify the keep/cut rule
before re-ingesting. Rule:
  CUT if ticker:
    - endswith -O/-F/-M/-P
    - startswith ! or $
    - starts with a digit
    - contains '-W' (warrant)
    - matches r'\d{2}[CP]\d{2}'  e.g. 01C26 / 01P26  (warrant call/put)
  KEEP otherwise  -> includes ordinary shares (A-Z only) AND DRs (e.g. AAPL01)
"""
import re, glob, os, csv
WARRANT_RE = re.compile(r'\d{2}[CP]\d{2}')

def classify(tk):
    if tk.endswith(("-O","-F","-M","-P")): return "CUT_suffix"
    if tk.startswith(("!","$")): return "CUT_prefix"
    if tk[0:1].isdigit(): return "CUT_leading_digit"
    if "-W" in tk: return "CUT_warrant_W"
    if WARRANT_RE.search(tk): return "CUT_warrant_CP"
    return "KEEP"

DATA_DIR = "/root/signalix/seed_data/set-archive_EOD"
files = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))
seen = {}
for p in files:
    with open(p, newline="") as f:
        r = csv.reader(f); next(r, None)
        for row in r:
            if len(row) < 1: continue
            tk = row[0].strip()
            if tk not in seen:
                seen[tk] = classify(tk)

from collections import Counter
c = Counter(seen.values())
print("=== classification counts (distinct tickers) ===")
for k,v in c.most_common():
    print(f"  {k:18s} {v}")
kept = [t for t,s in seen.items() if s=="KEEP"]
kept_digits = [t for t in kept if any(ch.isdigit() for ch in t)]  # DR candidates
print(f"\nKEEP total: {len(kept)}   (of which have digits = DR-likely: {len(kept_digits)})")
print("=== sample KEEP-with-digits (DR candidates) — please verify these ARE DRs ===")
for t in sorted(kept_digits)[:40]:
    print("  ", t)
print("\n=== sample KEEP plain ordinary (no digits) ===")
for t in sorted([t for t in kept if not any(ch.isdigit() for ch in t)])[:40]:
    print("  ", t)
print("\n=== sample CUT_warrant_CP ===")
for t,s in sorted(seen.items()):
    if s=="CUT_warrant_CP": print("  ", t)
print("(showing up to 15)")
