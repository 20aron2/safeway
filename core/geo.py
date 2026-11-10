"""거리 계산 도구 모음 (담당: 공간 분석).

위도·경도 숫자 차이를 그대로 거리로 쓰지 않고, 모든 결과를 '미터' 단위로 계산한다.
- 두 점 사이 거리: 하버사인(haversine) 공식
- 점과 경로(선) 사이 거리: 기준점 주변을 평면(미터 좌표)으로 펼친 뒤 계산
  (수 km 이내 도보 경로에서는 오차가 수 cm 수준이라 충분히 정확하다)

좌표는 항상 (위도, 경도) 순서의 튜플로 다룬다.
"""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8

LatLon = tuple[float, float]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 지점 사이의 실제 거리(m)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def polyline_length_m(coords: list[LatLon]) -> float:
    """경로(점 목록)의 전체 길이(m)."""
    return sum(
        haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(coords, coords[1:])
    )


def _to_xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """(lat0, lon0)을 원점으로 하는 평면 좌표(m)로 변환."""
    x = math.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * EARTH_RADIUS_M
    return x, y


def _point_segment_distance(px: float, py: float, ax: float, ay: float,
                            bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def point_to_polyline_m(lat: float, lon: float, coords: list[LatLon]) -> float:
    """한 지점에서 경로(선)까지의 최단 거리(m)."""
    if not coords:
        return math.inf
    if len(coords) == 1:
        return haversine_m(lat, lon, coords[0][0], coords[0][1])
    pts = [_to_xy(c[0], c[1], lat, lon) for c in coords]  # 시설 위치를 원점으로
    return min(
        _point_segment_distance(0.0, 0.0, a[0], a[1], b[0], b[1])
        for a, b in zip(pts, pts[1:])
    )


def offset_point(lat: float, lon: float, east_m: float, north_m: float) -> LatLon:
    """지점에서 동쪽/북쪽으로 몇 m 이동한 좌표."""
    new_lat = lat + math.degrees(north_m / EARTH_RADIUS_M)
    new_lon = lon + math.degrees(east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
    return new_lat, new_lon


def bbox(coords: list[LatLon], margin_m: float = 0.0) -> tuple[float, float, float, float]:
    """경로를 감싸는 사각형 (최소위도, 최소경도, 최대위도, 최대경도). margin_m만큼 넓힌다."""
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    if margin_m:
        min_lat, min_lon = offset_point(min_lat, min_lon, -margin_m, -margin_m)
        max_lat, max_lon = offset_point(max_lat, max_lon, margin_m, margin_m)
    return min_lat, min_lon, max_lat, max_lon


def densify(coords: list[LatLon], step_m: float = 10.0) -> list[LatLon]:
    """경로 위에 step_m 간격으로 점을 촘촘히 찍는다 (구간 분석용)."""
    if len(coords) < 2:
        return list(coords)
    out: list[LatLon] = [coords[0]]
    for a, b in zip(coords, coords[1:]):
        seg = haversine_m(a[0], a[1], b[0], b[1])
        n = max(1, int(math.ceil(seg / step_m)))
        for i in range(1, n + 1):
            t = i / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def route_gap_m(a: list[LatLon], b: list[LatLon], step_m: float = 20.0) -> float:
    """두 경로가 얼마나 다른지(m). 서로 상대 경로까지의 평균 거리 중 큰 값.

    값이 작으면(예: 25m 미만) 사실상 같은 경로로 본다.
    """
    def mean_dist(src: list[LatLon], dst: list[LatLon]) -> float:
        pts = densify(src, step_m)
        return sum(point_to_polyline_m(p[0], p[1], dst) for p in pts) / len(pts)

    return max(mean_dist(a, b), mean_dist(b, a))
