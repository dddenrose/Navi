"""Tool: 查詢即時股價與基本資訊."""

from langchain_core.tools import tool

from services.stock_service import get_stock_overview, normalize_ticker


@tool
def get_stock_price(ticker: str) -> str:
    """查詢股票的即時價格、漲跌幅、成交量和市值。

    Args:
        ticker: 股票代碼，可以是中文名稱（台積電）、數字代碼（2330）或美股代碼（AAPL）。
    """
    data = get_stock_overview(ticker)

    if data.price is None:
        return f"無法取得 {ticker} 的股價數據，請確認代碼是否正確。"

    sign = "+" if (data.change or 0) >= 0 else ""
    parts = [
        f"📌 {data.name} ({data.ticker})",
        f"現價：{data.currency} {data.price}",
        f"漲跌：{sign}{data.change} ({sign}{data.change_percent}%)",
    ]
    if data.volume:
        parts.append(f"成交量：{data.volume:,}")
    if data.market_cap:
        parts.append(f"市值：{data.market_cap:,}")

    return "\n".join(parts)
