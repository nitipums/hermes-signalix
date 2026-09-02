# กำหนด Reconciliation, Safe Mode และ Kill Switch

- Parent: `MAP.md`
- Type: `wayfinder:grilling`
- Status: OPEN
- Blocked by: `01-innovestx-settrade-api-sandbox`, `02-risk-policy-contract`

## Question

เมื่อข้อมูล stale, network timeout, order status unknown หรือ broker position ไม่ตรงกับ internal state ระบบต้อง reconcile, freeze, alert, recover และเปิด execution กลับอย่างไร โดยห้าม blind retry และต้องมี append-only audit evidence
