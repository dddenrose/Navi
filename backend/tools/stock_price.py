"""Tool: 查詢股票即時/收盤價與基本資訊。

台股股價預設來自 TWSE MIS 盤中即時報價（每 5 秒撮合一次），盤後則為當日收盤；
撮合間隔 `z` 缺值時，回退到最佳買賣價中位數。listing 名稱對照與 fallback
資料源仍使用 TWSE/TPEx Open API（T-1 收盤）。美股則來自 yfinance。
輸出會明確標示資料時點（現價 vs 收盤）與來源（MIS / TWSE / TPEx / yfinance）。
"""

from langchain_core.tools import tool

from services.stock_service import get_stock_overview


@tool
def get_stock_price(ticker: str) -> str:
    """查詢股票的最新價格、漲跌幅、成交量和市值。

    台股盤中（週一至週五 09:00–13:30）回傳即時撮合價（MIS，~5 秒延遲）；
    盤後回傳當日收盤；MIS 失敗時自動 fallback 到 TWSE/TPEx Open API（T-1 收盤）。
    美股回傳 yfinance 即時報價。

    Args:
        ticker: 股票代碼，可以是中文名稱（台積電）、數字代碼（2330）或美股代碼（AAPL）。
    """
    data = get_stock_overview(ticker)

    if data.price is None:
        return (
            f"無法取得 {ticker} 的股價數據，請確認代碼是否正確或稍後再試。"
            "（台股盤中以 TWSE MIS 即時報價為主，盤後改用 TWSE/TPEx 收盤；遇假日或休市可能暫時無資料）"
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
