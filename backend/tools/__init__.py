"""Navi LangChain Tools — Agent 可呼叫的工具集."""

from tools.backtest_tool import run_strategy_backtest
from tools.fundamental_analysis import analyze_fundamentals
from tools.institutional import get_institutional
from tools.knowledge_search import search_knowledge
from tools.margin_trading import get_margin_trading
from tools.news_search import search_financial_news
from tools.portfolio_tool import get_portfolio
from tools.stock_price import get_stock_price
from tools.technical_analysis import analyze_technicals

ALL_TOOLS = [
    get_stock_price,
    analyze_technicals,
    analyze_fundamentals,
    search_knowledge,
    get_institutional,
    get_margin_trading,
    search_financial_news,
    get_portfolio,
    run_strategy_backtest,
]

__all__ = [
    "ALL_TOOLS",
    "get_stock_price",
    "analyze_technicals",
    "analyze_fundamentals",
    "search_knowledge",
    "get_institutional",
    "get_margin_trading",
    "search_financial_news",
    "get_portfolio",
    "run_strategy_backtest",
]
