"""Stage 2 chips data fetcher — bulk TWSE institutional + margin queries.

不同於 `services.institutional_service.get_institutional_data` 一次只查單檔，
這裡一次抓「整個交易日所有上市股票」，平均每檔成本極低，
適合 Stage 2 對 80~200 檔候選一次補上 chips 因子。

回傳資料結構刻意簡化（dict[ticker -> dict[date -> values]]），由 factor_scorer 計算：
  - foreign_consecutive_days：連續買 / 賣超日數（正負號）
  - foreign_net_5d：近 5 日外資累積淨買超（張）
  - margin_change_5d：融資餘額變化（張）
  - short_change_5d：融券餘額變化（張）
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import requests

from services.twse_parsers import parse_margn_row, parse_t86_row, shares_to_lots

logger = logging.getLogger(__name__)

_TWSE_T86 = "https://www.twse.com.tw/rwd/zh/fund/T86"
_TWSE_MARGIN = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"


def _recent_dates(n: int = 7) -> list[str]:
    out: list[str] = []
    d = datetime.now()
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out


def _fetch_t86_day(date_str: str) -> dict[str, int]:
    """Return {bare_code: foreign_net_in_thousand_shares} for the date.

    foreign_net 已經換算為「張」（1 張 = 1000 股）。
    若該日無交易或 API 失敗，回空 dict。
    """
    try:
        resp = requests.get(
            _TWSE_T86,
            params={"date": date_str, "selectType": "ALL", "response": "json"},
            timeout=(3, 8),
            headers={"User-Agent": "Navi/1.0"},
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.debug("T86 %s failed: %s", date_str, e)
        return {}
    if payload.get("stat") != "OK" or not payload.get("data"):
        return {}
    out: dict[str, int] = {}
    for row in payload["data"]:
        try:
            parsed = parse_t86_row(row)
            out[parsed.code] = shares_to_lots(parsed.foreign_net)
        except (IndexError, ValueError):
            continue
    return out


def _fetch_margin_day(date_str: str) -> dict[str, tuple[int, int]]:
    """Return {bare_code: (margin_balance, short_balance)} for the date."""
    try:
        resp = requests.get(
            _TWSE_MARGIN,
            params={"date": date_str, "selectType": "ALL", "response": "json"},
            timeout=(3, 8),
            headers={"User-Agent": "Navi/1.0"},
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.debug("margin %s failed: %s", date_str, e)
        return {}
    if payload.get("stat") != "OK":
        return {}
    data_list = None
    if "tables" in payload and len(payload["tables"]) > 1:
        data_list = payload["tables"][1].get("data")
    elif "creditList" in payload:
        data_list = payload["creditList"]
    if not data_list:
        return {}
    out: dict[str, tuple[int, int]] = {}
    for row in data_list:
        try:
            # 欄位對應集中在 twse_parsers；舊版曾把融券「前日」餘額(row 11)誤當今日餘額。
            parsed = parse_margn_row(row)
            out[parsed.code] = (parsed.margin_balance, parsed.short_balance)
        except (IndexError, ValueError):
            continue
    return out


def _bare(ticker: str) -> str:
    return ticker.replace(".TW", "").replace(".TWO", "")


def _consecutive_days(values: list[int]) -> int:
    """values[0] 為最新日；連續同號回傳次數（買為正、賣為負、零中斷）."""
    if not values:
        return 0
    sign = 1 if values[0] > 0 else -1 if values[0] < 0 else 0
    if sign == 0:
        return 0
    n = 0
    for v in values:
        if (sign > 0 and v > 0) or (sign < 0 and v < 0):
            n += 1
        else:
            break
    return n * sign


def fetch_chips_bulk(
    tickers: list[str],
    days: int = 5,
) -> dict[str, dict[str, float]]:
    """Bulk fetch chips factors for many tickers.

    Returns:
        {ticker: {
            "foreign_consecutive_days": int,
            "foreign_net_5d": int (張),
            "margin_change_5d": int (張),
            "short_change_5d": int (張),
        }}
    缺資料的 ticker 會回 {}（缺的因子 None 由呼叫端處理）。
    """
    bare_to_full = {_bare(t): t for t in tickers}
    bare_codes = set(bare_to_full.keys())

    dates = _recent_dates(days + 3)  # 多抓幾天容錯
    inst_by_date: dict[str, dict[str, int]] = {}
    margin_by_date: dict[str, dict[str, tuple[int, int]]] = {}

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_fetch_t86_day, d): ("inst", d) for d in dates}
        futs.update({ex.submit(_fetch_margin_day, d): ("margin", d) for d in dates})
        for fut in as_completed(futs):
            kind, d = futs[fut]
            try:
                if kind == "inst":
                    inst_by_date[d] = fut.result()
                else:
                    margin_by_date[d] = fut.result()
            except Exception as e:
                logger.debug("chips %s %s failed: %s", kind, d, e)

    # 排序日期：最新→舊
    inst_sorted = sorted(
        [(d, m) for d, m in inst_by_date.items() if m], reverse=True
    )[:days]
    margin_sorted = sorted(
        [(d, m) for d, m in margin_by_date.items() if m], reverse=True
    )

    out: dict[str, dict[str, float]] = {t: {} for t in tickers}
    for bare_code, full in bare_to_full.items():
        # foreign_net 序列（最新→舊），缺日跳過
        nets = []
        for _, day_map in inst_sorted:
            if bare_code in day_map:
                nets.append(day_map[bare_code])
        if nets:
            out[full]["foreign_consecutive_days"] = float(_consecutive_days(nets))
            out[full]["foreign_net_5d"] = float(sum(nets))

        # margin / short balance change（latest - earliest within window）
        win = []
        for _, day_map in margin_sorted[:days]:
            if bare_code in day_map:
                win.append(day_map[bare_code])
        if len(win) >= 2:
            out[full]["margin_change_5d"] = float(win[0][0] - win[-1][0])
            out[full]["short_change_5d"] = float(win[0][1] - win[-1][1])

    if bare_codes:
        hit_inst = sum(1 for v in out.values() if "foreign_net_5d" in v)
        hit_mgn = sum(1 for v in out.values() if "margin_change_5d" in v)
        logger.info(
            "Chips bulk: %d tickers, foreign hit=%d, margin hit=%d",
            len(tickers),
            hit_inst,
            hit_mgn,
        )
    return out
