"""Stock Service — yfinance 即時股價、技術指標、財報數據."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache

import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# ── Cache ────────────────────────────────────────────────────────────────────

# TTL cache for yf.Ticker.info (avoid redundant API calls within same request)
_info_cache: dict[str, tuple[float, dict]] = {}
_INFO_CACHE_TTL = 300  # 5 minutes


def _get_ticker_info(ticker: str) -> dict:
    """Get yf.Ticker.info with simple TTL cache."""
    now = time.time()
    if ticker in _info_cache:
        cached_time, cached_info = _info_cache[ticker]
        if now - cached_time < _INFO_CACHE_TTL:
            return cached_info
    try:
        info = yf.Ticker(ticker).info
    except Exception as e:
        logger.warning("Failed to fetch info for %s: %s", ticker, e)
        info = {}
    _info_cache[ticker] = (now, info)
    return info

# ── 台股名稱 → 代碼 動態查表 ─────────────────────────────────────────────────

_tw_listing_cache: dict[str, str] = {}   # name → code (e.g. "緯創" → "3231")
_tw_listing_market: dict[str, str] = {}  # code → market suffix (".TW" or ".TWO")
_tw_listing_cache_time: float = 0
_TW_LISTING_CACHE_TTL = 86400  # 24 hours


def _fetch_tw_stock_listing() -> dict[str, str]:
    """從 TWSE + TPEx Open API 取得所有台股 name → code 對照表（24h 快取）。"""
    global _tw_listing_cache, _tw_listing_market, _tw_listing_cache_time

    now = time.time()
    if _tw_listing_cache and (now - _tw_listing_cache_time < _TW_LISTING_CACHE_TTL):
        return _tw_listing_cache

    mapping: dict[str, str] = {}
    market: dict[str, str] = {}

    # --- TWSE 上市 ---
    try:
        resp = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            timeout=10,
        )
        resp.raise_for_status()
        for item in resp.json():
            code = item.get("Code", "").strip()
            name = item.get("Name", "").strip()
            if code and name:
                mapping[name] = code
                market[code] = ".TW"
    except Exception as e:
        logger.warning("Failed to fetch TWSE stock listing: %s", e)

    # --- TPEx 上櫃 ---
    try:
        resp = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes",
            timeout=10,
        )
        resp.raise_for_status()
        for item in resp.json():
            code = item.get("SecuritiesCompanyCode", "").strip()
            name = item.get("CompanyName", "").strip()
            if code and name:
                mapping[name] = code
                market[code] = ".TWO"
    except Exception as e:
        logger.warning("Failed to fetch TPEx stock listing: %s", e)

    if mapping:
        _tw_listing_cache = mapping
        _tw_listing_market = market
        _tw_listing_cache_time = now
        logger.info("Loaded %d TW stock listings (TWSE + TPEx)", len(mapping))

    return _tw_listing_cache


def _lookup_tw_name(name: str) -> str | None:
    """用中文名稱查找台股代碼，回傳 yfinance ticker (e.g. '3231.TW') 或 None。"""
    listing = _fetch_tw_stock_listing()
    code = listing.get(name)
    if code is None:
        return None
    suffix = _tw_listing_market.get(code, ".TW")
    return f"{code}{suffix}"


# ── Ticker 正規化 ────────────────────────────────────────────────────────────

# 常見台股代碼映射（離線備援，當 API 不可用時使用）
_TW_STOCK_ALIASES: dict[str, str] = {
    "台積電": "2330.TW",
    "鴻海": "2317.TW",
    "聯發科": "2454.TW",
    "台達電": "2308.TW",
    "富邦金": "2881.TW",
    "國泰金": "2882.TW",
    "中華電": "2412.TW",
    "統一": "1216.TW",
    "大立光": "3008.TW",
    "廣達": "2382.TW",
}


def normalize_ticker(raw: str) -> str:
    """將使用者輸入正規化為 yfinance ticker。

    查找順序：
    1. TWSE / TPEx 動態名稱表（涵蓋所有上市櫃股票）
    2. 硬編碼別名表（離線備援）
    3. 純數字 → 自動偵測 .TW / .TWO
    4. 其它格式直接回傳

    Examples:
        "台積電"    → "2330.TW"
        "緯創"      → "3231.TW"
        "$TSMC"     → "TSM"
        "2330"      → "2330.TW" (or "2330.TWO" if listed on OTC)
        "AAPL"      → "AAPL"
    """
    cleaned = raw.strip()
    upper = cleaned.upper()

    # 1) 動態查表（支援所有台股中文名稱）
    result = _lookup_tw_name(cleaned)
    if result:
        return result

    # 2) 硬編碼備援
    if upper in _TW_STOCK_ALIASES:
        return _TW_STOCK_ALIASES[upper]

    # 3) $TICKER 格式
    if upper.startswith("$"):
        upper = upper[1:]

    # 4) 純數字 → 台股（自動偵測上市 .TW / 上櫃 .TWO）
    if upper.isdigit():
        return _resolve_tw_ticker(upper)

    # 5) 數字.TW / .TWO 已經是正確格式
    if upper.endswith(".TW") or upper.endswith(".TWO"):
        return upper

    return upper


@lru_cache(maxsize=256)
def _resolve_tw_ticker(code: str) -> str:
    """自動偵測台股代碼是上市 (.TW) 或上櫃 (.TWO)。

    1. 先查 TWSE/TPEx 動態快取（零成本）。
    2. 若快取未命中，再用 yfinance 逐一嘗試 .TW / .TWO。
    結果以 lru_cache 快取，避免每次 tool call 都重跑。
    """
    # 先從動態快取判斷市場
    _fetch_tw_stock_listing()  # ensure cache is warm
    suffix = _tw_listing_market.get(code)
    if suffix:
        return f"{code}{suffix}"

    # 快取未命中 → 用 yfinance 探測
    for suffix in [".TW", ".TWO"]:
        ticker = f"{code}{suffix}"
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if not hist.empty:
                return ticker
        except Exception:
            continue

    # 預設回傳 .TW
    return f"{code}.TW"


def search_tw_stocks(q: str, limit: int = 10) -> list[dict]:
    """搜尋台股，支援代碼或名稱模糊查詢，回傳最多 limit 筆。"""
    listing = _fetch_tw_stock_listing()
    q_norm = q.strip().lower()
    if not q_norm:
        return []

    results: list[dict] = []
    for name, code in listing.items():
        if q_norm in code.lower() or q_norm in name.lower():
            market_suffix = _tw_listing_market.get(code, ".TW")
            results.append({
                "code": code,
                "name": name,
                "ticker": f"{code}{market_suffix}",
                "market": "上市" if market_suffix == ".TW" else "上櫃",
            })
        if len(results) >= limit:
            break

    return results


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class StockOverviewData:
    """股票基本資訊。"""

    ticker: str
    name: str = ""
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    volume: int | None = None
    market_cap: int | None = None
    currency: str = ""
    exchange: str = ""
    high_52w: float | None = None   # 52 週最高價
    low_52w: float | None = None    # 52 週最低價


@dataclass
class TechnicalIndicators:
    """技術指標計算結果."""

    ticker: str
    period: str = "3mo"
    # 均線
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    current_price: float | None = None
    ma_trend: str = ""  # 多頭排列 / 空頭排列 / 糾結
    # RSI
    rsi_14: float | None = None
    rsi_signal: str = ""  # 超買 / 超賣 / 中性
    # MACD
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    macd_cross: str = ""  # 金叉 / 死叉 / 無
    # KD
    k_value: float | None = None
    d_value: float | None = None
    kd_signal: str = ""  # 超買 / 超賣 / 金叉 / 死叉
    # 布林通道
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_position: str = ""  # 上軌之上 / 中上軌 / 中下軌 / 下軌之下
    # 支撐/壓力
    supports: list[tuple[str, float]] = field(default_factory=list)
    """支撐位列表，每項 (來源描述, 價格)，按價格由高到低排列（最近支撐在前）。"""
    resistances: list[tuple[str, float]] = field(default_factory=list)
    """壓力位列表，每項 (來源描述, 價格)，按價格由低到高排列（最近壓力在前）。"""
    fibonacci_levels: dict[str, float] = field(default_factory=dict)
    """費波那契回撤位，key 為比率字串（'23.6%', '38.2%', '50.0%', '61.8%'），value 為價格。"""
    swing_high: float | None = None  # 近期波段最高點
    swing_low: float | None = None   # 近期波段最低點
    # 停損建議
    stop_loss: float | None = None          # 建議停損價位
    stop_loss_note: str = ""                # 停損依據說明
    risk_reward_note: str = ""              # 風險報酬比參考
    # 綜合
    summary: str = ""


@dataclass
class FundamentalData:
    """基本面財報數據。"""

    ticker: str
    name: str = ""
    # 估值指標
    pe_ratio: float | None = None
    forward_pe: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    # 獲利能力
    roe: float | None = None
    roa: float | None = None
    profit_margin: float | None = None
    operating_margin: float | None = None
    # 成長
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    # 每股數據
    eps: float | None = None
    forward_eps: float | None = None
    dividend_yield: float | None = None
    # 合理價位估算（本益比法）
    cheap_price: float | None = None    # 便宜價（歷史低本益比 × EPS）
    fair_price: float | None = None     # 合理價（歷史平均本益比 × EPS）
    expensive_price: float | None = None  # 昂貴價（歷史高本益比 × EPS）
    pe_low: float | None = None          # 估算用的低 PE
    pe_mid: float | None = None          # 估算用的中 PE
    pe_high: float | None = None         # 估算用的高 PE
    valuation_note: str = ""             # 估值方法說明或警告
    # 其他
    sector: str = ""
    industry: str = ""
    description: str = ""


# ── Core Functions ───────────────────────────────────────────────────────────


def get_stock_overview(ticker: str) -> StockOverviewData:
    """取得股票基本概覽。"""
    ticker = normalize_ticker(ticker)
    info = _get_ticker_info(ticker)
    if not info:
        return StockOverviewData(ticker=ticker)

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")

    change = None
    change_pct = None
    if price is not None and prev_close is not None and prev_close != 0:
        change = round(price - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2)

    return StockOverviewData(
        ticker=ticker,
        name=info.get("shortName") or info.get("longName") or "",
        price=price,
        change=change,
        change_percent=change_pct,
        volume=info.get("volume") or info.get("regularMarketVolume"),
        market_cap=info.get("marketCap"),
        currency=info.get("currency", ""),
        exchange=info.get("exchange", ""),
        high_52w=info.get("fiftyTwoWeekHigh"),
        low_52w=info.get("fiftyTwoWeekLow"),
    )


def get_technical_indicators(ticker: str, period: str = "3mo") -> TechnicalIndicators:
    """計算技術指標：MA, RSI, MACD, KD, 布林通道。"""
    ticker = normalize_ticker(ticker)
    stock = yf.Ticker(ticker)

    try:
        df = stock.history(period=period)
    except Exception as e:
        logger.warning("Failed to fetch history for %s: %s", ticker, e)
        return TechnicalIndicators(ticker=ticker)

    if df.empty or len(df) < 14:
        logger.warning("Insufficient data for %s (%d rows)", ticker, len(df))
        return TechnicalIndicators(ticker=ticker)

    close = df["Close"]
    result = TechnicalIndicators(ticker=ticker, period=period)
    result.current_price = round(float(close.iloc[-1]), 2)

    # ── 均線 ──
    if len(close) >= 5:
        result.ma5 = round(float(close.rolling(5).mean().iloc[-1]), 2)
    if len(close) >= 10:
        result.ma10 = round(float(close.rolling(10).mean().iloc[-1]), 2)
    if len(close) >= 20:
        result.ma20 = round(float(close.rolling(20).mean().iloc[-1]), 2)
    if len(close) >= 60:
        result.ma60 = round(float(close.rolling(60).mean().iloc[-1]), 2)

    # 判斷均線排列
    mas = [v for v in [result.ma5, result.ma10, result.ma20, result.ma60] if v is not None]
    if len(mas) >= 3:
        if all(mas[i] >= mas[i + 1] for i in range(len(mas) - 1)):
            result.ma_trend = "多頭排列"
        elif all(mas[i] <= mas[i + 1] for i in range(len(mas) - 1)):
            result.ma_trend = "空頭排列"
        else:
            result.ma_trend = "糾結"

    # ── RSI (14) ──
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_val = float(rsi.iloc[-1])
    result.rsi_14 = round(rsi_val, 1)

    if rsi_val > 70:
        result.rsi_signal = "超買"
    elif rsi_val < 30:
        result.rsi_signal = "超賣"
    else:
        result.rsi_signal = "中性"

    # ── MACD (12, 26, 9) ──
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    result.macd = round(float(macd_line.iloc[-1]), 4)
    result.macd_signal = round(float(signal_line.iloc[-1]), 4)
    result.macd_histogram = round(float(histogram.iloc[-1]), 4)

    # 判斷金叉死叉（看最近兩天）
    if len(histogram) >= 2:
        if histogram.iloc[-2] < 0 and histogram.iloc[-1] > 0:
            result.macd_cross = "金叉"
        elif histogram.iloc[-2] > 0 and histogram.iloc[-1] < 0:
            result.macd_cross = "死叉"
        elif histogram.iloc[-1] > 0:
            result.macd_cross = "多方（DIF > DEA）"
        else:
            result.macd_cross = "空方（DIF < DEA）"

    # ── KD 指標 (9, 3, 3) ──
    if len(close) >= 9:
        low_9 = df["Low"].rolling(9).min()
        high_9 = df["High"].rolling(9).max()
        rsv = (close - low_9) / (high_9 - low_9) * 100

        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()

        result.k_value = round(float(k.iloc[-1]), 1)
        result.d_value = round(float(d.iloc[-1]), 1)

        if result.k_value > 80 and result.d_value > 80:
            result.kd_signal = "超買"
        elif result.k_value < 20 and result.d_value < 20:
            result.kd_signal = "超賣"
        elif len(k) >= 2 and k.iloc[-2] < d.iloc[-2] and k.iloc[-1] > d.iloc[-1]:
            result.kd_signal = "金叉"
        elif len(k) >= 2 and k.iloc[-2] > d.iloc[-2] and k.iloc[-1] < d.iloc[-1]:
            result.kd_signal = "死叉"
        else:
            result.kd_signal = "中性"

    # ── 布林通道 (20, 2) ──
    if len(close) >= 20:
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = sma20 + 2 * std20
        lower = sma20 - 2 * std20

        result.bb_upper = round(float(upper.iloc[-1]), 2)
        result.bb_middle = round(float(sma20.iloc[-1]), 2)
        result.bb_lower = round(float(lower.iloc[-1]), 2)

        price = result.current_price
        if price > result.bb_upper:
            result.bb_position = "上軌之上（強勢突破）"
        elif price > result.bb_middle:
            result.bb_position = "中軌與上軌之間（偏多）"
        elif price > result.bb_lower:
            result.bb_position = "下軌與中軌之間（偏空）"
        else:
            result.bb_position = "下軌之下（弱勢破底）"

    # ── 支撐 / 壓力位計算 ──
    _calc_support_resistance(df, result)

    # ── 綜合判斷 ──
    bullish = 0
    bearish = 0
    signals = []

    if result.ma_trend == "多頭排列":
        bullish += 1
        signals.append("均線多頭排列 ✅")
    elif result.ma_trend == "空頭排列":
        bearish += 1
        signals.append("均線空頭排列 ❌")

    if result.rsi_signal == "超買":
        bearish += 1
        signals.append(f"RSI {result.rsi_14} 超買 ⚠️")
    elif result.rsi_signal == "超賣":
        bullish += 1
        signals.append(f"RSI {result.rsi_14} 超賣（可能反彈）🔄")
    else:
        signals.append(f"RSI {result.rsi_14} 中性")

    if "金叉" in (result.macd_cross or ""):
        bullish += 1
        signals.append("MACD 金叉 ✅")
    elif "死叉" in (result.macd_cross or ""):
        bearish += 1
        signals.append("MACD 死叉 ❌")
    elif "多方" in (result.macd_cross or ""):
        bullish += 1
        signals.append("MACD 多方")

    if "超買" in (result.kd_signal or ""):
        bearish += 1
        signals.append("KD 超買區 ⚠️")
    elif "超賣" in (result.kd_signal or ""):
        bullish += 1
        signals.append("KD 超賣區 🔄")
    elif "金叉" in (result.kd_signal or ""):
        bullish += 1
        signals.append("KD 金叉 ✅")

    if "偏多" in (result.bb_position or ""):
        bullish += 1
    elif "偏空" in (result.bb_position or "") or "弱勢" in (result.bb_position or ""):
        bearish += 1

    if bullish > bearish + 1:
        result.summary = f"📈 偏多（{bullish}多/{bearish}空）— {'、'.join(signals)}"
    elif bearish > bullish + 1:
        result.summary = f"📉 偏空（{bullish}多/{bearish}空）— {'、'.join(signals)}"
    else:
        result.summary = f"⚖️ 中性（{bullish}多/{bearish}空）— {'、'.join(signals)}"

    return result


def _calc_support_resistance(df, result: TechnicalIndicators) -> None:
    """計算支撐與壓力位，填入 result.supports / resistances / fibonacci_levels。

    來源：
    1. 均線（MA5/10/20/60）— 股價上方為壓力，下方為支撐
    2. 布林通道上下軌
    3. 前波高/低點（swing high / swing low）
    4. 費波那契回撤位（38.2%、50%、61.8%）
    5. 整數心理關卡
    """
    price = result.current_price
    if price is None:
        return

    supports: list[tuple[str, float]] = []
    resistances: list[tuple[str, float]] = []

    # ── 1. 均線 ──
    ma_map = [
        ("MA5", result.ma5),
        ("MA10", result.ma10),
        ("MA20", result.ma20),
        ("MA60", result.ma60),
    ]
    for label, val in ma_map:
        if val is None:
            continue
        if val < price:
            supports.append((f"均線支撐 {label}={val}", val))
        elif val > price:
            resistances.append((f"均線壓力 {label}={val}", val))

    # ── 2. 布林通道 ──
    if result.bb_lower is not None and result.bb_lower < price:
        supports.append((f"布林下軌 {result.bb_lower}", result.bb_lower))
    if result.bb_middle is not None:
        if result.bb_middle < price:
            supports.append((f"布林中軌 {result.bb_middle}", result.bb_middle))
        elif result.bb_middle > price:
            resistances.append((f"布林中軌 {result.bb_middle}", result.bb_middle))
    if result.bb_upper is not None and result.bb_upper > price:
        resistances.append((f"布林上軌 {result.bb_upper}", result.bb_upper))

    # ── 3. 前波高低點（Swing High / Low）——以 5 根 K 棒為窗口 ──
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    window = 5
    n = len(close)

    swing_lows: list[float] = []
    swing_highs: list[float] = []

    for i in range(window, n - window):
        lo = float(low.iloc[i])
        hi = float(high.iloc[i])
        neighborhood_low = low.iloc[i - window: i + window + 1]
        neighborhood_high = high.iloc[i - window: i + window + 1]
        if lo <= float(neighborhood_low.min()):
            swing_lows.append(lo)
        if hi >= float(neighborhood_high.max()):
            swing_highs.append(hi)

    # 取最近 3 個前低（高於布林下軌且低於現價）
    recent_lows = sorted(
        {round(v, 2) for v in swing_lows if result.bb_lower is None or v > result.bb_lower * 0.95},
        reverse=True,
    )
    for lo in recent_lows[:3]:
        if lo < price:
            supports.append((f"前波低點 {lo}", lo))

    # 取最近 3 個前高（高於現價）
    recent_highs = sorted(
        {round(v, 2) for v in swing_highs},
    )
    for hi in recent_highs[::-1][:3]:  # 從最近的壓力由低到高
        if hi > price:
            resistances.append((f"前波高點 {hi}", hi))

    result.swing_low = round(float(low.min()), 2)
    result.swing_high = round(float(high.max()), 2)

    # ── 4. 費波那契回撤位 ──
    # 以整段歷史的最高/最低點計算（適用 3mo 區間）
    fib_high = result.swing_high
    fib_low = result.swing_low
    if fib_high is not None and fib_low is not None and fib_high > fib_low:
        spread = fib_high - fib_low
        fib_ratios = {"23.6%": 0.236, "38.2%": 0.382, "50.0%": 0.500, "61.8%": 0.618}
        fib_levels: dict[str, float] = {}
        for label, ratio in fib_ratios.items():
            level = round(fib_high - spread * ratio, 2)
            fib_levels[label] = level
            if level < price:
                supports.append((f"Fibonacci {label} 回撤 {level}", level))
            elif level > price:
                resistances.append((f"Fibonacci {label} 回撤 {level}", level))
        result.fibonacci_levels = fib_levels

    # ── 5. 整數心理關卡 ──
    # 依股價大小決定「關卡間距」
    if price >= 500:
        step = 100
    elif price >= 100:
        step = 50
    elif price >= 50:
        step = 10
    else:
        step = 5

    import math
    nearest_int_below = math.floor(price / step) * step
    nearest_int_above = math.ceil(price / step) * step

    if nearest_int_below > 0 and nearest_int_below != price:
        supports.append((f"心理關卡 {nearest_int_below}", float(nearest_int_below)))
    if nearest_int_above != price:
        resistances.append((f"心理關卡 {nearest_int_above}", float(nearest_int_above)))

    # ── 排序並去重（價格相近 ±0.5% 視為同一關卡，保留描述性更強的那個）──
    def _dedup(levels: list[tuple[str, float]], tolerance: float = 0.005) -> list[tuple[str, float]]:
        if not levels:
            return []
        levels = sorted(levels, key=lambda x: x[1], reverse=True)
        result_list: list[tuple[str, float]] = [levels[0]]
        for label, val in levels[1:]:
            if abs(val - result_list[-1][1]) / result_list[-1][1] > tolerance:
                result_list.append((label, val))
        return result_list

    # 支撐：由高到低（最近支撐在前）
    result.supports = _dedup(sorted(supports, key=lambda x: x[1], reverse=True))
    # 壓力：由低到高（最近壓力在前）
    result.resistances = _dedup(sorted(resistances, key=lambda x: x[1]))

    # ── 停損建議 ──
    # 策略：以最近一道支撐位下方 3% 為停損，若無支撐位則用布林下軌下方 3%
    if result.supports:
        nearest_support_label, nearest_support_val = result.supports[0]
        sl = round(nearest_support_val * 0.97, 2)
        result.stop_loss = sl
        result.stop_loss_note = f"最近支撐 {nearest_support_label} 下方 3%"
    elif result.bb_lower is not None:
        sl = round(result.bb_lower * 0.97, 2)
        result.stop_loss = sl
        result.stop_loss_note = f"布林下軌 {result.bb_lower} 下方 3%"

    # 風險報酬比（以最近壓力 vs 停損計算）
    if result.stop_loss and result.resistances and price:
        nearest_resist_val = result.resistances[0][1]
        potential_gain = nearest_resist_val - price
        potential_loss = price - result.stop_loss
        if potential_loss > 0:
            rr = round(potential_gain / potential_loss, 1)
            result.risk_reward_note = (
                f"潛在獲利 {potential_gain:.1f} / 潛在虧損 {potential_loss:.1f} "
                f"→ 風險報酬比 1:{rr}"
            )


def _calc_valuation(ticker_str: str, info: dict, eps: float | None, forward_eps: float | None) -> dict:
    """用歷史本益比區間計算便宜/合理/昂貴價位。

    策略：
    1. 嘗試從歷史股價 + EPS 反推 PE 區間（最精確）
    2. 若無法取得歷史資料，使用 yfinance info 中的 trailingPE + forwardPE 推估
    3. 都不行就回傳空值
    """
    result: dict = {}

    # 決定用哪個 EPS（優先 forward → trailing）
    base_eps = forward_eps or eps
    if base_eps is None or base_eps <= 0:
        result["valuation_note"] = "EPS 為負或不可用，無法進行本益比估值"
        return result

    # 嘗試從歷史股價推算 PE 區間
    pe_values: list[float] = []
    try:
        stock = yf.Ticker(ticker_str)
        # 取近 3 年月收盤價
        hist = stock.history(period="3y", interval="1mo")
        if not hist.empty and eps and eps > 0:
            for price in hist["Close"]:
                pe = float(price) / eps
                if 0 < pe < 200:  # 過濾異常值
                    pe_values.append(pe)
    except Exception as e:
        logger.debug("Could not compute historical PE for %s: %s", ticker_str, e)

    if len(pe_values) >= 6:
        pe_values.sort()
        n = len(pe_values)
        pe_low = pe_values[int(n * 0.25)]   # 25th percentile
        pe_mid = pe_values[int(n * 0.50)]   # median
        pe_high = pe_values[int(n * 0.75)]  # 75th percentile
        result["pe_low"] = round(pe_low, 1)
        result["pe_mid"] = round(pe_mid, 1)
        result["pe_high"] = round(pe_high, 1)
        result["cheap_price"] = round(base_eps * pe_low, 2)
        result["fair_price"] = round(base_eps * pe_mid, 2)
        result["expensive_price"] = round(base_eps * pe_high, 2)
        result["valuation_note"] = (
            f"以近 3 年歷史 PE 區間 ({result['pe_low']}~{result['pe_high']}) × "
            f"{'Forward' if forward_eps else 'TTM'} EPS {base_eps:.2f} 計算"
        )
    else:
        # fallback: 用 info 中的 PE 估算 ±30% 區間
        trailing_pe = info.get("trailingPE")
        forward_pe_val = info.get("forwardPE")
        ref_pe = forward_pe_val or trailing_pe
        if ref_pe and 0 < ref_pe < 200:
            pe_low = ref_pe * 0.7
            pe_mid = ref_pe
            pe_high = ref_pe * 1.3
            result["pe_low"] = round(pe_low, 1)
            result["pe_mid"] = round(pe_mid, 1)
            result["pe_high"] = round(pe_high, 1)
            result["cheap_price"] = round(base_eps * pe_low, 2)
            result["fair_price"] = round(base_eps * pe_mid, 2)
            result["expensive_price"] = round(base_eps * pe_high, 2)
            result["valuation_note"] = (
                f"歷史數據不足，以當前 PE {ref_pe:.1f} ±30% 範圍估算 × "
                f"{'Forward' if forward_eps else 'TTM'} EPS {base_eps:.2f}"
            )
        else:
            result["valuation_note"] = "無法取得有效的 PE 數據進行估值"

    return result


def get_fundamental_data(ticker: str) -> FundamentalData:
    """取得基本面財報數據，含合理價位估算。"""
    ticker = normalize_ticker(ticker)
    info = _get_ticker_info(ticker)
    if not info:
        return FundamentalData(ticker=ticker)

    eps = info.get("trailingEps")
    forward_eps = info.get("forwardEps")

    # 計算估值
    valuation = _calc_valuation(ticker, info, eps, forward_eps)

    return FundamentalData(
        ticker=ticker,
        name=info.get("shortName") or info.get("longName") or "",
        # 估值
        pe_ratio=info.get("trailingPE"),
        forward_pe=info.get("forwardPE"),
        pb_ratio=info.get("priceToBook"),
        ps_ratio=info.get("priceToSalesTrailing12Months"),
        # 獲利能力
        roe=info.get("returnOnEquity"),
        roa=info.get("returnOnAssets"),
        profit_margin=info.get("profitMargins"),
        operating_margin=info.get("operatingMargins"),
        # 成長
        revenue_growth=info.get("revenueGrowth"),
        earnings_growth=info.get("earningsGrowth"),
        # 每股
        eps=eps,
        forward_eps=forward_eps,
        dividend_yield=info.get("dividendYield"),
        # 合理價位
        cheap_price=valuation.get("cheap_price"),
        fair_price=valuation.get("fair_price"),
        expensive_price=valuation.get("expensive_price"),
        pe_low=valuation.get("pe_low"),
        pe_mid=valuation.get("pe_mid"),
        pe_high=valuation.get("pe_high"),
        valuation_note=valuation.get("valuation_note", ""),
        # 分類
        sector=info.get("sector", ""),
        industry=info.get("industry", ""),
        description=info.get("longBusinessSummary", ""),
    )


# ── Formatting ───────────────────────────────────────────────────────────────


def format_stock_data_for_prompt(
    overview: StockOverviewData,
    technical: TechnicalIndicators,
    fundamental: FundamentalData,
) -> str:
    """將股票數據格式化為 Prompt 可用的文字。"""
    parts = []

    # 基本資訊
    parts.append(f"📌 {overview.name} ({overview.ticker})")
    if overview.price is not None:
        sign = "+" if (overview.change or 0) >= 0 else ""
        parts.append(
            f"   現價：{overview.currency} {overview.price}  "
            f"{sign}{overview.change} ({sign}{overview.change_percent}%)"
        )
    if overview.volume:
        parts.append(f"   成交量：{overview.volume:,}")
    if overview.market_cap:
        parts.append(f"   市值：{overview.market_cap:,}")

    # 技術指標
    parts.append("")
    parts.append("📊 技術指標：")
    if technical.ma_trend:
        mas_str = " / ".join(
            f"MA{n}={v}"
            for n, v in [(5, technical.ma5), (10, technical.ma10), (20, technical.ma20), (60, technical.ma60)]
            if v is not None
        )
        parts.append(f"   均線：{technical.ma_trend}（{mas_str}）")
    if technical.rsi_14 is not None:
        parts.append(f"   RSI(14)：{technical.rsi_14} — {technical.rsi_signal}")
    if technical.macd is not None:
        parts.append(
            f"   MACD：{technical.macd:.4f}（Signal: {technical.macd_signal:.4f}, "
            f"Histogram: {technical.macd_histogram:.4f}）— {technical.macd_cross}"
        )
    if technical.k_value is not None:
        parts.append(f"   KD：K={technical.k_value}, D={technical.d_value} — {technical.kd_signal}")
    if technical.bb_upper is not None:
        parts.append(
            f"   布林通道：上軌={technical.bb_upper}, 中軌={technical.bb_middle}, "
            f"下軌={technical.bb_lower} — {technical.bb_position}"
        )
    if technical.summary:
        parts.append(f"   📋 綜合：{technical.summary}")

    # 基本面
    parts.append("")
    parts.append("📈 基本面數據：")

    def _fmt_pct(val: float | None) -> str:
        return f"{val * 100:.1f}%" if val is not None else "N/A"

    def _fmt_num(val: float | None, decimals: int = 2) -> str:
        return f"{val:.{decimals}f}" if val is not None else "N/A"

    parts.append(f"   PE（TTM）：{_fmt_num(fundamental.pe_ratio)}  |  Forward PE：{_fmt_num(fundamental.forward_pe)}")
    parts.append(f"   PB：{_fmt_num(fundamental.pb_ratio)}  |  PS：{_fmt_num(fundamental.ps_ratio)}")
    parts.append(f"   ROE：{_fmt_pct(fundamental.roe)}  |  ROA：{_fmt_pct(fundamental.roa)}")
    parts.append(f"   淨利率：{_fmt_pct(fundamental.profit_margin)}  |  營業利益率：{_fmt_pct(fundamental.operating_margin)}")
    parts.append(f"   營收成長：{_fmt_pct(fundamental.revenue_growth)}  |  獲利成長：{_fmt_pct(fundamental.earnings_growth)}")
    parts.append(f"   EPS（TTM）：{_fmt_num(fundamental.eps)}  |  Forward EPS：{_fmt_num(fundamental.forward_eps)}")
    if fundamental.dividend_yield is not None:
        parts.append(f"   殖利率：{_fmt_pct(fundamental.dividend_yield)}")
    if fundamental.sector:
        parts.append(f"   產業：{fundamental.sector} / {fundamental.industry}")

    return "\n".join(parts)


def get_full_stock_data(ticker: str) -> str:
    """取得完整股票數據並格式化為 prompt 文字（一站式呼叫）。"""
    overview = get_stock_overview(ticker)
    technical = get_technical_indicators(ticker)
    fundamental = get_fundamental_data(ticker)
    return format_stock_data_for_prompt(overview, technical, fundamental)
