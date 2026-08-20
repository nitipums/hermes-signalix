# INDEX — Signalix Project Vault

> **Master catalog ของ Signalix Level-4 vault** (Karpathy-style LLM-wiki index)
> อัปเดตทุกครั้งที่มีไฟล์เข้า/ย้าย/ลบหรือเปลี่ยนสถานะ
> Source of truth: โค้ดจริงใน `/root/signalix/` + DB + ตัว container

## 1. วิธีการใช้

- **AI (ทุก profile):** เช็ค index นี้ก่อนเขียน handoff/note — ไฟล์ซ้ำหรือยัง?; หลังแก้ อัปเดตสถานะ
- **Arm:** เปิดอ่านว่า "เรื่อง Signalix X อยู่ไฟล์ไหน"
- **ลำดับความน่าเชื่อถือข้อมูล:** โค้ดจริง/DB/log  > vault note  > memory/fact
- Secrets: ห้ามเข้าบ้านี้ (อยู่ใน `/root/signalix/.env` / settradeupdated.env)

## 2. Catalog — ไฟล์ถาวร (evergreen)

| ไฟล์ | เรื่อง | สถานะ | หมายเหตุ |
|---|---|---|---|
| `README.md` | ภาพรวม project | ✅ active | |
| `Architecture.md` | สถาปัตยกรรม/data flow/containers/webhook | ✅ active | **อัปเดตแล้ว 2026-08-19: stage-first + intraday 60m full active ORD; current production shape workers=938/batch=938/delay=0; evaluator uses package module invocation** |
| `Components.md` | รายละเอียด component | ✅ active | |
| `Deployment.md` | Runbook/deploy | ✅ active | |
| `Phases.md` | แผนระยะ | ✅ active | |
| `Decisions.md` | การตัดสินใจ product/tech | ✅ active | |
| `Execution-Pipeline.md` | Pipeline สัญญาณ | ✅ active | |
| `Product-Feedback.md` | ฟีดแบ็กจาก tester | ✅ active | Mali เขียนได้ |
| `Product-Strategy-Market-to-Action.md` | Strategy: Market View → Action | ✅ active | plan หลัก |
| `Testing-and-Architecture.md` | Testing setup + UI asserts + architecture + 2026-08-19 acceptance evidence | ✅ active | coverage lineage + overview/cards API + browser evidence |
| `Browser-and-Freshness-Verification.md` | การ verify browser/freshness | ✅ active | |
| `Postmortems/README.md` | Postmortem registry | ✅ active | |
| `Postmortems/2026-08-19-Intraday-Evaluator-Import.md` | Intraday ExecStopPost import failure | ✅ current | fixed; reusable systemd/package-import lesson |
| `2026-08-20-Intraday-Master-Watchdog-Handoff.md` | Settrade master authority + 15m intraday/watchdog | ✅ current | |

## 3. Catalog — Handoff ตามวัน (dated, historical)

|| ไฟล์ | เรื่อง | สถานะ |
||---|---|---|
|| `2026-08-13-Intraday-Dashboard-Handoff.md` | Intraday dashboard 60m | 🟡 **HISTORICAL** (ถูก sequential 2026-08-18 ทับ) |
|| `2026-08-15-EOD-Scan-Optimization-Handoff.md` | Settrade EOD 30 workers/860 sym | 🟡 **HISTORICAL** (metric เก่า, architecture เปลี่ยน) |
|| `2026-08-15-Khim-End-to-End-Fix-Handoff.md` | Khim fix | 🟡 **HISTORICAL** |
|| `2026-08-15-Signalix-Taxonomy-Redesign-Handoff` | taxonomy 718 redesign | 🟡 **HISTORICAL — SUPERSEDED** (โดน stage-first ทับ; ดู `2026-08-17-Stage-First...`) |
|| `2026-08-17-Stage-First-Dashboard-Redesign-Handoff.md` | **Stage-first 1,143 ORD redesign** | ✅ **current** — สถาปัตยกรรมปัจจุบัน (LAYER1/LAYER2) |
|| `Bee-Handoff-Browser-Infrastructure-2026-08-15.md` | Browser infra fix | 🟡 **HISTORICAL** — permanent fix อยู่ใน skill `signalix-browser-permanent-fix` |
|| `Roadmap-Kanban.md` | **Experimental Kanban board** (Markdown) | ✅ **current** — synced from all plans + actual verified 2026-08-19 |

## 4. สถานะซิงค์กับ fact_store

- Stage-first / FULL ORD / LAYER1-LAYER2 ↔ fact 117, 121, 112; `MEMORY.md`
- Intraday sequential 60m ↔ fact (Memory 2026-08-18) + `signalix-backfill-and-parity` skill
- Test สถานะ ↔ fact 119 (126 unit + 6 integration)
- A2A/Browser infra ↔ fact 71/122 + skills

## 5. สิ่งที่ต้องทำ (backlog จริงตรวจพบ 2026-08-19)

~~1. **รีเฟรช `Architecture.md`** — เขียนใหม่ให้ตรง stage-first ✅ เสร็จ 2026-08-19~~
~~2. **Mark handoff เก่า** — ทั้ง 5 ตัว mark HISTORICAL/SUPERSEDED เรียบร้อย ✅~~
~~3. **Coverage lineage 1,143/934/718** — `coverage_report.json` + runtime validator fixed ✅~~
~~4. **Snapshot performance** — overview/cards API + static HTML async load; snapshot 47.8s → 2.73s ✅~~ *P0-1 commit 3906af1: compact overview contract (card `market` + explicit `unknown` projection)*
~~5. **Rendered acceptance** — real desktop/mobile/filter/modal/chart/error contract ✅~~
6. *(ว่าง — reopen เมื่อเจองานใหม่)*

## 6. Changelog

- **2026-08-19**: P0-1 compact overview data contract `DONE` (commit 3906af1) — `/dashboard/cards/compact` + `/dashboard/overview` + `/dashboard/cards`; RED→GREEN 9/9; browser mobile verified (390px no h-scroll; refresh-failure retains compact cards)

- **2026-08-19**: สร้าง INDEX นี้; เริ่มรีเฟรช Architecture.md ให้ตรง stage-first
- **2026-08-19 (P0-4)**: intraday event boundary — `scan_history.py` ต่อ `resolved_daily_event_id`/`reconciled_at` + observation dedup ต่อ candle + append-only mutation triggers; `reconcile_intraday_events_at_eod` ลิงก์ lineage เมื่อ EOD ยืนยัน; endpoint `/intraday/events`; tests: `test_intraday_event_boundary.py` + integration บน test DB (Architecture.md อัปเดตแล้ว)

- **2026-08-19**: Setup Radar / Stage + Actionable Setup State redesign `DONE` — `backend/setup_state.py` (quality gate + proximity pure functions); wired into `screening.group_scan_results` → `daily_state`; `build_dashboard.serialize` exposes `setup_quality`/`setup_proximity`/`radar`/`radarBadge` + stage→proximity→rs sort; `dashboard_template.html` Setup Radar section + proximity pills, L2 UI pills removed. Verified: 231 tests green; Docker scan produces 84 radar items (READY/WATCH badges); S3/S4 proximity.state=null; browser confirms Setup Radar heading, `data-prox` pills, no legacy L2 refs; screenshot at `/tmp/radar_screenshot.png`. Commits: 0d3a1ee (setup state), d383c9f (wiring), be99772 (serialize/sort/UI), 19b6c53 (test updates).

- **2026-08-20**: Settrade master became sole ORD authority; weekly sync + auto-reactivation/absent→inactive policy added. Intraday moved to 15-minute cadence, 10:00–16:45 Bangkok, 60m limit=4; old watchdog disabled and new 15m watchdog installed. Scanner keeps short-history symbols as explicit `INSUFFICIENT_HISTORY` non-signal rows. See `2026-08-20-Intraday-Master-Watchdog-Handoff.md`.