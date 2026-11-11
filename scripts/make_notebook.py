"""제출용 Colab 노트북(6조과제.ipynb) 만들기.

    python scripts/make_notebook.py

프로젝트의 코드 파일을 그대로 읽어 '%%writefile' 칸으로 넣는다.
코드를 고친 뒤 이 스크립트를 다시 돌리면 노트북도 최신 코드로 바뀐다.
API 키는 노트북에 들어가지 않는다 (Colab에서 실행할 때 직접 입력).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "6조과제.ipynb"
GITHUB_REPO = "20aron2/safeway"
APP_URL = ""   # 배포된 앱 주소를 알면 여기에 (예: https://xxxx.streamlit.app)

# (파일, 설명) — 읽는 사람이 위에서부터 차례로 이해할 수 있는 순서
FILES = [
    ("core/__init__.py", None),
    ("core/config.py", "**설정값**: 지도 중심, 분석 반경(기본 50m), 데이터 파일 위치, AI 모델 이름 등을 한곳에 모았어요."),
    ("core/texts.py", "**화면 문구**: 화면에 보이는 글자를 모아 둔 파일이에요. 코딩을 몰라도 따옴표 안만 바꾸면 문구가 바뀌어요."),
    ("core/geo.py", "**거리 계산**: 위도·경도 두 점 사이 거리(m)를 하버사인 공식으로 계산해요."),
    ("core/facilities.py", "**시설 데이터 읽기**: 정리된 공공데이터(CCTV·비상벨·보안등) CSV를 읽고, 경로 근처만 잘라내요."),
    ("core/routes.py", "**경로 후보**: TMAP 보행자 경로 API로 실제 걸어가는 길 2~3개를 받아요. 키가 없으면 가상 경로를 만들어요."),
    ("core/search.py", "**장소 검색**: '부산대역' 같은 이름을 TMAP 장소 검색으로 좌표로 바꿔요. 이름이 맞는 곳을 먼저 보여 줘요."),
    ("core/analysis.py", "**핵심 분석**: 경로에서 반경 안의 시설 수, 1km당 시설 수, 시설이 없는 가장 긴 구간, 보안등 없는 구간을 계산해요. (numpy로 한 번에 계산)"),
    ("core/recommend.py", "**비교 점수와 추천**: 거리 점수와 시설 점수를 가중치로 섞어 경로를 비교해요. 공식은 화면에도 공개해요."),
    ("core/explain.py", "**설명 문장과 AI**: Python이 계산한 숫자만 Gemini에 보내 설명을 받아요. AI 답에 계산 결과에 없는 숫자가 있으면 쓰지 않아요 (AI 숫자 검증)."),
    ("core/insights.py", "**데이터로 본 부산**: 구·군별 시설 수와 1㎢당 시설 수를 계산하고, 표에서 바로 읽히는 사실을 문장으로 만들어요."),
    ("core/map_view.py", "**지도 그리기 (브이월드/OSM)**: folium으로 경로, 시설, 빈 구간을 지도에 그려요."),
    ("core/tmap_map.py", "**TMAP 지도 (Python 쪽)**: TMAP 웹 지도 부품에 그릴 내용을 넘겨요."),
    ("core/tmap_component/index.html.template", "**TMAP 지도 (화면 쪽, HTML·JavaScript)**: 지도 표시, 클릭·터치로 위치 고르기, 내 위치 표시."),
    ("core/ui.py", "**화면 꾸미기**: 지도 앱처럼 보이게 하는 CSS와 경로 카드 디자인이에요."),
    (".streamlit/config.toml", "**화면 테마**"),
    ("app.py", "**메인 화면 (Streamlit)**: 검색창, 지도, 경로 카드, AI 설명, 귀가 알림을 배치하고 버튼 동작을 연결해요."),
]


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


def build() -> dict:
    app_line = f"- 배포된 앱: {APP_URL}\n" if APP_URL else "- 배포된 앱: (Streamlit Cloud 주소)\n"
    cells = [
        md(f"""
# 6조 · 안심길 (SafeWay)
**「인공지능과 디지털 사고」 팀 프로젝트** · 공공데이터로 야간 도보 경로를 비교하는 웹 앱

밤에 걸어서 집에 갈 때, 갈 수 있는 길 2~3개를 보여 주고 **길마다 주변 CCTV·안전비상벨·보안등이 몇 개 있는지** 비교해 줘요.
Python이 숫자를 계산하고, Gemini(AI)는 그 숫자만 써서 설명해요.

{app_line}- 코드 저장소: https://github.com/{GITHUB_REPO}
- 데이터 범위: 부산광역시 16개 구·군 (CCTV 11,186곳 · 비상벨 651곳 · 보안등 66,142곳, 공공데이터포털)

> 이 앱은 실제 안전을 보장하지 않아요. 공공데이터에 등록된 시설 위치를 참고해 경로를 비교할 뿐이에요.

### 실행 방법
1. 메뉴 **런타임 → 모두 실행**
2. 'API 키 입력' 칸에서 키를 묻으면 붙여 넣고 엔터 (없으면 그냥 엔터 → 데모 모드)
3. 마지막 칸에 나온 `https://….loca.lt` 주소를 열고, 비밀번호 칸에 바로 위 칸에 나온 IP 주소를 넣어요
"""),
        md("""
## 1. 필요한 패키지 설치
pandas, requests, numpy는 Colab에 이미 있어요.
"""),
        code("!pip -q install streamlit folium streamlit-folium google-genai streamlit-js-eval"),
        md("""
## 2. 앱 코드 파일 만들기
`%%writefile`로 칸의 내용을 파일로 저장해요. 기능별로 파일을 나눠서, 고칠 곳을 찾기 쉽게 만들었어요.

```
app.py              메인 화면
core/               실제 기능 (설정, 검색, 경로, 분석, 추천, 설명, 지도)
data/processed/     정리된 공공데이터 (다음 단계에서 받아요)
```
"""),
        code("!mkdir -p core/tmap_component data/processed .streamlit"),
    ]
    for rel, desc in FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        if desc:
            cells.append(md(f"#### `{rel}`\n{desc}"))
        cells.append(code(f"%%writefile {rel}\n{text}"))

    cells += [
        md(f"""
## 3. 공공데이터 받기
원본 CSV(구별 CCTV·비상벨·보안등)를 `scripts/build_facilities.py`로 정리한 파일이에요.
정리하면서 한 일: 교통단속용 CCTV 제외, 같은 위치 중복 합치기, 부산 밖·빈 좌표 제거.
(CCTV 원본 18,074줄 → 11,186곳)
"""),
        code(f"""
import os, urllib.request
import pandas as pd

URL = "https://raw.githubusercontent.com/{GITHUB_REPO}/main/data/processed/facilities_busan.csv"
PATH = "data/processed/facilities_busan.csv"
try:
    urllib.request.urlretrieve(URL, PATH)
except Exception as e:   # 인터넷 문제 등 → 파일을 직접 올리기
    print("GitHub에서 받지 못했어요:", e, "\\n facilities_busan.csv 파일을 직접 올려 주세요.")
    from google.colab import files
    up = files.upload()
    os.replace(next(iter(up)), PATH)

df = pd.read_csv(PATH)
print(f"시설 {{len(df):,}}곳")
display(df["kind"].map({{"cctv": "CCTV", "bell": "안전비상벨", "light": "보안등"}}).value_counts().rename("개수").to_frame())
display(df.head())
"""),
        md("""
## 4. 계산이 어떻게 되는지 확인 (키 없이)
부산대역 → 부산대학교 정문 사이에 가상 경로 3개를 만들고, Python이 경로별 시설 수와 점수를 계산해요.
앱 화면의 카드에 나오는 숫자가 바로 이 계산 결과예요.
"""),
        code("""
from core import analysis, recommend, explain
from core.routes import get_routes
from core.facilities import load_public_facilities, filter_bbox
from core.geo import bbox

start, end = (35.2295, 129.0896), (35.2316, 129.0846)   # 부산대역, 부산대학교 정문 근처
routes = get_routes(start, end)   # 키 없이 만드는 가상 경로 (앱에서는 TMAP 실제 경로)
fac = load_public_facilities("data/processed/facilities_busan.csv")
fac = filter_bbox(fac, bbox([p for r in routes for p in r["coords"]], margin_m=150))

metrics = [analysis.analyze_route(r, fac, radius_m=50) for r in routes]
scored = recommend.score_routes(metrics, "balanced")
cols = ["route_id", "distance_m", "cctv", "bell", "light", "per_km", "longest_gap_m", "longest_dark_m", "score"]
display(pd.DataFrame(scored["rows"])[cols].round(1))
print("추천 경로:", scored["recommended_id"])
print()
print(explain.build_basic_explanation(scored, 50, facilities_are_demo=False))
"""),
        md("""
## 5. API 키 입력
키는 화면에 보이지 않게 입력받아 Colab 안의 `.streamlit/secrets.toml`에만 저장해요. 노트북 파일에는 남지 않아요.
- TMAP: 실제 도보 경로·장소 검색·TMAP 지도 (없으면 가상 경로)
- Gemini: AI 설명·AI에게 물어보기 (없으면 Python 기본 설명)
- 브이월드: 브이월드 지도 (없으면 OpenStreetMap)
"""),
        code("""
from getpass import getpass

keys = {}
for name, label in [("TMAP_APP_KEY", "TMAP"), ("GEMINI_API_KEY", "Gemini"), ("VWORLD_API_KEY", "브이월드")]:
    value = getpass(f"{label} 키 (없으면 엔터): ").strip()
    if value:
        keys[name] = value
with open(".streamlit/secrets.toml", "w", encoding="utf-8") as f:
    for name, value in keys.items():
        f.write(f'{name} = "{value}"\\n')
print("저장한 키:", ", ".join(keys) or "없음 (데모 모드)")
"""),
        md("""
## 6. 앱 실행
수업에서 배운 방법 그대로예요.
1. 아래 칸이 앱을 백그라운드로 실행해요.
2. 그다음 칸에 나오는 숫자(IP 주소)를 복사해 두세요.
3. 마지막 칸에 나오는 `https://….loca.lt` 주소를 열고, 비밀번호 칸에 그 IP 주소를 넣으면 앱이 열려요.
"""),
        code("!streamlit run app.py &>/dev/null&"),
        code("!curl ipv4.icanhazip.com"),
        code("!npx -y localtunnel --port 8501"),
        md("""
## 7. 데이터 출처와 한계
- CCTV·안전비상벨·보안등: 공공데이터포털, 부산 16개 구·군 (2024~2026년 기준)
- 도보 경로·장소 검색·지도: TMAP API / 설명: Google Gemini API / 지도: 브이월드
- 구청에 등록된 시설만 있어요. 민간 CCTV, 큰길 가로등, 실제 작동 여부, 사람 통행량은 알 수 없어요.
- 사하구·사상구는 공개된 비상벨 데이터가 없어요.
- 비교 점수의 가중치는 팀이 정한 값이에요. 과학적으로 검증된 안전도가 아니에요.
"""),
    ]
    return {
        "cells": cells,
        "metadata": {
            "colab": {"provenance": [], "toc_visible": True},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }


if __name__ == "__main__":
    nb = build()
    OUT.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT.name}: {len(nb['cells'])}칸")
