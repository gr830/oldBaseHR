import os
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import webbrowser

EXPORT_DIR = Path("huntflow_full_export")
PORT = 8080

# 1. Загрузка всех справочников
metadata_dir = EXPORT_DIR / "metadata"
vacancies_map = {}
statuses_map = {}
tags_map = {}
reasons_map = {}

if (metadata_dir / "vacancies.json").exists():
    try:
        with open(metadata_dir / "vacancies.json", "r", encoding="utf-8") as f:
            vacancies_map = {v["id"]: v.get("position", f"Вакансия #{v['id']}") for v in json.load(f)}
    except Exception: pass

if (metadata_dir / "statuses.json").exists():
    try:
        with open(metadata_dir / "statuses.json", "r", encoding="utf-8") as f:
            statuses_map = {s["id"]: s.get("name", f"Этап #{s['id']}") for s in json.load(f).get("items", [])}
    except Exception: pass

if (metadata_dir / "tags.json").exists():
    try:
        with open(metadata_dir / "tags.json", "r", encoding="utf-8") as f:
            tags_map = {t["id"]: t.get("name", f"Метка #{t['id']}") for t in json.load(f).get("items", [])}
    except Exception: pass

if (metadata_dir / "rejection_reasons.json").exists():
    try:
        with open(metadata_dir / "rejection_reasons.json", "r", encoding="utf-8") as f:
            reasons_map = {r["id"]: r.get("name", f"Причина #{r['id']}") for r in json.load(f).get("items", [])}
    except Exception: pass

# 2. Индексация базы кандидатов
print("Индексация базы кандидатов...")
candidates_index = []
applicants_dir = EXPORT_DIR / "applicants"

if applicants_dir.exists():
    for cand_folder in applicants_dir.iterdir():
        if not cand_folder.is_dir():
            continue
        card_file = cand_folder / "card.json"
        if not card_file.exists():
            continue
        try:
            with open(card_file, "r", encoding="utf-8") as f:
                card = json.load(f)
            
            c_id = card.get("id") or cand_folder.name
            fio = f"{card.get('last_name', '')} {card.get('first_name', '')} {card.get('middle_name', '')}".strip()
            files_dir = cand_folder / "files"
            has_resume = False
            
            if files_dir.exists():
                for rf in files_dir.glob("resume_*.json"):
                    has_resume = True
                    if not fio or "ID_" in fio:
                        try:
                            with open(rf, "r", encoding="utf-8") as r_f:
                                r_data = json.load(r_f).get("data", {})
                                l = r_data.get("last_name", "")
                                fn = r_data.get("first_name", "")
                                mn = r_data.get("middle_name", "")
                                parsed_fio = f"{l} {fn} {mn}".strip()
                                if parsed_fio: fio = parsed_fio
                        except Exception: pass
                    break

            if not fio: fio = f"Кандидат #{c_id}"

            vac_name = "Без вакансии"
            stat_name = "Новый"
            links = card.get("links", [])
            if links:
                vac_name = vacancies_map.get(links[0].get("vacancy"), "Вакансия")
                stat_name = statuses_map.get(links[0].get("status"), "Этап")

            candidates_index.append({
                "id": str(c_id),
                "fio": fio,
                "position": card.get("position") or "Должность не указана",
                "company": card.get("company") or "",
                "phone": card.get("phone") or "",
                "email": card.get("email") or "",
                "vacancy": vac_name,
                "status": stat_name,
                "money": card.get("money") or "",
                "has_resume": has_resume
            })
        except Exception:
            pass

print(f"Готово! В базе найдено: {len(candidates_index)} кандидатов")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>ATS Архив Кандидатов</title>
<style>
  :root {
    --bg-page: #f8fafc;
    --border: #e2e8f0;
    --text-main: #0f172a;
    --text-muted: #64748b;
    --primary: #2563eb;
    --primary-light: #eff6ff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; }
  body { display: flex; height: 100vh; background: var(--bg-page); color: var(--text-main); overflow: hidden; }

  /* Сайдбар */
  #sidebar { width: 380px; min-width: 350px; background: #fff; border-right: 1px solid var(--border); display: flex; flex-direction: column; }
  .sidebar-header { padding: 16px; border-bottom: 1px solid var(--border); background: #f8fafc; }
  .sidebar-header h1 { font-size: 17px; font-weight: 700; display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .badge-total { background: #e2e8f0; color: #334155; font-size: 12px; padding: 2px 8px; border-radius: 12px; font-weight: 600; }
  .search-box { width: 100%; padding: 10px 14px; border: 1px solid var(--border); border-radius: 8px; font-size: 14px; margin-bottom: 8px; outline: none; }
  .search-box:focus { border-color: var(--primary); box-shadow: 0 0 0 2px var(--primary-light); }
  .filters-row { display: flex; gap: 6px; }
  .filter-select { flex: 1; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 12px; outline: none; background: #fff; }

  #cand-list { flex: 1; overflow-y: auto; }
  .cand-item { padding: 14px 16px; border-bottom: 1px solid var(--border); cursor: pointer; transition: background 0.1s; }
  .cand-item:hover { background: #f8fafc; }
  .cand-item.active { background: var(--primary-light); border-left: 4px solid var(--primary); }
  .cand-item-name { font-size: 15px; font-weight: 600; color: var(--text-main); margin-bottom: 2px; }
  .cand-item-pos { font-size: 13px; color: var(--text-muted); margin-bottom: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .cand-item-badges { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .badge { font-size: 11px; padding: 2px 7px; border-radius: 4px; font-weight: 500; }
  .badge-status { background: #e2e8f0; color: #1e293b; }
  .badge-vac { background: #fef3c7; color: #92400e; max-width: 160px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .badge-money { background: #dcfce7; color: #166534; font-weight: 600; }

  /* Главная панель */
  #main { flex: 1; overflow-y: auto; display: flex; flex-direction: column; background: var(--bg-page); }
  .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); }

  /* Шапка кандидата */
  .profile-card { background: #fff; border-bottom: 1px solid var(--border); padding: 24px 36px; }
  .profile-header-top { display: flex; gap: 24px; align-items: flex-start; }
  .avatar { width: 90px; height: 90px; border-radius: 50%; object-fit: cover; border: 3px solid #e2e8f0; background: #cbd5e1; flex-shrink: 0; }
  .profile-title-area { flex: 1; }
  .profile-name { font-size: 26px; font-weight: 800; color: #0f172a; margin-bottom: 4px; }
  .profile-sub { font-size: 16px; color: #334155; font-weight: 500; margin-bottom: 12px; }
  .profile-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
  .tag-pill { background: #e0e7ff; color: #3730a3; padding: 3px 9px; border-radius: 6px; font-size: 12px; font-weight: 500; }

  /* Контакты */
  .contacts-grid { display: flex; flex-wrap: wrap; gap: 12px; font-size: 14px; margin-top: 10px; }
  .contact-btn { display: inline-flex; align-items: center; gap: 6px; color: var(--primary); text-decoration: none; font-weight: 500; background: #f8fafc; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border); }
  .contact-btn:hover { background: var(--primary-light); }

  /* Навигация по вкладкам */
  .nav-tabs { display: flex; background: #fff; border-bottom: 1px solid var(--border); padding: 0 36px; }
  .tab-btn { padding: 14px 20px; border: none; background: none; font-size: 14px; font-weight: 600; color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; }
  .tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }

  .tab-content { padding: 30px 36px; max-width: 1050px; margin: 0 auto; width: 100%; }

  /* Информационные плашки */
  .grid-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
  .info-block { background: #fff; padding: 18px 20px; border-radius: 10px; border: 1px solid var(--border); }
  .info-block-title { font-size: 12px; text-transform: uppercase; font-weight: 700; color: var(--text-muted); margin-bottom: 8px; letter-spacing: 0.5px; }
  .info-block-val { font-size: 14px; color: var(--text-main); font-weight: 500; line-height: 1.6; }

  .section-header { font-size: 17px; font-weight: 700; color: #0f172a; margin: 30px 0 16px 0; border-bottom: 2px solid var(--border); padding-bottom: 8px; }
  .section-header:first-child { margin-top: 0; }

  /* Опыт работы */
  .exp-card { background: #fff; border: 1px solid var(--border); border-radius: 10px; padding: 20px 24px; margin-bottom: 16px; }
  .exp-card-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }
  .exp-comp { font-size: 17px; font-weight: 700; color: #0f172a; }
  .exp-period { font-size: 13px; color: var(--text-muted); font-weight: 500; }
  .exp-pos { font-size: 15px; font-weight: 600; color: var(--primary); margin-bottom: 10px; }
  .exp-desc { font-size: 14px; line-height: 1.6; color: #334155; white-space: pre-wrap; background: #f8fafc; padding: 14px; border-radius: 8px; }

  /* Навыки тегами */
  .skills-wrapper { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
  .skill-badge { background: #f1f5f9; color: #1e293b; padding: 6px 14px; border-radius: 6px; font-size: 13px; font-weight: 600; border: 1px solid #cbd5e1; }

  /* Таймлайн истории */
  .timeline { position: relative; padding-left: 28px; }
  .timeline::before { content: ""; position: absolute; left: 8px; top: 8px; bottom: 8px; width: 2px; background: #cbd5e1; }
  .timeline-entry { position: relative; margin-bottom: 20px; }
  .timeline-dot { position: absolute; left: -28px; top: 4px; width: 14px; height: 14px; border-radius: 50%; background: var(--primary); border: 2px solid #fff; box-shadow: 0 0 0 2px var(--border); }
  .timeline-content { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 14px 18px; }
  .timeline-head { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
  .timeline-action { font-size: 14px; font-weight: 700; color: #0f172a; }
  .timeline-comment { margin-top: 8px; padding: 10px 14px; background: #fefce8; border-left: 3px solid #facc15; border-radius: 4px; font-size: 13px; color: #713f12; line-height: 1.5; }

  .quote-box { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 18px 20px; line-height: 1.6; font-size: 14px; white-space: pre-wrap; color: #334155; }
</style>
</head>
<body>

<div id="sidebar">
  <div class="sidebar-header">
    <h1>Кандидаты <span class="badge-total" id="totalCount">0</span></h1>
    <input type="text" id="searchInput" class="search-box" placeholder="Поиск по ФИО, должности, телефону...">
    <div class="filters-row">
      <select id="vacFilter" class="filter-select"><option value="">Все вакансии</option></select>
      <select id="statFilter" class="filter-select"><option value="">Все этапы</option></select>
    </div>
  </div>
  <div id="cand-list"></div>
</div>

<div id="main">
  <div class="empty-state" id="emptyState">
    <h2>Выберите соискателя из списка слева</h2>
    <p style="margin-top: 8px;">Вся база контактов, полная история общения и структурированные резюме</p>
  </div>
  <div id="detailsWrapper" style="display: none;"></div>
</div>

<script>
let allCandidates = [];
let currentCandidate = null;

// Месяцы на русском
const MONTHS_RU = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const MONTHS_NOMINATIVE = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

// Склонение лет и месяцев
function pluralize(n, forms) {
  n = Math.abs(n) % 100;
  const n1 = n % 10;
  if (n > 10 && n < 20) return forms[2];
  if (n1 > 1 && n1 < 5) return forms[1];
  if (n1 === 1) return forms[0];
  return forms[2];
}

// Расчет реального возраста
function calculateAge(bdayStr) {
  if (!bdayStr) return '';
  const parts = bdayStr.split('-');
  if (parts.length < 3) return '';
  const birthDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
  const today = new Date();
  let age = today.getFullYear() - birthDate.getFullYear();
  const m = today.getMonth() - birthDate.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) {
    age--;
  }
  const text = pluralize(age, ['год', 'года', 'лет']);
  const day = parseInt(parts[2]);
  const monthName = MONTHS_RU[parseInt(parts[1]) - 1];
  return `${age} ${text} (${day} ${monthName} ${parts[0]})`;
}

// Форматирование даты (2012-01-01 -> Январь 2012)
function formatMonthYear(dStr) {
  if (!dStr) return '';
  const p = dStr.split('-');
  if (p.length >= 2) {
    const mIdx = parseInt(p[1]) - 1;
    return `${MONTHS_NOMINATIVE[mIdx]} ${p[0]}`;
  }
  return dStr;
}

// Расчет длительности периода
function getPeriodDuration(startStr, endStr, refDateStr) {
  if (!startStr) return '';
  const sP = startStr.split('-');
  const start = new Date(parseInt(sP[0]), parseInt(sP[1]) - 1, 1);
  
  let end;
  if (endStr) {
    const eP = endStr.split('-');
    end = new Date(parseInt(eP[0]), parseInt(eP[1]) - 1, 1);
  } else if (refDateStr) {
    end = new Date(refDateStr);
  } else {
    end = new Date();
  }

  let totalMonths = (end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth()) + 1;
  if (totalMonths <= 0) totalMonths = 1;

  const y = Math.floor(totalMonths / 12);
  const m = totalMonths % 12;

  let res = [];
  if (y > 0) res.push(`${y} ${pluralize(y, ['год', 'года', 'лет'])}`);
  if (m > 0) res.push(`${m} ${pluralize(m, ['месяц', 'месяца', 'месяцев'])}`);
  return res.join(' ');
}

// Красивое форматирование телефона
function formatPhone(phone) {
  if (!phone) return '';
  const digits = phone.replace(/\\D/g, '');
  if (digits.length === 11 && digits.startsWith('7')) {
    return `+7 ${digits.slice(1,4)} ${digits.slice(4,7)}-${digits.slice(7,9)}-${digits.slice(9,11)}`;
  }
  if (digits.length === 12 && digits.startsWith('375')) {
    return `+375 ${digits.slice(3,5)} ${digits.slice(5,8)}-${digits.slice(8,10)}-${digits.slice(10,12)}`;
  }
  return phone;
}

async function init() {
  const res = await fetch('/api/candidates');
  allCandidates = await res.json();
  document.getElementById('totalCount').innerText = allCandidates.length;

  const vacs = new Set(allCandidates.map(c => c.vacancy).filter(v => v && v !== 'Без вакансии'));
  const stats = new Set(allCandidates.map(c => c.status).filter(Boolean));
  
  const vSelect = document.getElementById('vacFilter');
  vacs.forEach(v => vSelect.innerHTML += `<option value="${v}">${v}</option>`);
  
  const sSelect = document.getElementById('statFilter');
  stats.forEach(s => sSelect.innerHTML += `<option value="${s}">${s}</option>`);

  renderList(allCandidates);
  if (allCandidates.length > 0) selectCandidate(allCandidates[0].id);
}

function renderList(list) {
  const container = document.getElementById('cand-list');
  container.innerHTML = '';
  list.forEach(c => {
    const div = document.createElement('div');
    div.className = 'cand-item' + (currentCandidate && currentCandidate.id === c.id ? ' active' : '');
    div.onclick = () => selectCandidate(c.id);
    
    div.innerHTML = `
      <div class="cand-item-name">${c.fio}</div>
      <div class="cand-item-pos">${c.position} ${c.company ? '• ' + c.company : ''}</div>
      <div class="cand-item-badges">
        <span class="badge badge-status">${c.status}</span>
        <span class="badge badge-vac">${c.vacancy}</span>
        ${c.money ? `<span class="badge badge-money">${c.money}</span>` : ''}
      </div>
    `;
    container.appendChild(div);
  });
}

function filterList() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const v = document.getElementById('vacFilter').value;
  const s = document.getElementById('statFilter').value;
  
  const filtered = allCandidates.filter(c => {
    const mSearch = c.fio.toLowerCase().includes(q) || 
                    c.position.toLowerCase().includes(q) || 
                    c.phone.toLowerCase().includes(q) || 
                    c.email.toLowerCase().includes(q);
    const mVac = !v || c.vacancy === v;
    const mStat = !s || c.status === s;
    return mSearch && mVac && mStat;
  });
  renderList(filtered);
}

document.getElementById('searchInput').oninput = filterList;
document.getElementById('vacFilter').onchange = filterList;
document.getElementById('statFilter').onchange = filterList;

async function selectCandidate(id) {
  document.querySelectorAll('.cand-item').forEach(el => el.classList.remove('active'));
  const el = [...document.querySelectorAll('.cand-item')].find(e => e.innerHTML.includes(id));
  if (el) el.classList.add('active');

  const res = await fetch('/api/candidate/' + id);
  const data = await res.json();
  currentCandidate = data;
  renderFullCard(data);
}

function renderFullCard(data) {
  document.getElementById('emptyState').style.display = 'none';
  const wrapper = document.getElementById('detailsWrapper');
  wrapper.style.display = 'block';

  const card = data.card || {};
  const history = data.history || [];
  const resume = data.resume || {};
  const rData = resume.data || {};
  const rBase = resume.resume || {};
  const meta = data.meta || {};

  // 1. ФИО и шапка
  let fio = `${rData.last_name || card.last_name || ''} ${rData.first_name || card.first_name || ''} ${rData.middle_name || card.middle_name || ''}`.trim();
  if (!fio) fio = `Кандидат #${card.id}`;

  const currentPos = card.position || rData.title || rBase.position || 'Должность не указана';
  const currentCompany = card.company || (rData.experience && rData.experience[0] ? rData.experience[0].company : '');
  const resumeTitle = rData.title || rBase.position || currentPos;
  
  // Зарплата
  let salaryStr = card.money || '';
  if (!salaryStr && rData.salary) {
    salaryStr = `${rData.salary.amount.toLocaleString('ru-RU')} ${rData.salary.currency}`;
  }

  // 2. Демография
  const bdayRaw = rData.birth_date || card.birthday || '';
  const ageFormatted = calculateAge(bdayRaw);
  const gender = (rData.gender && rData.gender.name) || (rBase.gender && rBase.gender.name) || 'Не указан';
  const city = (rData.area && rData.area.name) || (rBase.area && rBase.area.city && rBase.area.city.name) || 'Санкт-Петербург';
  const metro = (rData.metro && rData.metro.name) ? `м. ${rData.metro.name}` : '';

  // Переезд и командировки
  let relocation = 'не готов к переезду';
  if (rData.relocation) {
    relocation = (rData.relocation.type && rData.relocation.type.name) || rData.relocation.name || relocation;
  }
  let trips = 'Не готов к командировкам';
  if (rData.business_trip_readiness) {
    trips = rData.business_trip_readiness.name || trips;
  }

  // Гражданство и права
  const citizenship = (rData.citizenship && rData.citizenship[0] && rData.citizenship[0].name) || 'Россия';
  const workTicket = (rData.work_ticket && rData.work_ticket[0] && rData.work_ticket[0].name) || citizenship;
  const driver = (rData.driver_license_types || []).map(d => d.id || d).join(', ') || 'Нет';
  const travelTime = (rData.travel_time && rData.travel_time.name) || 'Не имеет значения';

  // Контакты
  const phone = formatPhone(card.phone || (rData.contact && rData.contact[0] ? rData.contact[0].contact_value || (rData.contact[0].value && rData.contact[0].value.formatted) : ''));
  const email = card.email || (rData.contact && rData.contact.find(c => c.type && c.type.id === 'email') ? rData.contact.find(c => c.type && c.type.id === 'email').value : '');
  
  let tg = '';
  if (card.social && card.social[0]) tg = card.social[0].value.replace('@','');
  if (!tg && rData.contact) {
    const tgObj = rData.contact.find(c => c.type && (c.type.id === 'telegram' || c.type.name === 'Telegram'));
    if (tgObj) tg = tgObj.value.replace('@','');
  }

  // Теги
  const tagsHtml = (card.tags || []).map(t => `<span class="tag-pill">${meta.tags_map[t.tag] || 'Метка #' + t.tag}</span>`).join('');

  // 3. Профессиональный опыт
  const experiences = rData.experience || rBase.experience || [];
  let expHtml = '';
  let calculatedTotalMonths = 0;

  experiences.forEach(exp => {
    const comp = exp.company || 'Компания';
    const pos = exp.position || 'Должность';
    const startStr = exp.start || (exp.date_from ? `${exp.date_from.year}-${String(exp.date_from.month).padStart(2,'0')}-01` : '');
    const endStr = exp.end || (exp.date_to ? `${exp.date_to.year}-${String(exp.date_to.month).padStart(2,'0')}-01` : '');
    
    const startFmt = formatMonthYear(startStr);
    const endFmt = endStr ? formatMonthYear(endStr) : 'по настоящее время';
    const duration = getPeriodDuration(startStr, endStr, card.created);

    expHtml += `
      <div class="exp-card">
        <div class="exp-card-header">
          <div class="exp-comp">${comp}</div>
          <div class="exp-period">${startFmt} — ${endFmt} (${duration})</div>
        </div>
        <div class="exp-pos">${pos}</div>
        <div class="exp-desc">${exp.description || 'Описание не заполнено'}</div>
      </div>
    `;
  });

  // Общий стаж
  let totalExpHeader = '';
  if (experiences.length > 0) {
    const firstJobStart = experiences[experiences.length - 1].start || (experiences[experiences.length - 1].date_from ? `${experiences[experiences.length - 1].date_from.year}-${String(experiences[experiences.length - 1].date_from.month).padStart(2,'0')}-01` : '');
    totalExpHeader = getPeriodDuration(firstJobStart, null, card.created);
  }
  if (!totalExpHeader && rData.total_experience) {
    const y = Math.floor(rData.total_experience.months / 12);
    const m = rData.total_experience.months % 12;
    totalExpHeader = `${y} ${pluralize(y, ['год', 'года', 'лет'])} ${m} ${pluralize(m, ['месяц', 'месяца', 'месяцев'])}`;
  }

  // 4. Навыки
  const skillsList = rData.skill_set || rBase.skill_set || [];
  let skillsHtml = skillsList.map(s => `<span class="skill-badge">${s}</span>`).join('');
  if (!skillsHtml) skillsHtml = '<span style="color:#64748b">Навыки не указаны</span>';

  // 5. Образование
  const edu = rData.education || rBase.education || {};
  let eduHtml = '';
  if (edu.level && edu.level.name) eduHtml += `<div style="font-weight:700; margin-bottom:12px; color:#1e293b;">Уровень: ${edu.level.name}</div>`;
  (edu.primary || edu.higher || []).forEach(e => {
    eduHtml += `
      <div style="margin-bottom:12px;">
        🎓 <b>${e.name || ''}</b> (${e.year || ''})<br>
        <span style="color:#475569;">${e.organization || e.faculty ? (e.organization || e.faculty) + ' — ' : ''}${e.result || e.description || ''}</span>
      </div>
    `;
  });
  (edu.additional || []).forEach(e => {
    eduHtml += `
      <div style="margin-bottom:10px;">
        📜 <b>Курсы:</b> ${e.name || ''} (${e.year || ''})<br>
        <span style="color:#475569;">${e.organization || ''} — ${e.result || ''}</span>
      </div>
    `;
  });
  if (!eduHtml) eduHtml = 'Не указано';

  // 6. Дополнительно (языки, специализации)
  const langs = (rData.language || []).map(l => `${l.name} (${l.level ? l.level.name : 'родной'})`).join(', ') || 'Русский (родной)';
  const specs = (rData.specialization || []).map(s => s.name).join(' • ') || '';

  // 7. Таймлайн истории
  let historyHtml = '<div class="timeline">';
  history.forEach(h => {
    const dt = (h.created || '').replace('T', ' ').slice(0, 19);
    const author = (h.account_info && h.account_info.name) || 'Я';
    
    let actionTitle = meta.statuses_map[h.status] || h.type || 'Действие';
    if (h.type === 'VACANCY-ADD') actionTitle = 'Взят в работу на вакансию';
    if (h.type === 'ADD') actionTitle = 'Добавлен в базу';
    if (h.type === 'COMMENT') actionTitle = 'Комментарий';

    const commentBox = h.comment ? `<div class="timeline-comment">💬 ${h.comment}</div>` : '';
    const reasonBox = meta.reasons_map[h.rejection_reason] ? `<div style="color:#dc2626; font-size:12px; margin-top:2px;">Причина отказа: ${meta.reasons_map[h.rejection_reason]}</div>` : '';

    historyHtml += `
      <div class="timeline-entry">
        <div class="timeline-dot"></div>
        <div class="timeline-content">
          <div class="timeline-head">
            <span>👤 ${author}</span>
            <span>🕒 ${dt}</span>
          </div>
          <div class="timeline-action">${actionTitle}</div>
          ${reasonBox}
          ${commentBox}
        </div>
      </div>
    `;
  });
  historyHtml += '</div>';

  // 8. Рендеринг финального HTML
  wrapper.innerHTML = `
    <div class="profile-card">
      <div class="profile-header-top">
        <img src="${data.photo_url || card.photo_url || 'https://via.placeholder.com/90?text=Фото'}" class="avatar" onerror="this.src='https://via.placeholder.com/90?text=Нет+Фото'">
        <div class="profile-title-area">
          <div class="profile-name">${fio}</div>
          <div class="profile-sub">
            ${currentPos} ${currentCompany ? '• ' + currentCompany : ''}
            ${salaryStr ? '• <span style="color:#16a34a; font-weight:700;">' + salaryStr + '</span>' : ''}
          </div>
          
          <div class="profile-tags">
            ${tagsHtml}
            <span class="badge badge-vac" style="font-size:12px; padding:4px 8px;">💼 ${meta.current_vacancy}</span>
            <span class="badge badge-status" style="font-size:12px; padding:4px 8px;">📌 ${meta.current_status}</span>
          </div>

          <div class="contacts-grid">
            ${phone ? `<a href="tel:${phone}" class="contact-btn">📞 ${phone}</a>` : ''}
            ${email ? `<a href="mailto:${email}" class="contact-btn">✉️ ${email}</a>` : ''}
            ${tg ? `<a href="https://t.me/${tg}" target="_blank" class="contact-btn" style="color:#0284c7;">✈️ @${tg}</a>` : ''}
          </div>
        </div>
      </div>
    </div>

    <div class="nav-tabs">
      <button class="tab-btn active" onclick="switchTab('tab-resume')">📄 Полное резюме</button>
      <button class="tab-btn" onclick="switchTab('tab-history')">⏱️ Лента истории (${history.length})</button>
      <button class="tab-btn" onclick="switchTab('tab-system')">ℹ️ Анкета и метаданные</button>
      <button class="tab-btn" onclick="switchTab('tab-json')">💻 Исходный JSON</button>
    </div>

    <div class="tab-content" id="tab-resume">
      <div class="grid-2col">
        <div class="info-block">
          <div class="info-block-title">Основная информация</div>
          <div class="info-block-val">
            Должность в резюме: <b>${resumeTitle}</b><br>
            Возраст: <b>${ageFormatted || 'Не указан'}</b><br>
            Пол: <b>${gender}</b><br>
            Город: <b>${city}</b> ${metro ? '(' + metro + ')' : ''}
          </div>
        </div>
        <div class="info-block">
          <div class="info-block-title">Условия и статус</div>
          <div class="info-block-val">
            Переезд: <b>${relocation}</b><br>
            Командировки: <b>${trips}</b><br>
            Занятость: <b>${(rData.employment && rData.employment.name) || 'Полная занятость'}</b><br>
            Гражданство: <b>${citizenship}</b> (Разрешение: ${workTicket})
          </div>
        </div>
      </div>

      <div class="section-header">Профессиональный опыт (${totalExpHeader || experiences.length + ' мест'})</div>
      ${expHtml}

      <div class="section-header">Ключевые навыки</div>
      <div class="skills-wrapper">${skillsHtml}</div>

      <div class="section-header">Образование</div>
      <div class="info-block">${eduHtml}</div>

      <div class="section-header">Дополнительно</div>
      <div class="info-block">
        Знание языков: <b>${langs}</b><br>
        ${specs ? `Сфера работы: <b>${specs}</b><br>` : ''}
        Водительские права: <b>Категория ${driver}</b><br>
        Время в пути: <b>${travelTime}</b><br>
        Обновлено кандидатом: <b>${rData.updated_at ? rData.updated_at.slice(0,10) : '—'}</b>
      </div>
    </div>

    <div class="tab-content" id="tab-history" style="display:none;">
      ${historyHtml}
    </div>

    <div class="tab-content" id="tab-system" style="display:none;">
      <div class="info-block">
        <div class="info-block-title">Параметры карточки Хантфлоу</div>
        <div class="info-block-val">
          • Внутренний ID кандидата: <b>${card.id}</b><br>
          • Дата добавления в базу: <b>${card.created}</b><br>
          • Текущая вакансия: <b>${meta.current_vacancy}</b><br>
          • Текущий статус: <b>${meta.current_status}</b><br>
          • Причина отказа (если есть): <b>${meta.rejection_reason || 'Нет'}</b><br>
          • Источник резюме: <b>${card.external && card.external[0] ? card.external[0].auth_type : 'Прямой ввод'}</b>
        </div>
      </div>
    </div>

    <div class="tab-content" id="tab-json" style="display:none;">
      <div style="margin-bottom:10px; font-weight:700;">card.json:</div>
      <pre style="background:#0f172a; color:#f8fafc; padding:16px; border-radius:8px; font-size:12px; overflow:auto; max-height:350px; margin-bottom:20px;">${JSON.stringify(card, null, 2)}</pre>
      
      <div style="margin-bottom:10px; font-weight:700;">resume.json:</div>
      <pre style="background:#0f172a; color:#f8fafc; padding:16px; border-radius:8px; font-size:12px; overflow:auto; max-height:400px;">${JSON.stringify(resume, null, 2)}</pre>
    </div>
  `;
}

function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
  
  event.target.classList.add('active');
  document.getElementById(tabId).style.display = 'block';
}

init();
</script>
</body>
</html>
"""


class ViewerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            return

        elif path == "/api/candidates":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(candidates_index, ensure_ascii=False).encode("utf-8"))
            return

        elif path.startswith("/api/candidate/"):
            cand_id = path.replace("/api/candidate/", "").strip()
            cand_dir = applicants_dir / cand_id
            
            card_data = {}
            history_data = []
            resume_data = {}
            photo_url = None

            if (cand_dir / "card.json").exists():
                with open(cand_dir / "card.json", "r", encoding="utf-8") as f:
                    card_data = json.load(f)

            if (cand_dir / "history_and_chat.json").exists():
                with open(cand_dir / "history_and_chat.json", "r", encoding="utf-8") as f:
                    history_data = json.load(f)

            files_dir = cand_dir / "files"
            if files_dir.exists():
                for rf in files_dir.glob("resume_*.json"):
                    with open(rf, "r", encoding="utf-8") as f:
                        resume_data = json.load(f)
                    break
                if (files_dir / "photo.jpg").exists():
                    photo_url = f"/api/photo/{cand_id}"

            # Сопоставление с текстовыми справочниками
            current_vac = "Без вакансии"
            current_stat = "Новый"
            rej_reason = ""
            if card_data.get("links"):
                link = card_data["links"][0]
                current_vac = vacancies_map.get(link.get("vacancy"), f"Вакансия #{link.get('vacancy')}")
                current_stat = statuses_map.get(link.get("status"), f"Этап #{link.get('status')}")
                if link.get("rejection_reason"):
                    rej_reason = reasons_map.get(link.get("rejection_reason"), f"Причина #{link.get('rejection_reason')}")

            result = {
                "id": cand_id,
                "card": card_data,
                "history": history_data,
                "resume": resume_data,
                "photo_url": photo_url,
                "meta": {
                    "current_vacancy": current_vac,
                    "current_status": current_stat,
                    "rejection_reason": rej_reason,
                    "statuses_map": statuses_map,
                    "tags_map": tags_map,
                    "reasons_map": reasons_map
                }
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            return

        elif path.startswith("/api/photo/"):
            cand_id = path.replace("/api/photo/", "").strip()
            photo_path = applicants_dir / cand_id / "files" / "photo.jpg"
            if photo_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.end_headers()
                with open(photo_path, "rb") as f:
                    self.wfile.write(f.read())
                return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def main():
    # Ставим 0.0.0.0, чтобы сайт открывался с других компьютеров в сети
    server = HTTPServer(("0.0.0.0", PORT), ViewerHandler)
    print("\n" + "=" * 60)
    print(f" ВЕБ-ИНТЕРФЕЙС ЗАПУЩЕН НА СЕРВЕРЕ (ПОРТ {PORT})")
    print("=" * 60 + "\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен.")