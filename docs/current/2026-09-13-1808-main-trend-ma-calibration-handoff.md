# Main Trend MA Calibration — Session Handoff

> **STATUS: OWNER-APPROVED SPEC / SESSION CLOSED** · 2026-09-13 18:08 ICT
> **Owner:** Arm · **Final gate:** Lite
> **Issue:** https://github.com/nitipums/hermes-signalix/issues/32

## Completed

- Grilled the taxonomy with Matt Pocock flow before writing the spec.
- Arm approved Main Trend 1–4 as deterministic Daily visual evidence.
- Focused spec is `docs/superpowers/specs/2026-09-13-main-trend-ma-calibration.md`.
- Decision recorded in `vault/Decisions.md`.
- Routing/index/acceptance references synced in `AGENTS.md`, `docs/START-HERE.md`, `vault/INDEX.md`, and `vault/Execution-Pipeline.md`.
- Issue #32 is open with `ready-for-agent` and owner-approval comment.

## Approved model

```text
Main 1 = base / weak / damaged
Main 2 = recovery + bullish advance
Main 3 = pullback / weakening / distribution while long-term structure is intact
          (subsumes former 4.1)
Main 4 = sustained bearish deterioration / breakdown
```

Inputs are Daily Close, SMA5/10/20/60/120/240, and slope over 20 completed Daily bars. Partial MA inputs may classify only with explicit `PARTIAL` evidence quality. Subtypes and action lanes are deferred. Current Trend Map remains public read-only and non-actionable until separate gates pass.

## Next bounded task

Build the deterministic MA diagnostic matrix/classifier test-first at the approved classifier/builder seam. Compare owner-labelled examples against legacy machine lanes, MA ordering, Close-vs-MA position, 20-bar slopes, missing periods, and ambiguity reasons. Do not tune subtypes or add action semantics in the first slice.

## Parked worktree changes

Codex's prior chart fix remains uncommitted and intentionally parked:

- `backend/canonical_chart_read.py`
- `backend/frontend/shared-drawer.js`
- `backend/mvp_chart_db.py`
- `backend/test_chart_provisional.py`
- `backend/test_mvp_ui_feedback_contract.py`

Do not reset, stash, clean, overwrite, or mix those chart changes into Issue #32 without a new bounded decision.

## Verification / boundary

- GitHub issue publication and approval comment read-back: PASS.
- Documentation edits and `git diff --check`: PASS at session close.
- Main Trend implementation: NOT STARTED.
- Runtime/API/browser promotion: NOT PERFORMED.
- No commit, push, restart, deploy, migration, database write, alert, broker, or auto-trading action performed for this taxonomy.
