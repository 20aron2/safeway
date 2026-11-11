"""TMAP 지도 부품 (담당: 지도 UI).

folium 대신 TMAP 웹 지도를 쓰는 Streamlit 부품. 화면 쪽은 core/tmap_component/index.html.template.

- build_payload(): 지도에 그릴 내용을 JSON으로 정리 (map_view.build_map 과 같은 재료)
- render(): 지도를 그리고, 클릭하면 {"last_clicked": {"lat", "lng"}} 를 돌려준다
  (st_folium 과 같은 모양이라 app.py 의 클릭 처리 코드를 그대로 쓴다)

TMAP 웹 지도는 키를 페이지 안에 넣어야 해서, 실행할 때 임시 폴더에 index.html을 만든다.
이 파일은 GitHub에 올라가지 않는다. 브라우저에서 쓰는 지도 키는 원래 페이지 소스에서 보인다.
"""
from __future__ import annotations

import hashlib
import tempfile
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import config

TEMPLATE = Path(__file__).resolve().parent / "tmap_component" / "index.html.template"


def _pt(p) -> list[float]:
    return [round(float(p[0]), 6), round(float(p[1]), 6)]


def build_payload(start=None, end=None, start_name=None, end_name=None, routes=None,
                  selected_id=None, facilities: pd.DataFrame | None = None, near_ids=(),
                  gap_segments=(), police=(), night: bool = False, dark_segments=(), stores=()) -> dict:
    routes = routes or []
    near = set(map(str, near_ids))
    # 선택한 경로를 마지막에 두어 맨 위에 그려지게 한다
    ordered = sorted(enumerate(routes), key=lambda ir: ir[1]["id"] == selected_id)
    route_items = [{
        "coords": [_pt(c) for c in r["coords"]],
        "color": config.ROUTE_COLORS[i % len(config.ROUTE_COLORS)],
        "selected": r["id"] == selected_id,
    } for i, r in ordered]

    lights, others = [], []
    if facilities is not None and len(facilities):
        for row in facilities.itertuples(index=False):
            item = {"lat": round(float(row.lat), 6), "lon": round(float(row.lon), 6),
                    "kind": row.kind, "name": row.name or "", "on": str(row.id) in near}
            (lights if row.kind == "light" else others).append(item)

    fit_points = [_pt(p) for p in (start, end) if p] + [_pt(c) for r in routes for c in r["coords"]]
    fit_key = hashlib.md5(repr((fit_points[:2], fit_points[-1:] if fit_points else [],
                                len(fit_points))).encode()).hexdigest()

    return {
        "center": _pt(fit_points[0]) if len(fit_points) == 1 else list(config.DEFAULT_CENTER),
        "zoom": config.DEFAULT_ZOOM,
        "height": config.MAP_HEIGHT_PX,
        "start": _pt(start) if start else None,
        "end": _pt(end) if end else None,
        "start_name": start_name or "",
        "end_name": end_name or "",
        "routes": route_items,
        "gaps": [{"coords": [_pt(c) for c in g["coords"]], "length_m": g["length_m"]} for g in gap_segments],
        "dark": [{"coords": [_pt(c) for c in g["coords"]], "length_m": g["length_m"]} for g in dark_segments],
        "facilities": others,
        "lights": lights,
        "police": [{"lat": p["lat"], "lon": p["lon"], "name": p["name"]} for p in police],
        "stores": [{"lat": p["lat"], "lon": p["lon"], "name": p["name"]} for p in stores],
        "fit_points": fit_points,
        "fit_key": fit_key,
        "night": bool(night),
    }


@lru_cache(maxsize=4)
def _component(app_key: str):
    """키를 넣은 index.html을 임시 폴더에 만들고 Streamlit 부품으로 등록한다."""
    import streamlit.components.v1 as components

    digest = hashlib.sha256(app_key.encode()).hexdigest()[:10]
    folder = Path(tempfile.gettempdir()) / f"safeway_tmap_{digest}"
    folder.mkdir(parents=True, exist_ok=True)
    html = TEMPLATE.read_text(encoding="utf-8").replace("__APPKEY__", app_key.strip())
    (folder / "index.html").write_text(html, encoding="utf-8")
    return components.declare_component("safeway_tmap_map", path=str(folder))


def render(payload: dict, app_key: str, key: str = "tmap_map"):
    """TMAP 지도를 그린다. 클릭하면 {'last_clicked': {...}} 를, 아니면 None을 돌려준다."""
    return _component(app_key)(data=payload, key=key, default=None)
