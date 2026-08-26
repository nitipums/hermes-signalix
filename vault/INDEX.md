# INDEX — Signalix Project Vault

> **Master catalog ของ Signalix Level-4 vault** (Karpathy-style LLM-wiki index)
> อัปเดตทุกครั้งที่มีไฟล์เข้า/ย้าย/ลบหรือเปลี่ยนสถานะ
> Governance: [[Documentation-Governance]]
> Active work source: `Execution-Pipeline.md` + linked focused plans. Kanban is audit/archive only.

## 0. Governance gate

อ่าน `Documentation-Governance.md` ก่อนเพิ่มหรือแก้ note ใดๆ ทุกครั้ง

- Product direction → `Product-Strategy-Market-to-Action.md`
- Atomic decisions → `Decisions.md`
- Current architecture/ops → `Architecture.md`, `Components.md`, `Deployment.md`, `Execution-Pipeline.md`
- Historical evidence → dated handoffs / `Postmortems/`
- Work status → owner decision required; do not mirror into notes/facts

## 1. วิธีการใช้

- **AI (ทุก profile):** เช็ค index นี้ก่อนเขียน handoff/note — ไฟล์ซ้ำหรือยัง?; หลังแก้ อัปเดตสถานะ
- **Arm:** เปิดอ่านว่า "เรื่อง Signalix X อยู่ไฟล์ไหน"
- **ลำดับความน่าเชื่อถือข้อมูล:** โค้ดจริง/DB/log  > vault note  > memory/fact
- Secrets: ห้ามเข้าบ้านี้ (อยู่ใน `/root/signalix/.env` / settradeupdated.env)

## 2. Catalog — ไฟล์ถาวร (evergreen)

| ไฟล์ | เรื่อง | สถานะ | หมายเหตุ |
|---|---|---|---|
|| `Documentation-Governance.md` | Authority map, status vocabulary, cleanup policy | ✅ current | Read before adding/editing notes |
|| `Memory-Cleanup-Candidates.md` | Fact/memory cleanup record | ✅ current | Cleanup completed 2026-08-26; historical vault preserved |
|| `README.md` | ภาพรวม project | ✅ current | Status reconciled 2026-08-26; stable MVP `4c7bf9c` |
|| `Canonical-Source-of-Truth-2026-08-25.md` | Current repo/worktree/runtime authority | ✅ current | Sole source authority after cutover |
|| `Krungsri-Credit-Balance-Marginable-2026-08-25.md` | Owner-selected marginable list, rates, permissions, refresh policy | ✅ current | PDF effective 2026-08-25; dataset in `backend/marginable_securities.json` |
| `Architecture.md` | สถาปัตยกรรม/data flow/containers/webhook | ✅ active | **MVP server, watch-only lanes, canonical chart timeframes reconciled 2026-08-25** |
| `Components.md` | รายละเอียด component | ✅ active | |
| `Deployment.md` | Runbook/deploy | ✅ active | |
| `Phases.md` | แผนระยะ | ✅ active | |
| `Decisions.md` | การตัดสินใจ product/tech | ✅ active | |
| `Execution-Pipeline.md` | Pipeline สัญญาณ | ✅ active | |
| `Product-Feedback.md` | ฟีดแบ็กจาก tester | ✅ active | Mali เขียนได้ |
| `Product-Strategy-Market-to-Action.md` | Canonical Signalix product strategy: Market View → Action + Decision-quality Setup Copilot | ✅ active | **Daily VCP Watchlist default + All VCP full view; official historical SET50/SET100 membership sync at stable `0ab8c44`; old Daily/Explorer contract superseded** |
| `VCP-Finder-MVP.md` | Current VCP-first MVP surface, table, grouping, filter, and provenance contract | ✅ active | primary MVP contract |
| `VCP-Replay-1M-2026-08-26.md` | One-month point-in-time VCP replay baseline | ✅ current baseline | 20 daily snapshots, 18,620 rows, no-lookahead |
| `Testing-and-Architecture.md` | Testing setup + UI asserts + architecture + 2026-08-19 acceptance evidence | ✅ active | coverage lineage + overview/cards API + browser evidence |
| `Browser-and-Freshness-Verification.md` | การ verify browser/freshness | ✅ active | |
| `Postmortems/README.md` | Postmortem registry | ✅ active | |
| `Postmortems/2026-08-19-Intraday-Evaluator-Import.md` | Intraday ExecStopPost import failure | ✅ current | fixed; reusable systemd/package-import lesson |
| `2026-08-20-Intraday-Master-Watchdog-Handoff.md` | Settrade master authority + 15m intraday/watchdog | ✅ current | |
| `2026-08-20-Dashboard-Data-Policy-Update-Handoff.md` | Pull-all yfinance + COLOR exclude | ✅ current | ดู Decisions.md + Architecture.md |
| `2026-08-21-Intraday-E2E-Reliability-Incident.md` | Intraday fetch → DB → dashboard E2E fix | ✅ current | dashboard refresh, watchdog tolerance, morning monitor |
| `2026-08-21-Intraday-Feed-Availability-Handoff.md` | 11 unavailable 60m feeds + COLOR boundary | ✅ current | feed-specific cooldown; Daily preserved |
|| `Postmortems/Chart-and-60m-Stabilization-2026-08-25.md` | Chart latency/60m feed stabilization + MVP timeframe follow-up | 🟡 historical evidence | prior candidate; not source authority |

## 3. Catalog — Handoff ตามวัน (dated, historical)

| ไฟล์ | เรื่อง | สถานะ |
|---|---|---|
| `2026-08-13-Intraday-Dashboard-Handoff.md` | Intraday dashboard 60m | 🟡 **HISTORICAL** (ถูก sequential 2026-08-18 ทับ) |
| `2026-08-15-EOD-Scan-Optimization-Handoff.md` | Settrade EOD 30 workers/860 sym | 🟡 **HISTORICAL** (metric เก่า, architecture เปลี่ยน) |
| `2026-08-15-Khim-End-to-End-Fix-Handoff.md` | Khim fix | 🟡 **HISTORICAL** |
| `2026-08-15-Signalix-Taxonomy-Redesign-Handoff` | taxonomy 718 redesign | 🟡 **HISTORICAL — SUPERSEDED** (โดน stage-first ทับ; ดู `2026-08-17-Stage-First...`) |
| `2026-08-17-Stage-First-Dashboard-Redesign-Handoff.md` | **Stage-first 1,143 ORD redesign** | 🟡 **HISTORICAL** — design/migration evidence; current UI contract verified from source/artifact/browser |
| `Bee-Handoff-Browser-Infrastructure-2026-08-15.md` | Browser infra fix | 🟡 **HISTORICAL** — permanent fix อยู่ใน skill `signalix-browser-permanent-fix` |
| `Roadmap-Kanban.md` | Archived Kanban mirror | 🟡 historical | Audit only; Markdown pipeline is active work source |
| `Team-Operating-Model.md` | Team roles, providers, review loop | 🟡 historical | Provider snapshot 2026-08-22; current work source is Markdown pipeline |

## 4. สถานะซิงค์กับ fact_store

- **2026-08-26:** Consolidated 24 overlapping Signalix skills into `signalix-production-delivery`, `signalix-dashboard`, and `signalix-screening-replay`; created Hermes umbrellas `hermes-operations` and `memory-documentation-governance`. Originals remain reversible under `_archived_consolidation_20260826`.

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

- **2026-08-25 (canonical source cutover)**: `release/signalix-mvp-stable` at `3ec48f7` became current. `/root/signalix` is the only registered worktree and production bind-mount source; temporary feature/quarantine/audit copies were retired after stable push.

- **2026-08-25 (stable MVP candidate `595eb49`)**: verified owner-only `/mvp` served from `signalix_dashboard`; added immediate Explorer filters, real `1D`/`1W`/`60M` chart controls, moved chart controls/indicator values below the plot, and reconciled current docs. Full suite: 246 passed; live 1D/1W/60M 200, retired 15M 400.
- **2026-08-25 (MVP watch lanes `195a090`)**: added `RISING MOVERS / WATCH ONLY` and `CAUTION / DO NOT CHASE` without weakening READY/PRE_READY; sanitized legacy projection labels at the canonical artifact boundary.

- **2026-08-23 (SUPERSEDED 2026-08-26)**: Owner approved `Daily Shortlist` as the default decision surface and retained the stage-first dashboard as secondary `All Stocks Explorer`; replaced by VCP Finder · 60m as the current MVP core. Historical design remains for audit.
- **2026-08-22**: Added cross-team review resolution to `Product-Strategy-Market-to-Action.md` after independent Ploy, Prae, View, Mali, Nida, and Khim reviews; direction PASS, implementation readiness REVISE; added regime/state/ranking/lifecycle/acceptance clarifications.
- **2026-08-22**: Added the approved **Decision-quality Setup Copilot** direction to the canonical `Product-Strategy-Market-to-Action.md`: experienced self-directed trader, setup-first, regime-aware queue, hard gates + quality ranking, immutable event-based outcomes, and explicit non-goals.
- **2026-08-22**: Team/provider closeout: created Prae PM, revived View designer, verified local A2A/profile boundaries, and recorded the provider allocation in `Team-Operating-Model.md`.
- **2026-08-22 (historical):** A live Kanban audit was recorded in `Roadmap-Kanban.md`; after the 2026-08-23 owner decision, Kanban remains audit/archive only and the Markdown execution pipeline is the active work source.
- **2026-08-21**: Kanban board management — promoted 5 P0 contract tasks to `running` (4×khim, 1×lite), created `Roadmap-Kanban.md` auto-sync from live board, updated INDEX.md
- **2026-08-21 (Intraday E2E)**: Fixed intraday-only path so every 60m fetch/evaluation rebuilds dashboard artifacts from the existing Daily scan; watchdog now tolerates expected partial-success, uses 90m candle / 30m evaluator thresholds, and morning no-agent monitor checks/self-heals served freshness. Commits `6ffb62e`, `d7b8a39`; 30 focused tests passed; live browser showed updated `Last Scanned`.
- **2026-08-21 (Intraday feed availability)**: Added `intraday_feed_status` with 3-failure/24h cooldown policy for 11 Settrade-empty 60m symbols; preserved Daily/EOD eligibility; dashboard now explicitly shows `60m unavailable · Daily EOD`; COLOR remains instrument-master excluded. Verified active intraday universe 913, canonical scan/dashboard 898, verifier PASS, focused tests 27 passed.
- **2026-08-19**: สร้าง INDEX นี้; เริ่มรีเฟรช Architecture.md ให้ตรง stage-first
- **2026-08-19 (P0-4)**: intraday event boundary — `scan_history.py` ต่อ `resolved_daily_event_id`/`reconciled_at` + observation dedup ต่อ candle + append-only mutation triggers; `reconcile_intraday_events_at_eod` ลิงก์ lineage เมื่อ EOD ยืนยัน; endpoint `/intraday/events`; tests: `test_intraday_event_boundary.py` + integration บน test DB (Architecture.md อัปเดตแล้ว)

- **2026-08-19**: Setup Radar / Stage + Actionable Setup State redesign `DONE` — `backend/setup_state.py` (quality gate + proximity pure functions); wired into `screening.group_scan_results` → `daily_state`; `build_dashboard.serialize` exposes `setup_quality`/`setup_proximity`/`radar`/`radarBadge` + stage→proximity→rs sort; `dashboard_template.html` Setup Radar section + proximity pills, L2 UI pills removed. Verified: 231 tests green; Docker scan produces 84 radar items (READY/WATCH badges); S3/S4 proximity.state=null; browser confirms Setup Radar heading, `data-prox` pills, no legacy L2 refs; screenshot at `/tmp/radar_screenshot.png`. Commits: 0d3a1ee (setup state), d383c9f (wiring), be99772 (serialize/sort/UI), 19b6c53 (test updates).

- **2026-08-20**: Settrade master became sole ORD authority; weekly sync + auto-reactivation/absent→inactive policy added. Intraday moved to 15-minute cadence, 10:00–16:45 Bangkok, 60m limit=4; old watchdog disabled and new 15m watchdog installed. Scanner keeps short-history symbols as explicit `INSUFFICIENT_HISTORY` non-signal rows. See `2026-08-20-Intraday-Master-Watchdog-Handoff.md`.

- **2026-08-20 (Data semantics)**: Removed the 15% yfinance price-gap skip in `update_data.py` — owner directive: pull ALL symbols, no price-gap filter. Excluded `COLOR` from `symbol_master` (status='excluded', reason: Settrade Symbol not found) so it drops from scan + dashboard; official master sync will auto-reactivate if it reappears. Verified: 931 active / 1 excluded, scan universe 904, COLOR absent from snapshot + served dashboard. See `2026-08-20-Dashboard-Data-Policy-Update-Handoff.md` + Decisions.md.

- **2026-08-20 (Dashboard UX)**: Moved Setup Radar to its own nav page (`#radar`), wrapped stage summary + filter rows + search in a sticky control cluster (`#ctrlSticky`), and stage-filter clicks auto-scroll to results. Tests 17/17 + related 47 passed; served HTML verified in real browser desktop + mobile (no h-scroll, sticky works at scrollY=1200). Commit `edaffbd`.

- **2026-08-21 (Intraday E2E)**: Fixed intraday-only path so every 60m fetch/evaluation rebuilds dashboard artifacts from the existing Daily scan; watchdog now tolerates expected partial-success, uses 90m candle / 30m evaluator thresholds, and morning no-agent monitor checks/self-heals served freshness. Commits `6ffb62e`, `d7b8a39`; 30 focused tests passed; live browser showed updated `Last Scanned`.

- **2026-08-21 (Instrument authority)**: Added active-ORD `instruments.py`, migration 004, bounded SET factsheet refresh timer (20 symbols/cycle), and `/instruments` APIs. Verified factsheet run: 20/20 fetched and parsed; production `company_profiles` now has 20 `set_factsheet` rows. Yahoo remains fallback. Focused authority/scraper/dashboard tests pass.