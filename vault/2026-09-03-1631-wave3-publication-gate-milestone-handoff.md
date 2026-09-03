# Signalix Milestone Handoff — 2026-09-03 16:31 ICT · W3 publication gate

> **STATUS: CURRENT MILESTONE** · W3 publication contract promoted and served; tuning of other wave evidence is the next frontier.
> **Owner:** Arm · **Orchestrator/final gate:** Lite · **Implementation worker:** Codex CLI `gpt-5.6-luna`
> **Canonical branch:** `release/signalix-mvp-stable` · **Promoted commit:** `807cdde`
> **Previous handoff:** `vault/2026-09-03-1430-mvp-wave-badge-fix-handoff.md`
>
> This note records the bounded W3 safety milestone. It does not reopen the historical full-wave implementation or claim semantic accuracy for every machine-generated label.

## Decision

Arm approved the safest W3 contract after Lite, Ploy, Codex, and authenticated AiPASS Claude Opus 5 review:

- `EARLY_WAVE_3` requires a completed Daily close above W1 high, with follow-through not yet PASS.
- `WAVE_3_CONTINUATION` requires the same Daily close plus follow-through PASS.
- Published W3 states require raw finite retracement `r <= 0.60`.
- `0.236 <= r <= 0.786` remains anchor admissibility/evidence only; it does not authorize publication.
- Hysteresis is suppression-only and cannot rescue a hard-gate failure.
- Historical/live anchor discrepancies remain unresolved until snapshot/as-of, raw OHLCV, anchor-selector version, producer path, and policy version are pinned.

## Implementation

Codex worked in isolated `/root/signalix/.worktrees/w3-publication-gate`, then Lite independently inspected and promoted the scoped commit.

Changed files:

- `backend/wave3_candidate_engine.py`
- `backend/test_wave3_candidate_engine.py`
- `docs/superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md`

The external Opus YAML/runner artifacts were not used as production code: they were incomplete scaffolds and were not connected to Signalix's real `classify_candles`/`classify_frame` path.

## Verification

- Codex transcript: `/tmp/codex_w3_gate_transcript.log`
- Codex last message: `/tmp/codex_w3_gate_last.md`
- Focused/relevant tests: passed; Codex reported `171 passed, 1 skipped`; Lite rerun passed with two environment/data skips.
- `python -m compileall -q backend`: PASS.
- `git diff --check`: PASS.
- Full backend suite: one pre-existing failure in `backend/test_marginable.py::test_frontend_has_both_filters_and_drawer_permissions`; same failure reproduced on the pre-change stable checkout.

## Runtime/public evidence

After promotion:

```text
docker restart signalix_dashboard
READ_MODEL_PUBLISHED count=237
source_version=read-model-7db1dfb3e7cf3f9e
```

Dashboard, backend, PostgreSQL, and Redis were healthy. Loopback and public canonical API both returned HTTP 200 with `evaluated=237`, `total=237`.

Observed public API after reload:

```text
CRC   NOT_VERIFIABLE · r=0.730769... · retracement_gate_exceeded
BGRIM NOT_VERIFIABLE · r=0.625       · retracement_gate_exceeded
AWC   NOT_VERIFIABLE · r=0.34375     · post_impulse_correction_excluded
```

Current lane counts:

```text
REVIEW_NOW       0
SETUP_FORMING    0
DAILY_CANDIDATE  8
WAIT             176
AVOID            47
DATA_BLOCKED     6
```

Public `/mvp` smoke and 390px containment:

```text
HTTP 200
innerWidth=390
scrollWidth=375
```

The user-facing page correctly shows `237 evaluated`, Daily/60m freshness separately, and no horizontal overflow. Full retry/error and broad semantic chart acceptance remain separate evidence axes.

## Important scope note — other waves

The canonical narrow Wave-3 detector currently publishes only:

```text
EARLY_WAVE_3 | WAVE_3_CONTINUATION | NOT_VERIFIABLE
```

Therefore Wave 1/2/4/5 are not currently visible as canonical primary states on `/mvp`. Their absence is a product/contract scope consequence, not deletion of OHLCV or historical evidence. The next bounded work is to design/review how other wave evidence should return without weakening the W3 gate or creating a competing primary-state authority.

## Intentionally untouched

- Existing dirty owner files: `backend/frontend/wave-context.js`, `backend/setup_candidate_contract.py`.
- Untracked owner `.scratch/*` artifacts.
- Historical handoffs, prototype artifacts, legacy VCP routes, alerts, broker execution, evaluator auto-caller, and database migrations.
- Remote push: not performed; local stable is one commit ahead of `origin/release/signalix-mvp-stable`.

## Timeline

- 2026-09-03 15:20 ICT — Lite captured live `/mvp` evidence and dispatched Ploy/Codex challenger reviews.
- 2026-09-03 15:52 ICT — Ploy/Codex reconciled Opus policy; Arm approved Early B and hard `r <= 0.60` direction.
- 2026-09-03 16:00 ICT — Codex completed bounded implementation in isolated worktree; Lite reran source/tests.
- 2026-09-03 16:25 ICT — Candidate commit `717b7c7` created; promoted as `807cdde` into stable.
- 2026-09-03 16:26 ICT — Dashboard reloaded and read model republished as `read-model-7db1dfb3e7cf3f9e`.
- 2026-09-03 16:30 ICT — Public API and `/mvp` mobile smoke rechecked.

## Resume boundary

On the next session, read this handoff and the focused Elliott spec first. Do not revive the old full-wave classifier as a production primary surface. Define the next bounded other-wave evidence decision, then run the same Codex → Lite source/test/runtime/UI gate.
