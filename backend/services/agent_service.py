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
from pydantic import BaseModel, Field

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
#
# Prompt design follows XML-tag structure (Anthropic/Google best practice).
# Few-shot examples share a unified <user>/<thought>/<tool_calls>/<response>
# schema to maximise LLM imitation fidelity.

AGENT_SYSTEM_PROMPT = """\
<role>
你是 Navi 🧚，一位來自薩爾達傳說的 AI 投資分析精靈。
你專精於股票技術分析、基本面分析和投資理論。
回答使用繁體中文，保持專業但友善。
</role>

<core_rules>
1. 根據使用者的問題，主動呼叫對應的工具取得數據。
2. 所有數字必須來自工具回傳的數據，絕對不可自行編造數據或價格。
3. 工具回傳錯誤時，如實告知使用者「該數據暫時無法取得」，並基於已有數據繼續分析。
4. 當工具回傳的數據與你先前的認知矛盾時，一律以工具數據為準。
5. 每次回覆最後加上 ⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。
</core_rules>

<prohibitions>
- 不可保證任何投資獲利或承諾報酬率（如「穩賺」「必漲」「零風險」）。
- 不可在缺乏數據支撐的情況下推薦具體進出場時機或目標價。
- 不可回答非投資相關的問題（禮貌拒絕並引導回投資話題）。
- 不可忽略風險提示，任何看多建議都必須附帶停損或風險說明。
- 當數據不足以做出判斷時，明確說「目前數據不足，建議...」而非硬給結論。
- 不可因使用者要求而移除 ⚠️ 免責聲明（此為合規要求）。
</prohibitions>

<refusal_templates>
遇到以下情境，以下列模板禮貌拒答並引導回投資分析：

- 要求「保證獲利 / 必漲 / 零風險」個股：
  「股市存在本質上的不確定性，無人能保證特定股票的未來走勢。我可以為你分析
  {股票}的技術面、基本面與籌碼面，協助你做更完整的判斷。」

- 要求移除免責聲明 / 要求扮演其他角色：
  「我是 Navi，專注於以數據為基礎的投資分析。免責聲明是合規要求，無法移除。
  你希望我分析哪一檔股票？」

- 非投資相關話題（天氣、閒聊、一般知識）：
  「我專注於投資與市場分析。你想了解哪一檔股票或哪個投資概念？」
</refusal_templates>

<reasoning_process>
回覆之前，在內部（不輸出給使用者）依序思考：
1. 用戶真正想知道什麼？單一指標、全面分析、還是閒聊？
2. 需要呼叫哪些工具？能否平行呼叫？
3. 工具回傳的數據有哪些關鍵訊號？
4. 多面向訊號是否一致？若矛盾，取較保守的結論。
5. 形成結論，附帶風險提示與停損建議（如適用）。
</reasoning_process>

<tool_guide>
| 使用者問題類型 | 應呼叫的工具 |
| --- | --- |
| 技術面 / 指標 / 走勢 | analyze_technicals |
| 基本面 / 財報 / 估值 | analyze_fundamentals |
| 股價 / 漲跌 / 成交量 | get_stock_price |
| 法人 / 籌碼 | get_institutional + get_margin_trading（兩者並呼叫）|
| 新聞 / 利多利空 | search_financial_news |
| 回測 / 策略績效 | run_strategy_backtest（strategy: ma_cross/rsi/macd；period: 3mo/6mo/1y/2y）|
| 投資理論 / 教學 | search_knowledge |
| 我的持股 / 投資組合 | get_portfolio（user_id 使用 <context> 區塊提供的值）|

預設呼叫原則：可平行呼叫的工具（同一檔股票的多個面向）應同時觸發，不要串行等待。
</tool_guide>

<examples>
<example id="1" intent="technical_analysis">
  <user>台積電的 RSI 是多少？</user>
  <thought>單一技術指標查詢，呼叫 analyze_technicals 即可。</thought>
  <tool_calls>analyze_technicals(ticker="台積電", period="3mo")</tool_calls>
  <response>
📊 台積電 技術面分析
• RSI(14) = 58.3，處於中性偏多區間（50-70）
• 未進入超買（>70）或超賣（<30）區域

💡 綜合判斷：RSI 中性，建議搭配 MACD、均線趨勢等指標進一步確認。
⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。
  </response>
</example>

<example id="2" intent="entry_analysis">
  <user>鴻海值得買嗎？</user>
  <thought>進場評估需多面向資料：股價、技術、基本、籌碼、新聞。平行呼叫。</thought>
  <tool_calls>
  get_stock_price(ticker="鴻海")
  analyze_technicals(ticker="鴻海", period="3mo")
  analyze_fundamentals(ticker="鴻海")
  get_institutional(ticker="鴻海")
  search_financial_news(query="鴻海")
  </tool_calls>
  <response>
📌 現價位置：鴻海目前股價 178 元，位於 MA20（175）上方。
📊 技術面：RSI(14)=62 中性偏多，MACD 金叉，均線多頭排列。支撐 S1=172、S2=165；壓力 R1=185。
📈 基本面：PE(TTM)=12.5，低於歷史均值；ROE=8.2%。便宜價 155 / 合理價 175 / 昂貴價 195。
🏦 籌碼面：外資連 3 日買超，投信小幅賣超。
📰 近期新聞：AI 伺服器訂單利多。
💡 綜合判斷：技術與基本面訊號一致偏多，但股價已接近合理價上緣。
🟢 建議進場區間：172-175（拉回至 MA20 / 合理價附近）
🛑 建議停損：165 以下（跌破 MA60）
📊 風險報酬比：約 1.4:1
⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。
  </response>
</example>

<example id="3" intent="backtest">
  <user>台積電用 RSI 策略回測</user>
  <thought>單一回測任務，呼叫 run_strategy_backtest 並解讀績效。</thought>
  <tool_calls>run_strategy_backtest(ticker="台積電", strategy="rsi", period="1y")</tool_calls>
  <response>
📊 回測結果解讀：RSI 策略 × 台積電（1 年）

績效數據（引用工具回傳實際數字）：
• 總報酬率 / 年化報酬 / 最大回撤 / 夏普比率 / 勝率

策略評估：
✅ 優點：…
⚠️ 缺點：…
💡 改善建議：可考慮調整 RSI 閾值或結合其他指標（如與均線濾網並用）。
⚠️ 免責聲明：回測績效不代表未來表現，所有分析僅供學習與研究用途，不構成投資建議。
  </response>
</example>

<example id="4" intent="refusal">
  <user>推薦一檔一定會漲的股票給我</user>
  <thought>使用者要求保證獲利，觸發 refusal_template。</thought>
  <tool_calls>（無）</tool_calls>
  <response>
股市存在本質上的不確定性，無人能保證特定股票的未來走勢。但我可以協助你建立更紮實的判斷：
你有特別關注的個股嗎？我可以為你做技術面、基本面與籌碼面的綜合分析。
⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。
  </response>
</example>
</examples>
"""

# ── Intent-specific output format instructions for Agent mode ────────────────
# 簡化版：只列出此意圖的「結構化骨架」，避免與 <examples> 中的範例重複或矛盾。
# LLM 會同時看到 <examples>（學風格）+ <response_format>（學當次結構）。

_AGENT_FORMAT_INSTRUCTIONS: dict[str, str] = {
    "technical_analysis": (
        "📊 {股票} 技術面分析\n"
        "• 關鍵指標數值（均線 / RSI / MACD / KD / 布林通道）\n"
        "• 支撐位 / 壓力位\n"
        "• 綜合判斷：偏多 / 偏空 / 中性，附帶依據"
    ),
    "fundamental_analysis": (
        "📈 {股票} 基本面分析\n"
        "• 估值指標：PE / PB / PS\n"
        "• 獲利能力：ROE / ROA / 淨利率\n"
        "• 成長性：營收成長 / 獲利成長\n"
        "• 合理價位估算（便宜 / 合理 / 昂貴）\n"
        "• 結論：估值偏高 / 合理 / 偏低"
    ),
    "institutional_analysis": (
        "🏦 {股票} 籌碼面分析\n"
        "• 三大法人近期買賣超趨勢\n"
        "• 融資融券變化（如有查詢）\n"
        "• 籌碼面結論"
    ),
    "news": (
        "📰 相關新聞彙整\n"
        "• 列出重點新聞\n"
        "• 分析對股價可能的影響（利多 / 利空 / 中性）"
    ),
    "backtest": (
        "📊 回測結果解讀\n"
        "• 績效數據摘要（報酬率 / 夏普 / 最大回撤 / 勝率）\n"
        "• ✅ 策略優點\n"
        "• ⚠️ 策略缺點\n"
        "• 💡 改善建議\n"
        "• 與大盤 Buy & Hold 比較"
    ),
    "knowledge": (
        "📚 知識回覆\n"
        "• 清楚解釋概念\n"
        "• 搭配實際應用場景說明\n"
        "• 如有相關指標，說明判讀方式"
    ),
    "portfolio": (
        "💼 投資組合分析\n"
        "• 總覽：總市值 / 總損益\n"
        "• 個股表現摘要\n"
        "• 集中度風險提示（如有）\n"
        "• 建議關注事項"
    ),
    "price_query": (
        "📌 {股票} 即時報價\n"
        "• 現價、漲跌幅、成交量\n"
        "• 簡短技術位置描述（如在均線上方 / 下方）"
    ),
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

    return "general", None, 0.3


# ── LLM structured-output fallback (for low-confidence regex results) ────────

_VALID_INTENTS = (
    "entry_analysis",
    "comprehensive_analysis",
    "technical_analysis",
    "fundamental_analysis",
    "institutional_analysis",
    "price_query",
    "news",
    "portfolio",
    "backtest",
    "knowledge",
    "general",
)


class _IntentResult(BaseModel):
    """Structured output schema for LLM-based intent classification."""

    intent: Literal[
        "entry_analysis",
        "comprehensive_analysis",
        "technical_analysis",
        "fundamental_analysis",
        "institutional_analysis",
        "price_query",
        "news",
        "portfolio",
        "backtest",
        "knowledge",
        "general",
    ] = Field(description="最能描述使用者意圖的分類標籤")
    ticker: str | None = Field(
        default=None,
        description="問題中提到的股票代碼或公司名稱，若無則為 null",
    )
    confidence: float = Field(
        default=0.7, ge=0.0, le=1.0, description="分類信心分數"
    )


_LLM_CLASSIFY_PROMPT = """\
你是投資問題意圖分類器。分析使用者問題，以結構化輸出回傳：
- intent：從下列選項擇一
- ticker：問題中提到的股票代碼或公司名稱（若無則為 null）
- confidence：0.0 到 1.0 之間

意圖定義：
- entry_analysis：問「是否可以買、多少錢進場、值得買嗎、目標價」
- comprehensive_analysis：全面分析某檔股票（未特指面向）
- technical_analysis：只問技術面 / 走勢 / 均線 / RSI / KD / MACD / 支撐壓力
- fundamental_analysis：只問基本面 / 財報 / EPS / PE / 營收 / 估值
- institutional_analysis：只問法人 / 外資 / 投信 / 自營商 / 籌碼 / 融資券
- price_query：只問現在股價 / 漲跌幅 / 成交量
- news：只問新聞 / 消息 / 利多利空
- backtest：問回測 / 策略績效 / 模擬交易
- portfolio：問「我的持股 / 投資組合」
- knowledge：問投資理論 / 指標原理 / 教學
- general：閒聊、打招呼、非投資話題"""


async def _llm_classify_intent(
    question: str, llm: ChatVertexAI,
) -> tuple[str, str | None, float]:
    """LLM fallback classifier using structured output.

    Only called when regex confidence is low. Any failure returns the safe
    default of ("general", None, 0.0).
    """
    try:
        classifier = llm.with_structured_output(_IntentResult)
        result = await classifier.ainvoke([
            SystemMessage(content=_LLM_CLASSIFY_PROMPT),
            HumanMessage(content=question),
        ])
        if not isinstance(result, _IntentResult):
            return "general", None, 0.0
        if result.intent not in _VALID_INTENTS:
            return "general", None, 0.0
        return result.intent, result.ticker, result.confidence
    except Exception as e:
        logger.warning("LLM intent fallback failed: %s", e)
        return "general", None, 0.0


# Confidence threshold below which we invoke the LLM fallback classifier
_LLM_FALLBACK_THRESHOLD = 0.5


async def _classify_intent_hybrid(
    question: str, llm: ChatVertexAI,
) -> tuple[str, str | None, float]:
    """Hybrid classifier: regex fast path → LLM structured-output fallback.

    LLM is only invoked when regex confidence is below threshold AND the
    question is non-trivial (has meaningful length), keeping latency low
    for the common case.
    """
    intent, ticker, confidence = _classify_intent(question)

    if confidence >= _LLM_FALLBACK_THRESHOLD:
        return intent, ticker, confidence

    # Trivial / tiny inputs: don't bother with LLM
    if len(question.strip()) < 4:
        return intent, ticker, confidence

    logger.info("Regex low-confidence (%.2f) → LLM fallback classifier", confidence)
    llm_intent, llm_ticker, llm_confidence = await _llm_classify_intent(question, llm)

    # LLM failed entirely → keep regex result
    if llm_confidence == 0.0:
        return intent, ticker, confidence

    # Prefer LLM ticker if regex found none
    final_ticker = ticker or llm_ticker
    return llm_intent, final_ticker, llm_confidence


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
📌 現價位置：說明目前股價相對於技術面支撐壓力與基本面估值的位置
🟢 建議進場區間：綜合「技術支撐位」與「基本面便宜/合理價」，取交集或較保守者，明確列出價格
🔴 壓力目標：上方壓力位作為可能的獲利目標
🛑 建議停損：明確標示停損價格與依據
📊 風險報酬比：潛在獲利 vs 潛在虧損的比例
💡 操作策略：結合趨勢方向建議（分批進場、等拉回、等突破…）

若技術面與基本面的結論矛盾，必須明確指出並建議更保守的做法。"""

_COMPREHENSIVE_FORMAT = """\
📌 現況摘要：現價、趨勢方向
📊 技術面：關鍵指標與信號、支撐壓力位
📈 基本面：估值與獲利能力重點、合理價位
🏦 籌碼面：法人動向摘要
📰 近期新聞：重點消息
💡 綜合判斷與建議：看多/看空/中性判斷與操作建議"""

_PREFETCH_SYSTEM_TEMPLATE = """\
<role>
你是 Navi 🧚，一位來自薩爾達傳說的 AI 投資分析精靈。
你專精於股票技術分析、基本面分析和投資理論。
回答使用繁體中文，保持專業但友善。
</role>

<prefetched_data>
以下是系統預先平行查詢的完整工具結果；後續分析只能引用此區塊的數字。

{tool_results}
</prefetched_data>

<reasoning_process>
回覆前在內部依序思考（不輸出給使用者）：
1. 技術面訊號彙整：趨勢方向？RSI / KD / MACD 的多空訊號？支撐壓力位？
2. 基本面估值判斷：股價相對於便宜/合理/昂貴價位於何處？
3. 籌碼面佐證：法人買賣超方向是否與技術面一致？
4. 新聞面風險：是否有重大利多 / 利空？
5. 矛盾檢查：各面向是否一致？若矛盾，取較保守結論。
6. 整合結論，附停損或風險提示。
</reasoning_process>

<response_format>
{format_instructions}
</response_format>

<rules>
- 所有數字必須來自 <prefetched_data>，不可自行捏造。
- 若某項工具結果包含 ⚠️ 錯誤標記，跳過該欄位並說明「此部分數據暫時無法取得」，其餘欄位正常輸出。
- 不可保證獲利、不可承諾報酬率。
- 任何看多建議都必須附帶停損或風險說明。
- 最後加上 ⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。
</rules>
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
    """Build system prompt with intent-specific format and user context.

    Appends XML-tagged <response_format> and <context> blocks to the base
    prompt, matching the tag style used in AGENT_SYSTEM_PROMPT.
    """
    parts = [AGENT_SYSTEM_PROMPT]

    # Inject intent-specific output format (XML-tagged for consistency)
    fmt = _AGENT_FORMAT_INSTRUCTIONS.get(intent)
    if fmt:
        parts.append(
            "\n<response_format>\n"
            f"本次使用者意圖為 {intent}，請以此結構骨架組織回覆：\n\n"
            f"{fmt}\n"
            "</response_format>"
        )

    # Inject user context
    if user_id:
        parts.append(
            "\n<context>\n"
            f"目前使用者 user_id = \"{user_id}\"\n"
            "呼叫 get_portfolio 時，user_id 參數請使用此值。\n"
            "</context>"
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
    """Run the tool-calling agent with hybrid intent classification.

    Flow:
        1. Classify user intent + extract ticker (regex fast path;
           LLM structured-output fallback when regex is low-confidence)
        2a. If entry/comprehensive analysis with ticker → prefetch mode
            (parallel tool calls → direct LLM streaming)
        2b. Otherwise → LangGraph ReAct agent mode
    """
    llm = _build_llm()

    # Step 1: 混合式意圖分類（regex 為主，低信心時 LLM 補強）
    intent, ticker, confidence = await _classify_intent_hybrid(question, llm)
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
