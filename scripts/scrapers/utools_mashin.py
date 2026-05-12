import json
import re
import time
import unicodedata
from pathlib import Path

STYLE_NAMES = ['도주', '선행', '선입', '추입']
STYLE_SLUGS = {
    '도주': 'runner',
    '선행': 'leader',
    '선입': 'betweener',
    '추입': 'chaser',
}
STYLE_BY_SLUG = {v: k for k, v in STYLE_SLUGS.items()}
STYLE_ALIASES = {
    '도주': '도주', 'runner': '도주', '逃げ': '도주',
    '선행': '선행', 'leader': '선행', '先行': '선행',
    '선입': '선입', 'betweener': '선입', '差し': '선입',
    '추입': '추입', 'chaser': '추입', '追込': '추입', '追い込み': '추입',
}


def clean_text(s):
    s = unicodedata.normalize('NFKC', str(s or ''))
    s = s.replace('\u200b', '')
    s = s.replace('◯', '○').replace('〇', '○')
    return re.sub(r'\s+', ' ', s).strip()


def norm_key(s):
    return clean_text(s).replace(' ', '').replace('・', '・').lower()


def parse_number(x):
    x = clean_text(x).replace(',', '')
    if not x or x == '-':
        return ''
    try:
        return float(x)
    except Exception:
        return x


def normalize_style(style):
    key = clean_text(style)
    return STYLE_ALIASES.get(key, STYLE_ALIASES.get(key.lower(), key))


def detect_style_from_url(url):
    m = re.search(r'/effects/(runner|leader|betweener|chaser)/?$', clean_text(url), flags=re.I)
    if not m:
        return ''
    return STYLE_BY_SLUG.get(m.group(1).lower(), '')


def base_url_from_effects_url(url):
    url = clean_text(url).rstrip('/')
    url = re.sub(r'/effects/(runner|leader|betweener|chaser)$', '/effects', url, flags=re.I)
    return url


def course_id_from_url(url, fallback_index=0):
    m = re.search(r'/race/courses/(\d+)/effects', clean_text(url))
    if m:
        return m.group(1)
    m = re.search(r'/race/tracks/(\d+)', clean_text(url))
    if m:
        return m.group(1)
    return f'course-{fallback_index}'


def style_url(base_url, style):
    base_url = base_url_from_effects_url(base_url)
    slug = STYLE_SLUGS.get(style)
    if not slug:
        return base_url
    return f'{base_url}/{slug}'


def make_entry(name, style, url, index):
    url = clean_text(url)
    style = normalize_style(style)
    detected_style = detect_style_from_url(url)
    if style in STYLE_NAMES and not detected_style:
        url = style_url(url, style)
    elif detected_style and style not in STYLE_NAMES:
        style = detected_style
    base_url = base_url_from_effects_url(url)
    cid = course_id_from_url(base_url, index)
    return {
        'courseId': cid,
        'name': clean_text(name) or f'코스 {cid}',
        'style': style,
        'url': url,
        'baseUrl': base_url,
    }


def expand_base_url(name, url, index):
    base_url = base_url_from_effects_url(url)
    cid = course_id_from_url(base_url, index)
    course_name = clean_text(name) or f'코스 {cid}'
    return [make_entry(course_name, style, style_url(base_url, style), index) for style in STYLE_NAMES]


def parse_url_line(line, index):
    line = line.strip()
    if not line or line.startswith('#'):
        return []
    parts = [p.strip() for p in line.split('|')]

    # 코스명|각질|URL
    if len(parts) >= 3:
        name = parts[0]
        style = parts[1]
        url = '|'.join(parts[2:]).strip()
        if normalize_style(style) in STYLE_NAMES:
            return [make_entry(name, style, url, index)]
        return expand_base_url(name, url, index)

    # 코스명|URL
    if len(parts) == 2 and parts[1].lower().startswith('http'):
        name, url = parts
        detected_style = detect_style_from_url(url)
        if detected_style:
            return [make_entry(name, detected_style, url, index)]
        return expand_base_url(name, url, index)

    # URL만
    url = line
    detected_style = detect_style_from_url(url)
    if detected_style:
        return [make_entry('', detected_style, url, index)]
    return expand_base_url('', url, index)


def load_replacement_map(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _translation_lookup(raw_name, skill_name_map=None):
    raw_name = clean_text(raw_name)
    if not raw_name:
        return ''
    skill_name_map = skill_name_map or {}
    if raw_name in skill_name_map:
        return clean_text(skill_name_map[raw_name])
    nk = norm_key(raw_name)
    if nk in skill_name_map:
        return clean_text(skill_name_map[nk])
    # 일부 utools 표기는 앞뒤 공백/전각 차이가 섞인다.
    for candidate in [raw_name.replace(' ', ''), raw_name.replace('・', '･'), raw_name.replace('･', '・')]:
        if candidate in skill_name_map:
            return clean_text(skill_name_map[candidate])
        if norm_key(candidate) in skill_name_map:
            return clean_text(skill_name_map[norm_key(candidate)])
    return raw_name


def _translate_rows(rows, skill_name_map=None):
    out = []
    translated = 0
    for r in rows or []:
        raw = clean_text(r.get('skill') or r.get('skillJp') or '')
        ko = _translation_lookup(raw, skill_name_map)
        if ko and ko != raw:
            translated += 1
        nr = dict(r)
        nr['skillJp'] = raw
        nr['skill'] = ko or raw
        nr['gain'] = parse_number(nr.get('gain'))
        nr['gainPerPt'] = parse_number(nr.get('gainPerPt'))
        nr['procRate'] = clean_text(nr.get('procRate'))
        nr['effectiveRate'] = clean_text(nr.get('effectiveRate'))
        out.append(nr)
    return out, translated


def scrape_visible_mashin(driver, url, wait_seconds=3.0, skill_name_map=None):
    driver.get(url)
    time.sleep(wait_seconds)
    title = clean_text(driver.title)

    js = r'''
        const done = arguments[0];
        (async function() {
          const clean = s => String(s || '').replace(/\s+/g, ' ').trim();
          const result = [];
          const seen = new Set();

          function pushRow(name, effectText, procRate='', effectiveRate='') {
            name = clean(name);
            effectText = clean(effectText);
            if (!name || !effectText) return;
            const m = effectText.match(/(-?\d+(?:\.\d+)?)\s*\[バ\]\s*、\s*(-?\d+(?:\.\d+)?)\s*\[バ\s*\/\s*Pt\]/);
            if (!m) return;
            const pct = effectText.match(/(\d+(?:\.\d+)?)\s*%/);
            const gain = m[1] || '';
            const gainPerPt = m[2] || '';
            if (!effectiveRate && pct) effectiveRate = pct[1] + '%';
            const key = name + '|' + gain + '|' + gainPerPt;
            if (seen.has(key)) return;
            seen.add(key);
            result.push({skill:name, gain, gainPerPt, procRate:clean(procRate), effectiveRate:clean(effectiveRate), effectText});
          }

          // 1차: 예전 utools CSS module 구조. 사용자가 기존에 쓰던 console 코드와 호환.
          try {
            const cards = document.querySelectorAll('[class*="container__rJc7U"]');
            for (const container of cards) {
              const card = container.querySelector('[class*="skillCard__NTfr_"]') || container;
              const nameEl = card.querySelector('[class*="skillCard__name"]');
              const effectEl = card.querySelector('[class*="skillCard__effect"]');
              const name = nameEl ? nameEl.innerText.trim() : '';
              const effectText = effectEl ? effectEl.innerText.trim() : '';
              if (!name || !effectText) continue;
              try {
                card.click();
                await new Promise(r => setTimeout(r, 120));
              } catch (e) {}
              let activation = '', effective = '';
              document.querySelectorAll('[class*="labelLine__Tbk0l"]').forEach(line => {
                const label = line.querySelector('[class*="labelLine__label"]')?.innerText?.trim();
                const value = line.querySelector('[class*="labelLine__body"]')?.innerText?.trim();
                if (label === '発動率') activation = value || '';
                if (label === '有効率') effective = value || '';
              });
              pushRow(name, effectText, activation, effective);
            }
          } catch (e) {}

          // 2차 fallback: 현재 utools는 HTML 본문 텍스트에 이미
          // "스킬명" 다음 줄 "x.xx[バ]、y.yy[バ/Pt]" 형태로 표 데이터를 노출한다.
          // CSS class가 바뀌어도 body.innerText만으로 긁는다.
          if (result.length === 0) {
            const rawText = document.body ? document.body.innerText : '';
            const lines = rawText.split(/\n+/).map(clean).filter(Boolean);
            const badNames = new Set([
              '最大', 'START', 'GOAL', '#', '.', '速度 スキル', '加速 スキル', 'パッシブ スキル', '回復 スキル',
              '白 スキル', '金 スキル', '継承 スキル', '共通 スキル', 'シナリオ スキル',
              '有効スキル', '有効キャラ', '詳細', 'キャラ', '逃げ', '先行', '差し', '追込'
            ]);
            const isBadName = s => {
              if (!s) return true;
              if (badNames.has(s)) return true;
              if (/^[-+]?\d+(?:\.\d+)?(?:\s*(?:m|%))?$/.test(s)) return true;
              if (/^\d{1,3}(?:,\d{3})*$/.test(s)) return true;
              if (/^[序中終]盤$/.test(s)) return true;
              if (/^(直線|コーナー)$/.test(s)) return true;
              if (/バ\s*\/\s*Pt|\[バ\]/.test(s)) return true;
              return false;
            };
            for (let i = 1; i < lines.length; i++) {
              const effect = lines[i];
              if (!/\[バ\]/.test(effect) || !/\[バ\s*\/\s*Pt\]/.test(effect)) continue;
              let j = i - 1;
              while (j >= 0 && isBadName(lines[j])) j--;
              if (j < 0) continue;
              const name = lines[j];
              // 캐릭터명/효과종류 보조 줄은 보통 " / 加速度"처럼 나오므로 제외.
              if (/\s\/\s/.test(name)) continue;
              pushRow(name, effect);
            }
          }
          done(result);
        })();
    '''
    try:
        rows = driver.execute_async_script(js)
    except Exception as e:
        print(f'Utools scrape JS failed: {type(e).__name__}: {e}')
        rows = []

    rows, translated = _translate_rows(rows, skill_name_map=skill_name_map)
    return {'title': title, 'url': url, 'rows': rows, 'translatedRows': translated}


def _existing_course_map(existing_courses):
    out = {}
    for c in existing_courses or []:
        cid = str(c.get('id') or c.get('courseId') or '')
        if cid:
            out[cid] = c
    return out


def build_courses_from_url_file(driver, url_file, existing_courses=None, old_styles=None, skill_name_map=None):
    old_styles = old_styles or {}
    existing_by_id = _existing_course_map(existing_courses)
    entries = []
    with open(url_file, 'r', encoding='utf-8-sig') as f:
        for i, line in enumerate(f, start=1):
            entries.extend(parse_url_line(line, i))

    if not entries:
        if existing_courses:
            return existing_courses, []
        return [{'id': 'default', 'name': '기본 마신표', 'url': '', 'styles': old_styles}], []

    courses = {}
    logs = []
    for entry in entries:
        cid = str(entry['courseId'])
        course = courses.setdefault(cid, {
            'id': cid,
            'name': entry['name'],
            'baseUrl': entry['baseUrl'],
            'styles': {},
        })
        if entry.get('name') and course['name'].startswith('코스 '):
            course['name'] = entry['name']
        scraped = scrape_visible_mashin(driver, entry['url'], skill_name_map=skill_name_map)
        style = entry.get('style') or detect_style_from_url(entry['url']) or '전체'
        rows = scraped['rows']

        # 새 스크래핑이 0건이면 기존 데이터가 있을 때만 보존한다.
        old_course = existing_by_id.get(cid, {})
        old_course_styles = old_course.get('styles', {}) if isinstance(old_course, dict) else {}
        if not rows and old_course_styles.get(style):
            rows = old_course_styles.get(style, [])

        course['styles'][style] = rows
        log_item = {
            'courseId': cid,
            'name': course.get('name'),
            'style': style,
            'url': entry['url'],
            'rows': len(rows),
            'translatedRows': scraped.get('translatedRows', 0),
        }
        logs.append(log_item)
        print(f"Utools {cid} {style}: {len(rows)} rows, translated {log_item['translatedRows']} rows")

    for cid, course in courses.items():
        old_course = existing_by_id.get(cid, {})
        old_course_styles = old_course.get('styles', {}) if isinstance(old_course, dict) else {}
        for st in STYLE_NAMES:
            course['styles'].setdefault(st, old_course_styles.get(st, old_styles.get(st, [])))

    ordered = list(courses.values())
    ordered.sort(key=lambda c: str(c.get('id', '')))
    return ordered, logs


def build_styles_from_url_file(driver, url_file, old_styles=None, skill_name_map=None):
    courses, logs = build_courses_from_url_file(driver, url_file, existing_courses=None, old_styles=old_styles, skill_name_map=skill_name_map)
    styles = courses[0]['styles'] if courses else (old_styles or {})
    return styles, logs
