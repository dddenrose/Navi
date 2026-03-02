"""Tool: 技術指標分析（MA, RSI, MACD, KD, 布林通道）."""

from dataclasses import asdict

from langchain_core.tools import tool

from services.stock_service import get_technical_indicators


@tool
def analyze_technicals(ticker: str, period: str = "3mo") -> str:
    """計算股票的技術指標，包含均線、RSI、MACD、KD、布林通道，並給出綜合判斷。

    Args:
        ticker: 股票代碼，可以是中文名稱（台積電）、數字代碼（2330）或美股代碼（AAPL）。
        period: 分析期間，預設 3 個月。可選：1mo, 3mo, 6mo, 1y。
    """
    data = get_technical_indicators(ticker, period=period)

    if data.current_price is None:
        return f"無法取得 {ticker} 的歷史數據，無法計算技術指標。"

    parts = [f"📊 {data.ticker} 技術面分析（期間：{data.period}）", ""]

    # 均線
    if data.ma_trend:
        mas = " / ".join(
            f"MA{n}={v}"
            for n, v in [(5, data.ma5), (10, data.ma10), (20, data.ma20), (60, data.ma60)]
            if v is not None
        )
        parts.append(f"均線：{data.ma_trend}（{mas}）")

    # RSI
    if data.rsi_14 is not None:
        parts.append(f"RSI(14)：{data.rsi_14} — {data.rsi_signal}")

    # MACD
    if data.macd is not None:
        parts.append(f"MACD：DIF={data.macd:.4f}, DEA={data.macd_signal:.4f}, 柱狀={data.macd_histogram:.4f} — {data.macd_cross}")

    # KD
    if data.k_value is not None:
        parts.append(f"KD：K={data.k_value}, D={data.d_value} — {data.kd_signal}")

    # 布林通道
    if data.bb_upper is not None:
        parts.append(f"布林通道：上={data.bb_upper}, 中={data.bb_middle}, 下={data.bb_lower} — {data.bb_position}")

    # 綜合
    if data.summary:
        parts.append(f"\n📋 綜合判斷：{data.summary}")

    return "\n".join(parts)
