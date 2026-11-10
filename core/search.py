"""장소 이름으로 좌표 찾기 (TMAP 장소 통합검색).

search_places("부산대역", app_key) →
    [{"name": "부산대역 1호선", "address": "부산 금정구 ...", "lat": 35.23, "lon": 129.08,
      "dist_km": 0.4}, ...]

금정구 공공데이터만 있으므로, 부산대 부근에서 가까운 순서로 10km 안에서만 찾는다.
"""
from __future__ import annotations

from . import config
from .geo import haversine_m

POI_URL = "https://apis.openapi.sk.com/tmap/pois"
SEARCH_RADIUS_KM = 10
MAX_RESULTS = 15


class SearchError(Exception):
    """사용자에게 그대로 보여줄 수 있는 검색 오류."""


def _num(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v != 0 else None


def _address(poi: dict) -> str:
    new = ((poi.get("newAddressList") or {}).get("newAddress") or [])
    if new and new[0].get("fullAddressRoad"):
        return new[0]["fullAddressRoad"]
    parts = [poi.get("upperAddrName"), poi.get("middleAddrName"), poi.get("lowerAddrName")]
    return " ".join(p for p in parts if p)


def parse_poi_response(data: dict, center=config.DEFAULT_CENTER) -> list[dict]:
    """TMAP 검색 응답에서 이름·주소·좌표만 꺼낸다. 좌표가 없는 결과는 버린다."""
    pois = (((data or {}).get("searchPoiInfo") or {}).get("pois") or {}).get("poi") or []
    if isinstance(pois, dict):  # 결과가 1개면 배열이 아닐 수 있다
        pois = [pois]
    out, seen = [], set()
    for poi in pois:
        # 걸어서 가는 경로라 건물 출입구 좌표(front)를 먼저 쓰고, 없으면 중심 좌표(noor)
        lat = _num(poi.get("frontLat")) or _num(poi.get("noorLat"))
        lon = _num(poi.get("frontLon")) or _num(poi.get("noorLon"))
        name = (poi.get("name") or "").strip()
        if lat is None or lon is None or not name:
            continue
        key = (name, round(lat, 5), round(lon, 5))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "name": name,
            "address": _address(poi),
            "lat": lat,
            "lon": lon,
            "dist_km": haversine_m(center[0], center[1], lat, lon) / 1000,
        })
    return out


def search_places(keyword: str, app_key: str, center=config.DEFAULT_CENTER) -> list[dict]:
    import requests

    keyword = (keyword or "").strip()
    if len(keyword) < 2:
        raise SearchError("검색어를 두 글자 이상 입력해 주세요.")
    params = {
        "version": "1", "searchKeyword": keyword, "count": str(MAX_RESULTS),
        "searchtypCd": "R", "centerLat": str(center[0]), "centerLon": str(center[1]),
        "radius": str(SEARCH_RADIUS_KM),
        "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
    }
    headers = {"appKey": app_key.strip(), "Accept": "application/json"}
    try:
        resp = requests.get(POI_URL, params=params, headers=headers, timeout=10)
    except requests.RequestException:
        raise SearchError("TMAP 서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요.")
    if resp.status_code == 204 or not resp.content:
        return []
    if resp.status_code in (401, 403):
        raise SearchError("TMAP 키가 올바르지 않거나 장소 검색 사용 권한이 없어요.")
    if resp.status_code == 429:
        raise SearchError("TMAP 무료 사용량을 넘었어요. 잠시 뒤에 다시 시도해 주세요.")
    if resp.status_code != 200:
        raise SearchError(f"장소 검색이 실패했어요 (오류 {resp.status_code}).")
    try:
        return parse_poi_response(resp.json(), center)
    except ValueError:
        raise SearchError("검색 결과를 읽지 못했어요.")
