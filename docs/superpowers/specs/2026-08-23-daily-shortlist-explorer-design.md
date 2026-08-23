# Signalix Daily Shortlist + All Stocks Explorer — Design

> **STATUS: APPROVED DESIGN**
>
> **Owner approval:** 2026-08-23
>
> **Scope:** Product and interface contract only. This document authorizes no code change, deployment, data deletion, or archival by itself.

## 1. Decision

Signalix will use two explicitly separate public research surfaces:

1. **Daily Shortlist** — the default, decision-first surface for trustworthy Thai daily swing-trade setups.
2. **All Stocks Explorer** — a secondary, on-demand research surface for the full ORD universe.

The existing stage-first dashboard is retained as the starting point for All Stocks Explorer. It must not be presented as the default recommendation surface or imply that every displayed symbol is a trade suggestion.

## 2. Product job and boundaries

### Daily Shortlist

The job is: *Which Thai equity setups deserve review today, and what must happen before action?*

It is for Daily-chart swing trades expected to be held for several days to several weeks. It is not a generic scanner, a portfolio manager, an intraday terminal, or automatic trading advice.

The default page contains only two states:

- **READY** — a mature setup whose trigger and invalidation boundary are explicit. This is ready for trader review, never an automatic order.
- **PRE-READY** — a mature setup with acceptable structure and risk, but an explicit confirmation condition remains unmet.

`DEVELOPING`, base-building, invalidated, broken, low-liquidity, and `DO NOT CHASE` names are not Daily Shortlist candidates. They remain available only where relevant in Explorer, deep dive, or audit/history.

### All Stocks Explorer

Explorer supports broad research: symbol lookup, Stage/structure inspection, market-wide comparison, and evidence drill-down. It retains full ORD coverage and may expose research filters, but those filters cannot alter scanner coverage or silently become recommendation eligibility rules.

Explorer must carry clear copy such as: **“Research universe — not a list of trade suggestions.”**

## 3. Universe and eligibility

- **Scan universe:** all active Thai ORD symbols. Coverage is preserved independently of any presentation or shortlist rule.
- **Daily Shortlist liquidity hard gate:** 20-day average daily traded value must be at least **THB 10,000,000**.
- A symbol that fails this gate remains in the full-universe scan and Explorer, with its liquidity limitation explicit. It is ineligible for Daily Shortlist publication.
- No hidden price, volume, stale-data, Stage, or taxonomy filter may reduce the full scan universe.

## 4. Deterministic decision contract

A Daily Shortlist item must serialize and display:

- symbol and Daily EOD as-of timestamp;
- freshness/source/provenance;
- `lifecycle_state` and action label as separate fields;
- `READY` or `PRE_READY` publication state;
- trigger / required confirmation;
- invalidation or system-stop boundary;
- liquidity gate evidence;
- structural evidence and gate reasons;
- ranking components, policy version, and total ordering.

Hard gates decide eligibility and state. Ranking never overrides a failed hard gate.

### Ineligible examples

- average traded value below THB 10m over 20 days;
- data freshness/provenance unavailable or insufficient;
- structurally broken or invalidated setup;
- materially extended setup where risk/reward is unsuitable (`DO NOT CHASE`);
- immature/base-building setup (`DEVELOPING`);
- no explicit trigger or invalidation boundary.

## 5. Quality ranking

Eligible items are ordered by transparent, deterministic components:

| Dimension | Weight | Intent |
|---|---:|---|
| Structure / setup quality | 40% | Trend quality, mature structure, base/breakout/pullback integrity, damage flags |
| Entry readiness | 30% | Trigger proximity and confirmation status; no extended chase |
| Risk / reward | 20% | Clear invalidation, risk distance, and available reward relative to risk |
| Liquidity | Gate + tie-breaker | THB 10m 20-day average is mandatory; stronger liquidity can resolve otherwise comparable ranks |

Market regime is visible market context only. Per owner decision, it does **not** suppress candidates, modify eligibility, or lower ranking.

## 6. Interface contract

### Daily Shortlist default page

1. Freshness/as-of status is visible before recommendations.
2. READY appears first, ordered by quality.
3. PRE-READY follows, ordered by quality.
4. Each card answers in seconds:
   - Why is this here?
   - What confirms the setup?
   - What invalidates it?
   - Why does it rank above the next candidate?
5. Chart and extended evidence load only when the trader opens a candidate.
6. Market regime is visible as context, not an action gate.
7. A direct route/link exposes **All Stocks Explorer**.

No default filter wall, full-universe card dump, portfolio control, or base-building section belongs on this surface.

### All Stocks Explorer

- Secondary navigation, not the default landing surface.
- Preserves the existing full-universe/research intent, with progressive loading and explicit research-not-recommendation copy.
- Stage, structural groups, liquidity views, and search/filter controls may remain here when they provide research value.
- Explorer does not call a symbol `READY`, `BUY ZONE`, or a suggestion unless it has passed the Daily Shortlist decision contract.

## 7. Data and performance boundaries

- Do not ship the entire full-universe payload as the first paint for Daily Shortlist.
- Use a compact shortlist endpoint/snapshot containing only candidate card data; deep evidence/chart stays on demand.
- FULL ORD scan records remain complete and append-only for audit and future Explorer use.
- Daily EOD classification is the authoritative source for this product surface. Intraday remains a separate observation layer and may not silently replace Daily state.

## 8. Acceptance criteria before release

### Decision engine

- Full active ORD coverage is demonstrably preserved in scan records.
- Every published candidate is `READY` or `PRE_READY`, passes the THB 10m liquidity gate, and has trigger, invalidation, provenance, and rank components.
- No invalidated, developing, low-liquidity, broken, or `DO NOT CHASE` candidate appears in Daily Shortlist.
- Ranking is reproducible from serialized components and policy version.
- Valid and invalid historical fixtures test hard-gate and ranking behavior.

### User-visible behavior

- Daily Shortlist loads as a usable desktop and mobile screen without requiring the complete market snapshot.
- First screen makes READY versus PRE-READY unmistakable.
- Card open, chart/evidence loading, empty-shortlist, stale-data, and API-error journeys are browser-tested.
- Explorer is reachable, visually labelled as research, and does not misrepresent all-stock results as suggestions.

### Governance and deployment

- Product strategy, decision ledger, execution pipeline, and focused implementation plan remain aligned.
- No generated logs, `.venv` files, old plans, or unrelated dirty work are included in the feature commit.
- Release is blocked until source/data/served artifact/browser evidence all pass Lite’s final gate.

## 9. Explicit non-goals for this slice

- Portfolio recommendations or broker execution.
- Intraday-first suggestions.
- Regime-based candidate suppression or rank penalties.
- Automatic buy/sell decisions.
- LLM-calculated states, scores, risk, trigger, stop, or rank.
- Deleting the existing Explorer/dashboard before its retained role is verified.

## 10. Implementation sequencing (after plan approval)

1. Repository safety and artifact classification; preserve pre-existing work.
2. Introduce and test the Daily Shortlist decision contract and compact data artifact.
3. Implement Daily Shortlist UI as a thin vertical slice.
4. Retain/adapt the current dashboard as All Stocks Explorer with clear boundary copy.
5. Run historical, API/data, served-artifact, desktop, mobile, empty, stale, and error acceptance gates.
6. Only after acceptance, archive superseded design/work artifacts according to vault governance.
