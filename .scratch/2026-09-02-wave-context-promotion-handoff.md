# Signalix Wave Context promotion handoff

> **STATUS: CURRENT HANDOFF · PROMOTED + RUNTIME VERIFIED · 2026-09-02 ICT**
> Owner: Arm · Final gate: Lite
> Authority: `docs/superpowers/specs/2026-09-02-wave-context-coverage-design.md`

## Timeline

- `2026-09-02` — Owner approved two production displays: Classic `/mvp` and dedicated `/wave-context`.
- `2026-09-02` — Wave context contract, review gating, bounded full-universe replay, and dedicated UI completed through Codex Sol + Lite gates.
- `2026-09-02` — Stable promoted and runtime recreated/restarted.

## Product surface

- `/mvp`: existing Classic Review surface preserved.
- `/wave-context`: new chart-first context review surface.
- Both use the same canonical `/api/setup-candidates`, engine output, and decision lanes.
- Wave 1/3/5 may reach `REVIEW_NOW` only when setup/risk/freshness/completed-60m gates pass. Wave 2/4 remain context-only. `WAVE_3_EXTENDED` is secondary only.

## Verification

- Stable commit: `178742842d607af13c88116de4918839d3f54c24`
- Remote branch SHA matches stable SHA.
- Backend/dashboard/PostgreSQL/Redis healthy after reload.
- `/health/readiness`: HTTP 200.
- `/mvp`: HTTP 200; Classic page title and existing controls preserved.
- `/wave-context`: HTTP 200; dedicated page/assets served.
- `/api/setup-candidates?universe=marginable_long&page=1&page_size=100`: HTTP 200; `237 evaluated`, `100 returned`, `3 pages`; context field present.
- `/api/chart-db/BGRIM?timeframe=1D`: HTTP 200; `250` candles; Daily source metadata present.
- Browser selected `TC` on `/wave-context`; chart loaded `250` candles and context/lane rendered.
- 390px DOM containment: `innerWidth=390`, `clientWidth=375`, `scrollWidth=375`, `body.scrollWidth=375`.
- Browser console/page errors: none.

## Separate verdicts

- Source/tests: **PASS**
- Runtime/API: **PASS**
- Local browser happy path/error preservation: **PASS**
- Public external ingress: **NOT VERIFIED** — `DASHBOARD_PUBLIC_URL` is not configured; local canonical port is the available ingress evidence.

## Deferred

- External public URL acceptance when a public ingress is configured.
- Full-year every-prefix 237 replay remains a performance follow-up; bounded single-as-of 237 gate passed.
- Alerts, broker execution, auto-trading, evaluator auto-caller remain OFF/PENDING.
- Legacy VCP/dashboard deletion remains separate.
