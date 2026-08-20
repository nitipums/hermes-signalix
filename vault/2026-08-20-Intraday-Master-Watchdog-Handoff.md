# Signalix — Intraday Master / Watchdog Handoff

Date: 2026-08-20 (Asia/Bangkok)
Owner: Bee / lite
Status: **current**

## Decisions

1. Settrade's browser/API stock master is the sole ORD instrument authority.
   Source page: `https://www.settrade.com/th/get-quote`
   Browser-rendered endpoint: `/api/set/stock/list`
   Import only `securityType=S` on SET/mai (including IFF); do not import DR,
   ETF, DW, futures, options, or fund types into ORD.
2. Official master symbols are auto-reactivated. ORD symbols absent from the
   official master are marked `inactive`. This supersedes manual exclusion as
   the long-term source of truth.
3. Weekly sync: `signalix-settrade-master.timer`, Sunday 03:00 Asia/Bangkok,
   randomized delay up to 10 minutes. It obtains Settrade page cookies before
   calling the WAF-protected JSON endpoint.
4. Intraday owner: full active ORD, 60m-only, every 15 minutes, 10:00–16:45
   Bangkok. Current bounded fetch shape: limit=4, workers=10, batch=50,
   batch_delay=2s, jitter=0.5s, session_retries=3, retry_backoff=5s.
5. Old `signalix-intraday-healthcheck.timer` is disabled. New
   `signalix-intraday-watchdog.timer` runs every 15 minutes in the same window,
   checking price/state freshness with 30-minute thresholds.
6. Daily scan no longer drops active symbols only because daily history is
   below the former 260-day technical window. Short-history symbols remain as
   explicit `INSUFFICIENT_HISTORY` non-signal records; no technical signal is
   fabricated.

## Evidence from 2026-08-20

- Settrade official stock master: 931 records.
- Final full intraday run: 931 attempted, 915 succeeded, 16 empty responses,
  3,659 bars offered, 784 inserted, 2,875 updated, ~180 seconds.
- Final scan: HTTP 200.
- Final dashboard snapshot: 904 unique items; 4 explicit short-history rows
  observed: GSTEEL, KPNREIT, SIRIPRT, WSOL.
- Runtime checks: backend health 200 (DB/Redis up), dashboard 200.
- Relevant tests passed: master parser, insufficient-history, screening policy,
  intraday resilience/ingestion; systemd-analyze verify passed.
- Session finalization: full pytest suite green; dashboard coverage fallback and
  scan-dashboard consistency tests aligned with current contracts; stale runtime
  logs/generated artifacts preserved in named stashes; Git working tree clean.
- Dashboard provenance now shows one concise `Last Scanned` timestamp sourced from
  the latest persisted intraday run; projection badge defaults prevent snapshot
  build failure when reconciled artifact rows are incomplete.

## Operational notes

`inserted` versus `updated` is normal idempotent upsert accounting. A run's
`rows_offered = rows_inserted + rows_updated`; a low inserted count alone is
not missing data. Empty intraday responses remain fetch errors, not proof that
an official symbol is delisted; the official master controls active/inactive.

## Related

- [[Architecture]]
- [[Deployment]]
- [[Testing-and-Architecture]]
- [[Browser-and-Freshness-Verification]]
