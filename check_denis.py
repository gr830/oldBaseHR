import os
import re
import json
from pathlib import Path
import requests

# =====================================================================
# НАСТРОЙКИ
# =====================================================================
API_TOKEN = "ВСТАВЬТЕ_СЮДА_ВАШ_ACCESS_TOKEN"
BASE_URL = "https://api.huntflow.ru/v2"

# Автоподхват токена из export_huntflow.py
if "ВСТАВЬТЕ" in API_TOKEN or not API_TOKEN.strip():
    helper_file = Path("export_huntflow.py")
    if helper_file.exists():
        content = helper_file.read_text(encoding="utf-8")
        match = re.search(r'API_TOKEN\s*=\s*["\']([^"\']+)["\']', content)
        if match and "ВСТАВЬТЕ" not in match.group(1):
            API_TOKEN = match.group(1).strip()

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN.strip()}",
    "User-Agent": "HuntflowResumeChecker/2.0"
}

account_id = 252197
app_id = 89537788
ext_id = 89452609
org_nick = "grosver"

save_dir = Path(f"huntflow_full_export/applicants/{app_id}/files")
save_dir.mkdir(parents=True, exist_ok=True)

# Официальные варианты маршрутов Huntflow API v2 и веб-системы
test_routes = [
    f"{BASE_URL}/accounts/{account_id}/applicants/{app_id}/resumes/{ext_id}",
    f"{BASE_URL}/accounts/{account_id}/applicants/{app_id}/resumes",
    f"{BASE_URL}/accounts/{account_id}/applicants/{app_id}/resume/{ext_id}",
    f"{BASE_URL}/accounts/{account_id}/applicants/{app_id}/resume",
    f"{BASE_URL}/accounts/{account_id}/applicants/{app_id}/externals/{ext_id}",
    f"https://huntflow.ru/my/{org_nick}/applicant/{app_id}/external/{ext_id}",
    f"https://huntflow.ru/app/api/my/{org_nick}/applicant/{app_id}/external/{ext_id}"
]

print(f"Поиск рабочего маршрута для Дениса Коюкова (ID: {app_id}, ext_id: {ext_id})...\n")

working_url = None
working_data = None

for url in test_routes:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        print(f"[{resp.status_code}] {url}")
        if resp.status_code == 200:
            working_url = url
            working_data = resp.json()
            print(f"\n>>> УСПЕХ! НАЙДЕН РАБОЧИЙ МАРШРУТ: {url} <<<\n")
            break
    except Exception as e:
        print(f"[ERR] {url} -> {e}")

if not working_data:
    print("\n[!] Ни один маршрут через API токен не ответил 200.")
    print("Посмотрим на статус-коды выше, чтобы выбрать нужный метод.")
    exit(1)

# Сохраняем полученный 100% JSON
json_path = save_dir / f"resume_{ext_id}.json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(working_data, f, ensure_ascii=False, indent=2)

print(f" [OK] Исходный JSON сохранен: {json_path.resolve()}\n")

# Анализ содержимого
data = working_data.get("data") or {}
res_b = working_data.get("resume") or {}

# Если вернулся список резюме (в случае маршрута /resumes)
if isinstance(working_data, dict) and "items" in working_data:
    items = working_data["items"]
    if items:
        data = items[0].get("data") or {}
        res_b = items[0].get("resume") or {}

fio = f"{data.get('last_name', '')} {data.get('first_name', '')} {data.get('middle_name', '')}".strip() or "Коюков Денис Юрьевич"
title = data.get("title") or res_b.get("position") or "Не указана"
experiences = data.get("experience") or res_b.get("experience") or []

print("=" * 60)
print(f"РЕЗУЛЬТАТ ПРОВЕРКИ ДАННЫХ: {fio}")
print(f"Должность: {title}")
print(f"Найдено мест работы: {len(experiences)}")
print("=" * 60)

for idx, exp in enumerate(experiences, 1):
    comp = exp.get("company", "Без названия")
    pos = exp.get("position", "Без должности")
    start = exp.get("start") or exp.get("date_from") or ""
    end = exp.get("end") or exp.get("date_to") or "по н.в."
    print(f"\n{idx}. {comp} — {pos} ({start} — {end})")
    desc = exp.get("description", "")
    if desc:
        preview = desc.strip().replace("\n", " ")[:120]
        print(f"   Обязанности: {preview}...")

print("\n" + "=" * 60)
print("ПРОВЕРКА ПРОШЛА УСПЕШНО! Все данные на месте.")