"""앱 전체에서 쓰는 설정값. 숫자를 바꾸고 싶으면 여기만 고치면 된다."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 지도 시작 위치: 부산 금정구 부산대학교 정문 부근
DEFAULT_CENTER = (35.2316, 129.0846)
DEFAULT_ZOOM = 16  # 도보 경로가 잘 보이는 확대 수준
MAP_HEIGHT_PX = 460
MAP_TILES = "OpenStreetMap"  # 브이월드 키가 없을 때 쓰는 기본 지도

# 브이월드(국토교통부) 배경지도. .streamlit/secrets.toml 에 VWORLD_API_KEY 가 있으면 사용.
# 레이어 선택: "Base"(일반 지도), "gray"(회색 지도), "midnight"(야간 지도), "Satellite"(위성)
VWORLD_LAYER = "Base"
VWORLD_NIGHT_LAYER = "midnight"  # 야간 지도
NIGHT_HOURS = (19, 6)            # 한국 시간 19시~다음 날 6시는 처음부터 야간 지도
VWORLD_URL = "https://api.vworld.kr/req/wmts/1.0.0/{key}/{layer}/{{z}}/{{y}}/{{x}}.{ext}"
VWORLD_ATTR = '&copy; <a href="https://www.vworld.kr">VWorld</a> (국토교통부)'

# 분석 반경(m): 공식적으로 검증된 '안전 반경'이 아니라 사용자가 바꿀 수 있는 분석 변수
DEFAULT_RADIUS_M = 50
RADIUS_OPTIONS_M = (20, 100)  # 슬라이더 최소/최대

# 경로 색상 (A, B, C 순서)
ROUTE_COLORS = ["#2563EB", "#16A34A", "#9333EA"]
ROUTE_IDS = ["A", "B", "C"]

# 경로 요청 제한
MIN_TRIP_M = 50       # 이보다 가까우면 경로를 만들지 않는다
MAX_TRIP_M = 5_000    # 도보 비교 대상으로 너무 먼 거리
DUPLICATE_ROUTE_M = 25  # 두 경로 차이가 이보다 작으면 같은 경로로 보고 하나만 남긴다

# 데모 경로 예상 시간 계산용 보행 속도 (약 4km/h). TMAP 연동 후에는 TMAP 값을 쓴다.
DEMO_WALK_SPEED_MPS = 1.1

# 시설 공백 구간 분석 간격(m)과 지도에 그릴 최소 길이(m)
GAP_SAMPLE_STEP_M = 10
GAP_DRAW_MIN_M = 100

# 실제 공공데이터 정리 파일 (STEP 3에서 생성). 이 파일이 있으면 시설은 실제 데이터를 쓴다.
PUBLIC_FACILITIES_PATH = PROJECT_ROOT / "data" / "processed" / "facilities_geumjeong.csv"

# Gemini 설명 모델. 무료 티어에서 쓸 수 있는 가벼운 모델.
# 모델 이름이 바뀌어 오류가 나면 여기만 고치면 된다 (예: "gemini-3.5-flash").
GEMINI_MODEL = "gemini-3.1-flash-lite"
