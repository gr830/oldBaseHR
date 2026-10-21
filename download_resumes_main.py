import os
import re
import csv
import json
import time
from pathlib import Path
import requests

API_TOKEN = "276383b79eab0ccaf521a3c79a5b197e06c2482cc2546a3d5e16af857d978e51"
BASE_URL = "https://api.huntflow.ru/v2"
EXPORT_DIR = Path("huntflow_full_export")
REQUEST_DELAY = 0.25

if "ВСТАВЬТЕ" in API_TOKEN or not API_TOKEN.strip():
    helper_file = Path("export_huntflow.py")
    if helper_file.exists():
        content = helper_file.read_text(encoding="utf-8")
        match = re.search(r'API_TOKEN\s*=\s*["\']([^"\']+)["\']', content)
        if match and "ВСТАВЬТЕ" not in match.group(1):
            API_TOKEN = match.group(1).strip()

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN.strip()}",
    "User-Agent": "HuntflowFullResumeDownloader/4.0"
}

session = requests.Session()
session.headers.update(HEADERS)


def fetch_resume_payload(account_id: int, app_id: int, ext_id: int, org_nick: str):
    """Опрашивает все известные маршруты API Хантфлоу для получения тела резюме."""
    endpoints = [
        f"{BASE_URL}/accounts/{account_id}/applicants/{app_id}/external/{ext_id}",
        f"{BASE_URL}/accounts/{account_id}/applicants/{app_id}/externals/{ext_id}",
        f"https://huntflow.ru/my/{org_nick}/applicant/{app_id}/external/{ext_id}",
        f"https://huntflow.ru/app/api/my/{org_nick}/applicant/{app_id}/external/{ext_id}"
    ]
    for url in endpoints:
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(url, timeout=25)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                wait_sec = int(resp.headers.get("Retry-After", 10))
                time.sleep(wait_sec)
        except Exception:
            pass
    return None


def generate_readable_html(fio: str, resume_json: dict) -> str:
    """Создает готовую верстку резюме, которую можно открыть в браузере и распечатать в PDF."""
    res_block = resume_json.get("resume") or {}
    data_block = resume_json.get("data") or {}

    title = res_block.get("position") or data_block.get("title") or "Резюме"
    skills = res_block.get("skill_set") or data_block.get("skills") or ""
    if isinstance(skills, list):
        skills = ", ".join(skills)

    experiences = res_block.get("experience") or data_block.get("experience") or []

    exp_html = ""
    for exp in experiences:
        comp = exp.get("company") or ""
        pos = exp.get("position") or ""
        d_from = exp.get("date_from") or exp.get("start") or ""
        d_to = exp.get("date_to") or exp.get("end") or "по наст. время"
        if isinstance(d_from, dict):
            d_from = f"{d_from.get('year', '')}-{d_from.get('month', '')}"
        if isinstance(d_to, dict):
            d_to = f"{d_to.get('year', '')}-{d_to.get('month', '')}"
        desc = (exp.get("description") or "").replace("\n", "<br>")
        exp_html += f"""
        <div style="margin-bottom: 20px;">
            <div style="font-weight: bold; font-size: 16px;">{comp} — <span style="color:#2563eb;">{pos}</span></div>
            <div style="color: #6b7280; font-size: 13px; margin-bottom: 6px;">Период: {d_from} — {d_to}</div>
            <div style="font-size: 14px; line-height: 1.5;">{desc}</div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{fio} — {title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 40px; color: #1f2937; line-height: 1.6; max-width: 900px; margin: auto; }}
h1 {{ margin: 0 0 5px 0; font-size: 26px; }}
h2 {{ color: #4b5563; font-size: 18px; margin-top: 0; font-weight: 500; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; }}
.section-title {{ font-size: 18px; font-weight: bold; margin-top: 30px; margin-bottom: 15px; color: #111827; border-bottom: 1px solid #e5e7eb; padding-bottom: 5px; }}
</style>
</head>
<body>
<h1>{fio}</h1>
<h2>{title}</h2>
<div class="section-title">Опыт работы</div>
{exp_html}
<div class="section-title">Навыки</div>
<div style="font-size: 14px;">{skills}</div>
</body>
</html>"""


def main():
    print("=========================================================")
    print("ВЫГРУЗКА РЕЗЮМЕ, ОПЫТА РАБОТЫ И ФАЙЛОВ ДЛЯ ВСЕЙ БАЗЫ")
    print("=========================================================")

    applicants_dir = EXPORT_DIR / "applicants"
    if not applicants_dir.exists():
        print("Ошибка: Папка huntflow_full_export/applicants не найдена.")
        return

    # Получаем ник организации из account.json
    org_nick = "grosver"
    meta_acc = EXPORT_DIR / "metadata" / "account.json"
    if meta_acc.exists():
        try:
            with open(meta_acc, "r", encoding="utf-8") as f:
                acc_obj = json.load(f)
                org_nick = acc_obj.get("nick") or acc_obj.get("slug") or org_nick
        except Exception:
            pass

    cand_folders = [f for f in applicants_dir.iterdir() if f.is_dir()]
    total_count = len(cand_folders)
    print(f"Кандидатов к обработке: {total_count}")

    updated_records = {}

    for idx, cand_dir in enumerate(cand_folders, 1):
        card_file = cand_dir / "card.json"
        if not card_file.exists():
            continue

        try:
            with open(card_file, "r", encoding="utf-8") as f:
                card = json.load(f)
        except Exception:
            continue

        app_id = card.get("id")
        account_id = card.get("account") or 252197
        fio = f"{card.get('last_name', '')} {card.get('first_name', '')}".strip() or f"ID_{app_id}"

        files_dir = cand_dir / "files"
        files_dir.mkdir(exist_ok=True)

        saved_files = []

        # 1. Фото
        photo_url = card.get("photo_url")
        photo_path = files_dir / "photo.jpg"
        if photo_url and not photo_path.exists():
            try:
                p_resp = requests.get(photo_url, timeout=15)
                if p_resp.status_code == 200:
                    with open(photo_path, "wb") as pf:
                        pf.write(p_resp.content)
                    saved_files.append("photo.jpg")
            except Exception:
                pass
        elif photo_path.exists():
            saved_files.append("photo.jpg")

        # 2. Резюме
        externals = card.get("external") or card.get("externals") or []
        for ext in externals:
            ext_id = ext.get("id")
            if not ext_id:
                continue

            json_file = files_dir / f"resume_{ext_id}.json"
            html_file = files_dir / f"resume_{ext_id}.html"
            pdf_file = files_dir / f"resume_{ext_id}.pdf"

            resume_payload = None
            if not json_file.exists():
                resume_payload = fetch_resume_payload(account_id, app_id, ext_id, org_nick)
                if resume_payload:
                    with open(json_file, "w", encoding="utf-8") as jf:
                        json.dump(resume_payload, jf, ensure_ascii=False, indent=2)
                    saved_files.append(f"resume_{ext_id}.json")
            else:
                try:
                    with open(json_file, "r", encoding="utf-8") as jf:
                        resume_payload = json.load(jf)
                    saved_files.append(f"resume_{ext_id}.json")
                except Exception:
                    pass

            if resume_payload:
                # Генерируем читаемую HTML-версию со всеми заводами и должностями
                if not html_file.exists():
                    html_content = generate_readable_html(fio, resume_payload)
                    with open(html_file, "w", encoding="utf-8") as hf:
                        hf.write(html_content)
                    saved_files.append(f"resume_{ext_id}.html")
                else:
                    saved_files.append(f"resume_{ext_id}.html")

                # Пробуем скачать оригинальный PDF, если есть ссылка
                if not pdf_file.exists():
                    data_block = resume_payload.get("data", {})
                    pdf_link = None
                    if isinstance(data_block, dict):
                        act = data_block.get("actions", {})
                        pdf_link = act.get("download", {}).get("pdf", {}).get("url") or data_block.get("download", {}).get("pdf", {}).get("url")
                    if pdf_link:
                        try:
                            pdf_resp = requests.get(pdf_link, timeout=25)
                            if pdf_resp.status_code == 200 and pdf_resp.content[:4] == b'%PDF':
                                with open(pdf_file, "wb") as pf:
                                    pf.write(pdf_resp.content)
                                saved_files.append(f"resume_{ext_id}.pdf")
                        except Exception:
                            pass
                else:
                    saved_files.append(f"resume_{ext_id}.pdf")

        existing = [f.name for f in files_dir.iterdir() if f.is_file()]
        final_list = list(set(saved_files + existing))
        updated_records[app_id] = final_list

        print(f"[{idx}/{total_count}] ID {app_id} ({fio}) -> Сохранено файлов: {len(final_list)}")

    # Обновляем CSV для Excel
    csv_path = EXPORT_DIR / "summary_table.csv"
    if csv_path.exists():
        print("\nОбновление summary_table.csv...")
        rows = []
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=";")
                fieldnames = reader.fieldnames
                for row in reader:
                    try:
                        r_id = int(row.get("ID", 0))
                    except ValueError:
                        r_id = 0
                    if r_id in updated_records and updated_records[r_id]:
                        row["Файлов_сохранено"] = ", ".join(updated_records[r_id])
                    rows.append(row)

            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
                writer.writeheader()
                writer.writerows(rows)
        except Exception as e:
            print(f"Ошибка обновления CSV: {e}")

    print("\n" + "=" * 60)
    print("ВЫГРУЗКА РЕЗЮМЕ ПО ВСЕЙ БАЗЕ ПОЛНОСТЬЮ ЗАВЕРШЕНА!")
    print("=" * 60)


if __name__ == "__main__":
    main()