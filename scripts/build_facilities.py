"""공공데이터 CSV → 앱이 읽는 시설 파일로 정리하는 스크립트.

사용법 (safeway 폴더에서):
    python scripts/build_facilities.py

입력 (data/raw 폴더. 원본은 커서 GitHub에 올리지 않는다)
    cctv*.csv       행정안전부_CCTV정보 (부산광역시)
    bell*.csv       행정안전부_안전비상벨위치정보 (부산광역시)
    light/*.csv     전국보안등정보표준데이터 중 부산 구·군 파일들 (여러 개, 없어도 됨)
출력
    data/processed/facilities_busan.csv   ← 앱이 자동으로 읽는 파일
    data/processed/cleaning_report.md     ← 정리 과정과 구·군별 결과 (발표 자료용)

정리 규칙
1. 좌표가 없거나 부산 범위 밖인 행은 제외
2. CCTV는 길을 비추는 용도(생활방범·다목적·어린이보호·쓰레기단속)만 사용
3. 관리번호만 다르고 내용이 같은 행(중복 등록)은 1개로
4. 서로 다른 주소 여러 개가 한 좌표에 몰린 경우 → 좌표 변환 실패로 보고 제외
5. 같은 좌표의 시설은 '설치 지점 1곳'으로 합친다
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "facilities_busan.csv"
REPORT = ROOT / "data" / "processed" / "cleaning_report.md"

REGION = "부산광역시"
# 부산을 넉넉히 감싸는 범위 (위도, 경도)
AREA = {"lat": (34.85, 35.45), "lon": (128.70, 129.35)}
GUS = ["중구", "서구", "동구", "영도구", "부산진구", "동래구", "남구", "북구", "해운대구",
       "사하구", "금정구", "강서구", "연제구", "수영구", "사상구", "기장군"]
# 길을 비추는 CCTV만 쓴다. 교통단속(차량 번호판), 재난재해(하천·산 감시),
# 시설물관리(건물 내부 등)는 보행자 주변을 비춘다고 보기 어려워 뺀다.
CCTV_PURPOSES = {"생활방범", "다목적", "어린이보호", "쓰레기단속"}
# 한 좌표에 서로 다른 주소가 이 개수 이상이면 좌표 변환 실패로 본다
BAD_POINT_MIN_ADDRESSES = 3
LABEL = {"cctv": "CCTV", "bell": "비상벨", "light": "보안등"}


def read_korean_csv(path: Path) -> pd.DataFrame:
    """공공데이터 CSV는 CP949(윈도우 한글) 또는 UTF-8이라 둘 다 시도한다."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path.name}: 글자 인코딩을 알 수 없어요.")


def guess_kind(df: pd.DataFrame) -> str | None:
    cols = set(df.columns)
    if "카메라대수" in cols:
        return "cctv"
    if "안전비상벨관리번호" in cols:
        return "bell"
    if "보안등위치명" in cols:
        return "light"
    return None


def gu_of(*texts) -> str:
    """주소나 관리기관 이름에서 구·군을 찾는다 ('부산진구'가 '진구'로 잘못 잡히지 않게 긴 이름부터)."""
    for t in texts:
        t = str(t or "")
        for g in sorted(GUS, key=len, reverse=True):
            if re.search(r"(?:^|\s|부산광역시\s?|부산\s?)" + g, t):
                return g
    return "알 수 없음"


def _coords(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    lat_col = "WGS84위도" if "WGS84위도" in df else "위도"   # 보안등 파일은 열 이름이 다르다
    lon_col = "WGS84경도" if "WGS84경도" in df else "경도"
    df["lat"] = pd.to_numeric(df[lat_col], errors="coerce").round(6)
    df["lon"] = pd.to_numeric(df[lon_col], errors="coerce").round(6)
    return df


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    return df[name].fillna("") if name in df else pd.Series("", index=df.index)


def _address(df: pd.DataFrame) -> pd.Series:
    road, jibun = _col(df, "소재지도로명주소"), _col(df, "소재지지번주소")
    return road.where(road.str.strip() != "", jibun).str.replace(f"{REGION} ", "", regex=False)


def clean(df: pd.DataFrame, kind: str, log: list[str], stats: dict) -> pd.DataFrame:
    """한 종류(cctv/bell/light)의 원본을 정리해 시설 표로 만든다. stats에 구·군별 개수를 남긴다."""
    label = LABEL[kind]
    df = _coords(df)
    df["address"] = _address(df)
    df["gu"] = [gu_of(a, b, c) for a, b, c in zip(_col(df, "소재지도로명주소"), _col(df, "소재지지번주소"),
                                                  _col(df, "관리기관명"))]
    if "관리번호" not in df:  # 보안등 파일에는 관리번호가 없어 '구·위치명'(없으면 줄 번호)을 쓴다
        name = _col(df, "보안등위치명")
        df["관리번호"] = (df["gu"] + "-" + name).where(name != "", df["gu"] + "-" + df.index.astype(str))
    raw_by_gu = df.groupby("gu").size()
    log.append(f"### {label}\n- 원본: {len(df):,}행")

    missing = df["lat"].isna() | df["lon"].isna()
    outside = ~missing & ~(df["lat"].between(*AREA["lat"]) & df["lon"].between(*AREA["lon"]))
    df = df[~missing & ~outside]
    log.append(f"- 좌표 없음 {missing.sum():,}행, 부산 범위 밖 {outside.sum():,}행 제외")

    if kind == "cctv" and "설치목적구분" in df:
        keep = df["설치목적구분"].isin(CCTV_PURPOSES)
        dropped = df.loc[~keep, "설치목적구분"].value_counts().to_dict()
        df = df[keep]
        log.append(f"- 길을 비추는 용도만 사용 ({', '.join(sorted(CCTV_PURPOSES))}). "
                   f"제외: {dropped}")

    ignore = {"관리번호", "데이터갱신시점", "최종수정시점", "데이터기준일자", "lat", "lon"}
    before = len(df)
    df = df.drop_duplicates(subset=[c for c in df.columns if c not in ignore])
    log.append(f"- 관리번호·기준일만 다른 중복 등록 {before - len(df):,}행 정리")

    addr_per_point = df.groupby(["lat", "lon"])["address"].nunique()
    bad_points = addr_per_point[addr_per_point >= BAD_POINT_MIN_ADDRESSES]
    bad = df.set_index(["lat", "lon"]).index.isin(bad_points.index)
    if bad.any():
        log.append(f"- 서로 다른 주소가 한 좌표에 몰린 곳 {len(bad_points)}곳({bad.sum():,}행) 제외 "
                   "→ 좌표 변환 실패로 판단")
    df = df[~bad]

    rows = []
    for (lat, lon), g in df.groupby(["lat", "lon"], sort=False):
        addresses = list(dict.fromkeys(a for a in g["address"] if a))
        where = addresses[0] if addresses else "주소 없음"
        if kind == "cctv":
            # 같은 주소가 설치연월·기준일자만 바꿔 여러 번 등록된 경우가 많아
            # 주소별로는 최댓값을 쓰고, 주소가 다르면 합산한다 (과대 집계 방지)
            per_addr = pd.to_numeric(g["카메라대수"], errors="coerce").fillna(1).groupby(g["address"]).max()
            name = f"CCTV {int(per_addr.sum())}대 · {where}"
        elif kind == "light":
            count = int(pd.to_numeric(_col(g, "설치개수"), errors="coerce").fillna(1).sum())
            name = f"보안등 {count}개 · {where}"
        else:
            place = _col(g, "설치위치").iloc[0]
            kind_of_place = _col(g, "설치장소유형").iloc[0]
            name = f"비상벨 · {place or where}" + (f" ({kind_of_place})" if kind_of_place else "")
        rows.append({"id": f"{kind}-{g['관리번호'].iloc[0]}", "kind": kind, "lat": lat, "lon": lon,
                     "name": name, "source": "public", "gu": g["gu"].iloc[0]})
    out = pd.DataFrame(rows, columns=["id", "kind", "lat", "lon", "name", "source", "gu"])
    # id가 겹치면 뒤에 번호를 붙인다
    dup = out.groupby("id").cumcount()
    out["id"] = out["id"].where(dup == 0, out["id"] + "-" + dup.astype(str))
    log.append(f"- **최종 설치 지점: {len(out):,}곳** (같은 좌표는 1곳으로 합침)")
    if kind == "bell" and "설치장소유형" in df:
        log.append(f"- 설치 장소 유형: {df['설치장소유형'].value_counts().to_dict()}")
    log.append("")

    final_by_gu = out.groupby("gu").size()
    for gu in set(raw_by_gu.index) | set(final_by_gu.index):
        stats.setdefault(gu, {})[f"{kind}_raw"] = int(raw_by_gu.get(gu, 0))
        stats[gu][kind] = int(final_by_gu.get(gu, 0))
    return out


def gu_table(stats: dict) -> list[str]:
    """구·군별 '원본 행 → 실제 설치 지점' 표 (마크다운)."""
    lines = ["## 구·군별 정리 결과 (원본 행 → 설치 지점)\n",
             "| 구·군 | CCTV | 비상벨 | 보안등 |", "|---|---|---|---|"]

    def cell(s, k):
        raw, final = s.get(f"{k}_raw", 0), s.get(k, 0)
        return "없음" if raw == 0 else f"{raw:,} → {final:,}"

    for gu in [g for g in GUS if g in stats] + [g for g in stats if g not in GUS]:
        s = stats[gu]
        lines.append(f"| {gu} | {cell(s, 'cctv')} | {cell(s, 'bell')} | {cell(s, 'light')} |")
    missing = {k: [g for g in GUS if stats.get(g, {}).get(f"{k}_raw", 0) == 0] for k in LABEL}
    for k, gus in missing.items():
        if gus:
            lines.append(f"\n- {LABEL[k]} 데이터가 없는 구·군: {', '.join(gus)}")
    return lines + [""]


def collect_inputs() -> dict[str, list[Path]]:
    """data/raw 안의 CSV를 내용(열 이름)으로 종류를 알아내 모은다."""
    found: dict[str, list[Path]] = {"cctv": [], "bell": [], "light": []}
    for path in sorted(RAW.rglob("*.csv")):
        try:
            kind = guess_kind(read_korean_csv(path).head(0))
        except Exception:
            kind = None
        if kind:
            found[kind].append(path)
    return found


def main() -> pd.DataFrame:
    inputs = collect_inputs()
    if not inputs["cctv"] or not inputs["bell"]:
        sys.exit("data/raw 폴더에 CCTV와 비상벨 CSV가 있어야 해요.")
    log = [f"# 공공데이터 정리 기록 ({REGION})\n"]
    stats: dict = {}
    parts = []
    for kind in ("cctv", "bell", "light"):
        if not inputs[kind]:
            log.append(f"_{LABEL[kind]} 파일이 없어 건너뛰었어요._\n")
            continue
        raw = pd.concat([read_korean_csv(p) for p in inputs[kind]], ignore_index=True)
        if "데이터기준일자" in raw:
            log.append(f"_{LABEL[kind]} 파일 {len(inputs[kind])}개 · 데이터기준일자 "
                       f"{raw['데이터기준일자'].min()} ~ {raw['데이터기준일자'].max()}_\n")
        parts.append(clean(raw, kind, log, stats))

    facilities = pd.concat(parts, ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    facilities.to_csv(OUT, index=False, encoding="utf-8-sig")  # 엑셀에서도 한글이 안 깨지게
    log += gu_table(stats)
    REPORT.write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))
    counts = facilities["kind"].value_counts().to_dict()
    print(f"저장: {OUT.relative_to(ROOT)}  (CCTV {counts.get('cctv', 0):,} · 비상벨 {counts.get('bell', 0):,} · "
          f"보안등 {counts.get('light', 0):,})")
    return facilities


if __name__ == "__main__":
    main()
