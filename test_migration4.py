import os
import json
import base64
import requests
import time
from pathlib import Path
from datetime import datetime

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
API_URL = "http://localhost:3000/api"
EMAIL = "adminTest2@by.local"
PASSWORD = "123456"  # <--- ВПИШИ ПАРОЛЬ
BASE_DIR = Path(r"C:\NW\oldBaseWork\huntflow_full_export")

# ОСТАВЬ ПУСТЫМ [], ЧТОБЫ ПЕРЕНЕСТИ ВСЕХ (3200 человек)
TARGET_FOLDERS = [] 

# Файл для сохранения прогресса (чтобы можно было прервать и продолжить)
PROGRESS_FILE = Path("migrated_ids.txt")
DELAY_SECONDS = 10  # Пауза между кандидатами

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
    print("   🤖 Отправляем данные на AI-парсинг...")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        # Увеличили таймаут до 60 сек, чтобы ИИ точно успел ответить
        res = requests.post(f"{API_URL}/candidates/parse-raw", headers=headers, json={"rawText": raw_text}, timeout=60)
        if res.status_code in [200, 201]:
            print("   ✅ AI успешно распарсил резюме!")
            return res.json()
        else:
            print(f"   ⚠️ Ошибка AI-парсинга (Код {res.status_code})")
            return {}
    except Exception as e:
        print(f"   ⚠️ Таймаут/Ошибка сети при запросе к ИИ: {e}")
        return {}

def load_progress():
    """Загружает ID уже перенесенных кандидатов"""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            return set(line.strip() for line in f)
    return set()

def save_progress(cand_id):
    """Дописывает ID в файл прогресса"""
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
    # Фильтруем те, что уже перенесены
    folders = [f for f in folders if f.name not in processed_ids]
    
    total_to_process = len(folders)
    print(f"\n🚀 Осталось перенести: {total_to_process} кандидатов (пропущено уже готовых: {len(processed_ids)})")
    
    if total_to_process == 0:
        print("✅ Вся база уже перенесена!")
        return

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
                text_for_ai = ""

            final_parsed_data = parse_raw_with_ai(text_for_ai, token) if text_for_ai else {}

            if not final_parsed_data:
                print("   ⚠️ ИИ не вернул данные. Берем базовые поля из карточки.")
                final_parsed_data = {
                    "personal": {"firstName": card_data.get("first_name", ""), "lastName": card_data.get("last_name", ""), "middleName": card_data.get("middle_name", "")},
                    "preferences": {"position": card_data.get("position", "")},
                    "experience": {"items": []},
                    "skills": [],
                    "education": {"items": []},
                    "additional": {}
                }

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
                    "salary": pref_data.get("salary"),
                    "employmentType": pref_data.get("employmentType"),
                    "relocation": pref_data.get("relocation"),
                    "businessTrips": pref_data.get("businessTrips")
                },
                "experience": {
                    "totalMonths": exp_data.get("totalMonths"),
                    "totalString": exp_data.get("totalString"),
                    "items": exp_data.get("items", [])
                },
                "skills": final_parsed_data.get("skills", []),
                "education": {
                    "level": edu_data.get("level"),
                    "items": edu_data.get("items", [])
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
                print(f"   ❌ ОШИБКА СЕРВЕРА: {res.text}")
                continue
                
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

            original_status_id = card_data.get("links", [{}])[0].get("status")
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

            # СОХРАНЯЕМ ПРОГРЕСС (чтобы в случае сбоя не начинать заново)
            save_progress(cand_id)

        except Exception as e:
            print(f"   ❌ КРИТИЧЕСКАЯ ОШИБКА на кандидате {cand_id}: {e}")
            print("   ⏭️ Пропускаем его и идем дальше...")
            continue

        # === ПАУЗА ===
        if i < total_to_process - 1:
            print(f"\n   ⏳ Пауза {DELAY_SECONDS} секунд...")
            time.sleep(DELAY_SECONDS)

if __name__ == "__main__":
    run_migration()