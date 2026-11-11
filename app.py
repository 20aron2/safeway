"""안심길(SafeWay) 메인 화면.

실행:  streamlit run app.py

화면 흐름 (지도 앱처럼)
1. 위 검색 패널: 장소 검색 / 📍 현재 위치 / 지도 클릭으로 출발·도착 지정 (⇅로 바꾸기)
2. 두 곳이 정해지면 자동으로 경로 후보 생성 → 시설 데이터 준비
3. 지도 아래: 옆으로 넘기는 경로 카드, AI 추천 설명, 자세히(공유·점수·데이터)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import quote, urlencode

import streamlit as st
from streamlit_folium import st_folium

from core import analysis, config, explain, insights, recommend, texts, ui
from core import facilities as fac
from core import routes as rt
from core import search as sr
from core.geo import bbox, haversine_m

KST = timezone(timedelta(hours=9))

try:  # 현재 위치·브라우저 시각 읽기 부품 (없어도 앱은 동작)
    from streamlit_js_eval import get_geolocation, streamlit_js_eval
except ImportError:
    get_geolocation = streamlit_js_eval = None
from core import tmap_map
from core.map_view import build_map

st.set_page_config(
    page_title=f"{texts.APP_NAME} · {texts.APP_NAME_EN}",
    page_icon="🛡️",
    layout="wide",
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
    "q_start": "",        # 검색칸 글자
    "q_end": "",
    "search_msg_start": None,
    "search_msg_end": None,
    "locating": False,    # 위치를 기다리는 중 ('📍 현재 위치'나 '🚨 긴급'에서 누름)
    "locate_for": "start",  # 받은 위치를 어디에 쓸지: 'start'(출발지) 또는 'sos'(긴급 문자)
    "my_pos": None,       # 마지막으로 확인한 내 위치 (긴급 문자용, 저장하지 않음)
    "my_addr": None,
    "loc_msg": None,
    "link_loaded": False, # 공유 링크로 들어왔을 때 한 번만 처리
    "last_click": None,   # 같은 클릭을 두 번 처리하지 않기 위한 기록
    "result": None,       # 탐색 결과 (경로 + 시설)
    "error": None,
    "data_warning": None,
    "search_id": 0,
    "pending_q": None,    # AI에게 보낼 질문 (질문칸·예시 질문에서)
    "qa": [],             # (질문, 답, 출처) 최근 4개
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
    S[f"search_msg_{which}"] = None
    S[f"q_sync_{which}"] = True   # 다음 실행 때 검색칸 글자를 장소 이름으로 맞춘다
    S.result = None
    S.error = None
    st.query_params.clear()  # 이전 경로의 공유 주소는 더 이상 맞지 않는다


def clear_point(which: str) -> None:
    S[which] = S[f"{which}_name"] = None
    S[f"q_sync_{which}"] = True
    S.result = None
    S.error = None


def handle_click(point: tuple[float, float]) -> None:
    if S.start is None:
        set_point("start", point, texts.MAP_PICK_NAME)
    elif S.end is None:
        set_point("end", point, texts.MAP_PICK_NAME)
    else:  # 둘 다 있으면 새로 시작
        set_point("start", point, texts.MAP_PICK_NAME)
        clear_point("end")


def reset() -> None:
    S.start = S.end = S.result = S.error = None
    S.start_name = S.end_name = S.loc_msg = None
    S.found_start, S.found_end = [], []
    S.search_msg_start = S.search_msg_end = None
    S.locating = False
    S.q_sync_start = S.q_sync_end = True
    st.query_params.clear()


def swap_points() -> None:
    """출발·도착 바꾸기 (⇅)."""
    S.start, S.end = S.end, S.start
    S.start_name, S.end_name = S.end_name, S.start_name
    S.found_start, S.found_end = [], []
    S.q_sync_start = S.q_sync_end = True
    S.result = S.error = None
    st.query_params.clear()


def run_place_search(which: str) -> None:
    """검색칸에서 엔터를 치면 실행된다."""
    keyword = (S.get(f"q_{which}") or "").strip()
    S[f"search_msg_{which}"] = None
    S[f"found_{which}"] = []
    if not keyword or keyword == (S.get(f"{which}_name") or ""):
        return
    try:
        other = S.end if which == "start" else S.start   # 다른 쪽 지점 근처를 먼저 (지도 앱처럼)
        bias = (round(other[0], 2), round(other[1], 2)) if other else None
        found = cached_places(keyword, get_secret("TMAP_APP_KEY"), bias)
    except sr.SearchError as e:
        S[f"search_msg_{which}"] = str(e)
        return
    if not found:
        S[f"search_msg_{which}"] = texts.SEARCH_EMPTY
    S[f"found_{which}"] = found[:sr.SHOW_RESULTS]
    S.found_seq += 1


def choose_place(which: str, idx: int) -> None:
    place = S[f"found_{which}"][idx]
    set_point(which, (place["lat"], place["lon"]), place["name"])


def start_locating(purpose: str = "start") -> None:
    S.locating = True
    S.locate_for = purpose
    S.loc_msg = None


def submit_question() -> None:
    """질문칸에서 엔터 → 다음 실행에서 답을 만든다."""
    q = (S.get("ask_text") or "").strip()
    S.ask_text = ""
    if q:
        S.pending_q = q[:explain.ASK_MAX_CHARS]


def pick_quick(widget_key: str) -> None:
    kind = S.get(widget_key)
    S[widget_key] = None
    if kind:
        S.pending_q = explain.QUICK_QUESTIONS[kind]


def search_row(which: str, side_button) -> None:
    """지도 앱처럼 '● 출발 [검색칸] [버튼]' 한 줄 + 후보 목록."""
    c_label, c_input, c_btn = st.columns([1.15, 6, 1], vertical_alignment="center")
    with c_label:
        st.markdown(ui.point_label(which), unsafe_allow_html=True)
    with c_input:
        st.text_input(
            "출발지" if which == "start" else "도착지", key=f"q_{which}", label_visibility="collapsed",
            placeholder=texts.SEARCH_START_PLACEHOLDER if which == "start" else texts.SEARCH_END_PLACEHOLDER,
            on_change=run_place_search, args=(which,),
        )
    with c_btn:
        side_button()
    if S[f"search_msg_{which}"]:
        st.caption(S[f"search_msg_{which}"])
    found = S[f"found_{which}"]
    if found:
        with st.container(key=f"cands_{which}"):
            for i, place in enumerate(found):
                st.button(f"📍 {place['name']} · {place['address']}", key=f"cand_{which}_{S.found_seq}_{i}",
                          on_click=choose_place, args=(which, i))


@st.cache_data(show_spinner=False)
def load_public(path_str: str, modified: float):
    return fac.load_public_facilities(config.PUBLIC_FACILITIES_PATH)


@st.cache_data(show_spinner=False)
def load_coverage(path_str: str, modified: float):
    df = load_public(path_str, modified)
    # (전체 시설 범위, 보안등 범위) — 보안등 범위 밖은 '어두운 구간'으로 세지 않는다
    return fac.coverage_cells(df), fac.coverage_cells(df[df["kind"] == "light"])


def prepare_facilities(routes: list[dict]):
    """실제 공공데이터 파일이 있으면 그것을, 없으면 가상 시설을 쓴다."""
    S.data_warning = None
    path = config.PUBLIC_FACILITIES_PATH
    if path.exists():
        try:
            mtime = path.stat().st_mtime
            df = load_public(str(path), mtime)
            coords = [c for r in routes for c in r["coords"]]
            coverage, light_coverage = load_coverage(str(path), mtime)
            return "public", fac.filter_bbox(df, bbox(coords, margin_m=150)), coverage, light_coverage
        except Exception as e:  # 파일 형식 문제 → 데모로 대체하고 알려준다
            S.data_warning = f"공공데이터 파일을 읽지 못해 가상 시설로 대신했어요: {e}"
    return "demo", fac.make_demo_facilities(routes, S.start), None, None


@st.cache_data(ttl=86400, show_spinner="AI 설명을 만드는 중…")
def cached_gemini(payload_json, api_key, model):
    """같은 계산 결과면 Gemini를 다시 부르지 않는다 (슬라이더를 움직일 때마다 호출 방지)."""
    return explain.call_gemini(payload_json, api_key, model)


@st.cache_data(ttl=86400, show_spinner="AI가 답을 쓰는 중…")
def cached_ask(payload_json, question, api_key, model):
    return explain.call_gemini_ask(payload_json, question, api_key, model)


@st.cache_data(ttl=3600, show_spinner="장소를 찾는 중…")
def cached_places(keyword, app_key, bias=None):
    return sr.search_places(keyword, app_key, bias=bias)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_police(center, app_key):
    return sr.find_police(center, app_key)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_stores(center, radius_km, app_key):
    return sr.find_stores(center, app_key, radius_km=radius_km)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_address(lat, lon, app_key):
    return sr.reverse_geocode(lat, lon, app_key)


@st.cache_data(show_spinner=False)
def cached_gu_summary(path_str: str, modified: float):
    return insights.gu_summary(load_public(path_str, modified))


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
    facility_source, facilities, coverage, light_coverage = prepare_facilities(routes)
    police, stores = [], None
    if tmap_key:  # 지구대·파출소·편의점은 참고 정보라 실패해도 경로 비교는 계속한다
        mid = ((S.start[0] + S.end[0]) / 2, (S.start[1] + S.end[1]) / 2)
        center = (round(mid[0], 3), round(mid[1], 3))
        try:
            police = cached_police(center, tmap_key)
        except sr.SearchError:
            police = []
        # 경로 전체가 들어가는 반경 (TMAP은 km 단위 정수, 1~3km)
        reach_m = max(haversine_m(*center, *c) for r in routes for c in r["coords"])
        try:
            stores = cached_stores(center, min(3, max(1, -(-int(reach_m + 100) // 1000))), tmap_key)
        except sr.SearchError:
            stores = None
    S.result = {
        "routes": routes,
        "facilities": facilities,
        "route_source": route_source,
        "facility_source": facility_source,
        "coverage": coverage,
        "light_coverage": light_coverage,
        "police": police,
        "stores": stores,      # None = 찾지 못함(키 없음 등), [] = 근처에 없음
    }
    S.error = None
    S.search_id += 1


def _place_word(name: str | None, fallback: str) -> str:
    """메시지에 쓸 장소 이름. '지도에서 고른 위치'처럼 이름이 없는 곳은 '출발지'·'도착지'로."""
    return fallback if not name or name in (texts.MAP_PICK_NAME, texts.SHARED_NAME) else name


def _parse_point(text: str | None):
    """'35.2316,129.0846' → (35.2316, 129.0846). 한국 범위를 벗어나거나 형식이 틀리면 None."""
    try:
        lat, lon = (float(v) for v in (text or "").split(","))
    except ValueError:
        return None
    return (round(lat, 6), round(lon, 6)) if 33 <= lat <= 39 and 124 <= lon <= 132 else None


def share_params(route_id: str | None = None) -> dict:
    params = {"from": f"{S.start[0]},{S.start[1]}", "to": f"{S.end[0]},{S.end[1]}"}
    # 검색한 장소 이름만 넣는다 ('현재 위치'는 받는 사람에게는 틀린 말이라 뺀다 → 링크도 짧아진다)
    for key, name in (("fn", S.start_name), ("tn", S.end_name)):
        if _place_word(name, "") and name != texts.MY_LOCATION_NAME:
            params[key] = name
    if route_id:
        params["r"] = route_id
    return params


def share_url(route_id: str | None = None) -> str | None:
    """지금 출발·도착(과 고른 경로)이 담긴 주소. 주소창의 서버 이름으로 만든다."""
    if S.start is None or S.end is None:
        return None
    query = urlencode(share_params(route_id))
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
        qp = dict(st.query_params)  # set_point가 주소를 지우므로 먼저 읽어 둔다
        set_point("start", qp_start, qp.get("fn") or texts.SHARED_NAME)
        set_point("end", qp_end, qp.get("tn") or texts.SHARED_NAME)
        run_search()
        S.loc_msg = texts.SHARED_OPENED
        if S.result:  # 보낸 사람이 고른 경로를 먼저 보여 준다
            S.shared_pick = (S.search_id, qp.get("r"))


# 검색칸 글자를 지정된 장소 이름에 맞춘다 (위젯을 만들기 전에만 바꿀 수 있다)
for _w in ("start", "end"):
    if S.get(f"q_sync_{_w}"):
        S[f"q_{_w}"] = S.get(f"{_w}_name") or ""
        S[f"q_sync_{_w}"] = False

# ---------------------------------------------------------------- 화면: 상단
ui.inject_css()
tmap_key = get_secret("TMAP_APP_KEY")
vworld_key = get_secret("VWORLD_API_KEY")

expected_fac_source = S.result["facility_source"] if S.result else (
    "public" if config.PUBLIC_FACILITIES_PATH.exists() else "demo")
expected_route_source = S.result["route_source"] if S.result else ("tmap" if tmap_key else "demo")
fac_counts = None
if expected_fac_source == "public":
    try:
        _p = config.PUBLIC_FACILITIES_PATH
        fac_counts = load_public(str(_p), _p.stat().st_mtime)["kind"].value_counts().to_dict()
    except Exception:
        fac_counts = None
is_demo, data_md = ui.banner_text(expected_route_source, expected_fac_source, fac_counts)
with st.container(key="headbar"):
    c_head, c_sos = st.columns([5, 1.25], vertical_alignment="center")
    with c_head:
        st.markdown(ui.header_html(is_demo), unsafe_allow_html=True)
    with c_sos:
        with st.popover(texts.SOS_BUTTON):
            st.link_button("📞 112 전화하기", "tel:112", type="primary")
            if S.my_pos:
                place = S.my_addr or f"위도 {S.my_pos[0]:.5f}, 경도 {S.my_pos[1]:.5f}"
                sos_text = texts.SOS_SMS.format(place=place, lat=S.my_pos[0], lon=S.my_pos[1])
            else:
                sos_text = texts.SOS_SMS_NO_LOC
            st.link_button("💬 112 문자 신고", "sms:112?&body=" + quote(sos_text))
            st.caption(sos_text.replace("\n", "  \n"))
            if get_geolocation is not None:
                st.button(texts.SOS_LOCATE, key="btn_sos_locate", on_click=start_locating, args=("sos",))
            st.caption(texts.SOS_HELP + " " + texts.SOS_LOC_NOTE)

# ---------------------------------------------------------------- 검색 패널
with st.container(border=True, key="searchbox"):
    if tmap_key:
        def _locate_btn():
            if get_geolocation is not None:
                st.button("📍", key="btn_locate", help=texts.MY_LOCATION_BUTTON, on_click=start_locating,
                          args=("start",))

        def _swap_btn():
            st.button("⇅", key="btn_swap", help="출발·도착 바꾸기", on_click=swap_points,
                      disabled=S.start is None and S.end is None)

        search_row("start", _locate_btn)
        search_row("end", _swap_btn)
    else:  # 장소 검색이 없으면 지도 클릭으로만 지정
        for _w in ("start", "end"):
            _name = S.get(f"{_w}_name")
            st.markdown(f'{ui.point_label(_w)}<div class="sw-hint">{escape(_name) if _name else "지도에서 눌러 지정"}</div>',
                        unsafe_allow_html=True)
    c_hint, c_reset = st.columns([5, 1.3], vertical_alignment="center")
    with c_hint:
        hint = (texts.PICK_GUIDE_START if S.start is None else
                texts.PICK_GUIDE_END if S.end is None else texts.PICK_GUIDE_READY)
        st.markdown(f'<div class="sw-hint">{hint}</div>', unsafe_allow_html=True)
    with c_reset:
        st.button("↺ " + texts.RESET_BUTTON, key="btn_reset", on_click=reset,
                  disabled=S.start is None and S.end is None)

# ---------------------------------------------------------------- 추천 기준 + 설정
if streamlit_js_eval is not None and S.get("browser_hour") is None:
    # '밤'은 보는 사람 기준이라 브라우저 시각을 쓴다 (보이지 않는 부품)
    _h = streamlit_js_eval(js_expressions="new Date().getHours()", key="browser_hour_js")
    if isinstance(_h, (int, float)):
        S.browser_hour = int(_h)
_hour = S.get("browser_hour")
if _hour is None:
    _hour = datetime.now(KST).hour  # 아직 모르면 한국 시간
if not S.get("night_touched"):  # 직접 바꾸기 전까지는 시각에 맞춰 자동
    S["night"] = _hour >= config.NIGHT_HOURS[0] or _hour < config.NIGHT_HOURS[1]
S.setdefault("radius", config.DEFAULT_RADIUS_M)

providers = (["tmap"] if tmap_key else []) + ["vworld"]
with st.container(key="modebar"):
    c_mode, c_set = st.columns([4, 1.4], vertical_alignment="center")
    with c_mode:
        mode = st.segmented_control(
            "추천 기준", options=list(recommend.MODES), label_visibility="collapsed",
            format_func=lambda k: recommend.MODES[k]["short"],
            default=recommend.DEFAULT_MODE, key="mode",
        ) or recommend.DEFAULT_MODE
    with c_set:
        # 라벨을 고정해 둬야 반경을 바꿀 때 설정 창이 닫히지 않는다
        with st.popover("⚙️ 설정"):
            radius = st.slider(
                "분석 반경 (m)", config.RADIUS_OPTIONS_M[0], config.RADIUS_OPTIONS_M[1], step=10, key="radius",
                help="경로에서 이 거리 안에 있는 시설을 셉니다. 검증된 '안전 반경'이 아닌 분석용 값이에요.",
            )
            default_provider = config.MAP_PROVIDER if config.MAP_PROVIDER in providers else providers[0]
            provider = st.segmented_control(
                "지도", options=providers, default=default_provider, key="map_provider",
                format_func=lambda p: {"tmap": "TMAP 지도",
                                       "vworld": "브이월드 지도" if vworld_key else "기본 지도"}[p],
            ) or default_provider
            night = False
            if provider == "tmap" or vworld_key:  # 야간 지도는 TMAP과 브이월드에서만
                night = st.toggle("🌙 야간 지도", key="night", on_change=lambda: S.update(night_touched=True))

# ---------------------------------------------------------------- 알림
if S.locating and get_geolocation is not None:   # '현재 위치를 출발지로': 위치를 기다린다
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
            S.my_pos = point
            S.my_addr = cached_address(round(point[0], 5), round(point[1], 5), tmap_key) if tmap_key else None
            if S.locate_for == "sos":   # 긴급 문자에만 쓴다 (출발지는 그대로)
                S.loc_msg = "🚨 긴급 문자에 지금 위치를 넣었어요. 맨 위 '🚨 긴급'을 다시 눌러 보내세요."
            else:
                set_point("start", point, texts.MY_LOCATION_NAME)
                far_km = haversine_m(*config.REGION_CENTER, *point) / 1000
                if far_km > config.REGION_RADIUS_KM:
                    S.loc_msg = texts.LOCATION_FAR.format(km=far_km)
        st.rerun()
if S.loc_msg:
    st.info(S.loc_msg)
if is_demo:
    st.caption("⚠️ " + data_md.replace("\n- ", " · ").lstrip("- "))

# 두 곳이 정해지면 바로 경로를 찾는다 (지도 앱처럼 버튼 없이)
if S.start and S.end and S.result is None and S.error is None:
    with st.spinner("경로를 찾는 중…"):
        run_search()
if S.error:
    st.error(S.error)
if S.data_warning:
    st.warning(S.data_warning)

map_slot = st.container()   # 지도는 결과 계산 후 이 자리에 그린다
legend_slot = st.container()

# ---------------------------------------------------------------- 결과
result = S.result
selected_id = None
near_ids: list[str] = []
gap_segments: list = []
dark_segments: list = []
police: list = []
near_stores = []

if result:
    routes = result["routes"]
    demo_fac = result["facility_source"] == "demo"

    memo_key = (S.search_id, radius)
    if S.get("metrics_key") != memo_key:  # 같은 탐색·반경이면 다시 계산하지 않는다
        S.metrics = [analysis.analyze_route(r, result["facilities"], radius, result.get("coverage"),
                                            result.get("light_coverage")) for r in routes]
        S.metrics_key = memo_key
    metrics = S.metrics
    scored = recommend.score_routes(metrics, mode)
    rec_id = scored["recommended_id"]
    all_stores = result.get("stores")
    near_stores: list = []
    if all_stores is not None:   # 편의점: 반경 안 개수만 카드에 (점수에는 넣지 않음)
        for row, route in zip(scored["rows"], routes):
            found = analysis.places_near_route(route["coords"], all_stores, radius)
            row["stores"] = len(found)
            near_stores += [p for p in found if p not in near_stores]

    route_ids = [r["id"] for r in routes]
    shared_sid, shared_rid = S.get("shared_pick") or (None, None)
    default_pick = shared_rid if shared_sid == S.search_id and shared_rid in route_ids else rec_id
    if len(routes) > 1:
        selected_id = st.segmented_control(
            "지도에서 강조할 경로", options=route_ids, label_visibility="collapsed",
            format_func=lambda i: f"경로 {i}" + (" ★추천" if i == rec_id else ""),
            default=default_pick, key=f"pick_{S.search_id}",
        ) or rec_id
    else:
        selected_id = rec_id
        st.caption("서로 다른 경로가 하나뿐이라 그 경로만 보여드려요.")

    rows_by_id = {row["route_id"]: row for row in scored["rows"]}
    near_ids = rows_by_id[selected_id]["near_ids"]
    gap_segments = rows_by_id[selected_id]["gap_segments"]
    dark_segments = rows_by_id[selected_id].get("dark_segments") or []
    police = result.get("police") or []

    # 선택한 경로 카드를 맨 앞에 (휴대폰에서 넘기지 않아도 보이게)
    ordered = sorted(enumerate(routes), key=lambda ir: ir[1]["id"] != selected_id)
    ui.route_strip([
        ui.route_card_html(rows_by_id[route["id"]], route, config.ROUTE_COLORS[i % len(config.ROUTE_COLORS)],
                           recommended=route["id"] == rec_id, selected=route["id"] == selected_id,
                           facilities_are_demo=demo_fac,
                           nearest_police=analysis.nearest_place(route["coords"], police))
        for i, route in ordered
    ])

    # 귀가 알림: 가족·친구에게 보낼 글 (상대방은 앱 설치 없이 링크로 경로를 본다)
    sel_route = next(r for r in routes if r["id"] == selected_id)
    arrive = datetime.now(KST) + timedelta(seconds=sel_route["duration_s"])
    notice = texts.HOME_NOTICE.format(
        start=_place_word(S.start_name, "출발지"), end=_place_word(S.end_name, "도착지"), route=selected_id,
        label=sel_route["label"], duration=explain.fmt_duration(sel_route["duration_s"]),
        distance=explain.fmt_distance(sel_route["distance_m"]),
        arrive=f"{'오전' if arrive.hour < 12 else '오후'} {(arrive.hour % 12) or 12}:{arrive.minute:02d}",
        url=share_url(selected_id) or "",
    )
    with st.popover("📨 귀가 알림 보내기"):
        st.caption(texts.HOME_NOTICE_HELP)
        st.code(notice, language=None, wrap_lines=True)
        st.link_button("💬 문자로 보내기", "sms:?&body=" + quote(notice))
        st.caption(texts.SHARE_NOTE)

    basic_text = explain.build_basic_explanation(scored, radius, demo_fac)
    gemini_key = get_secret("GEMINI_API_KEY")
    mode_label = recommend.MODES[mode]["label"]
    payload = explain.build_ai_payload(scored, routes, radius, mode_label, demo_fac)
    ai_text, ai_issue = explain.get_ai_explanation(payload, gemini_key, config.GEMINI_MODEL, caller=cached_gemini)
    with st.expander(f"💬 추천: 경로 {rec_id} · {mode_label} · 반경 {radius}m", expanded=True):
        st.markdown(ai_text or basic_text)
        if ai_text:
            st.caption("설명 출처: Gemini · Python이 계산한 숫자만 사용하도록 확인했어요")
        else:
            reason = f" (AI 설명을 쓰지 못한 이유: {ai_issue})" if gemini_key else ""
            st.caption("설명 출처: Python 계산 결과로 자동 생성한 기본 설명" + reason)

        # ---- AI에게 물어보기: 같은 탐색·기준·반경일 때만 대화를 이어 간다
        qa_key = (S.search_id, mode, radius)
        if S.get("qa_key") != qa_key:
            S.qa_key, S.qa = qa_key, []
        if S.get("pending_q"):
            question, S.pending_q = S.pending_q, None
            kind = explain.quick_kind(question)
            text, issue = explain.ask_ai(question, payload, gemini_key, config.GEMINI_MODEL,
                                         caller=lambda pj, q, k, m: cached_ask(pj, q, k, m))
            if text:
                source = "Gemini · 계산된 숫자만 썼는지 확인했어요"
            elif kind:
                text = explain.quick_answer(kind, scored, radius, mode_label, demo_fac)
                source = "Python 계산 결과로 만든 답변" + (f" (AI를 쓰지 못한 이유: {issue})" if gemini_key else "")
            elif not gemini_key:
                text, source = texts.ASK_NO_KEY, ""
            else:
                text, source = texts.ASK_FAILED.format(issue=issue), ""
            S.qa = (S.qa + [(question, text, source)])[-4:]
        st.markdown(f"**{texts.ASK_TITLE}**")
        for question, text, source in S.qa:
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant", avatar="🛡️"):
                st.markdown(text)
                if source:
                    st.caption(source)
        quick_key = f"quick_{S.search_id}"
        st.pills("예시 질문", options=list(explain.QUICK_QUESTIONS), key=quick_key,
                 format_func=lambda k: explain.QUICK_QUESTIONS[k], label_visibility="collapsed",
                 on_change=pick_quick, args=(quick_key,))
        if gemini_key:
            st.text_input("질문", key="ask_text", label_visibility="collapsed", max_chars=explain.ASK_MAX_CHARS,
                          placeholder=texts.ASK_PLACEHOLDER, on_change=submit_question)
            st.caption(texts.ASK_PRIVACY)
        else:
            st.caption(texts.ASK_NO_KEY)

    # 경로 공유: 주소창에도 같은 값을 넣어 두면 브라우저 '공유' 버튼으로도 보낼 수 있다
    st.query_params.update(share_params(selected_id))
    with st.expander("🔗 공유 · 점수 계산 · 데이터 한계"):
        t_share, t_score, t_basic, t_data, t_help = st.tabs(["공유", "점수 계산", "기본 설명", "데이터", "사용 방법"])
        with t_share:
            st.code(share_url(selected_id) or "", language=None)
            st.caption(texts.SHARE_NOTE)
        with t_score:
            st.markdown(recommend.formula_markdown(mode))
        with t_basic:
            st.markdown(basic_text)
        with t_data:
            st.markdown(data_md)
            st.markdown("**공공데이터로 알 수 없는 것**\n" + "\n".join(f"- {item}" for item in texts.DATA_LIMITS))
        with t_help:
            st.markdown(texts.HOW_TO_BODY)
else:
    with st.expander("ⓘ 사용 방법 · 데이터 출처"):
        st.markdown(texts.HOW_TO_BODY)
        st.markdown(data_md)

# ---------------------------------------------------------------- 지도 (위에 비워 둔 자리)
with map_slot:
    map_facilities = None
    if result:
        # 보안등은 수가 많아, 어느 경로든 반경 안에 든 것만 지도에 그린다 (휴대폰에서도 가볍게)
        df_all = result["facilities"]
        near_any = set().union(*(m["near_ids"] for m in S.get("metrics") or []))
        map_facilities = df_all[(df_all["kind"] != "light") | df_all["id"].astype(str).isin(near_any)]
    map_parts = dict(
        start=S.start, end=S.end, start_name=S.start_name, end_name=S.end_name,
        routes=result["routes"] if result else None,
        selected_id=selected_id,
        facilities=map_facilities,
        near_ids=near_ids,
        gap_segments=gap_segments,
        dark_segments=dark_segments,
        police=police,
        stores=near_stores,
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
    ui.legend(radius if result else None, has_police=bool(police), has_gaps=bool(gap_segments),
              has_lights=has_lights, has_dark=bool(dark_segments), has_stores=bool(near_stores))

# ---------------------------------------------------------------- 데이터로 본 부산
summary = None
if expected_fac_source == "public":
    try:
        _p = config.PUBLIC_FACILITIES_PATH
        summary = cached_gu_summary(str(_p), _p.stat().st_mtime)
    except Exception:
        summary = None
if summary is not None and len(summary):
    with st.expander(texts.DATA_VIEW_TITLE):
        for line in insights.insight_lines(summary):
            st.markdown(f"- {line}")
        kind = st.segmented_control("시설", options=list(insights.KIND_LABEL), default="cctv", key="dv_kind",
                                    format_func=lambda k: insights.KIND_LABEL[k]) or "cctv"
        per_area = st.toggle("면적(1㎢)당으로 보기", value=True, key="dv_per_area")
        value_col = f"{kind}_km2" if per_area else kind
        value_name = f"{insights.KIND_LABEL[kind]} " + ("1㎢당 (곳)" if per_area else "개수 (곳)")
        chart_df = summary[["구", value_col]].rename(columns={value_col: value_name})
        try:
            import altair as alt
            chart = (alt.Chart(chart_df).mark_bar(color="#2563EB", cornerRadiusEnd=3)
                     .encode(x=alt.X(f"{value_name}:Q", title=value_name),
                             y=alt.Y("구:N", sort="-x", title=None),
                             tooltip=["구", value_name])
                     .properties(height=420, width="container"))
            st.altair_chart(chart)
        except Exception:   # altair가 없으면 기본 막대그래프
            st.bar_chart(chart_df.set_index("구"))
        table = summary.rename(columns={"cctv": "CCTV", "bell": "비상벨", "light": "보안등", "면적": "면적(㎢)",
                                        "cctv_km2": "CCTV/㎢", "bell_km2": "비상벨/㎢", "light_km2": "보안등/㎢"})
        st.dataframe(table, hide_index=True)
        st.caption(texts.DATA_VIEW_NOTE)

ui.footer()

# ---------------------------------------------------------------- 지도 클릭 처리
clicked = (map_data or {}).get("last_clicked")
if clicked:
    point = (round(clicked["lat"], 6), round(clicked["lng"], 6))
    if point != S.last_click:
        S.last_click = point
        handle_click(point)
        st.rerun()
