# Signalix user-validation redesign packet — 2026-09-01

Authority/spec: `docs/superpowers/specs/2026-09-01-user-validation-refresh-card-wave-contract.md`

This packet captures Arm's TASCO feedback and the dependency-ordered implementation slices. T01–T04 are engineering tickets; T05 is the owner semantic confirmation gate. Automatic trading, broker execution, alerts, and evaluator auto-caller are out of scope and remain pending/future.

Order:

```text
01 freshness/decision lanes
   ├── 02 explicit refresh/overview controls
   ├── 03 card hierarchy
   └── 04 multi-timeframe evidence/provisional candles
          ↓
       05 Arm Wave confirmation
```
