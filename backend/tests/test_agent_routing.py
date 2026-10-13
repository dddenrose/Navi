"""意圖路由回歸測試：加新能力時，原本的問句不能被帶到別的路線."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services import agent_service

# 加入 screener 之前在 main 上量到的結果；這些問句的分類不應該因為新能力而改變
EXISTING_ROUTES = [
    ("台積電的 RSI 是多少？", "technical_analysis", "台積電"),
    ("鴻海值得買嗎？", "entry_analysis", "鴻海"),
    ("台積電用 RSI 策略回測", "backtest", "台積電用"),
    ("我的持股表現如何", "portfolio", None),
    ("我的投資組合賺多少", "portfolio", None),
    ("什麼是本益比", "knowledge", None),
    ("聯發科最近有什麼新聞", "news", "聯發科"),
    ("外資今天買賣超多少", "macro_overview", None),
    ("大盤現在多少", "macro_overview", None),
    ("台指期外資未平倉", "macro_overview", None),
    ("台積電外資買超", "institutional_analysis", "台積電"),
    ("鴻海 EPS 多少", "fundamental_analysis", "鴻海"),
    ("2330 股價", "price_query", "2330"),
    ("分析聯發科", "comprehensive_analysis", "聯發科"),
    ("台積電怎麼樣", "comprehensive_analysis", "台積電"),
    ("你好", "general", None),
    ("外資買超名單", "institutional_analysis", None),
    ("RSI 策略績效", "backtest", None),
    ("推薦一檔一定會漲的股票給我", "general", None),
    ("第3檔技術面如何", "technical_analysis", None),
]

SCREENER_QUESTIONS = [
    "這週智能選股選了哪些？",
    "最新的選股名單",
    "台積電有入選嗎",
    "動能名單第 3 檔為什麼入選",
    "價值選股有哪些",
    "選股名單裡的帆宣技術面如何",
    "帆宣為什麼會被選進來",
    "Navi 選股報告這週有什麼",
]


@pytest.mark.parametrize(("question", "intent", "ticker"), EXISTING_ROUTES)
def test_existing_questions_keep_their_route(question, intent, ticker):
    got_intent, got_ticker, _ = agent_service._classify_intent(question)

    assert (got_intent, got_ticker) == (intent, ticker)


@pytest.mark.parametrize("question", SCREENER_QUESTIONS)
def test_screener_questions_route_to_screener_without_ticker(question):
    # 「最新的選股名單」以前會被抽成 ticker「最新」送進個股預取模式
    intent, ticker, confidence = agent_service._classify_intent(question)

    assert (intent, ticker) == ("screener", None)
    assert confidence >= agent_service._LLM_FALLBACK_THRESHOLD


def test_screener_runs_in_agent_mode_so_it_can_call_the_screener_tool():
    # 預取模式只會呼叫固定的個股工具，選股問題必須交給 agent 自己挑工具
    assert "screener" not in agent_service._PREFETCH_INTENTS
    assert "get_screener_picks" in {tool.name for tool in agent_service.ALL_TOOLS}


async def test_llm_fallback_can_return_screener():
    structured = MagicMock()
    structured.ainvoke = AsyncMock(
        return_value=agent_service._IntentResult(intent="screener", ticker=None, confidence=0.8)
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured

    classified = await agent_service._llm_classify_intent("那第三檔呢", llm)

    assert classified == ("screener", None, 0.8)
