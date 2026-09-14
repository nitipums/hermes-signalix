# 2026-08-21 — Intraday Feed Availability / 11 Symbols + COLOR

## Status

Implemented and verified in production. This note is the durable contract for symbols that have Daily EOD data but no usable Settrade 60m intraday bars.

## Policy

- `COLOR` remains excluded at the instrument-master level:
  - `symbol_master.status = 'excluded'`
  - reason: `Owner override: Settrade Symbol not found [COLOR]`
  - excluded from Daily scan, dashboard, and intraday universe
  - historical rows are retained
  - official Settrade master sync may reactivate it if it reappears
- The 11 symbols below are **not** excluded from Signalix/Daily:
  `CIMBT`, `CV`, `GLAND`, `KWI`, `LRH`, `NFC`, `PICO`, `ROH`, `TR`, `TSR`, `TTCL`
- They are excluded only from the active 60m fetch while the feed is unavailable.

## Feed-status contract

New PostgreSQL table: `intraday_feed_status`.

Key fields:

- `symbol`, `feed` (`settrade_intraday_60m`)
- `status`: `available`, `retry`, or `unavailable`
- `consecutive_failures`
- `reason`, `last_success_at`, `last_failure_at`, `retry_at`

Rules:

1. First/second failure: `retry`.
2. Three consecutive failures: `unavailable` for 24 hours.
3. `retry_at` expiry allows automatic recheck.
4. Successful fetch resets status and failure count.
5. Feed status never changes Daily/EOD eligibility or deletes historical data.

The 11 symbols were initialized as `unavailable`, failure count 3, based on repeated Settrade `empty intraday response` evidence in the 2026-08-20/21 runs. Cooldown is 24 hours.

## Dashboard contract

When the feed is unavailable:

- no old 60m row is used as the current card quote
- `intradayAvailable = false`
- `intradayFreshness.status = unavailable`
- `decision_source = Daily EOD`
- `staleNote = 60m intraday feed unavailable; Daily EOD shown for decisions.`
- user-facing freshness badge: `60m unavailable · Daily EOD`

Daily EOD must never be relabelled as a 60m chart/quote.

## Verification evidence

- active intraday universe: 913 symbols (924 before excluding the 11 unavailable feeds)
- excluded symbols absent from `_intraday_universe`
- canonical scan refreshed: 898 evaluated/observed symbols
- dashboard snapshot: 898 items, 898 unique symbols
- `verify_scan_dashboard.py`: `ok=true`, no failures
- `/health`: DB up, Redis up
- served dashboard: HTTP 200
- focused tests: 27 passed (`test_intraday_ingestion.py`, `test_intraday_resilience.py`, `test_dashboard_freshness.py`)
- backend/build syntax compilation passed

## Implementation files

- `backend/update_data.py` — table, failure tracking, cooldown, universe filtering
- `backend/build_dashboard.py` — feed-status-aware snapshot serialization and no stale intraday overlay
- `backend/dashboard_template.html` — unavailable-feed badge
- `backend/verify_scan_dashboard.py` — snapshot contract verification; legacy scan group labels are not compared to reconciled dashboard taxonomy

## Operational follow-up

- Let the 24-hour retry policy recheck these symbols.
- If a symbol repeatedly fails after rechecks, investigate Settrade listing/suspension status or add an authoritative feed-specific override; do not exclude it from Daily automatically.
- Keep `COLOR` reactivation owned by the official Settrade master sync.
