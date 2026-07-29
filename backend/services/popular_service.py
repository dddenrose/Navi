"""Popular Stocks Service — 熱門標的排行（成交值／漲幅／跌幅）與迷你走勢圖.

資料來源全部沿用 `stock_service.get_tw_quotes_snapshot()` 已快取的全市場快照，
不額外呼叫交易所 API；只有 sparkline 需要向 yfinance 批次抓一次歷史。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import yfinance as yf

from services.stock_service import get_tw_quotes_snapshot

logger = logging.getLogger(__name__)

_TOP_N = 8
_SPARK_PERIOD = "1mo"

# 漲跌幅榜的流動性門檻（成交值，元）。沒有門檻的話榜單會被冷門股洗版——
# 它們一兩筆委託就能拉出 9% 的漲幅，對使用者沒有參考價值。
# 成交值榜本身就是流動性排序，不需要另外設限。
_MIN_TURNOVER_FOR_PCT_BOARD = 30_000_000

# 上市櫃普通股 = 4 位數字且不以 0 開頭（代碼範圍 1101–9958）。
# 排除 5–6 碼的權證（數量龐大會洗版）與 ETF——注意 ETF 有 4 碼的（0050、0056），
# 只靠長度濾不掉，必須另外排除開頭的 0。
_COMMON_STOCK_CODE_LEN = 4

_CACHE_TTL = 1800  # 30 分鐘，與報價快照一致

_NOTE = (
    "依交易所收盤資料排序，僅含上市櫃普通股（不含 ETF 與權證）；"
    "漲跌幅榜限成交值 3,000 萬元以上"
)


@dataclass
class PopularStock:
    """排行榜上的單檔個股."""

    ticker: str  # yfinance 格式，e.g. "2330.TW"
    code: str  # 交易所代碼，e.g. "2330"
    name: str
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    volume_shares: int | None = None
    turnover: float | None = None  # 成交值（元）
    spark: list[float] = field(default_factory=list)
    """近一個月的收盤序列（由舊到新），供前端畫 sparkline；抓取失敗時為空。"""


@dataclass
class PopularBoard:
    """單一排行榜."""

    key: str  # turnover / gainers / losers
    label: str
    items: list[PopularStock] = field(default_factory=list)


@dataclass
class PopularResult:
    """熱門標的查詢結果."""

    boards: list[PopularBoard] = field(default_factory=list)
    as_of_date: str = ""
    note: str = ""


# 以 top_n 為 key：不同的 limit 是不同的結果集，共用一個 slot 會回錯筆數
_cache: dict[int, tuple[float, PopularResult]] = {}


def _change_percent(close: float | None, change: float | None) -> float | None:
    """由收盤價與漲跌價差回推漲跌幅（交易所 API 未直接提供百分比）。"""
    if close is None or change is None:
        return None
    prev_close = close - change
    if not prev_close:
        return None
    return round((change / prev_close) * 100, 2)


def _fetch_sparklines(tickers: list[str]) -> dict[str, list[float]]:
    """一次批次抓多檔的近月收盤序列。

    逐檔呼叫 `yf.Ticker().history()` 在 24 檔時要數秒；`yf.download` 併發抓取
    只需約 1 秒。個別 ticker 失敗不影響其他檔。
    """
    if not tickers:
        return {}

    try:
        df = yf.download(
            " ".join(tickers),
            period=_SPARK_PERIOD,
            interval="1d",
            group_by="ticker",
            progress=False,
            auto_adjust=True,
            threads=True,
        )
    except Exception as e:
        logger.warning("Failed to batch download sparklines: %s", e)
        return {}

    if df is None or df.empty:
        return {}

    out: dict[str, list[float]] = {}
    single = len(tickers) == 1
    for ticker in tickers:
        try:
            # 單檔時 yf.download 不會加上 ticker 這層 column index
            series = df["Close"] if single else df[ticker]["Close"]
            values = [round(float(v), 2) for v in series.dropna().tolist()]
            if values:
                out[ticker] = values
        except Exception:  # noqa: PERF203 — 個別 ticker 缺資料屬正常情況
            logger.debug("No sparkline data for %s", ticker)
    return out


def _to_stock(quote) -> PopularStock:
    return PopularStock(
        ticker=f"{quote.code}{quote.market}",
        code=quote.code,
        name=quote.name,
        price=quote.close,
        change=quote.change,
        change_percent=_change_percent(quote.close, quote.change),
        volume_shares=quote.volume_shares,
        turnover=quote.turnover,
    )


def get_popular_stocks(top_n: int = _TOP_N, use_cache: bool = True) -> PopularResult:
    """取得熱門標的三榜：成交值、漲幅、跌幅（僅台股上市櫃普通股）。

    排行本身完全由已快取的全市場收盤快照計算，不額外呼叫交易所 API。
    """
    now = time.time()
    if use_cache:
        cached = _cache.get(top_n)
        if cached and (now - cached[0] < _CACHE_TTL):
            return cached[1]

    snapshot = get_tw_quotes_snapshot()
    if not snapshot:
        logger.warning("TW quote snapshot empty; cannot build popular boards")
        return PopularResult(note="暫時無法取得市場報價")

    candidates = [
        q
        for q in snapshot.values()
        if len(q.code) == _COMMON_STOCK_CODE_LEN
        and q.code.isdigit()
        and not q.code.startswith("0")
        and q.close is not None
    ]
    if not candidates:
        return PopularResult(note="暫時無法取得市場報價")

    by_turnover = sorted(
        (q for q in candidates if q.turnover is not None),
        key=lambda q: q.turnover or 0,
        reverse=True,
    )[:top_n]

    liquid = [
        q
        for q in candidates
        if (q.turnover or 0) >= _MIN_TURNOVER_FOR_PCT_BOARD
        and _change_percent(q.close, q.change) is not None
    ]
    by_change = sorted(liquid, key=lambda q: _change_percent(q.close, q.change) or 0)
    gainers = list(reversed(by_change[-top_n:]))
    losers = by_change[:top_n]

    boards = [
        PopularBoard(key="turnover", label="成交值", items=[_to_stock(q) for q in by_turnover]),
        PopularBoard(key="gainers", label="漲幅", items=[_to_stock(q) for q in gainers]),
        PopularBoard(key="losers", label="跌幅", items=[_to_stock(q) for q in losers]),
    ]

    # 三榜會有重疊，去重後只抓一次
    tickers = sorted({s.ticker for b in boards for s in b.items})
    sparks = _fetch_sparklines(tickers)
    for board in boards:
        for stock in board.items:
            stock.spark = sparks.get(stock.ticker, [])

    as_of = next((q.date for q in candidates if q.date), "")
    result = PopularResult(boards=boards, as_of_date=as_of, note=_NOTE)

    _cache[top_n] = (now, result)
    return result
