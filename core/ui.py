"""화면 꾸미기: CSS와 카드 HTML (담당: 지도 UI).

지도 앱(네이버·카카오·TMAP)처럼: 위에 검색 패널, 가운데 큰 지도, 아래에 옆으로 넘기는 경로 카드.
"""
from __future__ import annotations

from html import escape

import streamlit as st

from . import config, texts
from .explain import fmt_distance, fmt_duration

CSS = """
<style>
/* ---------- 바탕: Streamlit 기본 머리말 숨기고 여백 줄이기 */
header[data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer {display:none !important;}
.block-container {padding-top: .9rem; padding-bottom: 2.5rem; max-width: 1040px;}
@media (max-width: 640px) {
  .block-container {padding-left: .7rem; padding-right: .7rem; padding-top: .5rem;}
}

/* ---------- 머리말 */
.sw-header {display:flex; align-items:center; gap:.55rem;}
.sw-logo {width:34px; height:34px; border-radius:10px; background:#111827; color:#fff;
  display:flex; align-items:center; justify-content:center; font-size:18px; flex-shrink:0;}
.sw-title {font-size:1.25rem; font-weight:800; line-height:1.1; margin:0; color:#111827;}
.sw-title span {font-size:.8rem; font-weight:500; color:#9CA3AF; margin-left:.3rem;}
.sw-sub {color:#6B7280; margin:0; font-size:.8rem;}
.sw-status {display:inline-flex; align-items:center; gap:.35rem; font-size:.74rem; font-weight:600;
  padding:.18rem .55rem; border-radius:999px; background:#ECFDF5; color:#065F46; white-space:nowrap;}
.sw-status.demo {background:#FFFBEB; color:#92400E;}
.sw-status i {width:7px; height:7px; border-radius:50%; background:currentColor; display:inline-block;}
.sw-banner {font-size:.84rem; line-height:1.6; color:#374151;}

/* ---------- 검색 패널: 휴대폰에서도 한 줄로 (Streamlit 기본은 좁으면 칸을 세로로 쌓음) */
.st-key-searchbox, .st-key-modebar {--gap: .35rem;}
.st-key-searchbox [data-testid="stHorizontalBlock"],
.st-key-modebar [data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important; gap: var(--gap);}
.st-key-searchbox [data-testid="stColumn"],
.st-key-modebar [data-testid="stColumn"] {min-width: 0 !important; width: auto !important;}
.st-key-searchbox [data-testid="stVerticalBlock"] {gap: .35rem;}
.sw-pt {display:flex; align-items:center; gap:.35rem; font-size:.82rem; font-weight:700; color:#374151;
  white-space:nowrap; padding-top:.1rem;}
.sw-pt i {width:10px; height:10px; border-radius:50%; display:inline-block; flex-shrink:0;}
.sw-pt.s i {background:#111827;} .sw-pt.e i {background:#DC2626;}
.st-key-searchbox button {padding: .25rem .55rem; min-height: 2.4rem;}
[class*="st-key-cands_"] button {width:100%; justify-content:flex-start; text-align:left;
  border:none; background:#F9FAFB; min-height:2.2rem;}
[class*="st-key-cands_"] button p {font-size:.85rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
.sw-hint {font-size:.8rem; color:#6B7280; margin:.15rem 0 .1rem;}

/* ---------- 머리말 줄: 제목 + 🚨 긴급 (휴대폰에서도 한 줄) */
.st-key-headbar [data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important; gap: .4rem;}
.st-key-headbar [data-testid="stColumn"] {min-width: 0 !important; width: auto !important;}
.st-key-headbar [data-testid="stPopover"] button {border-color:#FCA5A5; color:#B91C1C; font-weight:700;}
@media (max-width: 640px) { .sw-sub {display:none;} }

/* ---------- 지도 아래 범례 */
.sw-legend {font-size:.76rem; color:#6B7280; margin:.15rem 0 .4rem; line-height:1.5;}

/* ---------- 경로 카드: 옆으로 넘기기 */
.sw-strip {display:flex; gap:.6rem; overflow-x:auto; scroll-snap-type:x mandatory;
  padding:.15rem .1rem .5rem; -webkit-overflow-scrolling:touch;}
.sw-strip::-webkit-scrollbar {height:6px;} .sw-strip::-webkit-scrollbar-thumb {background:#E5E7EB; border-radius:3px;}
.sw-rc {flex:0 0 min(300px, 82%); scroll-snap-align:start; border:1px solid #E5E7EB; border-radius:16px;
  padding:.75rem .85rem .7rem; background:#fff; border-left:5px solid var(--c);}
.sw-rc.sel {box-shadow:0 0 0 2px var(--c); border-color:transparent;}
.sw-rc-top {display:flex; align-items:center; justify-content:space-between; gap:.4rem;}
.sw-rc-id {font-weight:800; color:#111827; font-size:.95rem;}
.sw-rc-label {font-size:.72rem; color:#9CA3AF; font-weight:500; margin-left:.3rem;}
.sw-badge {background:#111827; color:#fff; font-size:.68rem; padding:.12rem .5rem; border-radius:999px; font-weight:700;}
.sw-rc-main {display:flex; align-items:baseline; gap:.45rem; margin:.3rem 0 .4rem;}
.sw-rc-time {font-size:1.45rem; font-weight:800; color:#111827; letter-spacing:-.02em;}
.sw-rc-dist {font-size:.9rem; color:#6B7280; font-weight:600;}
.sw-rc-icons {display:flex; gap:.7rem; font-size:.86rem; color:#111827; font-weight:600; flex-wrap:wrap;}
.sw-rc-sub {font-size:.74rem; color:#6B7280; margin-top:.35rem; line-height:1.5;}
.sw-warn {margin-top:.45rem; font-size:.74rem; color:#B45309; background:#FFFBEB; border-radius:8px; padding:.3rem .5rem;}
.sw-extra {margin-top:.35rem; font-size:.74rem; color:#1D4ED8;}
.sw-score {margin-top:.4rem; font-size:.72rem; color:#9CA3AF;}

.sw-foot {font-size:.74rem; color:#9CA3AF; line-height:1.6; margin-top:1rem;}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def header_html(is_demo: bool) -> str:
    status = (f'<span class="sw-status demo"><i></i>{texts.DEMO_BANNER_TITLE}</span>' if is_demo
              else '<span class="sw-status"><i></i>실제 데이터</span>')
    return (
        '<div class="sw-header"><div class="sw-logo">🛡️</div><div>'
        f'<p class="sw-title">{texts.APP_NAME}<span>{texts.APP_NAME_EN}</span></p>'
        f'<p class="sw-sub">{texts.TAGLINE}</p></div>'
        f'<div style="margin-left:auto">{status}</div></div>'
    )


def banner_text(route_source: str, facility_source: str, counts: dict | None = None) -> tuple[bool, str]:
    """(데모 여부, 데이터 출처 설명 마크다운)."""
    route_note = texts.DEMO_ROUTE_NOTE if route_source == "demo" else texts.REAL_ROUTE_NOTE
    if facility_source == "demo":
        fac_note = texts.DEMO_FACILITY_NOTE
    else:
        c = counts or {}
        fac_note = texts.REAL_FACILITY_NOTE.format(
            cctv=c.get("cctv", 0), bell=c.get("bell", 0), light=c.get("light", 0))
    is_demo = route_source == "demo" or facility_source == "demo"
    return is_demo, f"- {route_note}\n- {fac_note}"


def point_label(which: str) -> str:
    text = "출발" if which == "start" else "도착"
    return f'<div class="sw-pt {"s" if which == "start" else "e"}"><i></i>{text}</div>'


def legend(radius_m: float | None, has_police: bool = False, has_gaps: bool = False,
           has_lights: bool = False, has_dark: bool = False, has_stores: bool = False) -> None:
    parts = ["📷 CCTV", "🔔 비상벨"]
    if has_lights:
        parts.append('<span style="color:#CA8A04">●</span> 보안등')
    if has_stores:
        parts.append("🏪 편의점(참고)")
    if has_police:
        parts.append("🚓 지구대·파출소(참고)")
    text = " · ".join(parts)
    if radius_m:
        text += f" · 진한 표시 = 선택한 경로 {radius_m:.0f}m 안"
    if has_gaps:
        text += ' · <span style="color:#DC2626">빨간 점선</span> = CCTV·비상벨 없는 구간'
    if has_dark:
        text += (f' · <span style="color:#4B5563">회색 띠</span> = {config.LIGHT_REACH_M}m 안에 '
                 '보안등이 없는 구간 (큰길 가로등은 데이터에 없어요)')
    st.markdown(f'<div class="sw-legend">{text}</div>', unsafe_allow_html=True)


def route_card_html(row: dict, route: dict, color: str, recommended: bool, selected: bool,
                    facilities_are_demo: bool, nearest_police: dict | None = None) -> str:
    """경로 카드 하나 (지도 앱의 경로 요약 카드처럼 시간·거리를 크게)."""
    prefix = "가상 " if facilities_are_demo else ""
    badge = '<span class="sw-badge">추천</span>' if recommended else ""
    icons = [f"📷 {row['cctv']}", f"🔔 {row['bell']}"]
    if row.get("light") or row.get("light_per_km"):
        icons.append(f"💡 {row['light']}")
    if row.get("stores") is not None:
        icons.append(f"🏪 {row['stores']}")
    sub = [f"{prefix}CCTV·비상벨 1km당 {row['per_km']:.1f}곳",
           f"CCTV·비상벨 없는 최장 구간 {fmt_distance(row['longest_gap_m'])}"]
    if row.get("light_per_km"):
        sub.insert(1, f"보안등 1km당 {row['light_per_km']:.1f}곳")
    if row.get("longest_dark_m") is not None:
        sub.append(f"보안등 없는 최장 구간 {fmt_distance(row['longest_dark_m'])}")
    warn = (f'<div class="sw-warn">⚠️ 경로의 {row["outside_ratio"] * 100:.0f}%가 시설 데이터가 없는 지역이라 '
            f'시설 수가 실제보다 적게 나올 수 있어요</div>'
            if row.get("outside_ratio", 0) >= config.COVERAGE_WARN_RATIO else "")
    police = (f'<div class="sw-extra">🚓 가까운 지구대·파출소: {escape(nearest_police["name"])} '
              f'· 경로에서 {fmt_distance(nearest_police["dist_m"])}</div>' if nearest_police else "")
    return (
        f'<div class="sw-rc{" sel" if selected else ""}" style="--c:{color}">'
        f'<div class="sw-rc-top"><span><span class="sw-rc-id">경로 {row["route_id"]}</span>'
        f'<span class="sw-rc-label">{escape(route["label"])}</span></span>{badge}</div>'
        f'<div class="sw-rc-main"><span class="sw-rc-time">{fmt_duration(row["duration_s"])}</span>'
        f'<span class="sw-rc-dist">{fmt_distance(row["distance_m"])}</span></div>'
        f'<div class="sw-rc-icons">{"".join(f"<span>{i}</span>" for i in icons)}</div>'
        f'<div class="sw-rc-sub">{"<br>".join(sub)}</div>'
        f'{warn}{police}'
        f'<div class="sw-score">비교 점수 {row["score"]:.0f} / 100</div>'
        "</div>"
    )


def route_strip(cards_html: list[str]) -> None:
    st.markdown(f'<div class="sw-strip">{"".join(cards_html)}</div>', unsafe_allow_html=True)


def footer() -> None:
    st.markdown(f'<div class="sw-foot">{texts.DISCLAIMER}</div>', unsafe_allow_html=True)
