"""안심길(SafeWay) 메인 화면.

실행:  streamlit run app.py

화면 흐름
1. 장소 검색, 현재 위치, 지도 클릭 중 하나로 출발지·도착지 지정
2. [경로 탐색] → 경로 후보 생성 → 시설 데이터 준비
3. 경로별 시설 분석 → 점수 계산 → 카드·추천·설명 표시
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import streamlit as st
from streamlit_folium import st_folium

from core import analysis, config, explain, recommend, texts, ui
from core import facilities as fac
from core import routes as rt
from core import search as sr
from core.geo import bbox, haversine_m

try:  # 현재 위치·브라우저 시각 읽기 부품 (없어도 앱은 동작)
    from streamlit_js_eval import get_geolocation, streamlit_js_eval
except ImportError:
    get_geolocation = streamlit_js_eval = None
from core import tmap_map
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
    "start_name": None,   # 화면에 보여줄 이름 (검색한 장소명, "현재 위치" 등)
    "end_name": None,
    "found_start": [],    # 장소 검색 결과
    "found_end": [],
    "found_seq": 0,
    "search_msg_start": None,
    "search_msg_end": None,
    "locating": False,    # '현재 위치를 출발지로'를 누른 뒤 위치를 기다리는 중
    "loc_msg": None,
    "link_loaded": False, # 공유 링크로 들어왔을 때 한 번만 처리
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


def set_point(which: str, point, name: str) -> None:
    """출발지(which='start') 또는 도착지('end')를 지정하고 이전 결과를 지운다."""
    S[which] = point
    S[f"{which}_name"] = name
    S[f"found_{which}"] = []
    S.result = None
    S.error = None
    st.query_params.clear()  # 이전 경로의 공유 주소는 더 이상 맞지 않는다


def handle_click(point: tuple[float, float]) -> None:
    if S.start is None:
        set_point("start", point, texts.MAP_PICK_NAME)
    elif S.end is None:
        set_point("end", point, texts.MAP_PICK_NAME)
    else:  # 둘 다 있으면 새로 시작
        set_point("start", point, texts.MAP_PICK_NAME)
        S.end = S.end_name = None


def reset() -> None:
    S.start = S.end = S.result = S.error = None
    S.start_name = S.end_name = S.loc_msg = None
    S.found_start, S.found_end = [], []
    S.search_msg_start = S.search_msg_end = None
    S.locating = False
    st.query_params.clear()


def run_place_search(which: str, keyword: str) -> None:
    S[f"search_msg_{which}"] = None
    S[f"found_{which}"] = []
    try:
        found = cached_places(keyword.strip(), get_secret("TMAP_APP_KEY"))
    except sr.SearchError as e:
        S[f"search_msg_{which}"] = str(e)
        return
    if not found:
        S[f"search_msg_{which}"] = texts.SEARCH_EMPTY
    S[f"found_{which}"] = found
    S.found_seq += 1


def start_locating() -> None:
    S.locating = True
    S.loc_msg = None


def place_picker(which: str, label: str, placeholder: str) -> None:
    """장소 검색창 + 후보 선택."""
    with st.form(f"form_{which}", border=False):
        keyword = st.text_input(f"{label} 검색", placeholder=placeholder, key=f"q_{which}")
        submitted = st.form_submit_button("검색")
    if submitted:
        run_place_search(which, keyword)
    if S[f"search_msg_{which}"]:
        st.caption(S[f"search_msg_{which}"])
    found = S[f"found_{which}"]
    if found:
        idx = st.selectbox(
            f"{label} 후보", options=list(range(len(found))),
            format_func=lambda i: f"{found[i]['name']} · {found[i]['address']} ({found[i]['dist_km']:.1f}km)",
            key=f"pick_{which}_{S.found_seq}", label_visibility="collapsed",
        )
        place = found[idx]
        st.button(f"이곳을 {label}로", key=f"set_{which}", on_click=set_point,
                  args=(which, (place["lat"], place["lon"]), place["name"]))


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


@st.cache_data(ttl=3600, show_spinner="장소를 찾는 중…")
def cached_places(keyword, app_key):
    return sr.search_places(keyword, app_key)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_police(center, app_key):
    return sr.find_police(center, app_key)


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
    police = []
    if tmap_key:  # 지구대·파출소는 참고 정보라 실패해도 경로 비교는 계속한다
        mid = ((S.start[0] + S.end[0]) / 2, (S.start[1] + S.end[1]) / 2)
        try:
            police = cached_police((round(mid[0], 3), round(mid[1], 3)), tmap_key)
        except sr.SearchError:
            police = []
    S.result = {
        "routes": routes,
        "facilities": facilities,
        "route_source": route_source,
        "facility_source": facility_source,
        "police": police,
    }
    S.error = None
    S.search_id += 1


def _parse_point(text: str | None):
    """'35.2316,129.0846' → (35.2316, 129.0846). 한국 범위를 벗어나거나 형식이 틀리면 None."""
    try:
        lat, lon = (float(v) for v in (text or "").split(","))
    except ValueError:
        return None
    return (round(lat, 6), round(lon, 6)) if 33 <= lat <= 39 and 124 <= lon <= 132 else None


def share_url() -> str | None:
    """지금 출발·도착이 담긴 주소. 주소창의 서버 이름으로 만든다."""
    if S.start is None or S.end is None:
        return None
    query = urlencode({"from": f"{S.start[0]},{S.start[1]}", "to": f"{S.end[0]},{S.end[1]}",
                       "fn": S.start_name or "", "tn": S.end_name or ""})
    try:
        host = st.context.headers.get("host")
    except Exception:
        host = None
    if not host:
        return f"?{query}"
    scheme = "http" if host.startswith(("localhost", "127.0.0.1")) else "https"
    return f"{scheme}://{host}/?{query}"


# 공유 링크로 들어온 경우: 출발·도착을 채우고 바로 탐색 (처음 한 번만)
if not S.link_loaded:
    S.link_loaded = True
    qp_start, qp_end = _parse_point(st.query_params.get("from")), _parse_point(st.query_params.get("to"))
    if qp_start and qp_end:
        set_point("start", qp_start, st.query_params.get("fn") or texts.SHARED_NAME)
        set_point("end", qp_end, st.query_params.get("tn") or texts.SHARED_NAME)
        run_search()
        S.loc_msg = texts.SHARED_OPENED


# ---------------------------------------------------------------- 화면: 상단
ui.inject_css()
ui.header()

result = S.result
expected_fac_source = result["facility_source"] if result else (
    "public" if config.PUBLIC_FACILITIES_PATH.exists() else "demo")
expected_route_source = result["route_source"] if result else (
    "tmap" if get_secret("TMAP_APP_KEY") else "demo")
ui.data_banner(expected_route_source, expected_fac_source)

# 장소 검색 (TMAP 키가 있을 때)
if get_secret("TMAP_APP_KEY"):
    with st.container(border=True):
        col_s, col_e = st.columns(2)
        with col_s:
            place_picker("start", "출발지", texts.SEARCH_START_PLACEHOLDER)
            if get_geolocation is not None:
                st.button(texts.MY_LOCATION_BUTTON, on_click=start_locating)
        with col_e:
            place_picker("end", "도착지", texts.SEARCH_END_PLACEHOLDER)

# '현재 위치를 출발지로': 브라우저가 위치를 알려줄 때까지 기다린다
if S.locating and get_geolocation is not None:
    loc = get_geolocation()
    if not loc:
        st.caption(texts.LOCATING_WAIT)
    elif "error" in loc:
        code = (loc.get("error") or {}).get("code")
        S.loc_msg = texts.LOCATION_DENIED if code == 1 else texts.LOCATION_FAILED
        S.locating = False
        st.rerun()
    else:
        coords = loc.get("coords") or {}
        lat, lon = coords.get("latitude"), coords.get("longitude")
        S.locating = False
        if lat is None or lon is None:
            S.loc_msg = texts.LOCATION_FAILED
        else:
            point = (round(float(lat), 6), round(float(lon), 6))
            set_point("start", point, texts.MY_LOCATION_NAME)
            far_km = haversine_m(*config.DEFAULT_CENTER, *point) / 1000
            if far_km > sr.SEARCH_RADIUS_KM:
                S.loc_msg = texts.LOCATION_FAR.format(km=far_km)
        st.rerun()
if S.loc_msg:
    st.info(S.loc_msg)

col_guide, col_reset = st.columns([4, 1], vertical_alignment="center")
with col_guide:
    ui.pick_status(S.start, S.end, S.start_name, S.end_name)
with col_reset:
    st.button(texts.RESET_BUTTON, on_click=reset, disabled=S.start is None and S.end is None)

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
gap_segments: list = []
police: list = []
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

    memo_key = (S.search_id, radius)
    if S.get("metrics_key") != memo_key:  # 같은 탐색·반경이면 다시 계산하지 않는다
        S.metrics = [analysis.analyze_route(r, result["facilities"], radius) for r in routes]
        S.metrics_key = memo_key
    metrics = S.metrics
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
    gap_segments = rows_by_id[selected_id]["gap_segments"]
    police = result.get("police") or []

    cols = st.columns(len(routes))
    for i, (col, route) in enumerate(zip(cols, routes)):
        with col:
            ui.route_card(rows_by_id[route["id"]], route,
                          config.ROUTE_COLORS[i % len(config.ROUTE_COLORS)],
                          recommended=route["id"] == rec_id,
                          selected=route["id"] == selected_id,
                          facilities_are_demo=demo_fac,
                          nearest_police=analysis.nearest_place(route["coords"], police))

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

    # 경로 공유: 주소창에도 같은 값을 넣어 두면 브라우저 '공유' 버튼으로도 보낼 수 있다
    st.query_params.update({"from": f"{S.start[0]},{S.start[1]}", "to": f"{S.end[0]},{S.end[1]}",
                            "fn": S.start_name or "", "tn": S.end_name or ""})
    with st.expander("🔗 이 경로 공유하기"):
        st.code(share_url() or "", language=None)
        st.caption(texts.SHARE_NOTE)

    with st.expander("점수는 어떻게 계산하나요?"):
        st.markdown(recommend.formula_markdown(mode))
    with st.expander("공공데이터로 알 수 없는 것"):
        st.markdown("\n".join(f"- {item}" for item in texts.DATA_LIMITS))

# ---------------------------------------------------------------- 지도 (위에 비워 둔 자리)
with map_slot:
    vworld_key = get_secret("VWORLD_API_KEY")
    tmap_key = get_secret("TMAP_APP_KEY")
    c_map, c_night = st.columns([3, 2], vertical_alignment="bottom")
    with c_map:
        providers = (["tmap"] if tmap_key else []) + ["vworld"]
        default_provider = config.MAP_PROVIDER if config.MAP_PROVIDER in providers else providers[0]
        provider = st.segmented_control(
            "지도 선택", options=providers, default=default_provider, key="map_provider",
            format_func=lambda p: {"tmap": "TMAP 지도", "vworld": "브이월드 지도" if vworld_key else "기본 지도"}[p],
        ) or default_provider
    night = False
    with c_night:
        if provider == "tmap" or vworld_key:  # 야간 지도는 TMAP과 브이월드에서만
            # '밤'은 보는 사람 기준이라 브라우저 시각을 쓴다. 아직 모르면 한국 시간으로.
            if streamlit_js_eval is not None and S.get("browser_hour") is None:
                h = streamlit_js_eval(js_expressions="new Date().getHours()", key="browser_hour_js")
                if isinstance(h, (int, float)):
                    S.browser_hour = int(h)
            hour = S.get("browser_hour")
            if hour is None:
                hour = datetime.now(timezone(timedelta(hours=9))).hour
            start_h, end_h = config.NIGHT_HOURS
            if not S.get("night_touched"):  # 직접 바꾸기 전까지는 시각에 맞춰 자동
                S["night"] = hour >= start_h or hour < end_h
            night = st.toggle("🌙 야간 지도", key="night",
                              on_change=lambda: S.update(night_touched=True))

    map_parts = dict(
        start=S.start, end=S.end, start_name=S.start_name, end_name=S.end_name,
        routes=result["routes"] if result else None,
        selected_id=selected_id,
        facilities=result["facilities"] if result else None,
        near_ids=near_ids,
        gap_segments=gap_segments,
        police=police,
        night=night,
    )
    if provider == "tmap":
        map_data = tmap_map.render(tmap_map.build_payload(**map_parts), tmap_key)
    else:
        fmap = build_map(**map_parts, vworld_key=vworld_key)
        map_kwargs = dict(key="main_map", height=config.MAP_HEIGHT_PX, returned_objects=["last_clicked"])
        try:
            map_data = st_folium(fmap, use_container_width=True, **map_kwargs)
        except TypeError:  # streamlit-folium 버전에 따라 옵션 이름이 다를 때
            map_data = st_folium(fmap, **map_kwargs)
with legend_slot:
    has_lights = bool(result) and "light" in set(result["facilities"]["kind"])
    ui.legend(radius, has_police=bool(police), has_gaps=bool(gap_segments), has_lights=has_lights)

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
