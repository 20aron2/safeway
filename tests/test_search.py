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
    assert 0 < station["dist_km"] < 10   # 부산시청 기준 거리


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
    p = seen["params"]   # 결과가 적어서 마지막에 거리순 보충 검색을 했다
    assert p["searchKeyword"] == "부산대역" and p["searchtypCd"] == "R" and p["radius"] == "30"
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


def test_find_police_filters_and_dedupes(monkeypatch):
    payload = {"searchPoiInfo": {"pois": {"poi": [
        {"name": "부산금정경찰서 장전지구대", "noorLat": "35.2350", "noorLon": "129.0870"},
        {"name": "지구대 앞 식당", "noorLat": "35.2351", "noorLon": "129.0871"},
        {"name": "부곡치안센터[부산]", "noorLat": "35.2400", "noorLon": "129.0900"},
    ]}}}
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append((params["searchKeyword"], params["radius"]))
        return FakeResp(200, payload)

    monkeypatch.setattr(requests, "get", fake_get)
    found = sr.find_police((35.23, 129.08), "K")
    assert [p["name"] for p in found] == ["부산금정경찰서 장전지구대", "부곡치안센터[부산]"]  # 중복·식당 제외
    assert calls == [("지구대", "2"), ("파출소", "2")]   # 거리순(R) 검색만 쓴다


def _poi(name, lat, lon):
    return {"name": name, "noorLat": str(lat), "noorLon": str(lon)}


def _pois(*items):
    return {"searchPoiInfo": {"pois": {"poi": [_poi(*i) for i in items]}}}


def test_name_match_comes_first_like_map_apps(monkeypatch):
    """'부산대역'을 찾으면 시청 근처 교대역 출구가 아니라 부산대역이 맨 위."""
    accuracy = _pois(("교대역 1번출구", 35.1960, 129.0805), ("교대역[부산1호선]", 35.1958, 129.0802),
                     ("부산대역 3번출구", 35.2297, 129.0893), ("부산대학교", 35.2330, 129.0790),
                     ("부산대역[부산1호선]", 35.2295, 129.0896), ("서울 부산대역 식당", 37.56, 126.97),
                     ("부산대앞 버스정류장", 35.2300, 129.0880))
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append(params["searchtypCd"])
        return FakeResp(200, accuracy if params["searchtypCd"] == "A" else {})

    monkeypatch.setattr(requests, "get", fake_get)
    names = [p["name"] for p in sr.search_places("부산대역", "K")]
    assert names[:2] == ["부산대역[부산1호선]", "부산대역 3번출구"]   # 역 → 출구 순
    assert "서울 부산대역 식당" not in names                         # 부산 밖은 뺀다
    assert names.index("교대역[부산1호선]") > names.index("부산대학교")
    assert calls == ["A"]                                            # 6개 이상이라 보충 검색 안 함


def test_bias_orders_same_name_by_distance_and_fallback_merges(monkeypatch):
    far = (35.10, 129.03)     # 남포동 쪽
    near = (35.23, 129.09)    # 장전동 쪽
    a_res = _pois(("스타벅스 남포점", *far), ("스타벅스 부산대점", *near))
    r_res = _pois(("스타벅스 장전역점", 35.2350, 129.0870), ("스타벅스 부산대점", *near))
    seen_center = {}

    def fake_get(url, params, headers, timeout):
        if params["searchtypCd"] == "R":
            seen_center["c"] = (params["centerLat"], params["centerLon"])
            return FakeResp(200, r_res)
        return FakeResp(200, a_res)

    monkeypatch.setattr(requests, "get", fake_get)
    names = [p["name"] for p in sr.search_places("스타벅스", "K", bias=(35.23, 129.08))]
    assert names[0] in ("스타벅스 부산대점", "스타벅스 장전역점") and names[-1] == "스타벅스 남포점"
    assert len(names) == 3                                   # 중복 없이 합침
    assert seen_center["c"] == ("35.23", "129.08")           # 보충 검색은 다른 쪽 지점 근처에서


def test_relevance_tiers():
    assert sr.relevance("부산대역 [1호선]", "부산대역") == 0
    assert sr.relevance("부산대학교 정문", "부산대") == 1
    assert sr.relevance("국립부산대학교", "부산대") == 2
    assert sr.relevance("교대역 1번출구", "부산대역") == 5
    assert sr.relevance("부산대역 1번출구", "부산대역 1번출구") == 0


def test_find_stores_keeps_only_store_brands(monkeypatch):
    pois = _pois(("GS25 부산대점", 35.233, 129.085), ("CU 앞 주차장", 35.2331, 129.0851),
                 ("CUBE 카페", 35.234, 129.086), ("CU장전역점", 35.237, 129.088),
                 ("세븐일레븐 부산대점", 35.233, 129.085))
    seen = []

    def fake_get(url, params, headers, timeout):
        seen.append((params["searchKeyword"], params["searchtypCd"], params["count"]))
        return FakeResp(200, pois)

    monkeypatch.setattr(requests, "get", fake_get)
    names = [p["name"] for p in sr.find_stores((35.23, 129.08), "K")]
    assert names == ["GS25 부산대점", "CU장전역점"]          # 주차장·다른 가게·같은 자리 중복 제외
    assert [k for k, _, _ in seen] == list(sr.STORE_KEYWORDS) and all(t == "R" and c == "50" for _, t, c in seen)


def test_reverse_geocode(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(
        200, {"addressInfo": {"fullAddress": "부산광역시 금정구 장전동 1,부산광역시 금정구 부산대학로 63"}}))
    assert sr.reverse_geocode(35.23, 129.08, "K") == "부산광역시 금정구 장전동 1"
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(500, {}))
    assert sr.reverse_geocode(35.23, 129.08, "K") is None

    def boom(*a, **k):
        raise requests.ConnectionError
    monkeypatch.setattr(requests, "get", boom)
    assert sr.reverse_geocode(35.23, 129.08, "K") is None
