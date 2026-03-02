"""Stock Service — yfinance 即時股價、技術指標、財報數據."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import yfinance as yf

logger = logging.getLogger(__name__)

# ── Ticker 正規化 ────────────────────────────────────────────────────────────

# 常見台股代碼映射（使用者輸入 → yfinance ticker）
TW_STOCK_ALIASES: dict[str, str] = {
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

    Examples:
        "台積電"    → "2330.TW"
        "$TSMC"     → "TSM"
        "2330"      → "2330.TW" (or "2330.TWO" if listed on OTC)
        "AAPL"      → "AAPL"
    """
    raw = raw.strip().upper()

    # 中文名稱查表
    if raw in TW_STOCK_ALIASES:
        return TW_STOCK_ALIASES[raw]

    # $TICKER 格式
    if raw.startswith("$"):
        raw = raw[1:]

    # 純數字 → 台股（自動偵測上市 .TW / 上櫃 .TWO）
    if raw.isdigit():
        return _resolve_tw_ticker(raw)

    # 數字.TW / .TWO 已經是正確格式
    if raw.endswith(".TW") or raw.endswith(".TWO"):
        return raw

    return raw


def _resolve_tw_ticker(code: str) -> str:
    """自動偵測台股代碼是上市 (.TW) 或上櫃 (.TWO)。

    先嘗試 .TW，如果沒有數據就嘗試 .TWO。
    """
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
    # 其他
    sector: str = ""
    industry: str = ""
    description: str = ""


# ── Core Functions ───────────────────────────────────────────────────────────


def get_stock_overview(ticker: str) -> StockOverviewData:
    """取得股票基本概覽。"""
    ticker = normalize_ticker(ticker)
    stock = yf.Ticker(ticker)

    try:
        info = stock.info
    except Exception as e:
        logger.warning("Failed to fetch info for %s: %s", ticker, e)
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


def get_fundamental_data(ticker: str) -> FundamentalData:
    """取得基本面財報數據。"""
    ticker = normalize_ticker(ticker)
    stock = yf.Ticker(ticker)

    try:
        info = stock.info
    except Exception as e:
        logger.warning("Failed to fetch info for %s: %s", ticker, e)
        return FundamentalData(ticker=ticker)

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
        eps=info.get("trailingEps"),
        forward_eps=info.get("forwardEps"),
        dividend_yield=info.get("dividendYield"),
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
