"""공공데이터 CSV → 앱이 읽는 시설 파일로 정리하는 스크립트 (STEP 3).

사용법 (safeway 폴더에서):
    python scripts/build_facilities.py

입력:  data/raw/cctv.csv   (행정안전부_CCTV정보, 금정구분)
       data/raw/bell.csv   (행정안전부_안전비상벨위치정보, 금정구분)
       data/raw/light.csv  (전국보안등정보표준데이터 중 부산광역시 금정구, 없어도 됨)
출력:  data/processed/facilities_geumjeong.csv   ← 앱이 자동으로 읽는 파일
       data/processed/cleaning_report.md         ← 정리 과정 기록 (발표 자료용)

정리 규칙
1. 좌표가 없거나 금정구 범위 밖인 행은 제외
2. 관리번호만 다르고 내용이 같은 행(중복 등록)은 1개로
3. 서로 다른 주소 여러 개가 한 좌표에 몰린 경우 → 좌표 변환 실패로 보고 제외
   (실제 위치를 알 수 없는 시설을 엉뚱한 곳에 찍지 않기 위해)
4. 같은 좌표의 시설은 '설치 지점 1곳'으로 합친다 (카메라 대수는 합산)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "facilities_geumjeong.csv"
REPORT = ROOT / "data" / "processed" / "cleaning_report.md"

# 금정구를 넉넉히 감싸는 범위 (위도, 경도)
AREA = {"lat": (35.19, 35.33), "lon": (129.03, 129.15)}
# 한 좌표에 서로 다른 주소가 이 개수 이상이면 좌표 변환 실패로 본다
BAD_POINT_MIN_ADDRESSES = 3


def read_korean_csv(path: Path) -> pd.DataFrame:
    """공공데이터 CSV는 CP949(윈도우 한글) 또는 UTF-8이라 둘 다 시도한다."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path.name}: 글자 인코딩을 알 수 없어요.")


def _coords(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    lat_col = "WGS84위도" if "WGS84위도" in df else "위도"   # 보안등 파일은 열 이름이 다르다
    lon_col = "WGS84경도" if "WGS84경도" in df else "경도"
    df["lat"] = pd.to_numeric(df[lat_col], errors="coerce").round(6)
    df["lon"] = pd.to_numeric(df[lon_col], errors="coerce").round(6)
    return df


def _address(df: pd.DataFrame) -> pd.Series:
    road = df.get("소재지도로명주소", pd.Series("", index=df.index)).fillna("")
    jibun = df.get("소재지지번주소", pd.Series("", index=df.index)).fillna("")
    return road.where(road.str.strip() != "", jibun).str.replace("부산광역시 ", "", regex=False)


def clean(df: pd.DataFrame, kind: str, log: list[str]) -> pd.DataFrame:
    label = {"cctv": "CCTV", "bell": "비상벨", "light": "보안등"}[kind]
    df = _coords(df)
    if "관리번호" not in df:  # 보안등 파일에는 관리번호가 없어 위치명(없으면 줄 번호)을 쓴다
        df["관리번호"] = df.get("보안등위치명", pd.Series(index=df.index, dtype=str)).fillna("").where(
            lambda v: v != "", df.index.astype(str))
    df["address"] = _address(df)
    log.append(f"### {label}\n- 원본: {len(df):,}행")

    missing = df["lat"].isna() | df["lon"].isna()
    outside = ~missing & ~(df["lat"].between(*AREA["lat"]) & df["lon"].between(*AREA["lon"]))
    df = df[~missing & ~outside]
    log.append(f"- 좌표 없음 {missing.sum()}행, 금정구 범위 밖 {outside.sum()}행 제외")

    ignore = {"관리번호", "데이터갱신시점", "최종수정시점", "lat", "lon"}
    before = len(df)
    df = df.drop_duplicates(subset=[c for c in df.columns if c not in ignore])
    log.append(f"- 관리번호만 다른 중복 등록 {before - len(df)}행 정리")

    addr_per_point = df.groupby(["lat", "lon"])["address"].nunique()
    bad_points = addr_per_point[addr_per_point >= BAD_POINT_MIN_ADDRESSES]
    bad = df.set_index(["lat", "lon"]).index.isin(bad_points.index)
    if bad.any():
        log.append(
            f"- 서로 다른 주소가 한 좌표에 몰린 곳 {len(bad_points)}곳({bad.sum()}행) 제외 "
            "→ 좌표 변환 실패로 판단"
        )
    df = df[~bad]

    rows = []
    for (lat, lon), g in df.groupby(["lat", "lon"], sort=False):
        addresses = list(dict.fromkeys(a for a in g["address"] if a))
        if kind == "cctv":
            # 같은 주소가 설치연월·기준일자만 바꿔 여러 번 등록된 경우가 많아
            # 주소별로는 최댓값을 쓰고, 주소가 다르면 합산한다 (과대 집계 방지)
            per_addr = pd.to_numeric(g["카메라대수"], errors="coerce").fillna(1).groupby(g["address"]).max()
            cams = int(per_addr.sum())
            name = f"CCTV {cams}대 · {addresses[0] if addresses else '주소 없음'}"
        elif kind == "light":
            count = int(pd.to_numeric(g["설치개수"], errors="coerce").fillna(1).sum())
            name = f"보안등 {count}개 · {addresses[0] if addresses else g['관리번호'].iloc[0]}"
        else:
            place = g["설치위치"].dropna().iloc[0] if g["설치위치"].notna().any() else ""
            name = f"비상벨 · {place}" + (f" ({g['설치장소유형'].iloc[0]})" if "설치장소유형" in g else "")
        rows.append({"id": f"{kind}-{g['관리번호'].iloc[0]}", "kind": kind,
                     "lat": lat, "lon": lon, "name": name, "source": "public"})
    out = pd.DataFrame(rows)
    # 위치명이 겹치는 경우가 있어 id가 중복되면 뒤에 번호를 붙인다
    dup = out.groupby("id").cumcount()
    out["id"] = out["id"].where(dup == 0, out["id"] + "-" + dup.astype(str))
    log.append(f"- **최종 설치 지점: {len(out)}곳** (같은 좌표는 1곳으로 합침)")
    if kind == "cctv":
        repeated = (df.groupby(["lat", "lon", "address"]).size() > 1).sum()
        log.append(
            f"- 참고: {repeated}곳은 같은 주소·같은 카메라 대수가 설치연월과 기준일자만 다르게 "
            "여러 번 등록돼 있어요. 데이터 갱신 때 중복 등록된 것으로 보고 1곳으로 셌어요."
        )
    elif kind == "bell":
        places = df["설치장소유형"].value_counts().to_dict() if "설치장소유형" in df else {}
        log.append(f"- 설치 장소 유형: {places}")
    else:
        forms = df["설치형태"].value_counts().to_dict() if "설치형태" in df else {}
        log.append(f"- 설치 형태: {forms}")
    log.append("")
    return out


def main(cctv_path: Path = RAW / "cctv.csv", bell_path: Path = RAW / "bell.csv",
         light_path: Path = RAW / "light.csv") -> pd.DataFrame:
    log = ["# 공공데이터 정리 기록\n"]
    parts = []
    for path, kind in ((cctv_path, "cctv"), (bell_path, "bell"), (light_path, "light")):
        if not path.exists():
            if kind == "light":
                log.append("_보안등 파일이 없어 보안등은 건너뛰었어요._\n")
                continue
            sys.exit(f"파일이 없어요: {path}  (data/raw 폴더에 cctv.csv, bell.csv 로 넣어 주세요)")
        raw = read_korean_csv(path)
        if "데이터기준일자" in raw:
            log.append(f"_{path.name} 데이터기준일자: {raw['데이터기준일자'].min()} ~ {raw['데이터기준일자'].max()}_\n")
        parts.append(clean(raw, kind, log))

    facilities = pd.concat(parts, ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    facilities.to_csv(OUT, index=False, encoding="utf-8-sig")  # 엑셀에서도 한글이 안 깨지게
    REPORT.write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))
    print(f"저장: {OUT.relative_to(ROOT)}  ({len(facilities)}곳)")
    return facilities


if __name__ == "__main__":
    main()
