# 2026-08-28 — Kanban terminal-trigger and REVISE recovery gap

> **STATUS: CURRENT** · Durable operations lesson and control rule; live card IDs are historical evidence only.

## Symptom

The Signalix monitor reported an unrelated stale blocked card instead of the active release chain. It also detected a reviewer `REVISE` but stopped the chain without creating the next bounded remediation card. A completed Nida card was not reported as a terminal trigger to the owner.

## Root Cause

The monitor prompt selected from broad board status instead of an explicit active-chain lineage, so retired/superseded diagnostic cards could mask current work. The prompt had a stop rule for `REVISE`/`FAIL` but did not include the mandatory recovery action: create and dispatch a bounded remediation for the responsible implementation owner. Terminal-event reporting was described but not enforced as non-negotiable, allowing a completion to be missed or emitted as `[SILENT]`.

## Fix

- Defined the active chain as Khim → Nida → Ploy → Lite using explicit parent lineage and fresh cards.
- Excluded retired-profile, archived, superseded, and stale diagnostic cards from current selection and dispatch.
- Added mandatory terminal reporting for every active-chain `PASS`, `DONE`, `REVISE`, `FAIL`, and `BLOCKED` outcome.
- Added mandatory `REVISE`/`FAIL` recovery: stop downstream, identify the earliest failed gate, create/link an idempotent bounded remediation for the responsible implementation owner, and dispatch only after resource/concurrency checks.
- Kept stale evidence archived rather than purged.
- Added a bounded heartbeat checkpoint rule: repeated heartbeat without an evidence milestone must end in `kanban_complete` with non-empty artifacts or `kanban_block` with a concrete root cause; silent scope expansion is prohibited.
- Updated the canonical `hermes-kanban-ops` skill, monitor job, Level-1 memory, Level-3 facts, and governance notes.

## Verification

- Monitor job remains enabled and scheduled every 10 minutes with the updated prompt.
- Active chain was verified against live Kanban state, not board counts alone.
- The remediation flow was exercised: Ploy `REVISE` produced a fresh Khim remediation card and a single active Khim worker.
- No secrets or raw credentials are stored in this note.

## Prevention / Skill or Memory Update

The invariant is now recorded in `hermes-kanban-ops`, `MEMORY`, facts 147/161/189, `Decisions.md`, `Execution-Pipeline.md`, and Hermes/Signalix governance indexes. Future monitors must report terminal card outcomes and must never leave an active-chain `REVISE`/`FAIL` without a bounded remediation or explicit human/capability/resource blocker.
