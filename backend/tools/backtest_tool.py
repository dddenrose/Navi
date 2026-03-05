"""Tool: 策略回測 — 讓 Agent 能執行歷史回測並解讀結果."""

from langchain_core.tools import tool

from services.backtest_service import format_backtest_result, run_backtest


@tool
def run_strategy_backtest(
    ticker: str,
    strategy: str = "ma_cross",
    period: str = "1y",
    initial_capital: float = 1_000_000,
) -> str:
    """執行股票策略回測，模擬歷史績效並回傳詳細報告。

    支援三種內建策略：
    - ma_cross：均線交叉（MA5 上穿 MA20 買入，下穿賣出）
    - rsi：RSI 指標（RSI < 30 超賣買入，RSI > 70 超買賣出）
    - macd：MACD 指標（MACD 金叉買入，死叉賣出）

    Args:
        ticker: 股票代碼，支援中文名稱（台積電）、數字代碼（2330）或美股代碼（AAPL）。
        strategy: 策略名稱，可選 ma_cross / rsi / macd。預設 ma_cross。
        period: 回測期間，可選 3mo / 6mo / 1y / 2y。預設 1y。
        initial_capital: 初始資金，預設 1,000,000 元。
    """
    result = run_backtest(
        ticker=ticker,
        strategy=strategy,
        period=period,
        initial_capital=initial_capital,
    )
    return format_backtest_result(result)
