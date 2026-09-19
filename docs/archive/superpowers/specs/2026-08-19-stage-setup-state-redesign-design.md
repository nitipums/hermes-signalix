# Signalix Stage + Actionable Setup State — Design (2026-08-19)

Status: **Approved in chat** (Arm, 2026-08-19) — design spec pending review.

## 1. Problem

- Current L2 axes (structural `up_leg/pullback/tight_base/down_leg/bounce` + momentum `strong/up/down/ob/os/neu`) are labels, not decisions. Arm: *"L2 เดิมไม่ sacred ถ้าไม่ actionable ให้ redesign จากศูนย์"*.
- Goal: **ใช้ S1/S2 หา actionable setup** — ทุกหุ้น S1/S2 ได้ label setup state ที่บอก "คุณภาพ" และ "จังหวะเข้า" และมี Setup Radar (board สั้นๆ) ที่คัดหุ้นจับตาใกล้เข้า.

## 2. Design decisions (locked with Arm 2026-08-19)

| # | Decision |
|---|----------|
| D1 | **สองชั้น**: `setup_quality` (gate) → `setup_proximity` (timing). Label ทุกตัว + board คัด top picks. |
| D2 | **Quality gate รอบแรก = VCP/tightness** (range 20d แคบ + volume contraction + ไม่ extended). RS / liquidity / SET50 / price band **ยังเป็น filter bar เดิม** — ไม่เอาเข้ากลไก quality. |
| D3 | **Proximity states (enum)**: `forming` / `near_trigger` / `action` / `extended` |
| D4 | **Setup Radar** = quality pass AND proximity ∈ {`near_trigger`, `action`} (READY=`action`, WATCH=`near_trigger` — แยกด้วย proximity เอง ไม่มี tag เพิ่ม) |
| D5 | **S3/S4 ไม่มี actionable state** — เป็น risk bucket แสดงตามเดิม (S3 = ระวัง distribution, S4 = หลีกเลี่ยง) |
| D6 | **แยก field**: `setup_quality` + `setup_proximity` เก็บแยก (ไม่ merge string) |
| D7 | **Stage-first เดิม**: S2 → S1 → S3 → S4 section ตามเดิม; L2 structural/momentum เดิมถูกแทนที่จาก UI (เก็บ code ได้ ไม่แสดง) |
| D8 | **Sort**: stage → proximity (`action` > `near_trigger` > `forming` > `extended`) → `rs` DESC |
| D9 | **ยังไม่ทำ scoring / composite** จนกว่า setup state พิสูจน์ว่า useful (ตาม decision 2026-08-19) |

## 3. Setup state computation

### 3.1 setup_quality (pass/fail)

VCP / tightness gate — ทุกสัญญาณจาก data ที่มีอยู่แล้ว:

- `range_20d_pct` แคบ (threshold: ≤ 12% — reuse เกณฑ์ base tightness ที่มี)
- Volume contraction: `volume_ratio_50` ลดลง / ค่าเฉลี่ย vol 5d < vol 20d (ไม่ต้องมี spike ล่าสุด)
- ไม่ extended: `distance_from_pivot ≤ EXTENDED_FROM_TRIGGER_PCT` และ RSI(14) daily < 75
- fail ถ้าไม่ครบเงื่อนไข quality — แต่ยังได้ proximity label (ทุกหุ้น S1/S2 มี proximity เสมอ)

### 3.2 setup_proximity (per stage)

**S1 (basing):**
- `pivot` = จุด breakout trigger (base high / recent swing high 60d — ใช้ `readiness` trigger / `breakout_evidence.trigger` ที่มีอยู่)
- `near_trigger`: `close ≥ pivot × (1 − SETUP_PROXIMITY_PCT)` (5%)
- `action`: `close > pivot` (fresh breakout; volume confirm อยู่ฝั่ง quality)
- `extended`: `close > pivot × (1 + EXTENDED_FROM_TRIGGER_PCT)` (8%) หรือ RSI ≥ 75
- else → `forming`

**S2 (uptrend):**
- `buy_zone` = fib 50–61.8% ของ up-leg ล่าสุด (มีอยู่แล้วใน `/screen` readiness buy_zone) หรือ proximity MA50
- `near_trigger`: ราคาอยู่เหนือ zone บน ≤ 5% (กำลังย่อเข้ามา)
- `action`: ราคาอยู่ **ใน** zone (fib 50–61.8% / แตะ MA50) + trend intact (above MA200, MA200 slope > 0)
- `extended`: RSI ≥ 75 หรืออยู่ไกลกว่า zone มาก (> 8% เหนือ leg high)
- else → `forming`

### 3.3 Parameters (Bee-gate v1 — เริ่มต้น, เปิดปรับได้)

- `SETUP_PROXIMITY_PCT = 5` (%)
- `EXTENDED_FROM_TRIGGER_PCT = 8` (%)
- `EXTENDED_RSI = 75`
- `TIGHT_RANGE_20D_PCT = 12` (%)
- VCP volume: 5d avg < 20d avg (contraction)

## 4. Data contract

แต่ละ item ใน dashboard snapshot เพิ่ม:

```json
"setup_quality": {
  "pass": true,
  "reasons": ["tight_range", "vol_contraction"],
  "range_20d_pct": 8.2,
  "vol_ratio_50": 0.6
},
"setup_proximity": {
  "state": "near_trigger",
  "pivot": 45.5,
  "distance_pct": 3.1,
  "zone": {"lo": 43.2, "hi": 44.1}
}
```

- ทุก item S1/S2 มี `setup_quality` + `setup_proximity` (แม้ fail/forming)
- S3/S4: `setup_proximity.state = null` (ไม่มี actionable)
- Legacy field `layer2_structural` / `layer2_momentum` / `layer2_group`: เก็บใน payload ได้เพื่อ compat แต่ **UI ไม่ใช้** เป็นตัวจัดกลุ่ม/กรองหลักอีกต่อไป

## 5. UI

- **Setup Radar** section บนสุดของ dashboard (ก่อน stage sections):
  - หัวข้อ "Setup Radar" + count
  - การ์ดเฉพาะ quality pass + near_trigger/action
  - Badge: `READY` (action) / `WATCH` (near_trigger)
- Stage sections เดิมยังอยู่ (S2 → S1 → S3 → S4)
- ต่อ stage section: proximity pills (All / action / near_trigger / forming / extended) — ต่อจากเดิม L2 pills
- Filter bar เดิม (SET50 / value / price band / sector / industry) คงเดิม

## 6. Testing

- Unit: `test_setup_state.py` — quality gate, proximity per stage, params edge (pivot boundary, RSI threshold, S3/S4 null)
- Integration: dashboard snapshot มี field ใหม่ครบ; sort ถูกต้อง
- Regression: stage classifier tests เดิมยังเขียว (stage/phase ไม่ถูกแตะ)
- UI: browser happy path — board โผล่, pills filter ทำงาน, S3/S4 ไม่มี proximity state

## 7. Out of scope (รอบนี้)

- Scoring / composite / ranking weight
- Merge L3 qualifier เข้ากลไก (คงเป็น evidence แยก)
- Actionable state สำหรับ S3/S4 (short/avoid ฝั่ง)
- Auto-fetch fundamentals (Task 9/10 ยังตามเดิม รอคำสั่ง)
