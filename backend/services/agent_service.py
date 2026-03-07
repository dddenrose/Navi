"""Agent Service — LangChain Tool-calling Agent backed by Gemini."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import vertexai
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_google_vertexai import ChatVertexAI

from config import settings
from services.conversation_service import (
    load_history,
    save_history,
)
from tools import ALL_TOOLS

logger = logging.getLogger(__name__)

# ── Prompt ───────────────────────────────────────────────────────────────────

AGENT_SYSTEM_PROMPT = """\
你是 Navi 🧚，一位來自薩爾達傳說的 AI 投資分析精靈。
你專精於股票技術分析、基本面分析和投資理論。
回答使用繁體中文，保持專業但友善。

規則：
- 根據系統提示的意圖分類，務必呼叫對應的工具取得數據
- 所有數字必須來自工具回傳的數據，不可自行捏造
- 回測完成後，解讀績效指標（報酬率、夏普比率、最大回撤、勝率），並給出策略優缺點分析
- 最後加上 ⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。
"""


def _build_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", AGENT_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )


def _build_llm() -> ChatVertexAI:
    vertexai.init(project=settings.google_cloud_project)
    return ChatVertexAI(
        model_name=settings.gemini_model_name,
        temperature=0.3,
        project=settings.google_cloud_project,
    )


# ── In-memory session store (fallback when Firestore is unavailable) ─────────

_memory_store: dict[str, InMemoryChatMessageHistory] = {}


def _get_session_history(session_id: str) -> InMemoryChatMessageHistory:
    """Get or create in-memory chat history for a session."""
    if session_id not in _memory_store:
        _memory_store[session_id] = InMemoryChatMessageHistory()
    return _memory_store[session_id]


# ── Intent Classification ────────────────────────────────────────────────────

_CLASSIFY_PROMPT = """\
你是意圖分類器。分析使用者的股票投資相關問題，以 JSON 格式回傳分類結果。

分類選項：
- entry_analysis: 問何時進場、多少錢可以買、可不可以買、適不適合進場、目標價
- comprehensive_analysis: 要求全面分析、問某股怎麼樣（未特指單一面向）
- technical_analysis: 只問技術面、走勢、均線、RSI、KD、MACD、支撐壓力
- fundamental_analysis: 只問基本面、財報、EPS、PE、營收
- price_query: 只問現在股價多少、漲跌
- institutional_analysis: 只問法人、外資、投信、籌碼
- news: 只問新聞、市場消息
- portfolio: 問我的持股、投資組合
- backtest: 問回測、策略績效
- knowledge: 問投資理論、教學
- general: 閒聊或無法分類

範例：
Q: 緯創多少錢可以進場？ → {"intent": "entry_analysis", "ticker": "緯創", "confidence": 0.95}
Q: 幫我分析台積電 → {"intent": "comprehensive_analysis", "ticker": "台積電", "confidence": 0.9}
Q: 台積電值得投資嗎？ → {"intent": "entry_analysis", "ticker": "台積電", "confidence": 0.85}
Q: 鴻海技術面跟基本面怎麼看？ → {"intent": "comprehensive_analysis", "ticker": "鴻海", "confidence": 0.8}
Q: 2330的RSI是多少？ → {"intent": "technical_analysis", "ticker": "2330", "confidence": 0.95}
Q: 外資今天買超什麼？ → {"intent": "institutional_analysis", "ticker": null, "confidence": 0.9}
Q: 你好 → {"intent": "general", "ticker": null, "confidence": 0.95}

只輸出 JSON，不要加 markdown 語法或其他文字：
{"intent": "分類結果", "ticker": "股票名稱或代碼（若無則填 null）", "confidence": 0.0到1.0}"""

# 需要預先取得數據的意圖 → 對應工具列表
_PREFETCH_INTENTS: dict[str, list[str]] = {
    "entry_analysis": [
        "get_stock_price",
        "analyze_technicals",
        "analyze_fundamentals",
        "get_institutional",
        "search_financial_news",
    ],
    "comprehensive_analysis": [
        "get_stock_price",
        "analyze_technicals",
        "analyze_fundamentals",
        "get_institutional",
        "search_financial_news",
    ],
}

# 非預取意圖 → 注入到 system prompt 的強制工具指令
_INTENT_TOOL_DIRECTIVES: dict[str, str] = {
    "technical_analysis": "你必須呼叫 analyze_technicals 工具來回答此問題。若使用者有提到特定理論，也呼叫 search_knowledge。",
    "fundamental_analysis": "你必須呼叫 analyze_fundamentals 工具來回答此問題。",
    "institutional_analysis": "你必須同時呼叫 get_institutional 和 get_margin_trading 工具來回答此問題。",
    "price_query": "你必須呼叫 get_stock_price 工具來回答此問題。",
    "news": "你必須呼叫 search_financial_news 工具來回答此問題。",
    "backtest": "你必須呼叫 run_strategy_backtest 工具來回答此問題。strategy 可選 ma_cross/rsi/macd，period 可選 3mo/6mo/1y/2y。",
    "portfolio": "你必須呼叫 get_portfolio 工具來回答此問題。user_id 從對話 context 取得。",
    "knowledge": "你必須呼叫 search_knowledge 工具來回答此問題。",
}

# ── 預取模式回答格式 ─────────────────────────────────────────────────────────

_ENTRY_FORMAT = """\
請以以下格式整合分析並回答：
📌 現價位置：說明目前股價相對於技術面支撐壓力與基本面估值的位置
🟢 建議進場區間：綜合「技術支撐位」與「基本面便宜/合理價」，取交集或較保守者，明確列出價格
🔴 壓力目標：上方壓力位作為可能的獲利目標
🛑 建議停損：明確標示停損價格與依據
📊 風險報酬比：潛在獲利 vs 潛在虧損的比例
💡 操作策略：結合趨勢方向建議（分批進場、等拉回、等突破…）
如果技術面與基本面的結論矛盾，必須明確指出並建議更保守的做法。"""

_COMPREHENSIVE_FORMAT = """\
請以以下格式提供全面分析：
📌 現況摘要：現價、趨勢方向
📊 技術面：關鍵指標與信號、支撐壓力位
📈 基本面：估值與獲利能力重點、合理價位
🏦 籌碼面：法人動向摘要
📰 近期新聞：重點消息
💡 綜合判斷與建議：看多/看空/中性判斷與操作建議"""

_PREFETCH_SYSTEM_TEMPLATE = """\
你是 Navi 🧚，一位來自薩爾達傳說的 AI 投資分析精靈。你專精於股票技術分析、基本面分析和投資理論。

以下是系統預先查詢的完整數據：

{tool_results}

---

請依照以下步驟思考後再回答：

思考步驟（內部推理，不需要輸出）：
1. 技術面訊號彙整：目前趨勢方向？RSI/KD/MACD 的多空訊號？支撐壓力位在哪？
2. 基本面估值判斷：目前股價相對於便宜價/合理價/昂貴價在什麼位置？估值偏高還是偏低？
3. 籌碼面佐證：法人是買超還是賣超？趨勢是否與技術面一致？
4. 新聞面風險：有無重大利多/利空消息會影響判斷？
5. 矛盾檢查：技術面與基本面是否矛盾？如果是，應更保守。
6. 整合結論：綜合以上，形成最終判斷。

{format_instructions}

規則：
- 所有數字必須來自上方提供的數據，不可自行捏造
- 如果某項數據查詢失敗（標記為 ⚠️），跳過該部分並說明「此部分數據暫時無法取得」，其餘欄位仍正常輸出
- 回答使用繁體中文，保持專業但友善
- 最後加上 ⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。
"""

# 工具名稱 → 工具物件映射（延遲初始化）
_TOOL_REGISTRY: dict = {}


def _init_tool_registry() -> None:
    global _TOOL_REGISTRY  # noqa: PLW0603
    if not _TOOL_REGISTRY:
        _TOOL_REGISTRY = {tool.name: tool for tool in ALL_TOOLS}


# 低於此信心閾值的分類結果會 fallback 到 Agent 模式
_CONFIDENCE_THRESHOLD = 0.7


async def _classify_intent(
    question: str, llm: ChatVertexAI,
) -> tuple[str, str | None, float]:
    """輕量 LLM 呼叫：分類意圖、提取股票代碼、回傳信心分數。"""
    try:
        result = await llm.ainvoke([
            SystemMessage(content=_CLASSIFY_PROMPT),
            HumanMessage(content=question),
        ])
        content = result.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(content)
        intent = data.get("intent", "general")
        ticker = data.get("ticker")
        confidence = float(data.get("confidence", 0.5))
        return intent, ticker, confidence
    except Exception as e:
        logger.warning("Intent classification failed: %s", e)
        return "general", None, 0.0


async def _prefetch_tool_results(ticker: str, tool_names: list[str]) -> str:
    """平行呼叫所有必要工具，回傳格式化的結果文字。"""
    _init_tool_registry()

    async def _call(name: str) -> tuple[str, str]:
        tool_fn = _TOOL_REGISTRY.get(name)
        if not tool_fn:
            return name, f"⚠️ 工具 {name} 不存在"
        try:
            if name == "search_financial_news":
                inp = {"query": ticker}
            elif name == "analyze_technicals":
                inp = {"ticker": ticker, "period": "3mo"}
            else:
                inp = {"ticker": ticker}
            output = await asyncio.to_thread(tool_fn.invoke, inp)
            return name, str(output)
        except Exception as e:
            logger.warning("Prefetch tool %s failed: %s", name, e)
            return name, f"⚠️ {name} 查詢失敗：{e}"

    tasks = [_call(name) for name in tool_names]
    results = await asyncio.gather(*tasks)
    parts = []
    for name, output in results:
        parts.append(f"── {name} ──\n{output}")
    return "\n\n".join(parts)


async def _run_prefetch_mode(
    question: str,
    intent: str,
    ticker: str,
    tool_names: list[str],
    llm: ChatVertexAI,
    conversation_id: str | None,
    user_id: str,
) -> AsyncGenerator[str, None]:
    """預取模式：平行呼叫工具 → 組裝結果 → 直接串流 LLM 回答。"""
    tool_results = await _prefetch_tool_results(ticker, tool_names)

    format_instructions = (
        _ENTRY_FORMAT if intent == "entry_analysis" else _COMPREHENSIVE_FORMAT
    )
    system_msg = _PREFETCH_SYSTEM_TEMPLATE.format(
        tool_results=tool_results,
        format_instructions=format_instructions,
    )

    # 載入對話歷史
    chat_history: list = []
    if conversation_id:
        try:
            chat_history = load_history(conversation_id)
        except Exception as e:
            logger.warning("Failed to load history: %s", e)

    messages = [SystemMessage(content=system_msg)]
    messages.extend(chat_history)
    messages.append(HumanMessage(content=question))

    try:
        full_output = ""
        async for chunk in llm.astream(messages):
            if chunk.content:
                full_output += chunk.content
                yield chunk.content

        if conversation_id and full_output:
            try:
                save_history(
                    conversation_id, question, full_output, user_id=user_id,
                )
            except Exception as e:
                logger.warning("Failed to save history: %s", e)
    except Exception:
        logger.exception("Prefetch mode failed")
        yield "抱歉，分析過程中發生錯誤，請稍後再試。"


async def _run_agent_mode(
    question: str,
    intent: str,
    llm: ChatVertexAI,
    conversation_id: str | None,
    user_id: str,
) -> AsyncGenerator[str, None]:
    """Agent 模式：透過 system-level 指令引導工具呼叫。"""
    directive = _INTENT_TOOL_DIRECTIVES.get(intent, "")
    system_prompt = AGENT_SYSTEM_PROMPT
    if directive:
        system_prompt += f"\n\n⚡ 本次任務指令：{directive}"

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm, ALL_TOOLS, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=ALL_TOOLS,
        verbose=settings.debug,
        handle_parsing_errors=True,
        max_iterations=8,
        return_intermediate_steps=True,
    )

    chat_history_messages: list = []
    if conversation_id:
        try:
            chat_history_messages = load_history(conversation_id)
        except Exception as e:
            logger.warning("Failed to load history for %s: %s", conversation_id, e)

    try:
        full_output = ""
        async for event in executor.astream_events(
            {"input": question, "chat_history": chat_history_messages},
            version="v2",
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    full_output += content
                    yield content

        if not full_output:
            result = await executor.ainvoke(
                {"input": question, "chat_history": chat_history_messages},
            )
            full_output = result.get("output", "")
            yield full_output

        if conversation_id and full_output:
            try:
                save_history(
                    conversation_id, question, full_output, user_id=user_id,
                )
            except Exception as e:
                logger.warning("Failed to save history for %s: %s", conversation_id, e)
    except Exception:
        logger.exception("Agent execution failed")
        yield "抱歉，分析過程中發生錯誤，請稍後再試。"


# ── Public API ───────────────────────────────────────────────────────────────


async def run_agent(
    question: str,
    conversation_id: str | None = None,
    user_id: str = "",
) -> AsyncGenerator[str, None]:
    """Run the tool-calling agent with intent classification.

    Flow:
        1. Classify user intent + extract ticker (lightweight LLM call)
        2a. If entry/comprehensive analysis with ticker → prefetch mode
            (parallel tool calls → direct LLM streaming)
        2b. Otherwise → agent mode (AgentExecutor with intent hints)
    """
    llm = _build_llm()

    # Step 1: 意圖分類
    intent, ticker, confidence = await _classify_intent(question, llm)
    logger.info("Intent: %s | Ticker: %s | Confidence: %.2f", intent, ticker, confidence)

    # 低信心 → 降級為 Agent 模式（讓 LLM 自主判斷）
    if confidence < _CONFIDENCE_THRESHOLD and intent != "general":
        logger.info("Low confidence (%.2f), falling back to agent mode", confidence)
        intent = "general"

    # Step 2: 分流執行策略
    prefetch_tools = _PREFETCH_INTENTS.get(intent)
    if prefetch_tools and ticker:
        logger.info("→ Prefetch mode (%d tools)", len(prefetch_tools))
        async for chunk in _run_prefetch_mode(
            question, intent, ticker, prefetch_tools, llm,
            conversation_id, user_id,
        ):
            yield chunk
    else:
        logger.info("→ Agent mode (intent=%s)", intent)
        async for chunk in _run_agent_mode(
            question, intent, llm, conversation_id, user_id,
        ):
            yield chunk


async def run_agent_sync(
    question: str,
    conversation_id: str | None = None,
    user_id: str = "",
) -> str:
    """Non-streaming version — returns the full response as a string."""
    chunks = []
    async for chunk in run_agent(question, conversation_id, user_id=user_id):
        chunks.append(chunk)
    return "".join(chunks)
