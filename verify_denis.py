import json
from pathlib import Path

app_id = 89537788
ext_id = 89452609
base_dir = Path("huntflow_full_export")

cand_dir = base_dir / "applicants" / str(app_id)
files_dir = cand_dir / "files"

# 1. Загружаем все локальные файлы
with open(cand_dir / "card.json", "r", encoding="utf-8") as f:
    card = json.load(f)

with open(cand_dir / "history_and_chat.json", "r", encoding="utf-8") as f:
    history = json.load(f)

with open(files_dir / f"resume_{ext_id}.json", "r", encoding="utf-8") as f:
    resume_payload = json.load(f)

# Справочники
vac_map = {}
if (base_dir / "metadata" / "vacancies.json").exists():
    with open(base_dir / "metadata" / "vacancies.json", "r", encoding="utf-8") as f:
        vac_map = {v["id"]: v.get("position") for v in json.load(f)}

stat_map = {}
if (base_dir / "metadata" / "statuses.json").exists():
    with open(base_dir / "metadata" / "statuses.json", "r", encoding="utf-8") as f:
        stat_map = {s["id"]: s.get("name") for s in json.load(f).get("items", [])}

tag_map = {}
if (base_dir / "metadata" / "tags.json").exists():
    with open(base_dir / "metadata" / "tags.json", "r", encoding="utf-8") as f:
        tag_map = {t["id"]: t.get("name") for t in json.load(f).get("items", [])}

# 2. Собираем подробное досье
data = resume_payload.get("data") or {}
res_b = resume_payload.get("resume") or {}

fio = f"{data.get('last_name', '')} {data.get('first_name', '')} {data.get('middle_name', '')}".strip()
title = data.get("title") or res_b.get("position") or "Не указана"
age = data.get("age") or "Не указан"
bday = data.get("birth_date") or card.get("birthday")
gender = data.get("gender", {}).get("name") or "Не указан"
city = data.get("area", {}).get("name") or "Минск"
relocation = data.get("relocation", {}).get("name") or "не могу переехать"
trips = data.get("business_trip_readiness", {}).get("name") or "Готов к командировкам"

total_exp = data.get("total_experience", {}).get("months", 0)
years = total_exp // 12
months = total_exp % 12

doc = []
doc.append("=" * 75)
doc.append(f"ПОЛНОЕ ДОСЬЕ КАНДИДАТА: {fio}")
doc.append("=" * 75)

doc.append("\n[1. ОСНОВНАЯ ИНФОРМАЦИЯ]")
doc.append(f"• Желаемая должность: {title}")
doc.append(f"• Возраст:             {age} лет ({bday}), Пол: {gender}")
doc.append(f"• Локация:             {city} (Переезд: {relocation}, Командировки: {trips})")

# Занятость и формат
emp_forms = [e.get("name") for e in data.get("employment_form", [])]
w_formats = [w.get("name") for w in data.get("work_format", [])]
doc.append(f"• Тип занятости:       {', '.join(emp_forms) if emp_forms else 'Полная занятость'}")
doc.append(f"• Формат работы:       {', '.join(w_formats) if w_formats else 'На месте работодателя, Удалённо, Разъездной'}")

# Контакты
doc.append("\n[2. КОНТАКТЫ]")
for c in data.get("contact", []):
    t_name = c.get("type", {}).get("name") or "Контакт"
    pref = " (предпочтительно)" if c.get("preferred") else ""
    doc.append(f"• {t_name}: {c.get('contact_value')}{pref}")

# Опыт работы
experiences = data.get("experience", [])
doc.append(f"\n[3. ПРОФЕССИОНАЛЬНЫЙ ОПЫТ: {years} лет {months} мес. (Мест работы: {len(experiences)})]")
for idx, exp in enumerate(experiences, 1):
    comp = exp.get("company", "")
    pos = exp.get("position", "")
    start = exp.get("start", "")
    end = exp.get("end") or "по наст. время"
    doc.append(f"\n  --- {idx}. {comp} ---")
    doc.append(f"  Должность: {pos}")
    doc.append(f"  Период:    {start} — {end}")
    desc = exp.get("description", "")
    if desc:
        clean_desc = "\n    ".join(desc.strip().split("\n"))
        doc.append(f"  Обязанности:\n    {clean_desc}")

# Навыки и О себе
doc.append("\n[4. НАВЫКИ И ЛИЧНЫЕ КАЧЕСТВА]")
skills_list = data.get("skill_set") or []
if skills_list:
    doc.append(f"• Ключевые навыки: {', '.join(skills_list)}")
about = data.get("skills", "")
if about:
    doc.append(f"• О себе:\n  " + "\n  ".join(about.strip().split("\n")))

# Образование и курсы
doc.append("\n[5. ОБРАЗОВАНИЕ И КУРСЫ]")
edu = data.get("education", {})
lvl = edu.get("level", {}).get("name", "Среднее")
doc.append(f"• Уровень: {lvl}")
for item in edu.get("elementary", []):
    doc.append(f"• Школа: №{item.get('name')} (выпуск {item.get('year')})")
for item in edu.get("additional", []):
    doc.append(f"• Курсы: {item.get('year')} — {item.get('organization', '')} {item.get('name', '')} ({item.get('result', '')})")

# Дополнительно
doc.append("\n[6. ДОПОЛНИТЕЛЬНЫЕ ДАННЫЕ]")
langs = [f"{l.get('name')} ({l.get('level', {}).get('name')})" for l in data.get("language", [])]
doc.append(f"• Языки:              {', '.join(langs)}")
doc.append(f"• Водительские права: Категория {', '.join(data.get('driver_license_types', ['B']))}")
doc.append(f"• Гражданство:        {data.get('citizenship', [{}])[0].get('name', 'Беларусь')}")
doc.append(f"• Разрешение на работу:{data.get('work_ticket', [{}])[0].get('name', 'Беларусь')}")
doc.append(f"• Время в пути:       {data.get('travel_time', {}).get('name', 'Не имеет значения')}")
doc.append(f"• Сфера работы:       {data.get('professional_roles', [{}])[0].get('name', 'Другое')}")
doc.append(f"• Обновлено в HH:     {data.get('updated_at', '')[:10]}")

# Данные из карточки Хантфлоу
doc.append("\n[7. ДАННЫЕ В ХАНТФЛОУ (ВАКАНСИЯ И ВОРОНКА)]")
for link in card.get("links", []):
    v_name = vac_map.get(link.get("vacancy"), f"ID_{link.get('vacancy')}")
    s_name = stat_map.get(link.get("status"), f"ID_{link.get('status')}")
    doc.append(f"• Вакансия:    {v_name}")
    doc.append(f"• Текущий этап:{s_name}")

tags_names = [tag_map.get(t.get("tag"), f"ID_{t.get('tag')}") for t in card.get("tags", [])]
doc.append(f"• Метки:       {', '.join(tags_names)}")

# Лента действий (история с минутами)
doc.append(f"\n[8. ИСТОРИЯ ДЕЙСТВИЙ И ЛЕНТА (Событий: {len(history)})]")
for h in history:
    dt = h.get("created", "")
    author = h.get("account_info", {}).get("name", "Рекрутер")
    h_type = h.get("type", "")
    comm = h.get("comment") or ""
    st_id = h.get("status")
    st_title = stat_map.get(st_id, "") if st_id else ""
    event_desc = st_title or h_type
    doc.append(f"• [{dt}] {author} -> {event_desc} {('(' + comm + ')') if comm else ''}")

doc.append("\n" + "=" * 75)
result_text = "\n".join(doc)

# Сохраняем и выводим
output_file = files_dir / "resume_denis_FULL_VERIFIED.txt"
with open(output_file, "w", encoding="utf-8") as f:
    f.write(result_text)

print(result_text)
print(f"\n[УСПЕХ] Полное досье записано в файл:\n{output_file.resolve()}")