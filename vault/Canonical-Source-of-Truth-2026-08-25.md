# Signalix Canonical Source of Truth — 2026-08-25

> **STATUS: CURRENT** · `CANONICAL_FOR: repository/worktree/runtime source authority`

## Authority

- GitHub repository: `https://github.com/nitipums/hermes-signalix`
- Current branch: `release/signalix-mvp-stable`
- Current release commit at cutover: `3ec48f7` — `fix: preserve Daily run lineage in EOD dashboard build`
- Canonical local worktree: `/root/signalix`
- Registered worktrees: exactly one (`/root/signalix`)
- Production Docker bind mount: `/root/signalix/backend`

## Retired confusion sources

Feature worktrees and the former release-candidate path were retired on 2026-08-25 after their dirty scope was captured in:

`/root/signalix-cleanup-audit-20260825/`

The audit bundle is recovery evidence only. Its patches, untracked-source archives, old branches, generated files, and dated notes are not current implementation authority.

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

`mvp_snapshot.json` and `artifact_manifest.json` are generated runtime artifacts and remain outside Git source authority. The snapshot restored during this cutover came from `/root/signalix-mvp-quarantine/backend/mvp_snapshot.json`; it must be revalidated/rebuilt by the canonical EOD pipeline on the next successful Daily run. Do not copy generated snapshots into vault notes or treat them as source code.

## Secret boundary

`.env`, `settradeupdated.env`, and Hermes auth files remain host-only. They are not stored in this note, Git, fact_store, or any other vault note.
