"""공공데이터 정리 규칙 테스트."""
import importlib.util
from pathlib import Path

import pandas as pd

spec = importlib.util.spec_from_file_location(
    "build_facilities", Path(__file__).resolve().parent.parent / "scripts" / "build_facilities.py")
bf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bf)


def _cctv(rows):
    cols = ["관리번호", "소재지도로명주소", "WGS84위도", "WGS84경도", "카메라대수", "설치연월", "설치목적구분"]
    return pd.DataFrame([r + ("생활방범",) if len(r) == 6 else r for r in rows], columns=cols).astype(str)


def test_cctv_cleaning_rules():
    df = _cctv([
        # 같은 주소가 설치연월만 다르게 4번 → 1곳, 카메라 3대(합산 아님)
        ("1", "부산광역시 금정구 A로 1", "35.23", "129.08", "3", "202001"),
        ("2", "부산광역시 금정구 A로 1", "35.23", "129.08", "3", "202101"),
        ("3", "부산광역시 금정구 A로 1", "35.23", "129.08", "3", "202201"),
        ("4", "부산광역시 금정구 A로 1", "35.23", "129.08", "3", "202301"),
        # 관리번호만 다른 완전 중복 → 1행
        ("5", "부산광역시 금정구 B로 2", "35.24", "129.09", "1", "202001"),
        ("6", "부산광역시 금정구 B로 2", "35.24", "129.09", "1", "202001"),
        # 주소 3개가 한 좌표에 몰림 → 좌표 실패로 제외
        ("7", "부산광역시 금정구 C로 1", "35.25", "129.10", "1", "202001"),
        ("8", "부산광역시 금정구 D로 1", "35.25", "129.10", "1", "202001"),
        ("9", "부산광역시 금정구 E로 1", "35.25", "129.10", "1", "202001"),
        # 부산 밖, 좌표 없음 → 제외
        ("10", "부산광역시 금정구 F로 1", "37.5", "127.0", "1", "202001"),
        ("11", "부산광역시 금정구 G로 1", "", "", "1", "202001"),
        # 교통단속 CCTV → 제외
        ("12", "부산광역시 금정구 H로 1", "35.26", "129.11", "1", "202001", "교통단속"),
    ])
    log, stats = [], {}
    out = bf.clean(df, "cctv", log, stats)
    assert len(out) == 2
    a = out[out["lat"] == 35.23].iloc[0]
    assert a["name"] == "CCTV 3대 · 금정구 A로 1"
    assert a["id"] == "cctv-1" and a["source"] == "public" and a["gu"] == "금정구"
    assert any("좌표 변환 실패" in line for line in log)
    assert any("교통단속" in line for line in log)
    assert stats["금정구"] == {"cctv_raw": 12, "cctv": 2}


def test_two_addresses_same_point_are_one_site_with_summed_cameras():
    df = _cctv([
        ("1", "부산광역시 금정구 A로 1", "35.23", "129.08", "2", "202001"),
        ("2", "부산광역시 금정구 A로 1-1", "35.23", "129.08", "1", "202001"),
    ])
    out = bf.clean(df, "cctv", [], {})
    assert len(out) == 1 and out.iloc[0]["name"].startswith("CCTV 3대")


def test_lights_from_two_districts_get_unique_ids_and_table():
    cols = ["보안등위치명", "설치개수", "소재지도로명주소", "소재지지번주소", "위도", "경도", "관리기관명"]
    df = pd.DataFrame([
        ("A001", "1", "", "부산광역시 금정구 장전동 1", "35.23", "129.08", "부산광역시 금정구청"),
        ("A001", "1", "", "부산광역시 동래구 온천동 1", "35.20", "129.08", "부산광역시 동래구청"),
        ("A002", "2", "", "부산광역시 부산진구 부전동 1", "35.15", "129.06", "부산광역시 부산진구청"),
    ], columns=cols)
    stats = {}
    out = bf.clean(df, "light", [], stats)
    assert out["id"].is_unique and set(out["gu"]) == {"금정구", "동래구", "부산진구"}
    assert "부산진구" in stats and "진구" not in stats            # '부산진구'를 '진구'로 잘못 읽지 않음
    assert out[out["gu"] == "부산진구"].iloc[0]["name"].startswith("보안등 2개")
    table = "\n".join(bf.gu_table(stats))
    assert "| 금정구 | 없음 | 없음 | 1 → 1 |" in table


def test_guess_kind_and_gu():
    assert bf.guess_kind(pd.DataFrame(columns=["카메라대수"])) == "cctv"
    assert bf.guess_kind(pd.DataFrame(columns=["안전비상벨관리번호"])) == "bell"
    assert bf.guess_kind(pd.DataFrame(columns=["보안등위치명"])) == "light"
    assert bf.guess_kind(pd.DataFrame(columns=["x"])) is None
    assert bf.gu_of("", "부산광역시 해운대구 우동 1") == "해운대구"
    assert bf.gu_of("부산광역시 서구 대신동") == "서구"
    assert bf.gu_of("서울특별시 종로구") == "알 수 없음"
