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

- VCP Finder is the current primary surface and supports multi-select initial-margin rates with Select all/Clear/Apply; checkbox changes do not refresh until Apply.
- Daily Shortlist is removed from visible MVP navigation; Explorer remains secondary research/audit.
- VCP cards/tables show only a compact `%Margin X%` tag when the symbol is in the current list.
- Drawer shows only the compact `Marginable: X%` field when present; missing margin data has no placeholder/tag.
- Marginability is presentation/filter metadata only. It does not remove symbols from canonical scan history or mutate Daily state.
- Symbols outside the list remain visible in full-universe views without a fabricated margin status.

## Refresh policy

Arm expects a monthly refresh check. The issuer PDF note says the permitted buy/short list is reviewed quarterly, so each new owner-provided PDF is authoritative for its own effective date and must replace the dataset only after parsing/count/duplicate checks and focused API/UI verification.

Never infer a new rate from an old file, silently carry forward a missing symbol, or store the PDF's credentials/content in Git, memory, or vault. Keep the source filename/effective date and generated dataset hash in the delivery evidence.
