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

Inputs are Daily Close, SMA5/10/20/50/100/200, and slope over 20 completed Daily bars. Partial MA inputs may classify only with explicit `PARTIAL` evidence quality. Exact formula/predicate/precedence semantics live in `docs/current/2026-09-13-main-trend-calculation-contract.md`. Subtypes and action lanes are deferred. Current Trend Map remains public read-only and non-actionable until separate gates pass.

## Implementation result

Implemented the deterministic MA diagnostic matrix/classifier at the approved classifier/builder seam in `backend/main_trend_mapping.py`, with literal owner-labelled diagnostic fixtures in `backend/test_main_trend_mapping.py`. The read-only Trend Map builder carries the result as non-actionable `main_trend` evidence and preserves the legacy `machine_lane` compatibility field. No subtypes or action semantics were added.

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
- Main Trend implementation: CODE + FOCUSED TESTS COMPLETE; owner/Lite acceptance remains pending.
- UI/runtime promotion: owner-authorized promotion completed on 2026-09-13. Immutable artifact now carries `main_trend` policy `main-trend-ma-calibration-v6`; public 390px UI uses Main Trend 1–4 as the only visible taxonomy and no longer renders legacy `Machine lane`; the Trend Map drawer shows `Main Trend N · FULL/PARTIAL` as primary label. The canonical chart uses MA5/10/20/50/100/200 under `technical-indicators-v2`; 260 candles remains separate 52-week coverage, not an MA. v6 adds the MA100/MA200 long-slope gate: Main3 candidates with confirmed non-bullish long slopes demote to Main1; missing long slopes remain PARTIAL/reviewable. API/browser read-back passed. See `vault/Deployment.md` for artifact identity and counts.
- Runtime/API/browser promotion: PASS for the bounded Main Trend evidence/UI slice; no action semantics were added.
- No commit, push, migration, database write, alert, broker, or auto-trading action performed for this taxonomy. Backend/dashboard recreate and artifact publication were explicitly authorized runtime actions.
