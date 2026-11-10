"""장소 검색 테스트. 실제 TMAP 대신 가짜 응답을 넣어 확인한다."""
import pytest
import requests

from core import search as sr


def sample_pois():
    """TMAP 장소 검색 응답 형식을 흉내 낸 예시. 값은 모두 문자열로 온다."""
    return {"searchPoiInfo": {"totalCount": "3", "count": "3", "page": "1", "pois": {"poi": [
        {"name": "부산대역[1호선]", "noorLat": "35.22950", "noorLon": "129.08960",
         "frontLat": "35.22940", "frontLon": "129.08950",
         "upperAddrName": "부산", "middleAddrName": "금정구", "lowerAddrName": "장전동",
         "newAddressList": {"newAddress": [{"fullAddressRoad": "부산 금정구 중앙대로 지하1763"}]}},
        {"name": "부산대학교", "noorLat": "35.23300", "noorLon": "129.07900",
         "frontLat": "0", "frontLon": "0",                      # 출입구 좌표 없음 → 중심 좌표
         "upperAddrName": "부산", "middleAddrName": "금정구", "lowerAddrName": "장전동"},
        {"name": "좌표없는곳", "noorLat": "", "noorLon": ""},  # 버린다
        {"name": "부산대역[1호선]", "noorLat": "35.22950", "noorLon": "129.08960",
         "frontLat": "35.22940", "frontLon": "129.08950"},     # 중복 → 버린다
    ]}}}


class FakeResp:
    def __init__(self, status, payload=None, content=b"x"):
        self.status_code, self._payload, self.content = status, payload, content

    def json(self):
        return self._payload


def test_parse_prefers_entrance_and_drops_bad_rows():
    out = sr.parse_poi_response(sample_pois())
    assert [p["name"] for p in out] == ["부산대역[1호선]", "부산대학교"]
    station, univ = out
    assert (station["lat"], station["lon"]) == (35.2294, 129.0895)   # 출입구 좌표
    assert station["address"] == "부산 금정구 중앙대로 지하1763"
    assert (univ["lat"], univ["lon"]) == (35.233, 129.079)          # 중심 좌표로 대체
    assert univ["address"] == "부산 금정구 장전동"
    assert 0 < station["dist_km"] < 1


def test_parse_single_result_dict_and_empty():
    one = {"searchPoiInfo": {"pois": {"poi": {"name": "A", "noorLat": "35.2", "noorLon": "129.1"}}}}
    assert len(sr.parse_poi_response(one)) == 1
    assert sr.parse_poi_response({}) == []


def test_search_request_shape(monkeypatch):
    seen = {}

    def fake_get(url, params, headers, timeout):
        seen.update(url=url, params=params, headers=headers)
        return FakeResp(200, sample_pois())

    monkeypatch.setattr(requests, "get", fake_get)
    out = sr.search_places("  부산대역 ", " KEY ")
    assert len(out) == 2
    assert seen["headers"]["appKey"] == "KEY"
    p = seen["params"]
    assert p["searchKeyword"] == "부산대역" and p["searchtypCd"] == "R" and p["radius"] == "10"
    assert p["resCoordType"] == "WGS84GEO"


def test_no_content_means_no_results(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(204, None, b""))
    assert sr.search_places("없는장소", "K") == []


@pytest.mark.parametrize("status,msg", [(401, "키가 올바르지"), (429, "사용량"), (500, "오류 500")])
def test_search_errors(monkeypatch, status, msg):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(status, {}))
    with pytest.raises(sr.SearchError, match=msg):
        sr.search_places("부산대역", "K")


def test_short_keyword_rejected():
    with pytest.raises(sr.SearchError, match="두 글자"):
        sr.search_places("a", "K")
