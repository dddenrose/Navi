"""Stage 2 chips data fetcher — bulk TWSE institutional queries.

不同於 `services.institutional_service.get_institutional_data` 一次只查單檔，
這裡一次抓「整個交易日所有上市股票」，平均每檔成本極低，
適合 Stage 2 對 80~200 檔候選一次補上 chips 因子。

單次抓取、多視窗聚合（舊版 5d/20d 各抓一次全市場 = 2 倍 TWSE 請求量）：
  - foreign_consecutive_days：連續買 / 賣超日數（正負號）
  - foreign_net_{w}d：近 w 日外資累積淨買超（張），w 由 windows 參數決定

融資/融券欄位已移除 — 規則層從未消費，白抓的請求徒增 TWSE 限流風險。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import requests

from services.twse_parsers import parse_t86_row, shares_to_lots

logger = logging.getLogger(__name__)

_TWSE_T86 = "https://www.twse.com.tw/rwd/zh/fund/T86"


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
    windows: tuple[int, ...] = (5, 20),
) -> dict[str, dict[str, float]]:
    """Bulk fetch chips factors for many tickers（單次抓取、多視窗聚合）.

    Returns:
        {ticker: {
            "foreign_consecutive_days": int,
            "foreign_net_5d": float (張),    # windows 內每個 w 各一鍵
            "foreign_net_20d": float (張),
        }}
    缺資料的 ticker 會回 {}（缺的因子 None 由呼叫端處理）。
    """
    bare_to_full = {_bare(t): t for t in tickers}

    max_w = max(windows)
    dates = _recent_dates(max_w + 3)  # 多抓幾天容錯（假日/缺檔）
    inst_by_date: dict[str, dict[str, int]] = {}

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_fetch_t86_day, d): d for d in dates}
        for fut in as_completed(futs):
            d = futs[fut]
            try:
                inst_by_date[d] = fut.result()
            except Exception as e:
                logger.debug("chips inst %s failed: %s", d, e)

    # 排序日期：最新→舊
    inst_sorted = sorted(
        [(d, m) for d, m in inst_by_date.items() if m], reverse=True
    )[:max_w]

    out: dict[str, dict[str, float]] = {t: {} for t in tickers}
    for bare_code, full in bare_to_full.items():
        # foreign_net 序列（最新→舊），缺日跳過
        nets = [
            day_map[bare_code]
            for _, day_map in inst_sorted
            if bare_code in day_map
        ]
        if nets:
            out[full]["foreign_consecutive_days"] = float(_consecutive_days(nets))
            for w in windows:
                out[full][f"foreign_net_{w}d"] = float(sum(nets[:w]))

    if tickers:
        hit_inst = sum(1 for v in out.values() if v)
        logger.info(
            "Chips bulk: %d tickers, foreign hit=%d (windows=%s)",
            len(tickers), hit_inst, windows,
        )
    return out
