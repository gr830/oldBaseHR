import os
import json
import base64
import requests
from pathlib import Path
from datetime import datetime

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
API_URL = "http://localhost:3000/api"
EMAIL = "adminTest2@by.local"
PASSWORD = "123456"  # <--- ВПИШИ ПАРОЛЬ
BASE_DIR = Path(r"C:\NW\oldBaseWork\huntflow_full_export")

# Оставь пустым [], чтобы перенести ВСЕХ
TARGET_FOLDERS = ["53810208", "55725085"] 

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
    print("   🤖 Текст неструктурирован. Отправляем на AI-парсинг...")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    res = requests.post(f"{API_URL}/candidates/parse-raw", headers=headers, json={"rawText": raw_text})
    
    if res.status_code in [200, 201]:
        print("   ✅ AI успешно распарсил резюме!")
        return res.json()
    else:
        print(f"   ⚠️ Ошибка AI-парсинга: {res.text}")
        return {}

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
    
    folders = [f for f in applicants_dir.iterdir() if f.is_dir() and (not TARGET_FOLDERS or f.name in TARGET_FOLDERS)]
    print(f"\n🚀 Начинаем перенос ({len(folders)} кандидатов)...")
    
    for folder in folders:
        cand_id = folder.name
        print(f"\n{'='*50}\n👉 Обработка кандидата ID: {cand_id}")
        
        card_file = folder / "card.json"
        if not card_file.exists():
            continue
            
        with open(card_file, "r", encoding="utf-8") as f:
            card_data = json.load(f)

        files_dir = folder / "files"
        resume_files = list(files_dir.glob("resume*.json")) if files_dir.exists() else []
        
        resume_data = {}
        if resume_files:
            with open(resume_files[0], "r", encoding="utf-8") as f:
                resume_data = json.load(f)
                print(f"   📄 Найден файл резюме: {resume_files[0].name}")

        structured_resume = resume_data.get("resume") or {}
        r_data = resume_data.get("data") or {}
        raw_body = r_data.get("body") or ""
        
        final_parsed_data = {}
        
        if structured_resume and (structured_resume.get("experience") or structured_resume.get("personal_info")):
            print("   📄 Обработка структурированного резюме (HH).")
            exp_items = []
            for e in (structured_resume.get("experience") or r_data.get("experience") or []):
                start = e.get("date_from") or {}
                start_str = f"{start.get('year')}-{str(start.get('month', 1)).zfill(2)}" if start else None
                end = e.get("date_to") or {}
                end_str = f"{end.get('year')}-{str(end.get('month', 1)).zfill(2)}" if end else "present"
                
                exp_items.append({
                    "company": e.get("company") or "Не указано",
                    "position": e.get("position") or "Не указано",
                    "startDate": start_str,
                    "endDate": end_str,
                    "description": e.get("description") or ""
                })

            edu_items = []
            edu_info = structured_resume.get("education") or r_data.get("education") or {}
            for ed in (edu_info.get("higher") or edu_info.get("primary") or []):
                date_to = ed.get("date_to") or {}
                edu_items.append({
                    "institution": ed.get("name") or "Не указано",
                    "year": str(date_to.get("year", "")),
                    "faculty": ed.get("faculty") or "",
                    "specialty": ed.get("description") or ed.get("result") or ""
                })

            sal_amount = None
            money_raw = str(card_data.get("money") or "")
            digits = "".join(filter(str.isdigit, money_raw))
            if digits: sal_amount = int(digits)

            # ИЗВЛЕКАЕМ ДОПОЛНИТЕЛЬНУЮ ИНФУ (Языки, Права)
            add_data = {}
            langs = []
            for l in (r_data.get("language") or []):
                langs.append({
                    "language": l.get("name", ""), 
                    "level": (l.get("level") or {}).get("name", "")
                })
            if langs:
                add_data["languages"] = langs
                
            if r_data.get("driver_license_types"):
                add_data["driverLicense"] = ", ".join([d.get("id", "") for d in r_data.get("driver_license_types", [])])
            
            add_data["resumeUpdatedAt"] = r_data.get("updated_at")
            
            final_parsed_data = {
                "personal": {
                    "firstName": card_data.get("first_name") or structured_resume.get("personal_info", {}).get("first_name") or "",
                    "lastName": card_data.get("last_name") or structured_resume.get("personal_info", {}).get("last_name") or "",
                    "middleName": card_data.get("middle_name") or structured_resume.get("personal_info", {}).get("middle_name") or "",
                    "birthDate": card_data.get("birthday"),
                    "city": r_data.get("area", {}).get("name") or structured_resume.get("area", {}).get("city", {}).get("name") or "",
                    "citizenship": (r_data.get("citizenship") or [{}])[0].get("name") or "",
                },
                "preferences": {
                    "position": card_data.get("position") or structured_resume.get("position") or "",
                    "headline": r_data.get("title") or "",
                    "salary": {"amount": sal_amount, "currency": "RUB"} if sal_amount else None,
                    "employmentType": (r_data.get("employment") or {}).get("name") or "",
                    "relocation": (r_data.get("relocation") or {}).get("type", {}).get("name") or "",
                    "businessTrips": (r_data.get("business_trip_readiness") or {}).get("name") or ""
                },
                "experience": {
                    "totalMonths": r_data.get("total_experience", {}).get("months"),
                    "items": exp_items
                },
                "skills": r_data.get("skill_set") or structured_resume.get("skill_set") or [],
                "education": {
                    "level": (edu_info.get("level") or {}).get("name") or "",
                    "items": edu_items
                },
                "additional": add_data
            }

        elif raw_body:
            final_parsed_data = parse_raw_with_ai(raw_body, token)

        if not final_parsed_data:
            print("   ⚠️ Структурированных данных нет. Берем базовые поля из карточки.")
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
        res = requests.post(f"{API_URL}/candidates/from-parser", headers=headers_json, json=payload)
        
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
                            requests.post(f"{API_URL}/files", headers=headers_form, files=files, data=data)
                    except Exception:
                        pass

        original_status_id = card_data.get("links", [{}])[0].get("status")
        original_status_name = statuses_map.get(original_status_id, "Новый кандидат")
        target_stage_id = ats_stages_map.get(original_status_name)

        cv_payload = {"vacancyId": archive_vac_id}
        if target_stage_id:
            cv_payload["stageId"] = target_stage_id
            print(f"   📌 Прикрепляем на этап: {original_status_name}")

        cv_res = requests.post(f"{API_URL}/candidates/{cand_uuid}/vacancies", headers=headers_json, json=cv_payload)
        
        if cv_res.status_code == 201:
            cv_id = cv_res.json()["id"]
            
            # === ПЕРЕНОС ИСТОРИИ (С ДАТОЙ ВНУТРИ ТЕКСТА) ===
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
                        
                        # Форматируем старую дату для вывода в тексте
                        raw_date = h_item.get("created", "")
                        date_str = raw_date[:10] if raw_date else "Дата неизвестна"
                        
                        if comment_text or status_name:
                            # Убрал **, так как твой фронтенд их не парсит
                            msg = f"🕒 Дата: {date_str}\n"
                            msg += f"💼 Вакансия: {original_vac_name}\n"
                            msg += f"📌 Этап: {status_name}"
                            
                            if comment_text: 
                                msg += f"\n💬 Комментарий:\n{comment_text}"
                                
                            requests.post(f"{API_URL}/comments", headers=headers_json, json={
                                "candidateVacancyId": cv_id,
                                "text": msg
                            })
                print("   💬 История перенесена (с реальными датами в тексте)!")

if __name__ == "__main__":
    run_migration()