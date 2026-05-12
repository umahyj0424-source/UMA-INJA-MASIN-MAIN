import re, time

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
    return re.sub(r'\s+', ' ', str(s or '')).strip()

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
        # 각질 자리에 전체/auto 등을 적으면 네 각질 전체 확장
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

def scrape_visible_mashin(driver, url, wait_seconds=2.2):
    driver.get(url)
    time.sleep(wait_seconds)
    title = clean_text(driver.title)
    js = r'''
        const done = arguments[0];
        (async function() {
          const cards = document.querySelectorAll('[class*="container__rJc7U"]');
          const result = [];
          const seen = new Set();
          for (const container of cards) {
            const card = container.querySelector('[class*="skillCard__NTfr_"]');
            if (!card) continue;
            const nameEl = card.querySelector('[class*="skillCard__name"]');
            const name = nameEl ? nameEl.innerText.trim() : '';
            const effectEl = card.querySelector('[class*="skillCard__effect"]');
            if (!name || !effectEl) continue;
            const numbers = effectEl.innerText.match(/[\d]+\.[\d]+/g) || [];
            const gain = numbers[0] || '';
            const gainPerPt = numbers[1] || '';
            const key = name + gain;
            if (seen.has(key)) continue;
            seen.add(key);
            card.click();
            await new Promise(r => setTimeout(r, 250));
            let procRate = '', effectiveRate = '';
            document.querySelectorAll('[class*="labelLine__Tbk0l"]').forEach(line => {
              const label = line.querySelector('[class*="labelLine__label"]')?.innerText?.trim();
              const value = line.querySelector('[class*="labelLine__body"]')?.innerText?.trim();
              if (label === '発動率') procRate = value || '';
              if (label === '有効率') effectiveRate = value || '';
            });
            result.push({skill:name, gain, gainPerPt, procRate, effectiveRate});
          }
          done(result);
        })();
    '''
    rows = driver.execute_async_script(js)
    for r in rows:
        r['gain'] = parse_number(r.get('gain'))
        r['gainPerPt'] = parse_number(r.get('gainPerPt'))
        r['procRate'] = clean_text(r.get('procRate'))
        r['effectiveRate'] = clean_text(r.get('effectiveRate'))
    return {'title': title, 'url': url, 'rows': rows}

def _existing_course_map(existing_courses):
    out = {}
    for c in existing_courses or []:
        cid = str(c.get('id') or c.get('courseId') or '')
        if cid:
            out[cid] = c
    return out

def build_courses_from_url_file(driver, url_file, existing_courses=None, old_styles=None):
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
        # 같은 코스가 여러 줄에 있으면 첫 이름을 유지하되, 명시 이름이 있으면 보강
        if entry.get('name') and course['name'].startswith('코스 '):
            course['name'] = entry['name']
        scraped = scrape_visible_mashin(driver, entry['url'])
        style = entry.get('style') or detect_style_from_url(entry['url']) or '전체'
        course['styles'][style] = scraped['rows']
        logs.append({
            'courseId': cid,
            'name': course.get('name'),
            'style': style,
            'url': entry['url'],
            'rows': len(scraped['rows']),
        })

    # 누락된 각질은 기존 데이터가 있으면 보존한다.
    for cid, course in courses.items():
        old_course = existing_by_id.get(cid, {})
        old_course_styles = old_course.get('styles', {}) if isinstance(old_course, dict) else {}
        for st in STYLE_NAMES:
            course['styles'].setdefault(st, old_course_styles.get(st, old_styles.get(st, [])))

    ordered = list(courses.values())
    ordered.sort(key=lambda c: str(c.get('id', '')))
    return ordered, logs

def build_styles_from_url_file(driver, url_file, old_styles=None):
    courses, logs = build_courses_from_url_file(driver, url_file, existing_courses=None, old_styles=old_styles)
    styles = courses[0]['styles'] if courses else (old_styles or {})
    return styles, logs
