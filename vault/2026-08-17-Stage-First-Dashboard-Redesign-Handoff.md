# Signalix Stage-First Dashboard Redesign — Handoff 2026-08-17

> **STATUS: HISTORICAL** · Design/migration evidence. Current UI contract must be verified from source, served artifact, and browser.

**Owner:** Arm (Nitipum.s) · **Executor:** Bee (lite)
**Date:** 2026-08-17
**Status:** DONE — verified on prod (universe 1,143, modal + candlestick chart working)

## Goal
Unify the 3 inconsistent label systems (legacy 5-group, stage, phase) into a single
**Stage-first** classifier (Minervini/Weinstein S1–S4) as the primary UI axis, with
phase as sub-state and `trade_readiness.status` as a hint. Expand the scan universe to
**ALL ORD symbols** (no price/volume/stale filtering). Redesign the dashboard UI to be
stage-first, with clickable cards → detail modal → on-demand candlestick chart.

## What changed

### Screening pipeline (`backend/screening.py`)
- `_active_scan_symbols`: removed `MAX(date) >= cutoff` filter and `min_price` /
  `min_today_trade_value` params. Now returns **every ORD** in `price_data` (1,238 rows;
  1,143 have enough bars to scan). No stale exclusion.
- `scan_universe`: threshold for "too few bars" lowered from 200 → **20** (don't skip
  thin symbols, just don't classify them).
- `load_symbol_intraday(symbol, interval='60m', lookback=400)`: NEW. Loads 60m bars when
  daily < 200. **Gotcha:** `intraday_price_data` has NO `market` column — do not filter on it.
- Loop in `scan_universe`: if daily bars < 200, load intraday 60m instead, set
  `trend_source='intraday_60m'` (marks new listings).
- `group_scan_results`: unchanged behavior (keeps all scanned symbols).
- `RS_LOOKBACK=60` guarded with `min(RS_LOOKBACK, len(c))` — symbols with <60 bars no longer crash.

### Stage classifier (`backend/stage_classifier.py`)
- MA-stacking (MA50 > MA150 > MA200 + slopes) is the stage signal. **Volume gate removed**
  from breakout phase (user decision). Missing MA → returns `S1_basing` (no crash).

### Projection (`backend/reconciled_projection.py`)
- **CRITICAL FIX:** `apply_projection` previously hard-coded `if not a: continue` (drop
  symbols outside taxonomy) + `assert len(out) == 718`. Both removed — every scanned
  symbol is preserved (neutral default). This was the root cause of universe being stuck at 718.

### Dashboard build (`backend/build_dashboard.py`)
- `build(scanned=None)`: now accepts `scanned` list **directly** from `/scan` —
  `build_dashboard.build(scanned=scanned)`. No longer re-reads `scan_results.json`
  (API-process file reads could return a stale write → silent old-universe bug).
- `snapshots()` now keeps raw OHLC `history` (for the chart API) but does **NOT** embed it
  in card items (keeps HTML light).
- Template loader: `dashboard.html` is rendered from `dashboard_template.html` via string
  replace of `__ITEMS__` / `__STAGE_META__` (replaced the giant f-string).

### Dashboard UI (`backend/dashboard_template.html`)
- Stage-first layout: hero + stage-summary pills (clickable filter) + sections per S1–S4.
- Card: stage badge (color-coded), phase tag, price/vol/value strip, quality strip
  (RS/RSI/MACD), action line, breakout/volume-surge evidence.
- **Card click → `openDetail(i)`** opens a modal. **Modal CSS is mandatory**
  (`.modal-bg{display:none}` + `.modal-bg.open{display:flex}` + `.modal` box) — without it
  the modal "opens" but shows nothing.
- **Chart is on-demand**: on modal open, `fetch(/chart/{symbol}?timeframe=…&limit=…)` then
  draw candlesticks on canvas. Timeframes: `60M`=120(15d), `1D`=63(3M), `1W`=52(1Y),
  `1M`=500(all). Green body if close>=open, red otherwise.

### API (`backend/app.py`)
- `/scan` calls `build_dashboard.build(scanned=scanned)`.
- `/chart/{symbol}` (already existed) returns OHLC bars for 1D/1W/60M/1M — reused for the modal.

## Verification (final gate)
- `pytest test_stage_classifier.py test_reconciled_projection.py` → 19 passed.
- `curl -X POST /scan?push=false&min_conditions=0` → HTTP 200, `dashboard_snapshot.json`
  `items` = **1143**.
- `curl /chart/AOT?timeframe=1D&limit=63` → 200.
- Browser: `http://127.0.0.1:3001/dashboard.html` — click card → modal with candlestick;
  stage pills filter.

## Rebuild flow (NO GIT)
Signalix backend has **no git**. Edit on host (`/root/signalix/backend`); container mounts
`./backend:/app` so edits are live, but uvicorn must reload:
```
cd /root/signalix && docker compose up -d --force-recreate backend
curl -s -m 800 -X POST "http://127.0.0.1:8000/scan?push=false&min_conditions=0"
```
Plain `docker compose restart` does NOT pick up code changes.

## Gotchas for next session
- `terminal` tool is BLOCKED inside the gateway process (SIGTERM propagates). Use
  `execute_code` with `hermes_tools.terminal` for PG/Python diagnostics.
- Heavy integration pytest (scan-dependent) times out at 200s in execute_code — run only
  the fast unit tests for regression.
- Never bake 252 OHLC bars into every card item (1,143 symbols → 6.8 MB slow HTML).

## Files
`screening.py`, `stage_classifier.py`, `reconciled_projection.py`, `build_dashboard.py`,
`dashboard_template.html`, `app.py`. Skill: `signalix-stage-first-dashboard` (lite profile).
