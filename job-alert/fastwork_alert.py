#!/usr/bin/env python3
"""ดึงงานใหม่จาก Fastwork Jobboard ที่ตรงเงื่อนไขใน config.json แล้วส่งอีเมลแจ้งเตือน

ตัวแปรแวดล้อม (ตั้งเป็น GitHub Secrets):
  SMTP_USER      บัญชีที่ใช้ส่ง เช่น you@gmail.com
  SMTP_PASSWORD  App Password ของ Gmail (ไม่ใช่รหัสผ่านปกติ)
  MAIL_TO        อีเมลผู้รับ (คั่นหลายคนด้วย ,) ถ้าไม่ตั้งจะส่งหา SMTP_USER
  SMTP_HOST      ค่าเริ่มต้น smtp.gmail.com
  SMTP_PORT      ค่าเริ่มต้น 465 (SSL)
  DRY_RUN=1      พิมพ์ผลแทนการส่งเมล
"""
import html
import json
import os
import re
import smtplib
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

API_URL = "https://jobboard-api.fastwork.co/api/jobs"
JOB_URL = "https://jobboard.fastwork.co/jobs/{id}"
HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
STATE_PATH = HERE / "seen_jobs.json"
MAX_SEEN = 2000


def fetch_page(page, page_size=50):
    params = {
        "page": page,
        "page_size": page_size,
        "order_by[]": "inserted_at",
        "order_directions[]": "desc",
        "filters[0][field]": "kind",
        "filters[0][value]": "standard",
    }
    req = urllib.request.Request(
        API_URL + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def parse_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fetch_recent_jobs(since, max_pages):
    jobs = []
    for page in range(1, max_pages + 1):
        body = fetch_page(page)
        data = body.get("data") or []
        jobs.extend(data)
        times = [parse_time(j.get("inserted_at")) for j in data]
        times = [t for t in times if t]
        total_pages = (body.get("meta") or {}).get("total_pages") or page
        if not data or page >= total_pages or (times and min(times) < since):
            break
    return jobs


def flatten_text(obj):
    """รวมข้อความทุกฟิลด์ (รวมฟิลด์ซ้อน เช่น tag/category) เพื่อใช้ค้นคำ"""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in flatten_text(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in flatten_text(v)]
    return []


def budget_value(job):
    """คืนงบสูงสุดที่อ่านได้ (บาท) หรือ None ถ้าไม่ระบุ"""
    nums = []
    for key in ("budget", "budget_min", "budget_max", "min_budget", "max_budget", "price"):
        val = job.get(key)
        if isinstance(val, (int, float)):
            nums.append(float(val))
        elif val is not None:
            for s in flatten_text(val) or [str(val)]:
                nums += [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s)]
    return max(nums) if nums else None


def matches(job, cfg):
    text = " ".join(flatten_text(job)).lower()
    any_kw = [k.lower() for k in cfg.get("keywords_any", []) if k]
    all_kw = [k.lower() for k in cfg.get("keywords_all", []) if k]
    exclude = [k.lower() for k in cfg.get("keywords_exclude", []) if k]
    if any_kw and not any(k in text for k in any_kw):
        return False
    if not all(k in text for k in all_kw):
        return False
    if any(k in text for k in exclude):
        return False
    min_budget = cfg.get("min_budget") or 0
    if min_budget:
        b = budget_value(job)
        if b is not None and b < min_budget:
            return False
    return True


def budget_label(job):
    b = job.get("budget")
    if b in (None, "", [], {}):
        return "ไม่ระบุ"
    if isinstance(b, (dict, list)):
        return " ".join(flatten_text(b)) or json.dumps(b, ensure_ascii=False)
    return str(b)


def description(job, limit=300):
    for key in ("description", "detail", "details", "content", "body"):
        if isinstance(job.get(key), str) and job[key].strip():
            text = re.sub(r"<[^>]+>", " ", job[key])
            text = re.sub(r"\s+", " ", text).strip()
            return text[:limit] + ("…" if len(text) > limit else "")
    return ""


def build_email(jobs):
    lines, items = [], []
    for j in jobs:
        url = JOB_URL.format(id=j.get("id"))
        title = j.get("title") or "(ไม่มีชื่องาน)"
        budget = budget_label(j)
        desc = description(j)
        posted = j.get("inserted_at", "")
        lines.append(f"- {title}\n  งบ: {budget} | โพสต์: {posted}\n  {url}\n  {desc}\n")
        items.append(
            f'<li style="margin-bottom:14px"><a href="{html.escape(url)}"><b>{html.escape(title)}</b></a><br>'
            f'<small>งบ: {html.escape(budget)} · โพสต์: {html.escape(str(posted))}</small><br>'
            f'<span style="color:#555">{html.escape(desc)}</span></li>'
        )
    text = f"พบงานใหม่ที่ตรงเงื่อนไข {len(jobs)} งาน\n\n" + "\n".join(lines)
    body = f"<p>พบงานใหม่ที่ตรงเงื่อนไข {len(jobs)} งาน</p><ul>{''.join(items)}</ul>"
    return text, body


def send_email(subject, text, html_body):
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    to = os.environ.get("MAIL_TO") or user
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)


def load_seen():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []


def save_seen(seen):
    STATE_PATH.write_text(json.dumps(seen[-MAX_SEEN:], ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def main():
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    since = datetime.now(timezone.utc) - timedelta(hours=cfg.get("lookback_hours", 24))
    jobs = fetch_recent_jobs(since, cfg.get("max_pages", 5))
    seen = load_seen()
    seen_set = set(map(str, seen))

    new = []
    for j in jobs:
        jid = str(j.get("id"))
        t = parse_time(j.get("inserted_at"))
        if jid in seen_set or (t and t < since):
            continue
        if matches(j, cfg):
            new.append(j)
    print(f"ดึงมา {len(jobs)} งาน, ตรงเงื่อนไขและยังไม่เคยแจ้ง {len(new)} งาน")

    if new:
        text, html_body = build_email(new)
        subject = f"[Fastwork] งานใหม่ตรงเงื่อนไข {len(new)} งาน"
        if os.environ.get("DRY_RUN"):
            print(subject + "\n" + text)
        else:
            send_email(subject, text, html_body)
            print("ส่งอีเมลแล้ว")

    # จำทุกงานที่เห็นแล้ว (ไม่ใช่แค่ที่ตรงเงื่อนไข) เพื่อไม่ต้องเช็กซ้ำ
    for j in jobs:
        jid = str(j.get("id"))
        if jid not in seen_set:
            seen.append(jid)
            seen_set.add(jid)
    if not os.environ.get("DRY_RUN"):
        save_seen(seen)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # ให้ Actions แสดงเป็น failed
        print(f"ERROR: {e}", file=sys.stderr)
        raise
