# Signalix Session Handoff — 2026-09-03 14:30 ICT · /mvp wave-badge fix

> STATUS: CURRENT · Lite final-gate after /mvp bug investigation + bounded Codex repair.
> Owner: Arm · Orchestrator: Lite · Worker: Codex CLI gpt-5.6-luna (bounded)
> Branch: release/signalix-mvp-stable · Supersedes vault/2026-09-03-Current-Session-Handoff.md for this slice.
> Previous handoff: vault/2026-09-03-Current-Session-Handoff.md (rev 4, 11:15 ICT)

## Why

User reported http://91.98.72.120:3001/mvp looked "ผิดขนาดนั้น" vs port 8000 (legacy VCP backend). Systematic debugging traced 3 fail-closed presentation bugs verified against live API + source + browser.

## Root causes (evidence 2026-09-03)

1. **Wave badge used wrong field** — 44/50 cards diverged. UI read `wave.context.mapped_state` (secondary engine) for badge, grouping buckets, drawer Daily context. Canonical is `wave.primary_state`. Live proof: CRC primary=WAVE_3_CONTINUATION rendered as W1 advance; WAIT cards with primary=NOT_VERIFIABLE rendered W3/W5. Scope: `backend/frontend/app.js` badge/bucket/confidence only; lane logic in `setup_candidate_contract.py` was already correct.
2. **Header freshness poisoned by minority** — `aggregate_statuses` was any-unknown→unknown. 3 DATA_BLOCKED symbols (of 237) made header `Daily EOD: unavailable` while 234 were fresh. Footer already said Daily EOD 02 Sept.
3. **Drawer Trade value 0 lie** — `avgDailyValue20` not in card payload (`data.daily_metrics` absent) and fallback defaulted to 0, so mid/large caps showed `Trade value 0`.

Port 8000 is a different product (Signalix Backend v0.1.0, 33 routes under /signals, /dashboard/shortlist) — not comparable to /mvp.

## Bounded repair

- **Workspace:** isolated worktree `/root/signalix/.worktrees/mvp-wave-badge-fix` (branch fix/mvp-wave-badge-field @ d414e7c) → Codex → Lite final gate → ff-merge → canonical `/root/signalix`.
- **Codex CLI:** `HOME=/root CODEX_HOME=/root/.codex codex exec --ephemeral -m gpt-5.6-luna -s workspace-write` — process `codex exec` verified, transcript `/tmp/codex_wavefix_transcript.log` (109k tokens), `node --check` + focused pytest inside Codex.
- **Lite follow-up:** Codex used lowercase `close/volume` vs canonical `Close/Volume` → daily_metrics {} every card. Lite patched column case + bumped `MODEL_REVISION 4→5` (representation changed under identical lineage, content-addressed guard).

## Changed files

- `backend/frontend/app.js` — wave label/bucket/confidence read `wave.primary_state`/`wave.confidence`; context.mapped_state kept as labeled evidence row; freshness label adds `· N unavailable`; drawer trade value `daily_metrics.avg_trade_value_20` or `Not verified` (never bare 0).
- `backend/mvp_api.py` — majority freshness `_aggregate_freshness_status` + `daily_unavailable_count`; `_daily_metrics_observation` (Close/Volume), payload wiring.
- `backend/setup_candidate_contract.py` — `CANONICAL_METADATA_FIELDS` + `_LIST_ITEM_FIELDS/_LIST_NESTED_FIELDS` bounded daily_metrics allowlist.
- `backend/read_model_publisher.py` — `MODEL_REVISION = "5"`.
- Tests updated: `test_mvp_frontend_contract.py`, `test_setup_candidate_contract.py`, `test_setup_candidates_api.py`.

## Git

- `fb6a719` fix: wave badge uses canonical primary_state; majority freshness; real drawer trade value (Codex, 6 files)
- `b8ad677` fix: daily_metrics canonical columns; bump MODEL_REVISION 4→5 (Lite, 2 files)
- Base: `d414e7c` docs: record 2026-09-03 cockpit session handoff

## Publish & runtime

```
docker restart signalix_dashboard  # bind-mount /root/signalix/backend → /app
docker exec signalix_dashboard python -c "import update_data; update_data.publish_canonical_read_model()"
READ_MODEL_PUBLISHED {"count":237,"counts":{"AVOID":49,"DAILY_CANDIDATE":24,"DATA_BLOCKED":5,"REVIEW_NOW":0,"SETUP_FORMING":0,"WAIT":159},"path":"/app/read-model/versions/read-model-986f4c916d6fe3a3.json","source_version":"read-model-986f4c916d6fe3a3"}
```

Containers healthy. Earlier publish `read-model-53f9638a54e34b55` (first republish) gave 200 then 503 for new daily_metrics model until restart; after restart both paths OK.

## Verification (Lite independent)

- `node --check backend/frontend/app.js` PASS
- `pytest backend/test_setup_candidates_api.py backend/test_mvp_frontend_contract.py backend/test_setup_candidate_contract.py backend/test_read_model_publisher.py` — 203 passed, 1 skipped
- `git diff --check` PASS
- Live API: `freshness {daily_status:fresh, daily_unavailable_count:3, intraday_status:fresh}`; `IRPC daily avg_trade_value_20 330M`; `CRC symbol detail 470M`; `CRC primary WAVE_3_CONTINUATION`
- Browser 91.98.72.120:3001/mvp: header `Freshness available · Daily EOD: fresh · 3 unavailable · 1d ago`, grouping `EARLY_WAVE_3 9 + WAVE_3_CONTINUATION 15` (was W1/W2 mis-buckets), WAIT 159; `app.js` contains `wave.primary_state` and `Trade value Not verified`
- Served asset hash parity verified via bind mount; no legacy VCP routes touched.

## Docs touched / untouched

- Updated: this handoff (new), `MODEL_REVISION` runbook implied (publish guard).
- Untouched (no contract change): `vault/Execution-Pipeline.md`, `vault/Architecture.md`, `docs/superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md` — badge field was always primary_state per spec.
- Deferred: broader docs sync for read-model revision history (append to vault/2026-09-03-Current-Session-Handoff.md or INDEX on next closeout).

## Next

- No force-close of Kanban R4/R5 dependency graph; worktree `.worktrees/mvp-wave-badge-fix` to be archived/removed after push verification.
- Intraday timer `signalix-intraday.timer` continues 30m; next EOD publish will create new lineage naturally.
