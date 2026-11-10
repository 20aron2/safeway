"""안심길(SafeWay) 메인 화면.

실행:  streamlit run app.py

화면 흐름
1. 지도 클릭 → 출발지, 도착지 지정
2. [경로 탐색] → 경로 후보 생성 → 시설 데이터 준비
3. 경로별 시설 분석 → 점수 계산 → 카드·추천·설명 표시
"""
from __future__ import annotations

import streamlit as st
from streamlit_folium import st_folium

from core import analysis, config, explain, recommend, texts, ui
from core import facilities as fac
from core import routes as rt
from core.geo import bbox
from core.map_view import build_map

st.set_page_config(
    page_title=f"{texts.APP_NAME} · {texts.APP_NAME_EN}",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------- 상태 관리
DEFAULT_STATE = {
    "start": None,        # (위도, 경도)
    "end": None,
    "last_click": None,   # 같은 클릭을 두 번 처리하지 않기 위한 기록
    "result": None,       # 탐색 결과 (경로 + 시설)
    "error": None,
    "data_warning": None,
    "search_id": 0,
}
for key, value in DEFAULT_STATE.items():
    st.session_state.setdefault(key, value)
S = st.session_state


def get_secret(name: str) -> str | None:
    """API 키는 코드에 쓰지 않고 .streamlit/secrets.toml 에서 읽는다. 없으면 None."""
    try:
        return st.secrets.get(name)
    except Exception:
        return None


def handle_click(point: tuple[float, float]) -> None:
    if S.start is None:
        S.start = point
    elif S.end is None:
        S.end = point
    else:  # 둘 다 있으면 새로 시작
        S.start, S.end = point, None
    S.result = None
    S.error = None


def reset() -> None:
    S.start = S.end = S.result = S.error = None


@st.cache_data(show_spinner=False)
def load_public(path_str: str, modified: float):
    return fac.load_public_facilities(config.PUBLIC_FACILITIES_PATH)


def prepare_facilities(routes: list[dict]):
    """실제 공공데이터 파일이 있으면 그것을, 없으면 가상 시설을 쓴다."""
    S.data_warning = None
    path = config.PUBLIC_FACILITIES_PATH
    if path.exists():
        try:
            df = load_public(str(path), path.stat().st_mtime)
            coords = [c for r in routes for c in r["coords"]]
            return "public", fac.filter_bbox(df, bbox(coords, margin_m=150))
        except Exception as e:  # 파일 형식 문제 → 데모로 대체하고 알려준다
            S.data_warning = f"공공데이터 파일을 읽지 못해 가상 시설로 대신했어요: {e}"
    return "demo", fac.make_demo_facilities(routes, S.start)


@st.cache_data(ttl=86400, show_spinner="AI 설명을 만드는 중…")
def cached_gemini(payload_json, api_key, model):
    """같은 계산 결과면 Gemini를 다시 부르지 않는다 (슬라이더를 움직일 때마다 호출 방지)."""
    return explain.call_gemini(payload_json, api_key, model)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_routes(start, end, source, app_key):
    """같은 출발·도착은 1시간 동안 다시 묻지 않는다 (TMAP 무료 사용량 절약)."""
    return rt.get_routes(start, end, source=source, app_key=app_key)


def run_search() -> None:
    # TMAP 키가 있으면 실제 도보 경로, 없으면 데모(직선) 경로
    tmap_key = get_secret("TMAP_APP_KEY")
    route_source = "tmap" if tmap_key else "demo"
    try:
        routes = [dict(r) for r in cached_routes(S.start, S.end, route_source, tmap_key)]
    except rt.RouteError as e:
        S.result, S.error = None, str(e)
        return
    facility_source, facilities = prepare_facilities(routes)
    S.result = {
        "routes": routes,
        "facilities": facilities,
        "route_source": route_source,
        "facility_source": facility_source,
    }
    S.error = None
    S.search_id += 1


# ---------------------------------------------------------------- 화면: 상단
ui.inject_css()
ui.header()

result = S.result
expected_fac_source = result["facility_source"] if result else (
    "public" if config.PUBLIC_FACILITIES_PATH.exists() else "demo")
expected_route_source = result["route_source"] if result else (
    "tmap" if get_secret("TMAP_APP_KEY") else "demo")
ui.data_banner(expected_route_source, expected_fac_source)

col_guide, col_reset = st.columns([4, 1], vertical_alignment="center")
with col_guide:
    ui.pick_status(S.start, S.end)
with col_reset:
    st.button(texts.RESET_BUTTON, on_click=reset, disabled=S.start is None)

map_slot = st.container()   # 지도는 결과 계산 후 이 자리에 그린다
legend_slot = st.container()

st.button(texts.SEARCH_BUTTON, type="primary", on_click=run_search,
          disabled=S.start is None or S.end is None)

if S.error:
    st.error(S.error)
if S.data_warning:
    st.warning(S.data_warning)

# ---------------------------------------------------------------- 화면: 결과
selected_id = None
near_ids: list[str] = []
radius = None

if result:
    routes = result["routes"]
    demo_fac = result["facility_source"] == "demo"
    st.divider()
    st.subheader("경로 비교")

    c1, c2 = st.columns(2)
    with c1:
        mode = st.segmented_control(
            "추천 기준", options=list(recommend.MODES),
            format_func=lambda k: recommend.MODES[k]["label"],
            default=recommend.DEFAULT_MODE, key="mode",
        ) or recommend.DEFAULT_MODE
    with c2:
        radius = st.slider(
            "분석 반경 (m)", config.RADIUS_OPTIONS_M[0], config.RADIUS_OPTIONS_M[1],
            config.DEFAULT_RADIUS_M, step=10,
            help="경로에서 이 거리 안에 있는 시설을 셉니다. 검증된 '안전 반경'이 아닌 분석용 값이에요.",
        )

    metrics = [analysis.analyze_route(r, result["facilities"], radius) for r in routes]
    scored = recommend.score_routes(metrics, mode)
    rec_id = scored["recommended_id"]

    if len(routes) > 1:
        selected_id = st.segmented_control(
            "지도에서 강조할 경로", options=[r["id"] for r in routes],
            format_func=lambda i: f"경로 {i}" + (" ★" if i == rec_id else ""),
            default=rec_id, key=f"pick_{S.search_id}",
        ) or rec_id
    else:
        selected_id = rec_id
        st.info("서로 다른 경로가 하나뿐이라 그 경로만 보여드려요.")

    rows_by_id = {row["route_id"]: row for row in scored["rows"]}
    near_ids = rows_by_id[selected_id]["near_ids"]

    cols = st.columns(len(routes))
    for i, (col, route) in enumerate(zip(cols, routes)):
        with col:
            ui.route_card(rows_by_id[route["id"]], route,
                          config.ROUTE_COLORS[i % len(config.ROUTE_COLORS)],
                          recommended=route["id"] == rec_id,
                          selected=route["id"] == selected_id,
                          facilities_are_demo=demo_fac)

    with st.container(border=True):
        st.markdown(f"#### 추천: 경로 {rec_id}")
        st.caption(f"추천 기준: {recommend.MODES[mode]['label']} · 분석 반경 {radius}m")
        basic_text = explain.build_basic_explanation(scored, radius, demo_fac)
        gemini_key = get_secret("GEMINI_API_KEY")
        payload = explain.build_ai_payload(scored, routes, radius,
                                           recommend.MODES[mode]["label"], demo_fac)
        ai_text, ai_issue = explain.get_ai_explanation(
            payload, gemini_key, config.GEMINI_MODEL, caller=cached_gemini)
        st.markdown(ai_text or basic_text)
        if ai_text:
            st.caption("설명 출처: Gemini · Python이 계산한 숫자만 사용하도록 확인했어요")
            with st.expander("Python 계산 결과로 만든 기본 설명 보기"):
                st.markdown(basic_text)
        else:
            reason = f" (AI 설명을 쓰지 못한 이유: {ai_issue})" if gemini_key else ""
            st.caption("설명 출처: Python 계산 결과로 자동 생성한 기본 설명" + reason)

    with st.expander("점수는 어떻게 계산하나요?"):
        st.markdown(recommend.formula_markdown(mode))
    with st.expander("공공데이터로 알 수 없는 것"):
        st.markdown("\n".join(f"- {item}" for item in texts.DATA_LIMITS))

# ---------------------------------------------------------------- 지도 (위에 비워 둔 자리)
with map_slot:
    fmap = build_map(
        start=S.start, end=S.end,
        routes=result["routes"] if result else None,
        selected_id=selected_id,
        facilities=result["facilities"] if result else None,
        near_ids=near_ids,
        vworld_key=get_secret("VWORLD_API_KEY"),
    )
    map_kwargs = dict(key="main_map", height=config.MAP_HEIGHT_PX, returned_objects=["last_clicked"])
    try:
        map_data = st_folium(fmap, use_container_width=True, **map_kwargs)
    except TypeError:  # streamlit-folium 버전에 따라 옵션 이름이 다를 때
        map_data = st_folium(fmap, **map_kwargs)
with legend_slot:
    ui.legend(radius)

with st.expander(texts.HOW_TO_TITLE):
    st.markdown(texts.HOW_TO_BODY)
ui.footer()

# ---------------------------------------------------------------- 지도 클릭 처리
clicked = (map_data or {}).get("last_clicked")
if clicked:
    point = (round(clicked["lat"], 6), round(clicked["lng"], 6))
    if point != S.last_click:
        S.last_click = point
        handle_click(point)
        st.rerun()
