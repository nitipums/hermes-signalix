# Signalix VCP Finder MVP

> **STATUS: CURRENT** · **CANONICAL_FOR:** VCP-first MVP surface and display contract.
> **Last reviewed:** 2026-08-26

## Product surface

- `/mvp` opens on **Daily VCP Watchlist**, the fast review view.
- **All VCP · 60m** defaults to the current `marginable_long` operational universe (237 active Thai ORD symbols with `can_buy=true`); explicit `active_ord` remains the full 931-symbol audit/rollback view with forming/state filters.
- The current visible MVP focus is dashboard-only: Daily VCP Watchlist is the fast review view; All VCP · 60m / Explorer defaults to `marginable_long` and exposes the selected universe metadata. Former Daily Shortlist and legacy All Stocks Explorer labels are retired from visible MVP navigation; backend/API and historical notes remain preserved for rollback/audit.
- Alert delivery is paused. The delivery source remains preserved, but the Docker service is gated under Compose profile `alerts` and is not started by default.

## VCP type taxonomy — candidate implementation

The candidate implementation separates **VCP morphology**, **entry profile**, and **state/actionability**:

- `standard_vcp` — valid VCP morphology with the normal entry profile: wait for pivot breakout/confirmation.
- `low_cheat_vcp` — a stricter early-entry profile that is a subset of valid VCP morphology, requiring healthy 60m trend, shallow/tight final contraction, near-pivot price, and tight usable invalidation risk. It is review-only and never an automatic buy.
- `break_ath` — price-break overlay from historical `price_data` ATH when evidence qualifies.
- `new_stock` — reserved for verified listing-date evidence; not assigned from ticker/feed age.

Low-Cheat is not a looser or higher-quality replacement for Standard VCP. `cheat` describes the possible entry timing before a confirmed breakout, not a pattern name inferred from shallow numbers alone. Types never promote READY/CONFIRMED, and full-universe retention remains unchanged.

This taxonomy is still under sample validation; thresholds and sample outcomes must be reviewed before locking v1.

The 60m lifecycle trend gate is strict: Daily trend context cannot promote 60m `READY` or `CONFIRMED`; it is used only by context overlays.

## Review lanes

The current VCP lifecycle state remains authoritative. A separate `review_lane` preserves actionable context when a price/volume event exists before full VCP morphology qualifies:

- `PRICE_VOLUME_BREAKOUT` — close and breakout volume pass, but full structure does not.
- `PIVOT_TOUCH_VOLUME_WATCH` — pivot touched/near with volume evidence, close confirmation pending.
- `CLOSE_BREAKOUT_VOLUME_PENDING` — close clears the required level, but volume confirmation is absent.
- `INSURANCE · CONTEXT WATCH` — insurance industry context within the review distance window; not a buy signal.
- `DAILY_CONTEXT_WATCH` — Daily waiting-breakout context; independent from 60m confirmation.

These lanes are review overlays only. They do not change `state`, `actionable`, or `watchable`; low-liquidity exceptions remain visibly tagged.


Current state does not erase prior review-worthy events. API/UI may expose `last_watch_event` and `late_watch` context. `DAILY_CONTEXT_WATCH` surfaces the latest Daily `waiting_breakout` context when 60m VCP is not yet qualified; it does not change VCP state or actionability. `LATE WATCH · DO NOT CHASE` identifies a prior watch whose current distance is beyond the fresh-review threshold.

## Watchlist defaults

Daily VCP Watchlist defaults to these removable presentation filters:

- Marginable: on, all margin rates
- 20-day average trade value: `> THB 10,000,000`
- Current 60m price: `> THB 0.60`
- These defaults are presentation filters only and can be disabled by the owner.

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

- `BREAKOUT_WATCH` is an intrabar watch state: price reaches the 60m pivot and volume evidence passes, but the latest bar is not yet a closed confirmation. It is reviewable in Daily VCP Shortlist but `actionable=false`; it never means an automatic buy.
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
- Daily VCP Shortlist polls for a newer run while open; it shows review count separately from full-universe evaluation and feed coverage.
- Missing optional company description is hidden; it is not required for the core decision surface.
- **2026-08-29 unified decision migration, updated 2026-08-30:** The serving VCP projection exposes one compact v2 decision projection per sufficient-data result through `decision_shadow_v2`, with lane/actionability labels. The operational default is `marginable_long` (237 `can_buy=true` symbols); `active_ord` is explicit audit/rollback. Stale/unverified/insufficient evidence remains fail-closed. Daily context cannot promote 60m confirmation; raw VCP/lifecycle fields remain available for audit. Public `/mvp` and `/api/vcp-finder` were rechecked after service recreation on 2026-08-30, including real desktop/mobile checks, with no alert or threshold changes.
- **2026-08-30 structure-first candidate update:** Incomplete volume no longer blocks candidate discovery; the full `EVENT_WATCH` lane is visible as `WATCH_ONLY` without a cap. `REVIEW_NOW` remains actionable only; event evidence cannot promote confirmation. The mobile table is responsive at 390px and payload cache/coalescing protects repeated filter refreshes; cold API timing remains a separate performance metric.
