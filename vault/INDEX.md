# INDEX — Signalix Project Vault

> **STATUS: CURRENT** · Catalog and routing map for the Level-4 vault.
> **Last reconciled:** 2026-09-13 ICT
> **Authority:** the linked concern-specific documents, not this catalog.

## How to use

- Start at [`../docs/START-HERE.md`](../docs/START-HERE.md).
- Use this file to locate a note, not to learn the full product or runtime status.
- One concern has one authority. Supporting notes provide evidence; history does not override current authority.
- `vault/` notes must not contain secrets, tokens, passwords, or `.env` values.

## Current authority map

| Concern | Authority |
|---|---|
| Product thesis, surfaces, non-goals, roadmap | `Product-Strategy-Market-to-Action.md` |
| Owner-approved decisions | `Decisions.md` |
| Acceptance sequence and evidence standard | `Execution-Pipeline.md` |
| Architecture and data flow | `Architecture.md` |
| Component responsibilities | `Components.md` |
| Deployment, timers, runtime claims | `Deployment.md` |
| Domain vocabulary | `../GLOSSARY.md` |
| Documentation governance | `Documentation-Governance.md` |
| Research routing | `Research-Index.md` |
| Research formulas and promotion gate | `Research-Playbook-Bible.md` |

## Focused current specifications and evidence

- `../docs/superpowers/specs/` — current executable product/API/UI contracts.
- `../docs/current/2026-09-13-daily-trend-derived-fallback-spec.md` — current bounded Derived Daily fallback contract and Issue #22 implementation authority.
- `../docs/current/2026-09-13-1634-trend-map-drawer-navigation-handoff.md` — current bounded drawer navigation verification and release boundary.
- `../docs/superpowers/specs/2026-09-13-main-trend-ma-calibration.md` — owner-approved spec for Daily Main Trend 1–4 multiple-MA calibration.
- `../docs/current/2026-09-13-main-trend-calculation-contract.md` — exact current Main Trend v6 formulas, predicates, precedence, and verification contract.
- `../docs/current/` — dated decision records and bounded evidence handoffs.
- `Browser-and-Freshness-Verification.md` — browser/freshness procedure.
- `Memory-Cleanup-Candidates.md` — memory/fact cleanup record.
- `Team-Operating-Model.md` and `Codex-Standard-Workflow-2026-08-29.md` — roles and worker procedure.

Read a focused file only when the task routing in `../docs/START-HERE.md` requires it.

## Historical and non-authority material

- `archive/`, `Postmortems/`, dated handoffs, replay baselines, and old implementation plans are preserved evidence.
- `VCP-Finder-MVP.md` and older VCP-first records are compatibility/audit history unless a current authority says otherwise.
- Generated HTML/JSON, logs, snapshots, worktrees, scratch files, and Kanban history are artifacts or execution evidence, not documentation authorities.
- Active named-worker state belongs to the `signalix` Kanban board when a bounded run exists; do not mirror live card status here.

## Maintenance rule

When adding, moving, superseding, or archiving a note:

1. check whether an authority already exists;
2. add or update one catalog entry and its status;
3. scan references before moving anything;
4. preserve historical evidence with an explicit status/replacement link;
5. keep runtime claims in `Deployment.md` with dated evidence, not in this catalog.

This index intentionally has no product changelog, runtime snapshot, backlog, or fact-store ledger.
