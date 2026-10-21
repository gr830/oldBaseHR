import os
import json
import base64
import requests
import time
import sys
from pathlib import Path
from datetime import datetime

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
API_URL = "http://localhost:3000/api"
EMAIL = "adminTest2@by.local"
PASSWORD = "123456"  # <--- ВПИШИ ПАРОЛЬ
BASE_DIR = Path(r"C:\NW\oldBaseWork\huntflow_full_export")

TARGET_FOLDERS = [] 
PROGRESS_FILE = Path("migrated_ids.txt")
DELAY_SECONDS = 5

vacancies_map = {}
statuses_map = {}
tags_map = {}
ats_stages_map = {}

# ==========================================
# 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
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

def load_metadata_and_stages(token):
    print("📂 Загрузка справочников Huntflow и стадий ATS...")
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

    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{API_URL}/stages", headers=headers)
    if res.status_code == 200:
        for stage in res.json():
            ats_stages_map[stage["name"]] = stage["id"]

def get_archive_vacancy_id(token):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    title = "Архив истории Huntflow"
    res = requests.get(f"{API_URL}/vacancies?search={title}&status=closed", headers=headers)
    data = res.json().get("data", [])
    if data:
        return data[0]["id"]
    
    res = requests.post(f"{API_URL}/vacancies", headers=headers, json={"title": title, "status": "closed"})
    return res.json()["id"]

def parse_raw_with_ai(raw_text: str, token: str) -> dict:
    raw_text = raw_text[:15000]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    for attempt in range(3):
        print(f"   🤖 Отправляем на AI-парсинг (Попытка {attempt+1}/3)...")
        try:
            res = requests.post(f"{API_URL}/candidates/parse-raw", headers=headers, json={"rawText": raw_text}, timeout=360)
            if res.status_code in [200, 201]:
                print("   ✅ AI успешно распарсил резюме!")
                
                # === ИСПРАВЛЕНИЕ ОШИБКИ 'list' object has no attribute 'get' ===
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    print("   ⚠️ ИИ вернул список вместо объекта. Берем первый элемент.")
                    return data[0]
                return data
                # ==========================================================
                
            else:
                print(f"   ⚠️ Ошибка ИИ (Код {res.status_code}). Ждем 15 сек...")
                time.sleep(15)
        except Exception as e:
            print(f"   ⚠️ Ошибка сети/таймаут: {e}. Ждем 15 сек...")
            time.sleep(15)
            
    return None

def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            return set(line.strip() for line in f)
    return set()

def save_progress(cand_id):
    with open(PROGRESS_FILE, "a") as f:
        f.write(f"{cand_id}\n")

# ==========================================
# 3. ОСНОВНОЙ ПРОЦЕСС
# ==========================================
def run_migration():
    token = login()
    load_metadata_and_stages(token)
    
    headers_json = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    headers_form = {"Authorization": f"Bearer {token}"}
    
    archive_vac_id = get_archive_vacancy_id(token)
    applicants_dir = BASE_DIR / "applicants"
    
    processed_ids = load_progress()
    
    folders = [f for f in applicants_dir.iterdir() if f.is_dir() and (not TARGET_FOLDERS or f.name in TARGET_FOLDERS)]
    folders = [f for f in folders if f.name not in processed_ids]
    
    total_to_process = len(folders)
    print(f"\n🚀 Осталось перенести: {total_to_process} кандидатов (пропущено готовых: {len(processed_ids)})")
    
    if total_to_process == 0:
        print("✅ Вся база уже перенесена!")
        return

    try:
        for i, folder in enumerate(folders):
            cand_id = folder.name
            print(f"\n{'='*50}\n👉 Обработка: {cand_id} ({i+1} из {total_to_process})")
            
            card_file = folder / "card.json"
            if not card_file.exists():
                save_progress(cand_id)
                continue
                
            try:
                with open(card_file, "r", encoding="utf-8") as f:
                    card_data = json.load(f)

                files_dir = folder / "files"
                resume_files = list(files_dir.glob("resume*.json")) if files_dir.exists() else []
                
                resume_data = {}
                if resume_files:
                    with open(resume_files[0], "r", encoding="utf-8") as f:
                        resume_data = json.load(f)
                        print(f"   📄 Найден файл резюме: {resume_files[0].name}")

                r_data = resume_data.get("data") or {}
                raw_body = r_data.get("body") or ""
                
                if raw_body:
                    text_for_ai = raw_body
                elif resume_data:
                    text_for_ai = json.dumps(resume_data, ensure_ascii=False)
                else:
                    print("   ❌ НЕТ ТЕКСТА ДЛЯ ПЕРЕДАЧИ В ИИ. ОСТАНОВКА!")
                    sys.exit(1)

                final_parsed_data = parse_raw_with_ai(text_for_ai, token)

                if final_parsed_data is None:
                    print("\n" + "="*60)
                    print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: ИИ не справился за 3 попытки на кандидате {cand_id}.")
                    print("🛑 СКРИПТ ОСТАНОВЛЕН.")
                    print(f"💡 Чтобы пропустить его, добавьте ID {cand_id} в файл migrated_ids.txt и запустите заново.")
                    print("="*60)
                    sys.exit(1)

                # === ДОПОЛНИТЕЛЬНЫЙ САНИТАЙЗЕР ===
                # Если ИИ вернул пустоту вместо объекта
                if not isinstance(final_parsed_data, dict):
                    print("   ⚠️ ИИ вернул невалидный формат (не словарь). Пропускаем.")
                    save_progress(cand_id)
                    continue

                hf_tags = [tags_map.get(t.get("tag")) for t in card_data.get("tags", []) if tags_map.get(t.get("tag"))]
                
                photo_url = None
                if files_dir.exists():
                    if (files_dir / "photo.jpg").exists():
                        with open(files_dir / "photo.jpg", "rb") as img:
                            b64_str = base64.b64encode(img.read()).decode("utf-8")
                            photo_url = f"data:image/jpeg;base64,{b64_str}"
                    elif card_data.get("photo_url") and card_data["photo_url"].startswith("http"):
                        photo_url = card_data["photo_url"]

                p_data = final_parsed_data.get("personal", {})
                pref_data = final_parsed_data.get("preferences", {})
                exp_data = final_parsed_data.get("experience", {})
                edu_data = final_parsed_data.get("education", {})
                add_data = final_parsed_data.get("additional", {})
                skills_data = final_parsed_data.get("skills", [])

                # Очищаем навыки (если ИИ вернул объекты вместо строк)
                clean_skills = []
                if isinstance(skills_data, list):
                    for s in skills_data:
                        if isinstance(s, str):
                            clean_skills.append(s)
                        elif isinstance(s, dict) and "name" in s:
                            clean_skills.append(s["name"])

                # Принудительно делаем год образования строкой
                if edu_data.get("items") and isinstance(edu_data["items"], list):
                    for item in edu_data["items"]:
                        if isinstance(item, dict) and "year" in item and item["year"] is not None:
                            item["year"] = str(item["year"])

                # Умная очистка зарплаты
                raw_salary = pref_data.get("salary")
                clean_salary = None
                if raw_salary and isinstance(raw_salary, dict):
                    amount = raw_salary.get("amount")
                    currency = str(raw_salary.get("currency") or "").upper().strip()
                    
                    if amount and float(amount) > 0:
                        if currency in ['BYR', 'BYN', 'BR']:
                            currency = 'BYN'
                        elif currency in ['RUR', 'RUB', 'РУБ']:
                            currency = 'RUB'
                        elif currency in ['USD', 'ДОЛ']:
                            currency = 'USD'
                        elif currency in ['EUR', 'ЕВРО']:
                            currency = 'EUR'
                        else:
                            currency = 'RUB' 
                            
                        clean_salary = {"amount": amount, "currency": currency}

                payload = {
                    "personal": {
                        "firstName": p_data.get("firstName") or card_data.get("first_name") or "",
                        "lastName": p_data.get("lastName") or card_data.get("last_name") or "",
                        "middleName": p_data.get("middleName") or card_data.get("middle_name") or "",
                        "gender": p_data.get("gender"),
                        "age": p_data.get("age"),
                        "birthDate": p_data.get("birthDate") or card_data.get("birthday"),
                        "city": p_data.get("city"),
                        "citizenship": p_data.get("citizenship"),
                        "photoUrl": photo_url
                    },
                    "preferences": {
                        "position": pref_data.get("position") or card_data.get("position") or "",
                        "headline": pref_data.get("headline") or card_data.get("position") or "",
                        "salary": clean_salary,
                        "employmentType": pref_data.get("employmentType"),
                        "relocation": pref_data.get("relocation"),
                        "businessTrips": pref_data.get("businessTrips")
                    },
                    "experience": {
                        "totalMonths": exp_data.get("totalMonths"),
                        "totalString": exp_data.get("totalString"),
                        "items": exp_data.get("items", []) if isinstance(exp_data.get("items"), list) else []
                    },
                    "skills": clean_skills,
                    "education": {
                        "level": edu_data.get("level"),
                        "items": edu_data.get("items", []) if isinstance(edu_data.get("items"), list) else []
                    },
                    "additional": add_data,
                    "contacts": {
                        "phones": [card_data.get("phone")] if card_data.get("phone") else [],
                        "emails": [card_data.get("email")] if card_data.get("email") else []
                    },
                    "source": {
                        "platform": "Huntflow",
                        "domain": "huntflow.local",
                        "profileUrl": f"import_hf_{cand_id}",
                        "parsedAt": card_data.get("created") or datetime.now().isoformat(),
                        "detectedTags": ["Huntflow Архив"] + hf_tags
                    }
                }

                print(f"   📥 Сохранение профиля: {payload['personal']['lastName']} {payload['personal']['firstName']}...")
                res = requests.post(f"{API_URL}/candidates/from-parser", headers=headers_json, json=payload, timeout=30)
                
                if res.status_code not in [200, 201, 202]:
                    print(f"   ❌ ОШИБКА БЭКЕНДА ПРИ СОХРАНЕНИИ: {res.text}")
                    print("🛑 СКРИПТ ОСТАНОВЛЕН, ЧТОБЫ НЕ ПОТЕРЯТЬ ДАННЫЕ.")
                    sys.exit(1)
                    
                cand_uuid = res.json().get("candidate", {}).get("id") or res.json().get("id")
                print(f"   ✅ Профиль создан/обновлен (ID: {cand_uuid})")

                if files_dir.exists():
                    for file_path in files_dir.iterdir():
                        if file_path.suffix.lower() in [".pdf", ".doc", ".docx", ".rtf", ".txt"] and "resume" not in file_path.name:
                            try:
                                with open(file_path, "rb") as f:
                                    files = {"file": (file_path.name, f, "application/octet-stream")}
                                    data = {"entityType": "candidate", "entityId": cand_uuid}
                                    requests.post(f"{API_URL}/files", headers=headers_form, files=files, data=data, timeout=30)
                            except Exception:
                                pass

                original_status_id = None
                links = card_data.get("links")
                if links and isinstance(links, list) and len(links) > 0:
                    original_status_id = links[0].get("status")

                original_status_name = statuses_map.get(original_status_id, "Новый кандидат")
                target_stage_id = ats_stages_map.get(original_status_name)

                cv_payload = {"vacancyId": archive_vac_id}
                if target_stage_id:
                    cv_payload["stageId"] = target_stage_id
                    print(f"   📌 Прикрепляем на этап: {original_status_name}")

                cv_res = requests.post(f"{API_URL}/candidates/{cand_uuid}/vacancies", headers=headers_json, json=cv_payload, timeout=30)
                
                if cv_res.status_code == 201:
                    cv_id = cv_res.json()["id"]
                    
                    history_file = folder / "history_and_chat.json"
                    if history_file.exists():
                        with open(history_file, "r", encoding="utf-8") as hf:
                            history_list = json.load(hf)
                            history_list.sort(key=lambda x: x.get("created", ""))
                            
                            for h_item in history_list:
                                comment_text = h_item.get("comment")
                                status_id = h_item.get("status")
                                status_name = statuses_map.get(status_id, h_item.get("type", "Действие"))
                                original_vac_id = h_item.get("vacancy")
                                original_vac_name = vacancies_map.get(original_vac_id, "Без вакансии")
                                
                                raw_date = h_item.get("created", "")
                                date_str = raw_date[:10] if raw_date else "Дата неизвестна"
                                
                                if comment_text or status_name:
                                    msg = f"🕒 Дата: {date_str}\n"
                                    msg += f"💼 Вакансия: {original_vac_name}\n"
                                    msg += f"📌 Этап: {status_name}"
                                    
                                    if comment_text: 
                                        msg += f"\n💬 Комментарий:\n{comment_text}"
                                        
                                    requests.post(f"{API_URL}/comments", headers=headers_json, json={
                                        "candidateVacancyId": cv_id,
                                        "text": msg
                                    }, timeout=30)
                        print("   💬 История перенесена!")

                save_progress(cand_id)

            except requests.exceptions.RequestException as e:
                print(f"   ❌ ОШИБКА СЕТИ на кандидате {cand_id}: {e}")
                print("🛑 СКРИПТ ОСТАНОВЛЕН. Прогресс сохранен.")
                sys.exit(1)
            except Exception as e:
                print(f"   ❌ НЕИЗВЕСТНАЯ ОШИБКА на {cand_id}: {e}")
                print("🛑 СКРИПТ ОСТАНОВЛЕН. Прогресс сохранен.")
                sys.exit(1)

            if i < total_to_process - 1:
                print(f"\n   ⏳ Пауза {DELAY_SECONDS} секунд...")
                time.sleep(DELAY_SECONDS)
                
    except KeyboardInterrupt:
        print("\n\n🛑 ВЫ ОСТАНОВИЛИ СКРИПТ (Ctrl+C).")
        print("✅ Весь прогресс сохранен в migrated_ids.txt. При следующем запуске продолжим с этого места!")

if __name__ == "__main__":
    run_migration()