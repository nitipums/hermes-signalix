# 02: Explicit Refresh and Compact Overview Controls

**What to build:** Replace the large silent-refreshing overview controls with a compact Search/Lane/Refresh toolbar and collapsed Advanced filters. Keep the review set stable until Arm explicitly refreshes or opts into live refresh.

**Blocked by:** 01 — Freshness and Decision-Lane Separation

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Default overview has no silent auto-refresh that replaces rendered rows.
- [ ] Compact toolbar exposes Search, Lane, Refresh, and visible Last updated/update-boundary information.
- [ ] Detailed filters are collapsed by default and remain usable when opened.
- [ ] Optional live-refresh mode is opt-in, visibly enabled, and does not silently replace an open drawer/filter review.
- [ ] Explicit Refresh has loading/error/recovery behavior and preserves canonical counts.
- [ ] Desktop and 390px mobile browser journeys show compact controls without overflow.
- [ ] Regression test proves idle time does not change the rendered review set by default.
