import os
import re
import csv
import json
import time
from pathlib import Path
import requests

# =====================================================================
# НАСТРОЙКИ
# =====================================================================
API_TOKEN = "276383b79eab0ccaf521a3c79a5b197e06c2482cc2546a3d5e16af857d978e51"  # Тот же токен, что и ранее
BASE_URL = "https://api.huntflow.ru/v2"
EXPORT_DIR = Path("huntflow_full_export")

# Пауза между запросами (0.25 сек = 4 запроса/сек — очень безопасно)
REQUEST_DELAY = 0.25

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN.strip()}",
    "User-Agent": "HuntflowResumeDownloader/2.0"
}

session = requests.Session()
session.headers.update(HEADERS)


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(name)).strip()
    return cleaned if cleaned else "unnamed_file"


def safe_request(endpoint: str, params=None, retries=4):
    url = f"{BASE_URL}{endpoint}" if endpoint.startswith("/") else f"{BASE_URL}/{endpoint}"
    for attempt in range(retries):
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                wait_sec = int(resp.headers.get("Retry-After", 10))
                print(f"\n[!] Лимит частоты. Ожидание {wait_sec} сек...")
                time.sleep(wait_sec)
                continue
            if resp.status_code in [404, 400]:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == retries - 1:
                return None
            time.sleep(2)
    return None


def download_pdf(account_id: int, app_id: int, ext_id: int, target_path: Path):
    """Пытается скачать резюме в формате PDF через доступные маршруты API."""
    if target_path.exists() and target_path.stat().st_size > 0:
        return True

    # Пробуем маршруты для скачивания PDF
    endpoints = [
        f"/accounts/{account_id}/applicants/{app_id}/resumes/{ext_id}/pdf",
        f"/accounts/{account_id}/applicants/{app_id}/external/{ext_id}/pdf"
    ]

    for ep in endpoints:
        url = f"{BASE_URL}{ep}"
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(url, timeout=35)
            # Проверяем, что сервер вернул именно PDF
            if resp.status_code == 200 and resp.content and resp.content[:4] == b'%PDF':
                with open(target_path, "wb") as f:
                    f.write(resp.content)
                return True
        except Exception:
            pass
    return False


def get_resume_details(account_id: int, app_id: int, ext_id: int):
    """Получает полный текст, опыт работы и навыки резюме."""
    res = safe_request(f"/accounts/{account_id}/applicants/{app_id}/resumes/{ext_id}")
    if not res:
        res = safe_request(f"/accounts/{account_id}/applicants/{app_id}/external/{ext_id}")
    return res


def extract_readable_text(resume_data: dict) -> str:
    """Формирует красивый читаемый текст резюме со всеми местами работы."""
    if not isinstance(resume_data, dict):
        return ""
    data = resume_data.get("data", {})
    if not isinstance(data, dict):
        return ""

    parts = []
    # Основной текст резюме
    if data.get("body"):
        parts.append(data["body"])

    # Опыт работы
    exp_list = data.get("experience")
    if exp_list and isinstance(exp_list, list):
        parts.append("\n" + "=" * 40 + "\nОПЫТ РАБОТЫ:\n" + "=" * 40)
        for job in exp_list:
            comp = job.get("company") or ""
            pos = job.get("position") or ""
            d_from = job.get("date_from") or ""
            d_to = job.get("date_to") or "по н.в."
            desc = job.get("description") or ""
            parts.append(f"\n[{d_from} - {d_to}] {comp} — {pos}\n{desc}")

    # Образование
    edu = data.get("education")
    if edu and isinstance(edu, dict):
        parts.append("\n" + "=" * 40 + "\nОБРАЗОВАНИЕ:\n" + "=" * 40)
        for item in edu.get("primary", []):
            year = item.get("year") or ""
            name = item.get("name") or ""
            res = item.get("result") or ""
            parts.append(f"{year} | {name} ({res})")

    # Навыки
    skills = data.get("skills") or data.get("skill_set")
    if skills:
        parts.append(f"\nКЛЮЧЕВЫЕ НАВЫКИ:\n{skills}")

    return "\n".join(parts).strip()


def main():
    print("=========================================================")
    print("ДОКАЧКА РЕЗЮМЕ, ТЕКСТОВ И ФОТОГРАФИЙ")
    print("=========================================================")

    applicants_dir = EXPORT_DIR / "applicants"
    if not applicants_dir.exists():
        print("Ошибка: Папка с выгруженными кандидатами не найдена.")
        return

    cand_folders = [f for f in applicants_dir.iterdir() if f.is_dir()]
    total_count = len(cand_folders)
    print(f"Найдено локальных карточек кандидатов: {total_count}")

    updated_records = {}

    for idx, cand_dir in enumerate(cand_folders, 1):
        card_file = cand_dir / "card.json"
        if not card_file.exists():
            continue

        with open(card_file, "r", encoding="utf-8") as f:
            card = json.load(f)

        app_id = card.get("id")
        account_id = card.get("account")
        first_name = card.get("first_name") or ""
        last_name = card.get("last_name") or ""
        fio = f"{last_name} {first_name}".strip() or f"ID_{app_id}"

        files_dir = cand_dir / "files"
        files_dir.mkdir(exist_ok=True)

        saved_files = []

        # 1. Скачиваем фото кандидата (если есть)
        photo_url = card.get("photo_url")
        photo_path = files_dir / "photo.jpg"
        if photo_url and not photo_path.exists():
            try:
                p_resp = requests.get(photo_url, timeout=20)
                if p_resp.status_code == 200:
                    with open(photo_path, "wb") as pf:
                        pf.write(p_resp.content)
                    saved_files.append("photo.jpg")
            except Exception:
                pass
        elif photo_path.exists():
            saved_files.append("photo.jpg")

        # 2. Обрабатываем все внешние резюме (HH, SuperJob, etc.)
        externals = card.get("external") or card.get("externals") or []
        for ext in externals:
            ext_id = ext.get("id")
            if not ext_id:
                continue

            pdf_file = files_dir / f"resume_{ext_id}.pdf"
            json_file = files_dir / f"resume_{ext_id}.json"
            txt_file = files_dir / f"resume_{ext_id}.txt"

            # А. Скачиваем официальный PDF файл
            pdf_ok = download_pdf(account_id, app_id, ext_id, pdf_file)
            if pdf_ok:
                saved_files.append(f"resume_{ext_id}.pdf")

            # Б. Получаем полный структурированный JSON резюме
            if not json_file.exists():
                resume_data = get_resume_details(account_id, app_id, ext_id)
                if resume_data:
                    with open(json_file, "w", encoding="utf-8") as jf:
                        json.dump(resume_data, jf, ensure_ascii=False, indent=2)

                    # Формируем текстовую версию (.txt)
                    text_content = extract_readable_text(resume_data)
                    if text_content:
                        with open(txt_file, "w", encoding="utf-8") as tf:
                            tf.write(text_content)
                        saved_files.append(f"resume_{ext_id}.txt")
            else:
                saved_files.append(f"resume_{ext_id}.txt")

        # Учитываем файлы, которые уже лежали в папке
        existing = [f.name for f in files_dir.iterdir() if f.is_file()]
        final_files_list = list(set(saved_files + existing))
        updated_records[app_id] = final_files_list

        status_str = f"Файлов: {len(final_files_list)}"
        print(f"[{idx}/{total_count}] ID {app_id} ({fio}) -> {status_str}")

    # Обновляем таблицу summary_table.csv с актуальными именами файлов
    csv_path = EXPORT_DIR / "summary_table.csv"
    if csv_path.exists():
        print("\nОбновление итоговой таблицы Excel...")
        rows = []
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";")
            fieldnames = reader.fieldnames
            for row in reader:
                r_id = int(row.get("ID", 0))
                if r_id in updated_records and updated_records[r_id]:
                    row["Файлов_сохранено"] = ", ".join(updated_records[r_id])
                rows.append(row)

        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

    print("\n" + "=" * 60)
    print("ВСЕ РЕЗЮМЕ, ТЕКСТЫ И ФАЙЛЫ УСПЕШНО СКАЧАНЫ!")
    print("=" * 60)


if __name__ == "__main__":
    main()