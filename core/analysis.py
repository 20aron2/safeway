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
    }
"""
from __future__ import annotations

import pandas as pd

from . import config
from .facilities import filter_bbox
from .geo import bbox, densify, haversine_m, point_to_polyline_m


def analyze_route(route: dict, facilities: pd.DataFrame, radius_m: float) -> dict:
    coords = route["coords"]

    # 1차: 경로를 감싼 사각형(+반경) 안의 시설만 후보로
    cand = filter_bbox(facilities, bbox(coords, margin_m=radius_m)) if len(facilities) else facilities

    # 2차: 경로까지 실제 거리(m)가 반경 이내인 시설
    near_rows = []
    for row in cand.itertuples(index=False):
        if point_to_polyline_m(row.lat, row.lon, coords) <= radius_m:
            near_rows.append(row)

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
    }


def gap_runs(coords, near_facilities, radius_m: float,
             step_m: float = config.GAP_SAMPLE_STEP_M) -> list[tuple[float, list]]:
    """반경 안에 시설이 하나도 없는 연속 구간들을 (길이 m, 좌표 목록)으로 돌려준다."""
    samples = densify(coords, step_m)
    covered = [
        any(haversine_m(p[0], p[1], f.lat, f.lon) <= radius_m for f in near_facilities)
        for p in samples
    ]
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
