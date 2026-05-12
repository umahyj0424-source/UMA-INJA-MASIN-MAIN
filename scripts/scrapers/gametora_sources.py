# pip install selenium webdriver-manager pandas openpyxl requests beautifulsoup4



import os

import re

import json

import time

import unicodedata

from collections import defaultdict, Counter



import pandas as pd

import requests

from bs4 import BeautifulSoup



from selenium import webdriver

from selenium.webdriver.chrome.service import Service

from selenium.webdriver.chrome.options import Options

from selenium.webdriver.common.by import By

from selenium.webdriver.common.keys import Keys

from selenium.webdriver.common.action_chains import ActionChains

from selenium.webdriver.support.ui import WebDriverWait

from selenium.common.exceptions import (

    TimeoutException,

    StaleElementReferenceException,

    ElementClickInterceptedException,

)

from webdriver_manager.chrome import ChromeDriverManager





URL_SKILLS = "https://gametora.com/ko/umamusume/skills"

GAMETORA_BASE = "https://gametora.com"

INVEN_BASE = "https://uma.inven.co.kr/db/scard/"



EXPECTED_SKILL_COUNT = 1438



INCLUDE_SUPPORT_ID = True

PRESERVE_DUPLICATES = True



# 테스트: 20

# 전체 실행: None

TEST_LIMIT = None



OUTPUT_FILENAME = "uma_skill_sources_v11_morefix.xlsx"

CACHE_FILENAME = "uma_support_meta_cache.json"



SECTION_LABELS = [

    "캐릭터:",

    "캐릭터 (이벤트 획득):",

    "서포트 카드 (힌트 획득):",

    "서포트 카드 (이벤트 획득):",

]



COLUMN_BY_LABEL = {

    "캐릭터:": "캐릭터",

    "캐릭터 (이벤트 획득):": "캐릭터 (이벤트 획득)",

    "서포트 카드 (힌트 획득):": "서포트 카드 (힌트 획득)",

    "서포트 카드 (이벤트 획득):": "서포트 카드 (이벤트 획득)",

}





def clean_text(s: str) -> str:

    if s is None:

        return ""

    s = unicodedata.normalize("NFKC", str(s))

    s = s.replace("\u200b", "")

    s = s.replace("◯", "○").replace("〇", "○")

    s = re.sub(r"\s+", " ", s)

    return s.strip()





def skill_base_name(name: str) -> str:

    name = clean_text(name)

    return re.sub(r"[◎○〇◯×]", "", name).strip()





def xpath_literal(s: str) -> str:

    if "'" not in s:

        return f"'{s}'"

    if '"' not in s:

        return f'"{s}"'

    parts = s.split("'")

    return "concat(" + ", \"'\", ".join([f"'{p}'" for p in parts]) + ")"





def is_displayed_safe(el) -> bool:

    try:

        return el.is_displayed()

    except Exception:

        return False





def safe_text(el) -> str:

    try:

        return clean_text(el.text)

    except Exception:

        return ""





def dedupe_preserve_order(items):

    seen = set()

    out = []

    for x in items:

        if x and x not in seen:

            seen.add(x)

            out.append(x)

    return out





def smart_title_token(token: str) -> str:

    if not token:

        return token



    low = token.lower()



    if low.startswith("mc") and len(low) > 2:

        return "Mc" + low[2:].capitalize()



    if low in {"tm", "cb", "sr", "ssr", "r"}:

        return low.upper()



    return low.capitalize()





def slug_to_pretty_name(slug: str) -> str:

    slug = clean_text(slug).strip("-")

    if not slug:

        return ""



    return " ".join(

        smart_title_token(tok)

        for tok in slug.split("-")

        if tok

    )





def extract_skill_names(file_path: str):

    """

    UMA3.txt 구조:

    스킬명

    시계(우) 방향◎

    시계(우) 방향○

    ...

    """

    if not os.path.exists(file_path):

        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")



    with open(file_path, "r", encoding="utf-8-sig") as f:

        raw_lines = [clean_text(line) for line in f.readlines()]



    skills = []



    for line in raw_lines:

        if not line:

            continue

        if line == "스킬명":

            continue

        if line in ["스킬 목록", "필터 재설정", "설정"]:

            continue

        if "검색 결과" in line and "찾았습니다" in line:

            continue



        skills.append(line)



    counts = Counter(skills)

    dup_names = {k: v for k, v in counts.items() if v > 1}



    print(f"파일에서 읽은 스킬 수(원본): {len(skills)}개")



    if dup_names:

        print(f"중복 스킬명 종류: {len(dup_names)}개")

        print("중복 예시:", list(dup_names.items())[:10])



    if not PRESERVE_DUPLICATES:

        skills = dedupe_preserve_order(skills)

        print(f"중복 제거 후 스킬 수: {len(skills)}개")



    if len(skills) != EXPECTED_SKILL_COUNT:

        print(

            f"경고: 현재 읽은 스킬 수는 {len(skills)}개입니다. "

            f"사이트 기준 {EXPECTED_SKILL_COUNT}개와 다릅니다."

        )



    return skills





def make_driver():

    options = Options()

    options.add_argument("--window-size=1500,1000")
    if os.environ.get("HEADLESS", "1") != "0":
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    options.add_argument("--disable-blink-features=AutomationControlled")

    options.add_argument("--disable-popup-blocking")

    options.add_argument("--disable-notifications")

    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    options.add_experimental_option("useAutomationExtension", False)



    driver = webdriver.Chrome(

        service=Service(ChromeDriverManager().install()),

        options=options,

    )

    driver.set_page_load_timeout(60)



    return driver





def wait_page_ready(driver, timeout=20):

    WebDriverWait(driver, timeout).until(

        lambda d: d.execute_script("return document.readyState") == "complete"

    )








def click_show_all_skills(driver, wait=None, timeout=12):
    """GameTora 스킬 목록 페이지에서 [전체 보기]를 눌러 50개 제한을 해제한다.

    - 이미 전체 표시 상태면 조용히 넘어간다.
    - 실패해도 스크래핑 전체를 중단하지 않고 기존 50개 표시 상태로 계속 진행한다.
    """
    before_count = 0
    try:
        before_count = driver.execute_script("return document.querySelectorAll('[class*=\"table_row_ja\"]').length || 0;") or 0
    except Exception:
        before_count = 0

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
            if (!candidates.length) return { clicked:false, reason:'not-found' };
            candidates.sort((a, b) => a.text.length - b.text.length);
            let target = candidates[0].el;
            const clickable = target.closest('a, button');
            if (clickable) target = clickable;
            target.scrollIntoView({ block:'center', inline:'center' });
            const r = target.getBoundingClientRect();
            const opts = { bubbles:true, cancelable:true, view:window, clientX:r.left + r.width/2, clientY:r.top + r.height/2, button:0 };
            for (const type of ['pointerover','mouseover','pointerdown','mousedown','pointerup','mouseup','click']) {
              target.dispatchEvent(new MouseEvent(type, opts));
            }
            return { clicked:true, text:candidates[0].text };
            """
        )
    except Exception as e:
        print(f"GameTora 전체 보기 클릭 스킵: {type(e).__name__}")
        return False

    if not clicked or not clicked.get('clicked'):
        print(f"GameTora 전체 보기 버튼 없음 또는 이미 전체 표시: rows={before_count}")
        return False

    # rows가 늘어나거나, 표시 문구가 사라질 때까지 잠깐 대기
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


def find_search_input(driver, wait):

    selectors = [

        "input.skill-search-input",

        ".skill-search input",

        "input[placeholder*='스킬']",

        "input[placeholder*='검색']",

    ]



    def _locate(_):

        for selector in selectors:

            els = driver.find_elements(By.CSS_SELECTOR, selector)

            for el in els:

                if is_displayed_safe(el):

                    return el

        return False



    return wait.until(_locate)





def set_react_input(driver, input_el, value, wait):

    driver.execute_script(

        """

        const input = arguments[0];

        const value = arguments[1];



        input.focus();



        const setter = Object.getOwnPropertyDescriptor(

            window.HTMLInputElement.prototype,

            'value'

        ).set;



        setter.call(input, '');

        input.dispatchEvent(new Event('input', { bubbles: true }));

        input.dispatchEvent(new Event('change', { bubbles: true }));



        setter.call(input, value);

        input.dispatchEvent(new Event('input', { bubbles: true }));

        input.dispatchEvent(new Event('change', { bubbles: true }));

        input.dispatchEvent(new KeyboardEvent('keyup', {

            bubbles: true,

            key: 'Enter',

            code: 'Enter'

        }));

        """,

        input_el,

        value,

    )



    wait.until(lambda d: clean_text(input_el.get_attribute("value")) == clean_text(value))





def close_detail_panel_if_possible(driver):

    try:

        body = driver.find_element(By.TAG_NAME, "body")

        body.send_keys(Keys.ESCAPE)

        time.sleep(0.12)

    except Exception:

        pass





def _row_candidates_from_table(driver, skill_name):

    rows = driver.find_elements(By.CSS_SELECTOR, "tr.skill-list-row")

    matches = []

    target = clean_text(skill_name)



    for row in rows:

        if not is_displayed_safe(row):

            continue

        try:

            name_el = row.find_element(By.CSS_SELECTOR, ".skill-list-name")

            if clean_text(name_el.text) == target:

                matches.append(row)

        except Exception:

            continue



    return matches





def _row_candidates_generic(driver, skill_name):

    target = clean_text(skill_name)



    exact_nodes = driver.find_elements(

        By.XPATH,

        f"//*[normalize-space()={xpath_literal(target)}]"

    )



    matches = []

    seen = set()



    for node in exact_nodes:

        if not is_displayed_safe(node):

            continue



        cur = node



        for _ in range(10):

            try:

                text = safe_text(cur)



                if target in text and "더 보기" in text:

                    key = cur.id

                    if key not in seen:

                        seen.add(key)

                        matches.append(cur)

                    break



                cur = cur.find_element(By.XPATH, "./..")

            except Exception:

                break



    return matches





def find_skill_row(driver, wait, skill_name, occurrence=0):

    target = clean_text(skill_name)



    def _locate(_):

        matches = _row_candidates_from_table(driver, target)



        if not matches:

            matches = _row_candidates_generic(driver, target)



        if matches:

            if occurrence < len(matches):

                return matches[occurrence]

            return matches[0]



        return False



    return wait.until(_locate)





def get_row_description(row, skill_name):

    try:

        lines = [

            clean_text(x)

            for x in row.text.splitlines()

            if clean_text(x)

        ]

    except Exception:

        return ""



    lines = [

        x for x in lines

        if x != clean_text(skill_name)

        and "더 보기" not in x

        and "검색 결과" not in x

    ]



    lines.sort(key=len, reverse=True)



    return lines[0] if lines else ""





def detail_panel_is_open(driver, skill_name=None):

    """

    [더 보기] 클릭 후 tippy 상세 패널이 열렸는지 확인.

    """

    skill_name = clean_text(skill_name or "")

    base = skill_base_name(skill_name)



    return driver.execute_script(

        """

        const skillName = arguments[0] || "";

        const base = arguments[1] || "";



        const visible = el => {

            if (!el) return false;



            const r = el.getBoundingClientRect();

            const st = getComputedStyle(el);



            return (

                r.width > 80 &&

                r.height > 80 &&

                st.display !== "none" &&

                st.visibility !== "hidden" &&

                st.opacity !== "0"

            );

        };



        const panels = [

            ...document.querySelectorAll("[data-tippy-root], .tippy-box, .tippy-content, div")

        ].filter(el => {

            if (!visible(el)) return false;



            const text = el.innerText || "";



            if (!text.includes("게임내 설명")) return false;



            if (!(text.includes("캐릭터") || text.includes("서포트 카드"))) {

                return false;

            }



            if (skillName && text.includes(skillName)) return true;

            if (base && text.includes(base)) return true;



            return true;

        });



        return panels.length > 0;

        """,

        skill_name,

        base,

    )





def get_more_button_from_row(driver, row):

    """

    핵심 수정:

    파란색 [더 보기] 텍스트를 가장 우선적으로 찾는다.

    기존처럼 class='more'류를 먼저 잡으면 엉뚱한 부모 div를 클릭할 수 있어서,

    실제 화면 오른쪽의 '더 보기' 텍스트 요소를 스코어링해서 선택한다.

    """

    return driver.execute_script(

        """

        const row = arguments[0];



        if (!row) return null;



        const visible = el => {

            if (!el) return false;



            const r = el.getBoundingClientRect();

            const st = getComputedStyle(el);



            return (

                r.width > 0 &&

                r.height > 0 &&

                st.display !== "none" &&

                st.visibility !== "hidden" &&

                st.opacity !== "0"

            );

        };



        const rowRect = row.getBoundingClientRect();



        const candidates = [...row.querySelectorAll("a, button, span, div")]

            .filter(el => {

                if (!visible(el)) return false;



                const text = (el.innerText || el.textContent || "").trim();

                const cls = String(el.className || "");



                return (

                    text === "더 보기" ||

                    text.includes("더 보기") ||

                    cls.includes("skill-more") ||

                    cls.includes("more") ||

                    cls.includes("More")

                );

            })

            .map(el => {

                const r = el.getBoundingClientRect();

                const text = (el.innerText || el.textContent || "").trim();

                const tag = (el.tagName || "").toLowerCase();

                const cls = String(el.className || "");



                let score = 0;



                if (text === "더 보기") score += 1000;

                if (text.includes("더 보기")) score += 500;

                if (tag === "a" || tag === "button") score += 200;

                if (cls.includes("skill-more")) score += 150;

                if (cls.includes("more") || cls.includes("More")) score += 80;



                // 화면상 오른쪽에 있을수록 실제 파란 [더 보기]일 가능성이 큼

                score += Math.max(0, r.left - rowRect.left) / 5;



                // 너무 큰 부모 div는 감점

                const area = r.width * r.height;

                if (area > 50000) score -= 500;

                if (area > 120000) score -= 1000;



                return { el, score, area, left: r.left };

            });



        candidates.sort((a, b) => {

            if (b.score !== a.score) return b.score - a.score;

            return a.area - b.area;

        });



        if (!candidates.length) return null;



        let target = candidates[0].el;



        // 텍스트 span이 잡힌 경우, 실제 클릭 가능한 a/button 부모가 있으면 그쪽을 클릭

        const clickableParent = target.closest("a, button");



        if (clickableParent && row.contains(clickableParent)) {

            return clickableParent;

        }



        return target;

        """,

        row,

    )





def force_mouse_click(driver, el):

    """

    React/tippy 이벤트 대응용 강제 클릭.

    """

    return driver.execute_script(

        """

        const el = arguments[0];



        if (!el) return false;



        el.scrollIntoView({ block: "center", inline: "center" });



        const rect = el.getBoundingClientRect();

        const x = rect.left + rect.width / 2;

        const y = rect.top + rect.height / 2;



        const opts = {

            bubbles: true,

            cancelable: true,

            view: window,

            clientX: x,

            clientY: y,

            button: 0

        };



        for (const type of ["pointerover", "mouseover", "pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {

            el.dispatchEvent(new MouseEvent(type, opts));

        }



        return true;

        """,

        el,

    )





def click_row_right_side(driver, row):

    """

    최후 fallback:

    행의 오른쪽 끝, 즉 파란 [더 보기]가 있는 위치를 좌표 클릭.

    """

    try:

        driver.execute_script(

            "arguments[0].scrollIntoView({ block: 'center', inline: 'center' });",

            row,

        )

        time.sleep(0.1)



        size = row.size

        x = max(5, size["width"] - 45)

        y = max(5, size["height"] / 2)



        ActionChains(driver).move_to_element_with_offset(row, x, y).click().perform()

        return True

    except Exception:

        return False








def get_more_button_near_row(driver, row):
    """현재 row 내부에 [더 보기]가 없을 때, 같은 y좌표 근처의 전역 [더 보기]를 찾는다."""
    return driver.execute_script(
        """
        const row = arguments[0];
        if (!row) return null;
        const visible = el => {
          if (!el) return false;
          const r = el.getBoundingClientRect();
          const st = getComputedStyle(el);
          return r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
        };
        const rr = row.getBoundingClientRect();
        const rowY = rr.top + rr.height / 2;
        const candidates = [...document.querySelectorAll('a, button, span, div')]
          .filter(visible)
          .filter(el => {
            const text = (el.innerText || el.textContent || '').trim();
            return text === '더 보기' || text.includes('더 보기');
          })
          .map(el => {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || el.textContent || '').trim();
            const tag = (el.tagName || '').toLowerCase();
            const y = r.top + r.height / 2;
            let score = 0;
            score -= Math.abs(y - rowY) * 10;
            if (text === '더 보기') score += 1000;
            if (tag === 'a' || tag === 'button') score += 300;
            if (r.left > rr.left) score += 100;
            score += Math.max(0, r.left) / 10;
            const area = r.width * r.height;
            if (area > 50000) score -= 1000;
            return { el, score, dy: Math.abs(y - rowY), area };
          })
          .filter(x => x.dy <= Math.max(35, rr.height * 1.4));
        candidates.sort((a,b) => b.score - a.score || a.area - b.area);
        if (!candidates.length) return null;
        let target = candidates[0].el;
        const clickable = target.closest('a, button');
        if (clickable) return clickable;
        return target;
        """,
        row,
    )


def click_global_right_side(driver, row):
    """row 폭이 실제 화면 전체를 덮지 않을 때, viewport 오른쪽 같은 높이를 직접 클릭한다."""
    try:
        driver.execute_script("arguments[0].scrollIntoView({ block: 'center', inline: 'center' });", row)
        time.sleep(0.1)
        return bool(driver.execute_script(
            """
            const row = arguments[0];
            const rr = row.getBoundingClientRect();
            const x = Math.max(10, window.innerWidth - 45);
            const y = rr.top + rr.height / 2;
            const el = document.elementFromPoint(x, y);
            if (!el) return false;
            const target = el.closest('a, button, span, div') || el;
            const r = target.getBoundingClientRect();
            const opts = { bubbles:true, cancelable:true, view:window, clientX:x, clientY:y, button:0 };
            for (const type of ['pointerover','mouseover','pointerdown','mousedown','pointerup','mouseup','click']) {
              target.dispatchEvent(new MouseEvent(type, opts));
            }
            return true;
            """,
            row,
        ))
    except Exception:
        return False


def click_more(driver, row, wait=None, skill_name=None):

    """

    수정된 [더 보기] 클릭 함수.



    기존 함수와 같은 역할이지만 클릭 성공률을 높이기 위해:

    1. 실제 '더 보기' 텍스트 요소 탐색

    2. ActionChains 클릭

    3. WebElement.click()

    4. JS MouseEvent 강제 클릭

    5. 행 오른쪽 좌표 클릭

    순서로 재시도한다.

    """

    target = get_more_button_from_row(driver, row)
    if target is None:
        target = get_more_button_near_row(driver, row)

    errors = []



    if target is not None:

        # 1차: 실제 마우스 이동 + 클릭

        try:

            driver.execute_script(

                "arguments[0].scrollIntoView({ block: 'center', inline: 'center' });",

                target,

            )

            time.sleep(0.12)

            ActionChains(driver).move_to_element(target).pause(0.08).click().perform()

            time.sleep(0.35)



            if detail_panel_is_open(driver, skill_name):

                return



        except Exception as e:

            errors.append(f"ActionChains: {type(e).__name__}")



        # 2차: WebElement.click()

        try:

            target.click()

            time.sleep(0.35)



            if detail_panel_is_open(driver, skill_name):

                return



        except Exception as e:

            errors.append(f"element.click: {type(e).__name__}")



        # 3차: JS mouse event 강제 발생

        try:

            force_mouse_click(driver, target)

            time.sleep(0.35)



            if detail_panel_is_open(driver, skill_name):

                return



        except Exception as e:

            errors.append(f"force_mouse_click: {type(e).__name__}")



    # 4차: 행 오른쪽 끝 좌표 클릭

    if click_row_right_side(driver, row):

        time.sleep(0.45)

        if detail_panel_is_open(driver, skill_name):

            return

    # 5차: viewport 오른쪽 같은 높이를 전역 클릭

    if click_global_right_side(driver, row):

        time.sleep(0.45)

        if detail_panel_is_open(driver, skill_name):

            return

    error_text = " / ".join(errors) if errors else "no target"

    raise RuntimeError(f"더 보기 클릭 실패: {error_text}")





def find_detail_panel(driver, wait, skill_name, row_desc=""):

    base = skill_base_name(skill_name)

    desc_key = clean_text(row_desc)[:18]



    def _locate(_):

        candidates = driver.find_elements(

            By.XPATH,

            "//*[contains(., '게임내 설명') and (contains(., '캐릭터') or contains(., '서포트 카드'))]"

        )



        best = None

        best_score = -1



        for el in candidates:

            try:

                if not is_displayed_safe(el):

                    continue



                rect = el.rect



                if rect["width"] < 180 or rect["height"] < 120:

                    continue



                text = safe_text(el)



                if "게임내 설명" not in text:

                    continue



                if "캐릭터" not in text and "서포트 카드" not in text:

                    continue



                score = 0



                if base and base in text:

                    score += 40



                if desc_key and desc_key in text:

                    score += 50



                # 현재 패널은 a href가 아니라 img src 기반인 경우가 많음

                try:

                    score += len(el.find_elements(By.XPATH, ".//img[contains(@src, '/supports/')]")) * 3

                    score += len(el.find_elements(By.XPATH, ".//img[contains(@src, '/characters/')]")) * 2

                    score += len(el.find_elements(By.XPATH, ".//img[contains(@src, 'support_card_s_')]")) * 3

                    score += len(el.find_elements(By.XPATH, ".//img[contains(@src, 'chara_stand_')]")) * 2

                except Exception:

                    pass



                # 오른쪽 tippy 패널일 가능성

                if rect["x"] > 300:

                    score += 20



                if 220 <= rect["width"] <= 560:

                    score += 15



                if score > best_score:

                    best_score = score

                    best = el



            except StaleElementReferenceException:

                continue

            except Exception:

                continue



        return best if best is not None else False



    return wait.until(_locate)





def make_session():

    session = requests.Session()

    session.headers.update({

        "User-Agent": (

            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "

            "AppleWebKit/537.36 (KHTML, like Gecko) "

            "Chrome/136.0 Safari/537.36"

        ),

        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",

    })

    return session





def load_cache(cache_path):

    if not os.path.exists(cache_path):

        return {}



    try:

        with open(cache_path, "r", encoding="utf-8") as f:

            data = json.load(f)



        return data if isinstance(data, dict) else {}

    except Exception:

        return {}





def save_cache(cache, cache_path):

    try:

        with open(cache_path, "w", encoding="utf-8") as f:

            json.dump(cache, f, ensure_ascii=False, indent=2)

    except Exception:

        pass





def fetch_html(session, url, timeout=15):

    resp = session.get(url, timeout=timeout)

    resp.raise_for_status()

    resp.encoding = resp.apparent_encoding or resp.encoding

    return resp.text





def normalize_support_type(raw: str) -> str:

    raw = clean_text(raw)

    low = raw.lower()



    checks = [

        ("스피드", ["스피드", "speed", "spd", "スピード"]),

        ("스태미나", ["스태미나", "스태미너", "stamina", "sta", "スタミナ"]),

        ("파워", ["파워", "power", "pow", "パワー"]),

        ("근성", ["근성", "guts", "gut", "根性"]),

        ("지능", ["지능", "wisdom", "wit", "intelligence", "smart", "賢さ"]),

        ("친구", ["친구", "friend", "友人"]),

        ("그룹", ["그룹", "group", "グループ"]),

    ]



    for ko, keys in checks:

        for key in keys:

            if key.lower() in low:

                return ko



    return ""





def detect_support_type_from_text(raw: str) -> str:

    raw = unicodedata.normalize("NFKC", raw or "")



    # 제목에 (SSR, 파워), (SSR, Power) 같은 형태가 있으면 우선

    m = re.search(r"\((SSR|SR|R)\s*,\s*([^)]+)\)", raw, flags=re.I)

    if m:

        t = normalize_support_type(m.group(2))

        if t:

            return t



    patterns = [

        ("스피드", [

            r"스피드 상승량이 증가",

            r"초기 스피드 증가",

            r"스피드 보너스",

            r"Speed Bonus",

            r"Increases Speed gain",

            r"Initial Speed",

        ]),

        ("스태미나", [

            r"스태미나 상승량이 증가",

            r"스태미너 상승량이 증가",

            r"초기 스태미나 증가",

            r"초기 스태미너 증가",

            r"스태미나 보너스",

            r"스태미너 보너스",

            r"Stamina Bonus",

            r"Increases Stamina gain",

            r"Initial Stamina",

        ]),

        ("파워", [

            r"파워 상승량이 증가",

            r"초기 파워 증가",

            r"파워 보너스",

            r"Power Bonus",

            r"Increases Power gain",

            r"Initial Power",

        ]),

        ("근성", [

            r"근성 상승량이 증가",

            r"초기 근성 증가",

            r"근성 보너스",

            r"Guts Bonus",

            r"Increases Guts gain",

            r"Initial Guts",

        ]),

        ("지능", [

            r"지능 상승량이 증가",

            r"초기 지능 증가",

            r"지능 보너스",

            r"지능 우정 회복량 증가",

            r"Wit Bonus",

            r"Increases Wit gain",

            r"Initial Wit",

        ]),

        ("친구", [

            r"\(SSR,\s*친구\)",

            r"\(SR,\s*친구\)",

            r"\(R,\s*친구\)",

            r"\(SSR,\s*Friend\)",

            r"\(SR,\s*Friend\)",

            r"\(R,\s*Friend\)",

            r"친구 카드",

            r"Friend Card",

        ]),

        ("그룹", [

            r"\(SSR,\s*그룹\)",

            r"\(SR,\s*그룹\)",

            r"\(R,\s*그룹\)",

            r"\(SSR,\s*Group\)",

            r"\(SR,\s*Group\)",

            r"\(R,\s*Group\)",

            r"그룹 카드",

            r"Group Card",

        ]),

    ]



    for support_type, pats in patterns:

        for pat in pats:

            if re.search(pat, raw, flags=re.I):

                return support_type



    return ""





def infer_rarity_from_id(support_id: str) -> str:

    support_id = clean_text(support_id)



    if support_id.startswith("1"):

        return "R"

    if support_id.startswith("2"):

        return "SR"

    if support_id.startswith("3"):

        return "SSR"



    return ""





def parse_support_src(src: str):

    src = clean_text(src)



    m = re.search(r"support_card_s_(\d+)\.png", src)



    if not m:

        m = re.search(r"support_card_(\d+)\.png", src)



    if not m:

        return ""



    return m.group(1)





def parse_support_href(href: str):

    href = clean_text(href)



    m = re.search(r"/supports/(\d+)(?:-([^/?#]+))?", href)



    if not m:

        return "", ""



    return m.group(1), clean_text(m.group(2) or "")





def parse_support_meta_from_html(html: str, support_id: str, slug: str):

    soup = BeautifulSoup(html, "html.parser")



    title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")

    h1 = clean_text(soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "")

    text = clean_text(soup.get_text("\n", strip=True))

    raw = "\n".join([title, h1, text[:5000], html[:3000]])



    meta = {

        "support_id": support_id,

        "name": "",

        "rarity": infer_rarity_from_id(support_id),

        "type": "",

    }



    patterns = [

        r"(.+?)\s*\((SSR|SR|R)(?:\s*,\s*([^)]+))?\)\s*서포트 카드",

        r"(.+?)\s*\((SSR|SR|R)(?:\s*,\s*([^)]+))?\)\s*Support Card",

    ]



    for pat in patterns:

        m = re.search(pat, raw, flags=re.I)

        if m:

            meta["name"] = clean_text(m.group(1))

            meta["rarity"] = clean_text(m.group(2)).upper()



            if m.group(3):

                meta["type"] = normalize_support_type(m.group(3))



            break



    if not meta["name"]:

        meta["name"] = slug_to_pretty_name(slug)



    if not meta["type"]:

        meta["type"] = detect_support_type_from_text(raw)



    return meta





def resolve_support_meta(session, support_id, name_hint, cache):

    support_id = clean_text(support_id)

    name_hint = clean_text(name_hint)



    if not support_id:

        return {

            "support_id": "",

            "name": name_hint,

            "rarity": "",

            "type": "",

        }



    if support_id in cache:

        meta = cache[support_id]



        # 기존 캐시에 이름이 없을 때만 보강

        if name_hint and not meta.get("name"):

            meta["name"] = name_hint



        return meta



    meta = {

        "support_id": support_id,

        "name": name_hint or support_id,

        "rarity": infer_rarity_from_id(support_id),

        "type": "",

    }



    # slug를 모르는 경우도 있으므로 ID만으로 먼저 요청

    urls = [

        f"{GAMETORA_BASE}/ko/umamusume/supports/{support_id}",

        f"{GAMETORA_BASE}/umamusume/supports/{support_id}",

        f"{INVEN_BASE}{support_id}",

    ]



    for url in urls:

        try:

            html = fetch_html(session, url, timeout=12)

            parsed = parse_support_meta_from_html(html, support_id, "")



            if parsed.get("name"):

                meta["name"] = parsed["name"]



            if parsed.get("rarity"):

                meta["rarity"] = parsed["rarity"]



            if parsed.get("type"):

                meta["type"] = parsed["type"]



            if meta["name"] and meta["type"]:

                break



        except Exception:

            continue



    if not meta.get("name"):

        meta["name"] = name_hint or support_id



    if not meta.get("rarity"):

        meta["rarity"] = infer_rarity_from_id(support_id)



    cache[support_id] = meta



    return meta





def format_support_display(meta):

    name = clean_text(meta.get("name", ""))

    rarity = clean_text(meta.get("rarity", ""))

    support_type = clean_text(meta.get("type", ""))

    support_id = clean_text(meta.get("support_id", ""))



    if not name:

        name = support_id or "Unknown"



    tags = []



    if rarity:

        tags.append(rarity)



    if support_type:

        tags.append(support_type)



    if INCLUDE_SUPPORT_ID and support_id:

        tags.append(support_id)



    if tags:

        return f"{name}({','.join(tags)})"



    return name





def collect_section_img_infos(driver, panel, label):

    """

    상세 패널 내부에서 특정 라벨 구역의 img를 수집한다.



    핵심:

    - GameTora 패널은 a[href]가 아니라 img src 기반인 경우가 많다.

    - 서포트 카드: /images/umamusume/supports/support_card_s_30004.png

    - 캐릭터: /images/umamusume/characters/thumb/chara_stand_...

    - 기존 방식처럼 '가장 작은 div'를 잡으면 <b>라벨</b>만 잡혀서 img가 0개가 된다.

    """

    return driver.execute_script(

        """

        const panel = arguments[0];

        const targetLabel = arguments[1];



        const norm = s => (s || "").replace(/\\s+/g, " ").trim();



        if (!panel) return [];



        const visible = el => {

            if (!el) return false;



            const r = el.getBoundingClientRect();

            const st = getComputedStyle(el);



            return (

                r.width > 0 &&

                r.height > 0 &&

                st.display !== "none" &&

                st.visibility !== "hidden" &&

                st.opacity !== "0"

            );

        };



        const isSupport = targetLabel.includes("서포트 카드");

        const isCharacter = targetLabel.includes("캐릭터");



        function imgMatches(img) {

            const src = img.getAttribute("src") || "";



            if (isSupport) {

                return src.includes("/supports/") || src.includes("support_card_s_");

            }



            if (isCharacter) {

                return src.includes("/characters/") || src.includes("chara_stand_");

            }



            return false;

        }



        function readImg(img) {

            return {

                src: img.getAttribute("src") || "",

                alt: norm(img.getAttribute("alt") || ""),

                title: norm(img.getAttribute("title") || ""),

                outer: img.outerHTML || ""

            };

        }



        /*

         1차:

         tooltip line 단위로 찾는다.

         실제 구조는 보통:

         <div class="tooltips_tooltip_line...">

             <div><b>서포트 카드 (힌트 획득):</b></div>

             <span><img ...></span>

             <span><img ...></span>

         </div>

        */

        const allDivs = [...panel.querySelectorAll("div")];



        let lineCandidates = allDivs

            .filter(el => {

                if (!visible(el)) return false;



                const text = norm(el.innerText || el.textContent || "");

                if (!text.includes(targetLabel)) return false;



                const imgs = [...el.querySelectorAll("img")].filter(img => imgMatches(img));

                if (imgs.length <= 0) return false;



                const r = el.getBoundingClientRect();



                // 너무 큰 전체 패널은 제외

                if (r.height > 500) return false;



                return true;

            })

            .map(el => {

                const r = el.getBoundingClientRect();

                const imgs = [...el.querySelectorAll("img")].filter(img => imgMatches(img));



                let score = 0;



                // 해당 구역 이미지가 많을수록 좋음

                score += imgs.length * 100;



                // tooltip line 클래스면 가산

                const cls = String(el.className || "");

                if (cls.includes("tooltips_tooltip_line")) score += 500;



                // 너무 큰 부모 div는 감점

                const area = r.width * r.height;

                if (area > 250000) score -= 1000;



                return { el, score, area };

            });



        lineCandidates.sort((a, b) => {

            if (b.score !== a.score) return b.score - a.score;

            return a.area - b.area;

        });



        if (lineCandidates.length > 0) {

            const targetLine = lineCandidates[0].el;



            const imgs = [...targetLine.querySelectorAll("img")]

                .filter(img => visible(img))

                .filter(img => imgMatches(img))

                .map(img => readImg(img));



            return imgs;

        }



        /*

         2차 fallback:

         DOM을 순서대로 훑으면서 현재 라벨을 기억하고,

         다음 라벨이 나오기 전까지의 img를 수집한다.

        */

        const labels = [

            "캐릭터:",

            "캐릭터 (이벤트 획득):",

            "서포트 카드 (힌트 획득):",

            "서포트 카드 (이벤트 획득):",

            "시나리오 이벤트 획득:",

            "레어도:",

            "별도 희귀 스킬:",

            "발동 타입:"

        ];



        const result = [];

        const seen = new Set();



        const walker = document.createTreeWalker(

            panel,

            NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT

        );



        let currentLabel = null;



        while (walker.nextNode()) {

            const node = walker.currentNode;



            if (node.nodeType === Node.TEXT_NODE) {

                const text = norm(node.nodeValue || "");



                if (!text) continue;



                for (const lb of labels) {

                    if (text.includes(lb)) {

                        currentLabel = lb;

                        break;

                    }

                }



                continue;

            }



            if (node.nodeType !== Node.ELEMENT_NODE) continue;



            const el = node;

            const tag = (el.tagName || "").toLowerCase();



            if (tag !== "img") continue;

            if (currentLabel !== targetLabel) continue;

            if (!visible(el)) continue;

            if (!imgMatches(el)) continue;



            const src = el.getAttribute("src") || "";

            if (!src || seen.has(src)) continue;



            seen.add(src);

            result.push(readImg(el));

        }



        return result;

        """,

        panel,

        label,

    )





def extract_panel_data(driver, panel, session, support_cache):

    result = {

        "캐릭터": "",

        "캐릭터 (이벤트 획득)": "",

        "서포트 카드 (힌트 획득)": "",

        "서포트 카드 (이벤트 획득)": "",

    }



    for label in SECTION_LABELS:

        col = COLUMN_BY_LABEL[label]

        img_infos = collect_section_img_infos(driver, panel, label)



        items = []



        if "서포트 카드" in label:

            for info in img_infos:

                src = info.get("src", "")

                alt = clean_text(info.get("alt", ""))



                support_id = parse_support_src(src)



                if not support_id:

                    continue



                meta = resolve_support_meta(

                    session=session,

                    support_id=support_id,

                    name_hint=alt,

                    cache=support_cache,

                )



                display = format_support_display(meta)



                if display:

                    items.append(display)



        else:

            for info in img_infos:

                alt = clean_text(info.get("alt", ""))



                if alt:

                    items.append(alt)



        result[col] = ", ".join(dedupe_preserve_order(items))



    return result





def save_results(results, output_path):

    df = pd.DataFrame(results)



    columns = [

        "스킬명",

        "캐릭터",

        "캐릭터 (이벤트 획득)",

        "서포트 카드 (힌트 획득)",

        "서포트 카드 (이벤트 획득)",

        "상태",

    ]



    for col in columns:

        if col not in df.columns:

            df[col] = ""



    df = df[columns]

    df.to_excel(output_path, index=False)





def short_error(e: Exception) -> str:

    msg = clean_text(str(e))



    if len(msg) > 180:

        msg = msg[:180] + "..."



    return f"{type(e).__name__}: {msg}" if msg else type(e).__name__





def process_one_skill(driver, wait, session, support_cache, skill_name, occurrence):

    close_detail_panel_if_possible(driver)



    search_input = find_search_input(driver, wait)

    set_react_input(driver, search_input, skill_name, wait)



    time.sleep(0.6)



    row = find_skill_row(driver, wait, skill_name, occurrence=occurrence)

    row_desc = get_row_description(row, skill_name)



    # 여기만 핵심적으로 수정됨

    click_more(driver, row, wait=wait, skill_name=skill_name)



    time.sleep(0.35)



    panel = find_detail_panel(driver, wait, skill_name, row_desc=row_desc)



    data = extract_panel_data(driver, panel, session, support_cache)



    row_result = {

        "스킬명": skill_name,

        "캐릭터": data.get("캐릭터", ""),

        "캐릭터 (이벤트 획득)": data.get("캐릭터 (이벤트 획득)", ""),

        "서포트 카드 (힌트 획득)": data.get("서포트 카드 (힌트 획득)", ""),

        "서포트 카드 (이벤트 획득)": data.get("서포트 카드 (이벤트 획득)", ""),

        "상태": "성공",

    }



    found_any = any([

        row_result["캐릭터"],

        row_result["캐릭터 (이벤트 획득)"],

        row_result["서포트 카드 (힌트 획득)"],

        row_result["서포트 카드 (이벤트 획득)"],

    ])



    if not found_any:

        row_result["상태"] = "패널 성공 / 추출 0개"



    return row_result





def main():

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")



    file_path = os.path.join(desktop, "UMA3.txt")

    output_path = os.path.join(desktop, OUTPUT_FILENAME)

    cache_path = os.path.join(desktop, CACHE_FILENAME)



    skills = extract_skill_names(file_path)



    if TEST_LIMIT is not None:

        target_skills = skills[:TEST_LIMIT]

    else:

        target_skills = skills



    print(f"실행 대상 스킬 수: {len(target_skills)}개")



    support_cache = load_cache(cache_path)

    print(f"로드된 support cache 수: {len(support_cache)}개")



    occurrence_counter = defaultdict(int)

    results = []



    session = make_session()

    driver = make_driver()

    wait = WebDriverWait(driver, 15)



    try:

        driver.get(URL_SKILLS)

        wait_page_ready(driver, timeout=20)

        time.sleep(2.0)

        click_show_all_skills(driver, wait)



        for idx, skill_name in enumerate(target_skills, start=1):

            print(f"[{idx}/{len(target_skills)}] {skill_name} ... ", end="", flush=True)



            occurrence = occurrence_counter[skill_name]



            try:

                row_result = process_one_skill(

                    driver=driver,

                    wait=wait,

                    session=session,

                    support_cache=support_cache,

                    skill_name=skill_name,

                    occurrence=occurrence,

                )



                occurrence_counter[skill_name] += 1

                results.append(row_result)



                if row_result["상태"] == "성공":

                    print("✅")

                else:

                    print(f"⚠️ {row_result['상태']}")



            except Exception as e:

                occurrence_counter[skill_name] += 1

                err = short_error(e)



                results.append({

                    "스킬명": skill_name,

                    "캐릭터": "",

                    "캐릭터 (이벤트 획득)": "",

                    "서포트 카드 (힌트 획득)": "",

                    "서포트 카드 (이벤트 획득)": "",

                    "상태": f"실패: {err}",

                })



                print(f"❌ {err}")



            if idx % 20 == 0:

                save_results(results, output_path)

                save_cache(support_cache, cache_path)

                print(f"   ↳ 중간 저장 완료: {idx}개")



            time.sleep(0.25)



    finally:

        try:

            driver.quit()

        except Exception:

            pass



    save_results(results, output_path)

    save_cache(support_cache, cache_path)



    print()

    print(f"완료: {output_path}")

    print(f"캐시 저장: {cache_path}")





def scrape_sources_from_skills(skill_names, work_dir=None, test_limit=None):
    if work_dir is None:
        work_dir = os.path.join(os.getcwd(), "data", "work")
    os.makedirs(work_dir, exist_ok=True)
    cache_path = os.path.join(work_dir, CACHE_FILENAME)
    target_skills = list(skill_names)[:test_limit] if test_limit is not None else list(skill_names)
    print(f"GameTora source scrape target: {len(target_skills)} skills")
    support_cache = load_cache(cache_path)
    occurrence_counter = defaultdict(int)
    results = []
    session = make_session()
    driver = make_driver()
    wait = WebDriverWait(driver, 15)
    try:
        driver.get(URL_SKILLS)
        wait_page_ready(driver, timeout=20)
        time.sleep(2.0)
        click_show_all_skills(driver, wait)
        for idx, skill_name in enumerate(target_skills, start=1):
            print(f"[{idx}/{len(target_skills)}] {skill_name} ... ", end="", flush=True)
            occurrence = occurrence_counter[skill_name]
            try:
                row_result = process_one_skill(driver, wait, session, support_cache, skill_name, occurrence)
                occurrence_counter[skill_name] += 1
                results.append(row_result)
                print("✅" if row_result["상태"] == "성공" else f"⚠️ {row_result['상태']}")
            except Exception as e:
                occurrence_counter[skill_name] += 1
                err = short_error(e)
                results.append({"스킬명": skill_name, "캐릭터": "", "캐릭터 (이벤트 획득)": "", "서포트 카드 (힌트 획득)": "", "서포트 카드 (이벤트 획득)": "", "상태": f"실패: {err}"})
                print(f"❌ {err}")
            if idx % 20 == 0:
                save_cache(support_cache, cache_path)
            time.sleep(0.25)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    save_cache(support_cache, cache_path)
    return results


if __name__ == "__main__":

    main()




