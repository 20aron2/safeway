"""공공데이터 정리 규칙 테스트."""
import importlib.util
from pathlib import Path

import pandas as pd

spec = importlib.util.spec_from_file_location(
    "build_facilities", Path(__file__).resolve().parent.parent / "scripts" / "build_facilities.py")
bf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bf)


def _cctv(rows):
    cols = ["관리번호", "소재지도로명주소", "WGS84위도", "WGS84경도", "카메라대수", "설치연월"]
    return pd.DataFrame(rows, columns=cols).astype(str)


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
        # 금정구 밖, 좌표 없음 → 제외
        ("10", "부산광역시 금정구 F로 1", "35.02868", "129.08856", "1", "202001"),
        ("11", "부산광역시 금정구 G로 1", "", "", "1", "202001"),
    ])
    log = []
    out = bf.clean(df, "cctv", log)
    assert len(out) == 2
    a = out[out["lat"] == 35.23].iloc[0]
    assert a["name"] == "CCTV 3대 · 금정구 A로 1"
    assert a["id"] == "cctv-1" and a["source"] == "public"
    assert set(out["kind"]) == {"cctv"}
    assert any("좌표 변환 실패" in line for line in log)


def test_two_addresses_same_point_are_one_site_with_summed_cameras():
    df = _cctv([
        ("1", "부산광역시 금정구 A로 1", "35.23", "129.08", "2", "202001"),
        ("2", "부산광역시 금정구 A로 1-1", "35.23", "129.08", "1", "202001"),
    ])
    out = bf.clean(df, "cctv", [])
    assert len(out) == 1 and out.iloc[0]["name"].startswith("CCTV 3대")
