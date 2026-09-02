# Signalix Wave Review, Drawer Navigation, and Candidate Filtering

> STATUS: OWNER-APPROVED DESIGN FRONTIER — 2026-09-01
> Scope: Daily Candidate review UX on the public `/mvp` route.

## Problem Statement

The current setup-candidate card and drawer do not make the current machine-generated Elliott Wave and confidence immediately visible. Reviewing several candidates requires closing and reopening the drawer, and Daily Candidate rows cannot be grouped or filtered by Wave.

## Solution

Expose a compact Wave/confidence label on every card and in the drawer, add previous/next navigation over the current filtered candidate collection, and add Wave grouping/filtering to Daily Candidate without changing the underlying Wave engine or treating machine labels as truth.

## Contract

- Display primary Wave state plus confidence (`low`, `medium`, `high`) when available; missing/unknown confidence stays explicitly unavailable.
- Preserve exact source-timeframe/provenance semantics: Daily is structural authority; 60m is provisional setup evidence.
- Drawer navigation follows the currently displayed, filtered, deterministically ordered collection. It updates symbol, card evidence, chart, and enrichment atomically; stale responses cannot overwrite the newly selected symbol.
- Previous/next controls expose position and disable at collection boundaries. Filter/search/group changes reset or reconcile the selected position.
- Daily Candidate supports group-by-Wave and an explicit Wave filter. Groups include the canonical states present in the payload, with an Unknown/Not verified bucket for missing or invalid states. No client-side label inference.
- Existing error, loading, Retry, no-overflow, and full-universe metadata contracts remain intact.

## Vertical tickets

1. UI-T06 Wave/confidence display
2. UI-T07 Drawer previous/next navigation, blocked by UI-T06
3. UI-T08 Daily Candidate group/filter, blocked by UI-T07
4. UI-T09 final public browser/mobile and owner-semantic acceptance, blocked by UI-T08

## Testing Decisions

Use the highest existing frontend contract seam plus real public browser journeys. Add tests for present/missing confidence, each Wave state, navigation boundaries and stale selection protection, filter/group/reset behavior, empty states, 390px overflow, and failure→Retry→recovery. Verify served assets after each promotion. Machine Wave correctness remains owner-review evidence, not an automated truth gate.

## Out of Scope

No Wave-engine threshold tuning, new trading/alert behavior, broker execution, database migration, auto-trading, or automatic semantic confirmation.
