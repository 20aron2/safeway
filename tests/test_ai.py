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
