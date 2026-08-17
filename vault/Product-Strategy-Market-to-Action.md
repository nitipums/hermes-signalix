# Signalix Product Strategy — Market View to Action

_Last updated: 2026-08-12; curated from product discussion with Arm._

## Product thesis

Signalix should evolve from a technical signal broadcaster into a system that turns a verified market view into an asset-appropriate action:

```text
Market View → Instrument → Action → Decision/Execution → Outcome
```

The shared internal foundation is the **Market View to Action Engine**. User-facing products use separate language and workflows for different trader/investor groups.

## Product surfaces

| Surface | User language | Signal source | Action style |
|---|---|---|---|
| Stock Alert | Stock Alert | Stock price/technical setup | Alert / plan |
| DR Follow | Parent stock / DR | Underlying stock or index | DR proposal, later controlled execution |
| TFEX Trigger | Underlying / contract | Underlying or index | Futures order intent, later controlled execution |
| Fund Plan | Group / theme / benchmark | Index, regime, or theme | Allocation, DCA, rebalance proposal |
| Investment Copilot | Portfolio action | Market view + private portfolio | Cross-account action proposal |

The engine is shared, but terminology, policy, UX, and execution adapters are separate because DR, TFEX, and fund users are different groups.

## Core foundation

```text
Market View
├── Technical signal engine
├── Fundamental snapshot/context
├── Underlying and instrument mapping
├── Instrument eligibility/conversion
├── Asset-specific risk/allocation policy
├── Action proposal
├── Recommendation/decision/execution logs
└── Outcome evaluation
```

Deterministic code owns prices, ratios, signals, conversion, risk, position sizing, stops, targets, state transitions, and order bounds. LLMs may summarize and explain structured outputs only.

## Cross-instrument relationship

Model the distinction between the signal source and the instrument actually used:

```text
Underlying / Benchmark → Tradable instrument
NVDA → NVD01 (DR)
SET50 → S50 futures (TFEX)
Nasdaq 100 → eligible Nasdaq/technology fund
Gold reference → gold futures or gold fund
```

### DR Follow

A parent-stock signal drives a DR check. Before proposing action, verify mapping, conversion ratio, FX, theoretical price, premium/discount, spread, liquidity, market sessions, freshness, and corporate actions. Do not treat a DR-only price trigger as sufficient.

Suggested states: `READY`, `WAIT_DR_CONFIRMATION`, `PREMIUM_TOO_HIGH`, `SPREAD_TOO_WIDE`, `STALE_UNDERLYING`, `MARKET_CLOSED`, `INVALID_MAPPING`.

### TFEX Trigger

A parent/index signal drives a contract and risk check. Verify contract month, basis, multiplier, margin, session, liquidity, max contracts, maximum loss, stop, overnight policy, idempotency, order status, and kill switch.

Progression: signal-only → shadow order → one-tap approval → broker readback/reconciliation → bounded auto-trade.

### Fund Plan

A group, index, or regime signal drives a fund proposal, not an instant-price trade. Check benchmark, NAV timing, cut-off, holidays, fee, hedge policy, tracking difference, and current portfolio allocation. Support Fund Watch, Fund Proposal, DCA Plan, and rebalance workflows.

## Fundamental context

Ingest sourced basic fundamentals into Signalix for value investors and mixed-style users. Keep it separate from technical signal/risk logic and show source date/freshness.

Minimum initial fields: revenue, revenue growth, net income, EPS, EPS growth, gross/net margin, ROE, ROA, debt/equity, operating cash flow, free cash flow where available, P/E, P/BV, dividend yield, market cap, fiscal period, reported date, source, currency, and data status.

UI should expose an English **Fundamental Snapshot** and separate Technical View, Fundamental View, and Combined Context. Never present a stale or undated ratio as current and never turn fundamental quality alone into an automatic buy.

## Recommendation and outcome log

Every proposal is immutable and records what the system knew at proposal time:

- timestamp and data timestamp
- market view/underlying and signal evidence
- target instrument and action
- trigger, price, stop, target, risk bounds
- policy/version and source provenance
- expiry and invalidation condition
- user decision: accepted, rejected, ignored, or expired
- execution mode and paper/real result
- later realized outcome

Lifecycle:

```text
PROPOSED → ACCEPTED/REJECTED/IGNORED → EXECUTED/PAPER_EXECUTED
→ OPEN → CLOSED/EXPIRED/INVALIDATED → OUTCOME_RECORDED
```

Keep Recommendation Log, Decision Log, Portfolio Event Log, Execution Log, and Outcome Log conceptually distinct. Measure forward returns, MFE/MAE, stop/target outcomes, slippage/delay, and performance by asset/product type.

## Demo / pilot portfolio

Before live auto-trading, create an isolated paper/pilot portfolio. It must never mix with real broker accounts, balances, credentials, or positions, and all output must be labelled simulated.

Modes:

1. Shadow mode — order intent only.
2. Paper execution — simulate fill, slippage, fees, delay, sessions, and order lifecycle.
3. Auto-managed pilot — allow the policy engine to open/close/rebalance simulated positions, enforce risk limits, reconcile state, and emit audit events.

Use the pilot to test mapping, DR conversion, TFEX contract/risk logic, fund cut-off/NAV timing, stops, rebalancing, duplicate alerts/orders, stale data halts, reconciliation, and kill-switch behavior.

## Proposed delivery order

### Phase 0 — Product/domain foundation
- Lock terminology and boundaries for Stock, DR, TFEX, Fund, and Copilot.
- Define Market View to Action contracts and provenance.
- Define instrument master and underlying/benchmark mapping.
- Define recommendation, decision, paper portfolio, execution, and outcome schemas.

### Phase 1 — First vertical slice
- Alert Builder: horizontal line, OHLC magnet, timeframe, entry/stop/target, expiry.
- Basic instrument mapping.
- Recommendation log and outcome tracking.
- DR Follow proposal-only flow.
- English UI with source/freshness labels.

### Phase 2 — Pilot portfolio
- Paper ledger and deterministic paper execution.
- Asset-specific policies and auto-management.
- Dashboard comparing recommendations with simulated outcomes.
- Reconciliation, duplicate prevention, stale-data halt, and kill switch.

### Phase 3 — Market/product expansion
- US, HK, indexes, and Thai DR universe through Instrument Master.
- TFEX Trigger with shadow orders and InnovestX readback.
- Fund Plan with benchmark/NAV/cut-off and portfolio-aware proposals.
- Fundamental Snapshot, starting with authoritative Thai data and expanding by market.

### Phase 4 — Controlled real execution
- One-tap approval.
- Broker order status/fill reconciliation and idempotency.
- Strict symbol/contract whitelist, max loss, max exposure, and daily limits.
- Bounded automation only after pilot evidence is acceptable.

## Explicit non-goals for the first implementation

- No immediate live auto-trading.
- No full TradingView clone on day one; start with horizontal drawings and alerts.
- No LLM-generated free-form executable orders.
- No mixing private Portfolio Copilot data into public Signalix routing.
- No “buy” conclusion from an isolated fundamental score.
- No expansion to every market/broker before the shared data and audit contracts are proven.

## Success criteria

Signalix can show, for any proposal: what was observed, when it was observed, what instrument was selected and why, what policy bounded the action, what the user/system did, and what happened afterward. The pilot can run the same lifecycle without risking real capital.

## Detailed feature plan

### A. Alert Builder and chart interaction

Purpose: remove the daily manual work of drawing levels and creating TradingView alerts.

MVP features:
- chart with horizontal drawing objects;
- draggable handles with OHLC magnet/snap;
- timeframe selection;
- line types: entry, stop, target, support, resistance;
- trigger direction: cross above or cross below;
- alert expiry and notification cooldown;
- save, edit, disable, and audit alert rules;
- deep link from an alert to the chart and plan.

Later: trendlines, multi-point drawings, templates, and richer TradingView-like tools. Do not build a full charting clone before the basic alert lifecycle is reliable.

### B. Instrument Master and mapping

Create a canonical instrument registry for SET, TFEX, US, HK, indexes, DR, and funds. Each instrument needs symbol, venue, asset class, currency, timezone, trading session, data source, freshness policy, and active/inactive status.

Create explicit relationships:
- `UNDERLYING_OF` — DR or wrapper to parent stock;
- `TRACKS` — fund to benchmark/index/theme;
- `CONTRACT_FOR` — TFEX contract to underlying/index;
- `ALTERNATIVE_EXECUTION_FOR` — allowed execution instrument for a market view.

Mappings must be versioned and effective-dated. Invalid, changed, or ambiguous mappings block proposals rather than silently selecting an instrument.

### C. DR Follow

User flow:
1. User follows an underlying or selects a DR watch.
2. Underlying signal occurs.
3. Signalix resolves eligible DRs.
4. System checks ratio, FX, theoretical value, premium/discount, spread, liquidity, session, freshness, and corporate actions.
5. System creates a proposal with `READY`, `WAIT`, or a blocking reason.

MVP is proposal-only. Later execution must use a separate DR policy and broker adapter; a DR price-only trigger must never replace the underlying confirmation.

### D. TFEX Trigger

User flow:
1. User defines underlying, direction, contract family, and risk policy.
2. Underlying/index signal occurs.
3. System selects an eligible contract month.
4. Deterministic risk engine calculates quantity, margin, stop, maximum loss, and exposure.
5. System creates a shadow order and records the complete intent.
6. Only after pilot evidence: one-tap approval, broker readback, fill verification, and bounded automation.

Required controls: idempotency key, order-status check before retry, contract whitelist, market-session check, stale-data halt, daily-loss limit, max exposure, overnight policy, and global kill switch.

### E. Fund Plan

Fund flow is allocation-driven, not instant-price execution:
1. Index/group/theme regime changes.
2. System identifies mapped funds.
3. Eligibility filter checks benchmark, NAV freshness, cut-off, holidays, fee, hedge policy, tracking difference, minimum order, and dealing constraints.
4. Copilot compares the proposal with current allocation.
5. System proposes watch, DCA, buy, increase, reduce, or rebalance with a validity window.

MVP supports Fund Watch and Fund Proposal. DCA and rebalance come after paper portfolio support.

### F. Fundamental Snapshot

Start with authoritative Thai fundamentals, then add US/HK sources using a source adapter per market. Store period snapshots, source, reported date, currency, actual/estimate status, and freshness.

Initial fields: revenue, revenue growth, net income, EPS, EPS growth, margins, ROE, ROA, D/E, operating cash flow, free cash flow where available, P/E, P/BV, dividend yield, and market cap.

English UI cards:
- Technical View;
- Fundamental View;
- Combined Context;
- data source and `as of` date;
- unknown/not covered/stale states.

Ratios and scores are deterministic. LLM may explain trends or summarize filings but cannot invent missing values or turn a fundamental score into an executable order.

### G. Recommendation, decision, and outcome logging

Implement append-only event records with stable IDs and policy/data versions. Capture proposal evidence before the user responds. Keep system recommendation, user decision, paper execution, real execution, and realized outcome distinct.

Minimum event sequence:
`PROPOSED → ACCEPTED/REJECTED/IGNORED/EXPIRED → PAPER_EXECUTED/EXECUTED → OPEN → CLOSED/INVALIDATED → OUTCOME_RECORDED`.

Evaluation views should show counts and outcomes by product, underlying, instrument, signal type, policy version, and market. Include forward returns, MFE, MAE, stop/target hit, delay, slippage, and whether the user actually followed the proposal.

### H. Demo/Pilot Portfolio

Implement a separate portfolio namespace and ledger. It must not share real-account positions, balances, broker credentials, or execution endpoints.

Features:
- starting cash and account configuration;
- paper orders and deterministic fill simulator;
- configurable fee, slippage, latency, session, and partial-fill assumptions;
- positions, cash, exposure, margin, and P&L;
- auto-managed policies for open, close, stop, DCA, and rebalance;
- reconciliation and event audit;
- pause/kill switch;
- side-by-side recommendation versus outcome review.

Pilot exit gate before live integration:
- no duplicate or orphan orders in repeated/replayed events;
- stale and missing data halt actions;
- position/risk calculations reconcile;
- every action has provenance and an audit trail;
- kill switch is tested;
- representative DR, TFEX, fund, and technical/fundamental scenarios pass.

## Tomorrow's implementation starting point

Do not reopen product discovery. Start with these concrete artifacts:

1. Review the existing backend schema and choose migration strategy.
2. Write the domain contract for `instrument`, `mapping`, `market_view`, `recommendation`, `decision_event`, `paper_portfolio`, and `outcome`.
3. Build a minimal instrument/mapping seed for one Thai stock, one DR, one TFEX contract family, one index, and one fund benchmark.
4. Implement recommendation persistence before UI polish.
5. Add a small Alert Builder vertical slice: horizontal level, OHLC snap, trigger, expiry, notification, and log.
6. Add one DR proposal-only path using the seeded mapping and explicit blocking states.
7. Add fixture-based tests for stale data, invalid mapping, duplicate recommendation, expired proposal, and paper fill.

The first deliverable is not live trading. It is one auditable end-to-end path:

```text
underlying signal → mapped instrument → bounded proposal → logged decision → paper result → outcome
```

## Industry and group analysis

Industry analysis is a first-class layer, not only a display filter. It should answer:

1. Which groups are moving together?
2. Is the move broad or driven by one large constituent?
3. Which names are leaders, followers, laggards, or diverging?
4. Is leadership persistent, emerging, weakening, or rotating?
5. Which group-level view can drive a Stock Alert, DR Follow, TFEX Trigger, or Fund Plan?

### Two complementary group models

Use both models and show which one is being used:

- **Taxonomy group:** authoritative sector/industry classification from the exchange or a maintained instrument master. This is stable and explainable.
- **Behavioral cluster:** data-derived group of instruments that move or trend together over a defined lookback. This catches thematic relationships that formal taxonomy misses.

Do not silently replace the taxonomy with a correlation cluster. A stock may belong to one official industry and several temporary behavioral clusters.

### Group health metrics

For each group and time horizon, calculate deterministic metrics:

- equal-weight and market-cap-weight return;
- relative strength versus SET/index benchmark;
- member breadth: advancing, declining, above moving averages, in buy zone, and breaking out;
- median and dispersion of returns/RS;
- volume participation;
- leadership concentration and top-member contribution;
- persistence across 1W, 1M, 3M, and longer windows;
- rotation state: emerging, leading, weakening, or lagging;
- data coverage and freshness.

Equal-weight breadth is important for cases such as a semiconductor group where one very large name can hide weakness in the rest. A group with DELTA falling heavily, HANA moving sideways, and KCE strengthening should not be labelled simply “semiconductors strong”; it should be shown as **mixed/fragmented leadership**, with KCE as a possible individual leader rather than proof of group confirmation.

### Leader identification

Leader status should be a scored, explainable state—not just the biggest daily gainer. Candidate inputs include:

- relative strength within group and versus benchmark;
- trend-template quality and price structure;
- breakout/pullback quality;
- volume confirmation;
- persistence over multiple windows;
- liquidity and data quality;
- contribution to group breadth and return.

Suggested labels:

`GROUP_LEADER`, `EMERGING_LEADER`, `FOLLOWER`, `LAGGARD`, `DIVERGING`, `INVALIDATED`.

Group leadership must have a minimum participation threshold before it is used as confirmation. A single leader may create an individual Stock Alert, but should not automatically create a group-level buy or Fund Plan.

### Industry dashboard

The first UI should show a sortable group table and drill-down:

| Field | Example meaning |
|---|---|
| Group | Banks, Semiconductors, etc. |
| Group state | Leading / emerging / mixed / weakening / lagging |
| RS and returns | Relative performance by timeframe |
| Breadth | % members meeting selected technical condition |
| Leaders | Top explainable leaders |
| Divergence | Members moving against the group |
| Participation | Volume and breakout confirmation |
| Freshness | Latest covered trading date |

Drill-down should show leader/follower/laggard rows, group chart, breadth trend, and the exact rules behind the state. A group card should never hide its member dispersion.

### Examples of interpretation

- If KBANK and KTB continue higher after the broader bank group moved together, mark banks as a group with **persistent leaders**, then check whether other members confirm or whether leadership is narrowing.
- If DELTA drops sharply, HANA is flat, and KCE rises, mark semiconductors as **fragmented/mixed**, highlight KCE as an individual emerging or persistent leader, and avoid treating the whole industry as confirmed.
- If many members improve together while leaders are not yet extended, the group can create a group-level watch or Fund Plan candidate.

### Product integration

Industry/group context feeds all product surfaces but uses their own action policy:

- Stock Alert: group confirmation improves context for an individual setup.
- DR Follow: parent industry or theme can support the underlying signal, but the parent itself remains the trigger source.
- TFEX Trigger: group/index context is confirmation only; contract and risk rules remain separate.
- Fund Plan: group/benchmark regime can directly generate a fund watch, allocation, DCA, or rebalance proposal.
- Investment Copilot: group exposure and concentration can produce an attention item.

### Initial implementation scope

Start with official Thai industry groups and a small, auditable taxonomy. Add:

1. group membership and effective dates;
2. daily group aggregates;
3. breadth and dispersion metrics;
4. explainable leader ranking;
5. group state and rotation history;
6. industry dashboard and stock drill-down;
7. recommendation-log linkage from group observation to action proposal.

Behavior-based clustering can follow after the official-group version is stable and backtestable. All group signals must record membership version, lookback, benchmark, data date, and policy version.

## MiroFish as a UX/UI feedback and ideation tool

MiroFish should be evaluated as an external multi-agent scenario/feedback lab for Signalix—not as part of the deterministic trading engine and not as an authority on product requirements.

### Intended use

- Provide MiroFish with the Signalix product strategy, user personas, feature flows, screenshots/prototypes, and selected acceptance criteria.
- Ask simulated personas to review the UX/UI from different perspectives: technical trader, value investor, DR trader, TFEX trader, fund investor, beginner, and risk-conscious owner.
- Run scenario prompts such as first-time setup, interpreting a mixed industry group, following an underlying into a DR, reviewing a fund proposal, and inspecting a paper-portfolio outcome.
- Collect recurring confusion, missing information, terminology problems, trust concerns, and alternative workflow ideas.
- Convert useful findings into curated product-feedback entries or explicit decisions only after human review.

### Guardrails

- Treat MiroFish output as hypotheses and ideation, not user research evidence or market truth.
- Do not provide secrets, broker credentials, private portfolio data, raw account identifiers, or unnecessary personal information.
- Do not let simulated feedback override Signalix's deterministic calculations, risk controls, ownership boundaries, or English launch-ready UI requirement.
- Keep MiroFish experiments separate from production services and do not connect it to live execution or alert delivery.
- Label every finding with scenario, input version, simulated persona, date, and review status.

### Suggested feedback format

```text
finding_id
scenario
persona
surface: Stock Alert / DR Follow / TFEX Trigger / Fund Plan / Copilot
observed_confusion_or_idea
severity: friction / trust / comprehension / functional gap
evidence: screenshot, flow step, or prompt context
recommended_change
human_review: pending / accepted / rejected
```

### Pilot sequence

1. Start with a redacted product brief and one Signalix screen/flow.
2. Ask multiple personas to complete the same task independently.
3. Cluster repeated findings and separate persona-specific preferences from universal problems.
4. Have Arm/Bee/Ploy review the shortlist.
5. Test accepted changes with a real browser dogfood pass and record the result.

MiroFish is therefore a **scenario-based UX critic and idea generator** around Signalix. It complements, but does not replace, real user testing, deterministic system tests, or the final implementation review.
