# 01: Diagnostic Data and Setup-Reason Report

**What to build:** Produce a complete 237-symbol diagnostic report so Arm can distinguish unavailable Daily data, unavailable 60m data, stale/invalid evidence, no setup detected, and invalid risk/Fib without changing user-facing behavior yet.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## Files
- `backend/mvp_api.py`
- `backend/trade_setup_engine.py`
- `backend/setup_candidate_contract.py`
- `backend/test_setup_candidates_api.py`
- `.scratch/2026-09-01-signalix-review/`

## Tests
- Focused diagnostics/contract tests
- Full 237-row read-only API aggregation

## Live endpoints
- `http://127.0.0.1:3001/api/setup-candidates?page=1&page_size=50`
- `http://127.0.0.1:8000/health/readiness`

## Acceptance criteria
- [ ] Aggregate all 237 eligible symbols, not only the first page.
- [ ] Report separate counts and symbol lists for Daily unavailable, 60m unavailable, stale/invalid evidence, no setup detected, and risk invalid.
- [ ] Preserve current source behavior; diagnostic artifact is additive/read-only.
- [ ] Include exact `as_of`, universe, evaluated/returned counts, and lane totals.
- [ ] Produce a non-empty JSON/Markdown artifact by the first 15-minute checkpoint.
