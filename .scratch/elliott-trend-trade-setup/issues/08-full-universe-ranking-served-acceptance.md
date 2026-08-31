# 08: Full-universe ranking + served acceptance

**What to build:** The complete 237-symbol setup-candidates output with lexicographic lane ordering (Elliott confidence → trend → trigger proximity → target-1 R:R → strength/RS/52W-ATH → sector/peer → VCP bonus) and served acceptance across desktop and mobile via the public URL/IP. Error, empty, and data-blocked journeys render honestly; stale data never appears as fresh; alerts and auto-trading remain off.

This is the final read-only acceptance gate for the Elliott/Trend/Trade-Setup replacement.

**Blocked by:** 05 (MVP), 06 (sector/peer/VCP), 07 (lifecycle/owner-review)

**Status:** DONE (source) — T8 ranking commit pending (2026-08-31, Codex + Lite gate); served acceptance **NOT VERIFIED**.

- [x] All 237 eligible symbols return full setup-candidate contracts; excluded 931 symbols never leak into serving (source contract + T1 resolver tests)
- [x] Lane ordering is lexicographic per spec across the full universe; deterministic and stable across runs
- [ ] Served public URL/IP desktop + mobile have no horizontal overflow; error, empty, data-blocked journeys are honest — current container `/api/setup-candidates` 404 and served artifact is stale; no deploy/restart performed
- [x] `git diff --check` clean on the bounded source change; no alerts/broker/auto-trading enabled; production promotion remains gated on served acceptance/owner approval