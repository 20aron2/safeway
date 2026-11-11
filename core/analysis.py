"""경로 주변 안전시설 분석 (담당: 공간 분석).

analyze_route()는 경로 하나와 시설 표를 받아 아래 결과를 돌려준다.

    {
        "route_id": "A",
        "distance_m": 1234.5,
        "duration_s": 1122,
        "radius_m": 50,
        "cctv": 4,              # 반경 안 CCTV 설치 지점 수 (같은 지점은 1번만)
        "bell": 1,              # 반경 안 비상벨 수
        "total": 5,             # CCTV + 비상벨
        "per_km": 4.05,         # 경로 1km당 CCTV·비상벨 수
        "light": 30,            # 반경 안 보안등 수 (따로 센다)
        "light_per_km": 24.3,
        "longest_gap_m": 320.0, # 반경 안에 시설이 하나도 없는 가장 긴 연속 구간
        "gap_segments": [{"length_m": 320.0, "coords": [...]}, ...],  # 지도 표시용 (100m 이상)
        "near_ids": [...],      # 반경 안 시설 id 목록 (지도 강조용)
        "longest_dark_m": 80.0, # 30m 안에 보안등이 없는 가장 긴 구간 (보안등 데이터가 없으면 None)
        "dark_segments": [...], # 지도 표시용 (50m 이상)
    }
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config
from .facilities import cell_of, filter_bbox
from .geo import EARTH_RADIUS_M, bbox, densify, haversine_m, point_to_polyline_m


def _xy(lats, lons, lat0: float, lon0: float):
    """위경도를 (lat0, lon0) 기준 평면 좌표(m)로. 수 km 안에서는 오차가 수 cm 수준."""
    lats, lons = np.asarray(lats, dtype=float), np.asarray(lons, dtype=float)
    x = np.radians(lons - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    y = np.radians(lats - lat0) * EARTH_RADIUS_M
    return x, y


def distances_to_route(lats, lons, coords) -> np.ndarray:
    """여러 지점에서 경로(선)까지의 최단 거리(m)를 한 번에 계산한다."""
    lats = np.asarray(lats, dtype=float)
    if len(lats) == 0:
        return np.zeros(0)
    c = np.asarray(coords, dtype=float)
    lat0, lon0 = float(c[:, 0].mean()), float(c[:, 1].mean())
    px, py = _xy(lats, lons, lat0, lon0)
    cx, cy = _xy(c[:, 0], c[:, 1], lat0, lon0)
    if len(c) == 1:
        return np.hypot(px - cx[0], py - cy[0])
    ax, ay, bx, by = cx[:-1], cy[:-1], cx[1:], cy[1:]
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    seg2 = np.where(seg2 == 0, 1e-12, seg2)
    best = np.full(len(px), np.inf)
    chunk = max(1, 2_000_000 // len(ax))  # 메모리를 아끼려고 나눠서 계산
    for i in range(0, len(px), chunk):
        qx, qy = px[i:i + chunk, None], py[i:i + chunk, None]
        t = np.clip(((qx - ax) * dx + (qy - ay) * dy) / seg2, 0.0, 1.0)
        d = np.hypot(qx - (ax + t * dx), qy - (ay + t * dy)).min(axis=1)
        best[i:i + chunk] = d
    return best


def outside_ratio(coords, coverage, step_m: float = 20.0) -> float:
    """경로 중 시설 데이터 범위 밖에 있는 비율 (0~1). 범위 정보가 없으면 0."""
    if not coverage:
        return 0.0
    pts = densify(coords, step_m)
    return sum(1 for p in pts if cell_of(p[0], p[1]) not in coverage) / len(pts)


def analyze_route(route: dict, facilities: pd.DataFrame, radius_m: float,
                  coverage: frozenset | None = None, light_coverage: frozenset | None = None) -> dict:
    coords = route["coords"]
    dark = dark_runs(coords, facilities, light_coverage)

    # 1차: 경로를 감싼 사각형(+반경) 안의 시설만 후보로
    cand = filter_bbox(facilities, bbox(coords, margin_m=radius_m)) if len(facilities) else facilities

    # 2차: 경로까지 실제 거리(m)가 반경 이내인 시설 (numpy로 한 번에 계산)
    if len(cand):
        dist = distances_to_route(cand["lat"].to_numpy(), cand["lon"].to_numpy(), coords)
        near_rows = list(cand[dist <= radius_m].itertuples(index=False))
    else:
        near_rows = []

    # 같은 시설 id는 한 번만 센다
    seen: dict[str, object] = {}
    for row in near_rows:
        seen.setdefault(str(row.id), row)
    near = list(seen.values())

    cctv = sum(1 for r in near if r.kind == "cctv")
    bell = sum(1 for r in near if r.kind == "bell")
    light = sum(1 for r in near if r.kind == "light")
    km = route["distance_m"] / 1000
    total = cctv + bell  # 보안등은 수가 훨씬 많아서 따로 센다
    # '시설 없는 구간'은 CCTV·비상벨 기준 (보안등은 별도 지표)
    gaps = gap_runs(coords, [r for r in near if r.kind in ("cctv", "bell")], radius_m)

    return {
        "route_id": route["id"],
        "distance_m": route["distance_m"],
        "duration_s": route["duration_s"],
        "radius_m": radius_m,
        "cctv": cctv,
        "bell": bell,
        "total": total,
        "per_km": total / km if km > 0 else 0.0,
        "light": light,
        "light_per_km": light / km if km > 0 else 0.0,
        "longest_gap_m": max((length for length, _ in gaps), default=0.0),
        # 지도에 빨간 점선으로 그릴 '시설 없는 구간' (짧은 구간은 생략)
        "gap_segments": [{"length_m": length, "coords": seg} for length, seg in gaps
                         if length >= config.GAP_DRAW_MIN_M],
        "near_ids": list(seen.keys()),
        # 시설 데이터가 없는 지역을 지나는 비율. 높으면 시설 수가 실제보다 적게 나온다.
        "outside_ratio": outside_ratio(coords, coverage),
        # 보안등 없는 구간 (분석 반경과 상관없이 LIGHT_REACH_M 기준)
        "longest_dark_m": None if dark is None else max((length for length, _ in dark), default=0.0),
        "dark_segments": [{"length_m": length, "coords": seg} for length, seg in (dark or [])
                          if length >= config.DARK_DRAW_MIN_M],
    }


def dark_runs(coords, facilities: pd.DataFrame, light_coverage: frozenset | None = None,
              reach_m: float = config.LIGHT_REACH_M) -> list[tuple[float, list]] | None:
    """보안등이 reach_m 안에 하나도 없는 연속 구간들. 보안등 데이터가 없으면 None.

    보안등 데이터 범위(light_coverage) 밖의 지점은 '모름'이라 어두운 구간으로 세지 않는다.
    """
    if not len(facilities) or not (facilities["kind"] == "light").any():
        return None
    lights = facilities[facilities["kind"] == "light"]
    cand = filter_bbox(lights, bbox(coords, margin_m=reach_m))
    near = list(cand[distances_to_route(cand["lat"].to_numpy(), cand["lon"].to_numpy(), coords)
                     <= reach_m].itertuples(index=False)) if len(cand) else []
    unknown = None
    if light_coverage:
        unknown = lambda p: cell_of(p[0], p[1]) not in light_coverage  # noqa: E731
    return gap_runs(coords, near, reach_m, unknown=unknown)


def gap_runs(coords, near_facilities, radius_m: float,
             step_m: float = config.GAP_SAMPLE_STEP_M, unknown=None) -> list[tuple[float, list]]:
    """반경 안에 시설이 하나도 없는 연속 구간들을 (길이 m, 좌표 목록)으로 돌려준다.

    unknown(지점) 이 참인 지점은 데이터가 없어 판단하지 않는다 (구간을 끊는다).
    """
    samples = densify(coords, step_m)
    if near_facilities:
        s = np.asarray(samples, dtype=float)
        lat0, lon0 = float(s[:, 0].mean()), float(s[:, 1].mean())
        sx, sy = _xy(s[:, 0], s[:, 1], lat0, lon0)
        fx, fy = _xy([f.lat for f in near_facilities], [f.lon for f in near_facilities], lat0, lon0)
        d2 = (sx[:, None] - fx[None, :]) ** 2 + (sy[:, None] - fy[None, :]) ** 2
        covered = list((d2 <= radius_m * radius_m).any(axis=1))
    else:
        covered = [False] * len(samples)
    if unknown is not None:
        covered = [c or unknown(p) for c, p in zip(covered, samples)]
    runs: list[tuple[float, list]] = []
    length, seg = 0.0, []
    for i in range(1, len(samples)):
        if not covered[i - 1] and not covered[i]:
            if not seg:
                seg = [samples[i - 1]]
            seg.append(samples[i])
            length += haversine_m(samples[i - 1][0], samples[i - 1][1], samples[i][0], samples[i][1])
        elif seg:
            runs.append((length, seg))
            length, seg = 0.0, []
    if seg:
        runs.append((length, seg))
    return runs


def longest_gap_m(coords, near_facilities, radius_m: float,
                  step_m: float = config.GAP_SAMPLE_STEP_M) -> float:
    """반경 안에 시설이 하나도 없는 가장 긴 연속 구간의 길이(m)."""
    return max((length for length, _ in gap_runs(coords, near_facilities, radius_m, step_m)), default=0.0)


def nearest_place(coords, places) -> dict | None:
    """경로에서 가장 가까운 장소와 그 거리(m). places가 비면 None."""
    best = None
    for p in places:
        d = point_to_polyline_m(p["lat"], p["lon"], coords)
        if best is None or d < best["dist_m"]:
            best = {"name": p["name"], "dist_m": d}
    return best


def places_near_route(coords, places, radius_m: float) -> list[dict]:
    """경로에서 radius_m 안에 있는 장소들 (편의점처럼 점수에 넣지 않는 참고 정보용)."""
    if not places:
        return []
    lats = np.array([p["lat"] for p in places], dtype=float)
    lons = np.array([p["lon"] for p in places], dtype=float)
    dist = distances_to_route(lats, lons, coords)
    return [p for p, d in zip(places, dist) if d <= radius_m]
