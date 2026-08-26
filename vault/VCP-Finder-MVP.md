# Signalix VCP Finder MVP

> **STATUS: CURRENT** · **CANONICAL_FOR:** VCP-first MVP surface and display contract.
> **Last reviewed:** 2026-08-26

## Product surface

- `/mvp` opens on **Daily VCP Shortlist**, the fast actionable-only view.
- **All VCP · 60m** is the full current VCP universe view with forming/state filters and audit coverage.
- The former Daily Shortlist and All Stocks Explorer are removed from visible MVP navigation; their backend/API and historical notes remain preserved for rollback/audit.

## Table contract

The primary VCP table shows only:

- Symbol/name
- Price
- `% Change` from the latest two stored 60m closes
- Distance to pivot
- R/R when an authoritative target/risk source exists; otherwise `—`

Contraction and breakout-volume evidence remain deterministic sort inputs and drawer evidence, not primary table columns.

## Display and grouping

Display order:

1. CONFIRMED · REVIEW
2. NEAR TRIGGER · VOLUME CHECK
3. READY · WAIT FOR BREAKOUT
4. **BREAKOUT WATCH · INTRABAR**
5. **FORMING · MATURING**
6. **FORMING · EARLY**
7. **FORMING · NEEDS WORK**
8. **EXTENDED · DO NOT CHASE**
9. **FAILED / INVALIDATED**
10. **STALE DATA**
11. **NOT VERIFIED**

- `BREAKOUT_WATCH` is an intrabar watch state: price reaches pivot and volume evidence passes, but the latest bar is not yet a closed confirmation. It is actionable for review only, never an automatic buy.
- Forming filters are `all`, `maturing`, `early`, and `needs_work`. Full-universe persistence remains one result per eligible symbol; presentation grouping never changes scan eligibility.

## Filters

- Price range supports multi-select: `<2 THB`, `2–10 THB`, `>10 THB`.
- Margin rates support multi-select with **Select all / Clear / Apply**. Checkbox changes do not reload until Apply.
- Missing index/margin data produces no tag and never a `NOT_VERIFIED` placeholder.

## Data and provenance

- VCP reads stored 60m OHLCV only and does not overwrite Daily state.
- VCP runs after committed `full_success` or `partial_success` intraday ingestion, with ingestion lineage and overlap lock.
- Failed/skipped ingestion does not create a new VCP run.
- Drawer uses the VCP result payload immediately and fetches only the 60m chart; it does not fetch Daily symbol detail or substitute old Daily provenance.
- Provenance displays VCP run `as_of`/`fetch_completed_at` and latest closed bar.
- Missing optional company description is hidden; it is not required for the core decision surface.
