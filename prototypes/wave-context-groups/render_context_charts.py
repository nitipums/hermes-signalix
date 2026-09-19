#!/usr/bin/env python3
"""Render a dependency-free Daily price/context replay dashboard under /tmp.

The real-data path reuses replay_context_groups for its fixed scope, prefix-only
classification, exploratory map_context, and replay_lab's read-only connection
and guarded SELECT loader.  It never writes to the database.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPLAY_CONTEXT = HERE / "replay_context_groups.py"
DEFAULT_OUTPUT = "/tmp/wave_context_charts.html"
STABLE_RUN_SESSIONS = 2


def _load_context_module():
    spec = importlib.util.spec_from_file_location("signalix_context_replay", REPLAY_CONTEXT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load context replay from {REPLAY_CONTEXT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tmp_path(raw: str) -> Path:
    path = Path(raw).resolve()
    try:
        path.relative_to(Path("/tmp").resolve())
    except ValueError as exc:
        raise ValueError(f"output must be under /tmp: {path}") from exc
    return path


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _display_context(value: Any) -> str:
    marker = str(value or "UNKNOWN")
    return "UNKNOWN" if marker in {"NONE", "NONE/UNKNOWN"} else marker


def _price_rows(frame, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        date_value = row.Date.date() if hasattr(row.Date, "date") else row.Date
        if not start <= date_value <= end:
            continue
        close, high, low = _finite(row.Close), _finite(row.High), _finite(row.Low)
        if close is None:
            continue
        rows.append({
            "date": date_value.isoformat(),
            "close": close,
            "high": high if high is not None else close,
            "low": low if low is not None else close,
        })
    return rows


def _run_records(replay_rows: list[dict[str, Any]], prices: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return stable chart markers and every raw context transition for inspection."""
    if not replay_rows:
        return [], []
    runs: list[tuple[int, int]] = []
    start = 0
    for index in range(1, len(replay_rows)):
        left = (_display_context(replay_rows[index - 1]["context_marker"]), replay_rows[index - 1]["secondary_marker"])
        right = (_display_context(replay_rows[index]["context_marker"]), replay_rows[index]["secondary_marker"])
        if left != right:
            runs.append((start, index))
            start = index
    runs.append((start, len(replay_rows)))

    markers: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    for run_index, (left, right) in enumerate(runs):
        row = replay_rows[left]
        price = prices.get(row["as_of"])
        previous = replay_rows[left - 1] if left else None
        record = {
            "date": row["as_of"],
            "price": price["close"] if price else None,
            "previous": _display_context(previous["context_marker"]) if previous else "START",
            "new": _display_context(row["context_marker"]),
            "structural_state": row["structural_state"],
            "secondary": row["secondary_marker"],
            "confidence": row.get("confidence") or "UNKNOWN",
            "run_sessions": right - left,
            "chart_marker": run_index == 0 or right - left >= STABLE_RUN_SESSIONS,
        }
        if run_index:
            transitions.append(record)
        if record["chart_marker"] and price is not None:
            markers.append(record)
    return markers, transitions


def _build_symbol(symbol: str, frame, replay_rows: list[dict[str, Any]], start: dt.date, end: dt.date) -> dict[str, Any]:
    prices = _price_rows(frame, start, end)
    price_by_date = {row["date"]: row for row in prices}
    replay_dates = {row["as_of"] for row in replay_rows}
    price_dates = set(price_by_date)
    if replay_dates != price_dates:
        raise AssertionError(f"{symbol}: replay/price date mismatch ({len(replay_dates)} vs {len(price_dates)})")
    markers, transitions = _run_records(replay_rows, price_by_date)
    for marker in markers:
        exact = price_by_date[marker["date"]]["close"]
        if marker["price"] != exact:
            raise AssertionError(f"{symbol}: marker price is not exact Daily close on {marker['date']}")
    counts = Counter(_display_context(row["context_marker"]) for row in replay_rows)
    return {
        "symbol": symbol,
        "prices": prices,
        "markers": markers,
        "transitions": transitions,
        "context_counts": dict(sorted(counts.items())),
        "row_count": len(replay_rows),
    }


def build_real_data(context) -> tuple[dict[str, Any], dict[str, Any]]:
    helpers = context._load_replay_helpers()
    conn = helpers._get_conn()
    try:
        eligible_symbols, universe = helpers.resolve_universe(conn, "marginable_long")
        eligible = set(eligible_symbols)
        stocks = []
        for symbol in context.SYMBOLS:
            frame, _latest = context._load_bounded_daily(conn, helpers, symbol, context.WINDOW_END)
            rows = context.replay_symbol(symbol, frame, context.WINDOW_START, context.WINDOW_END)
            stock = _build_symbol(symbol, frame, rows, context.WINDOW_START, context.WINDOW_END)
            stock["marginable_long_eligible"] = symbol in eligible
            stocks.append(stock)
    finally:
        conn.close()
    return {"stocks": stocks}, universe


def build_synthetic_data(context) -> tuple[dict[str, Any], dict[str, Any]]:
    """Small deterministic fixture that exercises mapping, runs, and exact prices."""
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"synthetic smoke requires pandas: {exc}") from exc
    dates = pd.date_range("2026-08-17", periods=10, freq="B")
    close = [10, 10.4, 10.8, 10.6, 10.5, 10.9, 11.2, 11.5, 11.4, 11.8]
    frame = pd.DataFrame({"Date": dates, "Open": close, "High": [v + .2 for v in close], "Low": [v - .2 for v in close], "Close": close, "Volume": [100] * 10})
    states = ["WAVE_1_ADVANCE"] * 3 + ["WAVE_2_FORMING"] * 2 + ["EARLY_WAVE_3"] * 2 + ["WAVE_3_CONTINUATION"] * 3
    rows = []
    for date_value, state in zip(dates, states):
        wave = {"state": state, "evidence": {}}
        mapped = context.map_context(wave)
        rows.append({
            "as_of": date_value.date().isoformat(), "structural_state": state,
            "confidence": "MEDIUM", "context_marker": mapped["context_marker"],
            "secondary_marker": mapped["secondary_marker"],
        })
    stock = _build_symbol("SYNTH", frame, rows, dates[0].date(), dates[-1].date())
    stock["marginable_long_eligible"] = False
    assert len(stock["markers"]) == 4 and len(stock["transitions"]) == 3
    return {"stocks": [stock]}, {"universe_filter": "synthetic"}


def render_html(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    title = html.escape("Signalix · Daily Wave context replay")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{--bg:#091018;--panel:#111b26;--line:#263647;--ink:#eaf0f6;--muted:#91a0af;--grid:#253340}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,sans-serif}}button{{font:inherit}}
.shell{{max-width:1280px;margin:auto;padding:18px}}h1{{font-size:clamp(24px,4vw,38px);margin:4px 0}}h2{{font-size:18px;margin:0 0 10px}}.muted{{color:var(--muted)}}
.banner,.card{{border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:14px;margin-bottom:12px}}.banner{{border-color:#665225;background:#211c11;color:#f5d48d}}
.stock-nav{{display:flex;gap:7px;flex-wrap:wrap}}.stock-nav button{{color:var(--ink);background:#172331;border:1px solid var(--line);border-radius:8px;padding:7px 11px;cursor:pointer}}.stock-nav button.active{{border-color:#73b6ff;background:#20364c}}
.summary{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}}.metric{{background:#0c151e;border:1px solid var(--line);padding:10px;border-radius:9px;overflow-wrap:anywhere}}.metric strong{{display:block;font-size:20px}}
.chart-wrap{{width:100%;overflow:hidden}}svg{{display:block;width:100%;height:auto;min-height:270px}}.legend{{display:flex;flex-wrap:wrap;gap:7px 12px;margin:8px 0}}.key{{white-space:nowrap;font-size:12px}}.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:-1px}}
.table-wrap{{width:100%;overflow-x:auto}}table{{width:100%;border-collapse:collapse;min-width:720px}}th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);font-size:12px}}th{{color:#b8c5d1}}.pill{{font:11px ui-monospace,monospace;background:#192737;border-radius:999px;padding:2px 6px}}.empty{{padding:18px;color:var(--muted)}}
@media(max-width:600px){{.shell{{padding:10px}}.summary{{grid-template-columns:1fr 1fr}}.card{{padding:10px}}svg{{min-height:220px}}.table-wrap{{overflow:visible}}table{{min-width:0}}thead{{display:none}}tbody,tr,td{{display:block}}tr{{border-bottom:1px solid var(--line);padding:7px 0}}td{{border:0;padding:2px 0;overflow-wrap:anywhere}}td:before{{content:attr(data-label) ': ';color:var(--muted)}}}}
</style></head><body><main class="shell">
<div class="banner"><strong>EXPLORATORY · READ-ONLY DAILY REPLAY</strong> — machine-generated context for chart review, not objective Elliott truth or an order.</div>
<header><div class="muted">SIGNALIX / 2025-08-28..2026-08-28 INCLUSIVE / NO LOOKAHEAD</div><h1>Daily price + Wave context</h1><p class="muted">Every point is placed on its exact as-of Daily close. Light bars show the Daily high-low range.</p></header>
<section class="card"><div class="stock-nav" id="stockNav"></div></section>
<section class="card"><h2 id="stockTitle"></h2><div class="summary" id="summary"></div></section>
<section class="card"><div class="chart-wrap" id="chart"></div><div class="legend" id="legend"></div></section>
<section class="card"><h2>All context transitions</h2><p class="muted">Chart labels show first dates of runs stable for at least {STABLE_RUN_SESSIONS} sessions (and the initial run). This table preserves every transition, including short runs.</p><div class="table-wrap" id="details"></div></section>
<section class="card"><strong>Filter boundary:</strong> only canonical <span class="pill">EARLY_WAVE_3</span> and <span class="pill">WAVE_3_CONTINUATION</span> are filter-eligible. Wave 1/5 are visible context; Wave 2/4 are non-filter context; <span class="pill">WAVE_3_EXTENDED</span> is secondary only.</section>
</main><script>const DATA={data};
const COLORS={{WAVE_1_RISING:'#39d98a',WAVE_2_PULLBACK:'#f4d35e',WAVE_3_EARLY:'#ff5b5b',WAVE_3_CONTINUING:'#a66cff',WAVE_3_EXTENDED:'#ff9f43',WAVE_4_SIDEWAYS:'#55a8ff',WAVE_4_CORRECTION:'#1769aa',WAVE_5_RISING:'#ff73b9',UNKNOWN:'#8793a1'}};
const SHORT={{WAVE_1_RISING:'W1',WAVE_2_PULLBACK:'W2',WAVE_3_EARLY:'W3E',WAVE_3_CONTINUING:'W3C',WAVE_3_EXTENDED:'W3X',WAVE_4_SIDEWAYS:'W4S',WAVE_4_CORRECTION:'W4C',WAVE_5_RISING:'W5',UNKNOWN:'?'}};
const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
let current=DATA.stocks[0]?.symbol;const stock=()=>DATA.stocks.find(x=>x.symbol===current);
function chart(s){{if(!s.prices.length)return '<div class="empty">No Daily prices in bounded window.</div>';const W=1160,H=406,p={{l:55,r:78,t:24,b:58}};const vals=s.prices.flatMap(x=>[x.low,x.high]);let lo=Math.min(...vals),hi=Math.max(...vals);const pad=(hi-lo||1)*.07;lo-=pad;hi+=pad;const x=i=>p.l+i*(W-p.l-p.r)/Math.max(1,s.prices.length-1),y=v=>p.t+(hi-v)*(H-p.t-p.b)/(hi-lo);const idx=Object.fromEntries(s.prices.map((v,i)=>[v.date,i]));let z='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc(s.symbol)+' Daily close with Wave context markers">';for(let i=0;i<5;i++){{const v=lo+(hi-lo)*i/4,yy=y(v);z+='<line x1="'+p.l+'" x2="'+(W-p.r)+'" y1="'+yy+'" y2="'+yy+'" stroke="#253340"/><text x="4" y="'+(yy+4)+'" fill="#91a0af" font-size="11">'+v.toFixed(2)+'</text>'}}z+=s.prices.map((d,i)=>'<line x1="'+x(i)+'" x2="'+x(i)+'" y1="'+y(d.high)+'" y2="'+y(d.low)+'" stroke="#52677a" stroke-opacity=".35"/>').join('');z+='<polyline fill="none" stroke="#dce9f5" stroke-width="2" points="'+s.prices.map((d,i)=>x(i)+','+y(d.close)).join(' ')+'"/>';s.markers.forEach((m,j)=>{{const xx=x(idx[m.date]),yy=y(m.price),extended=m.secondary==='WAVE_3_EXTENDED',color=extended?COLORS.WAVE_3_EXTENDED:COLORS[m.new]||COLORS.UNKNOWN,dy=j%3===0?-12:j%3===1?18:-25,labelY=Math.max(12,Math.min(H-12,yy+dy));z+='<g><title>'+esc(m.date+' · '+m.price.toFixed(2)+' · '+m.previous+' → '+m.new+' · '+m.secondary+' · '+m.confidence)+'</title><circle cx="'+xx+'" cy="'+yy+'" r="'+(extended?7:5)+'" fill="'+(extended?'#091018':color)+'" stroke="'+color+'" stroke-width="'+(extended?3:2)+'"/><text x="'+xx+'" y="'+labelY+'" text-anchor="middle" fill="'+color+'" font-size="10" font-weight="700">'+esc(extended?'W3X':SHORT[m.new])+'</text></g>'}});[0,Math.floor((s.prices.length-1)/2),s.prices.length-1].forEach(i=>z+='<text x="'+x(i)+'" y="'+(H-10)+'" text-anchor="middle" fill="#91a0af" font-size="11">'+s.prices[i].date+'</text>');return z+'</svg>'}}
function render(){{const s=stock();document.querySelectorAll('[data-stock]').forEach(b=>b.classList.toggle('active',b.dataset.stock===current));document.getElementById('stockTitle').textContent=s.symbol+' · Daily replay';document.getElementById('summary').innerHTML='<div class="metric"><strong>'+s.row_count+'</strong>Daily rows</div><div class="metric"><strong>'+s.markers.length+'</strong>stable-run markers</div><div class="metric"><strong>'+s.transitions.length+'</strong>all transitions</div><div class="metric"><strong>'+(s.marginable_long_eligible?'YES':'NO')+'</strong>marginable_long</div>';document.getElementById('chart').innerHTML=chart(s);document.getElementById('legend').innerHTML=Object.entries(COLORS).map(([k,c])=>'<span class="key"><i class="dot" style="background:'+c+'"></i>'+k+'</span>').join('');document.getElementById('details').innerHTML=s.transitions.length?'<table><thead><tr><th>Date</th><th>Daily close</th><th>Previous → new context</th><th>Structural state</th><th>Secondary</th><th>Confidence</th><th>Run</th></tr></thead><tbody>'+s.transitions.map(m=>'<tr><td data-label="Date">'+m.date+'</td><td data-label="Daily close">'+m.price.toFixed(2)+'</td><td data-label="Context">'+esc(m.previous)+' → '+esc(m.new)+'</td><td data-label="State">'+esc(m.structural_state)+'</td><td data-label="Secondary">'+esc(m.secondary)+'</td><td data-label="Confidence">'+esc(m.confidence)+'</td><td data-label="Run">'+m.run_sessions+' session'+(m.run_sessions===1?'':'s')+(m.chart_marker?' · charted':' · table only')+'</td></tr>').join('')+'</tbody></table>':'<div class="empty">No context transitions in this window.</div>'}}
document.getElementById('stockNav').innerHTML=DATA.stocks.map(s=>'<button data-stock="'+s.symbol+'">'+s.symbol+'</button>').join('');document.getElementById('stockNav').addEventListener('click',e=>{{const b=e.target.closest('[data-stock]');if(b){{current=b.dataset.stock;render()}}}});render();</script></body></html>'''


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Render standalone Daily Wave-context charts under /tmp")
    parser.add_argument("--out", default=DEFAULT_OUTPUT, help="standalone HTML output under /tmp")
    parser.add_argument("--synthetic-smoke", action="store_true", help="render deterministic fixture without DB access")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        output = _tmp_path(args.out)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    context = _load_context_module()
    if context.ENGINE_IMPORT_ERROR is not None:
        print(f"ERROR importing engine dependencies: {context.ENGINE_IMPORT_ERROR}", file=sys.stderr)
        return 3
    data, universe = build_synthetic_data(context) if args.synthetic_smoke else build_real_data(context)
    payload = {
        **data,
        "window": {"from": str(context.WINDOW_START), "to": str(context.WINDOW_END), "inclusive": True},
        "no_lookahead": True,
        "stable_run_sessions": STABLE_RUN_SESSIONS,
        "universe": universe,
    }
    output.write_text(render_html(payload), encoding="utf-8")
    rows = sum(stock["row_count"] for stock in data["stocks"])
    markers = sum(len(stock["markers"]) for stock in data["stocks"])
    transitions = sum(len(stock["transitions"]) for stock in data["stocks"])
    print(f"wrote {output} stocks={len(data['stocks'])} rows={rows} markers={markers} transitions={transitions}")
    if args.synthetic_smoke:
        print("synthetic smoke: PASS (exact date/close marker invariant and stable-run collapse)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
