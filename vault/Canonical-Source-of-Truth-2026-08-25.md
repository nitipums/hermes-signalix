# Signalix Canonical Source of Truth — 2026-08-25

> **STATUS: HISTORICAL CUTOVER RECORD** · Records the 2026-08-25 source/worktree cutover; current repository/runtime authority is `AGENTS.md`, `vault/Deployment.md`, and fresh probes.
> **Last historical reconciliation:** 2026-09-01 · current release has since advanced beyond this record.

## Authority

- GitHub repository: `https://github.com/nitipums/hermes-signalix`
- Current branch: `release/signalix-mvp-stable`
- Code release commit at cutover: `3ec48f7` — historical cutover point
- Current branch HEAD: `4311c37` — T1–T9 promotion and freshness/retry UX evidence
- Canonical local release worktree: `/root/signalix`
- Additional registered prototype/feature worktrees exist; they are isolated and not release authority.
- Production Docker bind mount: `/root/signalix/backend`

## Retired confusion sources

Feature worktrees, the former release-candidate path, and temporary quarantine copies were retired after the stable branch became canonical. Their cleanup evidence was intentionally removed after the stable GitHub push; no retired path is a current implementation authority.

## Runtime verification at cutover

- `signalix_postgres`: healthy
- `signalix_redis`: healthy
- `signalix_backend`: healthy
- `signalix_dashboard`: healthy after force-recreate from `/root/signalix`
- `signalix_delivery`: healthy
- `/mvp`: HTTP 200
- `/api/daily-shortlist`: HTTP 200 after restoring the generated MVP snapshot artifact
- `/api/explorer`: HTTP 200
- `/api/chart/PTT`: HTTP 200

## Artifact boundary

`mvp_snapshot.json` and `artifact_manifest.json` are generated runtime artifacts and remain outside Git source authority. They must be revalidated/rebuilt by the canonical EOD pipeline on the next successful Daily run. Do not copy generated snapshots into vault notes or treat them as source code.

## Secret boundary

`.env`, `settradeupdated.env`, and Hermes auth files remain host-only. They are not stored in this note, Git, fact_store, or any other vault note.
