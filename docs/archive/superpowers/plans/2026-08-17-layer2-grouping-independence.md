# Signalix Layer 2 + Independence Filter + UI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Layer-2 short-term momentum grouping (60m: mini-trend + MACD + RSI) and an Independence filter (SET50 / value / price band) to the Signalix screener, plus a stage-first dashboard UI refresh where L2 is a drill-down subgroup inside each L1 stage section.

**Architecture:** `screening.py` computes `layer2` per symbol from 60m bars (reusing existing MA/MACD/RSI math on a 60m DataFrame) and reads SET50 membership from a new `index_membership` table seeded once by `fetch_set50.py`. `build_dashboard.py` attaches `layer2_*` + `independence` fields to each card and sorts within-stage by L2 group. The dashboard template gets a global Independence filter bar (SET50/value/price) and per-stage L2 subgroup pills (client-side, over the loaded JSON). No scoring, no daily SET50 refresh.

**Tech Stack:** Python 3.12, psycopg2, pandas, numpy (already in `/root/.venv_img`), Flask/uvicorn backend, vanilla JS dashboard template.

**Spec:** `docs/superpowers/specs/2026-08-17-layer2-grouping-independence-design.md` (v2.1)

## Global Constraints

- Layer 1 must scan the FULL ORD universe (no price/volume/stale pre-filter). Excluded (delisted/inactive) symbols from `symbol_master` stay out — verified 280 excluded.
- `build(scanned=...)` receives the scanned list directly; never re-read `scan_results.json`.
- `reconciled_projection.apply_projection` stays neutral (no hard-coded count, no taxonomy drop).
- Modal CSS (`.modal-bg.open`) is mandatory — do NOT remove it.
- Chart is on-demand via `GET /chart/{symbol}?timeframe=...`; never bake OHLC into items.
- No git history discipline beyond what the user approved; commit frequently per task.
- SET50 fetch is ONE-SHOT only (no cron/scheduler). Re-run manually when SET revises the index.
- L2 has NO scoring this round — grouping + signals only.

---

### Task 1: Migration — `index_membership` table

**Files:**
- Create: `backend/migrations/002_index_membership.sql`

**Interfaces:**
- Produces: table `index_membership(symbol TEXT PK, index_name TEXT, is_set50 BOOLEAN, effective_from DATE, source TEXT, fetched_at TIMESTAMPTZ)`

- [ ] **Step 1: Write the migration SQL**

```sql
CREATE TABLE IF NOT EXISTS index_membership (
    symbol         TEXT PRIMARY KEY,
    index_name     TEXT NOT NULL,
    is_set50       BOOLEAN NOT NULL DEFAULT FALSE,
    effective_from DATE,
    source         TEXT,
    fetched_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_index_membership_set50 ON index_membership (is_set50);
```

- [ ] **Step 2: Apply the migration**

Run:
```bash
cd /root/signalix/backend && \
PGPASSWORD=signalix_pass psql -h 127.0.0.1 -U signalix -d signalix -f migrations/002_index_membership.sql
```
Expected: `CREATE TABLE` / `CREATE INDEX` with no error.

- [ ] **Step 3: Commit**

```bash
cd /root/signalix && git add backend/migrations/002_index_membership.sql && git commit -m "migrate: add index_membership table for SET50 membership"
```

---

### Task 2: `fetch_set50.py` one-shot seeder

**Files:**
- Create: `backend/fetch_set50.py`
- Test: `backend/test_fetch_set50.py`

**Interfaces:**
- Consumes: SET official constituents page URL; fallback local dir `/root/set50_financials/<SYMBOL>` (48 dirs from prior work).
- Produces: upserts rows into `index_membership` with `index_name='SET50'`, `is_set50=TRUE`, `source='set.or.th-2026H1'`, `effective_from=<today>`. Idempotent.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/root/.venv_img/bin/python -m pytest test_fetch_set50.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'fetch_set50'`).

- [ ] **Step 3: Write minimal implementation**

```python
# fetch_set50.py
"""One-shot SET50 membership seeder. Run manually; never scheduled."""
import os, re, sys, datetime as dt
import psycopg2

PAGE_URL = "https://www.set.or.th/en/market/information/securities-list/constituents-list-set50-set100"
FALLBACK_DIR = "/root/set50_financials"
PG = dict(host=os.getenv("POSTGRES_HOST","127.0.0.1"), port=5432,
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/root/.venv_img/bin/python -m pytest test_fetch_set50.py -v`
Expected: PASS.

- [ ] **Step 5: Run the seeder once**

Run:
```bash
cd /root/signalix/backend && /root/.venv_img/bin/python fetch_set50.py
```
Expected: prints `Seeded N SET50 symbols` (N ~ 48-50).

- [ ] **Step 6: Commit**

```bash
cd /root/signalix && git add backend/fetch_set50.py backend/test_fetch_set50.py && git commit -m "feat: one-shot SET50 seeder (fetch_set50.py) + test"
```

---

### Task 3: Layer 2 compute in `screening.py`

**Files:**
- Modify: `backend/screening.py` (add functions near `load_symbol_intraday`)
- Test: `backend/test_layer2_grouping.py`

**Interfaces:**
- Consumes: `load_symbol_intraday(symbol, interval="60m", lookback=400)` (exists).
- Produces:
  - `compute_layer2(symbol, df_60m) -> dict` with keys `signals` (`mini_trend`, `macd`, `rsi`) and `group` (one of 6 enum values).
  - `universe_layer2(pg, symbols) -> dict[str, dict]` mapping symbol -> compute_layer2 result; symbols without 60m data are omitted.
  - `load_index_membership(pg) -> set[str]` of SET50 symbols.

- [ ] **Step 1: Write the failing test**

```python
# test_layer2_grouping.py
import pandas as pd, numpy as np
from screening import compute_layer2, universe_layer2, load_index_membership

def _make_60m(close_trend, n=120):
    idx = pd.date_range("2026-01-01", periods=n, freq="60min")
    close = np.array(close_trend)
    df = pd.DataFrame({"Open":close,"High":close*1.01,"Low":close*0.99,"Close":close,"Volume":1000.0}, index=idx)
    return df

def test_compute_layer2_up_strong():
    df = _make_60m(np.linspace(100,200,n=120))
    r = compute_layer2("X", df)
    assert r["group"] in {"momentum_up","momentum_strong","overbought"}
    assert set(r["signals"].keys()) == {"mini_trend","macd","rsi"}
    assert isinstance(r["signals"]["rsi"], (int,float))

def test_compute_layer2_enum_closed():
    df = _make_60m(np.linspace(100,50,n=120))
    r = compute_layer2("Y", df)
    assert r["group"] in {"momentum_up","momentum_strong","neutral",
                          "momentum_down","overbought","oversold"}

def test_universe_layer2_skips_missing():
    pg = __import__("psycopg2").connect(host="127.0.0.1",port=5432,user="signalix",
                                        password="signalix_pass",dbname="signalix")
    out = universe_layer2(pg, ["THIS_SYM_HAS_NO_60M_XYZ"])
    assert "THIS_SYM_HAS_NO_60M_XYZ" not in out
    pg.close()

def test_load_index_membership_returns_set():
    pg = __import__("psycopg2").connect(host="127.0.0.1",port=5432,user="signalix",
                                        password="signalix_pass",dbname="signalix")
    s = load_index_membership(pg)
    assert isinstance(s, set)
    pg.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/root/.venv_img/bin/python -m pytest test_layer2_grouping.py -v`
Expected: FAIL (functions not defined).

- [ ] **Step 3: Write minimal implementation** (append to `screening.py`)

```python
# --- Layer 2: short-term momentum grouping on 60m bars (no scoring) ---
def _ema(series, n):
    if len(series) < n or n <= 0:
        return None
    alpha, x = 2/(n+1), float(series.iloc[0])
    for v in series.iloc[1:]:
        x = float(v)*alpha + x*(1-alpha)
    return x

def _macd_state(close):
    if len(close) < 35:
        return "cross", 0.0
    vals = close.astype(float).tolist()
    a12, a26, a9 = 2/13, 2/27, 2/10
    e12, e26 = vals[0], vals[0]
    macd_line = []
    for v in vals:
        e12 = v*a12 + e12*(1-a12); e26 = v*a26 + e26*(1-a26)
        macd_line.append(e12 - e26)
    ms = macd_line[0]
    for m in macd_line[1:]:
        ms = m*a9 + ms*(1-a9)
    signal = ms
    macd_now = macd_line[-1]
    macd_prev = macd_line[-2] if len(macd_line) > 1 else macd_now
    diff_now = macd_now - signal
    diff_prev = macd_prev - signal
    if diff_now > 0 and macd_now > 0:
        state = "bullish"
    elif diff_now < 0 and macd_now < 0:
        state = "bearish"
    else:
        state = "cross"
    if (diff_now > 0) != (diff_prev > 0):
        state = "cross"
    return state, round(macd_now, 4)

def _rsi(close, period=14):
    if len(close) < period+1:
        return 50.0
    delta = close.diff().dropna()
    if len(delta) < period:
        return 50.0
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    ag = gains.rolling(period).mean().iloc[-1]
    al = losses.rolling(period).mean().iloc[-1]
    if al == 0:
        return 100.0
    rs = ag/al
    return round(100 - 100/(1+rs), 2)

def compute_layer2(symbol, df_60m):
    """Classify short-term momentum on 60m bars. Returns signals + group enum."""
    if df_60m is None or len(df_60m) < 30:
        return {"signals": {"mini_trend": "flat", "macd": "cross", "rsi": None}, "group": "neutral"}
    close = df_60m["Close"].astype(float)
    ma50 = close.rolling(50).mean()
    ma50_now = ma50.iloc[-1] if len(close) >= 50 else close.mean()
    ma50_prev = ma50.iloc[-5] if len(close) >= 54 else ma50_now
    slope = (ma50_now - ma50_prev) if ma50_prev else 0.0
    price = float(close.iloc[-1])
    mini_trend = "up" if (price > ma50_now and slope > 0) else \
                 "down" if (price < ma50_now and slope < 0) else "flat"
    macd_state, _ = _macd_state(close)
    rsi = _rsi(close, 14)
    if rsi >= 70:
        group = "overbought"
    elif rsi <= 30:
        group = "oversold"
    elif mini_trend == "up" and macd_state == "bullish":
        group = "momentum_strong"
    elif mini_trend == "up":
        group = "momentum_up"
    elif mini_trend == "down":
        group = "momentum_down"
    else:
        group = "neutral"
    return {"signals": {"mini_trend": mini_trend, "macd": macd_state, "rsi": rsi},
            "group": group}

def universe_layer2(pg, symbols):
    out = {}
    for sym in symbols:
        df = load_symbol_intraday(sym, pg=pg, interval="60m", lookback=400)
        if df is None or len(df) < 30:
            continue
        try:
            out[sym] = compute_layer2(sym, df)
        except Exception:
            continue
    return out

def load_index_membership(pg):
    cur = pg.cursor()
    cur.execute("SELECT to_regclass('public.index_membership')")
    if not cur.fetchone()[0]:
        cur.close(); return set()
    cur.execute("SELECT symbol FROM index_membership WHERE is_set50 = TRUE")
    rows = {r[0] for r in cur.fetchall()}
    cur.close()
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/root/.venv_img/bin/python -m pytest test_layer2_grouping.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /root/signalix && git add backend/screening.py backend/test_layer2_grouping.py && git commit -m "feat(screening): Layer 2 60m momentum grouping + SET50 membership loader"
```

---

### Task 4: Attach L2 + independence fields in `build_dashboard.py`

**Files:**
- Modify: `backend/build_dashboard.py` (`serialize` ~line 551, `build` ~line 735)
- Test: `backend/test_independence_filter.py`

**Interfaces:**
- Consumes: `universe_layer2(pg, symbols)`, `load_index_membership(pg)` (Task 3); `snapshots()` already returns `avgDailyValue20`.
- Produces: each item carries `layer1_stage`, `layer2_signals`, `layer2_group`, `independence{is_set50,avgTradeValue20,priceBand,passesValueFilter}`, `layer3_qualifiers={}`. `build()` sorts within-stage by L2 group priority then `rs` desc.

- [ ] **Step 1: Write the failing test**

```python
# test_independence_filter.py
from build_dashboard import _price_band, _passes_value

def test_price_band_thresholds():
    assert _price_band(1.5) == "low"
    assert _price_band(5.0) == "mid"
    assert _price_band(15.0) == "high"
    assert _price_band(None) is None

def test_passes_value_boundary():
    assert _passes_value(5_000_000) is True
    assert _passes_value(4_999_999) is False
    assert _passes_value(None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/root/.venv_img/bin/python -m pytest test_independence_filter.py -v`
Expected: FAIL (`ImportError` / functions missing).

- [ ] **Step 3: Add helper functions to `build_dashboard.py`** (near top, after `INTRADAY_STALE_HOURS`)

```python
def _price_band(close):
    try:
        c = float(close)
    except (TypeError, ValueError):
        return None
    if c < 2.0:
        return "low"
    if c <= 10.0:
        return "mid"
    return "high"

def _passes_value(avg_daily_value):
    try:
        v = float(avg_daily_value)
    except (TypeError, ValueError):
        return False
    return v >= 5_000_000
```

- [ ] **Step 4: Update `serialize` signature to accept `layer2=None, set50=None`**

Change the `def serialize(group, row, snapshot, intraday_state=None):` line to:
```python
def serialize(group, row, snapshot, intraday_state=None, layer2=None, set50=None):
```
and inside, add near the top:
```python
    l2 = layer2 or {}
    s50 = set50 or set()
```

- [ ] **Step 5: Add L2 + independence fields to the returned dict** (insert before the final `}` of the return dict, after `"tvUrl": ...` line)

```python
        # --- Layer 2 (short-term momentum grouping, 60m) + Independence filter ---
        "layer1_stage": stage or "S1_basing",
        "layer2_signals": l2.get("signals", {}),
        "layer2_group": l2.get("group"),
        "independence": {
            "is_set50": row["symbol"] in s50,
            "avgTradeValue20": number(snapshot.get("avgDailyValue20"), 0),
            "priceBand": _price_band(snapshot.get("close")),
            "passesValueFilter": _passes_value(snapshot.get("avgDailyValue20")),
        },
        "layer3_qualifiers": {},
```

- [ ] **Step 6: Update `snapshot_items` (line ~431) caller**

Change:
```python
    items = [serialize(key, row, latest.get(row["symbol"], {}))
             for key, values in source_groups.items() for row in values]
```
to:
```python
    items = [serialize(key, row, latest.get(row["symbol"], {}), None,
                      layer2_map.get(row["symbol"]), set50_set)
             for key, values in source_groups.items() for row in values]
```
(Add `layer2_map = {}` and `set50_set = set()` near the top of `snapshot_items` for the standalone path, or compute them if pg available.)

- [ ] **Step 7: Update `build()` to compute L2 + SET50 and sort**

In `build()`, after the `excluded = excluded_symbols(pg, market="TH")` line, add:
```python
        from screening import universe_layer2, load_index_membership
        layer2_map = universe_layer2(pg, [row["symbol"] for row in rows])
        set50_set = load_index_membership(pg)
```

Change the items comprehension (line ~768) from:
```python
    items = [serialize(key, row, latest.get(row["symbol"], {}), overlays.get(row["symbol"]))
             for key, values in source_groups.items() for row in values
             if row["symbol"] not in excluded]
```
to:
```python
    items = [serialize(key, row, latest.get(row["symbol"], {}), overlays.get(row["symbol"]),
                       layer2_map.get(row["symbol"]), set50_set)
             for key, values in source_groups.items() for row in values
             if row["symbol"] not in excluded]
    items = apply_projection(items)
```

Add within-stage L2 secondary sort right after `apply_projection` (before `stage_order`/`stage_counts`):
```python
    STAGE_ORDER_L2 = ["S2_uptrend", "S1_basing", "S3_distributing", "S4_down"]
    L2_PRIORITY = {"momentum_strong":0,"momentum_up":1,"neutral":2,"momentum_down":3,
                   "overbought":4,"oversold":5,None:6}
    items.sort(key=lambda i: (STAGE_ORDER_L2.index(i.get("stage")) if i.get("stage") in STAGE_ORDER_L2 else 99,
                              L2_PRIORITY.get(i.get("layer2_group"), 6),
                              -(i.get("rs") or 0)))
```

- [ ] **Step 8: Run test to verify it passes**

Run: `/root/.venv_img/bin/python -m pytest test_independence_filter.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /root/signalix && git add backend/build_dashboard.py backend/test_independence_filter.py && git commit -m "feat(dashboard): attach Layer2 + independence fields, within-stage L2 sort"
```

---

### Task 5: UI — Independence filter bar + L2 subgroup pills

**Files:**
- Modify: `backend/dashboard_template.html` (filter bar + per-stage L2 subgroup row + card small L2 text)

**Interfaces:**
- Consumes: item fields `layer2_group`, `independence{is_set50,avgTradeValue20,priceBand,passesValueFilter}` (Task 4).
- Produces: global Independence filter (SET50 toggle / value dropdown / price band) AND-combined with existing liquidity + stage filter; per-stage L2 subgroup pills filter within that stage section.

- [ ] **Step 1: Replace the `.liquidity-tools` block with an Independence filter bar**

Find (lines 128-131):
```html
    <div class="liquidity-tools">
      <button class="chip active" id="liquidOnly" data-liquidity="liquid">ซ่อน low value (&lt;฿10M/วัน)</button>
      <button class="chip" id="showLowValue" data-liquidity="all">โชว์ทั้งหมด</button>
    </div>
```
Replace with:
```html
    <div class="liquidity-tools" id="indepBar">
      <button class="chip" id="set50Only" data-indep="set50">SET50 เท่านั้น</button>
      <select id="valueFilter" class="chip" aria-label="Value filter">
        <option value="all">มูลค่าตลาด: ทั้งหมด</option>
        <option value="5">≥ ฿5M/วัน</option>
        <option value="10">≥ ฿10M/วัน</option>
        <option value="20">≥ ฿20M/วัน</option>
      </select>
      <select id="priceBand" class="chip" aria-label="Price band">
        <option value="all">ราคา: ทั้งหมด</option>
        <option value="low">ต่ำ (&lt;฿2)</option>
        <option value="mid">กลาง (฿2–10)</option>
        <option value="high">สูง (&gt;฿10)</option>
      </select>
      <button class="chip active" id="liquidOnly" data-liquidity="liquid">ซ่อน low value (&lt;฿10M/วัน)</button>
      <button class="chip" id="showLowValue" data-liquidity="all">โชว์ทั้งหมด</button>
    </div>
```

- [ ] **Step 2: Add L2 subgroup pills inside each stage section**

In `render()`, change the section template (lines ~205-208). Replace:
```javascript
    return `<section class=\"stage-section\"><div class=\"stage-head ${s.split(\"_\")[0]}\">\n      <h2>${esc(STAGE_LABEL[s])}</h2><span class=\"badge\">${list.length}</span>\n      <span class=\"desc\">${esc(STAGE_DESC[s])}</span></div>\n      <div class=\"cards\">${list.map(card).join(\"\")}</div></section>`;
```
with:
```javascript
    const L2GROUPS=["momentum_strong","momentum_up","neutral","momentum_down","overbought","oversold"];
    const counts={}; L2GROUPS.forEach(g=>counts[g]=list.filter(i=>i.layer2_group===g).length);
    const subpills=L2GROUPS.map(g=>`<button class=\"chip l2sub ${l2Filter[s]===g?"active":""}\" data-stage=\"${s}\" data-l2=\"${g}\">${g} <b>${counts[g]}</b></button>`).join("");
    return `<section class=\"stage-section\"><div class=\"stage-head ${s.split(\"_\")[0]}\">\n      <h2>${esc(STAGE_LABEL[s])}</h2><span class=\"badge\">${list.length}</span>\n      <span class=\"desc\">${esc(STAGE_DESC[s])}</span></div>\n      <div class=\"l2-bar\">${subpills}<button class=\"chip l2sub ${!l2Filter[s]?"active":""}\" data-stage=\"${s}\" data-l2=\"all\">All <b>${list.length}</b></button></div>\n      <div class=\"cards\">${list.map(card).join(\"\")}</div></section>`;
```

- [ ] **Step 3: Add L2 small text line on cards**

In `card(i)` (after the `phase-tag` span, ~line 174), add:
```javascript
      ${i.layer2_group?`<span class=\"phase-tag\" style=\"color:var(--slate)\">L2: ${esc(i.layer2_group)}</span>`:\"\"}
```

- [ ] **Step 4: Add filter state + logic in JS**

Add near the top state vars (line 165 area, where `let liquidity=...` is):
```javascript
let indep={set50:false,value:0,band:"all"}, l2Filter={};
```
Update `current()` (line 184-187) to AND-combine independence:
```javascript
function current(){
  const q=document.getElementById("search").value.trim().toLowerCase();
  return items.filter(i=>{
    if(liquidity!=="all"&&i.lowValue)return false;
    if(stageFilter!=="all"&&i.stage!==stageFilter)return false;
    if(indep.set50&&!(i.independence&&i.independence.is_set50))return false;
    if(indep.value>0&&!(i.independence&&i.independence.avgTradeValue20>=(indep.value*1e6)))return false;
    if(indep.band!=="all"&&!(i.independence&&i.independence.priceBand===indep.band))return false;
    const lf=l2Filter[stageFilter];
    if(lf&&lf!=="all"&&i.layer2_group!==lf)return false;
    if(q&&!`${i.symbol} ${i.stage} ${i.phase} ${i.action} ${i.actionReason}`.toLowerCase().includes(q))return false;
    return true;
  });
}
```
Add event listeners (inside the existing `document.addEventListener("click", ...)` block, augment the handler):
```javascript
  const set50=e.target.closest("#set50Only"); if(set50){indep.set50=!indep.set50;set50.classList.toggle("active",indep.set50);render();}
  const vf=e.target.closest("#valueFilter"); if(vf){indep.value=parseFloat(vf.value)||0;render();}
  const pb=e.target.closest("#priceBand"); if(pb){indep.band=pb.value;render();}
  const l2=e.target.closest(".l2sub"); if(l2){const st=l2.dataset.stage,g=l2.dataset.l2; l2Filter[st]=(l2Filter[st]===g?undefined:g); render();}
```
Add CSS for `.l2-bar` (after `.stage-head .desc` line ~61):
```css
.l2-bar{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px}
.l2-bar .chip{padding:5px 10px;font-size:11px}
.l2-bar .chip.active{background:var(--blue);color:#06101f;border-color:var(--blue)}
```

- [ ] **Step 5: Verify template still has mandatory Modal CSS**

Confirm `.modal-bg{display:none;...}` and `.modal-bg.open{display:flex}` remain (lines 98-100). No change needed; just don't delete them.

- [ ] **Step 6: Commit**

```bash
cd /root/signalix && git add backend/dashboard_template.html && git commit -m "feat(ui): Independence filter bar + L2 subgroup drill-down pills"
```

---

### Task 6: Deploy, scan, and verify

**Files:** (none new; verification only)

**Interfaces:** Uses existing deploy + scan flow.

- [ ] **Step 1: Recreate backend to pick up code**

Run:
```bash
cd /root/signalix && docker compose up -d --force-recreate backend
```
Wait for `Container signalix_backend Started`.

- [ ] **Step 2: Trigger a scan**

Run:
```bash
curl -s -m 800 -X POST "http://127.0.0.1:8000/scan?push=false&min_conditions=0" -o /tmp/scan_resp.json -w "HTTP %{http_code}\n"
```
Expected: `HTTP 200`.

- [ ] **Step 3: Verify snapshot carries Layer 2 + independence fields**

Run with `/root/.venv_img/bin/python`:
```python
import json
d=json.load(open("/root/signalix/backend/dashboard_snapshot.json"))
items=d["items"]
assert 800 <= len(items) <= 939, len(items)
sample=next(i for i in items if i.get("layer2_group"))
print("layer2_group sample:", sample["symbol"], sample["layer2_group"], sample["layer2_signals"])
print("independence sample:", sample["independence"])
assert "independence" in sample and "layer3_qualifiers" in sample
print("OK: L2 + independence fields present; excluded still absent (len=%d)" % len(items))
```

- [ ] **Step 4: Verify SET50 membership seeded**

Run:
```bash
cd /root/signalix/backend && /root/.venv_img/bin/python -c "import psycopg2;pg=psycopg2.connect(host='127.0.0.1',port=5432,user='signalix',password='signalix_pass',dbname='signalix');c=pg.cursor();c.execute('SELECT COUNT(*) FROM index_membership WHERE is_set50=TRUE');print('SET50 rows:',c.fetchone()[0])"
```
Expected: >= 40.

- [ ] **Step 5: Verify chart endpoint still works**

Run:
```bash
curl -s -m 10 "http://127.0.0.1:8000/chart/AOT?timeframe=1D&limit=63" -o /dev/null -w "%{http_code}\n"
```
Expected: `200`.

- [ ] **Step 6: Browser check (final gate)**

Open `http://127.0.0.1:3001/dashboard.html`:
- Click a stage pill (e.g. Stage 2) → section shows.
- Inside the section, L2 subgroup pills (momentum_strong / momentum_up / ...) appear with counts; clicking one filters that stage's cards.
- Toggle "SET50 เท่านั้น" → only SET50 cards remain across sections.
- Value / price-band dropdowns filter correctly.
- Card modal still opens with candlestick chart (Modal CSS intact).

- [ ] **Step 7: Commit verification note (no code change)**

```bash
cd /root/signalix && git commit --allow-empty -m "verify: Layer 2 + independence filter deployed and confirmed on dashboard"
```
