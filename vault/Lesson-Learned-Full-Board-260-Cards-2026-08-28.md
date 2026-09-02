# Lesson Learned — Full Board 260 Cards 355 Runs

> **Scan:** `2026-08-28 09:3x ICT` — `sqlite kanban.db` 260 tasks / 355 runs / 154 logs + every worker log under `/root/.hermes/kanban/boards/signalix/logs/*.log` (confirmed via `session_search` doesn't cover — checked live DB)
> **Prior delta:** รอบก่อนสแกนแค่ 13 runs เมื่อคืน (2026-08-27 23:05→28 08:11). รอบนี้คือ **ทั้งบอร์ด** ตั้งแต่วันแรก
> **Authority:** `vault/Execution-Pipeline.md` + `vault/Lesson-Learned-2026-08-28-Loop-Retrospective.md` (เมื่อคืน) + ไฟล์นี้ (ทั้งบอร์ด). Kanban เป็น execution state เท่านั้น.

## Snapshot ทั้งบอร์ด

- Tasks 260: `done 113 + blocked 1 + archived 146` — 260 คือ 180+ ที่พี่อาร์มบอก (อีก 146 archived ยังนับเป็นงานที่เคยทำ)
- Runs 355: `completed/pass` ส่วนใหญ่, `waste = reclaimed/timed_out/crashed/blocked/failed/gave_up = 148 runs (41.7%)`
- Logs on disk 154 ใบ — 106 ใบไม่มี log file (archived ก่อนระบบ log หรือ reclaim ก่อน spawn)
- Waste by profile: khim 50, lite 28, nida 27, view 23, prae 8, mali 4, bee 4, ploy 3 — khim/lite/view รับงานหนักสุด วนมากสุดตามสัดส่วน
- Tasks multi-run 58 ใบ — หัวแถว 15 ใบมี 5–15 runs (ดูตารางล่าง)

## Top 30 หนักสุด (lines / heartbeat / preparing)

| Rank | Task | Lines | Heart | Prep | Owner | Title cut |
|---|---|---|---|---|---|---|
|1| t_7e1964f8 |23588|59|175|lite|Decision-quality Setup Copilot Contract Gate|
|2| t_c266f5e4 |5068|6|329|prae→khim→nida|P0 Defect D5: Dashboard JS Syntax Error Stuck at 0% (15 runs)|
|3| t_5393ba7f |5031|1|225|lite|P0-4 Daily vs intraday event boundary (35m, 5 runs)|
|4| t_66d2850c |4974|0|288|view|P0 UI Redesign Correction (6 runs)|
|5| t_a4166c1c |4619|1|185|lite|P0-1 Compact overview data contract (5 runs)|
| ... | ... | ... | ... | ... | ... | ... |
|~10| t_3961d070 |2530|6|305|khim|P0 UI Redesign Implement (49m)|
|~11| t_7cca0a57 |2374|6|409|khim|P0 Provenance and Freshness (6 runs, prep 409 สูงสุด)|
|~12| t_3755a74f |2358|0→17*|137|khim|Khim remediation v4 (37m) *count via events|

\* t_3755a74f heart นับผ่าน `task_events` =17, grep ใน log ได้ 0 เพราะ format ใหม่

**Prep >150 = 21 ใบ** = สัญญาณ `terminal/read_file` วน — ส่วนใหญ่เป็น `grep -rn`, `ls -la`, `python -m pytest` ซ้ำ 150–400 ครั้งต่อใบ

**Heart >10 = 3 ใบเท่านั้น** — `t_7e1964f8 (59!)`, `t_3cc8dfde (11)`, `t_10c92fdc (11)` — นอกนั้น orchestrator guard ยังไม่จำเป็น แต่เมื่อคืนต้องเติม

## ใครวนตรงไหน — ทั้งบอร์ด

### 1) Crash cluster 08-19 และ 08-21 — วนจาก infra ไม่ใช่ logic
- **08-19 14:03 — 5 ใบพร้อมกัน** `t_a4166c1c, t_c7479220, t_5393ba7f, t_2c47fce1, t_ee34cb3b` : `crashed` รัว 4–5 ครั้งใน 1 นาที — Gateway/dispatcher ไม่มี `signalix_dashboard` หรือ worktree path ผิด (error: `no such file`, `exit 128`)
- **08-21 21:22 — 5 ใบพร้อมกัน** `t_7cca0a57, t_2bb5cee8, t_e86c97df, t_704520bf, t_aaaf4311` : `crashed → blocked` ภายในนาทีเดียว — สัญญาณ gateway restart หรือ Postgres/Redis ล่มชั่วคราว
- **Pattern:** crash หมู่ = infra, ไม่ใช่ worker วน — แต่ทำให้ทุกใบแตกเป็น 4–6 runs โดยไม่จำเป็น

### 2) Reclaim / blocked loop ยาว — วนจากการไม่ block ให้ชัด
- **แชมป์: t_c266f5e4 (15 runs)** — Prae เปิดมาเป็น `reclaimed×3 → blocked (corrupted artifact) → khim review_requested → nida blocked×2 → reclaimed×5 → prae completed` — 5068L, 329 prep, error keyword 331 ครั้ง — ส่วนใหญ่คือ `sed -n 411p | od -c` วนหา JS corruption ซ้ำ
- **รอง: t_46601185 (9 runs, nida)** — `reclaimed 30m → blocked (exploratory) → reclaimed → blocked → blocked → crashed×3 → completed` — QA วนเพราะไม่มี artifact ชัดแล้วโดน Bee block ซ้ำ
- **t_73900fec (9 runs, lite)** — `blocked×7 ติดกัน` รอ `t_c6075ac3 Nida Re-QA` PASS ก่อน — ไม่ได้วนงาน แต่ `blocked_reason` ซ้ำทำให้ task ไม่ promote (block-loop breaker ทำงาน)
- รวม `waste runs 148` กระจาย 08-19:19, 08-22:29, 08-23:33 — 3 วันนี้คือวันที่ทำ UI redesign / visual refresh / action queue พร้อมกัน (งานใหญ่ชนกัน)

### 3) Prep วน (read/terminal) — วนจากการหาไฟล์ไม่เจอ
- **Top prep 409:** `t_7cca0a57 khim Provenance` — `grep -n "compact|data_freshness"` + `find ... -name *.py` วน 400 ครั้งเพราะ contract กระจายหลายไฟล์ ไม่มี index รวม
- **t_2bb5cee8 / t_3961d070 / t_abcc7800 / t_2c47fce1** 250–380 prep — ทั้งหมดเป็น P0 contract ใหญ่ที่ต้องแก้หลายไฟล์พร้อมกัน (khim รับ 4 ใบ) — ไม่มี split
- สาเหตุร่วม: worker ไม่มี `files:` list ใน card body → ต้อง `find/grep/ls` เดา

### 4) Heartbeat วน — เดิมน้อย แต่มี 1 เคสหนัก
- `t_7e1964f8 lite` 59 heartbeats ใน 18m → doc 40 หน้าเขียน `Product-Strategy-Market-to-Action.md` — heartbeat ถี่เพราะงานเขียนยาว แต่มี artifact ชัด (contract_v0.2.0) เลยไม่ถือว่า waste
- เคสเดียวที่ heartbeat-only จริงคือ `t_3755a74f` เมื่อคืน (17 heartbeats ว่าง) — patch ไปแล้ว

### 5) เมื่อคืน (13 runs) — ย่อยของทั้งบอร์ด
- **t_925028aa 5 runs / 2215L / 262 prep** — resource reclaim + timed_out 23m — ที่สุดของเมื่อคืน แต่เทียบทั้งบอร์ดยังไม่ติด top 10 lines
- **t_cbd7e900 4 runs / 119 localhost block** — เดียวที่เจอ browser locality ทั้งบอร์ด
- **t_e8a856c5 schema `artifacts: []`** — เดียวที่เจอทั้งบอร์ด

## Waste timeline ทั้งบอร์ด

| วันที่ | waste runs | เหตุการณ์ |
|---|---|---|
|08-19|19|Crash cluster + P0-1..P0-4 4 ใบแตกพร้อมกัน|
|08-21|16|Crash cluster 21:22 หมู่ (gateway)|
|08-22|29|D5 JS defect + Fresh Visual วน (15+9 runs)|
|08-23|33|UI redesign + Action Queue + Outcome Log 7 ใบแตก (crashed 4 ครั้งรวด)|
|08-24|4|สงบ — แทบไม่มี waste|
|08-28|5|เมื่อคืน 5 runs (resource/reclaim/schema/heartbeat/content)|

→ **บทเรียน:** ทุกครั้งที่เปิดงานใหญ่พร้อมกันหลายใบ (08-22, 08-23) waste พุ่ง 2–3× — ต้อง stagger

## Lesson synthesis — ทั้งบอร์ด vs เมื่อคืน

| ประเด็น | เมื่อคืน (13 runs) | ทั้งบอร์ด (355 runs) | สรุป |
|---|---|---|---|
|Stale runtime|เจอ 3 ใบ|ทั้งบอร์ดไม่เจอนอกเมื่อคืน — เฉพาะ `daily_shortlist.py` 23:01|เมื่อคืนคือ unique, แต่กฎใหม่คุ้มทั้งบอร์ด|
|Resource reclaim|5 runs|148 waste runs รวม crash cluster 35 ใบ|เมื่อคืนเป็นเศษเสี้ยว — root cause ใหญ่คือ 08-19/21 crash หมู่|
|Browser locality|1 ใบ|1 ใบเท่านั้น|ไม่ต้องกลัวระบาด แต่กฎยังต้องล็อก|
|Schema|1 ใบ|1 ใบเท่านั้น|edge case|
|Heartbeat-only|1 ใบ|3 ใบ (59,11,11) แต่ 2 ใบแรกมี artifact|เมื่อคืนหนักสุดจริง|
|Content REVISE|3 ใบ|วนทั้งบอร์ด: P0 contract 4 ใบแก้ 5–6 รอบ, UI redesign 7 ใบแก้ 5–7 รอบ|เมื่อคืนย้ำ pattern เดิม|
|Prep วน|137 prep|21 ใบ prep>150, top 409|เมื่อคืนเล็กกว่าค่าเฉลี่ยทั้งบอร์ด|

## Prevention — อัพเดทครบแล้ว (ทำไปเมื่อเช้า)

1. **Lesson-Learned 2 ไฟล์:** `vault/Lesson-Learned-2026-08-28-Loop-Retrospective.md` (เมื่อคืน) + ไฟล์นี้ (ทั้งบอร์ด) — เป็นคู่กัน
2. **Execution-Pipeline.md:** 7 gates (card scoping / stale runtime / resource / browser / schema / heartbeat / no parallel)
3. **Skills patched:** `kanban-worker-common` + `hermes-kanban-ops` (ENFORCED + checklist 5 ข้อ)
4. **Memory + fact 190:** durable gates
5. **เพิ่มเติมจากทั้งบอร์ด:**
   - **Stagger งานใหญ่:** อย่าเปิด P0 5 ใบ + UI 3 ใบพร้อมกัน (08-22/23 waste 29–33)
   - **Crash cluster guard:** ถ้า `crashed` หมู่ >3 ใบใน 1 นาที → ให้ถือว่า gateway/DB ล่ม หยุด dispatch 10m อย่า reclaim ทันที
   - **Card body ต้องมี `files:`** — ลด prep 150–409 ครั้ง (ทุกใบ prep สูงคือไม่มี files list)
   - **Doc ใหญ่ (lite) ต้อง split:** `t_7e1964f8` 23588L คือเขียน 40 หน้าในใบเดียว — ควร split เป็น 3 docs + 1 review

## ต้องทำต่อ (ถ้าพี่อาร์มอนุมัติ)

- [ ] เพิ่ม `crash-cluster guard` ใน `hermes-kanban-ops` (3+ crashed/min → pause dispatch)
- [ ] Template การ์ดใหม่: `files:/tests:/endpoints:/first artifact 15m` — บังคับทุกใบ
- [ ] Archive log เกิน 5000L: `t_7e1964f8` 23588L ควรหมุน log หรือ split งาน

## Evidence

- `sqlite /root/.hermes/kanban/boards/signalix/kanban.db` — 260 tasks, 355 runs (58 multi-run)
- `/root/.hermes/kanban/boards/signalix/logs/*.log` — 154 files, top 30 scanned, 21 prep >150, 148 waste runs
- `vault/Lesson-Learned-2026-08-28-Loop-Retrospective.md` + ไฟล์นี้
- Skills: `kanban-worker-common`, `hermes-kanban-ops` (+ `references/signalix-2026-08-28-loop-retrospective.md`)
