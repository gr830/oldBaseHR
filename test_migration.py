import os
import json
import base64
import re
import requests
from pathlib import Path

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
API_URL = "http://localhost:3000/api"
EMAIL = "adminTest2@by.local"
PASSWORD = "123456"  # <--- ВПИШИ ПАРОЛЬ ОТ adminTest2
BASE_DIR = Path(r"C:\NW\oldBaseWork\huntflow_full_export")

# Папки кандидатов для теста
TARGET_FOLDERS = ["53810208", "55493851", "55725085"]

vacancies_map = {}
statuses_map = {}
tags_map = {}

# ==========================================
# 2. ФУНКЦИИ АВТОРИЗАЦИИ И СПРАВОЧНИКОВ
# ==========================================
def login():
    print(f"🔐 Авторизация под {EMAIL}...")
    res = requests.post(f"{API_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if res.status_code not in [200, 201]:
        print(f"❌ Ошибка входа: {res.text}")
        exit(1)
    token = res.json().get("accessToken")
    print("✅ Успешно!")
    return token

def load_metadata():
    print("📂 Загрузка справочников Huntflow...")
    meta_dir = BASE_DIR / "metadata"
    
    if (meta_dir / "vacancies.json").exists():
        with open(meta_dir / "vacancies.json", "r", encoding="utf-8") as f:
            for v in json.load(f):
                vacancies_map[v["id"]] = v.get("position", f"Вакансия #{v['id']}")
                
    if (meta_dir / "statuses.json").exists():
        with open(meta_dir / "statuses.json", "r", encoding="utf-8") as f:
            for s in json.load(f).get("items", []):
                statuses_map[s["id"]] = s.get("name")
                
    if (meta_dir / "tags.json").exists():
        with open(meta_dir / "tags.json", "r", encoding="utf-8") as f:
            for t in json.load(f).get("items", []):
                tags_map[t["id"]] = t.get("name")

# Создаем ЕДИНСТВЕННУЮ архивную вакансию для всей истории
def get_archive_vacancy_id(token):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    title = "Архив истории Huntflow"
    
    res = requests.get(f"{API_URL}/vacancies?search={title}&status=closed", headers=headers)
    data = res.json().get("data", [])
    if data:
        return data[0]["id"]
        
    res = requests.post(f"{API_URL}/vacancies", headers=headers, json={"title": title, "status": "closed"})
    return res.json()["id"]

# ==========================================
# 3. ОСНОВНОЙ ПРОЦЕСС
# ==========================================
def run_migration():
    load_metadata()
    token = login()
    headers_json = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    headers_form = {"Authorization": f"Bearer {token}"} # Для файлов Content-Type не ставим, requests сделает сам
    
    archive_vac_id = get_archive_vacancy_id(token)
    
    applicants_dir = BASE_DIR / "applicants"
    if not applicants_dir.exists():
        print("❌ Папка applicants не найдена!")
        return

    folders = [f for f in applicants_dir.iterdir() if f.is_dir() and f.name in TARGET_FOLDERS]
    print(f"\n🚀 Начинаем перенос тестовых кандидатов ({len(folders)} шт.)...")
    
    for folder in folders:
        cand_id = folder.name
        print(f"\n-------------------------------------------")
        print(f"👉 Обработка кандидата ID: {cand_id}")
        
        card_file = folder / "card.json"
        if not card_file.exists():
            continue
            
        with open(card_file, "r", encoding="utf-8") as f:
            card_data = json.load(f)
            
        # 1. ЧТЕНИЕ ФОТОГРАФИИ
        photo_b64 = None
        photo_path = folder / "files" / "photo.jpg"
        if photo_path.exists():
            with open(photo_path, "rb") as img:
                b64_str = base64.b64encode(img.read()).decode("utf-8")
                photo_b64 = f"data:image/jpeg;base64,{b64_str}"

        # 2. ЧТЕНИЕ РЕЗЮМЕ И ТЕКСТА
        files_dir = folder / "files"
        resume_data = {}
        if files_dir.exists():
            for rf in files_dir.glob("resume_*.json"):
                with open(rf, "r", encoding="utf-8") as f:
                    resume_data = json.load(f)
                break
                
        r_info = resume_data.get("resume") or {}
        c_data = card_data.get("data") or {}
        
        first_name = card_data.get("first_name") or ""
        last_name = card_data.get("last_name") or ""
        middle_name = card_data.get("middle_name") or ""
        position = card_data.get("position") or ""
        phone = card_data.get("phone") or ""
        email = card_data.get("email") or ""
        money_raw = str(card_data.get("money") or "")
        
        sal_amount = None
        digits = re.sub(r"[^\d]", "", money_raw)
        if digits: sal_amount = int(digits)
        
        # Парсинг опыта
        exp_items = []
        for e in r_info.get("experience") or []:
            start = e.get("date_from") or {}
            start_str = f"{start.get('year')}-{str(start.get('month', 1)).zfill(2)}-01" if start else "2000-01-01"
            end = e.get("date_to") or {}
            end_str = f"{end.get('year')}-{str(end.get('month', 1)).zfill(2)}-01" if end else "present"
            
            exp_items.append({
                "company": e.get("company") or "Компания",
                "position": e.get("position") or "Должность",
                "description": e.get("description") or "",
                "startDate": start_str,
                "endDate": end_str
            })

        # Парсинг образования
        edu_items = []
        edu_info = r_info.get("education") or {}
        for ed in (edu_info.get("higher") or []) + (edu_info.get("primary") or []):
            date_to = ed.get("date_to") or {}
            edu_items.append({
                "institution": ed.get("name") or "Не указано",
                "year": str(date_to.get("year", "")),
                "faculty": ed.get("faculty") or "",
                "specialty": ed.get("description") or ""
            })

        tags = []
        for t in card_data.get("tags") or []:
            t_name = tags_map.get(t.get("tag"))
            if t_name: tags.append(t_name)
            
        payload = {
            "personal": {
                "firstName": first_name,
                "lastName": last_name,
                "middleName": middle_name,
                "birthDate": card_data.get("birthday") or None,
                "photoUrl": photo_b64,
            },
            "preferences": {
                "position": position,
                "headline": position,
                "salary": {"amount": sal_amount, "currency": "RUB"} if sal_amount else None
            },
            "experience": { "items": exp_items },
            "skills": r_info.get("skill_set") or [],
            "education": {
                "level": (edu_info.get("level") or {}).get("name") or "Не указано",
                "items": edu_items
            },
            "contacts": {
                "phones": [phone] if phone else [],
                "emails": [email] if email else []
            },
            "source": {
                "platform": "Huntflow",
                "domain": "huntflow.local",
                "profileUrl": f"import_hf_{cand_id}",
                "parsedAt": card_data.get("created") or "2026-01-01T00:00:00Z",
                "detectedTags": ["Huntflow Архив"] + tags
            }
        }

        # 3. ОТПРАВКА КАНДИДАТА В БАЗУ
        print(f"   📥 Сохранение профиля: {last_name} {first_name}...")
        res = requests.post(f"{API_URL}/candidates/from-parser", headers=headers_json, json=payload)
        
        if res.status_code not in [200, 201]:
            print(f"   ❌ Ошибка сохранения: {res.text}")
            continue
            
        cand_uuid = res.json().get("candidate")["id"]
        print(f"   ✅ Профиль создан (ID: {cand_uuid})")

        # 4. ЗАГРУЗКА РЕАЛЬНЫХ ФАЙЛОВ (PDF, DOCX) В ТАБЛИЦУ `files`
        if files_dir.exists():
            for file_path in files_dir.iterdir():
                if file_path.suffix.lower() in [".pdf", ".doc", ".docx", ".rtf", ".txt"]:
                    print(f"   📎 Загрузка файла {file_path.name}...")
                    with open(file_path, "rb") as f:
                        files = {"file": (file_path.name, f, "application/octet-stream")}
                        data = {"entityType": "candidate", "entityId": cand_uuid}
                        f_res = requests.post(f"{API_URL}/files", headers=headers_form, files=files, data=data)
                        if f_res.status_code == 201:
                            print("      ✅ Файл успешно добавлен в таблицу files!")
                        else:
                            print(f"      ⚠️ Ошибка загрузки файла: {f_res.text}")

        # 5. ПРИКРЕПЛЕНИЕ К "АРХИВНОЙ ВАКАНСИИ" И ЗАЛИВКА ИСТОРИИ
        cv_res = requests.post(f"{API_URL}/candidates/{cand_uuid}/vacancies", headers=headers_json, json={"vacancyId": archive_vac_id})
        if cv_res.status_code == 201:
            cv_id = cv_res.json()["id"]
            
            # Закидываем сырой текст резюме (если нет опыта, но есть огромный текст)
            raw_body = c_data.get("body")
            if raw_body and not exp_items:
                requests.post(f"{API_URL}/comments", headers=headers_json, json={
                    "candidateVacancyId": cv_id,
                    "text": f"📄 ОРИГИНАЛЬНЫЙ ТЕКСТ РЕЗЮМЕ:\n\n{raw_body}"
                })

            # Читаем историю и заливаем комментарии
            history_file = folder / "history_and_chat.json"
            if history_file.exists():
                with open(history_file, "r", encoding="utf-8") as hf:
                    history_list = json.load(hf)
                    for h_item in reversed(history_list): # От старых к новым
                        comment_text = h_item.get("comment")
                        status_name = statuses_map.get(h_item.get("status"), h_item.get("type"))
                        original_vac_id = h_item.get("vacancy")
                        original_vac_name = vacancies_map.get(original_vac_id, "Без вакансии")
                        
                        if comment_text or status_name:
                            # Формируем красивый текст комментария с пометкой о старой вакансии
                            msg = f"💼 Вакансия: {original_vac_name}\n📌 Этап: {status_name}"
                            if comment_text: 
                                msg += f"\n💬 {comment_text}"
                                
                            requests.post(f"{API_URL}/comments", headers=headers_json, json={
                                "candidateVacancyId": cv_id,
                                "text": msg
                            })
                print("   💬 Вся история и комментарии успешно перенесены в Архив!")

if __name__ == "__main__":
    run_migration()