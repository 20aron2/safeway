"""비교 결과 설명 문장 (담당: AI 설명).

- build_basic_explanation(): Python 계산 결과만으로 만드는 기본 설명. 항상 동작한다.
- get_ai_explanation(): Gemini 설명. 실패하거나 숫자를 지어내면 None → 기본 설명을 쓴다.

어느 쪽이든 숫자는 Python이 계산한 값만 쓴다. AI가 숫자를 새로 만들지 않게 한다.
"""
from __future__ import annotations

import json
import re

COVERAGE_WARN_RATIO = 0.1  # config와 같은 값 (순환 import를 피하려고 따로 둔다)


def fmt_distance(m: float) -> str:
    m = abs(m)
    return f"{m:.0f}m" if m < 1000 else f"{m / 1000:.1f}km"


def fmt_duration(s: float) -> str:
    minutes = round(abs(s) / 60)
    return "1분 미만" if minutes < 1 else f"약 {minutes}분"


def _more_phrase(rec: dict, other: dict) -> str | None:
    parts = []
    if rec["cctv"] > other["cctv"]:
        parts.append(f"CCTV 지점이 {rec['cctv'] - other['cctv']}곳")
    if rec["bell"] > other["bell"]:
        parts.append(f"비상벨이 {rec['bell'] - other['bell']}곳")
    return " 더 많고 ".join(parts) + " 더 많아요" if parts else None


def build_basic_explanation(scored: dict, radius_m: float, facilities_are_demo: bool) -> str:
    rows = scored["rows"]
    if not rows:
        return "분석할 경로가 없어요."
    by_id = {r["route_id"]: r for r in rows}
    rec = by_id[scored["recommended_id"]]
    shortest = min(rows, key=lambda r: r["distance_m"])
    if rec["distance_m"] - shortest["distance_m"] < 1:  # 거리가 같으면 추천 경로를 최단으로 본다
        shortest = rec
    basis = f"경로에서 {radius_m:.0f}m 안에 등록된 " + ("가상 " if facilities_are_demo else "")
    lines = []

    if len(rows) == 1:
        lines.append(
            f"비교할 다른 경로가 없어 경로 {rec['route_id']} 하나만 분석했어요. "
            f"{basis}CCTV {rec['cctv']}곳, 비상벨 {rec['bell']}곳이 있어요."
        )
        return "\n\n".join(lines)

    if rec["route_id"] == shortest["route_id"]:
        lines.append(
            f"**경로 {rec['route_id']}**가 가장 짧아요 "
            f"({fmt_distance(rec['distance_m'])}, {fmt_duration(rec['duration_s'])})."
        )
        best_density = max(rows, key=lambda r: r["per_km"])
        if best_density["route_id"] == rec["route_id"] or best_density["per_km"] == rec["per_km"]:
            lines.append(
                f"{basis}CCTV·비상벨도 1km당 {rec['per_km']:.1f}곳으로 가장 많은 편이에요 "
                f"(CCTV {rec['cctv']}곳, 비상벨 {rec['bell']}곳)."
            )
        else:
            extra = best_density["distance_m"] - rec["distance_m"]
            lines.append(
                f"다만 CCTV·비상벨은 **경로 {best_density['route_id']}**가 1km당 {best_density['per_km']:.1f}곳으로 "
                f"더 많아요 ({fmt_distance(extra)} 더 걸어야 해요). "
                f"안전시설 접근성을 중요하게 생각한다면 경로 {best_density['route_id']}도 고려해 보세요."
            )
    else:
        extra_m = rec["distance_m"] - shortest["distance_m"]
        extra_s = rec["duration_s"] - shortest["duration_s"]
        more = _more_phrase(rec, shortest)
        reason = (
            f"{basis}{more}" if more else
            f"{basis}CCTV·비상벨이 1km당 {rec['per_km']:.1f}곳으로 경로 {shortest['route_id']}"
            f"({shortest['per_km']:.1f}곳)보다 촘촘해요"
        )
        lines.append(
            f"**경로 {rec['route_id']}**는 최단 경로 {shortest['route_id']}보다 "
            f"{fmt_distance(extra_m)}({fmt_duration(extra_s)}) 길지만, {reason}. "
            f"안전시설 접근성을 중요하게 생각한다면 경로 {rec['route_id']}를 고려할 수 있어요."
        )

    if any(r.get("light_per_km") for r in rows):
        lights = ", ".join(f"{r['route_id']} {r['light_per_km']:.1f}곳" for r in rows)
        lines.append(f"1km당 보안등: {lights}.")
    outside = [r for r in rows if r.get("outside_ratio", 0) >= COVERAGE_WARN_RATIO]
    if outside:
        parts = ", ".join(f"경로 {r['route_id']}의 {r['outside_ratio'] * 100:.0f}%" for r in outside)
        lines.append(f"⚠️ {parts}는 시설 데이터가 없는 지역이에요. 그 구간의 시설 수는 실제보다 적게 나올 수 있어요.")
    gaps = ", ".join(f"{r['route_id']} {fmt_distance(r['longest_gap_m'])}" for r in rows)
    lines.append(f"반경 안에 CCTV·비상벨이 하나도 없는 가장 긴 구간: {gaps}.")
    return "\n\n".join(lines)


# ---------------------------------------------------------------- Gemini 설명

AI_SYSTEM = (
    "너는 야간 보행 경로 비교 앱 '안심길'의 설명 도우미야. 사용자가 준 JSON의 계산 결과만 보고 "
    "한국어로 3~4문장의 짧은 설명을 써. 규칙: "
    "(1) 숫자는 JSON에 적힌 값을 글자 그대로만 써. 새로 계산하거나 반올림하거나 단위를 바꾸지 마. "
    "(2) 추천 경로가 왜 추천됐는지, 다른 경로와 무엇이 다른지 말해. "
    "(3) '안전하다', '위험하다'고 단정하지 말고 '등록된 시설이 더 많다'처럼 사실만 말해. "
    "(4) 마지막 문장은 공공데이터가 실제 작동 여부나 현장 상황을 알려주지 않는다는 짧은 주의로 끝내. "
    "(5) 제목, 목록, 표 없이 문단 하나로 써. "
    "(6) '~해요', '~예요'처럼 부드러운 해요체로 써. "
    "(7) 한 문장에서 경로의 숫자를 말할 때는 그 숫자가 속한 경로 이름을 같은 문장에 꼭 써. "
    "(8) 시설데이터_없는지역_비율이 있는 경로는, 그 경로의 시설 수가 실제보다 적게 나올 수 있다고 알려 줘."
)


def build_ai_payload(scored: dict, routes: list[dict], radius_m: float,
                     mode_label: str, facilities_are_demo: bool) -> dict:
    """Gemini에 보낼 계산 결과. 위치 좌표는 보내지 않는다 (개인정보 최소화)."""
    rows = scored["rows"]
    label_of = {r["id"]: r["label"] for r in routes}
    shortest = min(rows, key=lambda r: r["distance_m"])
    out = []
    for r in rows:
        extra_m = r["distance_m"] - shortest["distance_m"]
        extra_s = r["duration_s"] - shortest["duration_s"]
        out.append({
            "경로": r["route_id"],
            "종류": label_of.get(r["route_id"], ""),
            "거리": fmt_distance(r["distance_m"]),
            "예상시간": fmt_duration(r["duration_s"]),
            "최단경로보다_더긴거리": "없음(최단)" if extra_m < 1 else fmt_distance(extra_m),
            "최단경로보다_더걸리는시간": "없음(최단)" if extra_m < 1 else fmt_duration(extra_s),
            "반경안_CCTV": f"{r['cctv']}곳",
            "반경안_비상벨": f"{r['bell']}곳",
            "1km당_CCTV와비상벨": f"{r['per_km']:.1f}곳",
            "CCTV와비상벨이_없는_최장구간": fmt_distance(r["longest_gap_m"]),
            **({"반경안_보안등": f"{r['light']}곳", "1km당_보안등": f"{r['light_per_km']:.1f}곳"}
               if r.get("light_per_km") else {}),
            "비교점수": f"{r['score']:.0f}점",
            **({"시설데이터_없는지역_비율": f"{r['outside_ratio'] * 100:.0f}%"}
               if r.get("outside_ratio", 0) >= COVERAGE_WARN_RATIO else {}),
        })
    return {
        "추천경로": scored["recommended_id"],
        "추천기준": mode_label,
        "분석반경": f"{radius_m:.0f}m",
        "시설데이터": "가상 데이터(실제 위치 아님)" if facilities_are_demo
                      else "구청에 등록된 CCTV·비상벨·보안등 (공공데이터포털)",
        "경로들": out,
    }


_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def numbers_in(text: str) -> set[str]:
    return set(_NUMBER.findall(text))


_ROUTE_REF = re.compile(r"경로\s*([A-Z])")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def percents_in(text: str) -> set[str]:
    return set(_PERCENT.findall(text))
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def ai_text_is_grounded(ai_text: str, payload_json: str) -> bool:
    """AI 문장의 숫자가 보낸 계산 결과에서 왔는지 확인한다 (지어낸 숫자·잘못 붙인 숫자 차단).

    1) 모든 숫자는 보낸 데이터 안에 있어야 한다.
    2) 문장이 특정 경로(예: '경로 B')를 말하면, 그 문장의 숫자는 그 경로의 값이나
       공통 값(분석 반경 등)이어야 한다. 경로 A의 숫자를 경로 B에 붙이면 걸린다.
    """
    if "%" in ai_text and "%" not in payload_json:  # 보내지 않은 비율을 만들어 냈다
        return False
    try:
        payload = json.loads(payload_json)
    except ValueError:
        return False
    routes = payload.get("경로들") or []
    common = {k: v for k, v in payload.items() if k != "경로들"}
    common_text = json.dumps(common, ensure_ascii=False)
    route_text = {r.get("경로"): json.dumps(r, ensure_ascii=False) for r in routes}
    common_nums = numbers_in(common_text) | {"112"}
    per_route = {rid: numbers_in(t) for rid, t in route_text.items()}
    # 비율(%)은 비율끼리만 맞춘다. '35%'가 '약 35분'의 35로 통과하지 않게.
    common_pct = percents_in(common_text)
    per_route_pct = {rid: percents_in(t) for rid, t in route_text.items()}
    all_nums = common_nums.union(*per_route.values())
    all_pct = common_pct.union(*per_route_pct.values())

    if not numbers_in(ai_text) <= all_nums or not percents_in(ai_text) <= all_pct:
        return False
    for sentence in _SENTENCE_END.split(ai_text):
        nums, pcts = numbers_in(sentence), percents_in(sentence)
        named = [rid for rid in _ROUTE_REF.findall(sentence) if rid in per_route]
        if not (nums or pcts) or not named:
            continue
        allowed = common_nums.union(*(per_route[rid] for rid in named))
        allowed_pct = common_pct.union(*(per_route_pct[rid] for rid in named))
        if not nums <= allowed or not pcts <= allowed_pct:
            return False
    return True


def call_gemini(payload_json: str, api_key: str, model: str) -> str:
    """Gemini 호출. 실패하면 예외를 그대로 올린다 (화면에서 기본 설명으로 대체)."""
    from google import genai  # 키가 있을 때만 필요해서 여기서 불러온다
    from google.genai import types

    client = genai.Client(api_key=api_key.strip())
    resp = client.models.generate_content(
        model=model,
        contents="다음 경로 비교 결과를 설명해 줘.\n" + payload_json,
        config=types.GenerateContentConfig(system_instruction=AI_SYSTEM),
    )
    text = (resp.text or "").strip()
    if not text:
        raise ValueError("빈 응답")
    return text


def get_ai_explanation(payload: dict, api_key: str | None, model: str,
                       caller=call_gemini) -> tuple[str | None, str | None]:
    """(AI 설명, 실패 이유)를 돌려준다. 둘 중 하나는 None."""
    if not api_key:
        return None, "Gemini 키 없음"
    payload_json = json.dumps(payload, ensure_ascii=False)
    try:
        text = caller(payload_json, api_key, model)
    except Exception as e:  # 네트워크, 키, 사용량, 모델 이름 오류 등 무엇이든 기본 설명으로
        return None, f"Gemini 호출 실패 ({type(e).__name__})"
    if not ai_text_is_grounded(text, payload_json):
        return None, "AI가 계산 결과에 없는 숫자를 써서 사용하지 않음"
    return text, None
