"""계산 로직 테스트. 실행: python -m pytest"""
import math

import pandas as pd
import pytest

from core import analysis, explain, recommend
from core import routes as rt
from core.facilities import COLUMNS, filter_bbox, load_public_facilities, make_demo_facilities
from core.geo import haversine_m, offset_point, point_to_polyline_m, polyline_length_m, route_gap_m

PNU = (35.2316, 129.0846)


# ---------------------------------------------------------------- geo
def test_haversine_one_degree_latitude_is_about_111km():
    assert haversine_m(35.0, 129.0, 36.0, 129.0) == pytest.approx(111_195, rel=1e-3)


def test_offset_point_round_trip():
    lat, lon = offset_point(*PNU, east_m=300, north_m=-400)
    assert haversine_m(*PNU, lat, lon) == pytest.approx(500, abs=0.5)


def test_point_to_polyline_perpendicular_and_endpoint():
    a = PNU
    b = offset_point(*PNU, east_m=200, north_m=0)
    line = [a, b]
    p = offset_point(*PNU, east_m=100, north_m=30)          # 선 가운데에서 북쪽 30m
    assert point_to_polyline_m(*p, line) == pytest.approx(30, abs=0.1)
    q = offset_point(*PNU, east_m=240, north_m=30)          # 끝점 바깥 → 끝점까지 50m
    assert point_to_polyline_m(*q, line) == pytest.approx(50, abs=0.1)


def test_route_gap_same_and_different():
    a = [PNU, offset_point(*PNU, 300, 0)]
    shifted = [offset_point(*p, 0, 100) for p in a]
    assert route_gap_m(a, list(a)) == pytest.approx(0, abs=0.01)
    assert route_gap_m(a, shifted) == pytest.approx(100, abs=1)


# ---------------------------------------------------------------- routes
def test_demo_routes_basic_shape():
    end = offset_point(*PNU, east_m=600, north_m=400)
    routes = rt.get_routes(PNU, end)
    assert [r["id"] for r in routes] == ["A", "B", "C"]
    for r in routes:
        assert r["source"] == "demo"
        assert r["coords"][0] == PNU and r["coords"][-1] == end
        assert r["distance_m"] == pytest.approx(polyline_length_m(r["coords"]))
        assert r["duration_s"] > 0
    assert routes[0]["distance_m"] == pytest.approx(1000, rel=0.01)   # 600 + 400 (ㄱ자)


def test_aligned_points_drop_duplicate_route():
    # 정확히 북쪽이면 '남북 먼저'와 '동서 먼저'가 같은 길 → 하나 제거
    end = offset_point(*PNU, east_m=0, north_m=500)
    routes = rt.get_routes(PNU, end)
    assert len(routes) == 2
    assert [r["id"] for r in routes] == ["A", "B"]


@pytest.mark.parametrize("north_m", [10, 6000])
def test_too_close_or_too_far_raises(north_m):
    with pytest.raises(rt.RouteError):
        rt.get_routes(PNU, offset_point(*PNU, 0, north_m))


def test_missing_point_raises():
    with pytest.raises(rt.RouteError):
        rt.get_routes(PNU, None)


# ---------------------------------------------------------------- analysis
def _facility_df(items):
    rows = [{"id": i, "kind": k, "lat": p[0], "lon": p[1], "name": i, "source": "demo"}
            for i, k, p in items]
    return pd.DataFrame(rows, columns=COLUMNS)


def _straight_route(length_m=400):
    end = offset_point(*PNU, length_m, 0)
    coords = [PNU, offset_point(*PNU, length_m / 2, 0), end]
    return {"id": "A", "label": "t", "coords": coords,
            "distance_m": polyline_length_m(coords), "duration_s": 360, "source": "demo"}


def test_analyze_counts_within_radius_and_dedupes():
    route = _straight_route()
    df = _facility_df([
        ("c1", "cctv", offset_point(*PNU, 50, 20)),    # 20m → 포함
        ("c1", "cctv", offset_point(*PNU, 50, 20)),    # 같은 id 중복 → 1번만
        ("c2", "cctv", offset_point(*PNU, 150, -49)),  # 49m → 포함
        ("c3", "cctv", offset_point(*PNU, 150, 60)),   # 60m → 제외
        ("b1", "bell", offset_point(*PNU, 380, 10)),   # 포함
    ])
    m = analysis.analyze_route(route, df, radius_m=50)
    assert (m["cctv"], m["bell"], m["total"]) == (2, 1, 3)
    assert sorted(m["near_ids"]) == ["b1", "c1", "c2"]
    assert m["per_km"] == pytest.approx(3 / 0.4, rel=1e-3)


def test_radius_change_changes_count():
    route = _straight_route()
    df = _facility_df([("c3", "cctv", offset_point(*PNU, 150, 60))])
    assert analysis.analyze_route(route, df, 50)["cctv"] == 0
    assert analysis.analyze_route(route, df, 70)["cctv"] == 1


def test_longest_gap():
    route = _straight_route(400)
    assert analysis.analyze_route(route, _facility_df([]), 50)["longest_gap_m"] == pytest.approx(400, abs=1)
    # 시작점에 시설 하나 → 처음 50m는 커버, 나머지 약 350m가 공백
    df = _facility_df([("c1", "cctv", PNU)])
    gap = analysis.analyze_route(route, df, 50)["longest_gap_m"]
    assert gap == pytest.approx(350, abs=12)


# ---------------------------------------------------------------- recommend / explain
def _metric(rid, dist, cctv, bell):
    total = cctv + bell
    return {"route_id": rid, "distance_m": dist, "duration_s": dist / 1.1, "radius_m": 50,
            "cctv": cctv, "bell": bell, "total": total, "per_km": total / (dist / 1000),
            "longest_gap_m": 100.0, "near_ids": []}


def test_modes_pick_different_routes():
    metrics = [_metric("A", 1000, 1, 0), _metric("B", 1250, 6, 2)]
    assert recommend.score_routes(metrics, "shortest")["recommended_id"] == "A"
    assert recommend.score_routes(metrics, "facility")["recommended_id"] == "B"
    rows = recommend.score_routes(metrics, "balanced")["rows"]
    assert all(0 <= r["score"] <= 100 for r in rows)


def test_no_facilities_falls_back_to_shortest():
    metrics = [_metric("A", 1200, 0, 0), _metric("B", 1000, 0, 0)]
    for mode in recommend.MODES:
        assert recommend.score_routes(metrics, mode)["recommended_id"] == "B"


def test_basic_explanation_mentions_real_numbers():
    metrics = [_metric("A", 1000, 1, 0), _metric("B", 1250, 4, 1)]
    scored = recommend.score_routes(metrics, "facility")
    text = explain.build_basic_explanation(scored, 50, facilities_are_demo=False)
    assert "경로 B" in text and "250m" in text and "CCTV 지점이 3곳" in text and "비상벨이 1곳" in text


def test_explanation_single_route_and_tie():
    one = recommend.score_routes([_metric("A", 800, 2, 1)], "balanced")
    assert "다른 경로가 없어" in explain.build_basic_explanation(one, 50, True)
    tie = recommend.score_routes([_metric("A", 1000, 0, 0), _metric("B", 1000, 3, 0)], "facility")
    text = explain.build_basic_explanation(tie, 50, True)
    assert "보다 0m" not in text            # "0m 더 길지만" 같은 어색한 문장 금지
    assert "**경로 B**가 가장 짧아요" in text


def test_format_helpers():
    assert explain.fmt_distance(850) == "850m"
    assert explain.fmt_distance(1234) == "1.2km"
    assert explain.fmt_duration(20) == "1분 미만"
    assert explain.fmt_duration(600) == "약 10분"


# ---------------------------------------------------------------- facilities
def test_demo_facilities_are_labeled_and_repeatable():
    routes = rt.get_routes(PNU, offset_point(*PNU, 500, 300))
    a = make_demo_facilities(routes, PNU)
    b = make_demo_facilities(routes, PNU)
    assert (a["source"] == "demo").all()
    assert a["name"].str.startswith("가상").all()
    assert a["id"].is_unique
    pd.testing.assert_frame_equal(a, b)


def test_load_public_facilities_cleans_rows(tmp_path):
    p = tmp_path / "f.csv"
    p.write_text(
        "id,kind,lat,lon,name\n"
        "1,cctv,35.23,129.08,정문\n"
        "1,cctv,35.23,129.08,정문중복\n"
        "2,bell,,129.08,좌표없음\n"
        "3,parking,35.23,129.08,다른종류\n"
        "4,bell,35.24,129.09,후문\n",
        encoding="utf-8",
    )
    df = load_public_facilities(p)
    assert list(df["id"]) == ["1", "4"]
    assert (df["source"] == "public").all()
    assert len(filter_bbox(df, (35.235, 129.085, 35.245, 129.095))) == 1


def test_load_public_facilities_rejects_bad_columns(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("x,y\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_public_facilities(p)


def test_gap_segments_for_map():
    route = _straight_route(400)
    # 시작점 근처에만 시설 → 끝쪽 약 350m가 비어 있음
    m = analysis.analyze_route(route, _facility_df([("c1", "cctv", PNU)]), 50)
    segs = m["gap_segments"]
    assert len(segs) == 1
    seg = segs[0]
    assert seg["length_m"] == pytest.approx(m["longest_gap_m"])
    assert seg["coords"][-1] == pytest.approx(route["coords"][-1])
    # 짧은 공백(100m 미만)은 지도에 그리지 않는다
    short = _straight_route(80)
    assert analysis.analyze_route(short, _facility_df([]), 50)["gap_segments"] == []


def test_lights_counted_separately_and_scored():
    route = _straight_route(400)
    df = _facility_df([
        ("c1", "cctv", offset_point(*PNU, 50, 10)),
        ("l1", "light", offset_point(*PNU, 150, 10)),
        ("l2", "light", offset_point(*PNU, 300, -10)),
    ])
    m = analysis.analyze_route(route, df, 50)
    assert (m["cctv"], m["light"], m["total"]) == (1, 2, 1)   # 보안등은 total에 넣지 않음
    assert m["light_per_km"] == pytest.approx(5.0, rel=1e-3)
    # 공백 구간은 CCTV·비상벨 기준 → 보안등이 있어도 끝쪽은 공백
    assert m["longest_gap_m"] > 250

    a = {**_metric("A", 1000, 2, 0), "light": 10, "light_per_km": 10.0}
    b = {**_metric("B", 1000, 2, 0), "light": 30, "light_per_km": 30.0}
    sc = recommend.score_routes([a, b], "facility")
    assert sc["recommended_id"] == "B"   # CCTV 같으면 보안등이 많은 쪽
    rows = {r["route_id"]: r for r in sc["rows"]}
    assert rows["A"]["fac_score"] == pytest.approx(0.5 + 0.5 * 10 / 30)


def test_coverage_and_outside_ratio():
    from core.facilities import coverage_cells
    route = _straight_route(400)
    inside = _facility_df([("c1", "cctv", PNU)])
    cov = coverage_cells(inside)
    assert analysis.outside_ratio(route["coords"], cov) == 0.0
    far = _facility_df([("c9", "cctv", offset_point(*PNU, 0, 5000))])   # 5km 북쪽에만 데이터
    assert analysis.outside_ratio(route["coords"], coverage_cells(far)) == 1.0
    assert analysis.outside_ratio(route["coords"], None) == 0.0         # 범위 정보 없음 → 경고 안 함
    m = analysis.analyze_route(route, inside, 50, coverage=coverage_cells(far))
    assert m["outside_ratio"] == 1.0


def test_dark_segments_from_lights():
    from core import config
    from core.facilities import coverage_cells
    route = _straight_route(400)
    # 보안등 데이터가 아예 없으면 '모름' (None) → 0m로 오해하지 않게
    m = analysis.analyze_route(route, _facility_df([("c1", "cctv", PNU)]), 50)
    assert m["longest_dark_m"] is None and m["dark_segments"] == []
    # 앞쪽 200m에만 보안등 → 뒤쪽 약 170m(30m 빛 거리 제외)가 어두운 구간
    lights = [(f"l{i}", "light", offset_point(*PNU, x, 5)) for i, x in enumerate(range(0, 201, 40))]
    m = analysis.analyze_route(route, _facility_df(lights), 50)
    assert m["longest_dark_m"] == pytest.approx(400 - 200 - config.LIGHT_REACH_M, abs=12)
    assert len(m["dark_segments"]) == 1
    assert m["dark_segments"][0]["coords"][-1] == pytest.approx(route["coords"][-1])
    # 분석 반경과 상관없다 (보안등 기준 거리는 고정)
    assert analysis.analyze_route(route, _facility_df(lights), 100)["longest_dark_m"] == m["longest_dark_m"]
    # 보안등 데이터 범위 밖은 어둡다고 하지 않는다
    far = _facility_df([("lx", "light", offset_point(*PNU, 0, 5000))])
    m2 = analysis.analyze_route(route, far, 50, light_coverage=coverage_cells(far))
    assert m2["longest_dark_m"] == 0.0


def test_dark_numbers_reach_explanation_and_payload():
    rows = [{**_metric("A", 1000, 3, 0), "longest_dark_m": 120.0},
            {**_metric("B", 1100, 5, 1), "longest_dark_m": 0.0}]
    sc = recommend.score_routes(rows, "balanced")
    text = explain.build_basic_explanation(sc, 50, False)
    assert "보안등이 없는 가장 긴 구간: A 120m, B 0m" in text
    routes = [{"id": "A", "label": "a"}, {"id": "B", "label": "b"}]
    payload = explain.build_ai_payload(sc, routes, 50, "균형", False)
    assert payload["경로들"][0]["보안등이_30m안에_없는_최장구간"] == "120m"


def test_light_reach_constant_matches_config():
    from core import config
    assert explain.LIGHT_REACH_M == config.LIGHT_REACH_M


def test_places_near_route():
    route = _straight_route(400)
    places = [{"name": "가까움", "lat": offset_point(*PNU, 100, 20)[0], "lon": offset_point(*PNU, 100, 20)[1]},
              {"name": "멂", "lat": offset_point(*PNU, 100, 200)[0], "lon": offset_point(*PNU, 100, 200)[1]}]
    assert [p["name"] for p in analysis.places_near_route(route["coords"], places, 50)] == ["가까움"]
    assert analysis.places_near_route(route["coords"], [], 50) == []


def test_district_summary_and_insights():
    import pandas as pd
    from core import config, insights
    df = pd.DataFrame([
        {"id": "1", "kind": "cctv", "lat": 0, "lon": 0, "gu": "중구"},
        {"id": "2", "kind": "cctv", "lat": 0, "lon": 0, "gu": "중구"},
        {"id": "3", "kind": "bell", "lat": 0, "lon": 0, "gu": "중구"},
        {"id": "4", "kind": "light", "lat": 0, "lon": 0, "gu": "기장군"},
        {"id": "5", "kind": "cctv", "lat": 0, "lon": 0, "gu": "기장군"},
        {"id": "6", "kind": "cctv", "lat": 0, "lon": 0, "gu": "서울시"},   # 부산 밖 → 무시
    ])
    s = insights.gu_summary(df)
    assert len(s) == len(config.GU_AREA_KM2) == 16
    jung = s[s["구"] == "중구"].iloc[0]
    assert (jung["cctv"], jung["bell"], jung["light"]) == (2, 1, 0)
    assert jung["cctv_km2"] == round(2 / config.GU_AREA_KM2["중구"], 1)
    lines = insights.insight_lines(s)
    assert lines[0].startswith("1㎢당 CCTV·비상벨은 **중구**")
    assert any("공개된 안전비상벨 데이터가 0곳" in l for l in lines)
    assert insights.gu_summary(df.drop(columns=["gu"])).empty   # 구 정보 없으면 빈 표


def test_store_count_reaches_ai_payload():
    rows = [{**_metric("A", 1000, 3, 0), "stores": 2}, _metric("B", 1100, 5, 1)]
    sc = recommend.score_routes(rows, "balanced")
    p = explain.build_ai_payload(sc, [{"id": "A", "label": "a"}, {"id": "B", "label": "b"}], 50, "균형", False)
    assert p["경로들"][0]["반경안_편의점(참고, 점수에는 안 넣음)"] == "2곳"
    assert not any("편의점" in k for k in p["경로들"][1])
