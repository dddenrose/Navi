"""Agent Service — LangGraph ReAct Agent backed by Gemini.

Refactored from AgentExecutor to LangGraph for better state management,
and from LLM-based intent classification to rule-based for lower latency.
"""

import asyncio
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any, Literal, TypedDict

import vertexai
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_google_vertexai import ChatVertexAI
from langgraph.prebuilt import create_react_agent  # pyright: ignore[reportDeprecated]

from config import settings
from services.conversation_service import (
    load_history,
    save_history,
)
from tools import ALL_TOOLS

logger = logging.getLogger(__name__)

# ── Thinking Event Types ─────────────────────────────────────────────────────


class IntentEvent(TypedDict):
    type: Literal["intent"]
    intent: str
    ticker: str | None
    confidence: float


class ToolStartEvent(TypedDict):
    type: Literal["tool_start"]
    tool: str
    input: dict[str, Any]


class ToolEndEvent(TypedDict):
    type: Literal["tool_end"]
    tool: str


ThinkingEvent = IntentEvent | ToolStartEvent | ToolEndEvent
StreamChunk = str | ThinkingEvent


# ── Prompt ───────────────────────────────────────────────────────────────────

AGENT_SYSTEM_PROMPT = """\
你是 Navi 🧚，一位來自薩爾達傳說的 AI 投資分析精靈。
你專精於股票技術分析、基本面分析和投資理論。
回答使用繁體中文，保持專業但友善。

═══ 核心規則 ═══

1. 根據使用者的問題，主動呼叫對應的工具取得數據。
2. 所有數字必須來自工具回傳的數據，絕對不可自行編造數據或價格。
3. 工具回傳錯誤時，如實告知使用者「該數據暫時無法取得」，並基於已有數據繼續分析。
4. 每次回覆最後加上 ⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。

═══ 你不該做的事 ═══

- 不可保證任何投資獲利或承諾報酬率
- 不可在缺乏數據支撐的情況下推薦具體進出場時機
- 不可回答非投資相關的問題（禮貌拒絕並引導回投資話題）
- 不可忽略風險提示，任何看多建議都必須附帶停損或風險說明
- 當數據不足以做出判斷時，明確說「目前數據不足，建議...」而非硬給結論

═══ 思考步驟（先推理、再回覆）═══

分析股票前，在內部依序思考：
1. 用戶真正想知道什麼？需要呼叫哪些工具？
2. 工具回傳的數據有哪些關鍵訊號？
3. 多個面向的訊號是否一致？若矛盾，應取較保守的結論。
4. 形成結論，附帶風險提示。

═══ 工具使用指引 ═══

- 技術面問題 → analyze_technicals
- 基本面問題 → analyze_fundamentals
- 股價查詢 → get_stock_price
- 法人/籌碼 → 同時呼叫 get_institutional 和 get_margin_trading
- 新聞動態 → search_financial_news
- 策略回測 → run_strategy_backtest（strategy: ma_cross/rsi/macd，period: 3mo/6mo/1y/2y）
- 投資理論 → search_knowledge
- 投資組合 → get_portfolio（user_id 使用系統上下文提供的值）

═══ 範例對話 ═══

【範例 1：單一指標查詢】
使用者：台積電的 RSI 是多少？
助手行動：呼叫 analyze_technicals(ticker="台積電", period="3mo")
助手回覆：
📊 台積電 技術面快報
根據技術指標數據，台積電目前：
• RSI(14) = 58.3，處於中性偏多區間（50-70）
• 未進入超買（>70）或超賣（<30）區域

💡 建議：RSI 目前中性，建議搭配其他指標（如 MACD、均線趨勢）做進一步確認。
⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。

【範例 2：進場評估】
使用者：鴻海值得買嗎？
助手行動：依序呼叫 get_stock_price、analyze_technicals、analyze_fundamentals、get_institutional、search_financial_news
助手回覆：
📌 現價位置：鴻海目前股價 178 元，位於 MA20（175）上方，技術面偏多。
📊 技術面：RSI(14)=62 中性偏多，MACD 金叉，均線多頭排列。支撐位：S1=172（MA20）、S2=165（MA60）。壓力位：R1=185。
📈 基本面：PE(TTM)=12.5，低於歷史均值。ROE=8.2%。合理價估算：便宜價 155 / 合理價 175 / 昂貴價 195。
🏦 籌碼面：外資連3日買超，投信小幅賣超。
📰 近期新聞：AI 伺服器訂單利多。
💡 綜合判斷：技術面與基本面訊號一致偏多，但股價已接近合理價上緣。
🟢 建議進場區間：172-175（拉回至 MA20 / 合理價附近）
🛑 建議停損：165 以下（跌破 MA60）
📊 風險報酬比：潛在獲利 ~5.6% / 潛在虧損 ~3.9%，約 1.4:1
⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。

【範例 3：回測】
使用者：台積電用 RSI 策略回測
助手行動：呼叫 run_strategy_backtest(ticker="台積電", strategy="rsi", period="1y")
助手回覆：
📊 回測結果解讀：RSI 策略 × 台積電（1 年）

績效數據：（引用工具回傳的實際數字）
• 總報酬率 / 年化報酬 / 最大回撤 / 夏普比率 / 勝率

策略評估：
✅ 優點：…
⚠️ 缺點：…
💡 改善建議：可考慮調整 RSI 閾值或結合其他指標。
⚠️ 免責聲明：回測績效不代表未來表現，所有分析僅供學習與研究用途，不構成投資建議。
"""

# ── Intent-specific output format instructions for Agent mode ────────────────

_AGENT_FORMAT_INSTRUCTIONS: dict[str, str] = {
    "technical_analysis": """\
回覆格式：
📊 {股票} 技術面分析
• 列出關鍵指標數值（均線、RSI、MACD、KD、布林通道）
• 支撐位 / 壓力位
• 綜合判斷：偏多/偏空/中性，附帶依據""",

    "fundamental_analysis": """\
回覆格式：
📈 {股票} 基本面分析
• 估值指標：PE / PB / PS
• 獲利能力：ROE / ROA / 淨利率
• 成長性：營收成長 / 獲利成長
• 合理價位估算（便宜價/合理價/昂貴價）
• 結論：估值偏高/合理/偏低""",

    "institutional_analysis": """\
回覆格式：
🏦 {股票} 籌碼面分析
• 三大法人近期買賣超趨勢
• 融資融券變化（如有查詢）
• 籌碼面結論""",

    "news": """\
回覆格式：
📰 相關新聞彙整
• 列出重點新聞
• 分析對股價可能的影響（利多/利空/中性）""",

    "backtest": """\
回覆格式：
📊 回測結果解讀
• 績效數據摘要（報酬率、夏普比率、最大回撤、勝率）
• ✅ 策略優點
• ⚠️ 策略缺點
• 💡 改善建議
• 與大盤 Buy & Hold 比較""",

    "knowledge": """\
回覆格式：
📚 知識回覆
• 清楚解釋概念
• 搭配實際應用場景說明
• 如有相關指標，說明判讀方式""",

    "portfolio": """\
回覆格式：
💼 投資組合分析
• 總覽：總市值、總損益
• 個股表現摘要
• 集中度風險提示（如有）
• 建議關注事項""",

    "price_query": """\
回覆格式：
📌 {股票} 即時報價
• 現價、漲跌幅、成交量
• 簡短技術位置描述（如在均線上方/下方）""",
}


def _build_llm() -> ChatVertexAI:
    vertexai.init(project=settings.google_cloud_project)
    return ChatVertexAI(
        model_name=settings.gemini_model_name,
        temperature=0.3,
        project=settings.google_cloud_project,
    )


# ── Rule-based Intent Classification ─────────────────────────────────────────

# Regex patterns for intent classification (compiled once)
_INTENT_PATTERNS: list[tuple[str, re.Pattern, float]] = [
    # entry_analysis: 進場、買入、目標價
    ("entry_analysis", re.compile(
        r"(進場|可以買|能買|適合買|值得買|值得投資|適不適合|目標價|多少錢.*(買|進)|"
        r"該不該買|何時.*(買|進場)|買入|建議.*(買|進場)|可不可以買|entry)",
        re.IGNORECASE,
    ), 0.9),
    # backtest: 回測、策略
    ("backtest", re.compile(
        r"(回測|backt|策略績效|模擬交易|歷史績效|策略.*表現)",
        re.IGNORECASE,
    ), 0.95),
    # portfolio: 持股、投資組合
    ("portfolio", re.compile(
        r"(我的持股|投資組合|portfolio|我的股票|持倉|我買了|我有哪些股)",
        re.IGNORECASE,
    ), 0.95),
    # knowledge: 投資理論、教學
    ("knowledge", re.compile(
        r"(什麼是|教我|解釋.*(?:指標|理論|策略)|如何.*(?:分析|計算)|"
        r"怎麼看.*(?:技術|基本|財報)|原理|學習|入門|新手)",
        re.IGNORECASE,
    ), 0.85),
    # news: 新聞、消息
    ("news", re.compile(
        r"(新聞|消息|市場動態|最近.*(?:發生|怎麼了)|news|利多|利空|重大.*事件)",
        re.IGNORECASE,
    ), 0.9),
    # institutional_analysis: 法人、籌碼
    ("institutional_analysis", re.compile(
        r"(法人|外資|投信|自營商|籌碼|買超|賣超|融資|融券|三大法人|主力)",
        re.IGNORECASE,
    ), 0.9),
    # technical_analysis: 技術面
    ("technical_analysis", re.compile(
        r"(技術[面指]|RSI|MACD|KD|均線|MA\d|布林|支撐|壓力|走勢|K線|趨勢|"
        r"黃金交叉|死亡交叉|超買|超賣|乖離|波段|型態)",
        re.IGNORECASE,
    ), 0.9),
    # fundamental_analysis: 基本面
    ("fundamental_analysis", re.compile(
        r"(基本面|財報|EPS|PE|PB|ROE|本益比|殖利率|營收|毛利|淨利|股利|配息|估值)",
        re.IGNORECASE,
    ), 0.9),
    # price_query: 股價查詢
    ("price_query", re.compile(
        r"(股價|現在.*多少錢|目前.*(?:價格|價位)|(?:漲|跌)了?多少|收盤|開盤|成交量|市值)",
        re.IGNORECASE,
    ), 0.9),
    # comprehensive_analysis: 分析（廣泛）
    ("comprehensive_analysis", re.compile(
        r"((?:分析|怎麼樣|如何|怎樣|看法|看好|看壞|前景|展望).{0,6}$|"
        r"^(?:幫我|請|麻煩)?(?:分析|看看|評估))",
        re.IGNORECASE,
    ), 0.85),
]

# Ticker extraction pattern:
# Non-ticker uppercase words to skip
_NON_TICKER_WORDS = frozenset({
    "RSI", "MACD", "EPS", "PE", "PB", "ROE", "ROA", "MA", "KD",
    "ETF", "IPO", "AI", "BB", "ATR", "SMA", "EMA", "DCF", "DDM",
    "API", "SSE", "FAQ", "URL", "PDF", "CSV",
})

# Common greetings and general phrases
_GENERAL_PATTERN = re.compile(
    r"^(你好|嗨|hi|hello|hey|哈囉|安安|謝謝|thank|掰掰|bye|再見|早安|晚安|午安|"
    r"你是誰|自我介紹|help|幫助|使用方法|功能|你會什麼).{0,10}$",
    re.IGNORECASE,
)


def _extract_ticker(question: str) -> str | None:
    """Extract stock ticker or company name from the question.

    Uses multiple targeted patterns instead of a single greedy regex.
    """
    q = question.strip()

    # 1. Numeric TW stock code: 2330, 2330.TW, 2330.TWO
    m = re.search(r"(\d{4,6}(?:\.(?:TW|TWO))?)(?!\d)", q)
    if m:
        return m.group(1)

    # 2. US ticker symbol: AAPL, TSMC (uppercase 1-5 chars)
    for m in re.finditer(r"\b([A-Z]{1,5})\b", q):
        if m.group(1) not in _NON_TICKER_WORDS:
            return m.group(1)

    # 3. Chinese company name — multiple targeted patterns

    # a) After action verbs at the end: "分析鴻海", "幫我分析台積電"
    m = re.search(
        r"(?:(?:幫我|請|麻煩)\s*)?(?:分析|看看|查[詢看]?|評估|了解)\s*([一-龥]{2,5})\s*$",
        q,
    )
    if m:
        return m.group(1)

    # Words that appear at sentence start but are NOT company names
    _non_company = {
        "最近", "目前", "現在", "今天", "昨天", "什麼", "怎麼", "如何", "為什",
        "哪些", "哪個", "這個", "那個", "那些", "請問", "幫我", "麻煩", "可以",
        "能不", "應該", "是否", "我的", "你的", "不是",
    }

    # b) Company name at start of sentence before query keywords:
    #    "台積電可以買嗎", "鴻海怎麼樣", "台積電均線交叉"
    m = re.match(
        r"([一-龥]{2,5}?)"
        r"(?=的|可以|能不能|適合|值得|怎[麼樣]|如何|目前|股價|走勢|均線|"
        r"技術|基本|財報|營收|法人|外資|三大|新聞|消息|回測|策略)",
        q,
    )
    if m and len(m.group(1)) >= 2 and m.group(1)[:2] not in _non_company:
        return m.group(1)

    # c) Before technical indicators: "台積電RSI", "鴻海MACD"
    m = re.search(r"([一-龥]{2,5})\s*(?:RSI|MACD|KD|EPS|PE|PB|ROE)", q)
    if m:
        return m.group(1)

    return None


def _classify_intent(question: str) -> tuple[str, str | None, float]:
    """Rule-based intent classification with regex patterns.

    Returns:
        (intent, ticker_or_name, confidence)
    """
    q = question.strip()

    # General / greeting detection
    if _GENERAL_PATTERN.match(q):
        return "general", None, 0.95

    # Extract ticker/stock name
    ticker = _extract_ticker(q)

    # Match intent patterns (first match wins — patterns ordered by specificity)
    for intent, pattern, confidence in _INTENT_PATTERNS:
        if pattern.search(q):
            return intent, ticker, confidence

    # Fallback: if we found a ticker but no specific intent → comprehensive
    if ticker:
        return "comprehensive_analysis", ticker, 0.75

    return "general", None, 0.8


# ── Prefetch Configuration ───────────────────────────────────────────────────

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
- 不可保證任何投資獲利或承諾報酬率
- 任何看多建議都必須附帶停損或風險說明
- 回答使用繁體中文，保持專業但友善
- 最後加上 ⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。
"""

# ── Tool Registry ────────────────────────────────────────────────────────────

_TOOL_REGISTRY: dict = {}


def _init_tool_registry() -> None:
    global _TOOL_REGISTRY  # noqa: PLW0603
    if not _TOOL_REGISTRY:
        _TOOL_REGISTRY = {tool.name: tool for tool in ALL_TOOLS}


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


# ── Prefetch Mode ────────────────────────────────────────────────────────────


async def _run_prefetch_mode(
    question: str,
    intent: str,
    ticker: str,
    tool_names: list[str],
    llm: ChatVertexAI,
    conversation_id: str | None,
    user_id: str,
) -> AsyncGenerator[StreamChunk, None]:
    """預取模式：平行呼叫工具 → 組裝結果 → 直接串流 LLM 回答。"""
    for name in tool_names:
        yield ToolStartEvent(type="tool_start", tool=name, input={"ticker": ticker})

    tool_results = await _prefetch_tool_results(ticker, tool_names)

    for name in tool_names:
        yield ToolEndEvent(type="tool_end", tool=name)

    format_instructions = (
        _ENTRY_FORMAT if intent == "entry_analysis" else _COMPREHENSIVE_FORMAT
    )
    system_msg = _PREFETCH_SYSTEM_TEMPLATE.format(
        tool_results=tool_results,
        format_instructions=format_instructions,
    )

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


# ── LangGraph Agent Mode ─────────────────────────────────────────────────────


def _build_agent_system_prompt(intent: str, user_id: str) -> str:
    """Build system prompt with intent-specific format and user context."""
    parts = [AGENT_SYSTEM_PROMPT]

    # Inject intent-specific output format
    fmt = _AGENT_FORMAT_INSTRUCTIONS.get(intent)
    if fmt:
        parts.append(f"\n═══ 本次回覆格式要求 ═══\n\n{fmt}")

    # Inject user context
    if user_id:
        parts.append(
            f"\n═══ 系統上下文 ═══\n"
            f"目前使用者 user_id = \"{user_id}\"\n"
            f"呼叫 get_portfolio 時，user_id 參數請使用此值。"
        )

    return "\n".join(parts)


async def _run_agent_mode(
    question: str,
    intent: str,
    llm: ChatVertexAI,
    conversation_id: str | None,
    user_id: str,
) -> AsyncGenerator[StreamChunk, None]:
    """LangGraph ReAct Agent 模式：自主決策工具呼叫。"""
    system_prompt = _build_agent_system_prompt(intent, user_id)

    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=system_prompt,
    )

    chat_history_messages: list = []
    if conversation_id:
        try:
            chat_history_messages = load_history(conversation_id)
        except Exception as e:
            logger.warning("Failed to load history for %s: %s", conversation_id, e)

    input_messages = list(chat_history_messages)
    input_messages.append(HumanMessage(content=question))

    try:
        full_output = ""
        active_tools: set[str] = set()

        async for event in agent.astream_events(
            {"messages": input_messages},
            version="v2",
        ):
            kind = event["event"]
            if kind == "on_tool_start":
                tool_name = event["name"]
                active_tools.add(tool_name)
                yield ToolStartEvent(
                    type="tool_start",
                    tool=tool_name,
                    input=event["data"].get("input", {}),
                )
            elif kind == "on_tool_end":
                tool_name = event["name"]
                active_tools.discard(tool_name)
                yield ToolEndEvent(type="tool_end", tool=tool_name)
            elif kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content and not active_tools:
                    full_output += content
                    yield content

        if not full_output:
            result = await agent.ainvoke({"messages": input_messages})
            last_msg = result["messages"][-1]
            if isinstance(last_msg, AIMessage) and last_msg.content:
                full_output = last_msg.content
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
) -> AsyncGenerator[StreamChunk, None]:
    """Run the tool-calling agent with rule-based intent classification.

    Flow:
        1. Classify user intent + extract ticker (rule-based, zero latency)
        2a. If entry/comprehensive analysis with ticker → prefetch mode
            (parallel tool calls → direct LLM streaming)
        2b. Otherwise → LangGraph ReAct agent mode
    """
    llm = _build_llm()

    # Step 1: 規則式意圖分類（零延遲）
    intent, ticker, confidence = _classify_intent(question)
    logger.info("Intent: %s | Ticker: %s | Confidence: %.2f", intent, ticker, confidence)

    yield IntentEvent(type="intent", intent=intent, ticker=ticker, confidence=confidence)

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
    chunks: list[str] = []
    async for chunk in run_agent(question, conversation_id, user_id=user_id):
        if isinstance(chunk, str):
            chunks.append(chunk)
    return "".join(chunks)
