"""경로 주변 안전시설 분석 (담당: 공간 분석).

analyze_route()는 경로 하나와 시설 표를 받아 아래 결과를 돌려준다.

    {
        "route_id": "A",
        "distance_m": 1234.5,
        "duration_s": 1122,
        "radius_m": 50,
        "cctv": 4,              # 반경 안 CCTV 설치 지점 수 (같은 지점은 1번만)
        "bell": 1,              # 반경 안 비상벨 수
        "total": 5,
        "per_km": 4.05,         # 경로 1km당 시설 수
        "longest_gap_m": 320.0, # 반경 안에 시설이 하나도 없는 가장 긴 연속 구간
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
    km = route["distance_m"] / 1000
    total = cctv + bell

    return {
        "route_id": route["id"],
        "distance_m": route["distance_m"],
        "duration_s": route["duration_s"],
        "radius_m": radius_m,
        "cctv": cctv,
        "bell": bell,
        "total": total,
        "per_km": total / km if km > 0 else 0.0,
        "longest_gap_m": longest_gap_m(coords, near, radius_m),
        "near_ids": list(seen.keys()),
    }


def longest_gap_m(coords, near_facilities, radius_m: float,
                  step_m: float = config.GAP_SAMPLE_STEP_M) -> float:
    """반경 안에 시설이 하나도 없는 가장 긴 연속 구간의 길이(m)."""
    samples = densify(coords, step_m)
    covered = [
        any(haversine_m(p[0], p[1], f.lat, f.lon) <= radius_m for f in near_facilities)
        for p in samples
    ]
    longest = run = 0.0
    for i in range(1, len(samples)):
        seg = haversine_m(samples[i - 1][0], samples[i - 1][1], samples[i][0], samples[i][1])
        if not covered[i - 1] and not covered[i]:
            run += seg
            longest = max(longest, run)
        else:
            run = 0.0
    return longest
