"""TWSE OpenAPI 月營收 fetcher — 上市公司每月營業收入彙總表（t187ap05_L）.

台股每月 10 日前公布上月營收，是基本面最即時的公開訊號；
yfinance 只有季營收（且常缺前 5 季無法算 YoY），此模組補上這個缺口。

一次呼叫回傳全市場（~1000 檔），成本極低；資料約落後 1-2 個月內，
label 欄位保留資料年月供前端與 AI 揭露時效。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

MONTHLY_REVENUE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"


@dataclass
class MonthlyRevenue:
    code: str  # 純代號，如 "2330"
    yoy: float | None  # 去年同月增減，小數（0.30 = +30%）
    label: str  # 資料年月，如 "115年5月"


def _parse_yoy(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw) / 100
    except (TypeError, ValueError):
        return None


def _format_label(roc_ym: str) -> str:
    """'11505' → '115年5月'；格式異常時原樣回傳。"""
    if len(roc_ym) >= 5 and roc_ym.isdigit():
        return f"{roc_ym[:-2]}年{int(roc_ym[-2:])}月"
    return roc_ym


def fetch_monthly_revenue_bulk(
    timeout: tuple[float, float] = (3, 15),
) -> dict[str, MonthlyRevenue]:
    """抓全市場最新一期月營收 YoY。失敗回空 dict（呼叫端視為資料缺失）。

    Returns:
        {bare_code: MonthlyRevenue}
    """
    try:
        resp = requests.get(
            MONTHLY_REVENUE_URL,
            timeout=timeout,
            headers={"accept": "application/json", "User-Agent": "Navi/1.0"},
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        logger.warning("Monthly revenue fetch failed: %s", e)
        return {}

    out: dict[str, MonthlyRevenue] = {}
    for row in rows:
        code = (row.get("公司代號") or "").strip()
        if not code:
            continue
        out[code] = MonthlyRevenue(
            code=code,
            yoy=_parse_yoy(row.get("營業收入-去年同月增減(%)")),
            label=_format_label((row.get("資料年月") or "").strip()),
        )
    logger.info("Monthly revenue: fetched %d companies", len(out))
    return out
