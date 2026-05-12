import json, os, re, time
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime, timezone

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from scrapers.utools_mashin import build_courses_from_url_file
from scrapers.gametora_sources import scrape_sources_from_skills, clean_text

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / 'data' / 'site-data.json'
LOG_PATH = ROOT / 'data' / 'update-log.json'
URL_FILE = ROOT / 'config' / 'track_urls.txt'
GAMETORA_SKILLS_URL = 'https://gametora.com/ko/umamusume/skills'

def norm(s):
    return re.sub(r'\s+', '', str(s or '').strip()).replace('◯','○').replace('〇','○').lower()

def make_driver():
    options = Options()
    options.add_argument('--window-size=1500,1000')
    if os.environ.get('HEADLESS', '1') != '0':
        options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)



def click_show_all_skills(driver, timeout=12):
    before_count = 0
    try:
        before_count = driver.execute_script("return document.querySelectorAll('[class*=\"table_row_ja\"]').length || 0;") or 0
    except Exception:
        pass
    try:
        clicked = driver.execute_script(
            """
            const visible = el => {
              if (!el) return false;
              const r = el.getBoundingClientRect();
              const st = getComputedStyle(el);
              return r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
            };
            const candidates = [...document.querySelectorAll('a, button, span, div')]
              .filter(visible)
              .map(el => ({ el, text: (el.innerText || el.textContent || '').trim() }))
              .filter(x => x.text === '전체 보기' || x.text.includes('전체 보기'));
            if (!candidates.length) return false;
            candidates.sort((a,b) => a.text.length - b.text.length);
            let target = candidates[0].el;
            const clickable = target.closest('a, button');
            if (clickable) target = clickable;
            target.scrollIntoView({ block:'center', inline:'center' });
            const r = target.getBoundingClientRect();
            const opts = { bubbles:true, cancelable:true, view:window, clientX:r.left+r.width/2, clientY:r.top+r.height/2, button:0 };
            for (const type of ['pointerover','mouseover','pointerdown','mousedown','pointerup','mouseup','click']) {
              target.dispatchEvent(new MouseEvent(type, opts));
            }
            return true;
            """
        )
    except Exception as e:
        print(f"GameTora 전체 보기 클릭 스킵: {type(e).__name__}")
        return False
    if not clicked:
        print(f"GameTora 전체 보기 버튼 없음 또는 이미 전체 표시: rows={before_count}")
        return False
    end = time.time() + timeout
    after_count = before_count
    while time.time() < end:
        try:
            after_count = driver.execute_script("return document.querySelectorAll('[class*=\"table_row_ja\"]').length || 0;") or 0
            body_text = driver.execute_script("return document.body ? document.body.innerText : '';") or ''
            if after_count > before_count or '처음 50개' not in body_text:
                break
        except Exception:
            pass
        time.sleep(0.4)
    print(f"GameTora 전체 보기 클릭: rows {before_count} -> {after_count}")
    return True


def scrape_skill_names(driver):
    driver.get(GAMETORA_SKILLS_URL)
    time.sleep(3)
    click_show_all_skills(driver)
    time.sleep(1)
    js = r'''
        const out = [];
        document.querySelectorAll('[class*="table_row_ja"]').forEach(row => {
          const nameEl = row.querySelector('[class*="table_jpname"]');
          const name = nameEl ? nameEl.innerText.trim() : '';
          if (!name) return;
          // 중요: 여기서 중복 제거하지 않음.
          // GameTora에는 표시명은 같지만 별도 row인 스킬이 있어,
          // occurrence_counter로 1번째/2번째 row를 따로 긁어야 한다.
          out.push(name);
        });
        return out;
    '''
    names = [clean_text(x) for x in driver.execute_script(js) if clean_text(x)]

    counts = Counter(norm(x) for x in names)
    dup_keys = [k for k, v in counts.items() if v > 1]
    if dup_keys:
        first_name_by_key = {}
        for name in names:
            first_name_by_key.setdefault(norm(name), name)
        examples = [f"{first_name_by_key[k]}×{counts[k]}" for k in dup_keys[:20]]
        print(f"GameTora skill rows: {len(names)}, unique names: {len(counts)}, duplicate rows: {len(names) - len(counts)}")
        print("GameTora duplicate examples: " + ", ".join(examples))
    else:
        print(f"GameTora skill rows: {len(names)}, unique names: {len(counts)}, duplicate rows: 0")

    return names

def parse_cards(s):
    if not s: return []
    out=[]
    for part in str(s).split('), '):
        part=part.strip()
        if not part: continue
        if not part.endswith(')'): part += ')'
        out.append(part)
    return out

def parse_list_cell(s):
    return [x.strip() for x in str(s or '').split(', ') if x.strip()]

def parse_card_info(name):
    m = re.match(r'^(.*?)\((SSR|SR|R)(?:,([^,)]*))?(?:,([^,)]*))?\)$', name or '')
    if not m: return {'display': name, 'rarity':'', 'type':'', 'code':''}
    display, rarity, p1, p2 = m.group(1), m.group(2), m.group(3), m.group(4)
    type_, code = '', ''
    if p2 is None:
        if p1 and str(p1).isdigit(): code = str(p1)
        else: type_ = p1 or ''
    else:
        type_, code = p1 or '', p2 or ''
    return {'display': display.strip(), 'rarity': rarity, 'type': type_, 'code': code}

def sorted_list(values):
    return sorted(set(x for x in values if x), key=lambda x:(str(x).lower(), str(x)))

def merge_sources(existing, source_rows, skill_names):
    skills = {}
    card_map = {}
    char_map = {}
    existing_by_key = {norm(s.get('name')): s for s in existing.get('skills', [])}
    for name in skill_names:
        old = existing_by_key.get(norm(name), {})
        skills[norm(name)] = {'name': name, 'status': old.get('status',''), 'meta': old.get('meta',{}), 'cardsNormal': set(old.get('cardsNormal',[])), 'cardsEvent': set(old.get('cardsEvent',[])), 'charsNormal': set(old.get('charsNormal',[])), 'charsEvent': set(old.get('charsEvent',[]))}
    for old in existing.get('skills', []):
        if old.get('name') and norm(old.get('name')) not in skills:
            skills[norm(old.get('name'))] = {'name': old.get('name'), 'status': old.get('status',''), 'meta': old.get('meta',{}), 'cardsNormal': set(old.get('cardsNormal',[])), 'cardsEvent': set(old.get('cardsEvent',[])), 'charsNormal': set(old.get('charsNormal',[])), 'charsEvent': set(old.get('charsEvent',[]))}
    # 같은 표시명으로 여러 row가 있는 스킬이 있으므로,
    # 같은 스킬명 source row가 여러 번 들어와도 매번 초기화하면 안 된다.
    # 업데이트 대상이 된 스킬명은 첫 row에서 한 번만 비우고, 이후 row는 획득처를 합친다.
    cleared_source_keys = set()
    for row in source_rows:
        skill = clean_text(row.get('스킬명'))
        if not skill: continue
        key = norm(skill)
        rec = skills.setdefault(key, {'name': skill, 'status':'', 'meta':{}, 'cardsNormal': set(), 'cardsEvent': set(), 'charsNormal': set(), 'charsEvent': set()})

        if key not in cleared_source_keys:
            rec['cardsNormal'], rec['cardsEvent'], rec['charsNormal'], rec['charsEvent'] = set(), set(), set(), set()
            rec['status'] = ''
            cleared_source_keys.add(key)

        row_status = row.get('상태','') or ''
        if row_status == '성공':
            rec['status'] = '성공'
        elif not rec.get('status'):
            rec['status'] = row_status

        for c in parse_cards(row.get('서포트 카드 (힌트 획득)')): rec['cardsNormal'].add(c)
        for c in parse_cards(row.get('서포트 카드 (이벤트 획득)')): rec['cardsEvent'].add(c)
        for ch in parse_list_cell(row.get('캐릭터')): rec['charsNormal'].add(ch)
        for ch in parse_list_cell(row.get('캐릭터 (이벤트 획득)')): rec['charsEvent'].add(ch)
    for rec in skills.values():
        skill = rec['name']
        for c in rec['cardsNormal']: card_map.setdefault(c, {'normalSkills': set(), 'eventSkills': set()})['normalSkills'].add(skill)
        for c in rec['cardsEvent']: card_map.setdefault(c, {'normalSkills': set(), 'eventSkills': set()})['eventSkills'].add(skill)
        for ch in rec['charsNormal']: char_map.setdefault(ch, {'normalSkills': set(), 'eventSkills': set()})['normalSkills'].add(skill)
        for ch in rec['charsEvent']: char_map.setdefault(ch, {'normalSkills': set(), 'eventSkills': set()})['eventSkills'].add(skill)
    skills_list = [{'name':r['name'], 'status':r.get('status',''), 'meta':r.get('meta',{}), 'cardsNormal':sorted_list(r['cardsNormal']), 'cardsEvent':sorted_list(r['cardsEvent']), 'charsNormal':sorted_list(r['charsNormal']), 'charsEvent':sorted_list(r['charsEvent'])} for r in skills.values()]
    skills_list.sort(key=lambda s:norm(s['name']))
    cards=[]
    for name, rec in card_map.items(): cards.append({'name': name, **parse_card_info(name), 'normalSkills': sorted_list(rec['normalSkills']), 'eventSkills': sorted_list(rec['eventSkills'])})
    cards.sort(key=lambda c: ({'SSR':0,'SR':1,'R':2}.get(c.get('rarity'),9), c.get('display') or '', c['name']))
    characters=[{'name':name, 'normalSkills': sorted_list(rec['normalSkills']), 'eventSkills': sorted_list(rec['eventSkills'])} for name, rec in char_map.items()]
    characters.sort(key=lambda c:c['name'])
    return skills_list, sorted_list([s['name'] for s in skills_list]), cards, characters

def has_real_urls():
    if not URL_FILE.exists(): return False
    for line in URL_FILE.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if line and not line.startswith('#'): return True
    return False

def main():
    existing = json.loads(DATA_PATH.read_text(encoding='utf-8'))
    log = {'startedAt': datetime.now(timezone.utc).isoformat(), 'mode':'auto'}
    driver = make_driver()
    try:
        skill_names = scrape_skill_names(driver)
        skill_name_counts = Counter(norm(x) for x in skill_names)
        log['skillNameCount'] = len(skill_names)
        log['skillNameUniqueCount'] = len(skill_name_counts)
        log['skillNameDuplicateRows'] = len(skill_names) - len(skill_name_counts)
        styles = existing.get('styles', {})
        courses = existing.get('courses') or [{'id':'default','name':'기본 마신표','baseUrl':'','styles':styles}]
        if has_real_urls():
            courses, mashin_logs = build_courses_from_url_file(
                driver,
                URL_FILE,
                existing_courses=courses,
                old_styles=styles,
            )
            styles = courses[0]['styles'] if courses else styles
            log['mashin'] = mashin_logs
        else:
            log['mashin'] = 'config/track_urls.txt has no real URL; kept existing mashin data.'
    finally:
        try: driver.quit()
        except Exception: pass
    if os.environ.get('SKIP_GAMETORA_SOURCES', '0') == '1':
        source_rows = []
        log['sources'] = 'Skipped by SKIP_GAMETORA_SOURCES=1; kept existing source data.'
    else:
        limit = os.environ.get('TEST_LIMIT')
        source_rows = scrape_sources_from_skills(skill_names, work_dir=str(ROOT / 'data' / 'work'), test_limit=int(limit) if limit else None)
        log['sourceRows'] = len(source_rows)
    skills, skill_names_all, cards, characters = merge_sources(existing, source_rows, skill_names)
    data = {**existing, 'updatedAt': datetime.now(timezone.utc).isoformat(), 'sourceFile':'auto-scrape', 'styles': styles, 'courses': courses, 'skills':skills, 'skillNames':skill_names_all, 'cards':cards, 'characters':characters, 'counts':{'skills':len(skill_names_all),'cards':len(cards),'characters':len(characters)}, 'updateLog':log}
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    LOG_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ok':True, 'counts':data['counts']}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
