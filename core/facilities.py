"""CCTV·비상벨 시설 데이터 (담당: 공공데이터).

시설 데이터는 아래 열을 가진 pandas 표(DataFrame)로 주고받는다.

    id      시설 고유번호 (문자)
    kind    "cctv" 또는 "bell"
    lat     위도 (WGS84)
    lon     경도 (WGS84)
    name    표시용 이름/설치 위치
    source  "public"(공공데이터) 또는 "demo"(가상)

실제 공공데이터 CSV 정리는 STEP 3에서 scripts/ 폴더의 정리 스크립트로 만든다.
정리된 파일(data/processed/...)이 없으면 화면에 '가상 위치'라고 표시한 데모 시설을 쓴다.
"""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

from .geo import LatLon, bbox, offset_point

COLUMNS = ["id", "kind", "lat", "lon", "name", "source"]
KINDS = ("cctv", "bell")


def empty_facilities() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


def load_public_facilities(path: Path) -> pd.DataFrame:
    """정리된 공공데이터 CSV를 읽는다. 형식이 맞지 않으면 ValueError."""
    df = pd.read_csv(path, dtype={"id": str}, encoding="utf-8-sig")
    missing = [c for c in ("id", "kind", "lat", "lon") if c not in df.columns]
    if missing:
        raise ValueError(f"시설 파일에 필요한 열이 없어요: {', '.join(missing)}")
    if "name" not in df.columns:
        df["name"] = ""
    df["source"] = "public"
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])
    df = df[df["kind"].isin(KINDS)]
    df = df.drop_duplicates(subset=["id"])
    return df[COLUMNS].reset_index(drop=True)


def filter_bbox(df: pd.DataFrame, box: tuple[float, float, float, float]) -> pd.DataFrame:
    """사각형 범위 안의 시설만 남긴다 (계산량을 줄이기 위한 1차 거르기)."""
    min_lat, min_lon, max_lat, max_lon = box
    mask = df["lat"].between(min_lat, max_lat) & df["lon"].between(min_lon, max_lon)
    return df[mask].reset_index(drop=True)


def make_demo_facilities(routes: list[dict], seed_point: LatLon) -> pd.DataFrame:
    """경로 주변에 '가상' 시설을 흩뿌린다. 실제 설치 위치가 아니다.

    같은 출발지에서는 항상 같은 배치가 나오도록 출발 좌표로 난수를 고정한다.
    """
    rng = random.Random(f"{seed_point[0]:.5f},{seed_point[1]:.5f}")
    all_coords = [c for r in routes for c in r["coords"]]
    min_lat, min_lon, max_lat, max_lon = bbox(all_coords, margin_m=80)

    rows = []

    def add(kind: str, lat: float, lon: float) -> None:
        n = sum(1 for row in rows if row["kind"] == kind) + 1
        label = "가상 CCTV" if kind == "cctv" else "가상 비상벨"
        rows.append({"id": f"demo-{kind}-{n}", "kind": kind, "lat": lat, "lon": lon,
                     "name": f"{label} #{n}", "source": "demo"})

    # 1) 전체 범위에 고르게
    for kind, count in (("cctv", 18), ("bell", 6)):
        for _ in range(count):
            add(kind, rng.uniform(min_lat, max_lat), rng.uniform(min_lon, max_lon))

    # 2) 경로마다 차이가 나도록 한 경로 주변에 몇 개를 더 모은다
    favored = rng.choice(routes)
    for kind, count in (("cctv", 5), ("bell", 2)):
        for _ in range(count):
            lat, lon = rng.choice(favored["coords"])
            add(kind, *offset_point(lat, lon, rng.uniform(-30, 30), rng.uniform(-30, 30)))

    return pd.DataFrame(rows, columns=COLUMNS)
