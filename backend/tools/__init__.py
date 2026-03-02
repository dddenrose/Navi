"""Navi LangChain Tools — Agent 可呼叫的工具集."""

from tools.fundamental_analysis import analyze_fundamentals
from tools.knowledge_search import search_knowledge
from tools.stock_price import get_stock_price
from tools.technical_analysis import analyze_technicals

ALL_TOOLS = [
    get_stock_price,
    analyze_technicals,
    analyze_fundamentals,
    search_knowledge,
]

__all__ = [
    "ALL_TOOLS",
    "get_stock_price",
    "analyze_technicals",
    "analyze_fundamentals",
    "search_knowledge",
]
