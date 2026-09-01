# กำหนด Paper Trading และ Deterministic Replay Contract

- Parent: `MAP.md`
- Type: `wayfinder:prototype`
- Status: OPEN
- Blocked by: `01-innovestx-settrade-api-sandbox`, `02-risk-policy-contract`, `03-exit-trailing-stop-contract`

## Question

Paper simulator และ replay ต้องจำลอง market session, market-order fills, slippage, fees, partial/unknown fills, corporate actions, restart/idempotency และ no-lookahead อย่างไร เพื่อพิสูจน์ lifecycle และ P&L ก่อนแตะ live broker
