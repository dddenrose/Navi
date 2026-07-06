"""TWSE 開放資料列格式解析 — T86（三大法人）與 MI_MARGN（融資融券）.

TWSE 的 JSON API 以「純陣列 row」回傳，欄位順序一改就會整批錯位。
institutional_service / margin_service / screener.chips_data 過去各自硬編索引，
曾發生投信與外資自營商錯位、融券買賣對調等問題。此模組是唯一的欄位對應來源，
所有消費端都必須經由這裡解析，並以 tests/fixtures 的真實 API 回應鎖定格式。

T86 欄位（2026-07 實際回應，19 欄；selectType=ALL）：
    0 證券代號, 1 證券名稱,
    2 外陸資買進股數(不含外資自營商), 3 外陸資賣出股數(不含外資自營商),
    4 外陸資買賣超股數(不含外資自營商),
    5 外資自營商買進股數, 6 外資自營商賣出股數, 7 外資自營商買賣超股數,
    8 投信買進股數, 9 投信賣出股數, 10 投信買賣超股數,
    11 自營商買賣超股數(合計),
    12 自營商買進股數(自行買賣), 13 自營商賣出股數(自行買賣),
    14 自營商買賣超股數(自行買賣),
    15 自營商買進股數(避險), 16 自營商賣出股數(避險), 17 自營商買賣超股數(避險),
    18 三大法人買賣超股數

MI_MARGN tables[1] 欄位（2026-07 實際回應，16 欄；selectType=ALL）：
    0 代號, 1 名稱,
    2 融資買進, 3 融資賣出, 4 融資現金償還, 5 融資前日餘額, 6 融資今日餘額,
    7 融資次一營業日限額,
    8 融券買進, 9 融券賣出, 10 融券現券償還, 11 融券前日餘額, 12 融券今日餘額,
    13 融券次一營業日限額,
    14 資券互抵, 15 註記
"""

from __future__ import annotations

from dataclasses import dataclass

T86_EXPECTED_COLS = 19
MARGN_EXPECTED_COLS = 16


def parse_int(s: object) -> int:
    """Parse TWSE comma-separated integer, e.g. '1,234' → 1234；'--' 與空值視為 0."""
    try:
        return int(str(s).replace(",", "").replace(" ", "").replace("--", "0"))
    except (ValueError, AttributeError):
        return 0


def shares_to_lots(shares: int) -> int:
    """股 → 張（1 張 = 1000 股），朝零截斷以避免負值被 floor 放大（-500 股 → 0 張）."""
    return int(shares / 1000)


@dataclass
class T86Row:
    """T86 單檔法人買賣超（單位：股）。外資 = 外陸資 + 外資自營商，與三大法人合計一致."""

    code: str
    name: str
    foreign_buy: int
    foreign_sell: int
    foreign_net: int
    trust_buy: int
    trust_sell: int
    trust_net: int
    dealer_buy: int
    dealer_sell: int
    dealer_net: int
    total_net: int


def parse_t86_row(row: list) -> T86Row:
    """解析 T86 一列。欄數不符（schema 改版）時 raise ValueError，寧可失敗也不錯位."""
    if len(row) < T86_EXPECTED_COLS:
        raise ValueError(
            f"T86 row has {len(row)} columns, expected >= {T86_EXPECTED_COLS}; "
            "TWSE schema may have changed"
        )
    return T86Row(
        code=str(row[0]).strip(),
        name=str(row[1]).strip(),
        foreign_buy=parse_int(row[2]) + parse_int(row[5]),
        foreign_sell=parse_int(row[3]) + parse_int(row[6]),
        foreign_net=parse_int(row[4]) + parse_int(row[7]),
        trust_buy=parse_int(row[8]),
        trust_sell=parse_int(row[9]),
        trust_net=parse_int(row[10]),
        dealer_buy=parse_int(row[12]) + parse_int(row[15]),
        dealer_sell=parse_int(row[13]) + parse_int(row[16]),
        dealer_net=parse_int(row[11]),
        total_net=parse_int(row[18]),
    )


@dataclass
class MargnRow:
    """MI_MARGN 單檔融資融券（單位：張／交易單位）."""

    code: str
    name: str
    margin_buy: int
    margin_sell: int
    margin_cash_repay: int
    margin_prev_balance: int
    margin_balance: int
    margin_limit: int
    short_buy: int
    short_sell: int
    short_repay: int
    short_prev_balance: int
    short_balance: int
    short_limit: int
    offset: int


def parse_margn_row(row: list) -> MargnRow:
    """解析 MI_MARGN tables[1] 一列。欄數不符時 raise ValueError."""
    if len(row) < MARGN_EXPECTED_COLS:
        raise ValueError(
            f"MI_MARGN row has {len(row)} columns, expected >= {MARGN_EXPECTED_COLS}; "
            "TWSE schema may have changed"
        )
    return MargnRow(
        code=str(row[0]).strip(),
        name=str(row[1]).strip(),
        margin_buy=parse_int(row[2]),
        margin_sell=parse_int(row[3]),
        margin_cash_repay=parse_int(row[4]),
        margin_prev_balance=parse_int(row[5]),
        margin_balance=parse_int(row[6]),
        margin_limit=parse_int(row[7]),
        short_buy=parse_int(row[8]),
        short_sell=parse_int(row[9]),
        short_repay=parse_int(row[10]),
        short_prev_balance=parse_int(row[11]),
        short_balance=parse_int(row[12]),
        short_limit=parse_int(row[13]),
        offset=parse_int(row[14]),
    )
