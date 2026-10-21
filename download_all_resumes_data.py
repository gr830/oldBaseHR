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
API_TOKEN = "276383b79eab0ccaf521a3c79a5b197e06c2482cc2546a3d5e16af857d978e51"
BASE_URL = "https://api.huntflow.ru/v2"
EXPORT_DIR = Path("huntflow_full_export")

# Пауза между запросами (0.25 сек = 4 запроса/сек — безопасно для Хантфлоу)
REQUEST_DELAY = 0.25

# Автоматический подхват токена из export_huntflow.py
if "ВСТАВЬТЕ" in API_TOKEN or not API_TOKEN.strip():
    helper_file = Path("export_huntflow.py")
    if helper_file.exists():
        content = helper_file.read_text(encoding="utf-8")
        match = re.search(r'API_TOKEN\s*=\s*["\']([^"\']+)["\']', content)
        if match and "ВСТАВЬТЕ" not in match.group(1):
            API_TOKEN = match.group(1).strip()

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN.strip()}",
    "User-Agent": "HuntflowBulkResumeExtractor/1.0"
}

session = requests.Session()
session.headers.update(HEADERS)


def parse_and_format_resume(payload: dict, default_fio: str) -> str:
    """Формирует структурированный текстовый файл со всеми местами работы и описанием."""
    data = payload.get("data") or {}
    res_b = payload.get("resume") or {}

    fio = f"{data.get('last_name', '')} {data.get('first_name', '')} {data.get('middle_name', '')}".strip() or default_fio
    title = data.get("title") or res_b.get("position") or "Не указана"
    city = data.get("area", {}).get("name") or res_b.get("area", {}).get("city", {}).get("name") or "Не указан"
    age = data.get("age") or "Не указан"

    total_exp_months = data.get("total_experience", {}).get("months") or res_b.get("work_experience", {}).get("months", 0)
    total_exp_years = total_exp_months // 12 if total_exp_months else 0
    total_exp_rem = total_exp_months % 12 if total_exp_months else 0
    total_exp_str = f"{total_exp_years} лет {total_exp_rem} мес." if total_exp_months else "Не указан"

    lines = [
        "=" * 70,
        f"КАРТОЧКА РЕЗЮМЕ: {fio}",
        "=" * 70,
        f"Желаемая должность: {title}",
        f"Город: {city} | Возраст: {age} | Общий стаж: {total_exp_str}",
    ]

    # 1. Контакты
    contacts = data.get("contact") or res_b.get("contact") or []
    if contacts:
        lines.append("\n[КОНТАКТЫ]")
        for c in contacts:
            c_type = c.get("type", {}).get("name") or c.get("kind") or "Контакт"
            val = c.get("contact_value") or c.get("value")
            if val:
                lines.append(f"  • {c_type}: {val}")

    # 2. Опыт работы
    experiences = data.get("experience") or res_b.get("experience") or []
    lines.append(f"\n[ОПЫТ РАБОТЫ: Найдено мест: {len(experiences)}]")
    for idx, exp in enumerate(experiences, 1):
        comp = exp.get("company", "Компания не указана")
        pos = exp.get("position", "Должность не указана")

        start = exp.get("start") or exp.get("date_from") or ""
        end = exp.get("end") or exp.get("date_to") or "по наст. время"
        if isinstance(start, dict):
            start = f"{start.get('year', '')}-{start.get('month', ''):02d}" if isinstance(start.get('month'), int) else f"{start.get('year', '')}"
        if isinstance(end, dict):
            end = f"{end.get('year', '')}-{end.get('month', ''):02d}" if isinstance(end.get('month'), int) else f"{end.get('year', '')}"

        lines.append(f"\n  {idx}. {comp}")
        lines.append(f"     Должность: {pos}")
        lines.append(f"     Период:    {start} — {end}")

        desc = exp.get("description")
        if desc:
            clean_desc = "\n        ".join(desc.strip().split("\n"))
            lines.append(f"     Обязанности:\n        {clean_desc}")

    # 3. Образование
    edu = data.get("education") or res_b.get("education") or {}
    lines.append("\n[ОБРАЗОВАНИЕ]")
    level = edu.get("level", {})
    level_name = level.get("name") if isinstance(level, dict) else str(level)
    if level_name:
        lines.append(f"  Уровень: {level_name}")

    for item in edu.get("primary", []):
        lines.append(f"  • {item.get('year', '')} — {item.get('name', '')} ({item.get('result', '')})")
    for item in edu.get("additional", []):
        lines.append(f"  • Курсы: {item.get('year', '')} — {item.get('name', '')} ({item.get('result', '')})")
    for item in edu.get("elementary", []):
        lines.append(f"  • Школа: №{item.get('name', '')} (выпуск: {item.get('year', '')})")

    # 4. Навыки
    skill_set = data.get("skill_set") or res_b.get("skill_set") or []
    skills = data.get("skills") or ""
    if skill_set:
        lines.append("\n[КЛЮЧЕВЫЕ НАВЫКИ]")
        lines.append("  " + (", ".join(skill_set) if isinstance(skill_set, list) else str(skill_set)))
    if skills:
        lines.append("\n[О СЕБЕ / ЛИЧНЫЕ КАЧЕСТВА]")
        lines.append("  " + "\n  ".join(skills.strip().split("\n")))

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def main():
    print("=========================================================")
    print("МАССОВАЯ ВЫГРУЗКА РЕЗЮМЕ ДЛЯ ВСЕХ 3183 КАНДИДАТОВ")
    print("=========================================================")

    applicants_dir = EXPORT_DIR / "applicants"
    if not applicants_dir.exists():
        print("Ошибка: Папка huntflow_full_export/applicants не найдена.")
        return

    cand_folders = [f for f in applicants_dir.iterdir() if f.is_dir()]
    total_count = len(cand_folders)
    print(f"Всего кандидатов в базе: {total_count}")

    updated_records = {}
    downloaded_count = 0
    already_saved_count = 0

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
        saved_files = []

        for ext in externals:
            ext_id = ext.get("id")
            if not ext_id:
                continue

            json_file = files_dir / f"resume_{ext_id}.json"
            txt_file = files_dir / f"resume_{ext_id}.txt"

            # Если JSON уже был выгружен ранее — не делаем лишний запрос
            if json_file.exists() and json_file.stat().st_size > 50:
                already_saved_count += 1
                saved_files.extend([json_file.name, txt_file.name])
                continue

            # Запрос по подтвержденному рабочему маршруту API
            time.sleep(REQUEST_DELAY)
            url = f"{BASE_URL}/accounts/{account_id}/applicants/{app_id}/externals/{ext_id}"

            try:
                resp = session.get(url, timeout=25)

                if resp.status_code == 429:
                    wait_sec = int(resp.headers.get("Retry-After", 10))
                    print(f"\n[!] Лимит запросов. Пауза {wait_sec} сек...")
                    time.sleep(wait_sec)
                    resp = session.get(url, timeout=25)

                if resp.status_code == 200:
                    payload = resp.json()

                    # 1. Сохраняем полный сырой JSON резюме
                    with open(json_file, "w", encoding="utf-8") as jf:
                        json.dump(payload, jf, ensure_ascii=False, indent=2)

                    # 2. Сохраняем читаемый текстовый файл со всеми местами работы
                    formatted_txt = parse_and_format_resume(payload, fio)
                    with open(txt_file, "w", encoding="utf-8") as tf:
                        tf.write(formatted_txt)

                    saved_files.extend([json_file.name, txt_file.name])
                    downloaded_count += 1

                    data_obj = payload.get("data") or {}
                    exp_len = len(data_obj.get("experience", []))
                    print(f"[{idx}/{total_count}] ID {app_id} ({fio}) -> [OK] Найдено мест работы: {exp_len}")
                else:
                    print(f"[{idx}/{total_count}] ID {app_id} ({fio}) -> Код {resp.status_code}")

            except Exception as e:
                print(f"[{idx}/{total_count}] ID {app_id} ({fio}) -> Ошибка: {e}")

        existing = [f.name for f in files_dir.iterdir() if f.is_file()]
        final_list = list(set(saved_files + existing))
        updated_records[app_id] = final_list

    # Обновляем summary_table.csv для открытия в Excel
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
            print("Таблица Excel успешно обновлена!")
        except Exception as e:
            print(f"Предупреждение при обновлении CSV: {e}")

    print("\n" + "=" * 60)
    print("ВЫГРУЗКА ВСЕХ РЕЗЮМЕ УСПЕШНО ЗАВЕРШЕНА!")
    print(f"Скачано новых резюме: {downloaded_count}")
    print(f"Уже было выгружено: {already_saved_count}")
    print("=========================================================")


if __name__ == "__main__":
    main()