# Fastwork Job Alert

ดึงงานใหม่จาก https://jobboard.fastwork.co/jobs ทุก 30 นาทีด้วย GitHub Actions แล้วส่งอีเมลเฉพาะงานที่ตรงเงื่อนไข (งานเดิมจะไม่แจ้งซ้ำ)

## ตั้งค่า (ครั้งเดียว)

1. สร้าง Gmail App Password: https://myaccount.google.com/apppasswords (ต้องเปิด 2-Step Verification ก่อน)
2. ไปที่ repo → **Settings → Secrets and variables → Actions → New repository secret** แล้วเพิ่ม
   - `SMTP_USER` = อีเมล Gmail ที่ใช้ส่ง
   - `SMTP_PASSWORD` = App Password 16 หลัก
   - `MAIL_TO` = อีเมลผู้รับ (ไม่ใส่ก็ได้ จะส่งหา `SMTP_USER`)
3. แก้เงื่อนไขใน `job-alert/config.json`
4. ไปที่แท็บ **Actions → Fastwork job alert → Run workflow** เพื่อทดสอบ

## เงื่อนไขใน `config.json`

| ฟิลด์ | ความหมาย |
|---|---|
| `keywords_any` | ต้องมีคำใดคำหนึ่ง (ว่าง = ไม่กรอง) |
| `keywords_all` | ต้องมีครบทุกคำ |
| `keywords_exclude` | ถ้ามีคำเหล่านี้จะไม่แจ้ง |
| `min_budget` | งบขั้นต่ำ (บาท) งานที่ไม่ระบุงบจะยังแจ้ง |
| `lookback_hours` | ดูเฉพาะงานที่โพสต์ภายในกี่ชั่วโมง |
| `max_pages` | จำนวนหน้าสูงสุดที่ดึง (หน้าละ 50 งาน) |

คำค้นไม่สนตัวพิมพ์เล็ก/ใหญ่ และค้นจากทุกฟิลด์ของงาน (ชื่อ รายละเอียด หมวดหมู่)

## รันบนเครื่อง

```bash
DRY_RUN=1 python job-alert/fastwork_alert.py   # พิมพ์ผลออกจอ ไม่ส่งเมล
```
