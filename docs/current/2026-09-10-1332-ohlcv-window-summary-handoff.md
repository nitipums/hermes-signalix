# Signalix OHLCV Window Summary — Current Handoff

> **STATUS: SUPERSEDED** · Historical evidence handoff; current exact chart semantics are in `../../docs/current/2026-09-13-main-trend-calculation-contract.md` and `../../vault/Architecture.md`.
> **As of:** 2026-09-10 13:32 ICT (`Asia/Bangkok`)
> **Authority:** `../superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md`
> **Product boundary:** machine-generated candidate/evidence for Arm review; not truth, automatic BUY, or order execution.

## Purpose

Record the implemented and served OHLCV window-summary contract so the next Signalix session can verify the same source, API, and UI behavior without relying on chat history.

## Current contract

Canonical chart endpoint:

```text
GET /api/chart-db/{symbol}?timeframe=1D|1W|60M|1M
```

Policy:

```text
technical-indicators-v1
```

The canonical `indicators.latest.window_summary` has rows for:

```text
5, 10, 20, 60, 120, 240, 260 candles
```

Each row contains:

```text
open
high
low
close
volume_total
volume_average
change_pct
range_pct
ma
availability
```

Window definitions are deterministic:

- `open`: first candle Open in the trailing window;
- `high`: maximum High in the trailing window;
- `low`: minimum Low in the trailing window;
- `close`: latest candle Close;
- `volume_total`: sum of source candle volume;
- `volume_average`: arithmetic average of source candle volume;
- `change_pct`: `(Close - Open) / Open * 100`;
- `range_pct`: `(High - Low) / Low * 100`;
- `ma`: SMA for 5/10/20/60/120/240 only; MA260 is deliberately not defined.

`260 candles` means a 52-week trading range only for Daily data. Other timeframes label it `260 candles`.

The UI uses one table:

```text
Candles | Open | High | Low | Close | Avg Vol | MA
```

Rows 240 and 260 both contain OHLCV summaries. Row 260 has no MA; it uses the 260-candle range. Total Volume, Change %, and Range % appear as compact row detail. Large volumes are rendered with compact units such as `202.39M` and `1.01B`; the API retains exact numeric values.

## Timeline

- `2026-09-10 13:32 ICT` — Owner approved adding OHLC, Volume, Avg Volume, Change %, Range %, availability, as-of, and provenance to every window row.
- `2026-09-10` — Codex Sol implemented the deterministic window-summary engine, canonical API integration, one-table UI, tests, and focused-spec sync.
- `2026-09-10` — Corrected the distinct period sets: MA `5/10/20/60/120/240`; OHLCV window `5/10/20/60/120/240/260`.
- `2026-09-10` — Corrected chart source retrieval to provide at least 260 candles so the 52-week row can become available.
- `2026-09-10` — Added compact volume formatting for 390px readability.

## Evidence

### Source and tests — PASS

Release commits:

```text
49972b2  deterministic technical indicators
f997f58  rolling candle High/Low
9864484  MA240 versus 52-week 260 distinction
cdb7543  fetch at least 260 chart candles
 efbaed7  OHLCV window summaries
44fec0e  compact volume labels on mobile
```

Relevant checks passed:

```text
pytest -q backend/test_technical_indicators.py \
  backend/test_chart_provisional.py \
  backend/test_mvp_chart_ordering.py \
  backend/test_mvp_frontend_contract.py \
  -k 'not setup_candidate_layout_has_no_horizontal_overflow_at_390px'

python -m compileall -q backend
node --check backend/frontend/app.js
git diff --check
```

Codex Sol evidence:

```text
/tmp/codex_ohlcv_window_sol_transcript.log
/tmp/codex_ohlcv_window_sol_last.md
/tmp/codex_volume_ui_sol_transcript.log
/tmp/codex_volume_ui_sol_last.md
```

The browser-only Playwright test remains environment-limited by Chromium sandbox restrictions; the real `agent-browser` journey below passed.

### Served API — PASS

Read-back from:

```text
/api/chart-db/IRPC?timeframe=1D
```

Runtime returned:

```text
candles: 260
MA keys: 5, 10, 20, 60, 120, 240
OHLCV window keys: 5, 10, 20, 60, 120, 240, 260
260 availability: AVAILABLE
readiness: status=ok, db=up, redis=up
```

Example served Daily rows:

```text
5   → Open 2.84 · High 3.22 · Low 2.76 · Close 3.18 · Avg Vol 202.39M · MA 3.07
10  → Open 2.50 · High 3.22 · Low 2.48 · Close 3.18 · Avg Vol 193.92M · MA 2.89
20  → Open 2.54 · High 3.22 · Low 2.36 · Close 3.18 · Avg Vol 143.97M · MA 2.68
60  → Open 1.75 · High 3.22 · Low 1.63 · Close 3.18 · Avg Vol 155.07M · MA 2.22
120 → Open 1.15 · High 3.22 · Low 1.14 · Close 3.18 · Avg Vol 188.53M · MA 2.01
240 → Open 1.28 · High 3.22 · Low 0.96 · Close 3.18 · Avg Vol 123.09M · MA 1.57
260 → Open 0.94 · High 3.22 · Low 0.92 · Close 3.18 · Avg Vol 122.03M · MA —
```

### Rendered UI — PASS

Real `agent-browser` journey at 390px opened the IRPC drawer and read back the table rows. Headers were:

```text
Candles | Open | High | Low | Close | Avg Vol | MA
```

All seven rows were present. Compact volume values did not wrap. Metrics:

```text
innerWidth: 390
clientWidth: 390
scrollWidth: 390
bodyScrollWidth: 390
```

Screenshot:

```text
/tmp/signalix_volume_final_390.png
```

## Runtime and safety boundary

- `signalix_backend`, `signalix_dashboard`, PostgreSQL, and Redis were healthy after the final dashboard recreate.
- No migration, production database write, alert enablement, broker execution, or auto-trading was performed.
- Existing owner-owned dirty files in the stable worktree were not staged or overwritten.
- Wave remains machine-generated evidence; Arm reviews the chart and makes the final decision.

## Next resume boundary

Start from this handoff and the authority spec. For future changes, keep:

```text
MA_PERIODS = 5/10/20/60/120/240
WINDOW_PERIODS = 5/10/20/60/120/240/260
```

Do not replace MA240 with MA260. Treat missing history as `NOT_VERIFIED`, not zero or an inferred value.
