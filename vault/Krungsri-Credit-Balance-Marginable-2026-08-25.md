# Krungsri Credit Balance Marginable List — 2026-08-25

> **STATUS: CURRENT** · `CANONICAL_FOR: owner-selected marginable filter metadata`

## Source

- Source: Krungsri Securities Credit Balance Marginable Securities List PDF supplied by Arm
- Document: `Marginable_Securities_List_25082026_1787658633_copy.pdf`
- Effective date: **2026-08-25** (25 August 2569)
- Dataset: `/root/signalix/backend/marginable_securities.json`
- Schema: `signalix.marginable.v1`

## Coverage

- 353 securities in the PDF
- 323 ORD symbols used by the Signalix Thai equity universe
- 30 DR symbols retained as typed source records
- Initial margin rates: 50%, 60%, 70%, 80%, 100%
- `*`, `**`, and `***` permissions are preserved; no marker means buy/collateral permitted but short is not permitted according to the PDF notes.

## Product behavior

- Both Daily Shortlist and All Stocks Explorer default to `Krungsri · default`.
- Filter options: Krungsri list, All stocks, Not on Krungsri list.
- Cards show `Krungsri X%` when the symbol is in the current list.
- Drawer shows rate, effective date, and permissions: Buy / Collateral / Short.
- Marginability is presentation/filter metadata only. It does not remove symbols from canonical scan history or mutate Daily state.
- Symbols outside the list remain visible only when Arm selects `All stocks`; their margin fields are `NOT_VERIFIED`.

## Refresh policy

Arm expects a monthly refresh check. The issuer PDF note says the permitted buy/short list is reviewed quarterly, so each new owner-provided PDF is authoritative for its own effective date and must replace the dataset only after parsing/count/duplicate checks and focused API/UI verification.

Never infer a new rate from an old file, silently carry forward a missing symbol, or store the PDF's credentials/content in Git, memory, or vault. Keep the source filename/effective date and generated dataset hash in the delivery evidence.
