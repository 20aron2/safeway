"""화면 꾸미기: CSS와 카드 HTML (담당: 지도 UI)."""
from __future__ import annotations

from html import escape

import streamlit as st

from . import texts
from .explain import fmt_distance, fmt_duration

CSS = """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 960px;}
.sw-header {display:flex; align-items:center; gap:.7rem; margin-bottom:.2rem;}
.sw-logo {width:42px; height:42px; border-radius:12px; background:#111827; color:#fff;
  display:flex; align-items:center; justify-content:center; font-size:22px; flex-shrink:0;}
.sw-title {font-size:1.55rem; font-weight:700; line-height:1.2; margin:0; color:#111827;}
.sw-title span {font-size:.95rem; font-weight:500; color:#9CA3AF; margin-left:.35rem;}
.sw-sub {color:#6B7280; margin:.1rem 0 0; font-size:.95rem;}
.sw-banner {border:1px dashed #F59E0B; background:#FFFBEB; color:#92400E; border-radius:10px;
  padding:.55rem .8rem; font-size:.86rem; margin:.9rem 0 .6rem; line-height:1.55;}
.sw-banner.real {border-style:solid; border-color:#A7F3D0; background:#ECFDF5; color:#065F46;}
.sw-guide {font-size:.95rem; color:#111827; padding-top:.35rem;}
.sw-chips {display:flex; gap:.4rem; flex-wrap:wrap; margin-top:.35rem;}
.sw-chip {font-size:.78rem; padding:.18rem .6rem; border-radius:999px; background:#F3F4F6; color:#6B7280;}
.sw-chip.on {background:#111827; color:#fff;}
.sw-legend {font-size:.8rem; color:#6B7280; margin:-.4rem 0 .6rem;}
.sw-card {border:1px solid #E5E7EB; border-top:4px solid var(--c); border-radius:14px;
  padding:.85rem 1rem; background:#fff; margin-bottom:.6rem;}
.sw-card.sel {box-shadow:0 0 0 2px var(--c);}
.sw-card-head {display:flex; align-items:center; justify-content:space-between; font-weight:700; color:#111827;}
.sw-badge {background:#111827; color:#fff; font-size:.7rem; padding:.15rem .5rem; border-radius:999px; font-weight:600;}
.sw-label {color:#9CA3AF; font-size:.76rem; margin:.1rem 0 .6rem;}
.sw-grid {display:grid; grid-template-columns:1fr 1fr; gap:.5rem .8rem;}
.sw-k {color:#6B7280; font-size:.74rem;}
.sw-v {font-weight:600; font-size:1rem; color:#111827;}
.sw-score {margin-top:.65rem; padding-top:.5rem; border-top:1px solid #F3F4F6; font-size:.8rem; color:#374151;}
.sw-foot {font-size:.78rem; color:#9CA3AF; line-height:1.6; margin-top:1.2rem;}
div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] {width:100%;}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def header() -> None:
    st.markdown(
        '<div class="sw-header"><div class="sw-logo">🛡️</div><div>'
        f'<p class="sw-title">{texts.APP_NAME}<span>{texts.APP_NAME_EN}</span></p>'
        f'<p class="sw-sub">{texts.TAGLINE}</p></div></div>',
        unsafe_allow_html=True,
    )


def data_banner(route_source: str, facility_source: str) -> None:
    route_note = texts.DEMO_ROUTE_NOTE if route_source == "demo" else texts.REAL_ROUTE_NOTE
    fac_note = texts.DEMO_FACILITY_NOTE if facility_source == "demo" else texts.REAL_FACILITY_NOTE
    is_demo = route_source == "demo" or facility_source == "demo"
    title = f"<b>⚠️ {texts.DEMO_BANNER_TITLE}</b><br>" if is_demo else "<b>실제 데이터 모드</b><br>"
    css_class = "sw-banner" if is_demo else "sw-banner real"
    st.markdown(f'<div class="{css_class}">{title}· {route_note}<br>· {fac_note}</div>',
                unsafe_allow_html=True)


def pick_status(start, end) -> None:
    if start is None:
        guide = texts.PICK_GUIDE_START
    elif end is None:
        guide = texts.PICK_GUIDE_END
    else:
        guide = texts.PICK_GUIDE_READY
    st.markdown(guide)
    chips = (
        f'<span class="sw-chip{" on" if start else ""}">출발 {"✓" if start else "미지정"}</span>'
        f'<span class="sw-chip{" on" if end else ""}">도착 {"✓" if end else "미지정"}</span>'
    )
    st.markdown(f'<div class="sw-chips">{chips}</div>', unsafe_allow_html=True)


def legend(radius_m: float | None) -> None:
    extra = f" · 진하게 표시된 시설 = 선택한 경로 {radius_m:.0f}m 안" if radius_m else ""
    st.markdown(f'<div class="sw-legend">📷 CCTV · 🔔 비상벨{extra}</div>', unsafe_allow_html=True)


def route_card(row: dict, route: dict, color: str, recommended: bool, selected: bool,
               facilities_are_demo: bool) -> None:
    badge = '<span class="sw-badge">추천</span>' if recommended else ""
    prefix = "가상 " if facilities_are_demo else ""
    stats = [
        ("거리", fmt_distance(row["distance_m"])),
        ("예상 시간", fmt_duration(row["duration_s"])),
        (f"📷 {prefix}CCTV", f"{row['cctv']}곳"),
        (f"🔔 {prefix}비상벨", f"{row['bell']}곳"),
        ("1km당 시설", f"{row['per_km']:.1f}곳"),
        ("시설 없는 최장 구간", fmt_distance(row["longest_gap_m"])),
    ]
    grid = "".join(f'<div><div class="sw-k">{k}</div><div class="sw-v">{v}</div></div>' for k, v in stats)
    html = (
        f'<div class="sw-card{" sel" if selected else ""}" style="--c:{color}">'
        f'<div class="sw-card-head"><span>경로 {row["route_id"]}</span>{badge}</div>'
        f'<div class="sw-label">{escape(route["label"])}</div>'
        f'<div class="sw-grid">{grid}</div>'
        f'<div class="sw-score">비교 점수 <b>{row["score"]:.0f}</b> / 100</div>'
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def footer() -> None:
    st.markdown(f'<div class="sw-foot">{texts.DISCLAIMER}</div>', unsafe_allow_html=True)
