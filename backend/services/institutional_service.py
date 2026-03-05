"""Institutional Service — 三大法人買賣超（TWSE / TPEx Open API）."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

# ── TWSE / TPEx Open API endpoints ──
# 上市：https://www.twse.com.tw/rwd/zh/fund/T86
# 上櫃：https://www.tpex.org.tw/www/zh-tw/fund/institution

_TWSE_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
_TPEX_URL = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"


@dataclass
class InstitutionalDaily:
    """單日法人買賣超資料."""

    date: str = ""
    foreign_buy: int = 0
    foreign_sell: int = 0
    foreign_net: int = 0
    investment_trust_buy: int = 0
    investment_trust_sell: int = 0
    investment_trust_net: int = 0
    dealer_buy: int = 0
    dealer_sell: int = 0
    dealer_net: int = 0
    total_net: int = 0


@dataclass
class InstitutionalSummary:
    """多日法人買賣超匯總."""

    ticker: str
    name: str = ""
    records: list[InstitutionalDaily] = field(default_factory=list)
    foreign_consecutive_days: int = 0
    foreign_total_net: int = 0
    investment_trust_total_net: int = 0
    dealer_total_net: int = 0
    total_net: int = 0
    error: str = ""


def _parse_int(s: str) -> int:
    """Parse comma-separated integer string, e.g. '1,234' → 1234."""
    try:
        return int(s.replace(",", "").replace(" ", ""))
    except (ValueError, AttributeError):
        return 0


def _recent_trading_dates(n: int = 5) -> list[str]:
    """Generate recent N weekday dates in yyyyMMdd format going backward from today."""
    dates: list[str] = []
    d = datetime.now()
    while len(dates) < n:
        if d.weekday() < 5:  # Mon-Fri
            dates.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return dates


def _fetch_twse_institutional(date_str: str, ticker: str) -> InstitutionalDaily | None:
    """Fetch single-day institutional data from TWSE for 上市 stocks.

    API: GET https://www.twse.com.tw/rwd/zh/fund/T86?date=20260303&selectType=ALL&response=json
    Returns JSON with `data` array of per-stock rows.
    """
    try:
        resp = requests.get(
            _TWSE_URL,
            params={
                "date": date_str,
                "selectType": "ALL",
                "response": "json",
            },
            timeout=(3, 5),
            headers={"User-Agent": "Navi/1.0"},
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.warning("TWSE API request failed for %s: %s", date_str, e)
        return None

    if payload.get("stat") != "OK" or not payload.get("data"):
        return None

    # Strip .TW suffix for matching (e.g. "2330.TW" → "2330")
    code = ticker.replace(".TW", "").replace(".TWO", "")

    for row in payload["data"]:
        row_code = str(row[0]).strip()
        if row_code == code:
            # Columns: 證券代號, 證券名稱, 外資買, 外資賣, 外資淨, 投信買, 投信賣, 投信淨,
            #          自營商買, 自營商賣, 自營商淨, 合計淨
            return InstitutionalDaily(
                date=f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}",
                foreign_buy=_parse_int(row[2]),
                foreign_sell=_parse_int(row[3]),
                foreign_net=_parse_int(row[4]),
                investment_trust_buy=_parse_int(row[5]),
                investment_trust_sell=_parse_int(row[6]),
                investment_trust_net=_parse_int(row[7]),
                dealer_buy=_parse_int(row[8]),
                dealer_sell=_parse_int(row[9]),
                dealer_net=_parse_int(row[10]),
                total_net=_parse_int(row[11]),
            )
    return None


def _calc_consecutive_days(records: list[InstitutionalDaily]) -> int:
    """Calculate foreign consecutive buy/sell days from most recent record."""
    if not records:
        return 0
    direction = 1 if records[0].foreign_net > 0 else -1 if records[0].foreign_net < 0 else 0
    if direction == 0:
        return 0
    count = 0
    for r in records:
        if (direction > 0 and r.foreign_net > 0) or (direction < 0 and r.foreign_net < 0):
            count += 1
        else:
            break
    return count * direction  # positive = consecutive buy, negative = consecutive sell


def get_institutional_data(ticker: str, days: int = 5) -> InstitutionalSummary:
    """Fetch institutional buy/sell data for recent N trading days.

    Currently supports TWSE (上市) stocks. TPEx (上櫃) can be added later.
    """
    from services.stock_service import normalize_ticker

    norm_ticker = normalize_ticker(ticker)
    summary = InstitutionalSummary(ticker=norm_ticker)

    # Only .TW stocks are supported via TWSE API
    if not norm_ticker.endswith(".TW"):
        summary.error = f"{ticker} 不是上市股票，目前僅支援上市（TWSE）個股的法人買賣超查詢。"
        return summary

    dates = _recent_trading_dates(days + 5)  # fetch extra dates in case of holidays

    # Parallel fetch TWSE API for all dates
    records: list[InstitutionalDaily] = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_date = {
            executor.submit(_fetch_twse_institutional, d, norm_ticker): d
            for d in dates
        }
        date_records: dict[str, InstitutionalDaily] = {}
        for future in as_completed(future_to_date):
            d = future_to_date[future]
            try:
                rec = future.result()
                if rec is not None:
                    date_records[d] = rec
            except Exception:
                pass

    # Sort by date descending and take only `days` records
    for d in dates:
        if len(records) >= days:
            break
        if d in date_records:
            records.append(date_records[d])

    if not records:
        summary.error = f"無法取得 {ticker} 的法人買賣超資料，可能為非交易日或資料尚未公布。"
        return summary

    summary.records = records
    summary.foreign_total_net = sum(r.foreign_net for r in records)
    summary.investment_trust_total_net = sum(r.investment_trust_net for r in records)
    summary.dealer_total_net = sum(r.dealer_net for r in records)
    summary.total_net = sum(r.total_net for r in records)
    summary.foreign_consecutive_days = _calc_consecutive_days(records)

    # Get company name from cached ticker info
    try:
        from services.stock_service import _get_ticker_info

        info = _get_ticker_info(norm_ticker)
        summary.name = info.get("shortName") or info.get("longName") or ""
    except Exception:
        pass

    return summary
