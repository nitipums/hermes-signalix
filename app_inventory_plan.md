# 📦 App Inventory Playground → ปรับเป็น "Mini-ERP Inventory (SAP MM เบาๆ)"

**สั่งโดย:** พี่อาร์ม (Nitipum.s) · 2026-08-12
**flow:** set team → kanban → สร้างของเล่น → ปรึกษาพลอยทำ spex → วางแผน → (ลุยเด็กๆ)
**เจ้าของ final gate:** บี (lite)

---

## 0. บันทึกการแก้ความเข้าใจ (LESSON)
- ❌ เดิม: บีเดาว่า "app inventory" = launcher รายการแอปในเครื่อง (สุ่ม 8 อัน ไม่มี reference)
- ✅ จริง: พี่อาร์มหมายถึง **inventory คล้าย SAP MM (Materials Management) เบาๆ** = ระบบจัดการของ/วัตถุดิบ/สต็อก แบบ ERP เล็ก
- **บทเรียน:** ก่อนสุ่มรายการ/seed ต้องมี reference ชัดเจนจากพี่อาร์มก่อน

## 1. สถานะทีม (set team ✅)
Ping A2A ครบ 5 คน ตื่น: บี/พลอย/มะลิ/ขิม/นิดา · Kanban: `/root/team_kanban.md`

## 2. Spex ใหม่ (จากพลอย 🔮 — SAP MM เบาๆ)
**เป้าหมาย:** Inventory ติดตาม ของ/วัตถุดิบ/สินค้า ของกิจการพี่อาร์ม — ยอดสต็อกต้องย้อนกลับไปที่รายการเคลื่อนไหวได้เสมอ (operational truth ก่อนดวง)
**โมดูลหลัก:**
- **Material Master:** Material Code, ชื่อ, หมวด, หน่วยนับ(UoM), คลัง/ตำแหน่งหลัก, Reorder Point, สถานะ Active/Inactive [+Supplier/Barcode/Lot/Expiry/รูป แบบ optional ตาม reference]
- **Stock:** คงเหลือตาม Material+Warehouse — Available/On-hand/ต่ำกว่า Reorder/มูลค่าคงเหลือ · filter คลัง/หมวด/ใกล้หมด · ค้นหา
- **Movement Ledger (append-only):** Receive(รับ)/Issue(จ่าย)/Transfer(ย้ายคลัง)/Adjust(ปรับ มีเหตุผลบังคับ) · ฟิลด์: เวลา, Material, คลัง, จำนวน, UoM, ราคา/หน่วย(opt), ผู้ทำ, reference, note · **ห้ามแก้ยอดตรง → เปลี่ยนผ่าน movement เท่านั้น**
- **Price/Value เบาๆ:** Last Purchase Price / Average Cost · Stock Value = On-hand × ราคา · ระบุชัด = inventory reporting ไม่ใช่ GL
**UX (Signalix-inspired):** Mobile-first แนวตั้ง dark mode · Home KPI = จำนวน SKU/มูลค่าสต็อก/Low Stock/เคลื่อนไหววันนี้ · Quick actions `+รับเข้า / -จ่ายออก / ปรับยอด` · Material card มีแถบระดับเทียบ Reorder · Movement row สีตามประเภท
**ดวง (Stock Horoscope — garnish เท่านั้น):** micro-copy/badge เช่น "จันทร์เต็มดวง: ตรวจนับสต็อก" · ห้ามสีดวงแทนสถานะ · ห้ามเปลี่ยนยอด/คำเตือนจริง

## 3. ⏳ รอพี่อาร์มระบุ REFERENCE (สำคัญสุด)
พลอยระบุต้องรู้ก่อน build:
- (Q1) Inventory ของอะไร? (กิจการประเภทไหน / พอร์ต / อุปกรณ์ / อื่น)
- (Q2) มีคลังกี่แห่ง (ต้อง Transfer มั้ย)
- (Q3) ใช้ Lot / Serial / วันหมดอายุ หรือไม่
- (Q4) ใครเป็นผู้รับ-จ่ายของ (login/role หรือบันทึกชื่อแค่พอ)

## 4. แผน MVP (รอตอบ Q1–Q4 ก่อนลุยขิม)
**Tech stack (เสนอ):** Flask จิ๋ว + SQLite (materials/stock/movements 3 ตาราง) + UI HTML เดี่ยว mobile-first dark-mode + REST `/api/*`
**RACI:** ขิม=coder(ตาม brief บี) → มะลิ=เล่น → นิดา=QA(error state เช่น ยอดติดลบ/adjust ไม่มีเหตุผล) → บี=final gate → พลอย=ดู spex/ดวง

## 5. ถัดไป
- พี่อาร์มตอบ Q1–Q4 → บีอัปเดต spex+seed → สั่งขิมลุย P1
- หรือบีทำ prototype หน้าเดี่ยวให้ดูก่อน (ใส่ dummy data) ส่งขิมต่อทีหลัง
