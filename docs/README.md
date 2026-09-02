# Signalix Documentation Map

> **STATUS: CURRENT** · File-system organization map, not product authority.
> **Last organized:** 2026-09-02
> **First read:** [`START-HERE.md`](START-HERE.md)
> **Cleanup matrix:** [`current/2026-09-02-documentation-authority-matrix.md`](current/2026-09-02-documentation-authority-matrix.md)

## Layout

```text
docs/
├── README.md                              ← this map
├── Documentation-Cleanup-Review.html      ← visual inventory for review
├── current/
│   └── 2026-08-31-elliott-grill-decision-record.md ← consolidated grill + Opus record
├── superpowers/
│   ├── specs/
│   │   └── 2026-08-30-elliott-trend-trade-setup-design.md  ← active design
│   └── plans/        ← historical implementation evidence; not current task state
└── archive/
    ├── reviews/     ← historical review packets
    └── superpowers/ ← superseded plans/specs
```

## Current decision record

The historical review packet is now under `archive/reviews/2026-09-01-signalix-independent-review.md`. It is evidence only; new work starts from `START-HERE.md` and the relevant current authority.

## Authority routing

- Product/decision direction: `../vault/Product-Strategy-Market-to-Action.md` and the owner-approved Elliott design.
- Atomic decisions: `../vault/Decisions.md`.
- Acceptance/evidence: `../vault/Execution-Pipeline.md`.
- Architecture/runtime: `../vault/Architecture.md`, `../vault/Components.md`, `../vault/Deployment.md`.
- Vault governance/index: `../vault/Documentation-Governance.md`, `../vault/INDEX.md`.
- Historical implementation evidence: `archive/superpowers/` and `../vault/archive/`; never treat these as current direction.

## Protected from this organization pass

The following were deliberately untouched because they are owner changes, user research, runtime/generated data, or code:

- `../AGENTS.md` (owner-modified)
- `../CONTEXT.md`
- `../Trade Reference/`
- `../portfolio_monitor_log.txt`
- `../backend/` and live containers/artifacts
- ignored `.superpowers/sdd/` working evidence

## Current reconciliation — 2026-09-01

The semantic cleanup is complete for the canonical spine: T1–T9 Elliott/Trend/Trade-Setup is promoted, `/api/setup-candidates` is primary, and VCP documents are compatibility/audit history. Public 390px failure→Retry→recovery browser acceptance is PASS; broader desktop/drawer evidence and evaluator auto-caller remain separate. Do not use archived VCP notes or stale checklists as current direction.
