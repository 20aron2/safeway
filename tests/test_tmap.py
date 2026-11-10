"""TMAP 연동 테스트. 실제 서버 대신 가짜 응답을 넣어 확인한다."""
import pytest
import requests

from core import routes as rt

START = (35.2316, 129.0846)
END = (35.2380, 129.0880)


def sample_response(offset=0.0):
    """TMAP 응답 형식(GeoJSON)을 흉내 낸 예시. 좌표는 (경도, 위도) 순서."""
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [129.0846, 35.2316]},
             "properties": {"totalDistance": 812, "totalTime": 590, "pointType": "SP"}},
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [
                [129.0846, 35.2316], [129.0850 + offset, 35.2330], [129.0860 + offset, 35.2350]]},
             "properties": {"distance": 400, "time": 300}},
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [129.0860, 35.2350]},
             "properties": {"turnType": 12}},
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [
                [129.0860 + offset, 35.2350], [129.0880, 35.2380]]},
             "properties": {"distance": 412, "time": 290}},
        ],
    }


class FakeResp:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload


def test_parse_flips_lon_lat_and_reads_totals():
    r = rt.parse_tmap_response(sample_response(), "TMAP 추천")
    assert r["coords"][0] == (35.2316, 129.0846) and r["coords"][-1] == (35.2380, 129.0880)
    assert len(r["coords"]) == 4  # 이어지는 구간의 겹치는 점은 한 번만
    assert (r["distance_m"], r["duration_s"], r["source"]) == (812.0, 590, "tmap")


def test_parse_without_route_raises():
    with pytest.raises(rt.RouteError):
        rt.parse_tmap_response({"features": []}, "x")


def test_fetch_sends_lon_lat_and_options(monkeypatch):
    calls = []
    offsets = iter([0.0, 0.003, 0.0])  # 세 번째(대로 우선)는 첫 번째와 같은 경로

    def fake_post(url, headers, json, timeout):
        calls.append((headers["appKey"], json))
        return FakeResp(200, sample_response(next(offsets)))

    monkeypatch.setattr(requests, "post", fake_post)
    routes = rt.get_routes(START, END, source="tmap", app_key=" KEY ")
    assert calls[0][0] == "KEY"
    body = calls[0][1]
    assert (body["startX"], body["startY"]) == ("129.0846", "35.2316")
    assert [c[1]["searchOption"] for c in calls] == ["10", "0", "4"]
    assert [r["id"] for r in routes] == ["A", "B"]          # 같은 경로 하나 제거
    assert [r["label"] for r in routes] == ["TMAP 최단거리", "TMAP 추천"]


def test_bad_key_gives_clear_message_and_stops(monkeypatch):
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        return FakeResp(401, {"error": {"message": "INVALID_API_KEY"}})

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(rt.RouteError, match="키가 올바르지 않거나"):
        rt.get_routes(START, END, source="tmap", app_key="BAD")
    assert len(calls) == 1


def test_partial_failure_keeps_successful_routes(monkeypatch):
    responses = iter([FakeResp(500, {}), FakeResp(200, sample_response()),
                      FakeResp(200, sample_response(0.003))])
    monkeypatch.setattr(requests, "post", lambda *a, **k: next(responses))
    routes = rt.get_routes(START, END, source="tmap", app_key="K")
    assert len(routes) == 2


def test_network_error(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError()

    monkeypatch.setattr(requests, "post", boom)
    with pytest.raises(rt.RouteError, match="연결하지 못했어요"):
        rt.get_routes(START, END, source="tmap", app_key="K")
