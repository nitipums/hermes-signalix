# Signalix User-Validation Refresh, Card, and Wave Contract

> **STATUS: OWNER-APPROVED DESIGN FRONTIER — READY FOR TICKETS** · 2026-09-01
> **Scope:** public `/mvp` setup-candidate review surface after Arm's TASCO feedback.
> **Implementation boundary:** design/spec only in this document; no code, deployment, broker, alert, or automatic-trading authorization.

## Problem Statement

The current MVP can load real setup candidates, but the overview consumes too much space with filters, silently refreshes the review set, and does not make decision-critical evidence prominent. Cards hide or omit useful Target/R:R/context values. Wave evidence is difficult to follow across chart timeframes. The current data contract can mark a candidate `DATA_BLOCKED` when Daily data exists and current 60m data is fresh only because the latest official Daily EOD has not yet been published.

## Solution

Make the review surface explicit and stable:

1. Replace silent overview refresh with an explicit Refresh action, visible update boundary, and optional opt-in live-refresh mode.
2. Replace the large filter block with a compact Search/Lane/Refresh toolbar. Keep detailed filters behind a collapsed Advanced filters section.
3. Make cards scan-friendly and decision-first. Show price/change, lane/action, Wave/confidence, Trigger/Stop/Target/R:R when available, RS to two digits, compact 52W/ATH/breakout evidence, and freshness/data status. Keep Sector/Peer/VCP/full evidence in the drawer, with explicit `Not available` states when absent.
4. Separate data availability from setup readiness. Latest official Daily remains the structural Wave authority. Current 60m data supplies setup/entry evidence and may be provisional. Missing current-session official Daily EOD must not alone collapse otherwise usable evidence into generic `DATA_BLOCKED`.
5. Make chart evidence honest across timeframes. Daily markers remain Daily-source evidence. They may appear as contextual overlays on Week/60m only when clearly labelled `Daily source · not 60m wave`; 60m setup markers remain separate. Current/unclosed candles may render as provisional with an explicit timestamp/status and must not be confused with official Daily EOD.

## User Stories

1. As an Arm reviewing candidates, I want the overview controls compact, so that I can see candidates without scrolling past irrelevant filters.
2. As an Arm reviewing a setup, I want the current review set to remain stable, so that a background refresh does not replace the symbols I am inspecting.
3. As an Arm, I want an explicit Refresh action and update boundary, so that I know when new market data entered the screen.
4. As an Arm, I want an opt-in live-refresh mode, so that automatic updates are available without being the silent default.
5. As an Arm, I want the card to show the Wave state and confidence prominently, so that I can triage candidates quickly.
6. As an Arm, I want Trigger, Stop, Target, and R/R on the card when authoritative values exist, so that I can judge setup quality without opening every drawer.
7. As an Arm, I want RS shown to two digits, so that the ranking signal is compact but useful.
8. As an Arm, I want 52W, ATH, and breakout evidence expressed in plain compact labels, so that I do not have to decode ambiguous badges.
9. As an Arm, I want Sector, Peer, and VCP details available in the drawer, so that context is available without overcrowding the card.
10. As an Arm, I want missing context to say `Not available` with provenance/status, so that a dash is not mistaken for zero or a silently omitted field.
11. As an Arm, I want Daily structural Wave evidence to remain tied to the latest official Daily snapshot, so that intraday noise cannot rewrite the higher-timeframe thesis.
12. As an Arm, I want current 60m setup evidence to be visible with provisional status when needed, so that current-session information is useful without being mislabelled as official Daily evidence.
13. As an Arm, I want a candidate with valid latest Daily evidence and fresh 60m data to remain evaluable when only the current official Daily EOD is pending, so that the product does not look broken during the session boundary.
14. As an Arm, I want true missing, stale, invalid, or incoherent evidence to remain fail-closed, so that freshness improvements do not weaken safety.
15. As an Arm, I want Daily markers visible as contextual references on other charts only with a source-timeframe label, so that repeated markers do not imply false 60m precision.
16. As an Arm, I want 60m setup markers separated from Daily markers, so that trigger/stop evidence is not confused with structural Wave evidence.
17. As an Arm, I want an unclosed candle clearly labelled provisional, so that Day/Week/60m direction differences have an explainable as-of boundary.
18. As an Arm, I want Wave Evidence explanations to show rule, supporting evidence, alternative/missing evidence, policy, and snapshot identity, so that I can confirm or dispute the machine interpretation.
19. As an Arm, I want the review surface to preserve the canonical 237-symbol accounting and provenance, so that UI simplification does not drop data silently.
20. As an Arm, I want semantic disagreements captured as feedback rather than auto-tuned from one example, so that the Wave model changes only through an explicit decision process.

## Implementation Decisions

- Use the existing canonical setup-candidate response and current chart/detail seams; do not introduce a competing VCP primary contract.
- Treat `latest official Daily snapshot`, `current 60m setup evidence`, and `setup readiness` as separate concepts in the response and presentation.
- Preserve the six canonical decision lanes and full-universe evaluated/returned metadata.
- Replace timer-driven default refresh with explicit refresh. Any opt-in live refresh must be visibly enabled and must not overwrite an open drawer or an actively filtered review without a clear update boundary.
- Use a compact primary toolbar and a collapsed advanced-control region. Advanced controls remain literal and must not silently exempt rows from checked constraints.
- Define a card presentation contract around decision essentials; richer context stays in the drawer but remains honest and source-labelled.
- Use explicit availability vocabulary (`Not available`, `Awaiting official EOD`, `Provisional`, `Fresh`, `Stale`, `Invalid`) rather than ambiguous dashes.
- Daily markers retain `timeframe=1D`/Daily source identity. Week/60m contextual display requires an explicit mapped/contextual marker state; no marker may imply it was calculated from the displayed timeframe when it was not.
- Current/unclosed candles can be rendered only with explicit provisional status, exact timestamp/as-of, and separate official Daily provenance.
- No alerts, broker execution, evaluator auto-caller, or automatic trading is part of this design.

## Testing Decisions

- Test the real public `/mvp` path and canonical `/api/setup-candidates` response, not injected fixture payloads alone.
- Add a regression for no silent refresh: repeated idle time does not change the rendered review set unless explicit refresh or opt-in live refresh is enabled.
- Add contract tests for latest-official-Daily plus fresh-current-60m, pending official EOD, true missing/stale/invalid data, and setup-not-detected states.
- Assert full-universe counts and exact data/status reason fields independently from the visible page size.
- Add browser tests for compact toolbar, advanced-filter disclosure, card-to-drawer parity, R/R/target visibility, two-digit RS, and plain 52W/ATH/breakout labels.
- Add chart tests for Daily/Week/60m source-timeframe labels, contextual versus mapped markers, provisional current candles, and consistent snapshot/as-of identity.
- Run desktop and 390px mobile journeys through the public URL, including drawer scroll, chart controls, filter interaction, refresh, and console/page-error checks.
- Arm's examples (KCE, IRPC, BCP, RCL, BBGI) are validation fixtures/feedback inputs. They are not hard-coded expected production labels until replay and owner confirmation establish the rule.

## Out of Scope

- Automatic trading, broker execution, alerts, and evaluator auto-caller wiring.
- Changing Wave labels solely to match a single screenshot or subjective expectation.
- Rebuilding the entire chart engine or copying Daily markers onto 60m as if they were native 60m observations.
- Removing historical VCP/replay evidence.
- Broad product navigation or multi-user SaaS work.

## Further Notes

The current live TASCO probe showed `daily_available=true` and fresh 60m data while `daily_final_session_available=false` forced `STALE_DAILY_DATA` and `DATA_BLOCKED`. The first implementation slice should make this boundary explicit and testable before UI polish. Arm's manual Wave confirmation remains a separate owner-validation gate after the rendered contract is improved.
