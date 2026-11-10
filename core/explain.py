"""비교 결과 설명 문장 (담당: AI 설명).

- build_basic_explanation(): Python 계산 결과만으로 만드는 기본 설명. 항상 동작한다.
- get_ai_explanation(): Gemini 설명 (STEP 5에서 구현). 실패하면 None → 기본 설명을 쓴다.

어느 쪽이든 숫자는 Python이 계산한 값만 쓴다. AI가 숫자를 새로 만들지 않게 한다.
"""
from __future__ import annotations


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
                f"{basis}시설도 1km당 {rec['per_km']:.1f}곳으로 가장 많은 편이에요 "
                f"(CCTV {rec['cctv']}곳, 비상벨 {rec['bell']}곳)."
            )
        else:
            extra = best_density["distance_m"] - rec["distance_m"]
            lines.append(
                f"다만 시설은 **경로 {best_density['route_id']}**가 1km당 {best_density['per_km']:.1f}곳으로 "
                f"더 많아요 ({fmt_distance(extra)} 더 걸어야 해요). "
                f"안전시설 접근성을 중요하게 생각한다면 경로 {best_density['route_id']}도 고려해 보세요."
            )
    else:
        extra_m = rec["distance_m"] - shortest["distance_m"]
        extra_s = rec["duration_s"] - shortest["duration_s"]
        more = _more_phrase(rec, shortest)
        reason = (
            f"{basis}{more}" if more else
            f"{basis}시설이 1km당 {rec['per_km']:.1f}곳으로 경로 {shortest['route_id']}"
            f"({shortest['per_km']:.1f}곳)보다 촘촘해요"
        )
        lines.append(
            f"**경로 {rec['route_id']}**는 최단 경로 {shortest['route_id']}보다 "
            f"{fmt_distance(extra_m)}({fmt_duration(extra_s)}) 길지만, {reason}. "
            f"안전시설 접근성을 중요하게 생각한다면 경로 {rec['route_id']}를 고려할 수 있어요."
        )

    gaps = ", ".join(f"{r['route_id']} {fmt_distance(r['longest_gap_m'])}" for r in rows)
    lines.append(f"반경 안에 시설이 하나도 없는 가장 긴 구간: {gaps}.")
    return "\n\n".join(lines)


def get_ai_explanation(scored: dict, radius_m: float, api_key: str | None) -> str | None:
    """Gemini로 설명 생성 (STEP 5에서 구현). 지금은 항상 None."""
    return None
