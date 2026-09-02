# 02: Data-Block and No-Setup State Contract

**What to build:** Make user-facing state semantics honest: distinguish no Daily data from no 60m data, show `No setup detected` when data exists but no qualifying 60m anchor exists, and show `Risk invalid` when Fib/risk cannot produce a safe plan.

**Blocked by:** 01 — Diagnostic Data and Setup-Reason Report

**Status:** ready-for-agent

## Files
- `backend/mvp_api.py`
- `backend/trade_setup_engine.py`
- `backend/setup_candidate_contract.py`
- `backend/test_trade_setup_engine.py`
- `backend/test_setup_candidate_contract.py`
- `backend/test_setup_candidates_api.py`

## Tests
- Missing Daily, missing 60m, stale, invalid OHLCV, no-anchor, invalid Fib/risk fixtures
- Full contract regression suite for canonical lane mapping

## Live endpoints
- `http://127.0.0.1:3001/api/setup-candidates?page=1&page_size=50`
- `http://127.0.0.1:8000/health/readiness`

## Acceptance criteria
- [ ] Separate data reason and setup reason in the canonical contract; exact field placement may be chosen by Lite + Codex.
- [ ] `NO_DAILY_DATA` and `NO_60M_DATA` remain explicit blocked reasons.
- [ ] Valid Daily/60m data without qualifying anchors is `NO_SETUP_DETECTED` and maps to `SETUP_FORMING` or `DAILY_CANDIDATE`, never generic `DATA_BLOCKED`.
- [ ] Invalid Fib/risk is `RISK_INVALID` and never falls back to legacy output.
- [ ] Full 237-row lane/reason distribution is reproducible.
- [ ] Produce non-empty test/probe artifacts by the first 15-minute checkpoint.
