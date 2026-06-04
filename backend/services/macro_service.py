"""Macro Service — 大盤指數、三大法人總額、期貨未平倉。

提供 chat 工具回答「大盤怎麼看？」「外資今天買賣超？」「外資多空單怎麼看？」等問題。

資料來源：
- 加權指數 / 櫃買指數：TWSE MIS 即時報價（盤中每 ~5 秒）；fallback 為 TWSE Open API MI_INDEX 收盤
- 三大法人買賣超彙總：TWSE rwd/zh/fund/BFI82U（含自營/投信/外資，含日期參數可回溯）
- 期貨未平倉（TXF/MXF/小台/微台）：TAIFEX futContractsDateDown CSV（POST，charset MS950）
"""

from __future__ import annotations

import csv
import io
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

_TPE_TZ = ZoneInfo("Asia/Taipei")

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _safe_float(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "").replace("+", "")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _safe_int(val) -> int | None:
    f = _safe_float(val)
    return int(f) if f is not None else None


def _prev_weekday(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


# ── 1) 大盤指數即時報價 ─────────────────────────────────────────────────────


@dataclass
class MarketIndexData:
    """大盤指數快照（盤中即時或盤後收盤）。"""

    market: str  # "TWSE" or "TPEx"
    name: str  # "發行量加權股價指數" / "櫃買指數"
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    as_of_date: str = ""  # ISO yyyy-mm-dd
    as_of_time: str = ""  # HH:MM:SS（盤中才有）
    is_intraday: bool = False
    data_source: str = ""  # "MIS" / "MI_INDEX"
    error: str | None = None


_INDEX_EX_CH = {
    "TWSE": "tse_t00.tw",
    "TPEX": "otc_o00.tw",
}

_MIS_HEADERS = {
    "User-Agent": _UA,
    "Referer": "https://mis.twse.com.tw/stock/",
    "Accept": "application/json,text/plain,*/*",
}


def _fetch_mis_index(market: str) -> MarketIndexData | None:
    """從 TWSE MIS 取得指數即時報價。失敗回 None。"""
    ex_ch = _INDEX_EX_CH.get(market.upper())
    if ex_ch is None:
        return None
    try:
        resp = requests.get(
            "https://mis.twse.com.tw/stock/api/getStockInfo.jsp",
            params={
                "ex_ch": ex_ch,
                "json": "1",
                "delay": "0",
                "_": str(int(time.time() * 1000)),
            },
            headers=_MIS_HEADERS,
            timeout=8,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.warning("MIS index fetch failed for %s: %s", market, e)
        return None

    arr = payload.get("msgArray") or []
    if not arr:
        return None
    s = arr[0]

    price = _safe_float(s.get("z"))
    # 指數的 z 通常每 5 秒更新，極少為 "-"；若真為 "-" 退到 open
    if price is None:
        price = _safe_float(s.get("o"))

    prev_close = _safe_float(s.get("y"))
    change = None
    change_pct = None
    if price is not None and prev_close is not None and prev_close != 0:
        change = round(price - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2)

    d_raw = (s.get("d") or "").strip()
    date_iso = ""
    if len(d_raw) == 8 and d_raw.isdigit():
        date_iso = f"{d_raw[:4]}-{d_raw[4:6]}-{d_raw[6:8]}"

    return MarketIndexData(
        market="TWSE" if market.upper() == "TWSE" else "TPEx",
        name=(s.get("n") or "").strip(),
        price=price,
        change=change,
        change_percent=change_pct,
        open=_safe_float(s.get("o")),
        high=_safe_float(s.get("h")),
        low=_safe_float(s.get("l")),
        prev_close=prev_close,
        as_of_date=date_iso,
        as_of_time=(s.get("t") or s.get("%") or "").strip(),
        is_intraday=True,
        data_source="MIS",
    )


def _fetch_openapi_taiex() -> MarketIndexData | None:
    """從 TWSE Open API MI_INDEX 取得發行量加權股價指數收盤。fallback 用。"""
    try:
        resp = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX",
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        logger.warning("MI_INDEX fetch failed: %s", e)
        return None

    target = next(
        (r for r in rows if r.get("指數") == "發行量加權股價指數"),
        None,
    )
    if not target:
        return None

    price = _safe_float(target.get("收盤指數"))
    pts = _safe_float(target.get("漲跌點數"))
    sign = (target.get("漲跌") or "+").strip()
    change = pts if pts is None or sign == "+" else -pts
    pct = _safe_float(target.get("漲跌百分比"))
    if pct is not None and sign != "+":
        pct = -pct

    d_raw = (target.get("日期") or "").strip()
    date_iso = ""
    if len(d_raw) == 7 and d_raw.isdigit():
        # 民國年 → 西元
        try:
            year = int(d_raw[:3]) + 1911
            date_iso = f"{year:04d}-{d_raw[3:5]}-{d_raw[5:7]}"
        except ValueError:
            date_iso = ""

    return MarketIndexData(
        market="TWSE",
        name="發行量加權股價指數",
        price=price,
        change=change,
        change_percent=pct,
        as_of_date=date_iso,
        is_intraday=False,
        data_source="MI_INDEX",
    )


def get_market_index(market: str = "TWSE") -> MarketIndexData:
    """取得大盤指數即時報價（TWSE 加權 / TPEx 櫃買）。

    優先 MIS（盤中即時），失敗時 TWSE 才退到 MI_INDEX 收盤；TPEx 無 fallback。
    """
    data = _fetch_mis_index(market)
    if data is not None and data.price is not None:
        return data

    if market.upper() == "TWSE":
        fb = _fetch_openapi_taiex()
        if fb is not None and fb.price is not None:
            return fb

    return MarketIndexData(
        market=market.upper(),
        name="",
        error=f"無法取得 {market} 指數資料",
    )


# ── 2) 三大法人買賣超彙總（市場總額） ──────────────────────────────────────


@dataclass
class InstitutionalDailyAggregate:
    """單日三大法人買賣超彙總（金額單位：新台幣元）。"""

    date: str  # ISO yyyy-mm-dd
    dealer_self_net: int = 0  # 自營商（自行買賣）
    dealer_hedge_net: int = 0  # 自營商（避險）
    investment_trust_net: int = 0  # 投信
    foreign_net: int = 0  # 外資及陸資（不含外資自營商）
    foreign_dealer_net: int = 0  # 外資自營商
    total_net: int = 0  # 合計

    @property
    def dealer_net(self) -> int:
        """自營商合計（自行 + 避險）。"""
        return self.dealer_self_net + self.dealer_hedge_net

    @property
    def foreign_total_net(self) -> int:
        """外資合計（含外資自營商）。"""
        return self.foreign_net + self.foreign_dealer_net


@dataclass
class InstitutionalAggregateData:
    records: list[InstitutionalDailyAggregate] = field(default_factory=list)
    error: str | None = None


_BFI82U_LABEL_MAP = {
    "自營商(自行買賣)": "dealer_self_net",
    "自營商(避險)": "dealer_hedge_net",
    "投信": "investment_trust_net",
    "外資及陸資(不含外資自營商)": "foreign_net",
    "外資自營商": "foreign_dealer_net",
    "合計": "total_net",
}


def _fetch_bfi82u_one_day(d: date) -> InstitutionalDailyAggregate | None:
    """擷取單一日期的 BFI82U；查無資料（非交易日）回 None。"""
    day_str = d.strftime("%Y%m%d")
    try:
        resp = requests.get(
            "https://www.twse.com.tw/rwd/zh/fund/BFI82U",
            params={"dayDate": day_str, "type": "day", "response": "json"},
            headers={"User-Agent": _UA},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.warning("BFI82U fetch failed for %s: %s", day_str, e)
        return None

    if payload.get("stat") != "OK":
        return None
    rows = payload.get("data") or []
    if not rows:
        return None

    api_date = (payload.get("date") or day_str).strip()
    iso_date = (
        f"{api_date[:4]}-{api_date[4:6]}-{api_date[6:8]}"
        if len(api_date) == 8 and api_date.isdigit()
        else d.isoformat()
    )

    rec = InstitutionalDailyAggregate(date=iso_date)
    found_any = False
    for row in rows:
        if not row or len(row) < 4:
            continue
        label = (row[0] or "").strip()
        # row 結構：[單位名稱, 買進金額, 賣出金額, 買賣差額]
        net = _safe_int(row[3])
        if net is None:
            continue
        attr = _BFI82U_LABEL_MAP.get(label)
        if attr is None:
            continue
        setattr(rec, attr, net)
        found_any = True

    return rec if found_any else None


def get_institutional_aggregate(days: int = 1) -> InstitutionalAggregateData:
    """取得最近 N 個交易日的三大法人買賣超彙總（市場總額）。

    從今天起往回試最多 days*3 + 5 天，跳過假日 / 颱風 / 查無資料的日期。
    """
    days = max(1, min(int(days), 20))
    today = datetime.now(_TPE_TZ).date()

    records: list[InstitutionalDailyAggregate] = []
    cursor = today
    max_attempts = days * 3 + 5
    attempts = 0
    while len(records) < days and attempts < max_attempts:
        if cursor.weekday() >= 5:
            cursor = _prev_weekday(cursor)
            continue
        rec = _fetch_bfi82u_one_day(cursor)
        attempts += 1
        if rec is not None:
            records.append(rec)
        cursor = _prev_weekday(cursor)

    if not records:
        return InstitutionalAggregateData(error="無法取得三大法人買賣超資料")

    return InstitutionalAggregateData(records=records)


# ── 3) 期貨三大法人未平倉 ───────────────────────────────────────────────────


@dataclass
class FuturesPartyPosition:
    """單一身份別在某商品的期貨多空部位。

    口數單位：口；契約金額單位：千元（TAIFEX 原始單位）。
    """

    party: str  # 自營商 / 投信 / 外資
    long_trade_lots: int = 0
    short_trade_lots: int = 0
    net_trade_lots: int = 0
    long_oi_lots: int = 0
    short_oi_lots: int = 0
    net_oi_lots: int = 0
    net_oi_value_kntd: int = 0  # 多空未平倉契約金額淨額（千元）


@dataclass
class FuturesPositionsData:
    commodity: str  # "TXF" 等
    commodity_name: str = ""  # "臺股期貨"
    date: str = ""  # ISO yyyy-mm-dd
    parties: list[FuturesPartyPosition] = field(default_factory=list)
    error: str | None = None


_TAIFEX_COMMODITY_NAMES = {
    "TXF": "臺股期貨",
    "MXF": "小型臺指期貨",
    "TMF": "微型臺指期貨",
    "EXF": "電子期貨",
    "FXF": "金融期貨",
}


def _fetch_taifex_one_day(commodity: str, d: date) -> FuturesPositionsData | None:
    """擷取單一日期 TAIFEX 三大法人期貨報表。查無資料回 None。"""
    day_str = d.strftime("%Y/%m/%d")
    try:
        resp = requests.post(
            "https://www.taifex.com.tw/cht/3/futContractsDateDown",
            data={
                "queryStartDate": day_str,
                "queryEndDate": day_str,
                "commodityId": commodity,
            },
            headers={
                "User-Agent": _UA,
                "Referer": "https://www.taifex.com.tw/cht/3/futContractsDate",
            },
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning("TAIFEX fetch failed for %s %s: %s", commodity, day_str, e)
        return None

    # TAIFEX 回傳 charset MS950 (≈ cp950)；另外查無資料時回傳 HTML alert
    raw = resp.content
    text = ""
    for enc in ("ms950", "cp950", "big5", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if not text or text.lstrip().startswith("<"):
        # HTML response = 查無資料
        return None

    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if r and any(c.strip() for c in r)]
    if len(rows) < 2:
        return None

    # 跳過 header；資料列至少 15 欄
    parties: list[FuturesPartyPosition] = []
    api_date = ""
    commodity_name = ""
    for row in rows[1:]:
        if len(row) < 15:
            continue
        api_date = (row[0] or api_date).strip()
        commodity_name = (row[1] or commodity_name).strip()
        party = (row[2] or "").strip()
        if not party:
            continue
        parties.append(
            FuturesPartyPosition(
                party=party,
                long_trade_lots=_safe_int(row[3]) or 0,
                short_trade_lots=_safe_int(row[5]) or 0,
                net_trade_lots=_safe_int(row[7]) or 0,
                long_oi_lots=_safe_int(row[9]) or 0,
                short_oi_lots=_safe_int(row[11]) or 0,
                net_oi_lots=_safe_int(row[13]) or 0,
                net_oi_value_kntd=_safe_int(row[14]) or 0,
            )
        )

    if not parties:
        return None

    iso_date = api_date.replace("/", "-") if api_date else d.isoformat()
    return FuturesPositionsData(
        commodity=commodity,
        commodity_name=commodity_name or _TAIFEX_COMMODITY_NAMES.get(commodity, ""),
        date=iso_date,
        parties=parties,
    )


def get_futures_positions(commodity: str = "TXF") -> FuturesPositionsData:
    """取得最近一個交易日的 TAIFEX 三大法人期貨部位（預設臺指期 TXF）。

    從今天往回最多嘗試 7 天；TAIFEX 報表通常於收盤後 14:30 左右公布。
    """
    commodity = (commodity or "TXF").upper()
    today = datetime.now(_TPE_TZ).date()
    cursor = today
    for _ in range(7):
        if cursor.weekday() < 5:
            data = _fetch_taifex_one_day(commodity, cursor)
            if data is not None:
                return data
        cursor = _prev_weekday(cursor)

    return FuturesPositionsData(
        commodity=commodity,
        commodity_name=_TAIFEX_COMMODITY_NAMES.get(commodity, ""),
        error=f"無法取得 {commodity} 期貨三大法人資料",
    )
