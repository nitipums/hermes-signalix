# 04: Elliott Wave Chart Evidence and Markers

**What to build:** Let Arm see how the Daily Elliott interpretation was formed by rendering exact chart-linked identification points and a concise explanation without re-deriving wave logic in the frontend.

**Blocked by:** 02 — Data-Block and No-Setup State Contract

**Status:** ready-for-agent

## Files
- `backend/elliott_structure_engine.py`
- `backend/setup_candidate_contract.py`
- `backend/mvp_chart_db.py`
- `backend/frontend/app.js`
- `backend/frontend/index.html`
- `backend/test_elliott_wave_contract.py`
- `backend/test_mvp_frontend_contract.py`

## Tests
- Exact marker timestamp/price fixtures for CRC, BGRIM, and AWC
- Daily vs 60m marker visibility/mapping tests
- Chart-window truncation alignment tests
- Browser happy path and marker click-to-explain journey at desktop/390px

## Live endpoints
- `http://127.0.0.1:3001/mvp`
- `http://127.0.0.1:3001/api/setup-candidates?page=1&page_size=50`
- `http://127.0.0.1:8000/health/readiness`

## Acceptance criteria
- [ ] Provide Wave 1 low/high, Wave 2 pullback low, Wave 3 close confirmation, tested-high/structure-break, trigger, trade stop, and thesis invalidation markers.
- [ ] Marker objects contain id, kind, timeframe, timestamp, price, label, wave role, source, confidence, evidence refs, and snapshot identity.
- [ ] Add toggleable Wave Evidence layer and click-to-explain rule/evidence/alternative/missing/policy details.
- [ ] Do not project Daily markers onto 60m without explicit mapping.
- [ ] Produce payload plus rendered browser evidence by the first 15-minute checkpoint.
