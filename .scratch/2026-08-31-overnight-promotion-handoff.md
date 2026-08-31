# Signalix overnight session — T1–T9 promotion + anchor policy (2026-08-31)

## Final state
- Full T1–T9 spine PROMOTED to `release/signalix-mvp-stable` (commits 8573b9d..e07785e lineage).
- Backend + dashboard containers reloaded; container/host file shas verified identical.
- Full backend suite green (667 tests) on release.
- Lifecycle production e2e on :8000: PASS (GET 200/404, POST review 200/retry/409, 401 forged, append-only trigger verified). Migration 007 applied to canonical DB (0 rows, triggers on).
- Served `/api/setup-candidates` via :3001: 237 universe, honest lanes from live DB builder.

## Anchor policy (owner option A, executed overnight)
- `relaxed-1bar-scaled-20260831`: 1-bar legs, scaled 1% significance (3% for 2+ bars).
- Funnel: anchors pass 15/237 (was 1/237). Remaining 222 DATA_BLOCKED = honest fail-closed (no qualifying 60m structure in prior 30 bars).
- Served dist: AVOID 10 (do-not-chase), EXTENDED 8, INVALIDATED 7, DATA_BLOCKED 227; wave states flow (W3_CONT 40, W4 33, W5 31, W1 29, W2 variants 18, UNKNOWN 86). No REVIEW_NOW tonight — legitimate post-market state.
- Commits: c7529e0 (OHLC fix), 4724305 (timeframe stamp), f9508e2 (1-bar legs), e07785e (scaled significance).

## Root causes found & fixed overnight
1. Release engine lacked T2 OHLC fail-closed fix → cherry-picked af41452 (c7529e0).
2. `screening.load_symbol_intraday` never stamped attrs["timeframe"] → every 60m setup fail-closed (4724305).
3. Dashboard container runs its own Python process — bind mount does NOT reload imports; `docker restart signalix_dashboard` required after engine changes.
4. Stale `mvp_snapshot.json` (pre-promotion, 931 legacy items) is preferred by the route; falls back to live DB build correctly. Refreshes at next EOD/intraday build.

## Remaining for tomorrow
- Public desktop/390px browser journey on promoted spine (final T8 gate).
- Evaluator caller wiring for lifecycle persistence (owner decision).
- 3% → scaled policy review after a few sessions of real data.
- alerts/auto-trading remain OFF.
