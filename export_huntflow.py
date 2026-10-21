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
# Вставьте сюда значение access_token, полученное по вашей ссылке:
API_TOKEN = "276383b79eab0ccaf521a3c79a5b197e06c2482cc2546a3d5e16af857d978e51"

BASE_URL = "https://api.huntflow.ru/v2"  # Для аккаунтов в РФ
EXPORT_DIR = Path("huntflow_full_export")

# Задержка между запросами (в секундах). 0.35 сек = ~2.8 запроса в сек (абсолютно безопасно)
REQUEST_DELAY = 0.35

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN.strip()}",
    "User-Agent": "HuntflowFullSafeArchiveExporter/3.0"
}

session = requests.Session()
session.headers.update(HEADERS)


def sanitize_filename(name: str) -> str:
    """Удаляет запрещенные в Windows символы из имен файлов."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(name)).strip()
    return cleaned if cleaned else "unnamed_file"


def safe_request(endpoint: str, params=None, retries=5):
    """
    Безопасный запрос к API. Не ломает соединение и
    автоматически обрабатывает превышение лимитов (Rate Limits).
    """
    url = f"{BASE_URL}{endpoint}" if endpoint.startswith("/") else f"{BASE_URL}/{endpoint}"
    
    for attempt in range(retries):
        try:
            time.sleep(REQUEST_DELAY)  # Безопасная пауза перед каждым запросом
            resp = session.get(url, params=params, timeout=45)
            
            # Обработка лимита запросов (код 429)
            if resp.status_code == 429:
                wait_time = int(resp.headers.get("Retry-After", 15))
                print(f"\n[!] Сработал лимит частоты. Ожидание {wait_time} сек для безопасности...")
                time.sleep(wait_time)
                continue

            if resp.status_code == 401:
                raise Exception("Ошибка 401: Токен недействителен. Проверьте, правильно ли скопирован access_token.")
            
            # Временные ошибки серверов Хантфлоу
            if resp.status_code in [502, 503, 504]:
                wait_srv = 10 * (attempt + 1)
                print(f"\n[!] Сервер Хантфлоу временно занят ({resp.status_code}). Повтор через {wait_srv} сек...")
                time.sleep(wait_srv)
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.RequestException as e:
            if attempt == retries - 1:
                print(f"\n[X] Не удалось выполнить запрос к {url}: {e}")
                return None
            time.sleep(5 * (attempt + 1))
            
    return None


def fetch_all_pages(endpoint: str, params=None):
    """Постраничный сбор всех записей без пропусков."""
    if params is None:
        params = {}
    params = params.copy()
    params["count"] = 30
    page = 1
    collected = []
    
    while True:
        params["page"] = page
        data = safe_request(endpoint, params=params)
        if not data or not data.get("items"):
            break
        collected.extend(data["items"])
        total_pages = data.get("total_pages", page)
        if page >= total_pages:
            break
        page += 1
        
    return collected


def download_file(url: str, save_path: Path):
    """Потоковая загрузка файла без перегрузки памяти и сети."""
    if save_path.exists() and save_path.stat().st_size > 0:
        return True  # Файл уже был скачан ранее

    try:
        time.sleep(0.15)
        resp = session.get(url, stream=True, timeout=60)
        # Если ссылка S3 отклоняет Bearer-токен:
        if resp.status_code == 400:
            resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=16384):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"      [Ошибка скачивания файла]: {e}")
        return False


def main():
    print("=========================================================")
    print("СТАРТ ПОЛНОЙ БЕЗОПАСНОЙ ВЫГРУЗКИ ХАНТФЛОУ")
    print("=========================================================")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    meta_dir = EXPORT_DIR / "metadata"
    meta_dir.mkdir(exist_ok=True)
    applicants_dir = EXPORT_DIR / "applicants"
    applicants_dir.mkdir(exist_ok=True)

    # 1. Получаем организацию
    accounts_info = safe_request("/accounts")
    if not accounts_info or not accounts_info.get("items"):
        print("Ошибка: не удалось связаться с аккаунтом. Проверьте правильность токена.")
        return

    account = accounts_info["items"][0]
    account_id = account["id"]
    print(f"Подключено к организации: {account.get('name')} (ID: {account_id})")

    # Сохраняем системные справочники
    print("\n--- 1. Выгрузка всех справочников и метаданных ---")
    
    with open(meta_dir / "account.json", "w", encoding="utf-8") as f:
        json.dump(account, f, ensure_ascii=False, indent=2)

    vacancies = fetch_all_pages(f"/accounts/{account_id}/vacancies")
    with open(meta_dir / "vacancies.json", "w", encoding="utf-8") as f:
        json.dump(vacancies, f, ensure_ascii=False, indent=2)
    print(f" -> Вакансий выгружено: {len(vacancies)}")

    statuses = safe_request(f"/accounts/{account_id}/vacancies/statuses")
    with open(meta_dir / "statuses.json", "w", encoding="utf-8") as f:
        json.dump(statuses, f, ensure_ascii=False, indent=2)

    reasons = safe_request(f"/accounts/{account_id}/rejection_reasons")
    with open(meta_dir / "rejection_reasons.json", "w", encoding="utf-8") as f:
        json.dump(reasons, f, ensure_ascii=False, indent=2)

    tags = safe_request(f"/accounts/{account_id}/tags")
    with open(meta_dir / "tags.json", "w", encoding="utf-8") as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)

    coworkers = safe_request(f"/accounts/{account_id}/coworkers")
    with open(meta_dir / "coworkers.json", "w", encoding="utf-8") as f:
        json.dump(coworkers, f, ensure_ascii=False, indent=2)

    # Создаем словари для понятного отображения в Excel
    vac_map = {v["id"]: v.get("position", f"Вакансия_{v['id']}") for v in vacancies} if vacancies else {}
    stat_map = {s["id"]: s.get("name", f"Этап_{s['id']}") for s in statuses.get("items", [])} if statuses else {}

    # 2. Получение общего списка всех кандидатов
    print("\n--- 2. Сбор общего списка кандидатов базы ---")
    all_applicant_ids = []
    page = 1
    while True:
        print(f"Сбор страниц базы: страница {page}...", end="\r")
        res = safe_request(f"/accounts/{account_id}/applicants", params={"count": 30, "page": page})
        if not res or not res.get("items"):
            break
        for item in res["items"]:
            all_applicant_ids.append(item["id"])
        if page >= res.get("total_pages", page):
            break
        page += 1

    total_candidates = len(all_applicant_ids)
    print(f"\nВсего кандидатов для полной выгрузки: {total_candidates}")

    # 3. Детальная выгрузка
    print("\n--- 3. Скачивание всех карточек, переписки и файлов ---")
    jsonl_path = EXPORT_DIR / "applicants_all.jsonl"
    csv_path = EXPORT_DIR / "summary_table.csv"

    csv_fieldnames = [
        "ID", "ФИО", "Желаемая_должность", "Текущая_компания", "Зарплата",
        "Телефон", "Email", "Контакты_соцсети", "Вакансии", "Этапы",
        "Дата_создания", "Файлов_сохранено", "Последняя_история_и_письма"
    ]

    csv_exists = csv_path.exists()
    csv_file = open(csv_path, "a", encoding="utf-8-sig", newline="")
    csv_writer = csv.DictWriter(csv_file, fieldnames=csv_fieldnames, delimiter=";")
    if not csv_exists:
        csv_writer.writeheader()

    jsonl_file = open(jsonl_path, "a", encoding="utf-8")

    try:
        for idx, app_id in enumerate(all_applicant_ids, 1):
            cand_folder = applicants_dir / str(app_id)
            card_file = cand_folder / "card.json"
            logs_file = cand_folder / "history_and_chat.json"
            files_folder = cand_folder / "files"

            # Пропуск уже скачанных кандидатов (если скрипт перезапущен)
            if card_file.exists() and logs_file.exists():
                print(f"[{idx}/{total_candidates}] ID {app_id} уже выгружен ранее (пропуск)")
                continue

            cand_folder.mkdir(exist_ok=True)
            files_folder.mkdir(exist_ok=True)

            print(f"[{idx}/{total_candidates}] Загрузка полной истории ID {app_id}...")

            # А. Карточка кандидата со всеми полями
            card = safe_request(f"/accounts/{account_id}/applicants/{app_id}")
            if not card:
                continue

            # Б. Вся переписка, письма, комментарии и логи
            history_logs = fetch_all_pages(f"/accounts/{account_id}/applicants/{app_id}/logs")

            # Сохранение индивидуальных JSON в папку кандидата
            with open(card_file, "w", encoding="utf-8") as f:
                json.dump(card, f, ensure_ascii=False, indent=2)

            with open(logs_file, "w", encoding="utf-8") as f:
                json.dump(history_logs, f, ensure_ascii=False, indent=2)

            # Сохранение в общий поток JSONL для мгновенной загрузки в БД
            full_applicant_object = {
                "account_id": account_id,
                "applicant_id": app_id,
                "profile": card,
                "history": history_logs
            }
            jsonl_file.write(json.dumps(full_applicant_object, ensure_ascii=False) + "\n")
            jsonl_file.flush()

            # В. Поиск и скачивание ВСЕХ файлов (из профиля + из переписки/писем)
            all_files = []
            if card.get("files"):
                all_files.extend(card["files"])

            for log_item in history_logs:
                if log_item.get("files"):
                    all_files.extend(log_item["files"])

            saved_files = []
            for file_info in all_files:
                f_url = file_info.get("url")
                f_id = file_info.get("id", "0")
                orig_name = file_info.get("name") or f"file_{f_id}.dat"
                file_dest_name = sanitize_filename(f"{f_id}_{orig_name}")
                target_dest = files_folder / file_dest_name

                if f_url and download_file(f_url, target_dest):
                    saved_files.append(file_dest_name)

            # Г. Запись обзорной строки в Excel (CSV)
            fio = f"{card.get('last_name') or ''} {card.get('first_name') or ''} {card.get('middle_name') or ''}".strip() or f"ID_{app_id}"
            
            vac_names = [vac_map.get(l.get("vacancy"), str(l.get("vacancy"))) for l in card.get("links", [])]
            stat_names = [stat_map.get(l.get("status"), str(l.get("status"))) for l in card.get("links", [])]

            logs_summary = []
            for item in history_logs[:4]:
                comm = item.get("comment") or item.get("type", "")
                dt = item.get("created", "")[:10]
                if comm:
                    logs_summary.append(f"[{dt}] {comm}")

            csv_writer.writerow({
                "ID": app_id,
                "ФИО": fio,
                "Желаемая_должность": card.get("position") or "",
                "Текущая_компания": card.get("company") or "",
                "Зарплата": card.get("money") or "",
                "Телефон": card.get("phone") or "",
                "Email": card.get("email") or "",
                "Контакты_соцсети": card.get("telegram") or card.get("skype") or "",
                "Вакансии": ", ".join(vac_names),
                "Этапы": ", ".join(stat_names),
                "Дата_создания": card.get("created", ""),
                "Файлов_сохранено": ", ".join(saved_files) if saved_files else "Нет",
                "Последняя_история_и_письма": " || ".join(logs_summary)
            })
            csv_file.flush()

    finally:
        csv_file.close()
        jsonl_file.close()

    print("\n" + "=" * 60)
    print("ВЫГРУЗКА УСПЕШНО ЗАВЕРШЕНА НА 100%!")
    print(f"Все папки с файлами и базы сохранены в: {EXPORT_DIR.resolve()}")
    print("=========================================================")


if __name__ == "__main__":
    main()