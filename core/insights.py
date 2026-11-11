"""'데이터로 본 부산': 구·군별 안전시설 통계와 자동 해설 (담당: 데이터).

공공데이터를 구별로 모아 보면, 지역마다 시설 차이와 데이터가 빠진 곳이 보인다.
해설 문장은 Python이 계산한 값으로만 만든다.
"""
from __future__ import annotations

import pandas as pd

from . import config

KIND_LABEL = {"cctv": "CCTV", "bell": "안전비상벨", "light": "보안등"}


def gu_summary(df: pd.DataFrame) -> pd.DataFrame:
    """구·군별 시설 수와 1㎢당 시설 수. 열: 구, 면적, cctv, bell, light, cctv_km2, bell_km2, light_km2."""
    if "gu" not in df.columns or not df["gu"].isin(config.GU_AREA_KM2).any():
        return pd.DataFrame()   # 구 정보가 없는 데이터 → '데이터로 본 부산'을 보여 주지 않는다
    counts = (df[df["gu"].isin(config.GU_AREA_KM2)]
              .groupby(["gu", "kind"]).size().unstack(fill_value=0)
              .reindex(index=list(config.GU_AREA_KM2), columns=list(KIND_LABEL), fill_value=0))
    out = counts.reset_index().rename(columns={"gu": "구"})
    out["면적"] = out["구"].map(config.GU_AREA_KM2)
    for kind in KIND_LABEL:
        out[f"{kind}_km2"] = (out[kind] / out["면적"]).round(1)
    return out


def insight_lines(summary: pd.DataFrame) -> list[str]:
    """표에서 바로 읽을 수 있는 사실 몇 줄."""
    lines = []
    cb = summary.assign(cb_km2=(summary["cctv"] + summary["bell"]) / summary["면적"])
    hi, lo = cb.loc[cb["cb_km2"].idxmax()], cb.loc[cb["cb_km2"].idxmin()]
    ratio = f" (약 {hi['cb_km2'] / lo['cb_km2']:.0f}배 차이)" if lo["cb_km2"] > 0 else ""
    lines.append(f"1㎢당 CCTV·비상벨은 **{hi['구']}**가 {hi['cb_km2']:.1f}곳으로 가장 많고, "
                 f"**{lo['구']}**가 {lo['cb_km2']:.1f}곳으로 가장 적어요{ratio}.")
    zero_bell = summary.loc[summary["bell"] == 0, "구"].tolist()
    if zero_bell:
        lines.append(f"**{'·'.join(zero_bell)}**는 공개된 안전비상벨 데이터가 0곳이에요. "
                     "실제로 비상벨이 없는 게 아니라 데이터가 공개되지 않은 것일 수 있어요.")
    li_hi = summary.loc[summary["light_km2"].idxmax()]
    li_lo = summary.loc[summary["light_km2"].idxmin()]
    lines.append(f"1㎢당 보안등은 **{li_hi['구']}** {li_hi['light_km2']:.0f}곳, **{li_lo['구']}** {li_lo['light_km2']:.0f}곳이에요.")
    big = summary.sort_values("면적", ascending=False).head(2)["구"].tolist()
    lines.append(f"{'·'.join(big)}처럼 산·농지가 넓은 곳은 면적으로 나누면 숫자가 작게 나와요. "
                 "사람이 다니는 길만 따지면 차이가 줄어들 수 있어요.")
    return lines
