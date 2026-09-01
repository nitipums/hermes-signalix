# Wayfinder Map — Automated Trading for Signalix

## Destination

ระบบเทรดหุ้นไทย SET50 / `marginable_long` ที่เดินทางจาก Signalix candidate ไปสู่ paper trading, human-approved live execution และ bounded auto-execution อย่างปลอดภัย โดยมี deterministic risk/execution gates, replay, audit, reconciliation, safe mode และ kill switch ครบก่อนเปิด live

## Notes

- Domain: Signalix + InnovestX / Settrade Open API
- Planning only: map นี้ยังไม่อนุมัติการสร้าง broker execution หรือเปิด alerts/auto-trading
- Skills: wayfinder, grilling, domain-modeling, Signalix acceptance/data-lineage rules
- Owner: พี่อาร์มตัดสินใจ scope/risk และเป็น final approver ของ production side effects
- Local tracker: child tickets อยู่ใน `tickets/`; `blocked_by` ใช้แทน dependency เพราะยังไม่มี native issue tracker

## Decisions so far

- **Staged promotion path**: Paper → prepare/approve → live human approval → bounded auto-execution หลังผ่าน reliability gate
- **Broker boundary**: InnovestX เป็น broker แรก; ยังต้องยืนยันเส้นทาง Settrade Open API และ sandbox eligibility
- **Decision boundary**: Signalix สร้าง candidate/setup; execution engine เป็น authority สุดท้ายว่าจะส่งคำสั่งได้หรือไม่
- **Portfolio scope**: หุ้นไทย SET50 / `marginable_long`; รุ่นแรก long-only
- **Risk basis**: risk per trade ใช้ broker-reconciled portfolio equity; รวม fee + slippage buffer; invalidation จาก setup ต้องตรวจ freshness/policy ซ้ำ
- **Loss/profit behavior**: loss exit เมื่อถึง invalidation; profit ใช้ trailing stop เริ่มที่ `+1R`; trailing อิง structural/swing low และห้ามลด stop ลง
- **Failure behavior**: stale/unknown/mismatch เข้า safe mode, ห้ามเปิด position ใหม่, reconcile และห้าม blind retry
- **Order/session boundary**: market order เท่านั้นตาม owner decision; regular continuous SET session เท่านั้น; ไม่รวม pre-open/auction/ATC/post-close
- **Holding boundary**: ถือข้ามวันได้เมื่อ holding policy และ protective exit ชัดเจน พร้อม EOD reconciliation
- **Approval payload**: `symbol / side / qty / order type=market / reference price / max slippage / estimated value / stop-invalidation / max loss / reason / expiry`; payload เปลี่ยนแล้ว approval หมดอายุ

## Not yet specified

- เกณฑ์ตัวเลขของ risk per trade, max slippage, liquidity/spread, exposure และ daily loss
- นิยาม trailing stop เชิงตัวเลขของแต่ละ strategy/timeframe และ behavior เมื่อ gap ผ่าน stop
- InnovestX production onboarding, broker identifiers, permissions, rate limits, order lifecycle และ sandbox compatibility
- Paper simulator fidelity, corporate actions, fees, fills, partial fills และ no-lookahead replay contract
- Exact reconciliation cadence, alert channels, operator escalation และ kill-switch recovery procedure
- Promotion evidence package และ bounded auto-execution caps

## Out of scope

- Multi-broker และตลาดนอกหุ้นไทยใน effort นี้
- Short selling, TFEX, options, crypto และ foreign assets
- LLM เป็นผู้คำนวณตัวเลข risk/ราคา หรือผู้อนุมัติคำสั่ง
- เปิด auto-trading จริงก่อนมี explicit promotion decision จากพี่อาร์ม

## Open tickets

ดู child tickets ใน `tickets/` และเลือกทำทีละใบตาม frontier/dependencies
