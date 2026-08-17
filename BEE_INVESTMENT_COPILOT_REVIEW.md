# Bee Review — Investment Co-pilot P0 Monitor/Inspect

**Date:** 2026-08-12  
**Reviewer:** Bee/lite — final quality gate  
**Inputs reviewed:**
- `/root/signalix/INVESTMENT_COPILOT_DESIGN_BRIEF.md` from Ploy
- `/root/signalix/backend/portfolio.py`
- `/root/signalix/backend/app.py`
- `/root/signalix/backend/portfolio.html`
- Live API/UI checks
- Mali tester feedback

---

## Executive Summary

Ploy's new idea is directionally correct: Investment Co-pilot should stop being a “portfolio dashboard” and become a **private Monitor / Inspect operating view**.

The next feature should be:

> **Account Health + Reconciliation Engine**  
> Answer “what needs action now?” from source truth, not from decorative wealth summaries.

This aligns with the architecture boundary: Portfolio Copilot stays private/owner-only, may consume Signalix market data read-only, and must never expose holdings/cost basis/broker data to Signalix public SaaS or signal routing.

---

## Current verified state

Verified by Bee:

- Backend health OK.
- `/portfolio` serves successfully.
- `/portfolio?v=2` route fixed and serves successfully.
- `GET /portfolio/me` with owner token returns:
  - `accounts = 6`
  - `holdings = 33`
  - state = `observe_only_screenshot_mvp`
- DB currently has:
  - `portfolio_transactions = 15`
  - `portfolio_holding_items = 33`
- Unit tests pass:
  - `5 tests OK`
  - Includes owner token / bound chat-id auth test.

Current accounts:
- `krungsri_equity_main` — parsed document account
- `innovestx_tfex_main` — parsed document account
- `krungsri_equity_screenshot` — screenshot observation
- `innovestx_derivatives_screenshot` — screenshot observation
- `webull_us_screenshot` — screenshot observation
- `dime_us_screenshot` — screenshot observation

---

## Bee’s answer to Ploy’s review questions

### 1. Is the position/reconciliation boundary safe enough?

**Conceptually yes, implementation not yet.**

The design correctly separates:

| Source | Use |
|---|---|
| Broker PDF / confirmation | ledger evidence |
| Statement / broker snapshot | account-state evidence |
| Screenshot | observation only |
| Signalix market data | read-only market context |

But the current implementation still has separate `*_main` and `*_screenshot` accounts with no account-linking model. This means the UI can show both as separate accounts even though they may represent the same real-world broker account.

**Required before P0 is trustworthy:**
- Add owner-confirmed display-account linking.
- Never auto-merge by broker name.
- Add reconciliation state per display account.
- Label screenshots as observation/needs review everywhere.

### 2. What must be added to the normalized account-health API?

Current `/portfolio/me` is too raw. Add a separate endpoint:

`GET /portfolio/health?chat_id=...`

Recommended response shape:

```json
{
  "state": "monitor_p0",
  "generated_at": "...",
  "accounts": [
    {
      "display_account_id": "...",
      "display_name": "Krungsri Thai Equity",
      "broker": "krungsri",
      "asset_type": "thai_equity",
      "freshness": {
        "latest_source_type": "screenshot|document|statement",
        "latest_source_ref": "...",
        "as_of": "...",
        "status": "fresh|stale|unknown"
      },
      "reconciliation_state": "unlinked|snapshot_only|awaiting_statement|reconciled|mismatch|incomplete",
      "holdings": [],
      "risk_inputs": {
        "coverage": "not_ready|partial|ready",
        "missing": ["cost_basis", "stop_plan", "fx_timestamp"]
      },
      "data_limitations": []
    }
  ],
  "attention": []
}
```

Key rule: return `unknown`, `not_covered`, or `incomplete`; never return zero for unknown values.

### 3. Which P0 edge cases can mislead holdings/risk?

Top risks:

1. **Partial transaction history**  
   If old buys/sells are missing, calculated open quantity and average cost will be wrong.

2. **Screenshot ≠ ledger**  
   A screenshot can show current holdings but cannot prove transaction history, cost-basis method, or realized P&L.

3. **Duplicate real-world accounts**  
   `krungsri_equity_main` and `krungsri_equity_screenshot` may represent the same real account but are currently separate rows.

4. **TFEX contract multiplier**  
   Current screenshot seed uses `quantity × quote` style market values in some places. TFEX risk must not infer exposure unless multiplier/margin contract specs are encoded.

5. **Cross-currency wealth**  
   Dime/Webull USD holdings must not be merged into THB total without FX source + timestamp.

6. **Signalix coverage mismatch**  
   Signalix SET screening should not be applied to US ETFs, Dime/Webull, funds, or TFEX contracts unless a specific adapter exists.

---

## Mali tester feedback distilled

Mali likes the shift from “dashboard” to “what needs action now” because it feels more useful and trustworthy.

Mali’s main confusion:
- “Monitor” vs “Inspect” needs clearer wording.
- `reconciliation_state` is too technical for beginner UI.
- `freshness` needs human-readable labels.
- Risk inputs should explain what is missing rather than hide or fake output.

Mobile UX must show first:
- account status
- latest source timestamp
- data completeness / mismatch
- tap-to-inspect action
- clear stale/offline state

Mali would trust it only if:
- it says exactly what data is incomplete
- it avoids fake total wealth
- risk numbers explain source/assumption
- actions are follow-up-able, not just alerts

---

## Bee’s recommended next iteration

### P0.1 — Account Health API
Build normalized account-health endpoint from existing tables.

Deliverables:
- display account grouping model
- source freshness per account
- reconciliation state
- data limitations
- attention list derived from account state

### P0.2 — Monitor-first UI
Replace dashboard-ish metrics with truth-first cards:

Top of page:
1. Attention Now
2. Account Health Strip
3. Reconciliation Queue
4. Inspect Drawer

Avoid:
- fake portfolio value
- fake day P&L
- fake risk score
- cross-currency totals

### P0.3 — Thai equity position engine
For Krungsri confirmed transactions:
- ordered transaction ledger
- deterministic open quantity
- weighted average cost
- realized P&L only when evidence complete
- mark incomplete when history is partial

### P0.4 — TFEX monitor mode
For InnovestX:
- use screenshot/statement as authoritative state snapshot
- show contracts, side, source timestamp, margin fields
- do not infer full exposure until multiplier and contract policy are encoded

### P0.5 — Tests / UAT evidence
Must-have tests:
- owner token + wrong chat ID rejected
- screenshot import remains observation-only
- duplicate source hash ignored
- account health returns `unknown`, not zero
- UI renders 33 holdings / 6 accounts from live API
- browser/user-facing check before “ready”

---

## Feature idea verdict

Ploy’s idea is good and should be accepted, but scoped tightly:

**Accepted feature name:** Account Health + Reconciliation Monitor  
**Product surface:** Monitor / Inspect  
**Primary goal:** show what needs action from verified source state  
**Non-goal:** wealth dashboard / auto-trading / fake risk analytics

This is the correct bridge from current MVP to a real Investment Co-pilot.

---

## Bee final gate recommendation

Proceed with P0.1 first:

1. Add normalized `/portfolio/health` API.
2. Add display-account linking model.
3. Add reconciliation states.
4. Update `/portfolio` to show Attention + Account Health, not fake top metrics.
5. Keep screenshot holdings visible but labelled `observation / needs review`.

Do **not** start auto-trading, more broker ingestion, or total wealth aggregation until account-health and reconciliation are trustworthy.
