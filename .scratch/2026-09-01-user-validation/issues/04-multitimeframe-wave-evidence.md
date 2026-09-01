# 04: Multi-Timeframe Wave Evidence and Provisional Candles

**What to build:** Make Wave identification easy to follow across Day, Week, and 60m while preserving source-timeframe honesty and showing current/unclosed candles as explicitly provisional.

**Blocked by:** 01 — Freshness and Decision-Lane Separation

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Day chart shows Daily structural markers with exact source timeframe, timestamp, price, rule, and snapshot identity.
- [ ] Week and 60m can show Daily markers only as clearly labelled contextual overlays: `Daily source · not 60m wave` (or exact equivalent).
- [ ] 60m setup markers (trigger/stop/target) remain separate from Daily structural Wave markers.
- [ ] Current/unclosed candles render only with explicit provisional status and exact timestamp/as-of.
- [ ] Day/Week/60m views expose a clear data boundary so direction differences are explainable.
- [ ] Wave Evidence explanation is prominent and readable in the drawer, including alternative/missing evidence and policy.
- [ ] Chart truncation/windowing preserves marker alignment.
- [ ] Desktop and 390px mobile browser journeys verify marker visibility, drawer scroll, timeframe controls, and no overflow.
