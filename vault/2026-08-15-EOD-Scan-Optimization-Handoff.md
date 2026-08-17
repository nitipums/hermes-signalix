# Signalix EOD Scan & Dashboard Handoff

- **Date:** 2026-08-15
- **Owner / final gate:** Bee (lite)
- **Project:** Signalix
- **Related:** [[Execution-Pipeline]] · [[2026-08-13-Intraday-Dashboard-Handoff]]

## Current outcome

The EOD path is now optimized while preserving broad coverage:

```text
Settrade full dry-run: 860 symbols, 860 rows, 0 failed, 63.85s
Production Settrade workers: SETTRADE_DAILY_WORKERS=30
EOD scan universe: 718 Thai ORD symbols
Scan runtime: ~46.5s for 718 symbols
Daily observations: 718
Daily analysis snapshots: 718
Automated tests: 71/71 passed
```

## EOD scan eligibility

Keep these criteria:

1. Thai ordinary shares (`market=TH`, `instrument_type=ORD`).
2. At least **260 Daily bars**. This is required for valid MA200/52-week/RS calculations and must not be removed; otherwise new listings would be incorrectly treated as fully qualified.
3. Latest bar not stale by more than 10 calendar days.
4. Temporary minimum close price: `>= ฿0.60`.

Removed from EOD scan eligibility:

- Latest trade value / liquidity floor. Low-turnover names must remain available for EOD research.

Measured counts at the checkpoint:

```text
260 bars + fresh + old ฿15M trade-value filter: 184
260 bars + fresh + price >= ฿0.60: 718
260 bars + fresh + no price floor: 866
Recent symbols with <260 bars: 24
```

The dashboard may still hide names below ฿10M average daily value by default as a **presentation filter**. `Show all values` reveals them; they remain in scan results, DB observations, and snapshots.

## Fetch and scan changes

- Settrade remains authoritative for new EOD data; native Thai zip is historical/backfill only.
- Bounded worker benchmark in the real updater:
  - 3: 45.44s / 100
  - 5: 32.96s / 100
  - 10: 25.31s / 100
  - 20: 20.88s / 100
  - 30: 20.41s / 100
  - 50: 20.90s / 100
- No failures or rate-limit errors were observed. Production is set to 30, not 50.
- Scanner default is `SIGNALIX_SCAN_LOOKBACK=360`. A 600-vs-360 parity test matched symbol set, groups, and near-miss output for the test cohort; 360 reduced scan time by about 25%.
- `daily_analysis_snapshots` stores typed daily MA/RSI/high-low/volume/RS fields plus JSON metrics.
- `daily_symbol_ath_cache` initializes from history once and updates only when the latest high exceeds cached ATH.

## Dashboard regression and fix

### Root cause

During the 718-symbol expansion, `build_dashboard.py` intentionally set `latest = {}` to avoid history fan-out. This disabled all DB enrichment during serialization, so cards showed `0`/`—` for volume, turnover, MA, 52W, ATH, and MACD even though `/chart` and PostgreSQL were complete.

### Fix

- Restore dashboard enrichment through one batched `snapshots()` call for the full universe.
- Replace per-symbol lateral history lookup with set-based window queries.
- Scope price queries to `market='TH'`.
- Dashboard build remains bounded: approximately 30.8s for 718 symbols.

### Live rendered verification

SRS was opened in the public rendered dashboard after deployment and showed:

```text
Close 2.40; Change +10.09%; Volume 863.3K; Trade value ฿2.07M
52W high/low 3.06 / 1.41
ATH high/low 22.40 / 1.41
MACD 0.106
MA10 2.06; MA20 1.96; MA50 1.88; MA200 1.80
Risk to stop 7.1%; Fib target 161 3.07 · 3.9R
```

`Company profile pending` and `Sector pending` are separate slow metadata fields; they are not missing technical data.

## Operational deployment

After backend source changes:

```bash
cd /root/signalix
docker compose up -d --force-recreate backend
curl -fsS http://127.0.0.1:8000/health
curl -fsS -X POST 'http://127.0.0.1:8000/scan?push=false'
```

Verify both served HTML/API and rendered browser UI. API/HTML alone is not sufficient evidence for mobile/UI readiness.

## Memory layers

For project-manager handoffs, durable project decisions are recorded in all applicable layers:

- Level 1: raw session/state is retained automatically by Hermes.
- Level 3: queryable project facts are stored in Hermes `fact_store`.
- Level 4: this Obsidian vault note is the human/team handoff source.

## Open decisions / next work

1. Decide later whether the temporary ฿0.60 price floor should also be removed.
2. Decide whether dashboard default should show all low-value cards or keep the presentation toggle.
3. Incremental indicator state can be considered later; current daily snapshots provide reproducible historical analysis without requiring unsafe state shortcuts.
