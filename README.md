# 안심길 (SafeWay)

공공데이터(CCTV·안전비상벨)를 이용해 야간 도보 경로를 비교하는 웹 앱이에요.
「인공지능과 디지털 사고」 팀 프로젝트 · 시험 지역: 부산 금정구

> 이 앱은 실제 안전을 보장하지 않아요. 공공데이터에 등록된 시설 위치를 참고해 경로를 비교할 뿐이에요.

## 실행 방법 (Windows)

명령 프롬프트에서:

```
cd Documents\safeway
.venv\Scripts\activate
pip install -r requirements-dev.txt
streamlit run app.py
```

브라우저가 자동으로 열려요 (안 열리면 http://localhost:8501).
끝낼 때는 명령 프롬프트에서 `Ctrl + C`.

두 번째부터는 `pip install`은 건너뛰고 `activate` → `streamlit run app.py`만 하면 돼요.

## 테스트 방법

```
python -m pytest
```

거리 계산, 시설 개수 세기, 중복 제거, 추천 점수, 설명 문장을 자동으로 확인해요. 코드를 고친 뒤에는 꼭 한 번 돌려 보세요.

## 지금 상태

| 기능 | 상태 |
|---|---|
| 지도 클릭으로 출발지·도착지 지정, 초기화 | 동작 |
| 경로 후보 2~3개 표시, 중복 경로 제거 | TMAP 키가 있으면 **실제 도보 경로**, 없으면 가상 직선 경로 |
| CCTV·비상벨 표시와 반경 안 개수 세기 | **실제 공공데이터** (금정구청 CCTV 320곳, 비상벨 32곳) |
| 1km당 시설 수, 시설 없는 최장 구간 | 동작 |
| 추천 기준 3가지, 점수 공식 공개 | 동작 |
| 설명 문장 | Python 기본 설명 (Gemini는 다음 단계) |

화면 상단 노란 배너에 무엇이 가상 데이터인지 항상 표시돼요.

## 공공데이터 다시 정리하기

새 CSV를 받으면 `data/raw/cctv.csv`, `data/raw/bell.csv`로 저장한 뒤:

```
python scripts/build_facilities.py
```

정리 과정은 `data/processed/cleaning_report.md`에 기록돼요.

## API 키 넣는 법 (STEP 4~5에서)

`.streamlit/secrets.toml.example`을 복사해 `secrets.toml`로 이름을 바꾸고 키를 넣어요.
이 파일은 `.gitignore`에 있어서 GitHub에 올라가지 않아요.

## 구조

자세한 설계는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)를 보세요.
화면 문구만 바꾸고 싶으면 `core/texts.py`만 고치면 돼요.
