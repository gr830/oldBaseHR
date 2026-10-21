import json
import re
from pathlib import Path
import requests

API_TOKEN = "276383b79eab0ccaf521a3c79a5b197e06c2482cc2546a3d5e16af857d978e51"

# Если токен не указан, берем его из export_huntflow.py
if "ВСТАВЬТЕ" in API_TOKEN:
    content = Path("export_huntflow.py").read_text(encoding="utf-8")
    API_TOKEN = re.search(r'API_TOKEN\s*=\s*["\']([^"\']+)["\']', content).group(1).strip()

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "User-Agent": "HuntflowResumeTest/1.0"
}

account_id = 252197
app_id = 89537788
ext_id = 89452609
org_nick = "grosver"

urls_to_test = [
    f"https://api.huntflow.ru/v2/accounts/{account_id}/applicants/{app_id}/external/{ext_id}",
    f"https://api.huntflow.ru/v2/accounts/{account_id}/applicants/{app_id}/externals/{ext_id}",
    f"https://huntflow.ru/my/{org_nick}/applicant/{app_id}/external/{ext_id}",
    f"https://huntflow.ru/app/api/my/{org_nick}/applicant/{app_id}/external/{ext_id}"
]

print("Проверка маршрутов для Дениса Коюкова...")
working_data = None

for url in urls_to_test:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        print(f"[{resp.status_code}] {url}")
        if resp.status_code == 200:
            working_data = resp.json()
            print(f"\n УСПЕХ! Найден рабочий маршрут API: {url}")
            break
    except Exception as e:
        print(f"[ERR] {url} -> {e}")

if working_data:
    save_dir = Path("huntflow_full_export/applicants/89537788/files")
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Сохраняем полный JSON резюме
    with open(save_dir / f"resume_{ext_id}.json", "w", encoding="utf-8") as f:
        json.dump(working_data, f, ensure_ascii=False, indent=2)
    print(f" Сохранен resume_{ext_id}.json")

    # 2. Пробуем скачать PDF по ссылке из резюме
    pdf_url = None
    data_block = working_data.get("data", {})
    if isinstance(data_block, dict):
        actions = data_block.get("actions", {})
        pdf_url = actions.get("download", {}).get("pdf", {}).get("url") or data_block.get("download", {}).get("pdf", {}).get("url")
    
    if pdf_url:
        print(f"Найдена ссылка на PDF: {pdf_url}")
        try:
            p_res = requests.get(pdf_url, timeout=30)
            if p_res.status_code == 200 and p_res.content[:4] == b'%PDF':
                with open(save_dir / f"resume_{ext_id}.pdf", "wb") as pf:
                    pf.write(p_res.content)
                print(f" PDF успешно скачан в resume_{ext_id}.pdf!")
        except Exception as e:
            print(f"Не удалось скачать прямой PDF: {e}")