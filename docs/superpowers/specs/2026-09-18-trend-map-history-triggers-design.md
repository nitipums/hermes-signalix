# Trend Map Historical EOD Snapshots and Trigger Evidence

> **STATUS: OWNER-APPROVED DESIGN — SPEC DRAFT FOR REVIEW**
> **Date:** 2026-09-18
> **Scope:** Extend the canonical Daily Trend Mapping surface at `/trend-map` and `/api/trend-map` with up to 3 completed EOD trading-session snapshots, trend duration/change-date evidence, deterministic EOD trigger levels, and current-session intraday trigger markers.

## Problem Statement

Arm needs to inspect how each symbol's Daily trend evolved over recent completed EOD sessions, understand when the current trend began and how long it has persisted, and see the deterministic price levels at which an EOD close could change the trend. During the current session, Arm also needs an explicit visual indication when the intraday price reaches either trigger without mistaking that observation for a confirmed trend change.

The feature must preserve the existing Trend Map contract: deterministic, read-only evidence for chart review. It must not create alerts, orders, broker actions, or automatic trading behavior, and it must not degrade the current snapshot request path.

## Solution

At each EOD publication boundary, build and validate an immutable Trend Map snapshot artifact for that completed trading session. Retain an index of at most 3 completed EOD trading sessions. The API selects the current snapshot by default or an explicitly requested historical session. Historical snapshots use the universe resolved for that EOD session and expose their own as-of, coverage, quality, and provenance metadata.

The EOD artifact stores the deterministic trend state, the date the current trend began, the number of completed sessions in that trend, and the up/down trigger levels calculated from the same EOD state. The current snapshot may receive a display-only intraday quote overlay and trigger-reached markers. Historical snapshots do not receive today's intraday quote or trigger marker.

## User Stories

1. As Arm, I want to select any of the latest 3 completed EOD trading sessions, so that I can review historical Trend Map state without rebuilding data at request time.
2. As Arm, I want the latest EOD snapshot to remain the default, so that existing current-use behavior is unchanged.
3. As Arm, I want the selected snapshot date and whether it is current or historical to be visible before opening a drawer, so that I do not confuse old evidence with current evidence.
4. As Arm, I want a historical snapshot to retain the universe resolved on that EOD date, so that historical coverage is not silently rewritten by today's universe.
5. As Arm, I want the date on which the current trend began, so that I can see when the classifier first entered the displayed trend.
6. As Arm, I want the duration of the current trend in completed trading sessions, so that I can distinguish a newly changed trend from a persistent one.
7. As Arm, I want duration to start at 1 on the session where the trend changes, so that the count has an unambiguous boundary.
8. As Arm, I want duration to increment only when the same trend continues into another completed EOD session, so that intraday noise cannot change the count.
9. As Arm, I want an up trigger and down trigger for each row when they can be calculated, so that I know the deterministic price boundaries relevant to the next EOD classification.
10. As Arm, I want unavailable trigger values to be explicitly marked as not verified with a reason, so that missing evidence is not represented as zero or an invented estimate.
11. As Arm, I want the current intraday price to show when it reaches or crosses the up trigger, so that I can recognize a possible upward transition condition.
12. As Arm, I want the current intraday price to show when it reaches or crosses the down trigger, so that I can recognize a possible downward transition condition.
13. As Arm, I want trigger markers to remain provisional and not mutate the displayed trend during the session, so that only a completed EOD close and rerun can confirm a trend change.
14. As Arm, I want historical snapshots not to show today's intraday trigger markers, so that current prices are not projected backward onto old state.
15. As Arm, I want the UI to explain that an EOD close at or through the trigger may change the next EOD classification, so that a reached marker is not interpreted as a confirmed change.
16. As Arm, I want stale or missing intraday data to leave the EOD trend visible while marking trigger status unavailable, so that quote freshness does not erase valid Daily evidence.
17. As Arm, I want an EOD publication failure to leave the last validated snapshot served and avoid advertising an unpublished session, so that the surface fails closed.
18. As Arm, I want artifact/index mismatch or corruption to produce an explicit not-verified state rather than silently falling back to current, so that provenance remains trustworthy.
19. As Arm, I want current snapshot performance to remain within the existing read-model path, so that adding history does not slow normal use.
20. As Arm, I want the feature to remain read-only and non-actionable, so that evidence cannot become an automatic trading instruction.

## Implementation Decisions

- The canonical surfaces remain `/trend-map` and `/api/trend-map`.
- A snapshot means one completed EOD trading session, not a calendar day. The retention limit is 3 completed sessions.
- Each snapshot retains the historical universe resolved for that EOD session. Rows that disappear from today's universe remain visible in the historical snapshot where they existed.
- The latest snapshot remains the API default when no snapshot selector is supplied. Historical selection is explicit by EOD session date.
- The historical read path selects a validated immutable artifact from a bounded snapshot index. It must not query raw market history, rescan the universe, or rebuild indicators for a valid artifact.
- Artifact publication and index update must be atomic from the reader's perspective. A failed or incomplete EOD publication must not advertise a new snapshot.
- Each row carries snapshot/as-of identity, symbol, trend state, trend changed date, trend duration in completed sessions, up trigger, down trigger, trigger basis, and row-level quality/provenance fields.
- Trend changed date is the completed EOD session date on which the deterministic classifier first entered the current trend. It is the only user-facing change date required by this design; no separate publication timestamp is part of the display contract.
- Trend duration is `1` on the change session and increments by one for each subsequent completed session that retains the same trend. A transition resets the count to `1`.
- Up/down trigger values and their comparison operators are deterministic source-code outputs. An unavailable value is null/not-verified with an explicit reason; zero is never used as a missing sentinel.
- The trigger marker compares the latest usable intraday last price with the stored EOD trigger. Up is reached when last price is at or above the up trigger; down is reached when last price is at or below the down trigger. The marker is display-only and provisional.
- A trend changes only after the relevant completed EOD close has been classified by the EOD producer. Reaching a trigger intraday never mutates the trend, duration, or historical artifact.
- Intraday trigger markers attach only to the current EOD snapshot. Historical snapshots remain immutable EOD evidence without today's quote overlay.
- The UI uses explicit text and directional symbols in addition to color: `UP TRIGGER REACHED`, `DOWN TRIGGER REACHED`, and an explanation that confirmation requires EOD classification.
- Current/historical state, selected snapshot date, snapshot row count, universe-as-of, freshness, quality, and provenance remain visible in the API and are represented in the first-screen UI banner.
- Missing, stale, invalid, corrupt, or mismatched artifacts fail closed as `NOT_VERIFIED` with reason. The system must not silently return current data for an unavailable requested date.
- The feature preserves `status=PRODUCTION_READ_ONLY`, `research_only=false`, and `actionability=NONE`. It does not add alerts, broker execution, auto-trading, or action lanes.
- The existing intraday display quote/read-model boundary remains authoritative. Trigger status must use the validated intraday read model or explicit fallback provenance and must not introduce per-row PostgreSQL request queries.

## Testing Decisions

- Test externally observable deterministic behavior at the classifier/builder seam: first-day duration, continuation, transition reset, trigger boundaries, missing trigger reasons, no lookahead, and stable historical universe identity.
- Test artifact publication and index selection with 3 sessions, fewer than 3 sessions, retention trimming, exact date selection, unavailable dates, corrupt artifacts, index/artifact mismatch, and failed publication.
- Test API responses for current versus historical metadata, row counts, as-of identity, provenance, quality states, and explicit not-verified failures.
- Test intraday projection for up reached, down reached, neither reached, exact equality at boundary, stale/missing quote, both thresholds unavailable, and the invariant that trend state is unchanged.
- Follow existing Trend Map/read-model/artifact test patterns and keep source, artifact/API, data, and browser verdicts separate.
- Browser acceptance covers desktop and 390px mobile: snapshot selection, current/historical banner, row/drawer duration and changed date, both marker states, unavailable/error/recovery states, keyboard/focus behavior where relevant, and no horizontal overflow.
- Performance tests compare current snapshot reads before and after history support and exercise historical selection without raw-history access or indicator rebuild on the valid artifact path.
- Regression tests assert the non-actionable contract and ensure no alert/order/broker side effect is introduced.

## Out of Scope

- Intraday-confirmed trend changes.
- Alerts, notifications, broker execution, auto-trading, or automatic portfolio actions.
- Replacing the deterministic classifier with an LLM or using an LLM to calculate technical values.
- Arbitrary history beyond the latest 3 completed EOD sessions.
- Rewriting historical snapshots from the current universe or today's intraday price.
- New setup-candidate, Elliott, VCP, or `/mvp` behavior.
- Calendar-day duration semantics.
- A separate publication timestamp in the user-facing trend-change field.

## Further Notes

The approved implementation should be delivered as vertical slices: (1) deterministic snapshot/trend-duration/trigger foundation, (2) immutable EOD artifact/index and API selection, (3) current-session intraday marker projection, (4) Trend Map UI journey, and (5) runtime/browser/documentation acceptance and closeout. Each slice must use an isolated worktree, preserve owner-owned dirty files, and report source, tests, artifact/API, data, browser, and deployment verdicts separately.
