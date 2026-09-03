# Signalix Handoff — 2026-09-03 17:48 ICT · Daily structural evidence integration

> **STATUS: CURRENT MILESTONE — SOURCE/RUNTIME/UI VERIFIED**
> **Owner:** Arm · **Orchestrator/final gate:** Lite · **Worker:** Codex CLI `gpt-5.6-luna`
> **Branch:** `release/signalix-mvp-stable` · **Commit:** `9ec9e20`
> **Spec:** `docs/current/2026-09-03-daily-structure-evidence-integration-spec.md`
> **Ticket:** `.scratch/2026-09-03-daily-structure-evidence/issues/01-additive-daily-structure-evidence.md`
> **Previous milestone:** `vault/2026-09-03-1631-wave3-publication-gate-milestone-handoff.md`

## Outcome

Daily Wave 1/2/4/5 visibility is restored as an additive `wave.daily_structure` evidence object. `wave.primary_state` remains the sole canonical decision spine; the structural phase is always `actionability=NONE` and cannot create `REVIEW_NOW`, `AVOID`, or change setup validity.

## Contract

- `EARLY_WAVE_3` and `WAVE_3_CONTINUATION` remain canonical primary states.
- `WAVE_1_ADVANCE`, `WAVE_2_FORMING`, `WAVE_2_NEAR_COMPLETION`, `WAVE_4_CORRECTION`, and `WAVE_5_ADVANCE` are exposed as Daily structural evidence first.
- `UNKNOWN` remains explicit evidence; the canonical primary remains `NOT_VERIFIABLE` when W3 is not publishable.
- Daily structural evidence carries phase, confidence, actionability, Daily source timeframe, policy version, as-of/snapshot identity, anchors, retracement, alternatives, and supporting/contradicting/missing evidence.
- 60m setup evidence does not overwrite Daily primary or Daily structural phase.
- W3 raw finite retracement gate `r<=0.60` remains intact.

## Source/tests

Codex changed the engine, contract/projection, frontend drawer, and focused tests. Existing dirty Fix A/B/C/D behavior was preserved and included intentionally in the implementation commit. No scratch review artifacts were staged.

- Focused Wave/API/UI suites: PASS.
- Codex report: `188 passed, 2 skipped`; broader contract `105 passed`.
- Lite rerun of Wave, contract, API, frontend, and Wave Context tests: PASS; two environment/data skips remained (external BCP/BBGI fixtures and Chromium executable in test environment).
- `node --check` for `app.js` and `wave-context.js`: PASS.
- `python -m compileall -q backend`: PASS.
- `git diff --check`: PASS.
- Full backend suite has one pre-existing `test_marginable.py::test_frontend_has_both_filters_and_drawer_permissions` failure, reproduced on the pre-change baseline.

## Runtime/API

After `docker restart signalix_dashboard` and canonical read-model republish:

```text
READ_MODEL_PUBLISHED count=237
source_version=read-model-fb71255aa17e8e3b
```

Public and loopback `/api/setup-candidates` returned HTTP 200; `evaluated=237`, `retrieved=237`, and every row contained `wave.daily_structure` with `actionability=NONE`.

Live phase distribution:

```text
WAVE_3_CONTINUATION     40
WAVE_1_ADVANCE           17
WAVE_2_FORMING           14
WAVE_2_NEAR_COMPLETION    3
WAVE_4_CORRECTION        46
WAVE_5_ADVANCE           30
UNKNOWN                  87
```

Primary state remained intentionally narrow:

```text
WAVE_3_CONTINUATION 15
NOT_VERIFIABLE      222
```

Representative lineage:

```text
CRC   primary NOT_VERIFIABLE · daily phase WAVE_1_ADVANCE · r=.8571
BGRIM primary NOT_VERIFIABLE · daily phase WAVE_3_CONTINUATION · r=.2917
AWC   primary NOT_VERIFIABLE · daily phase UNKNOWN · r=.9118
```

## Browser/UI

Public `/mvp` loaded with HTTP 200 after reload. At 390px:

```text
innerWidth=390
scrollWidth=375
bodyScrollWidth=375
```

The drawer renders separate labels for `Primary Daily Wave` and `Daily structural context`, with explicit non-actionable wording and Daily source. Cards/grouping/lane remain based on primary state. Full failure→Retry→recovery was not rerun in this slice; prior verified gate remains separate evidence.

## Deferred

- Promote W1/W2 to canonical primary.
- Add automatic phase-to-lane mapping.
- Promote W4/W5 primary labels.
- Re-derive historical fixture lineage/accuracy.
- Alerts, evaluator auto-caller, broker execution, trading, migrations.

## Intentionally untouched

- Historical handoffs and prototype/archive artifacts.
- Untracked `.scratch/*` artifacts, including the existing chart worktree and cleanup archive.
- Two newly observed untracked diagnostic files at repository root (`review_2026_09_03.py` and `review_2026_09_03.json`) remain unstaged for owner review; they are not runtime inputs or part of this milestone.
- Remote push was not performed; local stable remains ahead of origin.

## Timeline

- 2026-09-03 15:20 ICT — Live W3 issue reviewed with Ploy, Codex, and external Claude/Opus input.
- 2026-09-03 16:25 ICT — W3 publication gate promoted and served.
- 2026-09-03 17:48 ICT — Additive Daily structural evidence implementation verified and served.

## Resume boundary

Next work is a new bounded policy/replay decision for `WAVE_2_NEAR_COMPLETION`; do not make phase evidence actionable or restore the legacy full-wave classifier as canonical primary without a new spec and replay gate.
