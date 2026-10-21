import os
import json
import base64
import re
import requests
from pathlib import Path
from datetime import datetime

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
API_URL = "http://localhost:3000/api"
EMAIL = "adminTest2@by.local"
PASSWORD = "123456"
BASE_DIR = Path(r"C:\NW\oldBaseWork\huntflow_full_export")

# Список папок для теста (оставь пустым [], чтобы перенести ВСЮ базу)
TARGET_FOLDERS = ["53810208", "55725085"]

vacancies_map = {}
statuses_map = {}
tags_map = {}

RU_MONTHS = {
    'январь': 1, 'января': 1, 'февраль': 2, 'февраля': 2,
    'март': 3, 'марта': 3, 'апрель': 4, 'апреля': 4,
    'май': 5, 'мая': 5, 'июнь': 6, 'июня': 6,
    'июль': 7, 'июля': 7, 'август': 8, 'августа': 8,
    'сентябрь': 9, 'сентября': 9, 'октябрь': 10, 'октября': 10,
    'ноябрь': 11, 'ноября': 11, 'декабрь': 12, 'декабря': 12
}

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
    print("✅ Успешно авторизован!")
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

def get_archive_vacancy_id(token):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    title = "Архив истории Huntflow"
    res = requests.get(f"{API_URL}/vacancies?search={title}&status=closed", headers=headers)
    data = res.json().get("data", [])
    if data:
        return data[0]["id"]
    
    res = requests.post(f"{API_URL}/vacancies", headers=headers, json={"title": title, "status": "closed"})
    return res.json()["id"]

def normalize_currency(curr):
    if not curr: return None
    curr = curr.upper().strip()
    if curr in ['RUR', 'RUB', 'РУБ', 'РУБ.']: return 'RUB'
    if curr in ['USD', '$']: return 'USD'
    if curr in ['EUR', '€']: return 'EUR'
    if curr in ['BYN', 'БЕЛ. РУБ']: return 'BYN'
    return None

def normalize_edu_level(lvl):
    if not lvl: return 'higher'
    lvl_lower = str(lvl).lower()
    if 'высш' in lvl_lower or 'higher' in lvl_lower: return 'higher'
    if 'средн' in lvl_lower and ('спец' in lvl_lower or 'колледж' in lvl_lower or 'техник' in lvl_lower) or 'vocational' in lvl_lower:
        return 'vocational'
    if 'средн' in lvl_lower or 'secondary' in lvl_lower: return 'secondary'
    if 'курс' in lvl_lower or 'course' in lvl_lower: return 'courses'
    return 'higher'

def parse_exp_string_to_months(s):
    if not s: return None
    years = 0
    months = 0
    m_y = re.search(r'(\d+)\s*(?:год|года|лет)', s)
    if m_y: years = int(m_y.group(1))
    m_m = re.search(r'(\d+)\s*(?:месяц|месяца|месяцев)', s)
    if m_m: months = int(m_m.group(1))
    total = years * 12 + months
    return total if total > 0 else None

def parse_month_year_to_date(m_str, y_str):
    m_num = RU_MONTHS.get(m_str.lower().strip(), 1)
    return f"{y_str}-{str(m_num).zfill(2)}-01"

# ==========================================
# 3. ПАРСЕРЫ РЕЗЮМЕ БЕЗ ИИ
# ==========================================

def parse_structured_resume(resume_data, card_data):
    """Парсинг структурированного резюме (HH-экспорт)"""
    r_data = resume_data.get("data") or {}
    r_base = resume_data.get("resume") or {}

    first_name = card_data.get("first_name") or r_data.get("first_name") or r_base.get("personal_info", {}).get("first_name") or ""
    last_name = card_data.get("last_name") or r_data.get("last_name") or r_base.get("personal_info", {}).get("last_name") or ""
    middle_name = card_data.get("middle_name") or r_data.get("middle_name") or r_base.get("personal_info", {}).get("middle_name") or ""
    full_name = f"{last_name} {first_name} {middle_name}".strip()

    birth_date = card_data.get("birthday") or r_data.get("birth_date")
    gender_raw = (r_data.get("gender") or {}).get("id") or (r_base.get("gender") or {}).get("external_id")
    gender = 'male' if gender_raw in ['male', 'Мужской'] else ('female' if gender_raw in ['female', 'Женский'] else None)

    city = (r_data.get("area") or {}).get("name") or ((r_base.get("area") or {}).get("city") or {}).get("name")
    citizenship = ((r_data.get("citizenship") or [{}])[0]).get("name") or ((r_base.get("citizenship") or [{}])[0]).get("name") or "Россия"

    position = card_data.get("position") or r_base.get("position") or r_data.get("title") or ""
    headline = r_data.get("title") or position

    # Зарплата
    sal_amount = None
    sal_currency = "RUB"
    if r_data.get("salary"):
        sal_amount = r_data["salary"].get("amount")
        sal_currency = normalize_currency(r_data["salary"].get("currency")) or "RUB"
    elif card_data.get("money"):
        money_str = str(card_data["money"])
        digits = re.sub(r"[^\d]", "", money_str)
        if digits: sal_amount = int(digits)
        curr_match = re.search(r"[A-Za-zА-Яа-я$€]+", money_str)
        if curr_match: sal_currency = normalize_currency(curr_match.group(0)) or "RUB"

    # Опыт работы
    exp_items = []
    raw_exp = r_data.get("experience") or r_base.get("experience") or []
    for exp in raw_exp:
        comp = exp.get("company") or "Компания"
        pos = exp.get("position") or "Должность"
        desc = exp.get("description") or ""

        # Даты начала и окончания
        start_date = "2000-01-01"
        if exp.get("start"):
            start_date = exp["start"] if len(exp["start"]) == 10 else f"{exp['start']}-01"
        elif exp.get("date_from"):
            df = exp["date_from"]
            start_date = f"{df.get('year', 2000)}-{str(df.get('month', 1)).zfill(2)}-01"

        end_date = "present"
        if exp.get("end"):
            end_date = exp["end"] if len(exp["end"]) == 10 else f"{exp['end']}-01"
        elif exp.get("date_to"):
            dt = exp["date_to"]
            end_date = f"{dt.get('year', 2020)}-{str(dt.get('month', 1)).zfill(2)}-01"

        exp_items.append({
            "company": comp,
            "position": pos,
            "description": desc,
            "startDate": start_date,
            "endDate": end_date
        })

    total_months = (r_data.get("total_experience") or {}).get("months")
    total_string = ""
    if total_months:
        y = total_months // 12
        m = total_months % 12
        total_string = f"{y} лет {m} месяцев" if y > 0 else f"{m} месяцев"

    # Образование
    edu_info = r_data.get("education") or r_base.get("education") or {}
    edu_level = normalize_edu_level((edu_info.get("level") or {}).get("name"))
    edu_items = []
    for ed in (edu_info.get("higher") or []) + (edu_info.get("primary") or []):
        year_val = ed.get("year") or (ed.get("date_to") or {}).get("year") or ""
        edu_items.append({
            "institution": ed.get("name") or "Учебное заведение",
            "year": str(year_val) if year_val else None,
            "faculty": ed.get("faculty") or ed.get("organization") or None,
            "specialty": ed.get("specialty") or ed.get("result") or ed.get("description") or "Специалист"
        })

    # Навыки
    skills = r_data.get("skill_set") or r_base.get("skill_set") or []

    # Дополнительно
    languages = []
    for l in (r_data.get("language") or r_base.get("language") or []):
        lvl_name = (l.get("level") or {}).get("name") if isinstance(l.get("level"), dict) else l.get("level")
        languages.append({"language": l.get("name", ""), "level": lvl_name or "родной"})

    specs = " • ".join([s.get("name", "") for s in r_data.get("specialization") or []])

    return {
        "fullName": full_name, "firstName": first_name, "lastName": last_name, "middleName": middle_name,
        "birthDate": birth_date, "gender": gender, "city": city, "citizenship": citizenship,
        "position": position, "headline": headline,
        "salaryAmount": sal_amount, "salaryCurrency": sal_currency,
        "employmentType": (r_data.get("employment") or {}).get("name") or "Полная занятость",
        "relocation": (r_data.get("relocation") or {}).get("type", {}).get("name") or "не готов к переезду",
        "businessTrips": (r_data.get("business_trip_readiness") or {}).get("name") or "Не готов к командировкам",
        "totalMonths": total_months, "totalString": total_string, "expItems": exp_items,
        "eduLevel": edu_level, "eduItems": edu_items, "skills": skills,
        "languages": languages, "category": specs, "resumeUpdatedAt": (r_data.get("updated_at") or "")[:10]
    }


def parse_unstructured_body(body_text, card_data):
    """Парсинг сырого текста резюме (HH/NATIVE экспорт) с помощью регулярных выражений"""
    first_name = card_data.get("first_name") or ""
    last_name = card_data.get("last_name") or ""
    middle_name = card_data.get("middle_name") or ""
    full_name = f"{last_name} {first_name} {middle_name}".strip()

    birth_date = card_data.get("birthday")
    gender = 'male' if 'Мужчина' in body_text else ('female' if 'Женщина' in body_text else None)

    # Город и гражданство
    m_city = re.search(r'Проживает:\s*([^\n,]+)', body_text)
    city = m_city.group(1).strip() if m_city else "Минск"

    m_cit = re.search(r'Гражданство:\s*([^\n,]+)', body_text)
    citizenship = m_cit.group(1).strip() if m_cit else "Беларусь"

    # Должность
    position = card_data.get("position") or ""
    m_pos = re.search(r'Желаемая должность и зарплата\s*\n+([^\n]+)', body_text)
    if m_pos:
        position = m_pos.group(1).strip()
    headline = card_data.get("position") or position

    # Переезд и командировки
    m_rel = re.search(r'(Готов к переезду[^\n,]*|Не готов к переезду[^\n,]*)', body_text, re.IGNORECASE)
    relocation = m_rel.group(1).strip() if m_rel else "Готов к переезду"

    m_trip = re.search(r'(готов к [^\n,]*командировкам|не готов к командировкам)', body_text, re.IGNORECASE)
    business_trips = m_trip.group(1).strip() if m_trip else "готов к редким командировкам"

    # Занятость
    m_emp = re.search(r'Занятость:\s*([^\n]+)', body_text)
    employment_type = m_emp.group(1).strip() if m_emp else "полная занятость"

    # Опыт работы (поиск блоков с датами)
    m_tot_exp = re.search(r'Опыт работы\s*[—–-]\s*([^\n]+)', body_text)
    total_string = m_tot_exp.group(1).strip() if m_tot_exp else ""
    total_months = parse_exp_string_to_months(total_string)

    exp_items = []
    # Выделяем блок между "Опыт работы" и "Образование"
    exp_block_m = re.search(r'Опыт работы.*?\n(?P<content>.*?)(?=\nОбразование|\nКлючевые навыки|\Z)', body_text, re.DOTALL)
    if exp_block_m:
        content = exp_block_m.group('content')
        date_pattern = re.compile(
            r'(?P<m1>Январь|Февраль|Март|Апрель|Май|Июнь|Июль|Август|Сентябрь|Октябрь|Ноябрь|Декабрь)\s+(?P<y1>\d{4})\s*[—–-]\s*(?:\n\s*)?'
            r'(?P<end>настоящее время|по настоящее время|(?:Январь|Февраль|Март|Апрель|Май|Июнь|Июль|Август|Сентябрь|Октябрь|Ноябрь|Декабрь)\s+\d{4})',
            re.IGNORECASE
        )
        matches = list(date_pattern.finditer(content))
        for i, match in enumerate(matches):
            start_date = parse_month_year_to_date(match.group('m1'), match.group('y1'))
            end_val = match.group('end').lower()
            if 'настоящее' in end_val:
                end_date = "present"
            else:
                parts = end_val.split()
                end_date = parse_month_year_to_date(parts[0], parts[1])

            # Текст между текущей датой и следующей
            text_start = match.end()
            text_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            chunk = content[text_start:text_end].strip()

            lines = [ln.strip() for ln in chunk.split('\n') if ln.strip()]
            # Фильтруем длительность (например, "3 месяца", "2 года 5 месяцев")
            filtered_lines = []
            for ln in lines:
                if re.match(r'^(?:\(?\d+\s*(?:год|года|лет|месяц|месяца|месяцев)\)?\s*)+$', ln, re.IGNORECASE):
                    continue
                if 'резюме обновлено' in ln.lower():
                    continue
                filtered_lines.append(ln)

            comp = filtered_lines[0] if len(filtered_lines) > 0 else "Компания"
            pos = filtered_lines[1] if len(filtered_lines) > 1 else "Специалист"
            desc_lines = filtered_lines[2:] if len(filtered_lines) > 2 else []
            desc = "\n".join(desc_lines)

            exp_items.append({
                "company": comp,
                "position": pos,
                "description": desc,
                "startDate": start_date,
                "endDate": end_date
            })

    # Образование
    edu_items = []
    edu_level = 'higher'
    edu_block_m = re.search(r'Образование\s*\n+(.*?)(?=\nКлючевые навыки|\nНавыки|\nОпыт вождения|\nДополнительная информация|\Z)', body_text, re.DOTALL)
    if edu_block_m:
        e_content = edu_block_m.group(1).strip()
        m_lvl = re.search(r'(Высшее|Среднее специальное|Среднее|Неоконченное высшее)', e_content, re.IGNORECASE)
        if m_lvl: edu_level = normalize_edu_level(m_lvl.group(1))

        # Паттерн "2022 Название вуза \n Специальность/Факультет"
        item_matches = re.finditer(r'(?P<year>\d{4})\s+(?P<inst>[^\n]+)\n+(?P<detail>[^\n]+)', e_content)
        for im in item_matches:
            year_val = im.group('year')
            inst = im.group('inst').strip()
            detail = im.group('detail').strip()

            faculty = None
            specialty = detail
            if ',' in detail:
                d_parts = detail.split(',', 1)
                faculty = d_parts[0].strip()
                specialty = d_parts[1].strip()

            edu_items.append({
                "institution": inst,
                "year": year_val,
                "faculty": faculty,
                "specialty": specialty
            })

    # Навыки
    skills = []
    m_sk = re.search(r'Навыки\s+([^\n]+)', body_text)
    if m_sk:
        skills.extend([s.strip() for s in re.split(r'[,;•]+', m_sk.group(1)) if s.strip()])

    # Языки
    languages = []
    lang_matches = re.findall(r'([А-Яа-яA-Za-z]+)\s*[—–-]\s*([А-Яа-яA-Za-z0-9\s()]+)', body_text)
    for l_name, l_lvl in lang_matches:
        if l_name.lower() in ['русский', 'английский', 'немецкий', 'французский', 'польский']:
            languages.append({"language": l_name.strip(), "level": l_lvl.strip()})
            skills.append(f"{l_name.strip()} ({l_lvl.strip()})")

    # Права категории
    driver_license = None
    m_drv = re.search(r'Права категори(?:и|й)\s*([A-Za-z,\s]+)', body_text)
    if m_drv:
        driver_license = m_drv.group(1).strip()
        skills.append("Опыт вождения")

    # Дата обновления резюме в тексте
    resume_updated_at = None
    m_upd = re.search(r'Резюме обновлено\s*(\d{1,2}\s+[а-я]+\s+\d{4})', body_text, re.IGNORECASE)
    if m_upd:
        resume_updated_at = m_upd.group(1)

    return {
        "fullName": full_name, "firstName": first_name, "lastName": last_name, "middleName": middle_name,
        "birthDate": birth_date, "gender": gender, "city": city, "citizenship": citizenship,
        "position": position, "headline": headline,
        "salaryAmount": None, "salaryCurrency": None,
        "employmentType": employment_type, "relocation": relocation, "businessTrips": business_trips,
        "totalMonths": total_months, "totalString": total_string, "expItems": exp_items,
        "eduLevel": edu_level, "eduItems": edu_items, "skills": skills,
        "languages": languages, "driverLicense": driver_license, "resumeUpdatedAt": resume_updated_at
    }

# ==========================================
# 4. ОСНОВНОЙ ПРОЦЕСС МИГРАЦИИ
# ==========================================
def run_migration():
    load_metadata()
    token = login()
    headers_json = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    archive_vac_id = get_archive_vacancy_id(token)
    applicants_dir = BASE_DIR / "applicants"
    
    if not applicants_dir.exists():
        print("❌ Папка applicants не найдена!")
        return

    folders = [f for f in applicants_dir.iterdir() if f.is_dir() and (not TARGET_FOLDERS or f.name in TARGET_FOLDERS)]
    print(f"\n🚀 Начинаем перенос кандидатов ({len(folders)} шт.)...\n")

    for folder in folders:
        cand_id = folder.name
        print(f"{'='*60}\n👉 Обработка кандидата ID: {cand_id}")

        card_file = folder / "card.json"
        if not card_file.exists():
            continue

        with open(card_file, "r", encoding="utf-8") as f:
            card_data = json.load(f)

        # 1. Поиск резюме (ИСПРАВЛЕН ГЛОББИНГ: resume_*.json)
        resume_data = {}
        files_dir = folder / "files"
        if files_dir.exists():
            for rf in files_dir.glob("resume*.json"):
                with open(rf, "r", encoding="utf-8") as f:
                    resume_data = json.load(f)
                break
        if not resume_data:
            for rf in folder.glob("resume*.json"):
                with open(rf, "r", encoding="utf-8") as f:
                    resume_data = json.load(f)
                break

        # 2. Выбор метода парсинга
        r_info = resume_data.get("resume") or {}
        r_data = resume_data.get("data") or {}
        raw_body = r_data.get("body") if isinstance(r_data, dict) else ""

        if r_info.get("experience") or (isinstance(r_data, dict) and r_data.get("experience")):
            print("   📄 Обнаружено структурированное резюме (HH/JSON)")
            parsed = parse_structured_resume(resume_data, card_data)
        elif raw_body:
            print("   📝 Обнаружен текст резюме (NATIVE) — парсинг регулярными выражениями")
            parsed = parse_unstructured_body(raw_body, card_data)
        else:
            print("   ⚠️ Резюме отсутствует, переносим базовые данные из карточки")
            parsed = parse_unstructured_body("", card_data)

        # 3. Фотография (Base64 или ссылка)
        photo_b64 = None
        if files_dir.exists() and (files_dir / "photo.jpg").exists():
            with open(files_dir / "photo.jpg", "rb") as img:
                b64_str = base64.b64encode(img.read()).decode("utf-8")
                photo_b64 = f"data:image/jpeg;base64,{b64_str}"
        elif card_data.get("photo_url"):
            photo_b64 = card_data["photo_url"]

        # 4. Теги кандидата
        hf_tags = []
        for t in card_data.get("tags") or []:
            t_name = tags_map.get(t.get("tag"))
            if t_name: hf_tags.append(t_name.strip())

        # Дополняем навыки тегами-технологиями (например SAP, NX)
        combined_skills = list(dict.fromkeys(parsed.get("skills", []) + hf_tags))

        # Текущий статус в воронке Huntflow
        detected_status = None
        if card_data.get("links"):
            detected_status = statuses_map.get(card_data["links"][0].get("status"))

        # 5. Сборка полного PAYLOAD для /candidates/from-parser
        payload = {
            "personal": {
                "fullName": parsed.get("fullName"),
                "firstName": parsed.get("firstName"),
                "lastName": parsed.get("lastName"),
                "middleName": parsed.get("middleName"),
                "gender": parsed.get("gender"),
                "birthDate": parsed.get("birthDate"),
                "city": parsed.get("city"),
                "citizenship": parsed.get("citizenship"),
                "photoUrl": photo_b64
            },
            "preferences": {
                "position": parsed.get("position"),
                "headline": parsed.get("headline"),
                "salary": {
                    "amount": parsed.get("salaryAmount"),
                    "currency": parsed.get("salaryCurrency") or "RUB"
                } if parsed.get("salaryAmount") else None,
                "employmentType": parsed.get("employmentType"),
                "relocation": parsed.get("relocation"),
                "businessTrips": parsed.get("businessTrips")
            },
            "experience": {
                "totalMonths": parsed.get("totalMonths"),
                "totalString": parsed.get("totalString"),
                "items": parsed.get("expItems", [])
            },
            "skills": combined_skills,
            "education": {
                "level": parsed.get("eduLevel", "higher"),
                "items": parsed.get("eduItems", [])
            },
            "contacts": {
                "phones": [card_data["phone"]] if card_data.get("phone") else [],
                "emails": [card_data["email"]] if card_data.get("email") else [],
                "telegram": card_data.get("skype") or None,
                "links": [f"http://huntflow.local/applicants/{cand_id}"]
            },
            "additional": {
                "languages": parsed.get("languages", []),
                "driverLicense": parsed.get("driverLicense"),
                "category": parsed.get("category"),
                "resumeUpdatedAt": parsed.get("resumeUpdatedAt")
            },
            "source": {
                "platform": "Huntflow",
                "domain": "huntflow.local",
                "baseUrl": "http://huntflow.local",
                "profileUrl": f"http://huntflow.local/applicants/{cand_id}",
                "parsedAt": card_data.get("created") or datetime.now().isoformat(),
                "detectedStatus": detected_status,
                "detectedTags": ["Huntflow Архив"] + hf_tags
            }
        }

        # 6. Отправка кандидата на сервер
        print(f"   📥 Сохранение досье: {parsed.get('lastName')} {parsed.get('firstName')}...")
        res = requests.post(f"{API_URL}/candidates/from-parser", headers=headers_json, json=payload)
        if res.status_code not in [200, 201, 202]:
            print(f"   ❌ Ошибка сохранения кандидата: {res.text}")
            continue

        res_data = res.json()
        cand_uuid = (res_data.get("candidate") or {}).get("id") or res_data.get("id")
        print(f"   ✅ Кандидат сохранён в БД! (UUID: {cand_uuid})")

        # 7. Загрузка оригинальных файлов резюме (.pdf, .docx) в таблицу `files`
        if files_dir.exists():
            for file_path in files_dir.iterdir():
                if file_path.suffix.lower() in [".pdf", ".doc", ".docx", ".rtf", ".txt"] and not file_path.name.startswith("resume"):
                    print(f"   📎 Загрузка файла {file_path.name}...")
                    with open(file_path, "rb") as f:
                        files = {"file": (file_path.name, f, "application/octet-stream")}
                        # ВАЖНО: передаём entityType и entityId в URL params, как того требует контроллер NestJS
                        f_res = requests.post(
                            f"{API_URL}/files",
                            headers={"Authorization": f"Bearer {token}"},
                            params={"entityType": "candidate", "entityId": cand_uuid},
                            files=files
                        )
                        if f_res.status_code == 201:
                            print(f"      ✅ Файл {file_path.name} сохранён в files!")
                        else:
                            print(f"      ⚠️ Ошибка файла: {f_res.text}")

        # 8. Добавление в архивную вакансию и перенос истории
        cv_id = None
        cv_res = requests.post(f"{API_URL}/candidates/{cand_uuid}/vacancies", headers=headers_json, json={"vacancyId": archive_vac_id})
        if cv_res.status_code == 201:
            cv_id = cv_res.json()["id"]
        elif cv_res.status_code == 400:
            # Если кандидат уже на этой вакансии, получаем его pipeline
            pipe_res = requests.get(f"{API_URL}/candidates/{cand_uuid}/pipeline", headers=headers_json)
            if pipe_res.status_code == 200:
                for cv_item in pipe_res.json():
                    if cv_item.get("vacancyId") == archive_vac_id:
                        cv_id = cv_item["id"]
                        break

        if cv_id:
            # Читаем историю и комментарии
            history_file = folder / "history_and_chat.json"
            if history_file.exists():
                with open(history_file, "r", encoding="utf-8") as hf:
                    history_list = json.load(hf)
                    history_list.sort(key=lambda x: x.get("created", ""))

                    for h_item in history_list:
                        comment_text = h_item.get("comment")
                        status_name = statuses_map.get(h_item.get("status"), h_item.get("type", "Действие"))
                        orig_vac_name = vacancies_map.get(h_item.get("vacancy"), "Без вакансии")

                        if comment_text or status_name:
                            msg = f"💼 Вакансия: {orig_vac_name}\n📌 Этап: {status_name}"
                            if comment_text:
                                msg += f"\n💬 Комментарий: {comment_text}"

                            requests.post(f"{API_URL}/comments", headers=headers_json, json={
                                "candidateVacancyId": cv_id,
                                "text": msg
                            })
                print("   💬 Вся история и комментарии успешно перенесены в Архив!")
        else:
            print("   ⚠️ Не удалось связать с архивной вакансией")

    print("\n🎉 Миграция успешно завершена!")

if __name__ == "__main__":
    run_migration()