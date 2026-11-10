"""TMAP 지도 부품의 Python 쪽 테스트 (화면은 브라우저에서 확인)."""
import pandas as pd

from core import tmap_map
from core.facilities import COLUMNS

S, E = (35.2316, 129.0846), (35.2380, 129.0880)
ROUTES = [
    {"id": "A", "coords": [S, (35.2350, 129.0846), E]},
    {"id": "B", "coords": [S, (35.2316, 129.0880), E]},
]


def test_payload_contents_and_order():
    fac = pd.DataFrame([
        {"id": "c1", "kind": "cctv", "lat": 35.233, "lon": 129.085, "name": "CCTV", "source": "public"},
        {"id": "l1", "kind": "light", "lat": 35.234, "lon": 129.085, "name": "보안등", "source": "public"},
        {"id": "l2", "kind": "light", "lat": 35.236, "lon": 129.087, "name": "보안등", "source": "public"},
    ], columns=COLUMNS)
    p = tmap_map.build_payload(start=S, end=E, start_name="부산대역", routes=ROUTES, selected_id="A",
                               facilities=fac, near_ids=["c1", "l2"],
                               gap_segments=[{"length_m": 120.0, "coords": [S, E]}],
                               police=[{"lat": 35.235, "lon": 129.087, "name": "장전지구대", "address": "x"}],
                               night=True)
    assert [r["selected"] for r in p["routes"]] == [False, True]          # 선택 경로가 마지막
    assert p["routes"][1]["color"] == "#2563EB"                            # A의 원래 색 유지
    assert [f["kind"] for f in p["facilities"]] == ["cctv"] and p["facilities"][0]["on"]
    assert [l["on"] for l in p["lights"]] == [False, True]
    assert p["gaps"][0]["length_m"] == 120.0 and p["police"][0] == {"lat": 35.235, "lon": 129.087, "name": "장전지구대"}
    assert p["start"] == [35.2316, 129.0846] and p["start_name"] == "부산대역" and p["night"] is True
    assert len(p["fit_points"]) == 2 + 6


def test_fit_key_changes_only_when_places_change():
    a = tmap_map.build_payload(start=S, end=E, routes=ROUTES, selected_id="A")
    b = tmap_map.build_payload(start=S, end=E, routes=ROUTES, selected_id="B", night=True)
    c = tmap_map.build_payload(start=S)
    assert a["fit_key"] == b["fit_key"]       # 경로 선택·야간 전환은 화면을 다시 맞추지 않는다
    assert a["fit_key"] != c["fit_key"]
    assert c["center"] == [35.2316, 129.0846]


def test_template_has_key_placeholder_once():
    html = tmap_map.TEMPLATE.read_text(encoding="utf-8")
    assert html.count("__APPKEY__") == 1
    assert "apis.openapi.sk.com/tmap/jsv2" in html
