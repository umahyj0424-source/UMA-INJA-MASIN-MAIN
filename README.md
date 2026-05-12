# UMA 스킬 추천기 자동 업데이트 프로젝트

기존 엑셀 기반 사이트를 `data/site-data.json`을 읽는 구조로 분리한 버전입니다.

## 사용 순서

1. 이 폴더 전체를 GitHub 저장소에 올립니다.
2. Netlify에서 `Deploy from Git`으로 저장소를 연결합니다.
3. Build command는 비워두고, Publish directory는 `/`로 둡니다.
4. `config/track_urls.txt`에 utools 마신표 URL을 한 줄에 하나씩 넣습니다.
5. GitHub Actions의 `Update UMA data`를 수동 실행하거나 매일 자동 실행을 기다립니다.

## URL 형식

가장 추천하는 형식은 코스의 `/effects` 주소를 한 줄에 하나씩 넣는 방식입니다.

```txt
https://xn--gck1f423k.xn--1bvt37a.tools/race/courses/10501/effects
https://xn--gck1f423k.xn--1bvt37a.tools/race/courses/10903/effects
https://xn--gck1f423k.xn--1bvt37a.tools/race/courses/10811/effects
```

이렇게 `/effects`까지만 넣으면 스크립트가 자동으로 아래 4개 URL을 만들어서 긁습니다.

```txt
/effects/runner     → 도주
/effects/leader     → 선행
/effects/betweener  → 선입
/effects/chaser     → 추입
```

코스명을 직접 붙이고 싶으면 아래처럼 씁니다.

```txt
6월 단거리 10501|https://xn--gck1f423k.xn--1bvt37a.tools/race/courses/10501/effects
```

특정 각질 URL만 직접 넣고 싶으면 아래 형식도 됩니다.

```txt
6월 단거리 10501|선행|https://xn--gck1f423k.xn--1bvt37a.tools/race/courses/10501/effects/leader
```

사이트 UI에는 코스 선택 드롭다운이 있으며, 여러 코스를 넣으면 코스별 마신표를 바꿔 볼 수 있습니다.

## 로컬 실행

```bash
python -m pip install -r requirements.txt
python scripts/update_data.py
```

로컬에서 사이트를 볼 때는 더블클릭보다 아래처럼 서버로 여는 편이 안전합니다.

```bash
python -m http.server 8000
```

브라우저에서 `http://localhost:8000` 접속.
