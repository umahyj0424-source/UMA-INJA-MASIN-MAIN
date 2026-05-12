let DATA = null;
async function boot(){
  DATA = await fetch('data/site-data.json', {cache:'no-cache'}).then(r => r.json());
const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => Array.from(document.querySelectorAll(sel));
    const norm = (s) => String(s ?? '').trim().replace(/\s+/g, '').replace(/[◯〇]/g, '○').toLowerCase();
    const uniq = (arr) => Array.from(new Set(arr));
    const byNorm = new Map(DATA.skillNames.map(s => [norm(s), s]));
    const skillByNorm = new Map(DATA.skills.map(s => [norm(s.name), s]));
    const courses = Array.isArray(DATA.courses) && DATA.courses.length
      ? DATA.courses
      : [{id: 'default', name: '기본 마신표', baseUrl: '', styles: DATA.styles || {}}];
    let activeCourseId = localStorage.getItem('umaSkillSiteCourse') || String(courses[0].id);
    if (!courses.some(c => String(c.id) === String(activeCourseId))) activeCourseId = String(courses[0].id);
    let statsMap = {};

    function currentCourse() {
      return courses.find(c => String(c.id) === String(activeCourseId)) || courses[0];
    }
    function currentStyles() {
      return currentCourse()?.styles || DATA.styles || {};
    }
    function rebuildStatsMap() {
      statsMap = {};
      for (const [style, rows] of Object.entries(currentStyles())) {
        statsMap[style] = new Map((rows || []).map(r => [norm(r.skill), r]));
      }
    }
    function populateCourseSelects() {
      const html = courses.map(c => `<option value="${escapeHtml(String(c.id))}">${escapeHtml(c.name || ('코스 ' + c.id))}</option>`).join('');
      ['courseSelect','statsCourse'].forEach(id => {
        const el = $('#'+id);
        if (!el) return;
        el.innerHTML = html;
        el.value = activeCourseId;
      });
    }
    function setActiveCourse(id) {
      activeCourseId = String(id || courses[0].id);
      localStorage.setItem('umaSkillSiteCourse', activeCourseId);
      ['courseSelect','statsCourse'].forEach(sel => { const el = $('#'+sel); if (el) el.value = activeCourseId; });
      rebuildStatsMap();
      renderAll();
      renderStatsTable();
      renderSkillDb();
    }
    rebuildStatsMap();

    let selected = [];
    let owned = loadOwned();

    function loadOwned() {
      try {
        return JSON.parse(localStorage.getItem('umaSkillSiteOwned') || '{"cards":[],"characters":[]}');
      } catch {
        return {cards:[], characters:[]};
      }
    }
    function saveOwned() { localStorage.setItem('umaSkillSiteOwned', JSON.stringify(owned)); }
    function isOwned(kind, name) { return (owned[kind] || []).includes(name); }
    function toggleOwned(kind, name) {
      owned[kind] = owned[kind] || [];
      if (owned[kind].includes(name)) owned[kind] = owned[kind].filter(x => x !== name);
      else owned[kind].push(name);
      saveOwned(); renderAll(); renderOwnedList();
    }
    function fmtNum(v) {
      if (v === null || v === undefined || v === '') return '-';
      if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(3).replace(/0+$/,'').replace(/\.$/,'');
      return String(v);
    }
    function fmtPct(v) {
      if (v === null || v === undefined || v === '') return '-';
      if (typeof v === 'number') return (v * 100).toFixed(v === 1 ? 0 : 1).replace(/\.0$/,'') + '%';
      return String(v);
    }
    function highlight(text, q) {
      text = String(text ?? '');
      q = String(q ?? '').trim();
      if (!q) return escapeHtml(text);
      const i = norm(text).indexOf(norm(q));
      if (i < 0) return escapeHtml(text);
      // Korean normalization removes spaces, so exact visual index is hard. Use safe fallback.
      return escapeHtml(text).replace(new RegExp(escapeReg(q), 'gi'), m => `<mark>${m}</mark>`);
    }
    function escapeHtml(s) { return String(s ?? '').replace(/[&<>"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch])); }
    function escapeReg(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

    function canonicalSkill(q) {
      const n = norm(q);
      if (!n) return null;
      if (byNorm.has(n)) return byNorm.get(n);
      const exactSkill = DATA.skillNames.find(s => norm(s) === n);
      if (exactSkill) return exactSkill;
      return DATA.skillNames.find(s => norm(s).includes(n)) || null;
    }
    function addSkill(q) {
      const skill = canonicalSkill(q || $('#skillInput').value);
      if (!skill) return;
      if (!selected.some(s => norm(s) === norm(skill))) selected.push(skill);
      $('#skillInput').value = '';
      renderSuggestions('');
      renderAll();
    }
    function removeSkill(skill) { selected = selected.filter(s => norm(s) !== norm(skill)); renderAll(); }

    function renderSuggestions(q) {
      const box = $('#skillSuggestions');
      const nq = norm(q);
      if (!nq) { box.innerHTML = ''; return; }
      const hits = DATA.skillNames
        .filter(s => norm(s).includes(nq))
        .slice(0, 12);
      box.innerHTML = hits.map(s => `<button class="suggestion" data-add="${escapeHtml(s)}">${highlight(s, q)}</button>`).join('') || '<div class="empty">검색 결과 없음</div>';
    }

    function statOf(style, skill) { return statsMap[style]?.get(norm(skill)); }
    function gainOf(style, skill) {
      const st = statOf(style, skill);
      return typeof st?.gain === 'number' ? st.gain : 0;
    }

    function renderSelected() {
      const chips = $('#selectedChips');
      chips.innerHTML = selected.length
        ? selected.map(s => `<span class="chip">${escapeHtml(s)} <button title="삭제" data-remove="${escapeHtml(s)}">×</button></span>`).join('')
        : '<span class="hint">아직 선택된 스킬 없음</span>';
    }

    function renderSelectedStats() {
      const style = $('#styleSelect').value;
      const rows = selected.map(skill => {
        const st = statOf(style, skill);
        const sk = skillByNorm.get(norm(skill));
        const sourceCount = (sk?.cardsNormal?.length || 0) + (sk?.cardsEvent?.length || 0) + (sk?.charsNormal?.length || 0) + (sk?.charsEvent?.length || 0);
        return {skill, st, sourceCount};
      });
      const totalGain = rows.reduce((a,r)=>a+(typeof r.st?.gain === 'number' ? r.st.gain : 0),0);
      const matchedStats = rows.filter(r => r.st).length;
      $('#summaryStats').innerHTML = `
        <div class="stat"><strong>${selected.length}</strong><span>선택 스킬</span></div>
        <div class="stat"><strong>${fmtNum(totalGain)}</strong><span>${style} 기준 마신합</span></div>
        <div class="stat"><strong>${matchedStats}</strong><span>마신표 매칭</span></div>`;
      if (!selected.length) {
        $('#selectedStats').innerHTML = '<div class="empty">스킬을 추가하면 여기서 각질별 마신이득을 바로 확인할 수 있음.</div>';
        return;
      }
      $('#selectedStats').innerHTML = `<div class="table-wrap"><table>
        <thead><tr><th>스킬</th><th>마신이득</th><th>마신/Pt</th><th>발동률</th><th>유효율</th><th>획득처 수</th></tr></thead>
        <tbody>${rows.map(r => `<tr>
          <td><b>${escapeHtml(r.skill)}</b></td>
          <td>${fmtNum(r.st?.gain)}</td>
          <td>${fmtNum(r.st?.gainPerPt)}</td>
          <td>${fmtPct(r.st?.procRate)}</td>
          <td>${fmtPct(r.st?.effectiveRate)}</td>
          <td>${r.sourceCount}</td>
        </tr>`).join('')}</tbody></table></div>`;
    }

    function scoreEntity(entity, style) {
      const normalSet = new Set(entity.normalSkills.map(norm));
      const eventSet = new Set(entity.eventSkills.map(norm));
      const normalMatches = [];
      const eventMatches = [];
      const matched = [];
      for (const s of selected) {
        const n = norm(s);
        const inNormal = normalSet.has(n);
        const inEvent = eventSet.has(n);
        if (inNormal) normalMatches.push(s);
        if (inEvent) eventMatches.push(s);
        if (inNormal || inEvent) matched.push(s);
      }
      const missing = selected.filter(s => !matched.some(m => norm(m) === norm(s)));
      const score = uniq(matched.map(norm)).reduce((acc, n) => acc + gainOf(style, byNorm.get(n) || n), 0);
      return {normalMatches, eventMatches, matched: uniq(matched), missing, count: uniq(matched.map(norm)).length, score};
    }
    function sortResults(a, b) {
      const mode = $('#sortSelect').value;
      if (mode === 'count') return (b.match.count - a.match.count) || (b.match.score - a.match.score) || a.name.localeCompare(b.name, 'ko');
      if (mode === 'name') return a.name.localeCompare(b.name, 'ko');
      return (b.match.score - a.match.score) || (b.match.count - a.match.count) || a.name.localeCompare(b.name, 'ko');
    }

    function resultCard(item, match, kind, rank) {
      const ownedKey = kind === 'cards' ? 'cards' : 'characters';
      const ownedOn = isOwned(ownedKey, item.name);
      const sub = kind === 'cards'
        ? `${item.rarity || ''}${item.type ? ' · ' + item.type : ''}${item.code ? ' · ' + item.code : ''}`
        : '캐릭터';
      const totalSkills = (item.normalSkills?.length || 0) + (item.eventSkills?.length || 0);
      return `<article class="result-card">
        <div class="result-head">
          <div>
            <div class="title-line">${rank}. ${escapeHtml(kind === 'cards' ? item.display || item.name : item.name)}</div>
            <div class="meta">${escapeHtml(sub)} · 전체 스킬 ${totalSkills}개</div>
          </div>
          <button class="star ${ownedOn ? 'on' : ''}" title="보유 토글" data-own-kind="${ownedKey}" data-own-name="${escapeHtml(item.name)}">★</button>
        </div>
        <div class="badges">
          <span class="badge score">매칭 ${match.count}/${selected.length}</span>
          <span class="badge score">마신합 ${fmtNum(match.score)}</span>
          ${match.normalMatches.map(s => `<span class="badge normal">일반: ${escapeHtml(s)}</span>`).join('')}
          ${match.eventMatches.map(s => `<span class="badge event">이벤트: ${escapeHtml(s)}</span>`).join('')}
          ${match.missing.length ? `<span class="badge miss">부족 ${match.missing.length}개</span>` : ''}
        </div>
        <details>
          <summary>전체 스킬 보기</summary>
          <div class="badges">
            ${item.normalSkills.map(s => `<span class="badge normal">${escapeHtml(s)}</span>`).join('')}
            ${item.eventSkills.map(s => `<span class="badge event">${escapeHtml(s)}</span>`).join('')}
          </div>
        </details>
      </article>`;
    }

    function renderRecommendations() {
      if (!selected.length) {
        $('#cardResults').innerHTML = '<div class="empty">희망 스킬을 먼저 추가해줘.</div>';
        $('#charResults').innerHTML = '<div class="empty">희망 스킬을 먼저 추가해줘.</div>';
        return;
      }
      const style = $('#styleSelect').value;
      const ownedOnly = $('#ownedOnly').checked;
      const cardResults = DATA.cards.map(c => ({...c, match: scoreEntity(c, style)}))
        .filter(x => x.match.count > 0)
        .filter(x => !ownedOnly || isOwned('cards', x.name))
        .sort(sortResults)
        .slice(0, 30);
      const charResults = DATA.characters.map(c => ({...c, match: scoreEntity(c, style)}))
        .filter(x => x.match.count > 0)
        .filter(x => !ownedOnly || isOwned('characters', x.name))
        .sort(sortResults)
        .slice(0, 30);
      $('#cardResults').innerHTML = cardResults.length ? cardResults.map((x,i)=>resultCard(x,x.match,'cards',i+1)).join('') : '<div class="empty">조건에 맞는 서포트카드 없음</div>';
      $('#charResults').innerHTML = charResults.length ? charResults.map((x,i)=>resultCard(x,x.match,'characters',i+1)).join('') : '<div class="empty">조건에 맞는 캐릭터 없음</div>';
    }

    function renderStatsTable() {
      const style = $('#statsStyle').value;
      const q = norm($('#statsSearch').value);
      const sort = $('#statsSort').value;
      let rows = [...(currentStyles()[style] || [])];
      if (q) rows = rows.filter(r => norm(r.skill).includes(q));
      rows.sort((a,b) => sort === 'name' ? a.skill.localeCompare(b.skill, 'ko') : sort === 'pt' ? ((b.gainPerPt || 0) - (a.gainPerPt || 0)) : ((b.gain || 0) - (a.gain || 0)));
      rows = rows.slice(0, 250);
      $('#statsTable').innerHTML = `<div class="table-wrap"><table>
        <thead><tr><th>추가</th><th>스킬명</th><th>마신이득</th><th>마신/Pt</th><th>발동률</th><th>유효율</th></tr></thead>
        <tbody>${rows.map(r => `<tr>
          <td><button class="btn small secondary" data-add="${escapeHtml(r.skill)}">+</button></td>
          <td><b>${highlight(r.skill, $('#statsSearch').value)}</b></td>
          <td>${fmtNum(r.gain)}</td><td>${fmtNum(r.gainPerPt)}</td><td>${fmtPct(r.procRate)}</td><td>${fmtPct(r.effectiveRate)}</td>
        </tr>`).join('')}</tbody></table></div>`;
    }

    function renderSkillDb() {
      const qRaw = $('#dbSearch').value;
      const q = norm(qRaw);
      const filter = $('#dbFilter').value;
      const allStatsNorm = new Set(Object.values(statsMap).flatMap(m => Array.from(m.keys())));
      let rows = DATA.skills.filter(s => {
        const meta = s.meta || {};
        const hasSource = (s.cardsNormal.length + s.cardsEvent.length + s.charsNormal.length + s.charsEvent.length) > 0;
        const hasStats = allStatsNorm.has(norm(s.name));
        if (filter === 'source' && !hasSource) return false;
        if (filter === 'stats' && !hasStats) return false;
        if (!q) return true;
        return [s.name, meta.jp, meta.category, meta.grade, meta.owner].some(x => norm(x).includes(q));
      }).slice(0, 80);
      $('#skillDbResults').innerHTML = rows.length ? rows.map(s => {
        const meta = s.meta || {};
        const sourceCount = s.cardsNormal.length + s.cardsEvent.length + s.charsNormal.length + s.charsEvent.length;
        const statBadges = Object.keys(statsMap).filter(style => statsMap[style].has(norm(s.name))).map(style => `<span class="badge score">${style} ${fmtNum(statsMap[style].get(norm(s.name)).gain)}</span>`).join('');
        return `<article class="result-card">
          <div class="result-head">
            <div><div class="title-line">${highlight(s.name, qRaw)}</div>
            <div class="meta">${escapeHtml([meta.category, meta.grade, meta.jp, meta.owner].filter(Boolean).join(' · ') || '분류 정보 없음')} · 획득처 ${sourceCount}개</div></div>
            <button class="btn small secondary" data-add="${escapeHtml(s.name)}">추천기에 추가</button>
          </div>
          <div class="badges">${statBadges || '<span class="badge">마신표 없음</span>'}</div>
          <details open><summary>획득처</summary>
            <div class="badges">
              ${s.cardsNormal.map(x => `<span class="badge normal">카드 일반: ${escapeHtml(x)}</span>`).join('')}
              ${s.cardsEvent.map(x => `<span class="badge event">카드 이벤트: ${escapeHtml(x)}</span>`).join('')}
              ${s.charsNormal.map(x => `<span class="badge normal">캐릭터 일반: ${escapeHtml(x)}</span>`).join('')}
              ${s.charsEvent.map(x => `<span class="badge event">캐릭터 이벤트: ${escapeHtml(x)}</span>`).join('')}
              ${sourceCount ? '' : '<span class="badge miss">획득처 데이터 없음</span>'}
            </div>
          </details>
        </article>`;
      }).join('') : '<div class="empty">검색 결과 없음</div>';
    }

    function renderOwnedList() {
      const q = norm($('#ownedSearch')?.value || '');
      const cards = DATA.cards.filter(c => !q || norm(c.name).includes(q) || norm(c.display).includes(q)).slice(0, 120);
      const chars = DATA.characters.filter(c => !q || norm(c.name).includes(q)).slice(0, 120);
      $('#ownedList').innerHTML = `
        <h3>서포트카드</h3>
        ${cards.map(c => `<article class="result-card"><div class="result-head"><div><div class="title-line">${escapeHtml(c.display || c.name)}</div><div class="meta">${escapeHtml([c.rarity,c.type,c.code].filter(Boolean).join(' · '))}</div></div><button class="star ${isOwned('cards', c.name) ? 'on' : ''}" data-own-kind="cards" data-own-name="${escapeHtml(c.name)}">★</button></div></article>`).join('')}
        <h3>캐릭터</h3>
        ${chars.map(c => `<article class="result-card"><div class="result-head"><div><div class="title-line">${escapeHtml(c.name)}</div><div class="meta">스킬 ${c.normalSkills.length + c.eventSkills.length}개</div></div><button class="star ${isOwned('characters', c.name) ? 'on' : ''}" data-own-kind="characters" data-own-name="${escapeHtml(c.name)}">★</button></div></article>`).join('')}`;
    }

    function renderAll() {
      renderSelected();
      renderSelectedStats();
      renderRecommendations();
      const courseLabel = currentCourse()?.name || '기본 마신표';
      $('#dataCounts').textContent = `코스 ${courseLabel} · 스킬 ${DATA.counts.skills.toLocaleString()} · 카드 ${DATA.counts.cards.toLocaleString()} · 캐릭터 ${DATA.counts.characters.toLocaleString()}`;
    }

    document.addEventListener('click', e => {
      const tab = e.target.closest('[data-tab]');
      if (tab) {
        $$('.tab').forEach(t=>t.classList.toggle('active', t === tab));
        $$('.section').forEach(s=>s.classList.toggle('active', s.id === tab.dataset.tab));
        if (tab.dataset.tab === 'stats') renderStatsTable();
        if (tab.dataset.tab === 'skilldb') renderSkillDb();
        if (tab.dataset.tab === 'owned') renderOwnedList();
      }
      const add = e.target.closest('[data-add]');
      if (add) addSkill(add.dataset.add);
      const rem = e.target.closest('[data-remove]');
      if (rem) removeSkill(rem.dataset.remove);
      const own = e.target.closest('[data-own-kind]');
      if (own) toggleOwned(own.dataset.ownKind, own.dataset.ownName);
    });
    $('#addSkillBtn').addEventListener('click', () => addSkill());
    $('#skillInput').addEventListener('input', e => renderSuggestions(e.target.value));
    $('#skillInput').addEventListener('keydown', e => { if (e.key === 'Enter') addSkill(); });
    $('#clearSelectedBtn').addEventListener('click', () => { selected = []; renderAll(); });
    $('#sampleBtn').addEventListener('click', () => { selected = ['터다지기', '전광석화', '스프린트 터보', '꽃봉오리, 피어날 때']; renderAll(); });
    populateCourseSelects();
    ['courseSelect','statsCourse'].forEach(id => {
      const el = $('#'+id);
      if (el) el.addEventListener('change', e => setActiveCourse(e.target.value));
    });
    ['styleSelect','sortSelect','ownedOnly'].forEach(id => $('#'+id).addEventListener('change', renderAll));
    $('#statsStyle').addEventListener('change', renderStatsTable);
    $('#statsSearch').addEventListener('input', renderStatsTable);
    $('#statsSort').addEventListener('change', renderStatsTable);
    $('#dbSearch').addEventListener('input', renderSkillDb);
    $('#dbFilter').addEventListener('change', renderSkillDb);
    $('#ownedSearch').addEventListener('input', renderOwnedList);
    $('#clearOwnedBtn').addEventListener('click', () => { owned = {cards:[], characters:[]}; saveOwned(); renderAll(); renderOwnedList(); });
    $('#exportOwnedBtn').addEventListener('click', async () => {
      await navigator.clipboard.writeText(JSON.stringify(owned, null, 2));
      $('#exportOwnedBtn').textContent = '복사 완료';
      setTimeout(()=>$('#exportOwnedBtn').textContent='보유 JSON 복사', 900);
    });
    renderAll();
}
boot().catch(err => {
  console.error(err);
  document.body.innerHTML = '<main class="wrap"><section class="panel"><h1>데이터 로딩 실패</h1><p>data/site-data.json 파일을 확인해줘.</p></section></main>';
});
