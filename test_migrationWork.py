# import os
# import json
# import base64
# import re
# import time
# import requests
# from pathlib import Path
# from datetime import datetime

# # ==========================================
# # 1. НАСТРОЙКИ
# # ==========================================
# API_URL = "http://localhost:3000/api"
# EMAIL = "adminTest2@by.local"
# PASSWORD = "123456"
# BASE_DIR = Path(r"C:\NW\oldBaseWork\huntflow_full_export")

# # ⚠️ ДЛЯ ПЕРЕНОСА ВСЕХ 3183 КАНДИДАТОВ ОСТАВЬТЕ СПИСОК ПУСТЫМ: TARGET_FOLDERS = []
# # Если хотите протестировать конкретного (например Киселева) — впишите его ID папки:
# TARGET_FOLDERS = []

# # Небольшая пауза между кандидатами в секундах (чтобы сервер не захлебывался)
# DELAY_BETWEEN_CANDIDATES = 2

# STATE_FILE = Path("migration_state.json")
# LOG_FILE = Path("migration_log.txt")

# vacancies_map = {}
# statuses_map = {}
# tags_map = {}
# reasons_map = {}
# ats_stages_by_name = {}

# current_token = None
# token_issued_at = 0

# RU_MONTHS = {
#     'январь': 1, 'января': 1, 'февраль': 2, 'февраля': 2,
#     'март': 3, 'марта': 3, 'апрель': 4, 'апреля': 4,
#     'май': 5, 'мая': 5, 'июнь': 6, 'июня': 6,
#     'июль': 7, 'июля': 7, 'август': 8, 'августа': 8,
#     'сентябрь': 9, 'сентября': 9, 'октябрь': 10, 'октября': 10,
#     'ноябрь': 11, 'ноября': 11, 'декабрь': 12, 'декабря': 12
# }

# # ==========================================
# # 2. УПРАВЛЕНИЕ ЛОГАМИ И СОСТОЯНИЕМ
# # ==========================================
# def log_message(msg: str):
#     print(msg)
#     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     clean_msg = re.sub(r'[^\w\s\d.,:;!@#$%^&*()_+=\-\[\]{}|\\/<>?~`"\'а-яА-ЯёЁ]', '', msg)
#     try:
#         with open(LOG_FILE, "a", encoding="utf-8") as f:
#             f.write(f"[{timestamp}] {clean_msg}\n")
#     except Exception:
#         pass

# def load_migration_state():
#     if STATE_FILE.exists():
#         try:
#             with open(STATE_FILE, "r", encoding="utf-8") as f:
#                 return json.load(f)
#         except Exception:
#             pass
#     return {"completed": [], "failed": {}}

# def save_migration_state(state):
#     try:
#         with open(STATE_FILE, "w", encoding="utf-8") as f:
#             json.dump(state, f, ensure_ascii=False, indent=2)
#     except Exception as e:
#         print(f"⚠️ Ошибка сохранения прогресса: {e}")

# # ==========================================
# # 3. АВТОРИЗАЦИЯ И СЕТЕВЫЕ ЗАПРОСЫ (С АВТО-ОБНОВЛЕНИЕМ ТОКЕНА)
# # ==========================================
# def login():
#     global current_token, token_issued_at
#     log_message(f"🔐 Получение JWT токена для {EMAIL}...")
#     res = requests.post(f"{API_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD})
#     if res.status_code not in [200, 201]:
#         log_message(f"❌ Ошибка входа: {res.text}")
#         exit(1)
#     current_token = res.json().get("accessToken")
#     token_issued_at = time.time()
#     log_message("✅ Токен успешно получен и обновлен!")
#     return current_token

# def get_auth_token(force_refresh=False):
#     """Автоматически обновляет токен, если прошло более 8 минут"""
#     global current_token, token_issued_at
#     if force_refresh or not current_token or (time.time() - token_issued_at > 480):
#         login()
#     return current_token

# def api_request(method, endpoint, **kwargs):
#     """Универсальная обертка: при 401 автоматически перелогинивается и повторяет запрос"""
#     token = get_auth_token()
#     headers = kwargs.get("headers", {})
#     headers["Authorization"] = f"Bearer {token}"
#     kwargs["headers"] = headers

#     url = f"{API_URL}{endpoint}" if endpoint.startswith("/") else f"{API_URL}/{endpoint}"
#     res = requests.request(method, url, **kwargs)

#     if res.status_code == 401:
#         log_message("⚠️ Токен истек (401). Автоматический перелогин...")
#         token = get_auth_token(force_refresh=True)
#         headers["Authorization"] = f"Bearer {token}"
#         kwargs["headers"] = headers
#         res = requests.request(method, url, **kwargs)

#     return res

# # ==========================================
# # 4. СПРАВОЧНИКИ
# # ==========================================
# def load_metadata():
#     log_message("📂 Загрузка справочников Huntflow...")
#     meta_dir = BASE_DIR / "metadata"
    
#     if (meta_dir / "vacancies.json").exists():
#         with open(meta_dir / "vacancies.json", "r", encoding="utf-8") as f:
#             for v in json.load(f):
#                 vacancies_map[v["id"]] = v.get("position", f"Вакансия #{v['id']}")
                
#     if (meta_dir / "statuses.json").exists():
#         with open(meta_dir / "statuses.json", "r", encoding="utf-8") as f:
#             for s in json.load(f).get("items", []):
#                 statuses_map[s["id"]] = s.get("name")
                
#     if (meta_dir / "tags.json").exists():
#         with open(meta_dir / "tags.json", "r", encoding="utf-8") as f:
#             for t in json.load(f).get("items", []):
#                 tags_map[t["id"]] = t.get("name")

#     if (meta_dir / "rejection_reasons.json").exists():
#         with open(meta_dir / "rejection_reasons.json", "r", encoding="utf-8") as f:
#             for r in json.load(f).get("items", []):
#                 reasons_map[r["id"]] = r.get("name")
#         log_message(f"   • Найдено причин отказа: {len(reasons_map)}")

# def load_ats_stages():
#     log_message("📋 Получение стадий воронки компании из ATS...")
#     res = api_request("GET", "/stages")
#     if res.status_code == 200:
#         for stage in res.json():
#             ats_stages_by_name[stage["name"]] = stage["id"]
#         log_message(f"✅ Найдено стадий в ATS: {len(ats_stages_by_name)}")
#     else:
#         log_message(f"⚠️ Ошибка получения стадий: {res.text}")

# def get_archive_vacancy_id():
#     title = "Архив истории Huntflow"
#     res = api_request("GET", f"/vacancies?search={title}&status=closed")
#     data = res.json().get("data", [])
#     if data:
#         return data[0]["id"]
    
#     res = api_request("POST", "/vacancies", json={"title": title, "status": "closed"})
#     return res.json()["id"]

# def map_huntflow_status_to_ats_stage_id(hf_status_name):
#     if not hf_status_name:
#         return ats_stages_by_name.get("Новый кандидат")

#     lower = hf_status_name.lower().strip()

#     if 'трудоустроен' in lower or 'исп. срок' in lower or 'нанят' in lower:
#         target = "Трудоустроен"
#     elif 'отказ' in lower:
#         target = "Отказ кандидата"
#     elif 'оффер' in lower:
#         target = "Выставление оффера"
#     elif 'принятие решения' in lower or 'согласование' in lower:
#         target = "Принятие решения"
#     elif 'hr' in lower or 'хр' in lower or 'интервью с hr' in lower:
#         target = "Интервью с HR"
#     elif 'руководител' in lower or 'заказчик' in lower:
#         target = "Интервью с руководителем"
#     elif 'техническ' in lower:
#         target = "Техническое интервью"
#     elif 'тестов' in lower:
#         target = "Тестовое задание"
#     elif 'телефон' in lower:
#         target = "Телефонное интервью"
#     elif 'письмо' in lower or 'смс' in lower or 'приглашение' in lower:
#         target = "Отправлено письмо"
#     elif 'база' in lower or 'резерв' in lower:
#         target = "База"
#     else:
#         target = "Новый кандидат"

#     return ats_stages_by_name.get(target) or ats_stages_by_name.get("Новый кандидат")

# def calculate_age(birth_date_str):
#     if not birth_date_str: return None
#     try:
#         b_date = datetime.strptime(str(birth_date_str)[:10], "%Y-%m-%d")
#         today = datetime.now()
#         return today.year - b_date.year - ((today.month, today.day) < (b_date.month, b_date.day))
#     except Exception:
#         return None

# def pluralize(n, one, two, five):
#     n = abs(int(n)) % 100
#     n1 = n % 10
#     if 10 < n < 20: return five
#     if 1 < n1 < 5: return two
#     if n1 == 1: return one
#     return five

# def format_experience_string(total_months):
#     if not total_months: return ""
#     y = total_months // 12
#     m = total_months % 12
#     parts = []
#     if y > 0: parts.append(f"{y} {pluralize(y, 'год', 'года', 'лет')}")
#     if m > 0: parts.append(f"{m} {pluralize(m, 'месяц', 'месяца', 'месяцев')}")
#     return " ".join(parts)

# def normalize_currency(curr):
#     if not curr: return None
#     curr = curr.upper().strip()
#     if curr in ['RUR', 'RUB', 'РУБ', 'РУБ.']: return 'RUB'
#     if curr in ['USD', '$']: return 'USD'
#     if curr in ['EUR', '€']: return 'EUR'
#     if curr in ['BYN', 'БЕЛ. РУБ']: return 'BYN'
#     return None

# def normalize_edu_level(lvl):
#     if not lvl: return 'higher'
#     lvl_lower = str(lvl).lower()
#     if 'высш' in lvl_lower or 'higher' in lvl_lower: return 'higher'
#     if 'средн' in lvl_lower and ('спец' in lvl_lower or 'колледж' in lvl_lower or 'техник' in lvl_lower) or 'vocational' in lvl_lower:
#         return 'vocational'
#     if 'средн' in lvl_lower or 'secondary' in lvl_lower: return 'secondary'
#     if 'курс' in lvl_lower or 'course' in lvl_lower: return 'courses'
#     return 'higher'

# def parse_exp_string_to_months(s):
#     if not s: return None
#     years = 0
#     months = 0
#     m_y = re.search(r'(\d+)\s*(?:год|года|лет)', s)
#     if m_y: years = int(m_y.group(1))
#     m_m = re.search(r'(\d+)\s*(?:месяц|месяца|месяцев)', s)
#     if m_m: months = int(m_m.group(1))
#     total = years * 12 + months
#     return total if total > 0 else None

# def parse_month_year_to_date(m_str, y_str):
#     m_num = RU_MONTHS.get(m_str.lower().strip(), 1)
#     return f"{y_str}-{str(m_num).zfill(2)}-01"

# # ==========================================
# # 5. ПАРСИНГ РЕЗЮМЕ
# # ==========================================
# def parse_structured_resume(resume_data, card_data):
#     r_data = resume_data.get("data") or {}
#     r_base = resume_data.get("resume") or {}

#     first_name = card_data.get("first_name") or r_data.get("first_name") or r_base.get("personal_info", {}).get("first_name") or ""
#     last_name = card_data.get("last_name") or r_data.get("last_name") or r_base.get("personal_info", {}).get("last_name") or ""
#     middle_name = card_data.get("middle_name") or r_data.get("middle_name") or r_base.get("personal_info", {}).get("middle_name") or ""
#     full_name = f"{last_name} {first_name} {middle_name}".strip()

#     birth_date = card_data.get("birthday") or r_data.get("birth_date")
#     age = calculate_age(birth_date)

#     gender_raw = (r_data.get("gender") or {}).get("id") or (r_base.get("gender") or {}).get("external_id")
#     gender = 'male' if gender_raw in ['male', 'Мужской'] else ('female' if gender_raw in ['female', 'Женский'] else None)

#     city = (r_data.get("area") or {}).get("name") or ((r_base.get("area") or {}).get("city") or {}).get("name")
#     citizenship = ((r_data.get("citizenship") or [{}])[0]).get("name") or ((r_base.get("citizenship") or [{}])[0]).get("name") or "Россия"

#     desired_pos = r_data.get("title") or r_base.get("position") or card_data.get("position") or ""

#     sal_amount = None
#     sal_currency = "RUB"
#     if r_data.get("salary"):
#         sal_amount = r_data["salary"].get("amount")
#         sal_currency = normalize_currency(r_data["salary"].get("currency")) or "RUB"
#     elif card_data.get("money"):
#         money_str = str(card_data["money"])
#         digits = re.sub(r"[^\d]", "", money_str)
#         if digits: sal_amount = int(digits)
#         curr_match = re.search(r"[A-Za-zА-Яа-я$€]+", money_str)
#         if curr_match: sal_currency = normalize_currency(curr_match.group(0)) or "RUB"

#     exp_items = []
#     raw_exp = r_data.get("experience") or r_base.get("experience") or []
#     for exp in raw_exp:
#         comp = exp.get("company") or "Компания"
#         pos = exp.get("position") or "Должность"
#         desc = exp.get("description") or ""

#         start_date = "2000-01-01"
#         if exp.get("start"):
#             start_date = exp["start"] if len(exp["start"]) == 10 else f"{exp['start']}-01"
#         elif exp.get("date_from"):
#             df = exp["date_from"]
#             start_date = f"{df.get('year', 2000)}-{str(df.get('month', 1)).zfill(2)}-01"

#         end_date = "present"
#         if exp.get("end"):
#             end_date = exp["end"] if len(exp["end"]) == 10 else f"{exp['end']}-01"
#         elif exp.get("date_to"):
#             dt = exp["date_to"]
#             end_date = f"{dt.get('year', 2020)}-{str(dt.get('month', 1)).zfill(2)}-01"

#         exp_items.append({
#             "company": comp,
#             "position": pos,
#             "description": desc,
#             "startDate": start_date,
#             "endDate": end_date
#         })

#     total_months = (r_data.get("total_experience") or {}).get("months")
#     total_string = format_experience_string(total_months)

#     edu_info = r_data.get("education") or r_base.get("education") or {}
#     edu_level = normalize_edu_level((edu_info.get("level") or {}).get("name"))
#     edu_items = []
#     for ed in (edu_info.get("higher") or []) + (edu_info.get("primary") or []):
#         year_val = ed.get("year") or (ed.get("date_to") or {}).get("year") or ""
#         edu_items.append({
#             "institution": ed.get("name") or "Учебное заведение",
#             "year": str(year_val) if year_val else None,
#             "faculty": ed.get("faculty") or ed.get("organization") or None,
#             "specialty": ed.get("specialty") or ed.get("result") or ed.get("description") or "Специалист"
#         })

#     skills = r_data.get("skill_set") or r_base.get("skill_set") or []
#     languages = []
#     for l in (r_data.get("language") or r_base.get("language") or []):
#         lvl_name = (l.get("level") or {}).get("name") if isinstance(l.get("level"), dict) else l.get("level")
#         languages.append({"language": l.get("name", ""), "level": lvl_name or "родной"})

#     specs = " • ".join([s.get("name", "") for s in r_data.get("specialization") or []])

#     return {
#         "fullName": full_name, "firstName": first_name, "lastName": last_name, "middleName": middle_name,
#         "birthDate": birth_date, "age": age, "gender": gender, "city": city, "citizenship": citizenship,
#         "position": desired_pos, "headline": desired_pos,
#         "salaryAmount": sal_amount, "salaryCurrency": sal_currency,
#         "employmentType": (r_data.get("employment") or {}).get("name") or "Полная занятость",
#         "relocation": (r_data.get("relocation") or {}).get("type", {}).get("name") or "не готов к переезду",
#         "businessTrips": (r_data.get("business_trip_readiness") or {}).get("name") or "Не готов к командировкам",
#         "totalMonths": total_months, "totalString": total_string, "expItems": exp_items,
#         "eduLevel": edu_level, "eduItems": edu_items, "skills": skills,
#         "languages": languages, "category": specs, "resumeUpdatedAt": (r_data.get("updated_at") or "")[:10]
#     }

# def parse_unstructured_body(body_text, card_data):
#     first_name = card_data.get("first_name") or ""
#     last_name = card_data.get("last_name") or ""
#     middle_name = card_data.get("middle_name") or ""
#     full_name = f"{last_name} {first_name} {middle_name}".strip()

#     birth_date = card_data.get("birthday")
#     age = calculate_age(birth_date)
#     gender = 'male' if 'Мужчина' in body_text else ('female' if 'Женщина' in body_text else None)

#     m_city = re.search(r'Проживает:\s*([^\n,]+)', body_text)
#     city = m_city.group(1).strip() if m_city else "Минск"

#     m_cit = re.search(r'Гражданство:\s*([^\n,]+)', body_text)
#     citizenship = m_cit.group(1).strip() if m_cit else "Беларусь"

#     position = card_data.get("position") or ""
#     m_pos = re.search(r'Желаемая должность и зарплата\s*\n+([^\n]+)', body_text)
#     if m_pos:
#         position = m_pos.group(1).strip()
#     headline = position

#     m_rel = re.search(r'(Готов к переезду[^\n,]*|Не готов к переезду[^\n,]*)', body_text, re.IGNORECASE)
#     relocation = m_rel.group(1).strip() if m_rel else "Готов к переезду"

#     m_trip = re.search(r'(готов к [^\n,]*командировкам|не готов к командировкам)', body_text, re.IGNORECASE)
#     business_trips = m_trip.group(1).strip() if m_trip else "готов к редким командировкам"

#     m_emp = re.search(r'Занятость:\s*([^\n]+)', body_text)
#     employment_type = m_emp.group(1).strip() if m_emp else "полная занятость"

#     m_tot_exp = re.search(r'Опыт работы\s*[—–-]\s*([^\n]+)', body_text)
#     total_string = m_tot_exp.group(1).strip() if m_tot_exp else ""
#     total_months = parse_exp_string_to_months(total_string)

#     exp_items = []
#     exp_block_m = re.search(r'Опыт работы.*?\n(?P<content>.*?)(?=\nОбразование|\nКлючевые навыки|\Z)', body_text, re.DOTALL)
#     if exp_block_m:
#         content = exp_block_m.group('content')
#         date_pattern = re.compile(
#             r'(?P<m1>Январь|Февраль|Март|Апрель|Май|Июнь|Июль|Август|Сентябрь|Октябрь|Ноябрь|Декабрь)\s+(?P<y1>\d{4})\s*[—–-]\s*(?:\n\s*)?'
#             r'(?P<end>настоящее время|по настоящее время|(?:Январь|Февраль|Март|Апрель|Май|Июнь|Июль|Август|Сентябрь|Октябрь|Ноябрь|Декабрь)\s+\d{4})',
#             re.IGNORECASE
#         )
#         matches = list(date_pattern.finditer(content))
#         for i, match in enumerate(matches):
#             start_date = parse_month_year_to_date(match.group('m1'), match.group('y1'))
#             end_val = match.group('end').lower()
#             end_date = "present" if 'настоящее' in end_val else parse_month_year_to_date(end_val.split()[0], end_val.split()[1])

#             text_start = match.end()
#             text_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
#             chunk = content[text_start:text_end].strip()

#             lines = [ln.strip() for ln in chunk.split('\n') if ln.strip()]
#             filtered_lines = []
#             for ln in lines:
#                 if re.match(r'^(?:\(?\d+\s*(?:год|года|лет|месяц|месяца|месяцев)\)?\s*)+$', ln, re.IGNORECASE):
#                     continue
#                 if 'резюме обновлено' in ln.lower():
#                     continue
#                 filtered_lines.append(ln)

#             comp = filtered_lines[0] if len(filtered_lines) > 0 else "Компания"
            
#             pos = "Специалист"
#             desc_start_idx = 1
#             for idx in range(1, len(filtered_lines)):
#                 candidate_line = filtered_lines[idx]
#                 lower_c = candidate_line.lower()

#                 if any(ext in lower_c for ext in ['.ru', '.com', '.by', '.org', 'http']):
#                     continue
#                 if re.match(r'^(?:минск|москва|санкт-петербург|россия|беларусь)[\s,.]*$', lower_c):
#                     continue
#                 if any(w in lower_c for w in ['автомобильный бизнес', 'дилерский центр', 'торговл', 'продвижен', 'производств', 'оптов', 'розничн']):
#                     continue
#                 if candidate_line.startswith(('-', '•', '*', '–')):
#                     continue

#                 clean_line = re.sub(r'\(?\d+\s*(?:год|года|лет|месяц|месяца|месяцев)\)?', '', candidate_line).strip()
#                 if clean_line and not clean_line.startswith(('-', '•', '*', '–')):
#                     pos = clean_line
#                     desc_start_idx = idx + 1
#                     break

#             desc = "\n".join(filtered_lines[desc_start_idx:])

#             exp_items.append({
#                 "company": comp,
#                 "position": pos,
#                 "description": desc,
#                 "startDate": start_date,
#                 "endDate": end_date
#             })

#     edu_items = []
#     edu_level = 'higher'
#     edu_block_m = re.search(r'Образование\s*\n+(.*?)(?=\nКлючевые навыки|\nНавыки|\nОпыт вождения|\nДополнительная информация|\Z)', body_text, re.DOTALL)
#     if edu_block_m:
#         e_content = edu_block_m.group(1).strip()
#         m_lvl = re.search(r'(Высшее|Среднее специальное|Среднее|Неоконченное высшее)', e_content, re.IGNORECASE)
#         if m_lvl: edu_level = normalize_edu_level(m_lvl.group(1))

#         item_matches = re.finditer(r'(?P<year>\d{4})\s+(?P<inst>[^\n]+)\n+(?P<detail>[^\n]+)', e_content)
#         for im in item_matches:
#             year_val = im.group('year')
#             inst = im.group('inst').strip()
#             detail = im.group('detail').strip()

#             faculty = None
#             specialty = detail
#             if ',' in detail:
#                 d_parts = detail.split(',', 1)
#                 faculty = d_parts[0].strip()
#                 specialty = d_parts[1].strip()

#             edu_items.append({
#                 "institution": inst,
#                 "year": year_val,
#                 "faculty": faculty,
#                 "specialty": specialty
#             })

#     specializations = []
#     m_specs = re.search(r'Специализации:\s*\n(?P<specs>.*?)(?=\nЗанятость|\nГрафик|\nОпыт работы|\Z)', body_text, re.DOTALL)
#     if m_specs:
#         for sp in m_specs.group('specs').split('\n'):
#             clean_sp = re.sub(r'^[—–\-•*\s]+', '', sp).strip()
#             if clean_sp:
#                 for sub_sp in clean_sp.split(','):
#                     if sub_sp.strip():
#                         specializations.append(sub_sp.strip())

#     skills = []
#     m_sk = re.search(r'Навыки\s+([^\n]+)', body_text)
#     if m_sk:
#         skills.extend([s.strip() for s in re.split(r'[,;•]+', m_sk.group(1)) if s.strip()])

#     languages = []
#     for line in body_text.split('\n'):
#         clean_l = re.sub(r'^Знание языков\s*', '', line.strip()).strip()
#         m_lang = re.match(r'^([А-Яа-яA-Za-z]+)\s*[—–-]\s*(.+)$', clean_l)
#         if m_lang:
#             l_name = m_lang.group(1).strip()
#             l_lvl = m_lang.group(2).strip()
#             if l_name.lower() in ['русский', 'английский', 'немецкий', 'французский', 'польский', 'испанский', 'итальянский']:
#                 languages.append({"language": l_name, "level": l_lvl})
#                 skills.append(f"{l_name} ({l_lvl})")

#     driver_license = None
#     m_drv = re.search(r'Права категори(?:и|й)\s*([A-Za-z,\s]+)', body_text)
#     if m_drv:
#         driver_license = m_drv.group(1).strip()
#         skills.append("Опыт вождения")

#     resume_updated_at = None
#     m_upd = re.search(r'Резюме обновлено\s*(\d{1,2}\s+[а-я]+\s+\d{4})', body_text, re.IGNORECASE)
#     if m_upd:
#         resume_updated_at = m_upd.group(1)

#     return {
#         "fullName": full_name, "firstName": first_name, "lastName": last_name, "middleName": middle_name,
#         "birthDate": birth_date, "age": age, "gender": gender, "city": city, "citizenship": citizenship,
#         "position": position, "headline": headline,
#         "salaryAmount": None, "salaryCurrency": None,
#         "employmentType": employment_type, "relocation": relocation, "businessTrips": business_trips,
#         "totalMonths": total_months, "totalString": total_string, "expItems": exp_items,
#         "eduLevel": edu_level, "eduItems": edu_items, "skills": skills,
#         "languages": languages, "specializations": specializations,
#         "driverLicense": driver_license, "resumeUpdatedAt": resume_updated_at
#     }

# # ==========================================
# # 6. ГЛАВНЫЙ ПРОЦЕСС МИГРАЦИИ
# # ==========================================
# def run_migration():
#     load_metadata()
#     login()
#     load_ats_stages()
#     archive_vac_id = get_archive_vacancy_id()
    
#     applicants_dir = BASE_DIR / "applicants"
#     if not applicants_dir.exists():
#         log_message("❌ Папка applicants не найдена!")
#         return

#     state = load_migration_state()
#     completed_set = set(state.get("completed", []))
#     log_message(f"ℹ️ Ранее успешно перенесено кандидатов: {len(completed_set)}")

#     all_folders = [f for f in applicants_dir.iterdir() if f.is_dir()]
#     if TARGET_FOLDERS:
#         folders = [f for f in all_folders if f.name in TARGET_FOLDERS]
#     else:
#         folders = all_folders

#     total_count = len(folders)
#     log_message(f"\n🚀 Всего кандидатов к обработке в этом запуске: {total_count} шт.\n")

#     success_count = 0
#     skipped_count = 0
#     error_count = 0

#     for idx, folder in enumerate(folders, 1):
#         cand_id = folder.name
        
#         # Пропускаем уже готовых кандидатов
#         if cand_id in completed_set:
#             skipped_count += 1
#             continue

#         log_message(f"{'='*60}\n👉 [{idx}/{total_count}] Обработка кандидата ID: {cand_id}")

#         try:
#             card_file = folder / "card.json"
#             if not card_file.exists():
#                 log_message(f"   ⚠️ card.json не найден для {cand_id}, пропускаем")
#                 continue

#             with open(card_file, "r", encoding="utf-8") as f:
#                 card_data = json.load(f)

#             # 1. Поиск резюме
#             resume_data = {}
#             files_dir = folder / "files"
#             if files_dir.exists():
#                 for rf in files_dir.glob("resume*.json"):
#                     try:
#                         with open(rf, "r", encoding="utf-8") as f:
#                             resume_data = json.load(f)
#                         break
#                     except Exception: pass
#             if not resume_data:
#                 for rf in folder.glob("resume*.json"):
#                     try:
#                         with open(rf, "r", encoding="utf-8") as f:
#                             resume_data = json.load(f)
#                         break
#                     except Exception: pass

#             r_info = resume_data.get("resume") or {}
#             r_data = resume_data.get("data") or {}
#             raw_body = r_data.get("body") if isinstance(r_data, dict) else ""

#             if r_info.get("experience") or (isinstance(r_data, dict) and r_data.get("experience")):
#                 log_message("   📄 Обнаружено структурированное резюме (HH/JSON)")
#                 parsed = parse_structured_resume(resume_data, card_data)
#             elif raw_body:
#                 log_message("   📝 Обнаружен текст резюме (NATIVE)")
#                 parsed = parse_unstructured_body(raw_body, card_data)
#             else:
#                 log_message("   ⚠️ Резюме отсутствует, переносим базовые данные из карточки")
#                 parsed = parse_unstructured_body("", card_data)

#             # 2. Фотография
#             photo_b64 = None
#             if files_dir.exists() and (files_dir / "photo.jpg").exists():
#                 with open(files_dir / "photo.jpg", "rb") as img:
#                     b64_str = base64.b64encode(img.read()).decode("utf-8")
#                     photo_b64 = f"data:image/jpeg;base64,{b64_str}"
#             elif card_data.get("photo_url"):
#                 photo_b64 = card_data["photo_url"]

#             # 3. Теги и специализации
#             hf_tags = []
#             for t in card_data.get("tags") or []:
#                 t_name = tags_map.get(t.get("tag"))
#                 if t_name: hf_tags.append(t_name.strip())

#             specs = parsed.get("specializations", [])
#             combined_tags = list(dict.fromkeys(hf_tags + specs))
#             combined_skills = list(dict.fromkeys(parsed.get("skills", []) + combined_tags))

#             # Исходный статус кандидата из Huntflow
#             detected_status_name = None
#             if card_data.get("links"):
#                 detected_status_name = statuses_map.get(card_data["links"][0].get("status"))

#             target_stage_id = map_huntflow_status_to_ats_stage_id(detected_status_name)
#             log_message(f"   🎯 Исходный статус: «{detected_status_name}» ➔ Стадия ID: {target_stage_id}")

#             # 4. Сборка PAYLOAD
#             payload = {
#                 "personal": {
#                     "fullName": parsed.get("fullName"),
#                     "firstName": parsed.get("firstName"),
#                     "lastName": parsed.get("lastName"),
#                     "middleName": parsed.get("middleName"),
#                     "gender": parsed.get("gender"),
#                     "age": parsed.get("age"),
#                     "birthDate": parsed.get("birthDate"),
#                     "city": parsed.get("city"),
#                     "citizenship": parsed.get("citizenship"),
#                     "photoUrl": photo_b64
#                 },
#                 "preferences": {
#                     "position": parsed.get("position"),
#                     "headline": parsed.get("headline"),
#                     "salary": {
#                         "amount": parsed.get("salaryAmount"),
#                         "currency": parsed.get("salaryCurrency") or "RUB"
#                     } if parsed.get("salaryAmount") else None,
#                     "employmentType": parsed.get("employmentType"),
#                     "relocation": parsed.get("relocation"),
#                     "businessTrips": parsed.get("businessTrips")
#                 },
#                 "experience": {
#                     "totalMonths": parsed.get("totalMonths"),
#                     "totalString": parsed.get("totalString"),
#                     "items": parsed.get("expItems", [])
#                 },
#                 "skills": combined_skills,
#                 "education": {
#                     "level": parsed.get("eduLevel", "higher"),
#                     "items": parsed.get("eduItems", [])
#                 },
#                 "contacts": {
#                     "phones": [card_data["phone"]] if card_data.get("phone") else [],
#                     "emails": [card_data["email"]] if card_data.get("email") else [],
#                     "telegram": card_data.get("skype") or None,
#                     "links": [f"http://huntflow.local/applicants/{cand_id}"]
#                 },
#                 "additional": {
#                     "languages": parsed.get("languages", []),
#                     "driverLicense": parsed.get("driverLicense"),
#                     "category": parsed.get("category"),
#                     "resumeUpdatedAt": parsed.get("resumeUpdatedAt")
#                 },
#                 "source": {
#                     "platform": "Huntflow",
#                     "domain": "huntflow.local",
#                     "baseUrl": "http://huntflow.local",
#                     "profileUrl": f"http://huntflow.local/applicants/{cand_id}",
#                     "parsedAt": card_data.get("created") or datetime.now().isoformat(),
#                     "detectedStatus": detected_status_name,
#                     "detectedTags": ["Huntflow Архив"] + combined_tags
#                 }
#             }

#             # 5. Сохранение профиля кандидата
#             log_message(f"   📥 Сохранение досье: {parsed.get('lastName')} {parsed.get('firstName')}...")
#             res = api_request("POST", "/candidates/from-parser", json=payload)
#             if res.status_code not in [200, 201, 202]:
#                 raise Exception(f"Ошибка сохранения кандидата HTTP {res.status_code}: {res.text}")

#             res_data = res.json()
#             cand_uuid = (res_data.get("candidate") or {}).get("id") or res_data.get("id")
#             log_message(f"   ✅ Кандидат сохранён в БД! (UUID: {cand_uuid})")

#             # 6. Загрузка вложений (.pdf, .docx)
#             if files_dir.exists():
#                 for file_path in files_dir.iterdir():
#                     if file_path.suffix.lower() in [".pdf", ".doc", ".docx", ".rtf", ".txt"] and not file_path.name.startswith("resume"):
#                         try:
#                             with open(file_path, "rb") as f:
#                                 files = {"file": (file_path.name, f, "application/octet-stream")}
#                                 f_res = api_request(
#                                     "POST",
#                                     "/files",
#                                     params={"entityType": "candidate", "entityId": cand_uuid},
#                                     files=files
#                                 )
#                                 if f_res.status_code == 201:
#                                     log_message(f"      📎 Файл {file_path.name} сохранён!")
#                         except Exception as fe:
#                             log_message(f"      ⚠️ Ошибка файла {file_path.name}: {fe}")

#             # 7. ДОБАВЛЕНИЕ В ВОРОНКУ СРАЗУ НА НУЖНУЮ СТАДИЮ
#             cv_payload = {
#                 "vacancyId": archive_vac_id,
#                 "stageId": target_stage_id
#             }
            
#             cv_id = None
#             cv_res = api_request("POST", f"/candidates/{cand_uuid}/vacancies", json=cv_payload)
#             if cv_res.status_code == 201:
#                 cv_id = cv_res.json()["id"]
#                 log_message(f"   📌 Кандидат добавлен на этап воронки ID: {target_stage_id}")
#             elif cv_res.status_code == 400:
#                 pipe_res = api_request("GET", f"/candidates/{cand_uuid}/pipeline")
#                 if pipe_res.status_code == 200:
#                     for cv_item in pipe_res.json():
#                         if cv_item.get("vacancyId") == archive_vac_id:
#                             cv_id = cv_item["id"]
#                             api_request("PUT", f"/candidate-vacancies/{cv_id}/move", json={"newStageId": target_stage_id})
#                             log_message(f"   🔄 Кандидат переведён на этап воронки ID: {target_stage_id}")
#                             break

#             # 8. ПЕРЕНОС ВСЕЙ ИСТОРИИ И ЧАТА (ВКЛЮЧАЯ ПРИЧИНЫ ОТКАЗА И АВТОРОВ)
#             if cv_id:
#                 history_file = folder / "history_and_chat.json"
#                 if history_file.exists():
#                     with open(history_file, "r", encoding="utf-8") as hf:
#                         history_list = json.load(hf)
#                         # Сортируем от самых старых к самым новым
#                         history_list.sort(key=lambda x: x.get("created", ""))

#                         for h_item in history_list:
#                             dt_raw = h_item.get("created") or ""
#                             dt_str = dt_raw.replace("T", " ")[:16] if dt_raw else ""
#                             author = (h_item.get("account_info") or {}).get("name") or ""
                            
#                             comment_text = h_item.get("comment")
#                             status_id = h_item.get("status")
#                             status_name = statuses_map.get(status_id)
#                             type_str = h_item.get("type")

#                             if not status_name:
#                                 if type_str == 'VACANCY-ADD': status_name = 'Взят в работу на вакансию'
#                                 elif type_str == 'ADD': status_name = 'Добавлен в базу'
#                                 elif type_str == 'COMMENT': status_name = 'Комментарий'
#                                 else: status_name = type_str or 'Действие'

#                             orig_vac_name = vacancies_map.get(h_item.get("vacancy"), "Без вакансии")
#                             rej_id = h_item.get("rejection_reason")
#                             rej_text = reasons_map.get(rej_id)

#                             # Собираем подробное и красивое сообщение
#                             msg_parts = []
#                             header_line = f"💼 Вакансия: {orig_vac_name}"
#                             if dt_str: header_line += f" • 🕒 {dt_str}"
#                             msg_parts.append(header_line)

#                             if author:
#                                 msg_parts.append(f"👤 Автор: {author}")
#                             msg_parts.append(f"📌 Этап: {status_name}")

#                             if rej_text:
#                                 msg_parts.append(f"🚫 Причина отказа: {rej_text}")
#                             if comment_text:
#                                 msg_parts.append(f"💬 {comment_text}")

#                             full_msg = "\n".join(msg_parts)

#                             c_res = api_request("POST", "/comments", json={
#                                 "candidateVacancyId": cv_id,
#                                 "text": full_msg
#                             })
#                             if c_res.status_code not in [200, 201]:
#                                 log_message(f"      ⚠️ Ошибка комментария: {c_res.text}")

#                     log_message(f"   💬 История ({len(history_list)} событий) успешно перенесена!")

#             # УСПЕШНО ЗАВЕРШЕН КАНДИДАТ
#             state["completed"].append(cand_id)
#             if cand_id in state.get("failed", {}):
#                 del state["failed"][cand_id]
#             save_migration_state(state)
#             success_count += 1

#             # Пауза между запросами для стабильности
#             if DELAY_BETWEEN_CANDIDATES > 0:
#                 time.sleep(DELAY_BETWEEN_CANDIDATES)

#         except Exception as e:
#             error_count += 1
#             err_msg = str(e)
#             log_message(f"   ❌ Ошибка при переносе кандидата {cand_id}: {err_msg}")
#             state["failed"][cand_id] = err_msg
#             save_migration_state(state)
#             continue

#     log_message("\n" + "="*60)
#     log_message("🎉 МИГРАЦИЯ ЗАВЕРШЕНА!")
#     log_message(f"   • Успешно перенесено за этот запуск: {success_count}")
#     log_message(f"   • Пропущено (были перенесены ранее): {skipped_count}")
#     log_message(f"   • Ошибок: {error_count}")
#     log_message(f"   • Всего перенесено кандидатов: {len(state.get('completed', []))}")
#     log_message(f"   • Подробный лог сохранён в: {LOG_FILE.resolve()}")
#     log_message("="*60)

# if __name__ == "__main__":
#     run_migration()

import os
import json
import base64
import re
import time
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

# Оставляем пустым: скрипт сам увидит в migration_state.json 3174 готовых
# и возьмет в работу только 9 оставшихся!
TARGET_FOLDERS = []

DELAY_BETWEEN_CANDIDATES = 3

STATE_FILE = Path("migration_state.json")
LOG_FILE = Path("migration_log.txt")

vacancies_map = {}
statuses_map = {}
tags_map = {}
reasons_map = {}
ats_stages_by_name = {}

current_token = None
token_issued_at = 0

RU_MONTHS = {
    'январь': 1, 'января': 1, 'февраль': 2, 'февраля': 2,
    'март': 3, 'марта': 3, 'апрель': 4, 'апреля': 4,
    'май': 5, 'мая': 5, 'июнь': 6, 'июня': 6,
    'июль': 7, 'июля': 7, 'август': 8, 'августа': 8,
    'сентябрь': 9, 'сентября': 9, 'октябрь': 10, 'октября': 10,
    'ноябрь': 11, 'ноября': 11, 'декабрь': 12, 'декабря': 12
}

def safe_str(val, max_len=None):
    """Обрезает строку до max_len, чтобы не падать по валидации бэкенда"""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if max_len and len(s) > max_len:
        return s[:max_len].strip()
    return s

# ==========================================
# 2. УПРАВЛЕНИЕ ЛОГАМИ И СОСТОЯНИЕМ
# ==========================================
def log_message(msg: str):
    print(msg)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_msg = re.sub(r'[^\w\s\d.,:;!@#$%^&*()_+=\-\[\]{}|\\/<>?~`"\'а-яА-ЯёЁ]', '', msg)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {clean_msg}\n")
    except Exception:
        pass

def load_migration_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed": [], "failed": {}}

def save_migration_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения прогресса: {e}")

# ==========================================
# 3. АВТОРИЗАЦИЯ И СЕТЕВЫЕ ЗАПРОСЫ
# ==========================================
def login():
    global current_token, token_issued_at
    log_message(f"🔐 Получение JWT токена для {EMAIL}...")
    res = requests.post(f"{API_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if res.status_code not in [200, 201]:
        log_message(f"❌ Ошибка входа: {res.text}")
        exit(1)
    current_token = res.json().get("accessToken")
    token_issued_at = time.time()
    log_message("✅ Токен успешно получен и обновлен!")
    return current_token

def get_auth_token(force_refresh=False):
    global current_token, token_issued_at
    if force_refresh or not current_token or (time.time() - token_issued_at > 480):
        login()
    return current_token

def api_request(method, endpoint, **kwargs):
    token = get_auth_token()
    headers = kwargs.get("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    kwargs["headers"] = headers

    url = f"{API_URL}{endpoint}" if endpoint.startswith("/") else f"{API_URL}/{endpoint}"
    res = requests.request(method, url, **kwargs)

    if res.status_code == 401:
        log_message("⚠️ Токен истек (401). Автоматический перелогин...")
        token = get_auth_token(force_refresh=True)
        headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = headers
        res = requests.request(method, url, **kwargs)

    return res

# ==========================================
# 4. СПРАВОЧНИКИ
# ==========================================
def load_metadata():
    log_message("📂 Загрузка справочников Huntflow...")
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

    if (meta_dir / "rejection_reasons.json").exists():
        with open(meta_dir / "rejection_reasons.json", "r", encoding="utf-8") as f:
            for r in json.load(f).get("items", []):
                reasons_map[r["id"]] = r.get("name")

def load_ats_stages():
    log_message("📋 Получение стадий воронки компании из ATS...")
    res = api_request("GET", "/stages")
    if res.status_code == 200:
        for stage in res.json():
            ats_stages_by_name[stage["name"]] = stage["id"]
        log_message(f"✅ Найдено стадий в ATS: {len(ats_stages_by_name)}")
    else:
        log_message(f"⚠️ Ошибка получения стадий: {res.text}")

def get_archive_vacancy_id():
    title = "Архив истории Huntflow"
    res = api_request("GET", f"/vacancies?search={title}&status=closed")
    data = res.json().get("data", [])
    if data:
        return data[0]["id"]
    
    res = api_request("POST", "/vacancies", json={"title": title, "status": "closed"})
    return res.json()["id"]

def map_huntflow_status_to_ats_stage_id(hf_status_name):
    if not hf_status_name:
        return ats_stages_by_name.get("Новый кандидат")

    lower = hf_status_name.lower().strip()

    if 'трудоустроен' in lower or 'исп. срок' in lower or 'нанят' in lower:
        target = "Трудоустроен"
    elif 'отказ' in lower:
        target = "Отказ кандидата"
    elif 'оффер' in lower:
        target = "Выставление оффера"
    elif 'принятие решения' in lower or 'согласование' in lower:
        target = "Принятие решения"
    elif 'hr' in lower or 'хр' in lower or 'интервью с hr' in lower:
        target = "Интервью с HR"
    elif 'руководител' in lower or 'заказчик' in lower:
        target = "Интервью с руководителем"
    elif 'техническ' in lower:
        target = "Техническое интервью"
    elif 'тестов' in lower:
        target = "Тестовое задание"
    elif 'телефон' in lower:
        target = "Телефонное интервью"
    elif 'письмо' in lower or 'смс' in lower or 'приглашение' in lower:
        target = "Отправлено письмо"
    elif 'база' in lower or 'резерв' in lower:
        target = "База"
    else:
        target = "Новый кандидат"

    return ats_stages_by_name.get(target) or ats_stages_by_name.get("Новый кандидат")

def calculate_age(birth_date_str):
    if not birth_date_str: return None
    try:
        b_date = datetime.strptime(str(birth_date_str)[:10], "%Y-%m-%d")
        today = datetime.now()
        return today.year - b_date.year - ((today.month, today.day) < (b_date.month, b_date.day))
    except Exception:
        return None

def pluralize(n, one, two, five):
    n = abs(int(n)) % 100
    n1 = n % 10
    if 10 < n < 20: return five
    if 1 < n1 < 5: return two
    if n1 == 1: return one
    return five

def format_experience_string(total_months):
    if not total_months: return ""
    y = total_months // 12
    m = total_months % 12
    parts = []
    if y > 0: parts.append(f"{y} {pluralize(y, 'год', 'года', 'лет')}")
    if m > 0: parts.append(f"{m} {pluralize(m, 'месяц', 'месяца', 'месяцев')}")
    return " ".join(parts)

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
# 5. ПАРСЕРЫ РЕЗЮМЕ
# ==========================================
def parse_structured_resume(resume_data, card_data):
    r_data = resume_data.get("data") or {}
    r_base = resume_data.get("resume") or {}

    first_name = card_data.get("first_name") or r_data.get("first_name") or r_base.get("personal_info", {}).get("first_name") or ""
    last_name = card_data.get("last_name") or r_data.get("last_name") or r_base.get("personal_info", {}).get("last_name") or ""
    middle_name = card_data.get("middle_name") or r_data.get("middle_name") or r_base.get("personal_info", {}).get("middle_name") or ""
    full_name = f"{last_name} {first_name} {middle_name}".strip()

    birth_date = card_data.get("birthday") or r_data.get("birth_date")
    age = calculate_age(birth_date)

    gender_raw = (r_data.get("gender") or {}).get("id") or (r_base.get("gender") or {}).get("external_id")
    gender = 'male' if gender_raw in ['male', 'Мужской'] else ('female' if gender_raw in ['female', 'Женский'] else None)

    city = (r_data.get("area") or {}).get("name") or ((r_base.get("area") or {}).get("city") or {}).get("name")
    citizenship = ((r_data.get("citizenship") or [{}])[0]).get("name") or ((r_base.get("citizenship") or [{}])[0]).get("name") or "Россия"

    desired_pos = r_data.get("title") or r_base.get("position") or card_data.get("position") or ""

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

    exp_items = []
    raw_exp = r_data.get("experience") or r_base.get("experience") or []
    for exp in raw_exp:
        comp = safe_str(exp.get("company"), 255) or "Компания"
        pos = safe_str(exp.get("position"), 255) or "Должность"
        desc = exp.get("description") or ""

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
    total_string = format_experience_string(total_months)

    edu_info = r_data.get("education") or r_base.get("education") or {}
    edu_level = normalize_edu_level((edu_info.get("level") or {}).get("name"))
    edu_items = []
    for ed in (edu_info.get("higher") or []) + (edu_info.get("primary") or []):
        year_val = ed.get("year") or (ed.get("date_to") or {}).get("year") or ""
        edu_items.append({
            "institution": safe_str(ed.get("name"), 255) or "Учебное заведение",
            "year": str(year_val) if year_val else None,
            "faculty": safe_str(ed.get("faculty") or ed.get("organization"), 255),
            "specialty": safe_str(ed.get("specialty") or ed.get("result") or ed.get("description"), 255) or "Специалист"
        })

    skills = r_data.get("skill_set") or r_base.get("skill_set") or []
    languages = []
    for l in (r_data.get("language") or r_base.get("language") or []):
        lvl_name = (l.get("level") or {}).get("name") if isinstance(l.get("level"), dict) else l.get("level")
        languages.append({"language": l.get("name", ""), "level": lvl_name or "родной"})

    specs = " • ".join([s.get("name", "") for s in r_data.get("specialization") or []])

    return {
        "fullName": full_name, "firstName": first_name, "lastName": last_name, "middleName": middle_name,
        "birthDate": birth_date, "age": age, "gender": gender, "city": city, "citizenship": citizenship,
        "position": desired_pos, "headline": desired_pos,
        "salaryAmount": sal_amount, "salaryCurrency": sal_currency,
        "employmentType": (r_data.get("employment") or {}).get("name") or "Полная занятость",
        "relocation": (r_data.get("relocation") or {}).get("type", {}).get("name") or "не готов к переезду",
        "businessTrips": (r_data.get("business_trip_readiness") or {}).get("name") or "Не готов к командировкам",
        "totalMonths": total_months, "totalString": total_string, "expItems": exp_items,
        "eduLevel": edu_level, "eduItems": edu_items, "skills": skills,
        "languages": languages, "category": specs, "resumeUpdatedAt": (r_data.get("updated_at") or "")[:10]
    }

def parse_unstructured_body(body_text, card_data):
    first_name = card_data.get("first_name") or ""
    last_name = card_data.get("last_name") or ""
    middle_name = card_data.get("middle_name") or ""
    full_name = f"{last_name} {first_name} {middle_name}".strip()

    birth_date = card_data.get("birthday")
    age = calculate_age(birth_date)
    gender = 'male' if 'Мужчина' in body_text else ('female' if 'Женщина' in body_text else None)

    m_city = re.search(r'Проживает:\s*([^\n,]+)', body_text)
    city = m_city.group(1).strip() if m_city else "Минск"

    m_cit = re.search(r'Гражданство:\s*([^\n,]+)', body_text)
    citizenship = m_cit.group(1).strip() if m_cit else "Беларусь"

    position = card_data.get("position") or ""
    m_pos = re.search(r'Желаемая должность и зарплата\s*\n+([^\n]+)', body_text)
    if m_pos:
        position = m_pos.group(1).strip()
    headline = position

    m_rel = re.search(r'(Готов к переезду[^\n,]*|Не готов к переезду[^\n,]*)', body_text, re.IGNORECASE)
    relocation = m_rel.group(1).strip() if m_rel else "Готов к переезду"

    m_trip = re.search(r'(готов к [^\n,]*командировкам|не готов к командировкам)', body_text, re.IGNORECASE)
    business_trips = m_trip.group(1).strip() if m_trip else "готов к редким командировкам"

    m_emp = re.search(r'Занятость:\s*([^\n]+)', body_text)
    employment_type = m_emp.group(1).strip() if m_emp else "полная занятость"

    m_tot_exp = re.search(r'Опыт работы\s*[—–-]\s*([^\n]+)', body_text)
    total_string = m_tot_exp.group(1).strip() if m_tot_exp else ""
    total_months = parse_exp_string_to_months(total_string)

    exp_items = []
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
            end_date = "present" if 'настоящее' in end_val else parse_month_year_to_date(end_val.split()[0], end_val.split()[1])

            text_start = match.end()
            text_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            chunk = content[text_start:text_end].strip()

            lines = [ln.strip() for ln in chunk.split('\n') if ln.strip()]
            filtered_lines = []
            for ln in lines:
                if re.match(r'^(?:\(?\d+\s*(?:год|года|лет|месяц|месяца|месяцев)\)?\s*)+$', ln, re.IGNORECASE):
                    continue
                if 'резюме обновлено' in ln.lower():
                    continue
                filtered_lines.append(ln)

            comp = safe_str(filtered_lines[0] if len(filtered_lines) > 0 else "Компания", 255)
            
            pos = "Специалист"
            desc_start_idx = 1
            for idx in range(1, len(filtered_lines)):
                candidate_line = filtered_lines[idx]
                lower_c = candidate_line.lower()

                if any(ext in lower_c for ext in ['.ru', '.com', '.by', '.org', 'http']):
                    continue
                if re.match(r'^(?:минск|москва|санкт-петербург|россия|беларусь)[\s,.]*$', lower_c):
                    continue
                if any(w in lower_c for w in ['автомобильный бизнес', 'дилерский центр', 'торговл', 'продвижен', 'производств', 'оптов', 'розничн']):
                    continue
                if candidate_line.startswith(('-', '•', '*', '–')):
                    continue

                clean_line = re.sub(r'\(?\d+\s*(?:год|года|лет|месяц|месяца|месяцев)\)?', '', candidate_line).strip()
                if clean_line and not clean_line.startswith(('-', '•', '*', '–')):
                    pos = safe_str(clean_line, 255)
                    desc_start_idx = idx + 1
                    break

            desc = "\n".join(filtered_lines[desc_start_idx:])

            exp_items.append({
                "company": comp,
                "position": pos,
                "description": desc,
                "startDate": start_date,
                "endDate": end_date
            })

    edu_items = []
    edu_level = 'higher'
    edu_block_m = re.search(r'Образование\s*\n+(.*?)(?=\nКлючевые навыки|\nНавыки|\nОпыт вождения|\nДополнительная информация|\Z)', body_text, re.DOTALL)
    if edu_block_m:
        e_content = edu_block_m.group(1).strip()
        m_lvl = re.search(r'(Высшее|Среднее специальное|Среднее|Неоконченное высшее)', e_content, re.IGNORECASE)
        if m_lvl: edu_level = normalize_edu_level(m_lvl.group(1))

        item_matches = re.finditer(r'(?P<year>\d{4})\s+(?P<inst>[^\n]+)\n+(?P<detail>[^\n]+)', e_content)
        for im in item_matches:
            year_val = im.group('year')
            inst = safe_str(im.group('inst').strip(), 255)
            detail = im.group('detail').strip()

            faculty = None
            specialty = detail
            if ',' in detail:
                d_parts = detail.split(',', 1)
                faculty = safe_str(d_parts[0].strip(), 255)
                specialty = safe_str(d_parts[1].strip(), 255)
            else:
                specialty = safe_str(detail, 255)

            edu_items.append({
                "institution": inst,
                "year": year_val,
                "faculty": faculty,
                "specialty": specialty
            })

    specializations = []
    m_specs = re.search(r'Специализации:\s*\n(?P<specs>.*?)(?=\nЗанятость|\nГрафик|\nОпыт работы|\Z)', body_text, re.DOTALL)
    if m_specs:
        for sp in m_specs.group('specs').split('\n'):
            clean_sp = re.sub(r'^[—–\-•*\s]+', '', sp).strip()
            if clean_sp:
                for sub_sp in clean_sp.split(','):
                    if sub_sp.strip():
                        specializations.append(sub_sp.strip())

    skills = []
    m_sk = re.search(r'Навыки\s+([^\n]+)', body_text)
    if m_sk:
        skills.extend([s.strip() for s in re.split(r'[,;•]+', m_sk.group(1)) if s.strip()])

    languages = []
    for line in body_text.split('\n'):
        clean_l = re.sub(r'^Знание языков\s*', '', line.strip()).strip()
        m_lang = re.match(r'^([А-Яа-яA-Za-z]+)\s*[—–-]\s*(.+)$', clean_l)
        if m_lang:
            l_name = m_lang.group(1).strip()
            l_lvl = m_lang.group(2).strip()
            if l_name.lower() in ['русский', 'английский', 'немецкий', 'французский', 'польский', 'испанский', 'итальянский']:
                languages.append({"language": l_name, "level": l_lvl})
                skills.append(f"{l_name} ({l_lvl})")

    driver_license = None
    m_drv = re.search(r'Права категори(?:и|й)\s*([A-Za-z,\s]+)', body_text)
    if m_drv:
        driver_license = m_drv.group(1).strip()
        skills.append("Опыт вождения")

    resume_updated_at = None
    m_upd = re.search(r'Резюме обновлено\s*(\d{1,2}\s+[а-я]+\s+\d{4})', body_text, re.IGNORECASE)
    if m_upd:
        resume_updated_at = m_upd.group(1)

    return {
        "fullName": full_name, "firstName": first_name, "lastName": last_name, "middleName": middle_name,
        "birthDate": birth_date, "age": age, "gender": gender, "city": city, "citizenship": citizenship,
        "position": position, "headline": headline,
        "salaryAmount": None, "salaryCurrency": None,
        "employmentType": employment_type, "relocation": relocation, "businessTrips": business_trips,
        "totalMonths": total_months, "totalString": total_string, "expItems": exp_items,
        "eduLevel": edu_level, "eduItems": edu_items, "skills": skills,
        "languages": languages, "specializations": specializations,
        "driverLicense": driver_license, "resumeUpdatedAt": resume_updated_at
    }

# ==========================================
# 6. ГЛАВНЫЙ ПРОЦЕСС МИГРАЦИИ
# ==========================================
def run_migration():
    load_metadata()
    login()
    load_ats_stages()
    archive_vac_id = get_archive_vacancy_id()
    
    applicants_dir = BASE_DIR / "applicants"
    if not applicants_dir.exists():
        log_message("❌ Папка applicants не найдена!")
        return

    state = load_migration_state()
    completed_set = set(state.get("completed", []))
    log_message(f"ℹ️ Ранее успешно перенесено кандидатов: {len(completed_set)}")

    all_folders = [f for f in applicants_dir.iterdir() if f.is_dir()]
    if TARGET_FOLDERS:
        folders = [f for f in all_folders if f.name in TARGET_FOLDERS]
    else:
        folders = all_folders

    total_count = len(folders)
    log_message(f"\n🚀 Всего кандидатов в очереди: {total_count} шт.\n")

    success_count = 0
    skipped_count = 0
    error_count = 0

    for idx, folder in enumerate(folders, 1):
        cand_id = folder.name
        
        if cand_id in completed_set:
            skipped_count += 1
            continue

        log_message(f"{'='*60}\n👉 [{idx}/{total_count}] Обработка кандидата ID: {cand_id}")

        try:
            card_file = folder / "card.json"
            if not card_file.exists():
                log_message(f"   ⚠️ card.json не найден для {cand_id}, пропускаем")
                continue

            with open(card_file, "r", encoding="utf-8") as f:
                card_data = json.load(f)

            # 1. Поиск резюме
            resume_data = {}
            files_dir = folder / "files"
            if files_dir.exists():
                for rf in files_dir.glob("resume*.json"):
                    try:
                        with open(rf, "r", encoding="utf-8") as f:
                            resume_data = json.load(f)
                        break
                    except Exception: pass
            if not resume_data:
                for rf in folder.glob("resume*.json"):
                    try:
                        with open(rf, "r", encoding="utf-8") as f:
                            resume_data = json.load(f)
                        break
                    except Exception: pass

            r_info = resume_data.get("resume") or {}
            r_data = resume_data.get("data") or {}
            raw_body = r_data.get("body") if isinstance(r_data, dict) else ""

            if r_info.get("experience") or (isinstance(r_data, dict) and r_data.get("experience")):
                log_message("   📄 Обнаружено структурированное резюме (HH/JSON)")
                parsed = parse_structured_resume(resume_data, card_data)
            elif raw_body:
                log_message("   📝 Обнаружен текст резюме (NATIVE)")
                parsed = parse_unstructured_body(raw_body, card_data)
            else:
                log_message("   ⚠️ Резюме отсутствует, переносим базовые данные из карточки")
                parsed = parse_unstructured_body("", card_data)

            # 2. Фотография
            photo_b64 = None
            if files_dir.exists() and (files_dir / "photo.jpg").exists():
                with open(files_dir / "photo.jpg", "rb") as img:
                    b64_str = base64.b64encode(img.read()).decode("utf-8")
                    photo_b64 = f"data:image/jpeg;base64,{b64_str}"
            elif card_data.get("photo_url"):
                photo_b64 = card_data["photo_url"]

            # 3. Теги и специализации
            hf_tags = []
            for t in card_data.get("tags") or []:
                t_name = tags_map.get(t.get("tag"))
                if t_name: hf_tags.append(t_name.strip())

            specs = parsed.get("specializations", [])
            combined_tags = list(dict.fromkeys(hf_tags + specs))
            combined_skills = list(dict.fromkeys(parsed.get("skills", []) + combined_tags))

            detected_status_name = None
            if card_data.get("links"):
                detected_status_name = statuses_map.get(card_data["links"][0].get("status"))

            target_stage_id = map_huntflow_status_to_ats_stage_id(detected_status_name)
            log_message(f"   🎯 Исходный статус: «{detected_status_name}» ➔ Стадия ID: {target_stage_id}")

            # 4. Сборка PAYLOAD с безопасным усечением длины строк
            payload = {
                "personal": {
                    "fullName": safe_str(parsed.get("fullName"), 255),
                    "firstName": safe_str(parsed.get("firstName"), 100),
                    "lastName": safe_str(parsed.get("lastName"), 100),
                    "middleName": safe_str(parsed.get("middleName"), 100),
                    "gender": parsed.get("gender"),
                    "age": parsed.get("age"),
                    "birthDate": parsed.get("birthDate"),
                    "city": safe_str(parsed.get("city"), 150),
                    "citizenship": safe_str(parsed.get("citizenship"), 100),
                    "photoUrl": photo_b64
                },
                "preferences": {
                    "position": safe_str(parsed.get("position"), 255),
                    "headline": safe_str(parsed.get("headline"), 255),
                    "salary": {
                        "amount": parsed.get("salaryAmount"),
                        "currency": parsed.get("salaryCurrency") or "RUB"
                    } if parsed.get("salaryAmount") else None,
                    "employmentType": safe_str(parsed.get("employmentType"), 50),
                    "relocation": safe_str(parsed.get("relocation"), 100),
                    "businessTrips": safe_str(parsed.get("businessTrips"), 100)
                },
                "experience": {
                    "totalMonths": parsed.get("totalMonths"),
                    "totalString": safe_str(parsed.get("totalString"), 100),
                    "items": parsed.get("expItems", [])
                },
                "skills": combined_skills,
                "education": {
                    "level": safe_str(parsed.get("eduLevel", "higher"), 50),
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
                    "detectedStatus": detected_status_name,
                    "detectedTags": ["Huntflow Архив"] + combined_tags
                }
            }

            # 5. Сохранение профиля кандидата
            log_message(f"   📥 Сохранение досье: {parsed.get('lastName')} {parsed.get('firstName')}...")
            res = api_request("POST", "/candidates/from-parser", json=payload)
            if res.status_code not in [200, 201, 202]:
                raise Exception(f"Ошибка сохранения кандидата HTTP {res.status_code}: {res.text}")

            res_data = res.json()
            cand_uuid = (res_data.get("candidate") or {}).get("id") or res_data.get("id")
            log_message(f"   ✅ Кандидат сохранён в БД! (UUID: {cand_uuid})")

            # 6. Загрузка вложений (.pdf, .docx)
            if files_dir.exists():
                for file_path in files_dir.iterdir():
                    if file_path.suffix.lower() in [".pdf", ".doc", ".docx", ".rtf", ".txt"] and not file_path.name.startswith("resume"):
                        try:
                            with open(file_path, "rb") as f:
                                files = {"file": (file_path.name, f, "application/octet-stream")}
                                f_res = api_request(
                                    "POST",
                                    "/files",
                                    params={"entityType": "candidate", "entityId": cand_uuid},
                                    files=files
                                )
                                if f_res.status_code == 201:
                                    log_message(f"      📎 Файл {file_path.name} сохранён!")
                        except Exception as fe:
                            log_message(f"      ⚠️ Ошибка файла {file_path.name}: {fe}")

            # 7. ДОБАВЛЕНИЕ В ВОРОНКУ СРАЗУ НА НУЖНУЮ СТАДИЮ
            cv_payload = {
                "vacancyId": archive_vac_id,
                "stageId": target_stage_id
            }
            
            cv_id = None
            cv_res = api_request("POST", f"/candidates/{cand_uuid}/vacancies", json=cv_payload)
            if cv_res.status_code == 201:
                cv_id = cv_res.json()["id"]
                log_message(f"   📌 Кандидат добавлен на этап воронки ID: {target_stage_id}")
            elif cv_res.status_code == 400:
                pipe_res = api_request("GET", f"/candidates/{cand_uuid}/pipeline")
                if pipe_res.status_code == 200:
                    for cv_item in pipe_res.json():
                        if cv_item.get("vacancyId") == archive_vac_id:
                            cv_id = cv_item["id"]
                            api_request("PUT", f"/candidate-vacancies/{cv_id}/move", json={"newStageId": target_stage_id})
                            log_message(f"   🔄 Кандидат переведён на этап воронки ID: {target_stage_id}")
                            break

            # 8. ПЕРЕНОС ВСЕЙ ИСТОРИИ И ЧАТА
            if cv_id:
                history_file = folder / "history_and_chat.json"
                if history_file.exists():
                    with open(history_file, "r", encoding="utf-8") as hf:
                        history_list = json.load(hf)
                        history_list.sort(key=lambda x: x.get("created", ""))

                        for h_item in history_list:
                            dt_raw = h_item.get("created") or ""
                            dt_str = dt_raw.replace("T", " ")[:16] if dt_raw else ""
                            author = (h_item.get("account_info") or {}).get("name") or ""
                            
                            comment_text = h_item.get("comment")
                            status_id = h_item.get("status")
                            status_name = statuses_map.get(status_id)
                            type_str = h_item.get("type")

                            if not status_name:
                                if type_str == 'VACANCY-ADD': status_name = 'Взят в работу на вакансию'
                                elif type_str == 'ADD': status_name = 'Добавлен в базу'
                                elif type_str == 'COMMENT': status_name = 'Комментарий'
                                else: status_name = type_str or 'Действие'

                            orig_vac_name = vacancies_map.get(h_item.get("vacancy"), "Без вакансии")
                            rej_id = h_item.get("rejection_reason")
                            rej_text = reasons_map.get(rej_id)

                            msg_parts = []
                            header_line = f"💼 Вакансия: {orig_vac_name}"
                            if dt_str: header_line += f" • 🕒 {dt_str}"
                            msg_parts.append(header_line)

                            if author:
                                msg_parts.append(f"👤 Автор: {author}")
                            msg_parts.append(f"📌 Этап: {status_name}")

                            if rej_text:
                                msg_parts.append(f"🚫 Причина отказа: {rej_text}")
                            if comment_text:
                                msg_parts.append(f"💬 {comment_text}")

                            full_msg = "\n".join(msg_parts)

                            c_res = api_request("POST", "/comments", json={
                                "candidateVacancyId": cv_id,
                                "text": full_msg
                            })
                            if c_res.status_code not in [200, 201]:
                                log_message(f"      ⚠️ Ошибка комментария: {c_res.text}")

                    log_message(f"   💬 История ({len(history_list)} событий) успешно перенесена!")

            # УСПЕШНО ЗАВЕРШЕН КАНДИДАТ
            state["completed"].append(cand_id)
            if cand_id in state.get("failed", {}):
                del state["failed"][cand_id]
            save_migration_state(state)
            success_count += 1

            if DELAY_BETWEEN_CANDIDATES > 0:
                time.sleep(DELAY_BETWEEN_CANDIDATES)

        except Exception as e:
            error_count += 1
            err_msg = str(e)
            log_message(f"   ❌ Ошибка при переносе кандидата {cand_id}: {err_msg}")
            state["failed"][cand_id] = err_msg
            save_migration_state(state)
            continue

    log_message("\n" + "="*60)
    log_message("🎉 МИГРАЦИЯ ЗАВЕРШЕНА!")
    log_message(f"   • Успешно перенесено за этот запуск: {success_count}")
    log_message(f"   • Пропущено (были перенесены ранее): {skipped_count}")
    log_message(f"   • Ошибок: {error_count}")
    log_message(f"   • Всего перенесено кандидатов: {len(state.get('completed', []))}")
    log_message(f"   • Подробный лог сохранён в: {LOG_FILE.resolve()}")
    log_message("="*60)

if __name__ == "__main__":
    run_migration()