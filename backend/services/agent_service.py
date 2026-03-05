"""Agent Service — LangChain Tool-calling Agent backed by Gemini."""

import logging
from collections.abc import AsyncGenerator

import vertexai
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.chat_history import InMemoryChatMessageHistory
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

你擁有以下工具：
1. get_stock_price — 查詢即時股價
2. analyze_technicals — 技術指標分析（MA, RSI, MACD, KD, 布林通道）
3. analyze_fundamentals — 基本面財報分析（PE, ROE, EPS…）
4. search_knowledge — 搜尋投資知識庫（理論、方法論）
5. get_institutional — 三大法人買賣超數據（外資、投信、自營商）
6. get_margin_trading — 融資融券餘額與使用率
7. search_financial_news — 搜尋最新財經新聞
8. get_portfolio — 查詢使用者投資組合（持股、市值、損益）

規則：
- 使用者問到股價/漲跌時 → 呼叫 get_stock_price
- 使用者問到技術面/走勢 → 呼叫 analyze_technicals，並用 search_knowledge 搜尋相關理論
- 使用者問到基本面/財報 → 呼叫 analyze_fundamentals
- 使用者問到投資理論/方法 → 呼叫 search_knowledge
- 使用者問到籌碼面/法人動向/外資 → 呼叫 get_institutional 和 get_margin_trading
- 使用者問到新聞/市場消息 → 呼叫 search_financial_news
- 使用者問到「我的持股」「投資組合」「我的股票」→ 呼叫 get_portfolio，user_id 從對話 context 取得
- 綜合分析請求 → 同時呼叫多個工具，提供全面分析
- 所有數字必須來自工具回傳的數據，不可自行捏造
- 回答使用繁體中文，保持專業但友善
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


# ── Public API ───────────────────────────────────────────────────────────────


async def run_agent(
    question: str,
    conversation_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Run the tool-calling agent and stream the response.

    Args:
        question: User's natural language question.
        conversation_id: Optional conversation ID for multi-turn memory.

    Yields:
        Text chunks from the agent's response.
    """
    llm = _build_llm()
    prompt = _build_prompt()
    agent = create_tool_calling_agent(llm, ALL_TOOLS, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=ALL_TOOLS,
        verbose=settings.debug,
        handle_parsing_errors=True,
        max_iterations=8,
        return_intermediate_steps=True,
    )

    # Load conversation history from Firestore (if available)
    chat_history_messages = []
    if conversation_id:
        try:
            chat_history_messages = load_history(conversation_id)
        except Exception as e:
            logger.warning("Failed to load history for %s: %s", conversation_id, e)

    try:
        # Use astream_events for true streaming
        full_output = ""
        async for event in executor.astream_events(
            {"input": question, "chat_history": chat_history_messages},
            version="v2",
        ):
            kind = event["event"]
            # Stream tokens from the final LLM call (not tool calls)
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    full_output += content
                    yield content

        # If no streaming output was captured (fallback)
        if not full_output:
            result = await executor.ainvoke(
                {"input": question, "chat_history": chat_history_messages},
            )
            full_output = result.get("output", "")
            yield full_output

        # Persist conversation to Firestore
        if conversation_id and full_output:
            try:
                save_history(conversation_id, question, full_output)
            except Exception as e:
                logger.warning("Failed to save history for %s: %s", conversation_id, e)

    except Exception:
        logger.exception("Agent execution failed")
        yield "抱歉，分析過程中發生錯誤，請稍後再試。"


async def run_agent_sync(
    question: str,
    conversation_id: str | None = None,
) -> str:
    """Non-streaming version — returns the full response as a string."""
    chunks = []
    async for chunk in run_agent(question, conversation_id):
        chunks.append(chunk)
    return "".join(chunks)
