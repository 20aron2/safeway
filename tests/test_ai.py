"""Gemini 설명 테스트. 실제 Gemini 대신 가짜 응답을 넣어 확인한다."""
import json
import sys
import types

from core import explain, recommend


def _metric(rid, dist, cctv, bell, gap=300.0):
    total = cctv + bell
    return {"route_id": rid, "distance_m": dist, "duration_s": dist / 1.1, "radius_m": 50,
            "cctv": cctv, "bell": bell, "total": total, "per_km": total / (dist / 1000),
            "longest_gap_m": gap, "near_ids": []}


ROUTES = [{"id": "A", "label": "TMAP 최단거리", "coords": [(35.2316, 129.0846), (35.24, 129.09)]},
          {"id": "B", "label": "TMAP 추천", "coords": [(35.2316, 129.0846), (35.24, 129.09)]}]


def payload():
    scored = recommend.score_routes([_metric("A", 2100, 3, 0), _metric("B", 2300, 4, 0, 150)], "facility")
    return explain.build_ai_payload(scored, ROUTES, 50, "안전시설 접근성 우선", False)


def test_payload_has_formatted_numbers_and_no_coordinates():
    p = payload()
    text = json.dumps(p, ensure_ascii=False)
    assert "35.23" not in text and "129.08" not in text      # 위치는 보내지 않는다
    b = p["경로들"][1]
    assert b["최단경로보다_더긴거리"] == "200m" and b["거리"] == "2.3km"
    assert p["경로들"][0]["최단경로보다_더긴거리"] == "없음(최단)"


def test_grounding_accepts_given_numbers_and_rejects_invented():
    pj = json.dumps(payload(), ensure_ascii=False)
    ok = "경로 B는 경로 A보다 200m 길지만 반경 50m 안 CCTV가 4곳이에요. 위급하면 112에 신고하세요."
    assert explain.ai_text_is_grounded(ok, pj)
    assert not explain.ai_text_is_grounded("경로 B는 시설이 7곳 더 많아요.", pj)   # 7은 없는 숫자
    assert not explain.ai_text_is_grounded("경로 B는 약 35% 더 많아요.", pj)      # 35는 있지만 비율은 금지


def test_get_ai_explanation_paths():
    p = payload()
    good = lambda pj, k, m: "경로 B는 200m 더 길지만 CCTV가 4곳이에요."
    text, issue = explain.get_ai_explanation(p, "KEY", "m", caller=good)
    assert text and issue is None

    invented = lambda pj, k, m: "경로 B가 99점으로 훨씬 좋아요."
    text, issue = explain.get_ai_explanation(p, "KEY", "m", caller=invented)
    assert text is None and "없는 숫자" in issue

    def boom(pj, k, m):
        raise ConnectionError()
    text, issue = explain.get_ai_explanation(p, "KEY", "m", caller=boom)
    assert text is None and "ConnectionError" in issue

    assert explain.get_ai_explanation(p, None, "m") == (None, "Gemini 키 없음")


def test_call_gemini_uses_sdk_correctly(monkeypatch):
    seen = {}

    class FakeModels:
        def generate_content(self, model, contents, config):
            seen.update(model=model, contents=contents, config=config)
            return types.SimpleNamespace(text="  설명 문장  ")

    class FakeClient:
        def __init__(self, api_key):
            seen["key"] = api_key
            self.models = FakeModels()

    class FakeConfig:
        def __init__(self, system_instruction):
            self.system_instruction = system_instruction

    genai = types.ModuleType("google.genai")
    genai.Client = FakeClient
    genai_types = types.ModuleType("google.genai.types")
    genai_types.GenerateContentConfig = FakeConfig
    genai.types = genai_types
    google = types.ModuleType("google")
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai_types)

    out = explain.call_gemini('{"추천경로": "B"}', " KEY ", "gemini-x")
    assert out == "설명 문장"
    assert seen["key"] == "KEY" and seen["model"] == "gemini-x"
    assert '"추천경로": "B"' in seen["contents"]
    assert "숫자는 JSON에 적힌 값을" in seen["config"].system_instruction


def test_grounding_catches_number_on_wrong_route():
    pj = json.dumps(payload(), ensure_ascii=False)       # A: CCTV 3곳, B: CCTV 4곳
    assert explain.ai_text_is_grounded("경로 B는 CCTV가 4곳이에요.", pj)
    assert not explain.ai_text_is_grounded("경로 A는 CCTV가 4곳이에요.", pj)   # B의 숫자를 A에 붙임
    # 두 경로를 함께 말하는 문장은 둘의 숫자를 모두 쓸 수 있다
    assert explain.ai_text_is_grounded("경로 B는 경로 A보다 200m 길고 CCTV가 4곳, A는 3곳이에요.", pj)
    # 경로를 말하지 않는 문장은 보낸 숫자 안에서 자유
    assert explain.ai_text_is_grounded("분석 반경 50m 안에서 비교했어요.", pj)
    # 다음 문장에서 다시 경로 A를 말하면 그 문장 기준으로 다시 확인
    assert not explain.ai_text_is_grounded("경로 B는 2.3km예요. 경로 A는 2.3km예요.", pj)


def test_outside_ratio_in_payload_and_percent_allowed():
    m_a = {**_metric("A", 2100, 3, 0), "outside_ratio": 0.35}
    m_b = {**_metric("B", 2300, 4, 0, 150), "outside_ratio": 0.0}
    scored = recommend.score_routes([m_a, m_b], "facility")
    p = explain.build_ai_payload(scored, ROUTES, 50, "균형", False)
    assert p["경로들"][0]["시설데이터_없는지역_비율"] == "35%"
    assert "시설데이터_없는지역_비율" not in p["경로들"][1]
    pj = json.dumps(p, ensure_ascii=False)
    assert explain.ai_text_is_grounded("경로 A는 35%가 데이터가 없는 지역이에요.", pj)
    assert not explain.ai_text_is_grounded("경로 B는 35%가 데이터가 없는 지역이에요.", pj)
    basic = explain.build_basic_explanation(scored, 50, False)
    assert "경로 A의 35%는 시설 데이터가 없는 지역" in basic
