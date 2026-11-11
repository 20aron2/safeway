"""경로 비교 점수와 추천 (담당: 추천 알고리즘). 규칙 기반이며 머신러닝을 쓰지 않는다.

계산 공식 (경로끼리 비교한 상대 점수, 0~100):

    거리 점수   = 가장 짧은 경로 거리 ÷ 이 경로 거리          (가장 짧으면 1)
    시설 점수   = 0.5 × (1km당 CCTV·비상벨 ÷ 가장 높은 값) + 0.5 × (1km당 보안등 ÷ 가장 높은 값)
                  (보안등 데이터가 없으면 CCTV·비상벨만 사용)
    비교 점수   = 100 × (거리 가중치 × 거리 점수 + 시설 가중치 × 시설 점수)

가중치는 팀이 정한 임의의 값이며, 과학적으로 검증된 안전도 지표가 아니다.
"""
from __future__ import annotations

MODES = {
    "shortest": {"label": "최단거리 우선", "short": "최단", "w_dist": 1.0, "w_fac": 0.0},
    "balanced": {"label": "거리·시설 균형", "short": "균형", "w_dist": 0.5, "w_fac": 0.5},
    "facility": {"label": "안전시설 접근성 우선", "short": "시설 우선", "w_dist": 0.3, "w_fac": 0.7},
}
DEFAULT_MODE = "balanced"


def score_routes(metrics: list[dict], mode: str = DEFAULT_MODE) -> dict:
    """경로별 분석 결과에 점수를 붙이고 추천 경로를 고른다."""
    if not metrics:
        return {"mode": mode, "rows": [], "recommended_id": None}
    weights = MODES[mode]
    min_dist = min(m["distance_m"] for m in metrics)
    max_density = max(m["per_km"] for m in metrics)
    max_light = max(m.get("light_per_km", 0.0) for m in metrics)

    rows = []
    for m in metrics:
        dist_score = min_dist / m["distance_m"] if m["distance_m"] > 0 else 0.0
        cb_score = m["per_km"] / max_density if max_density > 0 else 0.0
        if max_light > 0:  # 보안등 데이터가 있으면 CCTV·비상벨과 보안등을 반씩
            fac_score = 0.5 * cb_score + 0.5 * m.get("light_per_km", 0.0) / max_light
        else:
            fac_score = cb_score
        score = 100 * (weights["w_dist"] * dist_score + weights["w_fac"] * fac_score)
        rows.append({**m, "dist_score": dist_score, "fac_score": fac_score, "score": round(score, 1)})

    # 점수가 같으면: 더 짧은 경로 → 시설이 더 많은 경로 순으로 고른다
    best = max(rows, key=lambda r: (r["score"], -r["distance_m"], r["total"]))
    return {"mode": mode, "rows": rows, "recommended_id": best["route_id"]}


def formula_markdown(mode: str) -> str:
    w = MODES[mode]
    return (
        "**비교 점수 계산 방법** (경로끼리 비교한 상대 점수)\n\n"
        "- 거리 점수 = 가장 짧은 경로 거리 ÷ 이 경로 거리\n"
        "- 시설 점수 = 0.5 × (1km당 CCTV·비상벨 ÷ 경로 중 가장 높은 값) "
        "+ 0.5 × (1km당 보안등 ÷ 경로 중 가장 높은 값)  \n"
        "  (보안등 데이터가 없으면 CCTV·비상벨만 써요)\n"
        f"- 비교 점수 = 100 × ({w['w_dist']} × 거리 점수 + {w['w_fac']} × 시설 점수)  "
        f"← 현재 기준: **{w['label']}**\n\n"
        "가중치는 팀이 정한 임의의 값이에요. 과학적으로 검증된 안전도가 아니며, "
        "점수가 높다고 더 안전하다는 뜻이 아니에요."
    )
