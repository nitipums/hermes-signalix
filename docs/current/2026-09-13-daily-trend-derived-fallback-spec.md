# Daily Trend Map Derived-Daily Fallback

> **STATUS: CURRENT — bounded implementation spec**
> **Owner:** Arm · **Orchestrator:** Lite
> **Authority:** `AGENTS.md`, `vault/Execution-Pipeline.md`, `vault/Deployment.md`

## Problem Statement

Three symbols in the canonical `marginable_long` universe lack official Daily rows. The Daily Trend Map runner must continue to show the complete 237-symbol universe without relabeling Settrade 60m-derived data as official Daily evidence. The current read path can consume prebuilt derived rows, but it does not yet fill a missing current session automatically and does not preserve all derived lineage in the published row contract.

## Solution

Use official `price_data` rows first. For each symbol and date absent from official Daily, use only a validated completed-session row from `derived_daily_price_data`, produced deterministically from Settrade 60m. The EOD runner may fetch a bounded 60m window only for symbols/dates missing official Daily, aggregate complete current sessions, and publish the derived row. If neither source is valid, retain explicit `DATA_BLOCKED`/`NO_DATA`.

## User Stories

1. As Arm, I want all 237 declared symbols visible, so missing history does not silently remove coverage.
2. As Arm, I want official Daily to override derived data on the same symbol/date, so the authoritative source remains primary.
3. As Arm, I want derived rows clearly labeled, so a 60m aggregate cannot be mistaken for official EOD.
4. As Arm, I want the runner to fill only missing current sessions, so routine EOD work does not perform an unbounded historical backfill.
5. As an auditor, I want source run ID, source timestamps, source timeframe, bar count, and derivation method, so every derived value is reproducible.
6. As a reviewer, I want incomplete/provisional sessions rejected, so no lookahead or partial-session Daily bar enters the read model.
7. As Arm, I want the Trend Map to remain public read-only and non-actionable, so fallback data cannot create orders or alerts.

## Implementation Decisions

- Keep `price_data` as official Daily storage and `derived_daily_price_data` as a separate, non-official fallback store.
- Resolve rows per symbol/date: official rows are selected first; derived rows fill only dates not represented by official rows for that symbol.
- Derived eligibility requires the complete Bangkok session timestamps 09:00 through 16:00 ICT, valid OHLCV geometry, `source_bar_count=8`, `is_official=false`, the exact `settrade_60m_complete_bangkok_session_ohlcv_v1` method, and persisted `source_completion_cutoff` at or after 17:00 ICT and no later than the report cutoff (the 16:00 bar completes at 17:00; exactly 16:00 is rejected).
- Persist `source_completion_cutoff` as lineage alongside source, source timeframe, source run ID, first/last source timestamps, bar count, and derivation method. Migration 008 safely backfills only exact 09:00/16:00, 8-bar Settrade rows to 17:00 ICT; malformed rows remain ineligible. Quote provenance must identify the actual selected table and retain the Daily-first change basis without claiming official source.
- The bounded EOD fallback fetches only the current missing session for affected symbols using Settrade 60m, with an explicit limit sufficient for one current session and no historical expansion. It writes only the derived table and never mutates official Daily rows.
- Keep the publisher SELECT-only and keep all writes in the bounded ingestion/aggregation path.
- The report remains `PRODUCTION_READ_ONLY`, `research_only=false`, `actionability=NONE`, and preserves declared/evaluated/returned counts.

## Testing Decisions

- Test the public adapter behavior with a fake connection: official-first same-date precedence, derived fallback for no official row, derived fill for a missing official date, cutoff enforcement, and invalid/incomplete derived rows rejected.
- Test report/provenance behavior through the publisher contract: official and derived quote sources, source metadata preservation, 237-row coverage, and non-actionable envelope.
- Test the bounded current-session aggregator with complete 8-bar, 7-bar, 16:00 rejection, 17:00 acceptance, invalid-geometry, and idempotent rerun cases.
- Run focused tests, relevant backend regression tests, Python compile, `git diff --check`, live publisher, readiness, public API, and 390px browser acceptance.

## Out of Scope

- Yahoo Finance, Settrade Web scraping, TradingView MCP, or any external fallback beyond Settrade API 60m.
- Replacing official Daily history or claiming 52-week completeness from a short derived window.
- Setup/Elliott semantics, alerts, broker execution, auto-trading, or BUY policy changes.
- Broad historical backfill; history recovery remains a separate bounded task.

## Further Notes

Derived Daily is evidence for the read-only Trend Map and must remain visibly distinguishable in machine provenance. A successful transport response or process exit is not sufficient; source, lineage, freshness, artifact, API, and browser gates remain separate.
