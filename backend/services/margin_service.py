"""Margin Service — 融資融券數據（TWSE Open API）."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

# TWSE 融資融券 API
# https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN
_TWSE_MARGIN_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"


@dataclass
class MarginDaily:
    """單日融資融券資料."""

    date: str = ""
    # 融資
    margin_buy: int = 0           # 融資買進
    margin_sell: int = 0          # 融資賣出
    margin_cash_repay: int = 0    # 融資現金償還
    margin_balance: int = 0       # 融資餘額（張）
    margin_limit: int = 0         # 融資限額
    margin_utilization: float = 0.0  # 融資使用率 (%)
    # 融券
    short_sell: int = 0           # 融券賣出
    short_buy: int = 0            # 融券買進
    short_cash_repay: int = 0     # 融券現券償還
    short_balance: int = 0        # 融券餘額（張）
    # 資券互抵
    offset: int = 0               # 資券互抵（當沖）


@dataclass
class MarginSummary:
    """融資融券匯總."""

    ticker: str
    name: str = ""
    records: list[MarginDaily] = field(default_factory=list)
    latest: MarginDaily | None = None
    margin_change: int = 0       # 融資餘額近期變化
    short_change: int = 0        # 融券餘額近期變化
    error: str = ""


def _parse_int(s: str) -> int:
    try:
        return int(s.replace(",", "").replace(" ", "").replace("--", "0"))
    except (ValueError, AttributeError):
        return 0


def _parse_float(s: str) -> float:
    try:
        return float(s.replace(",", "").replace(" ", "").replace("%", "").replace("--", "0"))
    except (ValueError, AttributeError):
        return 0.0


def _recent_trading_dates(n: int = 5) -> list[str]:
    dates: list[str] = []
    d = datetime.now()
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return dates


def _fetch_twse_margin(date_str: str, ticker: str) -> MarginDaily | None:
    """Fetch margin trading data from TWSE for a single date.

    API: GET https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=20260303&selectType=ALL&response=json
    """
    try:
        resp = requests.get(
            _TWSE_MARGIN_URL,
            params={
                "date": date_str,
                "selectType": "ALL",
                "response": "json",
            },
            timeout=10,
            headers={"User-Agent": "Navi/1.0"},
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.warning("TWSE margin API failed for %s: %s", date_str, e)
        return None

    if payload.get("stat") != "OK":
        return None

    # 個股融資融券在 tables[1] (creditList)
    # 有些回傳格式把它放 "data" 或 "creditList"
    data_list = None
    if "tables" in payload and len(payload["tables"]) > 1:
        data_list = payload["tables"][1].get("data")
    elif "creditList" in payload:
        data_list = payload["creditList"]

    if not data_list:
        return None

    code = ticker.replace(".TW", "").replace(".TWO", "")

    for row in data_list:
        row_code = str(row[0]).strip()
        if row_code == code:
            # Row format (typical):
            # [0] 代號, [1] 名稱,
            # [2] 融資買進, [3] 融資賣出, [4] 融資現償, [5] 融資前日餘額, [6] 融資今日餘額, [7] 融資限額,
            # [8] 融券賣出, [9] 融券買進, [10] 融券現券償還, [11] 融券前日餘額, [12] 融券今日餘額,
            # [13] 資券互抵
            margin_balance = _parse_int(row[6]) if len(row) > 6 else 0
            margin_limit = _parse_int(row[7]) if len(row) > 7 else 0
            utilization = round((margin_balance / margin_limit * 100), 2) if margin_limit > 0 else 0.0

            return MarginDaily(
                date=f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}",
                margin_buy=_parse_int(row[2]),
                margin_sell=_parse_int(row[3]),
                margin_cash_repay=_parse_int(row[4]) if len(row) > 4 else 0,
                margin_balance=margin_balance,
                margin_limit=margin_limit,
                margin_utilization=utilization,
                short_sell=_parse_int(row[8]) if len(row) > 8 else 0,
                short_buy=_parse_int(row[9]) if len(row) > 9 else 0,
                short_cash_repay=_parse_int(row[10]) if len(row) > 10 else 0,
                short_balance=_parse_int(row[12]) if len(row) > 12 else 0,
                offset=_parse_int(row[13]) if len(row) > 13 else 0,
            )
    return None


def get_margin_data(ticker: str, days: int = 5) -> MarginSummary:
    """Fetch margin trading data for recent N trading days."""
    from services.stock_service import normalize_ticker

    norm_ticker = normalize_ticker(ticker)
    summary = MarginSummary(ticker=norm_ticker)

    if not norm_ticker.endswith(".TW"):
        summary.error = f"{ticker} 不是上市股票，目前僅支援上市（TWSE）個股的融資融券查詢。"
        return summary

    dates = _recent_trading_dates(days + 5)

    records: list[MarginDaily] = []
    for d in dates:
        if len(records) >= days:
            break
        rec = _fetch_twse_margin(d, norm_ticker)
        if rec is not None:
            records.append(rec)

    if not records:
        summary.error = f"無法取得 {ticker} 的融資融券資料，可能為非交易日或資料尚未公布。"
        return summary

    summary.records = records
    summary.latest = records[0]

    if len(records) >= 2:
        summary.margin_change = records[0].margin_balance - records[-1].margin_balance
        summary.short_change = records[0].short_balance - records[-1].short_balance

    # Company name
    try:
        from services.stock_service import get_stock_overview

        overview = get_stock_overview(ticker)
        summary.name = overview.name
    except Exception:
        pass

    return summary
