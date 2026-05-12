const STORAGE_KEY = 'uma_editable_site_data_v1';
const SELECTED_KEY = 'uma_selected_skills_v1';
const OWNED_KEY = 'uma_owned_state_v1';
const STYLE_NAMES = ['도주', '선행', '선입', '추입'];

let defaultData = null;
let data = null;
let selectedSkills = [];
let ownedState = { cards: {}, characters: {} };
let activeTab = 'recommend';

const $ = (id) => document.getElementById(id);
const deepClone = (obj) => JSON.parse(JSON.stringify(obj));
const safe = (v) => (v ?? '').toString();
const trim = (v) => safe(v).trim();
const uniq = (arr) => [...new Set((arr || []).map(trim).filter(Boolean))];
const splitList = (s) => uniq(safe(s).split(',').map(x => x.trim()).filter(Boolean));
const joinList = (arr) => uniq(arr).join(', ');
const escapeHtml = (s) => safe(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const parseMaybeNumber = (v) => {
  const s = trim(v);
  if (!s) return '';
  const n = Number(s.replace(/,/g, ''));
  return Number.isFinite(n) ? n : s;
};
const formatRate = (v) => {
  if (v === '' || v == null) return '-';
  if (typeof v === 'number') {
    if (v <= 1) return `${Math.round(v * 1000) / 10}%`;
    return `${v}`;
  }
  return safe(v);
};
const formatNum = (v) => {
  if (v === '' || v == null) return '-';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(Math.round(v * 1000) / 1000);
  const n = Number(v);
  if (Number.isFinite(n)) return Number.isInteger(n) ? String(n) : String(Math.round(n * 1000) / 1000);
  return safe(v);
};
const toast = (msg) => {
  const el = $('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 1800);
};

async function init() {
  try {
    const res = await fetch('data/site-data.json?v=' + Date.now());
    defaultData = await res.json();
  } catch (e) {
    defaultData = { title: 'UMA 추천기', courses: [], skillNames: [], skills: [], cards: [], characters: [] };
    toast('기본 data/site-data.json을 불러오지 못했습니다.');
  }
  const saved = localStorage.getItem(STORAGE_KEY);
  data = saved ? JSON.parse(saved) : deepClone(defaultData);
  selectedSkills = JSON.parse(localStorage.getItem(SELECTED_KEY) || '[]');
  ownedState = JSON.parse(localStorage.getItem(OWNED_KEY) || '{"cards":{},"characters":{}}');
  hydrateOwnedFromState();
  bindEvents();
  renderAll();
}

function hydrateOwnedFromState() {
  (data.cards || []).forEach(c => c.owned = !!ownedState.cards[c.name]);
  (data.characters || []).forEach(c => c.owned = !!ownedState.characters[c.name]);
}
function persistOwned() {
  ownedState = { cards: {}, characters: {} };
  (data.cards || []).forEach(c => { if (c.owned) ownedState.cards[c.name] = true; });
  (data.characters || []).forEach(c => { if (c.owned) ownedState.characters[c.name] = true; });
  localStorage.setItem(OWNED_KEY, JSON.stringify(ownedState));
}
function saveLocal() {
  hydrateOwnedFromState();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  localStorage.setItem(SELECTED_KEY, JSON.stringify(selectedSkills));
  persistOwned();
  toast('브라우저에 저장했습니다.');
}
function getActiveCourse() {
  const id = $('recCourse')?.value || data.activeCourseId || data.courses?.[0]?.id;
  return (data.courses || []).find(c => c.id === id) || data.courses?.[0];
}
function getCourseById(id) {
  return (data.courses || []).find(c => c.id === id);
}
function updateCounts() {
  const mashinRows = (data.courses || []).reduce((acc, c) => acc + STYLE_NAMES.reduce((s, st) => s + ((c.styles?.[st] || []).length), 0), 0);
  const counts = {
    courses: data.courses?.length || 0,
    skillNames: data.skillNames?.length || 0,
    skills: data.skills?.length || 0,
    cards: data.cards?.length || 0,
    characters: data.characters?.length || 0,
    mashinRows,
  };
  $('summaryCounts').textContent = `코스 ${counts.courses} · 스킬목록 ${counts.skillNames} · 스킬DB ${counts.skills} · 카드 ${counts.cards} · 캐릭터 ${counts.characters} · 마신표 ${counts.mashinRows}`;
  const summary = {
    title: data.title,
    version: data.version,
    updatedAt: new Date().toLocaleString('ko-KR'),
    counts,
    courses: (data.courses || []).map(c => ({ id: c.id, name: c.name, rows: Object.fromEntries(STYLE_NAMES.map(st => [st, c.styles?.[st]?.length || 0])) }))
  };
  if ($('dataSummary')) $('dataSummary').textContent = JSON.stringify(summary, null, 2);
}
function renderCourseSelects() {
  const options = (data.courses || []).map(c => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name || c.id)}</option>`).join('');
  ['recCourse','mashinCourse'].forEach(id => { if ($(id)) $(id).innerHTML = options; });
  const active = data.activeCourseId || data.courses?.[0]?.id || '';
  if ($('recCourse')) $('recCourse').value = active;
  if ($('mashinCourse')) $('mashinCourse').value = active;
  const c = getCourseById(active) || data.courses?.[0];
  if ($('mashinCourseName')) $('mashinCourseName').value = c?.name || '';
}
function renderDatalist() {
  const list = $('skillDatalist');
  if (!list) return;
  list.innerHTML = (data.skillNames || []).slice(0, 5000).map(s => `<option value="${escapeHtml(s)}"></option>`).join('');
}
function renderSelectedChips() {
  $('selectedSkills').innerHTML = selectedSkills.map(s => `<span class="chip">${escapeHtml(s)} <button data-remove-skill="${escapeHtml(s)}">×</button></span>`).join('') || '<span class="hint">선택된 스킬이 없습니다.</span>';
}
function findMashinRow(skill, course, style) {
  const rows = course?.styles?.[style] || [];
  return rows.find(r => r.skill === skill);
}
function renderSelectedMashin() {
  const course = getActiveCourse();
  const style = $('recStyle').value;
  let total = 0, matches = 0;
  const rows = selectedSkills.map(skill => {
    const m = findMashinRow(skill, course, style);
    if (m) { matches++; total += Number(m.gain) || 0; }
    return { skill, ...m };
  });
  $('kpiSelected').textContent = selectedSkills.length;
  $('kpiMashin').textContent = formatNum(total);
  $('kpiMatches').textContent = matches;
  $('selectedMashinTable').innerHTML = `<thead><tr><th>스킬명</th><th>마신이득</th><th>마신/Pt</th><th>발동률</th><th>유효율</th></tr></thead><tbody>` +
    rows.map(r => `<tr><td>${escapeHtml(r.skill)}</td><td class="num">${formatNum(r.gain)}</td><td class="num">${formatNum(r.gainPerPt)}</td><td class="num">${formatRate(r.procRate)}</td><td class="num">${formatRate(r.effectiveRate)}</td></tr>`).join('') +
    `</tbody>`;
}
function scoreItem(item, type) {
  const course = getActiveCourse();
  const style = $('recStyle').value;
  const normal = item.normalSkills || [];
  const event = item.eventSkills || [];
  const all = new Set([...normal, ...event]);
  const matched = selectedSkills.filter(s => all.has(s));
  const missing = selectedSkills.filter(s => !all.has(s));
  const mashin = matched.reduce((sum, s) => sum + (Number(findMashinRow(s, course, style)?.gain) || 0), 0);
  return { item, type, matched, missing, mashin, matchCount: matched.length };
}
function renderRecommendations() {
  const ownedOnly = $('recOwned').value === 'owned';
  const sortMode = $('recSort').value;
  const sorter = (a,b) => {
    if (sortMode === 'mashin') return b.mashin - a.mashin || b.matchCount - a.matchCount || a.missing.length - b.missing.length;
    if (sortMode === 'missing') return a.missing.length - b.missing.length || b.matchCount - a.matchCount || b.mashin - a.mashin;
    return b.matchCount - a.matchCount || b.mashin - a.mashin || a.missing.length - b.missing.length;
  };
  const renderList = (arr, target) => {
    const valid = arr.filter(x => x.matchCount > 0 && (!ownedOnly || x.item.owned)).sort(sorter).slice(0, 20);
    $(target).innerHTML = valid.length ? valid.map((x, i) => `<div class="result-card">
      <h4>${i+1}. ${escapeHtml(x.item.name)}</h4>
      <div class="muted">${escapeHtml([x.item.rarity, x.item.type, x.item.id].filter(Boolean).join(' · '))}</div>
      <div class="badges"><span class="badge match">매칭 ${x.matchCount}/${selectedSkills.length}</span><span class="badge mashin">마신합 ${formatNum(x.mashin)}</span><span class="badge miss">부족 ${x.missing.length}</span></div>
      <details><summary>매칭/부족 보기</summary><div class="hint">매칭: ${escapeHtml(x.matched.join(', ') || '-')}</div><div class="hint">부족: ${escapeHtml(x.missing.join(', ') || '-')}</div></details>
    </div>`).join('') : '<div class="hint">조건에 맞는 결과가 없습니다.</div>';
  };
  renderList((data.cards || []).map(c => scoreItem(c, 'card')), 'supportResults');
  renderList((data.characters || []).map(c => scoreItem(c, 'character')), 'characterResults');
}
function renderRecommend() {
  renderSelectedChips();
  renderSelectedMashin();
  renderRecommendations();
}

function parseMashinPaste(text) {
  const rows = safe(text).replace(/\r/g, '').split('\n').map(line => line.split('\t'));
  const parsed = [];
  for (const r of rows) {
    if (!r.length || !trim(r[0])) continue;
    if (trim(r[0]).includes('스킬명')) continue;
    parsed.push({
      skill: trim(r[0]),
      gain: parseMaybeNumber(r[1]),
      gainPerPt: parseMaybeNumber(r[2]),
      procRate: parseMaybeNumber(r[3]),
      effectiveRate: parseMaybeNumber(r[4]),
    });
  }
  return parsed;
}
function renderMashinEditor() {
  const cid = $('mashinCourse').value || data.activeCourseId || data.courses?.[0]?.id;
  const course = getCourseById(cid) || data.courses?.[0];
  if (!course) return;
  data.activeCourseId = course.id;
  $('mashinCourseName').value = course.name || '';
  const style = $('mashinStyle').value;
  const q = trim($('mashinSearch').value).toLowerCase();
  const rows = course.styles?.[style] || [];
  const filtered = rows.map((r, idx) => ({...r, idx})).filter(r => !q || safe(r.skill).toLowerCase().includes(q));
  $('mashinEditorTable').className = 'editor-table';
  $('mashinEditorTable').innerHTML = `<thead><tr><th>#</th><th>스킬명</th><th>마신이득</th><th>마신/Pt</th><th>발동률</th><th>유효율</th><th>관리</th></tr></thead><tbody>` +
    filtered.map((r, displayIdx) => `<tr data-mashin-idx="${r.idx}"><td>${displayIdx+1}</td>
      <td><input class="wide" data-field="skill" value="${escapeHtml(r.skill)}"></td>
      <td><input data-field="gain" value="${escapeHtml(r.gain)}"></td>
      <td><input data-field="gainPerPt" value="${escapeHtml(r.gainPerPt)}"></td>
      <td><input data-field="procRate" value="${escapeHtml(r.procRate)}"></td>
      <td><input data-field="effectiveRate" value="${escapeHtml(r.effectiveRate)}"></td>
      <td><button data-mashin-save="${r.idx}">저장</button> <button class="danger" data-mashin-del="${r.idx}">삭제</button></td></tr>`).join('') + '</tbody>';
}
function applyMashinRowFromInputs(idx) {
  const course = getCourseById($('mashinCourse').value);
  const style = $('mashinStyle').value;
  const tr = document.querySelector(`tr[data-mashin-idx="${idx}"]`);
  if (!course || !tr) return;
  const row = {};
  tr.querySelectorAll('input[data-field]').forEach(inp => row[inp.dataset.field] = ['gain','gainPerPt','procRate','effectiveRate'].includes(inp.dataset.field) ? parseMaybeNumber(inp.value) : trim(inp.value));
  if (!row.skill) return toast('스킬명은 비울 수 없습니다.');
  course.styles[style][idx] = row;
  syncSkillNames([row.skill]);
  renderAllLight();
  toast('마신표 행을 저장했습니다.');
}
function replaceOrAppendMashin(mode) {
  const parsed = parseMashinPaste($('mashinPaste').value);
  if (!parsed.length) return toast('붙여넣은 마신표를 읽지 못했습니다.');
  const course = getCourseById($('mashinCourse').value);
  const style = $('mashinStyle').value;
  course.styles ||= {}; course.styles[style] ||= [];
  if (mode === 'replace') course.styles[style] = parsed;
  else course.styles[style].push(...parsed);
  syncSkillNames(parsed.map(r => r.skill));
  $('mashinPasteInfo').textContent = `${parsed.length}행 반영`;
  renderAllLight();
  toast(`마신표 ${parsed.length}행을 반영했습니다.`);
}

function parseSkillDbPaste(text) {
  const rows = safe(text).replace(/\r/g, '').split('\n').map(line => line.split('\t'));
  const parsed = [];
  for (const r of rows) {
    if (!r.length || !trim(r[0])) continue;
    if (trim(r[0]).includes('스킬명')) continue;
    parsed.push({
      skill: trim(r[0]),
      characters: splitList(r[1] || ''),
      characterEvents: splitList(r[2] || ''),
      supportHints: splitList(r[3] || ''),
      supportEvents: splitList(r[4] || ''),
      status: trim(r[5] || ''),
    });
  }
  return parsed;
}
function renderSkillDbEditor() {
  const q = trim($('skillDbSearch').value).toLowerCase();
  const limitVal = $('skillDbLimit').value;
  let rows = (data.skills || []).map((r, idx) => ({...r, idx})).filter(r => !q || JSON.stringify(r).toLowerCase().includes(q));
  if (limitVal !== 'all') rows = rows.slice(0, Number(limitVal));
  $('skillDbEditorTable').className = 'editor-table';
  $('skillDbEditorTable').innerHTML = `<thead><tr><th>#</th><th>스킬명</th><th>캐릭터</th><th>캐릭터 이벤트</th><th>서포트 힌트</th><th>서포트 이벤트</th><th>상태</th><th>관리</th></tr></thead><tbody>` +
    rows.map((r, i) => `<tr data-skilldb-idx="${r.idx}"><td>${i+1}</td>
      <td><input class="mid" data-field="skill" value="${escapeHtml(r.skill)}"></td>
      <td><input class="wide" data-field="characters" value="${escapeHtml(joinList(r.characters))}"></td>
      <td><input class="wide" data-field="characterEvents" value="${escapeHtml(joinList(r.characterEvents))}"></td>
      <td><input class="wide" data-field="supportHints" value="${escapeHtml(joinList(r.supportHints))}"></td>
      <td><input class="wide" data-field="supportEvents" value="${escapeHtml(joinList(r.supportEvents))}"></td>
      <td><input class="mid" data-field="status" value="${escapeHtml(r.status)}"></td>
      <td><button data-skilldb-save="${r.idx}">저장</button> <button class="danger" data-skilldb-del="${r.idx}">삭제</button></td></tr>`).join('') + '</tbody>';
}
function applySkillDbRowFromInputs(idx) {
  const tr = document.querySelector(`tr[data-skilldb-idx="${idx}"]`);
  if (!tr) return;
  const row = {};
  tr.querySelectorAll('input[data-field]').forEach(inp => {
    const f = inp.dataset.field;
    row[f] = ['characters','characterEvents','supportHints','supportEvents'].includes(f) ? splitList(inp.value) : trim(inp.value);
  });
  if (!row.skill) return toast('스킬명은 비울 수 없습니다.');
  data.skills[idx] = row;
  syncSkillNames([row.skill]);
  rebuildGroupsFromSkillDb();
  renderAllLight();
  toast('스킬 DB 행을 저장했습니다.');
}
function mergeSkillDbRows(rows, replace=false) {
  if (replace) data.skills = rows;
  else {
    const map = new Map((data.skills || []).map((r, i) => [r.skill, {row:r, idx:i}]));
    rows.forEach(r => {
      if (map.has(r.skill)) data.skills[map.get(r.skill).idx] = r;
      else data.skills.push(r);
    });
  }
  syncSkillNames(rows.map(r => r.skill));
  rebuildGroupsFromSkillDb();
  renderAllLight();
}
function rebuildGroupsFromSkillDb() {
  // 기존 카드/캐릭터 DB는 유지하되, 스킬DB에만 새로 등장한 항목은 자동 생성한다.
  const cardMap = new Map((data.cards || []).map(c => [c.name, c]));
  const charMap = new Map((data.characters || []).map(c => [c.name, c]));
  (data.skills || []).forEach(row => {
    (row.supportHints || []).forEach(name => {
      if (!cardMap.has(name)) { const item = { name, normalSkills: [], eventSkills: [], owned:false }; data.cards.push(item); cardMap.set(name, item); }
      const item = cardMap.get(name); if (!item.normalSkills.includes(row.skill)) item.normalSkills.push(row.skill);
    });
    (row.supportEvents || []).forEach(name => {
      if (!cardMap.has(name)) { const item = { name, normalSkills: [], eventSkills: [], owned:false }; data.cards.push(item); cardMap.set(name, item); }
      const item = cardMap.get(name); if (!item.eventSkills.includes(row.skill)) item.eventSkills.push(row.skill);
    });
    (row.characters || []).forEach(name => {
      if (!charMap.has(name)) { const item = { name, normalSkills: [], eventSkills: [], owned:false }; data.characters.push(item); charMap.set(name, item); }
      const item = charMap.get(name); if (!item.normalSkills.includes(row.skill)) item.normalSkills.push(row.skill);
    });
    (row.characterEvents || []).forEach(name => {
      if (!charMap.has(name)) { const item = { name, normalSkills: [], eventSkills: [], owned:false }; data.characters.push(item); charMap.set(name, item); }
      const item = charMap.get(name); if (!item.eventSkills.includes(row.skill)) item.eventSkills.push(row.skill);
    });
  });
}
function syncSkillNames(names) {
  data.skillNames = uniq([...(data.skillNames || []), ...(names || [])]);
}
function renderSkillList() {
  $('skillListText').value = (data.skillNames || []).join('\n');
  $('skillListInfo').textContent = `${data.skillNames?.length || 0}개`;
}
function mergeSkillListFromData() {
  const names = [...(data.skillNames || [])];
  (data.skills || []).forEach(r => names.push(r.skill));
  (data.courses || []).forEach(c => STYLE_NAMES.forEach(st => (c.styles?.[st] || []).forEach(r => names.push(r.skill))));
  data.skillNames = uniq(names);
  renderAllLight();
  toast('스킬 목록을 병합했습니다.');
}
function renderOwned() {
  const type = $('ownedType').value;
  const q = trim($('ownedSearch').value).toLowerCase();
  const arr = (type === 'cards' ? data.cards : data.characters) || [];
  const filtered = arr.filter(x => !q || safe(x.name).toLowerCase().includes(q)).slice(0, 600);
  $('ownedList').innerHTML = filtered.map((x, i) => `<label class="owned-item"><input type="checkbox" data-owned-type="${type}" data-owned-name="${escapeHtml(x.name)}" ${x.owned ? 'checked' : ''}><span>${escapeHtml(x.name)}</span></label>`).join('') || '<div class="hint">검색 결과가 없습니다.</div>';
}
function setOwnedForFiltered(value) {
  const type = $('ownedType').value;
  const q = trim($('ownedSearch').value).toLowerCase();
  const arr = (type === 'cards' ? data.cards : data.characters) || [];
  arr.filter(x => !q || safe(x.name).toLowerCase().includes(q)).forEach(x => x.owned = value);
  persistOwned();
  renderOwned(); renderRecommendations();
}

function exportJSON(filename='site-data.json') {
  const exportData = deepClone(data);
  exportData.updatedAt = new Date().toISOString();
  exportData.counts = {
    courses: exportData.courses?.length || 0,
    skillNames: exportData.skillNames?.length || 0,
    skills: exportData.skills?.length || 0,
    cards: exportData.cards?.length || 0,
    characters: exportData.characters?.length || 0,
    mashinRows: (exportData.courses || []).reduce((acc,c)=>acc+STYLE_NAMES.reduce((s,st)=>s+(c.styles?.[st]?.length||0),0),0),
  };
  downloadText(filename, JSON.stringify(exportData, null, 2), 'application/json;charset=utf-8');
}
function downloadText(filename, text, type='text/plain;charset=utf-8') {
  const blob = new Blob([text], {type});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
function toMashinTsv(rows) {
  return ['스킬명\t마신이득\t마신/Pt\t발동률\t유효율', ...(rows || []).map(r => [r.skill, r.gain, r.gainPerPt, r.procRate, r.effectiveRate].map(v => safe(v)).join('\t'))].join('\n');
}
function toSkillDbTsv(rows) {
  return ['스킬명\t캐릭터\t캐릭터 (이벤트 획득)\t서포트 카드 (힌트 획득)\t서포트 카드 (이벤트 획득)\t상태', ...(rows || []).map(r => [r.skill, joinList(r.characters), joinList(r.characterEvents), joinList(r.supportHints), joinList(r.supportEvents), r.status].map(v => safe(v)).join('\t'))].join('\n');
}
function exportAllTsv() {
  const parts = [];
  (data.courses || []).forEach(c => STYLE_NAMES.forEach(st => {
    parts.push(`### ${c.name} / ${st}\n` + toMashinTsv(c.styles?.[st] || []));
  }));
  parts.push('### 스킬 DB\n' + toSkillDbTsv(data.skills || []));
  parts.push('### 스킬 목록\n' + (data.skillNames || []).join('\n'));
  downloadText('uma-data-tables.txt', parts.join('\n\n'));
}

function renderAllLight() {
  updateCounts(); renderDatalist(); renderRecommend();
  if (activeTab === 'mashin') renderMashinEditor();
  if (activeTab === 'skilldb') renderSkillDbEditor();
  if (activeTab === 'skilllist') renderSkillList();
  if (activeTab === 'owned') renderOwned();
}
function renderAll() {
  renderCourseSelects(); renderDatalist(); renderRecommend(); renderMashinEditor(); renderSkillDbEditor(); renderSkillList(); renderOwned(); updateCounts();
}

function bindEvents() {
  $('tabs').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-tab]'); if (!btn) return;
    activeTab = btn.dataset.tab;
    document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'tab-' + activeTab));
    if (activeTab === 'mashin') renderMashinEditor();
    if (activeTab === 'skilldb') renderSkillDbEditor();
    if (activeTab === 'skilllist') renderSkillList();
    if (activeTab === 'owned') renderOwned();
  });
  $('saveLocalBtn').onclick = saveLocal;
  $('exportJsonTopBtn').onclick = () => exportJSON();
  $('exportJsonBtn').onclick = () => exportJSON();
  $('exportBackupBtn').onclick = () => exportJSON('uma-site-backup.json');
  $('exportAllTsvBtn').onclick = exportAllTsv;
  $('resetDataBtn').onclick = () => { if (confirm('브라우저 저장 데이터를 지우고 기본 데이터로 되돌릴까요?')) { localStorage.removeItem(STORAGE_KEY); data = deepClone(defaultData); renderAll(); toast('기본 데이터로 초기화했습니다.'); } };
  $('importJsonInput').onchange = async (e) => {
    const file = e.target.files[0]; if (!file) return;
    data = JSON.parse(await file.text()); hydrateOwnedFromState(); renderAll(); saveLocal(); toast('JSON을 불러왔습니다.');
  };

  $('recCourse').onchange = () => { data.activeCourseId = $('recCourse').value; $('mashinCourse').value = data.activeCourseId; renderRecommend(); updateCounts(); };
  $('recStyle').onchange = renderRecommend; $('recSort').onchange = renderRecommendations; $('recOwned').onchange = renderRecommendations;
  $('addSkillBtn').onclick = () => { const s = trim($('skillSearchInput').value); if (!s) return; if (!selectedSkills.includes(s)) selectedSkills.push(s); $('skillSearchInput').value=''; renderRecommend(); localStorage.setItem(SELECTED_KEY, JSON.stringify(selectedSkills)); };
  $('skillSearchInput').addEventListener('keydown', e => { if (e.key === 'Enter') $('addSkillBtn').click(); });
  $('selectedSkills').addEventListener('click', e => { const s = e.target.dataset.removeSkill; if (!s) return; selectedSkills = selectedSkills.filter(x => x !== s); renderRecommend(); localStorage.setItem(SELECTED_KEY, JSON.stringify(selectedSkills)); });
  $('clearSelectedBtn').onclick = () => { selectedSkills = []; renderRecommend(); };
  $('exampleSelectedBtn').onclick = () => { selectedSkills = uniq(['터다지기','전광석화','스프린트 터보','빠른 걸음','우마무스메 애호가','장난은 끝이야!']); renderRecommend(); };

  $('mashinCourse').onchange = () => { data.activeCourseId = $('mashinCourse').value; $('recCourse').value = data.activeCourseId; renderMashinEditor(); renderRecommend(); updateCounts(); };
  $('mashinStyle').onchange = renderMashinEditor; $('mashinSearch').oninput = renderMashinEditor;
  $('saveCourseNameBtn').onclick = () => { const c = getCourseById($('mashinCourse').value); if (c) { c.name = trim($('mashinCourseName').value) || c.id; renderCourseSelects(); renderAllLight(); toast('코스명을 저장했습니다.'); } };
  $('addCourseBtn').onclick = () => { const name = prompt('새 코스 이름', '새 코스'); if (!name) return; const id = 'course-' + Date.now(); data.courses.push({id, name, styles:{도주:[],선행:[],선입:[],추입:[]}}); data.activeCourseId = id; renderAll(); toast('코스를 추가했습니다.'); };
  $('deleteCourseBtn').onclick = () => { if ((data.courses||[]).length <= 1) return toast('코스는 최소 1개 필요합니다.'); const c = getCourseById($('mashinCourse').value); if (c && confirm(`코스 [${c.name}]을 삭제할까요?`)) { data.courses = data.courses.filter(x => x.id !== c.id); data.activeCourseId = data.courses[0].id; renderAll(); } };
  $('addMashinRowBtn').onclick = () => { const c = getCourseById($('mashinCourse').value); const st = $('mashinStyle').value; c.styles ||= {}; c.styles[st] ||= []; c.styles[st].unshift({skill:'',gain:'',gainPerPt:'',procRate:'',effectiveRate:''}); renderMashinEditor(); };
  $('mashinEditorTable').addEventListener('click', e => {
    if (e.target.dataset.mashinSave) applyMashinRowFromInputs(Number(e.target.dataset.mashinSave));
    if (e.target.dataset.mashinDel) { const c = getCourseById($('mashinCourse').value); const st = $('mashinStyle').value; c.styles[st].splice(Number(e.target.dataset.mashinDel),1); renderAllLight(); }
  });
  $('previewMashinPasteBtn').onclick = () => { const p = parseMashinPaste($('mashinPaste').value); $('mashinPasteInfo').textContent = `${p.length}행 인식`; };
  $('replaceMashinPasteBtn').onclick = () => replaceOrAppendMashin('replace');
  $('appendMashinPasteBtn').onclick = () => replaceOrAppendMashin('append');
  $('exportMashinTsvBtn').onclick = () => { const c = getCourseById($('mashinCourse').value); const st = $('mashinStyle').value; downloadText(`${c.name}_${st}_마신표.tsv`, toMashinTsv(c.styles?.[st] || []), 'text/tab-separated-values;charset=utf-8'); };

  $('skillDbSearch').oninput = renderSkillDbEditor; $('skillDbLimit').onchange = renderSkillDbEditor;
  $('addSkillDbRowBtn').onclick = () => { data.skills.unshift({skill:'',characters:[],characterEvents:[],supportHints:[],supportEvents:[],status:'수기 추가'}); renderSkillDbEditor(); };
  $('skillDbEditorTable').addEventListener('click', e => {
    if (e.target.dataset.skilldbSave) applySkillDbRowFromInputs(Number(e.target.dataset.skilldbSave));
    if (e.target.dataset.skilldbDel) { data.skills.splice(Number(e.target.dataset.skilldbDel),1); renderAllLight(); }
  });
  $('replaceSkillDbPasteBtn').onclick = () => { const rows = parseSkillDbPaste($('skillDbPaste').value); if (!rows.length) return toast('읽을 행이 없습니다.'); mergeSkillDbRows(rows, true); $('skillDbPasteInfo').textContent = `${rows.length}행으로 교체`; };
  $('appendSkillDbPasteBtn').onclick = () => { const rows = parseSkillDbPaste($('skillDbPaste').value); if (!rows.length) return toast('읽을 행이 없습니다.'); mergeSkillDbRows(rows, false); $('skillDbPasteInfo').textContent = `${rows.length}행 추가/병합`; };
  $('exportSkillDbTsvBtn').onclick = () => downloadText('skill-db.tsv', toSkillDbTsv(data.skills || []), 'text/tab-separated-values;charset=utf-8');

  $('applySkillListBtn').onclick = () => { data.skillNames = uniq($('skillListText').value.split(/\r?\n/)); renderAllLight(); toast('스킬 목록을 적용했습니다.'); };
  $('mergeSkillListBtn').onclick = mergeSkillListFromData;
  $('exportSkillListBtn').onclick = () => downloadText('skill-list.txt', (data.skillNames||[]).join('\n'));

  $('ownedSearch').oninput = renderOwned; $('ownedType').onchange = renderOwned;
  $('ownedAllBtn').onclick = () => setOwnedForFiltered(true); $('ownedNoneBtn').onclick = () => setOwnedForFiltered(false);
  $('ownedList').addEventListener('change', e => { const cb = e.target.closest('input[data-owned-name]'); if (!cb) return; const arr = cb.dataset.ownedType === 'cards' ? data.cards : data.characters; const item = arr.find(x => x.name === cb.dataset.ownedName); if (item) item.owned = cb.checked; persistOwned(); renderRecommendations(); });
}

init();
