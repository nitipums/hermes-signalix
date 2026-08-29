# Signalix Scan & Evaluation Logic Map

> **STATUS: REVIEW_REQUIRED**
> **Date:** 2026-08-29
> **Purpose:** อธิบายว่า Signalix ตอนนี้ scan/evaluate อะไร อย่างไร และจุดไหนซ้ำซ้อน
> **Scope:** source review ของ branch `release/signalix-mvp-stable`; ยังไม่ใช่ runtime acceptance

## 0. Executive summary

ตอนนี้ Signalix ไม่ได้มี scan/evaluate pipeline เดียว แต่มี 4 ชั้นที่ทำงานขนานกัน:

1. **Daily legacy/stage-first pipeline** — สแกน ORD ทั้งตลาดด้วย Trend Template + Daily VCP + Fib/RSI/readiness แล้วจัด Stage/Phase/Queue
2. **Isolated 60m VCP Finder** — ตรวจ VCP morphology จากแท่ง 60m โดยตรง แล้วสร้าง VCP state/lane แยกอีกชุด
3. **Intraday overlay** — เอาราคา 60m ล่าสุดมาเทียบ reference ของ Daily แล้วเปลี่ยน effective group/action ชั่วคราว โดยตั้งใจไม่เปลี่ยน Daily truth
4. **Shadow/replay policies** — ทดลอง sequence ล่าสุดและ decision lanes ใหม่ แต่ยังไม่ควรเป็น serving authority

**ข้อสรุปสั้น:** ความซับซ้อนไม่ได้มาจาก indicator เยอะอย่างเดียว แต่มาจากการมี **หลายระบบตัดสินใจที่อธิบายคำว่า “พร้อม/รอ/ไม่ทำ” คนละภาษา** แล้วนำมาแสดงใกล้กัน

```mermaid
flowchart TD
    U[Full TH ORD universe] --> D[Daily data / price_data]
    U --> I[60m data / intraday_price_data]

    D --> S[screening.scan_universe]
    S --> T[8-condition Trend Template + RS]
    S --> V[Legacy Daily VCP: 3 shrinking ranges]
    S --> R[Daily RSI / Fib / breakout / stop / readiness]
    T --> C[stage_classifier: Stage + Phase]
    R --> C
    C --> Q[setup_state: quality + proximity]
    Q --> AQ[action_queue: one queue]
    C --> RK[ranking.py: 40/30/20/10]
    AQ --> DS[Daily Shortlist / Explorer projection]
    S --> P[persist Daily run + observations + lifecycle]

    I --> F[vcp_finder_60m]
    F --> M[60m pivots / contractions / base / volume / breakout]
    M --> VS[VCP state + VCP lane]
    VS --> VW[/api/vcp-finder Watchlist / Explorer]

    P --> O[intraday_evaluator]
    I --> O
    O --> OV[temporary intraday effective group/action]
    OV --> UI[dashboard overlay]

    F -. optional replay .-> SH[sequence-policy shadow v2]
    VS -. replay only .-> DH[decision-policy shadow v2]

    style DS fill:#d9f2d9
    style VW fill:#d9f2d9
    style SH fill:#fff2cc
    style DH fill:#fff2cc
    style OV fill:#d9eaf7
```

สีเขียว = serving surfaces คนละ pipeline, สีฟ้า = overlay, สีเหลือง = shadow/replay

## 1. Pipeline A — Daily scan / stage-first

### 1.1 Universe

`backend/app.py:1188-1314` เรียก `scan_universe(min_conditions=0)` เพื่อประเมินทุก row ที่ scan ได้ แล้วค่อยแยกกลุ่ม/publish ภายหลัง

`backend/screening.py:232-257` เลือก symbol จาก `price_data` ที่ `market='TH'` และ `instrument_type='ORD'`; ตัด inactive จาก `symbol_master` แต่ไม่ควร pre-filter ด้วย stale/price/liquidity ตาม architecture rule

**ข้อควรระวัง:** ในทางปฏิบัติ `scan_universe` ยังสามารถหายจากผลลัพธ์ได้เมื่อไม่มี bar ใช้ได้ (`screening.py:647-653`) หรือเกิด exception ระหว่าง analysis แล้ว `continue` (`screening.py:663-666`) จึงยังไม่ใช่ “ทุก ORD มี observation เสมอ”

### 1.2 Per-symbol calculations

`backend/screening.py:363-440` ทำ:

- load Daily OHLCV (ถ้า history สั้น ใช้ 60m fallback)
- `trend_template()` — Trend Template 8 เงื่อนไข
- `detect_vcp()` — legacy Daily VCP
- `buy_zone()` — Fib 50/62 และ stop
- `trade_readiness()` — Daily RSI, MA slope, breakout level, volume ratio, BUY/HOLD/WAIT/BREAK/OVERBOUGHT
- position sizing และ analysis metrics

ตัวเลขหลักจาก `backend/signal_core.py:15-17, 118-151`:

| Evidence | Current rule |
|---|---|
| History | `MIN_DAYS=260` |
| RS | 252-session relative return percentile, scan threshold `RS >= 50` |
| Trend Template | 8 conditions: MA150/200/50 stack, MA200 slope, 52w low/high, RS |
| Legacy Daily VCP | last 60 bars split 3 legs; ทุก leg ต้องแคบลงจาก leg ก่อน |
| Daily breakout | close เทียบ prior 20-day high |
| Daily setup | RSI/Fib/MA/volume/readiness; emits legacy statuses |

### 1.3 Canonical-ish Stage/Phase + setup overlays

`backend/screening.py:445-544` เรียก `stage_classifier.classify_stage()` แล้วติด:

- **Stage:** `S1_basing`, `S2_uptrend`, `S3_distributing`, `S4_down`
- **Phase:** `base_early`, `base_tight`, `breakout_new`, `breakout_retest`, `breakout_extended`, `uptrend_pullback`, `waiting_breakout`, `topping`, `declining`, `broken`
- **Primary state:** 7-state compatibility field
- `setup_quality` + `setup_proximity` จาก `setup_state.py`
- `scan_group`: `breakout_new`, `uptrend_pullback`, `waiting_breakout`, `base`, `down_or_broken`
- `ranking`: attach ตอนท้าย

Stage logic อยู่ที่ `backend/stage_classifier.py:97-190`:

- S2 ต้อง bullish MA stack และ MA50/150/200 slope >= 0.5%
- S4 ต้องต่ำกว่า MA200 และมี bearish stack หรือ MA200 slope <= -0.5%
- ที่เหลือส่วนใหญ่ตก S1 หรือ S3 ตาม stack/slope
- Phase ใช้ persisted breakout event ก่อน แล้ว fallback ไป rolling trigger

Setup overlay อยู่ที่ `backend/setup_state.py:28-117`:

- **quality pass** = range 20d <= 12% + volume ratio < 1.0 + ไม่ extended
- **proximity** = `forming`, `near_trigger`, `action`, `extended`
- S3/S4 ไม่มี actionable proximity

### 1.4 Daily action/presentation

`backend/action_queue.py:70-123` map หนึ่ง symbol ไปหนึ่ง queue:

- `intraday_emerging`
- `fresh_breakout`
- `pre_breakout`
- `retest_watch`
- `qualified_pullback`
- `monitor_only`
- `avoid_new_longs`

จากนั้น `backend/daily_shortlist.py:323-...` ใช้ hard gates เพิ่ม เช่น:

- Daily EOD freshness
- average daily value 20 วัน >= 10m THB
- queue ต้องเป็น Daily queue
- ไม่ broken/declining/S3/S4
- คำนวณ shortlist score แยกอีกสูตร

Production `/scan` (`backend/app.py:1293-1300`) publish เฉพาะ `breakout_new + uptrend_pullback` แต่ยัง persist/display ทุกกลุ่มที่ scan ได้

## 2. Pipeline B — isolated 60m VCP Finder

`backend/vcp_finder_db.py:373-...` ใช้ active ORD + committed 60m bars แล้วเรียก `backend/vcp_finder.py:413-579`

### 2.1 Morphology

`VCP60Config` (`vcp_finder.py:23-42`) ใช้:

| Evidence | Current rule |
|---|---|
| Minimum data | 80 bars; pattern window 60 bars |
| Shape | confirmed pivots, sequence `high-low-high-low-high` |
| Base | depth 5–35%; latest contraction <= 12% |
| Contraction | ratio <= 0.85 |
| Volume dry-up | <= 0.80 |
| Breakout volume | >= 1.50x |
| Breakout buffer | max(0.5%, 0.1 ATR) above pivot |
| Extension | >3% from pivot |
| Failure | below prior pivot low / invalidation |

ผลลัพธ์มี state เช่น `FORMING`, `READY`, `NEAR_TRIGGER`, `CONFIRMED`, `EXTENDED`, `FAILED`, `STALE`, `NOT_VERIFIED`, รวม `actionable` และ evidence เต็มชุด

### 2.2 Serving surface

`backend/mvp_routes.py:65-97` ให้ `/api/vcp-finder` โดยมี filter `state`, `actionable`, `focused`, `review`, `daily_watchlist`

`backend/vcp_finder_db.py:602-861` ทำ projection/lane เพิ่ม freshness, quality, invalidation coherence, Daily context, liquidity และ caps ของ watchlist

**ความหมายสำคัญ:** นี่ไม่ใช่แค่ Layer 2 ของ Daily scan แต่เป็น **VCP detector อีกตัวที่มี state/lane/actionability ของตัวเอง**

## 3. Pipeline C — intraday overlay

`backend/intraday_evaluator.py:60-84, 123-207`:

1. load latest canonical Daily scan
2. load latest 60m price
3. เทียบกับ Daily Fib zone / breakout trigger / stop
4. สร้าง `intraday_state` และ append `intraday_transitions`
5. สร้าง emerging breakout event ได้เมื่อราคา 60m แตะ/ทะลุ Daily trigger

เจตนาถูกต้อง: 60m ไม่ควร overwrite official Daily state และ EOD reconciliation ทำใน `scan_history.py:948-1110`

แต่ในเชิง UX ถ้าเอา `effective_group/action` มาโชว์ใกล้ Daily label มากเกินไป trader อาจเข้าใจว่า Daily decision เปลี่ยนแล้ว ทั้งที่เป็น observation overlay

## 4. Pipeline D — shadow/replay

### Sequence shadow

`backend/vcp_finder.py:248-410` ทดลองเลือก **latest non-broken sequence** แทน compatibility selection; ยังมี field `promotion_allowed=False`

เอกสาร replay ระบุว่าการเลือก pivot ต่างกันมาก และยังไม่มี owner approval ให้เปลี่ยน serving behavior

### Decision shadow

`backend/vcp_decision_policy.py:206-225` สร้าง non-serving lanes:

- `REVIEW_NOW`
- `PREPARE`
- `EVENT_WATCH`
- `RESEARCH`
- `DO_NOT_CHASE`
- `DATA_BLOCKED`

policy นี้มี quality, entry coherence, liquidity, marginable, price และ freshness logic ของตัวเอง แต่ยังเป็น replay/shadow input ไม่ใช่ serving authority

## 5. อะไรคือ gate, อะไรคือ label, อะไรคือ presentation

| Layer | ทำหน้าที่ | สถานะปัจจุบัน |
|---|---|---|
| Universe | กำหนด symbols ที่ถูก evaluate | authoritative intent; มี silent-drop gaps |
| Data validity | history/feed/freshness | decision evidence; ต้อง fail-closed |
| Trend Template | 8-condition Daily trend quality | authoritative ใน Daily legacy path |
| Legacy Daily VCP | contraction hint | authoritative ใน Daily legacy path แต่ morphology ง่าย |
| Stage/Phase | trend story + lifecycle phase | intended canonical แต่ยังมี duplicate classifier |
| Setup quality/proximity | quality gate + entry timing | decision gate สำหรับ Daily shortlist |
| Action queue | ทำ/รอ/monitor/avoid projection | serving presentation decision |
| Ranking | sort candidates | presentation; มีหลายสูตร |
| 60m VCP morphology | dedicated intraday VCP state | authoritative ใน VCP Finder path |
| Intraday evaluator | current price overlay | overlay เท่านั้น ไม่ควรแก้ Daily truth |
| Shadow policies | ทดลอง policy | replay-only; ไม่ควร serve |

## 6. จุดซ้ำซ้อน/เสี่ยงสับสน

### A. มี Daily state หลายภาษา

`stage_classifier.py` ระบุว่ามาแทน 3 ระบบ แต่โค้ดยังมีครบ/ยัง reachable:

1. `signal_core.trade_readiness.status` = `BUY/HOLD/OVERBOUGHT/BREAK/WAIT`
2. `daily_setup_state.classify_daily_state()` = 7 primary states
3. `stage_classifier.classify_stage()` = Stage + Phase + primary_state
4. `setup_state.py` = quality/proximity
5. `action_queue.py` = 7 action queues

ดังนั้น symbol เดียวอาจมี status, phase, proximity และ queue ที่ดูเหมือนขัดกัน แม้แต่ละ field จะมีเหตุผลของตัวเอง

### B. คำว่า VCP หมายถึง 2 detector

- Daily legacy: 3 range legs แบบหยาบ
- 60m finder: pivot sequence + depth + contraction + dry-up + breakout volume + invalidation

ทั้งคู่ถูกเรียกว่า VCP แต่ตอบคนละคำถามและใช้ threshold คนละชุด

### C. มี ranking หลายชุด

- `ranking.py:23-159` = 40% structure / 30% proximity / 20% risk-reward / 10% market
- `daily_shortlist.py:88-155` = shortlist score ของตัวเอง
- `vcp_finder_db.py:264-278, 602-861` = VCP state/lane ranking
- `vcp_decision_policy.py:181-203` = lane/confirmation/quality/age/liquidity sort

จึงยังไม่มี “ทำไมตัวนี้อยู่บนสุด” แบบ single contract ครอบทุก surface

### D. Threshold ชนกันตาม path/timeframe

| Concept | Daily/stage path | 60m VCP path |
|---|---:|---:|
| Extension | >8% หรือ RSI >=75 | >3% |
| Breakout volume | >=1.2x (Daily setup contract) | >=1.5x |
| Breakout buffer | close >= trigger +1% | max(0.5%, 0.1 ATR) |
| Liquidity | shortlist >=10m; legacy policy constant 15m | VCP projection มี own gate |
| Invalidation | Daily swing/7% style stop | pivot-low/ATR-linked failure |

ความต่างอาจถูกต้องถ้าประกาศชัดว่าเป็นคนละ timeframe/policy แต่ตอนนี้ UI/product language ยังเสี่ยงทำให้ trader เห็นเป็นกฎชุดเดียว

### E. Short-history fallback เสี่ยง semantic mismatch

`screening.py:645-652` ใช้ 60m data แทน Daily history แล้วส่งเข้า `analyze_symbol_db()` ซึ่งคำนวณ Daily-shaped Trend Template/readiness บน frame ที่จริงเป็น 60m แม้ติด `trend_source='intraday_60m'` แล้วก็ตาม

### F. Full-universe intent ยังไม่เท่ากับ full observation

No usable bars และ analysis exception ถูก skip ก่อน persistence ใน Daily path; ถ้าต้องการ audit coverage จริงควรสร้าง explicit `NOT_VERIFIED` / `NO_DATA` / `INSUFFICIENT_HISTORY` observation แทนการหายไป

### G. Shadow boundary/version อ่านยาก

`vcp_finder.py` ใช้ version name `signalix/vcp-finder-60m-v2-latest-sequence` ขณะที่เอกสาร replay แยก v1/v2 และ decision policy shadow อีกตัว ทำให้ต้องอ่านหลายที่กว่าจะรู้ว่าอะไร serve จริง อะไรทดลอง

## 7. Product fit ตาม objective

### ตรง objective

- Full ORD scan เป็นฐาน coverage
- deterministic math ไม่ใช้ LLM คำนวณ signal
- Daily EOD แยกจาก intraday observation โดย intent
- มี trigger, invalidation, freshness, provenance และ immutable lifecycle primitives
- มี dedicated VCP Finder ที่ morphology เหมาะกับ VCP-first กว่า legacy detector

### ยังไม่ตรงเต็มที่

- VCP-first MVP ยังเป็น 2 product surfaces: legacy Daily shortlist + isolated VCP Finder ไม่ใช่ decision spine เดียว
- trader ต้องแปล Stage/Phase/quality/proximity/queue/state/lane เอง
- “actionable” บาง path เป็น review/watch ไม่ใช่ order ซึ่งดีด้าน safety แต่ terminology ยังซ้อน
- invalidation/freshness อาจอยู่คนละ layer กับ action label
- ranking ไม่เป็นหนึ่งเดียว

พลอยสรุปในมุม trader ได้ตรงกันว่า flow ที่ควรเห็นคือ:

```text
FULL universe → Stage → VCP quality → Proximity → Trigger + Invalidation + Risk + Freshness → ทำ / รอ / ไม่ทำ
```

และไม่ควรให้ diagnostic labels หลายชุดแย่งกันเป็น lane หลัก

## 8. ข้อเสนอแนะเรียงลำดับ

### P0 — กำหนด decision spine เดียวก่อนเพิ่ม indicator

เลือกให้ชัดว่า serving authority คือ:

```text
Daily EOD structure/context
+ isolated 60m VCP morphology
→ one decision contract
→ one action lane
```

หรือให้ Daily path เป็น authority แล้ว 60m VCP เป็น evidence enrichment — แต่ต้องเลือก ไม่ใช่ให้สอง path สร้าง actionability ของตัวเอง

### P1 — ลด label ที่ trader ต้องอ่าน

ภายในยังเก็บ evidence ได้เต็ม แต่ UI/export ให้มี primary contract เดียว:

```text
stage: S1-S4
setup_quality: PASS/FAIL/UNKNOWN
entry_state: FORMING/NEAR/CONFIRMED/EXTENDED/INVALIDATED
decision: REVIEW / WAIT / AVOID / DATA_BLOCKED
```

`trade_readiness.status`, legacy `primary_state`, scan group และ VCP lane ควรเป็น compatibility/audit fields หรือ map เข้าสู่ contract เดียว

### P1 — แยก timeframe ใน schema ให้เห็นชัด

ห้ามเอา 60m bars ไปคำนวณ Daily-labelled metrics โดยไม่ประกาศเด็ดขาด แยก `daily_evidence` กับ `intraday_evidence` และถ้า Daily history ไม่พอให้เป็น `INSUFFICIENT_HISTORY` หรือใช้ classifier ที่ชื่อ intraday โดยตรง

### P1 — รวม threshold ownership

สร้าง policy table กลาง แยก `daily_eod` กับ `60m` แต่ละค่ามี owner/version: breakout buffer, volume, extension, RSI, liquidity, invalidation, freshness

### P2 — รวม ranking

เลือก canonical ordering หนึ่งชุด; ส่วน lane cap/filter เป็น presentation และต้องอธิบายเหตุผลที่แยกจาก ranking

### P2 — ทำ full-universe audit ให้ครบ

แทน silent `continue` ด้วย explicit observation status เพื่อให้ count ที่เห็นใน dashboard อธิบายได้ว่า evaluated / no data / error / insufficient history เท่าไร

### P2 — Shadow ต้องมี promotion gate

ใช้ replay แบบ point-in-time เทียบ pivot, state, invalidation, confirmation และ outcome ก่อน promote; จนกว่าจะผ่าน owner acceptance ให้ติด `shadow_only` ชัดใน API/docs

## 9. Practical mental model สำหรับพี่อาร์ม

ถ้าดูแบบไม่ลง code ให้จำแค่นี้:

```text
1) Scan = ดูทุก ORD ว่าโครงสร้าง trend อยู่ Stage ไหน
2) Evaluate = ดูว่า setup มีคุณภาพไหม และราคาอยู่จุดไหนเทียบ trigger/zone
3) 60m VCP = detector ละเอียดอีกตัวสำหรับ VCP โดยเฉพาะ
4) Intraday = แค่ overlay ราคาปัจจุบัน ไม่ใช่เปลี่ยน Daily truth
5) Dashboard = filter/rank/จัด lane; ไม่ควรสร้าง truth ใหม่
6) Shadow = ห้องทดลอง ยังไม่ใช่กฎ production
```

## 10. Evidence / verification boundary

### Checked

- Source files: `screening.py`, `signal_core.py`, `scanner.py`, `stage_classifier.py`, `daily_setup_state.py`, `setup_state.py`, `action_queue.py`, `ranking.py`, `daily_shortlist.py`, `vcp_finder.py`, `vcp_finder_db.py`, `intraday_evaluator.py`, `vcp_decision_policy.py`, `app.py`, `mvp_routes.py`
- Product/acceptance docs: `AGENTS.md`, `vault/Execution-Pipeline.md`, `vault/Product-Strategy-Market-to-Action.md`, `vault/Documentation-Governance.md`
- Codex CLI read-only architecture review, model `gpt-5.6-luna`
- Ploy product/trader challenge (product-level, no code access)
- Git baseline and `git diff --check`

### Not verified

- Live API response, live DB counts, container/runtime version
- Served desktop/mobile rendered behavior
- Current production snapshot contents
- End-to-end tests: Codex attempted focused pytest but collection failed with `FileNotFoundError: No usable temporary directory found`
- No code/deploy/database changes were made for this review

## Appendix — source map

| Concern | Source |
|---|---|
| Daily universe + scan | `backend/screening.py:615-686` |
| Daily calculations | `backend/screening.py:363-440`, `backend/signal_core.py:85-324` |
| Stage/phase | `backend/stage_classifier.py:97-282` |
| Quality/proximity | `backend/setup_state.py:28-117` |
| Queue | `backend/action_queue.py:70-123` |
| Daily persistence | `backend/app.py:1188-1300`, `backend/scan_history.py` |
| 60m finder | `backend/vcp_finder.py:23-42, 140-214, 270-410, 413-579` |
| VCP projection | `backend/vcp_finder_db.py:373-...`, `602-861` |
| Intraday overlay | `backend/intraday_evaluator.py:60-207` |
| Ranking | `backend/ranking.py:23-166`, `backend/daily_shortlist.py:88-155` |
| Shadow policies | `backend/vcp_finder.py:248-410`, `backend/vcp_decision_policy.py:206-225` |
