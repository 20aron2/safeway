"""도보 경로 후보 만들기 (담당: 경로 탐색).

모든 경로는 아래 형식의 딕셔너리로 주고받는다.

    {
        "id": "A",                      # 화면 표시용 이름 (A, B, C)
        "label": "가상 경로 · 남북 먼저",  # 경로 설명
        "coords": [(위도, 경도), ...],    # 경로 좌표 목록
        "distance_m": 1234.5,           # 총 거리 (m)
        "duration_s": 1122,             # 예상 소요 시간 (초)
        "source": "demo" | "tmap",      # 데이터 출처
    }

지금은 데모(가상) 경로만 만든다. TMAP 실제 경로는 STEP 4에서 fetch_tmap_routes()를 채운다.
"""
from __future__ import annotations

import math

from . import config
from .geo import LatLon, densify, haversine_m, offset_point, polyline_length_m, route_gap_m


class RouteError(Exception):
    """사용자에게 그대로 보여줄 수 있는 경로 오류."""


def _make_route(label: str, waypoints: list[LatLon], source: str) -> dict:
    coords = densify(waypoints, step_m=30)
    dist = polyline_length_m(coords)
    return {
        "id": "",
        "label": label,
        "coords": coords,
        "distance_m": dist,
        "duration_s": round(dist / config.DEMO_WALK_SPEED_MPS),
        "source": source,
    }


def make_demo_routes(start: LatLon, end: LatLon) -> list[dict]:
    """출발지·도착지를 잇는 가상 경로 3개. 실제 길을 따르지 않는 직선 조합이다."""
    (s_lat, s_lon), (e_lat, e_lon) = start, end
    # 도착지가 출발지 기준 동/북쪽으로 몇 m인지
    east = haversine_m(s_lat, s_lon, s_lat, e_lon) * (1 if e_lon >= s_lon else -1)
    north = haversine_m(s_lat, s_lon, e_lat, s_lon) * (1 if e_lat >= s_lat else -1)
    d = math.hypot(east, north)

    # 사선 경로: 중간 지점을 진행 방향의 옆으로 밀어낸 꺾인 직선
    detour = min(0.3 * d, 300.0)
    mid = ((s_lat + e_lat) / 2, (s_lon + e_lon) / 2)
    via = offset_point(mid[0], mid[1], -north / d * detour, east / d * detour)

    return [
        _make_route("가상 경로 · 남북 먼저", [start, (e_lat, s_lon), end], "demo"),
        _make_route("가상 경로 · 동서 먼저", [start, (s_lat, e_lon), end], "demo"),
        _make_route("가상 경로 · 사선 경유", [start, via, end], "demo"),
    ]


TMAP_URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1&format=json"
# searchOption: 10 = 최단거리, 0 = 추천, 4 = 추천 + 대로 우선
TMAP_OPTIONS = [(10, "TMAP 최단거리"), (0, "TMAP 추천"), (4, "TMAP 대로 우선")]


def parse_tmap_response(data: dict, label: str) -> dict:
    """TMAP 응답(GeoJSON)에서 경로 좌표·거리·시간을 꺼낸다."""
    features = data.get("features") or []
    coords: list[LatLon] = []
    for f in features:
        geom = f.get("geometry") or {}
        if geom.get("type") == "LineString":
            for lon, lat in geom.get("coordinates", []):
                pt = (float(lat), float(lon))  # TMAP은 (경도, 위도) 순서
                if not coords or coords[-1] != pt:
                    coords.append(pt)
    if len(coords) < 2:
        raise RouteError("TMAP이 경로를 찾지 못했어요. 출발지나 도착지를 길 가까이로 옮겨 보세요.")
    props = (features[0].get("properties") or {}) if features else {}
    dist = float(props.get("totalDistance") or polyline_length_m(coords))
    secs = float(props.get("totalTime") or dist / config.DEMO_WALK_SPEED_MPS)
    return {"id": "", "label": label, "coords": coords,
            "distance_m": dist, "duration_s": round(secs), "source": "tmap"}


def _tmap_error_message(resp) -> str:
    if resp.status_code in (401, 403):
        return "TMAP 키가 올바르지 않거나 TMAP 사용 신청이 아직 처리되지 않았어요."
    if resp.status_code == 429:
        return "TMAP 무료 사용량을 넘었어요. 잠시 뒤나 내일 다시 시도해 주세요."
    try:
        msg = resp.json().get("error", {}).get("message")
    except ValueError:
        msg = None
    return f"TMAP 경로 요청이 실패했어요 (오류 {resp.status_code}{': ' + msg if msg else ''})."


def fetch_tmap_routes(start: LatLon, end: LatLon, app_key: str) -> list[dict]:
    """TMAP 보행자 경로 API를 탐색 옵션별로 호출한다. 일부만 실패하면 성공한 것만 쓴다."""
    import requests  # 데모 모드에서는 필요 없어서 여기서 불러온다

    headers = {"appKey": app_key.strip(), "Accept": "application/json",
               "Content-Type": "application/json"}
    base = {
        "startX": str(start[1]), "startY": str(start[0]),
        "endX": str(end[1]), "endY": str(end[0]),
        "startName": "start", "endName": "end",
        "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
    }
    routes, errors = [], []
    for option, label in TMAP_OPTIONS:
        try:
            resp = requests.post(TMAP_URL, headers=headers,
                                 json={**base, "searchOption": str(option)}, timeout=10)
        except requests.RequestException:
            errors.append("TMAP 서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요.")
            continue
        if resp.status_code != 200:
            errors.append(_tmap_error_message(resp))
            if resp.status_code in (401, 403, 429):
                break  # 키·사용량 문제는 다른 옵션도 똑같이 실패한다
            continue
        try:
            routes.append(parse_tmap_response(resp.json(), label))
        except (RouteError, ValueError) as e:
            errors.append(str(e) if isinstance(e, RouteError) else "TMAP 응답을 읽지 못했어요.")
    if not routes:
        raise RouteError(errors[0] if errors else "TMAP 경로를 받지 못했어요.")
    return routes


def dedupe_routes(routes: list[dict], threshold_m: float = config.DUPLICATE_ROUTE_M) -> list[dict]:
    """거의 같은 경로는 하나만 남긴다 (먼저 나온 경로 우선)."""
    kept: list[dict] = []
    for r in routes:
        if all(route_gap_m(r["coords"], k["coords"]) >= threshold_m for k in kept):
            kept.append(r)
    return kept


def get_routes(start: LatLon, end: LatLon, source: str = "demo", app_key: str | None = None) -> list[dict]:
    """경로 후보를 받아 검사·중복 제거 후 A, B, C 이름을 붙여 돌려준다."""
    if start is None or end is None:
        raise RouteError("출발지와 도착지를 모두 지정해 주세요.")
    trip = haversine_m(start[0], start[1], end[0], end[1])
    if trip < config.MIN_TRIP_M:
        raise RouteError(f"출발지와 도착지가 너무 가까워요 ({trip:.0f}m). 조금 더 떨어진 곳을 골라 주세요.")
    if trip > config.MAX_TRIP_M:
        raise RouteError(
            f"직선거리가 {trip / 1000:.1f}km예요. 도보 비교는 {config.MAX_TRIP_M / 1000:.0f}km 이내에서만 해요."
        )

    if source == "tmap":
        if not app_key:
            raise RouteError("TMAP API 키가 설정되지 않았어요.")
        candidates = fetch_tmap_routes(start, end, app_key)
    else:
        candidates = make_demo_routes(start, end)

    routes = dedupe_routes(candidates)
    if not routes:
        raise RouteError("경로를 찾지 못했어요. 위치를 바꿔 다시 시도해 주세요.")
    for rid, r in zip(config.ROUTE_IDS, routes):
        r["id"] = rid
    return routes[: len(config.ROUTE_IDS)]
