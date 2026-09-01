# Signalix Product Strategy — Market View to Action

> **STATUS: CURRENT** · Canonical product direction. `CANONICAL_FOR: thesis, target user, product surfaces, non-goals, roadmap boundary`.
> **Current stock-setup surface (2026-09-01):** Trend + Daily Elliott candidate + 60m Trade Setup is primary. T1–T9 source is promoted; public 390px failure→Retry→recovery browser acceptance is PASS, with evaluator auto-caller and broader acceptance separate. VCP is bonus/compatibility evidence only.
_Last updated: 2026-09-01; durable strategy retained below, with the current stock-setup replacement explicitly overriding older MVP surface sections._

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

Signalix is therefore a **scenario-based UX critic and idea generator** around Signalix. It complements, but does not replace, real user testing, deterministic system tests, or the final implementation review.

## 2026-08-22 — Decision-quality Setup Copilot (approved product direction)

> **SUPERSEDED IN PART (2026-08-23):** The product thesis, full-ORD preservation, deterministic gates, provenance, lifecycle, and explainable ranking remain current. The former default queue composition (`DEVELOPING` included) and regime-aware presentation/ranking are superseded by the owner-approved **Daily Shortlist + All Stocks Explorer** contract in section 11 and `docs/superpowers/specs/2026-08-23-daily-shortlist-explorer-design.md`: Daily Shortlist shows only `READY`/`PRE_READY`; regime is context only; Explorer owns broad research.

### Product thesis

Signalix's primary new product direction is a **decision-quality copilot for experienced, self-directed traders**. It is setup-first: the product helps a trader find and assess new technical setups, separating trend quality, setup maturity, entry readiness, and risk. It is not a beginner education product, a generic scanner, or a portfolio manager in the first phase.

```text
FULL ORD scan
→ Market-regime context
→ Setup queue
→ Entry readiness and risk review
→ Trader decision
→ Immutable outcome record
```

The scanner remains the deterministic engine/foundation. The user-facing product promise is not "find more tickers" but **reduce low-quality decisions and avoid chasing immature or structurally damaged setups**.

### Beachhead user and first surface

- Beachhead: experienced self-directed trader.
- Primary job: identify which new setups deserve review today and what condition must be confirmed before action.
- First surface: a daily, regime-aware **Setup Queue**.
- Portfolio management (`HOLD`, `ADD`, `TRIM`, `CUT`, `SELL`) is a later Portfolio Companion phase, not the setup queue's primary vocabulary.
- Beginner education and tutorial/quiz flows are explicit non-goals for this direction.

`shortlist` is a presentation/ranking layer only. It must never reduce the FULL ORD scan universe or silently remove symbols from backend coverage.

### Setup Queue contract

The queue is separated by current market regime:

```text
Current regime
├── SUPPORTIVE
├── NEUTRAL
└── DEFENSIVE
```

The landing view follows the current regime automatically. A Defensive regime emphasizes risk context before setups; other regimes lead with the setup queue. Other regime views remain accessible. Regime separation is presentation/context, not a hidden universe filter.

Within each regime, the queue contains only the focused setup states:

```text
CONFIRMED READY
PRE-READY
DEVELOPING
```

Other states such as `DO NOT CHASE` and `INVALIDATED` remain available in deep dive/history/audit views but do not compete for the primary queue's attention.

### Status engine and ranking

Status is produced by deterministic hard gates; an explainable score only ranks items that pass the relevant gate. A high score cannot override an unmet gate.

Hard-gate dimensions:

- trend quality;
- setup maturity/structure;
- entry condition;
- risk quality;
- data freshness and provenance.

Quality-first ranking weights for the focused queue:

```text
setup / structure  40%
entry proximity    30%
risk / reward      20%
market alignment   10%
```

The ranking must expose the component dimensions. It must not collapse into an opaque score that users cannot audit.

### Status meanings and lifecycle

- `DEVELOPING`: trend/setup is interesting but needs more structure.
- `PRE-READY`: setup is mature and near its trigger, but entry is not confirmed.
- `CONFIRMED READY`: entry condition and risk gate are confirmed; this means ready for trader review, not an automatic order.
- `BUY ZONE`: a setup/price area worth reviewing; not a personalized or automatic buy instruction.
- `WAIT FOR CONFIRMATION`: the missing trigger is explicit.
- `DO NOT CHASE`: extension, overhead supply, poor risk/reward, or other quality warning makes immediate pursuit unattractive.
- `INVALIDATED`: structural/risk/data conditions no longer support the setup.

Lifecycle is event-based rather than fixed-horizon:

```text
PUBLISHED → DEVELOPING → PRE-READY → CONFIRMED
                         └──────────→ INVALIDATED
```

A setup that remains unresolved receives a **time-decay ranking penalty** rather than automatic invalidation. This preserves legitimate base-building while preventing stale setups from dominating the queue.

### Decision card and deep dive

The front-door card is decision-first. In the first few seconds it shows:

- ticker and setup state;
- action label;
- why now / why not now;
- trigger or confirmation condition;
- stop/invalidation condition;
- short explanation.

Evidence is available through drill-down rather than hidden:

- candlestick chart and structural levels;
- Stage 1–4 and minor-trend state;
- MA/RS/VCP evidence;
- volume and liquidity context;
- extension and overhead-supply warnings;
- market regime;
- source, timestamp, freshness, and limitations.

Launch-ready UI copy remains English. Use process/setup labels for the setup surface: `BUY ZONE`, `WAIT FOR CONFIRMATION`, `DO NOT CHASE`, and `INVALIDATED`. Reserve portfolio labels such as `HOLD`, `ADD`, `TRIM`, `CUT`, and `SELL` for the later portfolio context.

### Immutable decision and outcome record

Record every system decision from day one. Do not infer a trade or user intent from passive behavior. Default telemetry may record setup opened, evidence expanded, chart/risk viewed, watchlist interaction, and return visits; it must not interpret an open as a buy or a non-click as a skip.

At publication, preserve:

- timestamp and data timestamp;
- market regime;
- setup state and ranking components;
- evidence and policy/version;
- displayed action, trigger, and invalidation;
- source/freshness/provenance.

Later append events for confirmation, invalidation, repair, expiry/decay, paper/live execution when explicitly available, and realized outcome. Do not rewrite the original recommendation after seeing the result.

Outcome evaluation is primarily **event-based**: confirmed, invalidated, repaired, or still developing. Fixed 5D/20D/60D horizons may be added as secondary analytics later, but must not replace lifecycle outcomes.

### North-star success measurement

Primary product success is **decision quality plus outcome**, not raw win rate. Track at least:

- setup confirmation quality;
- invalidation discipline;
- avoidance of chasing;
- outcome after confirmation/invalidation;
- evidence completeness and freshness;
- time from full scan to useful review.

Do not attribute market outcome to Signalix when the user did not act, and do not collapse system quality, user decision, execution, and market outcome into one number.

### Roadmap boundary

1. **Setup decision foundation:** preserve FULL ORD coverage, formalize regime/setup/entry/risk contracts, and ship the queue/card/deep-dive vertical slice.
2. **Evidence and lifecycle:** immutable setup observations, confirmation/invalidation events, time-decay ranking, and outcome views.
3. **Decision-quality analytics:** compare setup quality, entry readiness, risk gates, regime, and outcomes without hindsight rewriting.
4. **Portfolio Companion:** add position-aware `HOLD`/`ADD`/`TRIM`/`CUT`/`SELL`, paper execution, and portfolio heat only after the setup-first foundation is trustworthy.
5. **Research/content funnel:** publish selected confirmed setups as cited, visual research/education after the evidence and lifecycle contracts are stable.

### Explicit non-goals for this product direction

- No beginner-first curriculum, quiz, or tutorial product.
- No automatic buy/sell instruction from a score.
- No hidden price/volume/stale filter that reduces FULL ORD coverage.
- No portfolio action labels without portfolio context.
- No LLM ownership of indicator math, ranking, risk, or state transitions.
- No outcome claims without immutable timestamped evidence and clear user/execution attribution.

## 2026-08-22 — Cross-team review resolution (Ploy, Prae, View, Mali, Nida, Khim)

### Review status

The six independent reviews agree on the product direction but do not approve implementation readiness yet:

```text
product direction: PASS
strategy foundation: PASS
implementation readiness: REVISE
```

This section records review findings and proposed contract clarifications. It does not claim that the proposed contracts are implemented or verified.

### Cross-team consensus

The reviewers support:

- experienced self-directed trader as the beachhead;
- setup-first rather than beginner education, generic scanning, or portfolio management as the first product;
- deterministic gates before ranking;
- explicit separation of trend quality, setup maturity, entry readiness, risk, user decision, execution, and outcome;
- regime-aware presentation without silently reducing FULL ORD scan coverage;
- immutable, append-only outcome evidence and no hindsight rewriting;
- portfolio labels (`HOLD`, `ADD`, `TRIM`, `CUT`, `SELL`) postponed to a later Portfolio Companion.

### Required contract clarification before implementation

#### 1. Separate lifecycle state, action label, and portfolio action

The current strategy uses related terms that can be interpreted as the same thing. The implementation contract should separate them:

```text
Lifecycle state:
DEVELOPING
PRE-READY
STRUCTURE CONFIRMED
ENTRY CONFIRMED
INVALIDATED

Setup action/display label:
BUY ZONE
WAIT FOR CONFIRMATION
DO NOT CHASE
INVALIDATED

Portfolio action (later phase only):
HOLD
ADD
TRIM
CUT
SELL
```

`CONFIRMED READY` remains a product-facing concept only if its exact meaning is made explicit. It must not silently mean that a user should buy. `BUY ZONE` must display the trigger and disclaimer/context that it is a review area, not an automatic or personalized order instruction.

#### 2. Define an observable market-regime contract

`SUPPORTIVE`, `NEUTRAL`, and `DEFENSIVE` need deterministic, versioned criteria before they drive the landing experience. The contract should record:

```text
regime_state
benchmark/index inputs
breadth inputs
volatility inputs
leadership/participation inputs
reason_codes
policy_version
data_timestamp
```

Regime should influence presentation, ranking, warnings, and confirmation policy, but must not silently remove symbols from FULL ORD coverage. A Defensive regime may emphasize risk context and prevent an item from reaching `ENTRY CONFIRMED`; it must still preserve the underlying scan observation and audit trail.

#### 3. Define queue inclusion and exclusion explicitly

The focused queue may show `CONFIRMED READY`, `PRE-READY`, and `DEVELOPING`, while `DO NOT CHASE` and `INVALIDATED` remain available in history/deep dive/audit views. The contract must state:

- the exact hard gates required for each queue state;
- whether regime affects state or only ranking/context;
- why an item leaves the focused queue;
- how full-scan coverage is reconciled against presentation counts;
- how stale/error/provenance failures are shown.

A queue is a presentation and review surface, not a second hidden scan universe.

#### 4. Make ranking reproducible and inspectable

The quality-first weights remain the approved working hypothesis:

```text
setup / structure  40%
entry proximity    30%
risk / reward      20%
market alignment   10%
```

Before implementation, each component needs an observable value, unit/range, missing-data behavior, policy version, and persisted calculation snapshot. Ranking should be precomputed or pinned to a scan run, not silently recomputed differently on each API request. A displayed total must never hide the component scores or gate failures.

#### 5. Define event transitions and time decay

The event contract must distinguish structural progress from elapsed time:

```text
PUBLISHED → DEVELOPING → PRE-READY → STRUCTURE CONFIRMED → ENTRY CONFIRMED
                                      └──────────────────→ INVALIDATED
```

Time decay is a ranking penalty, not automatic invalidation. Its inputs should be observable and versioned, such as lack of structural improvement, weakening participation, changed distance to pivot, regime change, or degraded data freshness. Legitimate base-building must not disappear without a reason code.

### Current implementation gap reported by reviewers

Khim reported that the existing code has useful foundations for FULL ORD scanning, setup quality/proximity, snapshots, and append-only lifecycle patterns, but that the new regime states and `SUPPORTIVE`/`NEUTRAL`/`DEFENSIVE` computation are not yet implemented. View reported that the current dashboard still presents legacy `Action`/`Near Trigger`/`Forming`/`Extended` vocabulary rather than the new setup-maturity model. Nida reported that the strategy requirements remain NOT VERIFIED until source→DB→ranking→served UI evidence exists.

These are review inputs, not Bee's final acceptance claims. Bee must verify source code, DB contract, live API, served artifact, and real desktop/mobile journey before marking any item PASS.

### Proposed next review gate

Before creating implementation cards, revise and re-review this strategy section with:

1. regime formula and reason-code contract;
2. lifecycle/action vocabulary decision;
3. queue hard-gate and coverage reconciliation matrix;
4. ranking component and persistence contract;
5. event/time-decay schema and transition fixtures;
6. decision-card/UI contract aligned with the new vocabulary;
7. acceptance matrix for full coverage, stale/error states, immutability, LLM boundary, and served desktop/mobile behavior.

Only after this gate passes should the team create the first vertical slice:

```text
one scan run
→ one pinned regime snapshot
→ candidate queue
→ hard-gate trace
→ decision card
→ read-only evidence review
```

No live portfolio action or automatic trading is part of this first slice.

---

# Canonical Contract — Setup Copilot v0.2.0 (Bee takeover)

_Last updated: 2026-08-23 UTC. Contract owner: Lite/Bee. Source gate: parent Kanban task `t_7e1964f8`, review packet comment #222. This section is the normative contract for implementation and acceptance._

## 1. Explicit supersession of legacy definitions

This v0.2.0 section supersedes every earlier Setup Copilot definition in this file wherever wording conflicts. In particular:

- The legacy three-regime vocabulary `SUPPORTIVE / NEUTRAL / DEFENSIVE` is superseded by the four-state observable regime enum below: `HIGH_VOLATILITY / LOW_SPREAD / LIQUIDITY_EVENT / NORMAL`.
- `CONFIRMED READY` is not a lifecycle state. It is superseded by lifecycle `ENTRY CONFIRMED` and setup display label `BUY ZONE`.
- `READY`, `ACTION`, `NEAR TRIGGER`, `FORMING`, and `EXTENDED` are legacy display terms and MUST NOT be emitted by the canonical Setup Queue API/UI. They remain historical aliases only for migration/audit.
- `shortlist` and `queue` are presentation layers; neither may change FULL ORD scan coverage.
- Portfolio labels `HOLD / ADD / TRIM / CUT / SELL` remain out of scope for Setup Copilot and belong only to Portfolio Companion.
- Any implementation, fixture, or UI using a superseded term fails contract acceptance unless it is explicitly labelled `legacy_alias` in migration/audit data.

## 2. Normative vocabulary and boundaries

### 2.1 Lifecycle state

The lifecycle state describes deterministic structural progress:

`PUBLISHED → DEVELOPING → PRE-READY → STRUCTURE CONFIRMED → ENTRY CONFIRMED → INVALIDATED`

`INVALIDATED` is terminal for the current setup instance. A repaired/new setup receives a new immutable setup instance and does not rewrite the old one.

### 2.2 Setup action/display label

Allowed labels are exactly:

- `BUY ZONE`: review area; never a personalized or automatic order.
- `WAIT FOR CONFIRMATION`: required trigger is absent.
- `DO NOT CHASE`: extension, supply, poor risk/reward, or policy warning blocks pursuit.
- `INVALIDATED`: structural, risk, or data conditions no longer support review.

A label MUST show its trigger/confirmation condition, invalidation condition, timestamp, and provenance. No label is a portfolio instruction.

### 2.3 Portfolio action boundary

`HOLD / ADD / TRIM / CUT / SELL` MUST NOT be produced by Setup Copilot. They require Portfolio Companion context and a separate policy/version.

### 2.4 LLM boundary

Deterministic code owns scan coverage, regime, gates, state, ranking, risk, timestamps, and event transitions. LLM output may summarize already-structured fields only. LLM output MUST NOT create, alter, infer, or backfill a state, score, trigger, risk limit, user decision, or outcome.

## 3. Deterministic market regime contract

Policy version: `regime-v0.2.0`. All input values are from one pinned scan snapshot and use UTC timestamps. The regime is presentation/context and may change ranking, warning, and confirmation policy; it MUST NOT remove an instrument from FULL ORD coverage.

### 3.1 Required inputs

For each scan snapshot, persist:

`regime_state`, `benchmark_id`, `benchmark_return_20d`, `benchmark_at_or_above_ma50`, `breadth_pct_above_ma50`, `atr_pct_20d`, `median_spread_bps`, `liquidity_event_flag`, `liquidity_event_reason_codes`, `input_snapshot_id`, `policy_version`, `data_timestamp_utc`, `computed_at_utc`.

Missing input is represented as `NULL`, never as zero, empty string, `NaN`, `Infinity`, or a guessed value.

### 3.2 Formula and precedence

Let `V = atr_pct_20d`, `S = median_spread_bps`, `B = breadth_pct_above_ma50`, `M = benchmark_at_or_above_ma50`, and `L = liquidity_event_flag`.

- `HIGH_VOLATILITY` iff `V IS NOT NULL AND V >= 4.0`.
- Else `LIQUIDITY_EVENT` iff `L = true`.
- Else `LOW_SPREAD` iff `S IS NOT NULL AND S <= 25.0`.
- Else `NORMAL`.

Precedence is exactly `HIGH_VOLATILITY > LIQUIDITY_EVENT > LOW_SPREAD > NORMAL`. `B` and `M` are recorded context inputs and may affect hard confirmation policy, but never change the enum formula. If any required regime input is missing, retain `NORMAL` with reason code `REGIME_INPUT_MISSING`; do not infer volatility, spread, or liquidity.

Boundary behavior is deterministic: `V = 4.0` is HIGH_VOLATILITY; `S = 25.0` is LOW_SPREAD only when neither higher-precedence state applies; negative `V` or `S` is invalid input and yields `NORMAL` plus `INVALID_NEGATIVE_INPUT`; `NaN`, `Infinity`, malformed, or non-finite values yield `NORMAL` plus `INVALID_NONFINITE_INPUT`. Values outside provider-declared physical bounds are not clipped; they are invalid and retained in the provenance error list.

## 4. FULL ORD coverage and queue contract

Every active ORD instrument in the pinned instrument master MUST produce exactly one scan observation per scan run, including instruments with missing, stale, invalid, or error data. Required reconciliation invariant:

`full_ord_count = covered_count + missing_count + stale_count + error_count`

and every instrument ID MUST occur exactly once in those mutually exclusive buckets. A presentation queue is a ranked projection of observations, never a hidden backend filter.

### 4.1 Default hard gates

Default gate policy `setup-gates-v0.2.0`:

- `DEVELOPING`: trend quality passes; setup maturity may be incomplete; data provenance must be present and not hard-error.
- `PRE-READY`: trend quality and structure maturity pass; entry trigger not yet confirmed; fresh data required.
- `STRUCTURE CONFIRMED`: trend and structure pass; risk inputs present and valid; fresh data required.
- `ENTRY CONFIRMED`: all prior gates pass, entry condition is confirmed, risk/reward is valid, and no hard regime/data block applies.
- `INVALIDATED`: explicit structural/risk/data invalidation reason; never inferred from elapsed time alone.

Default hard blocks are `DATA_MISSING_REQUIRED`, `DATA_STALE`, `DATA_ERROR_PERMANENT`, `NEGATIVE_OR_NONFINITE_INPUT`, `INVALID_PROVENANCE`, `RISK_INPUT_MISSING`, `RISK_REWARD_BELOW_POLICY`, `REGIME_CONFIRMATION_BLOCK`, and `INSTRUMENT_INACTIVE`. A hard block prevents `ENTRY CONFIRMED`; it does not delete the scan observation.

Freshness defaults: `<=15 minutes` is fresh for intraday input, `>15 and <=60 minutes` is stale-warning, and `>60 minutes` is hard-stale. Daily inputs use the declared trading-date/session freshness policy and MUST include `data_timestamp_utc`. Transient provider errors retry at most 3 times with bounded backoff; permanent errors are surfaced for manual remediation. Nightly reconciliation compares source, DB snapshot, scan, ranking, API, and served artifact counts.

Focused queue default inclusion is `DEVELOPING`, `PRE-READY`, `STRUCTURE CONFIRMED`, and `ENTRY CONFIRMED` when their required gates pass. `DO NOT CHASE` and `INVALIDATED` remain queryable in deep dive/history/audit. Missing, stale, and error observations remain queryable with their blocking state and never silently appear as healthy candidates.

## 5. Reproducible ranking contract

Ranking policy `setup-ranking-v1.0.0` uses persisted component values and weights:

- setup/structure: `40%`
- entry proximity: `30%`
- risk/reward: `20%`
- market alignment: `10%`

Each component is stored with value, unit/range, missing-data status, reason codes, policy version, and scan snapshot ID. Components are normalized to `[0,1]`; values outside the declared range are invalid, not clipped. A hard-gated item is excluded from focused ranking with an explicit exclusion reason; its observation remains in coverage reconciliation.

Missing-data rules: a missing component is `NULL`, never zero. If a required hard-gate component is missing, the item cannot reach `ENTRY CONFIRMED`. If an optional ranking component is missing, the total is `NULL` and the item is ranked after complete-value items using deterministic tie-breakers `(complete_component_count DESC, lifecycle_state_order DESC, instrument_id ASC)`. No imputation, LLM completion, or request-time recalculation is allowed. Persist `total_score`, component snapshot, weights, policy version, and rank at scan time.

## 6. Append-only event and time-decay contract

Event policy `lifecycle-events-v0.2.0`. Events have immutable `event_id`, `setup_instance_id`, `instrument_id`, `event_type`, `from_state`, `to_state`, `action_label`, `reason_codes`, `source_snapshot_id`, `policy_version`, `occurred_at_utc`, `recorded_at_utc`, `idempotency_key`, and payload hash.

Allowed event types are `PUBLISHED`, `STATE_TRANSITION`, `ACTION_LABEL_CHANGED`, `REGIME_SNAPSHOT`, `RANKING_SNAPSHOT`, `HARD_GATE_BLOCKED`, `HARD_GATE_CLEARED`, `INVALIDATED`, and `OUTCOME_RECORDED`. Events are insert-only: no UPDATE/DELETE, and corrections are compensating events linked by `corrects_event_id` with a new event ID.

Idempotency: same `idempotency_key` plus same payload hash is a no-op returning the original event ID; same key with a different hash is rejected as `IDEMPOTENCY_CONFLICT`. Ordering is by `(occurred_at_utc, event_id)`; late events are retained and flagged `LATE_ARRIVAL`, never silently reordered or dropped. Duplicate identical events are not added twice. Corrections never mutate the original event.

All timestamps MUST be ISO-8601 UTC with `Z` suffix. Naive timestamps, local timezone timestamps, malformed timestamps, `NULL` event time, and non-finite numeric payloads are rejected. Negative elapsed durations or negative price/volume/risk values are rejected with explicit validation errors; legitimate signed returns may be negative only in fields whose schema declares signed semantics.

Time decay is a ranking penalty only. With `lambda = 0.05`, `decay_factor = exp(-lambda * elapsed_days)` where `elapsed_days >= 0` is computed from the last qualifying structural/participation/regime/freshness observation. Decay never auto-invalidates a setup. A decay reason code and source timestamps are required; legitimate base-building remains visible with its penalty.

## 7. Valid and invalid fixtures

### Valid fixtures

- `FX-REGIME-001`: `atr_pct_20d=4.0`, finite spread, no liquidity event → `HIGH_VOLATILITY`.
- `FX-REGIME-002`: volatility below 4, `liquidity_event_flag=true` → `LIQUIDITY_EVENT`.
- `FX-REGIME-003`: volatility below 4, no liquidity event, spread exactly 25 → `LOW_SPREAD`.
- `FX-REGIME-004`: all valid, volatility below 4, spread above 25 → `NORMAL`.
- `FX-COVERAGE-001`: 100 active ORD instruments split into covered/missing/stale/error buckets summing to 100, each ID once.
- `FX-RANK-001`: all four components present; persisted total equals `0.40*S + 0.30*E + 0.20*R + 0.10*M` under `setup-ranking-v1.0.0`.
- `FX-EVENT-001`: replaying an identical event returns the original ID and creates no second row.
- `FX-EVENT-002`: a correction creates a new compensating event and leaves the original byte-for-byte unchanged.

### Invalid fixtures

- `FX-REGIME-101`: `atr_pct_20d=NaN` → `NORMAL`, `INVALID_NONFINITE_INPUT`.
- `FX-REGIME-102`: negative spread → invalid input, no LOW_SPREAD classification.
- `FX-REGIME-103`: missing volatility → `NORMAL`, `REGIME_INPUT_MISSING`, never guessed.
- `FX-RANK-101`: missing required risk component → cannot reach `ENTRY CONFIRMED`.
- `FX-RANK-102`: negative/non-finite component → hard validation failure, no clipping.
- `FX-EVENT-101`: same idempotency key with changed payload → reject `IDEMPOTENCY_CONFLICT`.
- `FX-EVENT-102`: local/naive timestamp or negative elapsed duration → reject.
- `FX-COVERAGE-101`: duplicate instrument or hidden filter → reconciliation FAIL.

## 8. Acceptance matrix

| ID | Boundary | Required evidence | Verdict condition |
|---|---|---|---|
| AC-REG-001 | source→DB→regime | pinned inputs, formula, reason codes, UTC | reproducible exact enum |
| AC-REG-002 | regime→scan | all active ORD IDs retained | no silent coverage loss |
| AC-QUEUE-001 | scan→queue | inclusion/exclusion and hard-gate trace | every omission explained |
| AC-QUEUE-002 | stale/error/empty | API/UI fixtures | safe state, no false readiness |
| AC-RANK-001 | ranking | component snapshot + v1.0.0 weights | replay gives same ranks |
| AC-RANK-002 | missing/invalid | NULL/NaN/negative fixtures | no imputation or clipping |
| AC-EVENT-001 | lifecycle | transition fixture/event log | append-only and immutable |
| AC-EVENT-002 | replay/correction | duplicate/order/correction readback | idempotent, ordered, compensating |
| AC-DATA-001 | source→DB | provenance/freshness reconciliation | counts and timestamps reconcile |
| AC-API-001 | DB→API | schema and error responses | fields/blocks preserved |
| AC-UI-001 | API→served UI desktop | real 1280px journey | English labels and evidence visible |
| AC-UI-002 | API→served UI mobile | real 512px journey | no horizontal scroll, usable cards |
| AC-UI-003 | empty/error/stale UI | rendered failure states | no misleading action label |
| AC-LLM-001 | structured output→summary | boundary test | LLM cannot mutate deterministic fields |
| AC-IMM-001 | recommendation→outcome | original row/event readback | no hindsight rewrite |

Acceptance status at contract handoff: `NOT VERIFIED` for live source, DB, API, served artifact, and rendered desktop/mobile journey. This contract gate approves the specification only; implementation cards remain blocked until their own evidence satisfies the matrix.

## 9. Signed review findings and open decisions

Review packet recorded in parent gate comment #222, dated 2026-08-22 UTC. The following are signed role inputs to v0.2.0; Lite/Bee is the final decision owner:

- **Ploy — trader/product challenge — signed 2026-08-22 UTC:** setup-first queue is decision-useful only with explicit trigger, invalidation, anti-chase label, and no automatic-buy implication. Accepted in v0.2.0.
- **Khim — implementation feasibility — signed 2026-08-22 UTC:** FULL ORD scan/snapshot foundations are reusable; regime, ranking persistence, and event contracts require explicit versioned fields. Accepted with implementation readiness still evidence-gated.
- **View — UI/UX — signed 2026-08-22 UTC:** queue/card hierarchy must use canonical lifecycle/setup vocabulary, expose trigger/risk/freshness, and work at 1280px and 512px without horizontal scroll. Accepted as AC-UI-001/002.
- **Mali — retail comprehension — signed 2026-08-22 UTC:** labels must not imply an order; missing/stale/error states must be plain and visible; passive viewing is not a decision. Accepted as AC-QUEUE-002 and AC-IMM-001.
- **Nida — QA/evidence — signed 2026-08-22 UTC:** readiness remains NOT VERIFIED until source→DB→ranking→API→served UI and lifecycle evidence reconcile. Accepted as the explicit status above.

Resolved decisions: `OD-1` regime formula and precedence; `OD-2` lifecycle/setup/portfolio vocabulary separation; `OD-3` queue hard gates and FULL ORD reconciliation; `OD-4` 40/30/20/10 ranking persistence and missing-data behavior; `OD-5` append-only event/idempotency/order/correction semantics and decay; `OD-6` decision-card/UI and acceptance matrix boundaries. No unresolved decision is silently treated as approved.

## 10. Gate verdict and downstream boundary

Product direction: `PASS`.
Strategy foundation: `PASS`.
Implementation readiness: `REVISE` / `NOT VERIFIED` pending evidence matrix execution.
Canonical contract gate: `PASS` for specification takeover by Lite/Bee.

Dependent Action Queue, Outcome Log, and UI redesign cards MUST remain blocked until this canonical file is read back and this gate is explicitly accepted. No production implementation, live portfolio action, or automatic trading is authorized by this contract alone.

## 11. 2026-08-23 — Owner-approved Daily Shortlist reset

> **STATUS: SUPERSEDED 2026-08-26** — The historical Daily Shortlist reset remains preserved for audit, but VCP Finder · 60m is now the owner-approved MVP core. See section 12.

Owner approved a product reset to a **Daily Shortlist** as Signalix's default decision surface and retained the existing stage-first dashboard as a secondary **All Stocks Explorer**. The approved design is `docs/superpowers/specs/2026-08-23-daily-shortlist-explorer-design.md`.

- Daily Shortlist serves Thai Daily-chart swing trades held for several days to several weeks.
- It publishes only `READY` and `PRE_READY` candidates; `DEVELOPING`, base-building, invalidated, broken, low-liquidity, and `DO NOT CHASE` names are excluded from this surface.
- FULL active ORD coverage remains the scan/data foundation. A 20-day average daily traded-value gate of **THB 10,000,000** determines Daily Shortlist eligibility only; it must not delete or hide symbols from the full scan or Explorer.
- Ranking is deterministic and explainable: structure 40%, entry readiness 30%, risk/reward 20%, with liquidity as a hard gate and tie-breaker. Market regime remains visible context only and does not alter eligibility or rank.
- All Stocks Explorer is research-only, remains secondary navigation, and must clearly state that its full-universe results are not trade suggestions.
- Strong price/volume moves that fail actionability remain visible in separate context lanes: `RISING MOVERS / WATCH ONLY` for S1/S2 evidence and `CAUTION / DO NOT CHASE` for S3/S4/topping/extended evidence. These lanes never receive shortlist rank or entry permission.
- Explorer Stage/Search filters apply immediately. Detail charts use real stored-data `1D`, `1W`, and `60M` views; timeframe/layer controls stay below the plot.

## 12. 2026-09-01 — Current stock-setup replacement (authoritative)

> **STATUS: CURRENT OVERRIDE** · This section reconciles the older strategy layers above with the owner-approved release direction.

For Thai stock setup discovery, the current primary surface is **Daily Trend/Strength + Elliott candidate → 60m Trade Setup → Arm review**, served by `/api/setup-candidates` and `/mvp`. T1–T9 source is promoted; runtime/API verification is partial; public desktop/mobile/error acceptance remains open. `marginable_long` is 237 eligible symbols, while 931 active ORD is audit/rollback coverage. VCP is bonus/compatibility evidence, not the primary candidate gate. Alerts, auto-trading, and broker execution remain off.

Sections describing Daily Shortlist, All Stocks Explorer, or VCP-first serving are preserved historical transition context and are superseded where they conflict with this override.
