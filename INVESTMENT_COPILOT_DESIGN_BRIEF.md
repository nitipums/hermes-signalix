# Investment Co-pilot — Design & Engine Brief

**Status:** owner-only MVP review, 12 Aug 2026  
**Audience:** Arm, Ploy, Bee, Mali  
**Surface:** **Monitor** first; the user is watching portfolio state and must act only on material exceptions. It is not a marketing page and not merely a wealth-allocation dashboard.

## One-line product definition

**Investment Co-pilot turns broker-confirmed transactions and explicitly labelled portfolio snapshots into an account-aware, asset-specific “what needs action now?” operating view.**

It sits inside Signalix as a private owner-beta module and may consume Signalix market intelligence read-only. It does not share portfolio data with Signalix’s public signal SaaS.

---

## Evidence: what exists and runs now

### Working backend / data

- Signalix backend health endpoint returns `200 {status: ok}`.
- Owner-gated endpoints exist:
  - `POST /portfolio/documents`: parses InnovestX derivatives and Krungsri equity PDFs in memory.
  - `POST /portfolio/snapshots`: imports reviewed manual/screenshot observations.
  - `GET /portfolio/me`: returns account summaries plus latest screenshot holdings.
- Owner auth requires both private token and `owner` tier. Public tier escalation was fixed and returns 403.
- Document idempotency, atomic persistence, size/page/text limits, and trade-ID validation are implemented.
- Two parsed ledger sources are present: InnovestX TFEX (8 transactions) and Krungsri equity (7 transactions).
- Four screenshot observation accounts were seeded: Krungsri Thai equities, InnovestX derivatives, Webull US, and Dime US.
- A private static cockpit is served at `/portfolio` and requires the owner token in-browser.

### Critical distinction in the data

| Source | Meaning | Trust for transactions | Trust for current holdings |
|---|---|---:|---:|
| Broker confirmation PDF | Formal execution evidence | High | Partial; may be historical |
| Broker daily statement | Broker account snapshot | High | High at statement timestamp |
| Screenshot | User-reviewed observation | No ledger authority | Medium, timestamped observation only |
| Signalix chart/screen | Market context / price trend | N/A | Market signal only |

No source may silently overwrite another. Reconciliation must show disagreement rather than “fix” it automatically.

---

## Why the current experience feels like “nothing”

The user observation is correct. The current MVP is **ingestion proof + static shell**, not an Investment Co-pilot decision engine yet.

1. **The UI hides its best data.** `/portfolio/me` returns screenshot holdings and per-account totals, but `portfolio.html` renders only account aliases, transaction counts, and latest trade date. It does not render holdings, asset types, allocation, source timestamps, snapshot totals, or account drill-down.
2. **Top metrics are placeholders.** “Portfolio value,” “Day P&L,” “cash/margin buffer,” and “reconciliation” show setup/draft labels rather than deterministic portfolio values.
3. **Attention cards are generic rules, not facts from holdings.** They say “margin policy required” or “execution locked,” but do not name a position, a current figure, a threshold, or a proposed action.
4. **There are two parallel representations with no reconciliation.** Broker-PDF accounts (`*_main`) and screenshot accounts (`*_screenshot`) represent the same real-world brokers but are not linked as one account/portfolio source chain. So parsed transactions do not form the displayed positions.
5. **No position/lot engine exists.** Transactions have not been transformed into open quantities, average costs, realized P&L, or close/open state. Screenshot positions are not reconciled with those calculations.
6. **No market-intelligence join is implemented.** Signalix has `/chart/{symbol}` and `/screen/{symbol}`, but Co-pilot does not join holdings to those outputs or label staleness/coverage. US, fund, and TFEX contract coverage need separate adapters rather than pretending all are SET equities.
7. **No explicit account hierarchy is exposed.** The concept needs account → asset type → holding → monitoring policy; the existing UI stops at account metadata.

Conclusion: **do not add more parser sources or auto-trading next. First make one verified account observable and decision-capable end-to-end.**

---

## P0: the thin vertical slice to build next

### Chosen proof path

Start with **InnovestX TFEX** and **Krungsri Thai equity** because both have real parsed documents, but keep them as distinct account types.

### Desired user journey

1. Arm opens `/portfolio` and authenticates as owner.
2. The home screen immediately answers **“What needs action now?”** using real evidence.
3. Arm selects an account and sees its latest broker source, freshness, and holdings.
4. Arm can compare:
   - calculated position from broker transactions;
   - latest broker/screenshot holding snapshot;
   - Signalix market trend context where coverage exists.
5. Any mismatch is clearly `NEEDS REVIEW`, not hidden.
6. No order can be submitted. No fake value/P&L is shown.

### P0 backend deliverables

1. **Account identity / source linking**
   - Add a private account profile that can link `*_main` document data and `*_screenshot` observation data to one display account only after owner confirmation.
   - Never merge sources merely by broker name.

2. **Position calculation engine — Thai equities first**
   - Deterministically derive quantity, weighted average cost, realized P&L, and open/closed state from ordered confirmed transactions.
   - Document and test the cost-basis method.
   - Show date range and evidence count; show `incomplete` when confirmation history is partial.

3. **TFEX snapshot monitor — do not infer lots yet**
   - Use latest broker statement/screenshot as the authoritative position/margin view at timestamp.
   - Display contracts, side, margin fields, excess/insufficient status, and source freshness.
   - Do not calculate market value as `contract quantity × quote` unless the contract multiplier is known and encoded.

4. **Normalized account health response**
   - Add a backend response shape separate from raw ingestion records:
     `account → freshness → reconciliation_state → holdings[] → risk_inputs → data_limitations[]`.
   - Return `unknown`/`not covered` rather than zero.

5. **Asset-specific policy contract (configuration only, no auto-execution)**
   - Thai equity: Signalix trend/template only when symbol coverage is verified; a position needs an explicit stop/thesis plan before stop-distance alerting.
   - TFEX: margin buffer, max contracts, loss/day, and overnight policy fields must be defined before any action card.
   - US equity/ETF: price + FX + US-session freshness policy, no Signalix SET screen assumption.
   - Funds: official NAV / cutoff + underlying proxy policy, not intraday NAV fabrication.

### P0 UI deliverables

**Surface:** Monitor with a secondary Inspect drill-down. Dense, sober, no hero and no fake metrics.

1. **Attention rail (top, max 5)**
   - Each card must say: account + holding, observation timestamp, triggered rule, real input, threshold, proposed human action, and reason for any block.
   - Empty state: “No actionable event from verified data” — not “all good.”

2. **Accounts strip**
   - One card per real display account, showing asset type, broker, source freshness, verification/reconciliation state, and known vs unknown fields.

3. **Account drill-down**
   - Holdings table grouped by asset type.
   - Columns vary by asset type instead of forcing a generic table.
   - Thai equity: position / avg cost / reference price / Signalix trend coverage / plan status.
   - TFEX: long/short contracts / source timestamp / margin buffer / settlement reference / risk-policy status.

4. **Evidence drawer**
   - “Why this?” expands source type, source timestamp, parser/snapshot status, and data limitations without showing raw account numbers or documents.

5. **Source status, never fake total wealth**
   - Cross-currency aggregation and total portfolio value remain unavailable until FX timestamp/method and source coverage are explicit.

---

## P1 after the vertical slice proves useful

- Attach additional Webull, Dime, and fund import sources.
- Email inbox ingestion with sender whitelist and attachment dedupe.
- Signalix read-only market-data adapter with explicit coverage/staleness per holding.
- Deterministic policy evaluator and alert state machine/deduplication.
- Daily reconcile job and owner review queue.
- Shadow order intents only after state/reconciliation evidence is stable.

## Explicit non-goals now

- Auto-trading, broker order submission, or browser-click execution.
- LLM-calculated P&L/position size/stop/margin decisions.
- Showing a glamorous total wealth number from mixed timestamps/currencies.
- Treating screenshot snapshots as broker-confirmed ledger records.
- Making this visible to Signalix public users or mixing portfolio data into public signal routing.

---

## Design direction requested from Mali

Please critique and propose a production-quality **Monitor / Inspect** flow for the P0 scope only.

- Prioritize truthfulness, data lineage, calm attention hierarchy, mobile usability, and easy scanning during market hours.
- Use an original finance-operations visual language; do not clone WiseT/My Wealth screens.
- Avoid generic dashboard decoration, gradients, fake metrics, equal-weight card grids, and trend charts that do not cause a decision.
- Provide: information architecture, primary/empty/error states, component hierarchy, data labels, and interaction notes.
- Call out data states: `broker-confirmed`, `observation`, `reconciled`, `needs review`, `stale`, `not covered`.

## Review questions for Bee

1. Is the position/reconciliation boundary above sufficiently safe for mixed documents and screenshots?
2. What must be added to the normalized account-health API before UI implementation?
3. Which P0 edge cases can create misleading holdings or risk signals?
