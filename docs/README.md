# Signalix Documentation Map

> **STATUS: CURRENT** · File-system organization map, not product authority.
> **Last organized:** 2026-08-31

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
│   └── plans/
│       └── 2026-08-30-elliott-trend-trade-setup.md         ← active implementation plan
└── archive/superpowers/
    ├── specs/   ← prior designs; preserved, not current authority
    ├── plans/   ← prior implementation plans; preserved, not current authority
    └── sdd/     ← reserved for historical SDD evidence when tracked
```

## Current decision record

The consolidated grill, prototype/replay evidence, open gates, and AiPASS/Opus routing caveat are recorded in `current/2026-08-31-elliott-grill-decision-record.md`. This is the durable handoff/index; executable product semantics remain in the focused design spec.

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

## Current caveat

The file layout is now separated, but semantic cleanup is intentionally next: the vault still contains conflicting VCP-first versus Trend/Elliott/Trade-Setup wording. Do not resolve that conflict by reading archive files as authority. Reconcile the canonical vault notes in a separate documentation pass.
