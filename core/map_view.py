"""지도 그리기 (담당: 지도 UI). folium 지도 객체를 만들어 돌려준다."""
from __future__ import annotations

import folium
import pandas as pd

try:
    from folium.plugins import LocateControl
except ImportError:  # 아주 오래된 folium
    LocateControl = None

from . import config
from .explain import fmt_distance

PIN_COLORS = {"출발": "#111827", "도착": "#DC2626"}


def _pin(label: str) -> folium.DivIcon:
    html = (
        f'<div style="background:{PIN_COLORS[label]};color:#fff;font:600 12px/1 sans-serif;'
        'padding:6px 9px;border-radius:12px;white-space:nowrap;text-align:center;'
        f'box-shadow:0 1px 4px rgba(0,0,0,.35)">{label}</div>'
    )
    return folium.DivIcon(html=html, icon_size=(46, 24), icon_anchor=(23, 30), class_name="empty")


def _facility_icon(kind: str, emphasized: bool) -> folium.DivIcon:
    emoji = "📷" if kind == "cctv" else "🔔"
    opacity = 1.0 if emphasized else 0.35
    html = (
        f'<div style="font-size:15px;line-height:22px;text-align:center;opacity:{opacity};'
        f'filter:drop-shadow(0 1px 1px rgba(0,0,0,.35))">{emoji}</div>'
    )
    return folium.DivIcon(html=html, icon_size=(22, 22), icon_anchor=(11, 11), class_name="empty")


def _police_icon() -> folium.DivIcon:
    html = ('<div style="font-size:16px;line-height:24px;width:24px;text-align:center;background:#fff;'
            'border:2px solid #1D4ED8;border-radius:50%;box-shadow:0 1px 3px rgba(0,0,0,.35)">🚓</div>')
    return folium.DivIcon(html=html, icon_size=(28, 28), icon_anchor=(14, 14), class_name="empty")


def build_map(start=None, end=None, start_name=None, end_name=None, routes=None, selected_id=None,
              facilities: pd.DataFrame | None = None, near_ids=(),
              vworld_key: str | None = None, gap_segments=(), police=(),
              night: bool = False) -> folium.Map:
    routes = routes or []
    points = [p for p in (start, end) if p] + [c for r in routes for c in r["coords"]]
    center = points[0] if len(points) == 1 else config.DEFAULT_CENTER

    if vworld_key:
        m = folium.Map(location=center, zoom_start=config.DEFAULT_ZOOM,
                       tiles=None, control_scale=True, max_zoom=19)
        layer = config.VWORLD_NIGHT_LAYER if night else config.VWORLD_LAYER
        ext = "jpeg" if layer == "Satellite" else "png"
        folium.TileLayer(
            tiles=config.VWORLD_URL.format(key=vworld_key, layer=layer, ext=ext),
            attr=config.VWORLD_ATTR, name="브이월드", max_zoom=19, min_zoom=6,
            detect_retina=True,  # 고해상도 화면에서 한 단계 더 촘촘한 지도를 받아 선명하게
        ).add_to(m)
    else:
        m = folium.Map(location=center, zoom_start=config.DEFAULT_ZOOM,
                       tiles=config.MAP_TILES, control_scale=True)

    # 경로: 선택한 경로를 마지막에 그려서 맨 위에 보이게
    color_of = {r["id"]: config.ROUTE_COLORS[i % len(config.ROUTE_COLORS)] for i, r in enumerate(routes)}
    for r in sorted(routes, key=lambda r: r["id"] == selected_id):
        selected = r["id"] == selected_id
        folium.PolyLine(
            r["coords"], color=color_of[r["id"]],
            weight=7 if selected else 4, opacity=0.95 if selected else 0.35,
            tooltip=f"경로 {r['id']} · {fmt_distance(r['distance_m'])}",
        ).add_to(m)

    # 선택한 경로에서 반경 안에 시설이 없는 구간: 빨간 점선
    for gap in gap_segments:
        folium.PolyLine(
            gap["coords"], color="#DC2626", weight=5, opacity=0.95, dash_array="2 10",
            tooltip=f"CCTV·비상벨 없는 구간 {fmt_distance(gap['length_m'])}",
        ).add_to(m)

    # 지구대·파출소 (참고용, 점수에는 넣지 않음)
    for p in police:
        folium.Marker([p["lat"], p["lon"]], icon=_police_icon(),
                      tooltip=f"🚓 {p['name']}").add_to(m)

    # 시설: 선택한 경로 반경 안의 시설은 진하게
    if facilities is not None and len(facilities):
        near = set(near_ids)
        # 보안등은 수가 많아 작은 노란 점으로 (선택한 경로 반경 안이면 진하게)
        for row in facilities[facilities["kind"] == "light"].itertuples(index=False):
            on = str(row.id) in near
            folium.CircleMarker(
                [row.lat, row.lon], radius=3 if on else 2, weight=0,
                fill=True, fill_color="#EAB308", fill_opacity=0.95 if on else 0.35,
                tooltip=row.name or "보안등",
            ).add_to(m)
        for row in facilities[facilities["kind"] != "light"].itertuples(index=False):
            folium.Marker(
                [row.lat, row.lon],
                icon=_facility_icon(row.kind, str(row.id) in near),
                tooltip=row.name or ("CCTV" if row.kind == "cctv" else "비상벨"),
            ).add_to(m)

    if start:
        folium.Marker(start, icon=_pin("출발"), tooltip=f"출발: {start_name or '출발지'}").add_to(m)
    if end:
        folium.Marker(end, icon=_pin("도착"), tooltip=f"도착: {end_name or '도착지'}").add_to(m)

    # 내 위치 버튼: 누르면 파란 점으로 현재 위치를 보여주고 움직이면 따라간다.
    # 브라우저 안에서만 처리되고 서버로 보내지 않는다.
    if LocateControl is not None:
        LocateControl(
            auto_start=False, position="topleft", flyTo=True,
            strings={"title": "내 위치 보기"},
            locateOptions={"enableHighAccuracy": True, "maxZoom": 17},
        ).add_to(m)

    if len(points) >= 2:
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(30, 30), max_zoom=17)
    return m
