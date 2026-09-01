# Signalix — Elliott / Trend / Trade-Setup Grill Decision Record

> **STATUS: CURRENT DECISION RECORD** · Curated 2026-08-31
> **Authority:** owner decisions recorded here are inputs to the focused design/spec; Lite remains final quality gate.
> **Scope:** Signalix candidate discovery and setup preparation for Thai `marginable_long`.

## 1. Purpose

This note preserves the owner grilling session, prototype/replay evidence, implementation boundary, and the AiPASS/Opus consultation so the next session does not reconstruct decisions from chat history. It is a decision/evidence index, not a replacement for the executable design spec or live runtime evidence.

## 2. Owner decisions locked during the grill

- Product universe: `marginable_long = active Thai ORD ∩ owner-supplied marginable list ∩ can_buy=true`.
  - Current reference counts: 931 active ORD; 237 product-eligible; 694 excluded.
  - The 931-symbol path remains explicit audit/rollback coverage, not default candidate serving.
- Product spine:

```text
Daily trend + strength + 52W/ATH context
→ Daily Elliott structural candidate
→ 60m minor structure / entry timing
→ trigger + trade stop + thesis invalidation + targets + R:R
→ sector/peer context
→ VCP as bonus evidence
→ Arm chart review and decision
```

- Daily owns big-picture trend, strength, 52W/ATH, and Elliott structural evidence.
- 60m owns lower-timeframe minor structure, trigger, confirmation, and entry timing. It must not overwrite Daily state or be labelled as Daily evidence.
- Elliott v1 covers Wave 1–5 plus `UNKNOWN`; every interpretation needs confidence, alternative state where plausible, and supporting/contradicting/missing evidence.
- Wave 1 is a preparation state; the system does not wait for Wave 2 before preparing a valid setup.
- Lifecycle separates:
  - `DAILY_CANDIDATE`
  - `SETUP_FORMING`
  - `REVIEW_NOW`
  - setup states `PRE_TRIGGER`, `TESTED_TRIGGER`, `TRIGGERED`, `EXTENDED`, `STOPPED`, `INVALIDATED`, `EXPIRED`, `DATA_BLOCKED`
- `REVIEW_NOW` means worth Arm's chart review, never an automatic BUY or executable order.
- Minimum `target_1` reward/risk for `REVIEW_NOW` is `1:2`; R:R cannot override freshness, structure, trigger, invalidation, or target quality.
- `trade_stop` is lower-timeframe risk; `thesis_invalidation` is the Daily structural break. They are separate.
- Prior 52W/ATH references use historical `High`; trading through without a close is `TESTED_HIGH`, while a close above is `BREAKOUT`.
- Sector/industry/peer context ranks and explains; it is not a silent hard exclusion.
- VCP remains supporting/bonus evidence and cannot remove a valid non-VCP candidate.
- Candidate thesis identity and immutable setup-attempt identity are separate. Changed levels create a new `setup_id`; historical machine snapshots are not rewritten.

## 3. Detection tuning captured from the grill

- Wave 1: use measurable advance from the confirmed swing engine; do not require prior advance, confirmed anchors, and intact structure as one over-strict conjunction before reaching medium confidence.
- Wave 2 near completion: retracement 30–60% (Fib 0.382–0.618), duration 5–25 sessions, and actual low remains above Wave 1 low.
- Below 30% retracement remains forming; above 60% or a break of Wave 1 low is correction/unknown territory.
- Early Wave 3 / continuation: Daily `Close` above Wave 1 high. A wick alone is tested-high evidence, not a close breakout. Breakout volume is supporting evidence, not a standalone candidate gate.
- Dual-degree prototype:
  - large `1,2,3`: Day 5% / 5 bars pilot
  - small `(1),(2),(3)`: Day 3% / 2 bars pilot
  - Week-large 7% / 2 bars is a candidate option for 6M+ trend context and remains subject to validation.
- CRC correction: Wave 1 must anchor to actual January Low 16.5 rather than a September Close 25.25; June high 23.8 and July low 22.0 must satisfy `Wave2 low > Wave1 low`.

## 4. Evidence captured

### 4.1 Prototype

- Single-file LOGIC prototype exists under the Elliott replay worktree.
- Reported checks: reducer walkthrough, desktop/mobile 390px layout, axe 0 violations, 11 guided walkthroughs.
- Prototype evidence is not production-serving evidence.

### 4.2 Replay and tests

- Initial 6M replay exposed an overly strict engine: mostly LOW confidence and Wave 4/5 outputs.
- Tuning improved the reported 12-symbol replay to 66% MEDIUM/HIGH.
- Focused CRC/BGRIM/AWC/GULF/BA review exposed Wave 4 sticking and flicker; OHLC extremes, hysteresis, and `Wave2 > Wave1` anchoring were introduced.
- Reported focused engine test result: `30/30` passed.
- 1Y 10-stock replay reported 2,912 rows; the long-horizon Week-large choice still needs validation.
- These are evidence inputs from the handoff/worktree, not a production promotion verdict.

### 4.3 Remaining technical gate

- Compare corrected Wave 3 behavior across the 10-stock 1Y dual-degree set using Day + Week-large candidates.
- Run Standards-vs-Spec code review on the actual engine/worktree.
- Perform Arm chart review on representative Wave 1–5, Wave 3, false-positive, and blocked cases.
- Do not promote the throwaway prototype or deploy the new product spine until source, replay, runtime, and served UI gates agree.

## 5. AiPASS / Thai AI Passport consultation

### Session reference

The consultation is in the AiPASS session titled **“ลองเข้า Thai AI Passport”**, preserved in session history at @session:lite/20260831_115154_50c23095. Arm can open the session and inspect the original prompt, model picker, comments, and responses directly.

### Routing evidence

- User-authenticated AiPASS session was opened with the approved browser profile.
- UI selection before consultation: `Anthropic → Claude Opus 5`.
- The first response showed actual response metadata as `Gemini 3.1 Flash Lite`, with an automatic model switch/credit limitation notice.
- A later response visually self-identified as Claude Opus 5, but self-identification is not routing proof.
- A fresh short routing probe again reported `Gemini 3.1 Flash Lite`, and the composer reverted to Gemini after completion.

**Routing verdict: `NOT VERIFIED` — do not attribute the consultation to Claude Opus 5.**

The AI response can be retained as an advisory/challenger input only. Lite must independently validate every product, architecture, data, and implementation claim. No secrets, credentials, OTPs, or private account data belong in this record.

### Advisory themes visible in the consultation

Treat these as unverified AI advisory, not owner decisions:

- Configuration/provenance drift between worktree, spec, runtime, and served result is a higher-order risk than an isolated algorithm bug.
- VCP versus Elliott should be represented as one clear primary spine with legacy/audit evidence explicitly separated.
- 237 product symbols and 931 audit symbols need separate lineage and replay boundaries to avoid state pollution.
- Suggested next sequence: close the written contract, validate a bounded replay/fixture set, then independently verify API/runtime/UI before expansion.

## 6. Authority routing for future work

| Concern | Read/update first | Status |
|---|---|---|
| Owner grill decisions and evidence index | This record | CURRENT |
| Prototype/replay/chart-review phase | `docs/superpowers/plans/2026-08-30-elliott-trend-trade-setup.md` + throwaway worktree | HISTORICAL evidence; T1–T9 later promoted; 390px failure/recovery gate passed |
| Domain terminology | `CONTEXT.md` | CURRENT working glossary |
| Executable Elliott product contract | `docs/superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md` | CURRENT; source implemented/promoted; 390px failure/recovery gate passed |
| Implementation plan | `docs/superpowers/plans/2026-08-30-elliott-trend-trade-setup.md` | CURRENT closeout; checklists historical evidence |
| Product thesis/roadmap | `vault/Product-Strategy-Market-to-Action.md` | CURRENT authority; current override at section 12 |
| Atomic decisions | `vault/Decisions.md` | CURRENT ledger; team review added 2026-09-01 |
| Acceptance/evidence | `vault/Execution-Pipeline.md` | CURRENT authority; team review is next gate |
| Architecture/runtime | `vault/Architecture.md`, `vault/Deployment.md` | CURRENT; served 390px failure/recovery gate passed; broader/evaluator items separate |
| Historical work | `docs/archive/superpowers/`, `vault/archive/`, dated postmortems | HISTORICAL / ARCHIVED |

## 7. Current verdict

| Gate | Verdict | Evidence |
|---|---|---|
| Owner product direction | PASS | Owner-approved Elliott/Trend/Trade-Setup direction |
| Prototype logic | PASS | Throwaway evidence only |
| Focused engine tests | PASS | `30/30` at prototype checkpoint |
| Long-horizon Wave 3 validation | NOT VERIFIED | Week-large / 1Y comparison remains open |
| Runtime transport | PASS | `/mvp` and `/api/setup-candidates` respond locally; readiness 200 |
| Served semantics | REVISE | current full aggregation shows 227 DATA_BLOCKED / 10 AVOID and no positive review lanes |
| Browser/public acceptance | NOT VERIFIED | desktop/mobile/error journey remains open |
| Production readiness | BLOCKED | four owner concerns require bounded review/fixes first |

## 8. Resume sequence

1. Arm reviews the linked AiPASS comments and confirms which advisory observations are useful.
2. Lite reconciles this record with the focused spec, `CONTEXT.md`, and canonical vault notes; stale VCP-first wording is marked historical/superseded rather than silently deleted.
3. Validate the bounded Wave 3 replay/chart gate in the throwaway worktree.
4. Only after owner/spec gate: create bounded implementation tickets, then verify source → tests → runtime → public UI.
5. Keep alerts, auto-trading, and broker execution off.

> **Current closeout:** T1–T9 source and release promotion are complete. The live dashboard shell/API have been reloaded and return the DB-built contract; the public 390px failure→Retry→recovery journey is PASS. This record is the durable evidence index, not runtime authority.

> **Closeout reconciliation 2026-09-01:** The isolated public 390px failure→Retry→recovery browser journey is now `PASS`; direct evidence is recorded in `vault/2026-09-01-Current-Session-Handoff.md`. The evaluator auto-caller decision and any broader desktop/drawer regression remain separate.

- **Phase:** T1–T9 implementation and release promotion complete; 390px failure/recovery acceptance passed; broader desktop/drawer evidence remains separate.
- **Active release checkout:** `/root/signalix` on `release/signalix-mvp-stable`; prototype worktree is historical evidence and remains isolated.
- **Prototype assets:** `prototypes/elliott-state-replay/index.html`, `replay_lab.py`, `engine_evidence_chart.py`, `crc_dual_wave.py`, and worktree Elliott/variant files.

### Current implementation closeout
- **T1–T9:** source implemented and promoted to `release/signalix-mvp-stable`.
- **Remaining gates:** broader desktop/drawer regression evidence and evaluator auto-caller decision; the explicit 390px API/error-state journey is closed by the isolated harness.
- **Do not restart implementation from ticket 01:** the later T1/T2 closeout notes below are retained evidence, not an outstanding task list.

- **Retracement gate fixed:** `backend/elliott_structure_engine.py` adds `retrace_ok_for_w3` (retrace ≤60 AND holds) — blocks W3 promotion when retrace >60% or Wave1-low broken. Verified: CRC 85.71%→WAVE_1_ADVANCE, AWC 91.18%→WAVE_1_ADVANCE, BGRIM 29.17%→WAVE_3_CONTINUATION (correct).
- **Universe resolver fixed:** `replay_lab.resolve_universe` now queries `symbol_master` (931 active ORD) instead of `price_data` (1,219) — eligible now 237. Verified 237/237.
- **Focused tests:** `backend/test_elliott_setup_engine.py` 30/30 PASS (Lite rerun).
- **Chart gate:** replayed CRC/BGRIM/AWC 1Y no-lookahead; `engine_evidence_chart.py` emits honest detection-date charts; owner chart review: **Arm approved** 2026-08-31.
- **Opus challenger review (review.md) analyzed:** aligns with documentation reconciliation; standalone stress-test suggestion noted but not started.
- **Documentation reconciliation (Lite-verified):**
  - `vault/Execution-Pipeline.md` — product contract now Elliott/Trend/Trade-Setup; VCP marked DEPRECATED (deprecated-table added)
  - `vault/Decisions.md` — added 3 entries: Elliott replacement, prototype phase confirmed, documentation authority reconciliation
  - `vault/INDEX.md` — VCP-Finder-MVP, 2026-08-30 closeout, Scan-Evaluation-Logic-Map marked ⛔ deprecated/historical
  - `vault/Architecture.md` — MVP surface contract updated to Elliott/Trend spine
  - `docs/superpowers/specs/2026-08-29-unified-vcp-decision-contract-design.md` and `docs/superpowers/plans/2026-08-26-vcp-first-surface-and-cadence.md` — DEPRECATED banners
  - `docs/superpowers/specs/2026-08-30-elliott-trend-trade-setup-design.md` — legacy-path wording sync
- **Implementation tickets published:** `.scratch/elliott-trend-trade-setup/issues/01..08` (Matt Pocock to-tickets; owner approved granularity).
  - Frontier: **01** (None), then 02/03 → 04 → 05/06 → 07 → 08.
  - Historical next action at that checkpoint: implement ticket 01, then 02/03 engine boundaries. This was completed by the later T1–T9 promotion.

### Historical T2 closeout evidence (checkpoint before release promotion)
- **T2 — Elliott engine → production + contract test: DONE.** Commit `d31a2d2` on `prototype/elliott-state-replay` (scoped: engine + tests + fixtures only).
- **Close-gate enforced (spec §2.7):** `EARLY_WAVE_3`/`WAVE_3_CONTINUATION` now require a Daily Close above Wave 1 high; wick alone = `TESTED_HIGH` never promotes; volume/markers are supporting evidence only. Regression path (marker-promoted EWR3 without close) removed; old test updated to spec.
- **`build_wave_contract` added (spec §2.2):** primary_state/alternative_state/confidence LOW–MEDIUM–HIGH + supporting/contradicting/missing arrays, dual-degree evidence-only, JSON-safe. Ready for T4 to consume.
- **Evidence:** full backend suite 594 passed / 2 skipped; frozen 1Y fixtures CRC/BGRIM/AWC (as_of 2026-08-28) lock owner-verified states — CRC 85.71%→WAVE_1_ADVANCE, AWC 91.18%→WAVE_1_ADVANCE, BGRIM 29.17%→WAVE_3_CONTINUATION HIGH; live read-only replay dry-run reproduced all three.
- **Historical checkpoint only:** no deploy/restart at that prototype stage; T3+ were open then. This is superseded by the later T1–T9 release promotion recorded above.

### Historical implementation notes (retained evidence)
- Ticket 01/T2 completion and the later T3–T9 implementation are retained as historical evidence; no ticket is currently outstanding from this record.
- Week-large 7%/2-bars production validation (prototype only, NOT locked; skill notes keep as candidate option for 6M+).
- Opus stress-test corner-case loop (optional challenger input only).
- No production promotion, DB writes, deployment, alert activation, broker integration, or auto-trading.

### Safety
- no DB writes, deployment, alerts, broker action, or auto-trading.

This closeout is the resume pointer. On the next session, read this record and then re-check the actual worktree/diff before touching any file.
