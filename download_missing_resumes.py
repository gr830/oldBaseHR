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
    "User-Agent": "HuntflowResumesFixer/2.0"
}

session = requests.Session()
session.headers.update(HEADERS)


def get_resume_with_retry(account_id, app_id, ext_id, max_retries=4):
    """Делает запрос строго по проверенному адресу и обязательно повторяет при 429."""
    url = f"{BASE_URL}/accounts/{account_id}/applicants/{app_id}/externals/{ext_id}"
    for attempt in range(max_retries):
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(url, timeout=25)
            
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait_sec = int(resp.headers.get("Retry-After", 10))
                print(f" [!] 429 Лимит на ID {app_id}. Ожидание {wait_sec} сек (попытка {attempt+1}/{max_retries})...")
                time.sleep(wait_sec)
                continue  # ПОВТОРЯЕМ ЭТОГО ЖЕ КАНДИДАТА
            elif resp.status_code in [404, 400]:
                return None
        except Exception as e:
            time.sleep(2)
    return None


def main():
    print("=========================================================")
    print("ДОКАЧКА ПРОПУЩЕННЫХ РЕЗЮМЕ ДЛЯ ВСЕЙ БАЗЫ")
    print("=========================================================")

    applicants_dir = EXPORT_DIR / "applicants"
    cand_folders = [f for f in applicants_dir.iterdir() if f.is_dir()]
    total_count = len(cand_folders)
    print(f"Кандидатов на проверку: {total_count}")

    downloaded = 0
    already_had = 0

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

        externals = card.get("external") or card.get("externals") or []
        for ext in externals:
            ext_id = ext.get("id")
            if not ext_id:
                continue

            json_file = files_dir / f"resume_{ext_id}.json"

            # Если файл уже есть и он не пустой — мгновенно пропускаем
            if json_file.exists() and json_file.stat().st_size > 100:
                already_had += 1
                continue

            # Докачиваем пропущенного кандидата
            payload = get_resume_with_retry(account_id, app_id, ext_id)
            if payload:
                with open(json_file, "w", encoding="utf-8") as jf:
                    json.dump(payload, jf, ensure_ascii=False, indent=2)
                downloaded += 1
                exp_count = len(payload.get("data", {}).get("experience", []))
                print(f"[{idx}/{total_count}] ID {app_id} ({fio}) -> [ДОКАЧАНО] Опыт: мест {exp_count}")
            else:
                print(f"[{idx}/{total_count}] ID {app_id} ({fio}) -> Не найдено в API")

    print("\n" + "=" * 60)
    print(f"ДОКАЧКА ЗАВЕРШЕНА!")
    print(f"Уже было скачано ранее: {already_had}")
    print(f"Успешно докачано пропущенных: {downloaded}")
    print("=" * 60)


if __name__ == "__main__":
    main()