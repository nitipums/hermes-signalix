# Wave Candidate Lineage Prototype — Session Closeout

> **STATUS: HISTORICAL RESEARCH HANDOFF — PRODUCTION INTEGRATION DEFERRED**
> **As of:** 2026-09-11 20:35 +07 · Current delivery focus is Daily Trend Mapping.
> **Owner/final gate:** Arm / Lite

## Question

Determine how Signalix can recognize that several `L → H → L` candidates belong to the same major wave instead of replacing the major structure with the latest local pattern.

## Findings

The previous all-universe fallback selected the latest candidate. This caused the chart to lose the larger structure when a later candidate was nested inside it or extended it.

Examples from the 260-bar research snapshot:

| Symbol | Major candidate | Later candidate | Interpretation |
|---|---:|---:|---|
| CRC | `99 → 126 → 129` | `108 → 126 → 129` | nested/connected structure |
| GUNKUL | `145 → 153 → 166` | `205 → 225 → 230` | later higher-low continuation candidate |
| CENTEL | `79 → 87 → 102` | `228 → 240 → 253` | requires lineage review; not automatically a new root |
| CHG | `178 → 203 → 228` | `228 → 236 → 243` | later candidate follows the prior structure |

The correct model is a candidate lineage graph, not “first candidate” or “last candidate.” A later candidate can be:

- `MACRO_ROOT` — starts a new connected structure;
- `INTERNAL_NESTED` — remains inside the parent anchors;
- `CONTINUATION` — makes a higher low and extends the parent impulse;
- `NEW_STRUCTURE` — follows invalidation or a structural reset.

The production safety boundary remains unchanged: Elliott output is machine-generated evidence, not an objectively confirmed count, and no automatic BUY or trading behavior is allowed.

## Research changes

Untracked research work is under `research/02-multiscale-wave-counter/`:

- `counter.py` — standalone multi-scale candidate counter and lineage linker;
- `test_counter.py` — focused prototype tests;
- `multiscale-counter.html` — shareable chart prototype with candidate markers and visible lineage;
- `README.md` — prototype scope and limitations.

The prototype now links candidates using anchor order, higher-low continuity, containment, and impulse extension. The HTML universe view uses a simplified visible lineage mapping; the Python prototype contains the scale-aware research classifier.

## Verification

Passed:

- `PYTHONDONTWRITEBYTECODE=1 .analysis-venv/bin/pytest -q research/02-multiscale-wave-counter/test_counter.py` — `3 passed`;
- HTML parser check — passed;
- `node --check /tmp/signalix_counter_check.js` — passed;
- `git diff --check` — passed;
- full 237-symbol research snapshot scanned: 1,658 candidates classified as 668 macro roots, 680 continuations, and 310 internal/nested candidates.

The temporary research preview was served at:

`http://91.98.72.120:8766/02-multiscale-wave-counter/multiscale-counter.html`

This is not production runtime evidence. Production Docker/API/browser verification was not performed in this session.

## Deferred production work

Do not copy the prototype HTML into `/mvp`. Resume by:

1. Porting the lineage representation into `backend/wave3_candidate_engine.py`.
2. Preserving the canonical `setup-candidates` contract and current publication gates.
3. Exposing lineage as explicit Daily evidence and chart markers, without silently changing lanes or enabling actionability.
4. Adding production regression fixtures for CRC, GUNKUL, CENTEL, CHG, AIMIRT, AWC, and BGRIM.
5. Running backend tests, served `/api/setup-candidates` verification, and desktop/390px `/mvp` chart review.
6. Updating the owning design/architecture documentation if the production contract changes.

## Git and runtime state

- Branch: `release/signalix-mvp-stable`.
- Production branch was aligned with origin before this session.
- This handoff is an untracked research record pending the documentation closeout commit; current repository also contains preserved owner/research artifacts outside this handoff.
- No production files, database, containers, services, deployment, commit, or push were changed in this session.
- The research preview server is temporary and separate from `/mvp` and production APIs.
