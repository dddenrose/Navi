"""Tool: 查詢股票收盤價與基本資訊。

台股股價來自 TWSE / TPEx Open API（最近一個交易日收盤，官方來源），
美股股價來自 yfinance。為避免使用者混淆，輸出會明確標示資料時點與來源。
"""

from langchain_core.tools import tool

from services.stock_service import get_stock_overview


@tool
def get_stock_price(ticker: str) -> str:
    """查詢股票的最近一個交易日收盤價、漲跌幅、成交量和市值（台股為收盤資料，非盤中即時）。

    Args:
        ticker: 股票代碼，可以是中文名稱（台積電）、數字代碼（2330）或美股代碼（AAPL）。
    """
    data = get_stock_overview(ticker)

    if data.price is None:
        return (
            f"無法取得 {ticker} 的股價數據，請確認代碼是否正確或稍後再試。"
            "（台股以 TWSE/TPEx 收盤資料為準，遇假日或休市可能暫時無資料）"
        )

    sign = "+" if (data.change or 0) >= 0 else ""

    # 明確標註資料時點
    if data.is_intraday:
        price_label = "現價"
    elif data.as_of_date:
        price_label = f"收盤（{data.as_of_date} {data.data_source}）"
    else:
        price_label = "報價"

    parts = [
        f"📌 {data.name} ({data.ticker})",
        f"{price_label}：{data.currency} {data.price}",
        f"漲跌：{sign}{data.change} ({sign}{data.change_percent}%)",
    ]
    if data.volume:
        # 台股 1 張 = 1000 股；同時顯示張數方便閱讀
        if data.currency == "TWD":
            sheets = data.volume // 1000
            parts.append(f"成交量：{sheets:,} 張（{data.volume:,} 股）")
        else:
            parts.append(f"成交量：{data.volume:,} 股")
    if data.market_cap:
        parts.append(f"市值：{data.market_cap:,}")

    return "\n".join(parts)
