"""Agent Service — LangGraph ReAct Agent backed by Gemini.

Refactored from AgentExecutor to LangGraph for better state management,
and from LLM-based intent classification to rule-based for lower latency.
"""

import asyncio
import logging
import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
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


class Citation(TypedDict, total=False):
    id: int
    type: str  # tool category: price | technicals | fundamentals | institutional | margin | news | knowledge | backtest | portfolio
    source: str  # human-readable provider name
    title: str | None  # news article title / knowledge doc title
    url: str | None  # link to source (news article, TWSE page, etc.)
    detail: str | None  # e.g. "ticker=2330, period=3mo"
    note: str | None  # compliance / sanity note
    fetched_at: str  # ISO timestamp


class CitationsEvent(TypedDict):
    type: Literal["citations"]
    citations: list[Citation]


ThinkingEvent = IntentEvent | ToolStartEvent | ToolEndEvent | CitationsEvent
StreamChunk = str | ThinkingEvent


# ── Citation Source Registry ─────────────────────────────────────────────────

_TOOL_SOURCE_INFO: dict[str, dict[str, str | None]] = {
    "get_stock_price": {
        "type": "price",
        "source": "TWSE MIS 盤中即時報價 / TWSE / TPEx Open API（盤後收盤）/ Yahoo Finance（美股）",
        "url": None,
    },
    "analyze_technicals": {
        "type": "technicals",
        "source": "Yahoo Finance（歷史 K 線）",
        "url": None,
    },
    "analyze_fundamentals": {
        "type": "fundamentals",
        "source": "Yahoo Finance（公司財務）",
        "url": None,
    },
    "get_institutional": {
        "type": "institutional",
        "source": "台灣證券交易所（三大法人買賣超）",
        "url": "https://www.twse.com.tw/zh/trading/foreign/bfi82u.html",
    },
    "get_margin_trading": {
        "type": "margin",
        "source": "台灣證券交易所（融資融券）",
        "url": "https://www.twse.com.tw/zh/trading/exchange/MI_MARGN.html",
    },
    "search_knowledge": {
        "type": "knowledge",
        "source": "Navi 投資知識庫",
        "url": None,
    },
    "run_strategy_backtest": {
        "type": "backtest",
        "source": "Navi 內部回測（歷史資料來自 Yahoo Finance）",
        "url": None,
    },
    "get_portfolio": {
        "type": "portfolio",
        "source": "Navi 投資組合（使用者資料）",
        "url": None,
    },
    "search_financial_news": {
        "type": "news",
        "source": "Google News",
        "url": None,
    },
    "get_market_overview": {
        "type": "market_index",
        "source": "TWSE MIS 指數即時報價 / TWSE Open API（盤後）",
        "url": None,
    },
    "get_market_institutional_flows": {
        "type": "institutional",
        "source": "台灣證券交易所（三大法人買賣金額統計表 BFI82U）",
        "url": "https://www.twse.com.tw/zh/trading/foreign/bfi82u.html",
    },
    "get_market_futures_positions": {
        "type": "futures",
        "source": "臺灣期貨交易所（三大法人區分各期貨契約類別交易情形）",
        "url": "https://www.taifex.com.tw/cht/3/futContractsDate",
    },
}


# Regex to extract per-item news citations from search_financial_news output.
# Tool format (after refactor): "[1] Title（Source） — time\n   🔗 url"
# Title stops at first 「（」 or 「—」 so source/time are captured separately.
_NEWS_ITEM_RE = re.compile(
    r"\[(\d+)\]\s*([^（—\n]+?)\s*(?:（([^）\n]+)）)?\s*(?:—\s*([^\n]+?))?\s*\n\s*🔗\s*(\S+)"
)

# Regex for knowledge base items: "[1] Title（Category）"
_KB_ITEM_RE = re.compile(r"\[(\d+)\]\s*(.+?)（(.+?)）")


def _build_citations(tool_calls: list[dict]) -> list[Citation]:
    """Build citation list from collected tool call records.

    Args:
        tool_calls: list of {"name": str, "input": dict, "output": str}
    """
    citations: list[Citation] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    next_id = 1

    def _add(cit: Citation) -> None:
        nonlocal next_id
        key = (cit.get("type", ""), cit.get("title"), cit.get("url"))
        if key in seen:
            return
        seen.add(key)
        cit["id"] = next_id
        cit.setdefault("fetched_at", fetched_at)
        citations.append(cit)
        next_id += 1

    for call in tool_calls:
        name = call.get("name", "")
        tool_input = call.get("input") or {}
        output = call.get("output") or ""

        info = _TOOL_SOURCE_INFO.get(name)
        if info is None:
            continue

        ticker = tool_input.get("ticker") if isinstance(tool_input, dict) else None
        query = tool_input.get("query") if isinstance(tool_input, dict) else None
        detail_parts: list[str] = []
        if ticker:
            detail_parts.append(f"ticker={ticker}")
        if query and name != "search_financial_news":
            detail_parts.append(f"query={query}")
        detail = "、".join(detail_parts) if detail_parts else None

        # Per-item citations: news
        if name == "search_financial_news":
            matches = _NEWS_ITEM_RE.findall(output)
            if matches:
                for _idx, title, source, _time, url in matches:
                    _add(
                        Citation(
                            type="news",
                            source=(source.strip() if source else "Google News"),
                            title=title.strip(),
                            url=url.strip(),
                            detail=None,
                            note=None,
                            fetched_at=fetched_at,
                        )
                    )
                continue
            # Fallback: single generic citation
            _add(
                Citation(
                    type="news",
                    source="Google News",
                    title=None,
                    url=None,
                    detail=(f"query={query}" if query else None),
                    note=None,
                    fetched_at=fetched_at,
                )
            )
            continue

        # Per-item citations: knowledge base
        if name == "search_knowledge":
            matches = _KB_ITEM_RE.findall(output)
            if matches:
                for _idx, title, category in matches:
                    _add(
                        Citation(
                            type="knowledge",
                            source="Navi 投資知識庫",
                            title=f"{title.strip()}（{category.strip()}）",
                            url=None,
                            detail=None,
                            note=None,
                            fetched_at=fetched_at,
                        )
                    )
                continue
            _add(
                Citation(
                    type="knowledge",
                    source="Navi 投資知識庫",
                    title=None,
                    url=None,
                    detail=detail,
                    note=None,
                    fetched_at=fetched_at,
                )
            )
            continue

        # Generic single citation per tool
        note: str | None = None
        if name == "analyze_fundamentals":
            note = "Forward EPS / Forward PE 為第三方分析師共識估值，非 Navi 預測"
        elif name == "run_strategy_backtest":
            note = "回測績效不代表未來表現"

        _add(
            Citation(
                type=str(info["type"]),
                source=str(info["source"]),
                title=None,
                url=info["url"],
                detail=detail,
                note=note,
                fetched_at=fetched_at,
            )
        )

    return citations



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
5. **若你呼叫了 search_knowledge，必須在最終回應中實際引用其內容**（例如以
   「根據知識庫說明」、「概念上需注意」、「台股實務上」等用語帶出），
   不可只呼叫卻不使用；尤其是以下眼角必須依 KB 內容說明：
   • 技術指標超買（RSI > 80 / KD > 80）為「強多頭鈍化」與「反轉訊號」的區別
   • 三大法人買賣超數據單位為「張」（1 張 = 1000 股）
   • 「目標價」是估算值，非承諾
   • 用戶出現 FOMO / 鎖定 / 追高語言時的行為偏誤提醒
6. 每次回覆最後加上 ⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。
7. **不以投顧式「具體價位指令」回覆**：不說「建議 X-Y 元進場」「建議 Z 元停損」；
   改以「關鍵價位是 X，意義是…，不同投資週期（長 / 波段 / 短）用法不同」呼應，
   讓使用者根據自己的週期與風險承受度取用。
8. **個人化原則**：若訊息中包含「投資組合」資料或 get_portfolio 回傳顯示使用者
   已持有該檔或集中於同產業，必須以「你的部位狀況」段落進行集中度與加碼合理性提醒。
</core_rules>

<prohibitions>
- 不可保證任何投資獲利或承諾報酬率（如「穩賺」「必漲」「零風險」）。
- 不可在缺乏數據支撐的情況下推薦具體進出場時機或目標價。
- **不可使用「建議 X-Y 元進場」「建議 Z 元停損」「風險報酬比 N:M」這類投顧式句型**；
  需以「關鍵價位」「不同週期解讀」、「趨勢警戒位」等中性描述取代。
- 不可回答非投資相關的問題（禮貌拒絕並引導回投資話題）。
- 不可忽略風險提示，任何看多描述都必須附帶「趨勢警戒位」或風險說明。
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
5. 形成結論，附帶風險提示與「趨勢警戒位」等中性風險說明（不得給停損價位指令）。
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
| 投資理論 / 教學 / 名詞解釋 | search_knowledge |
| 我的持股 / 投資組合 | get_portfolio（user_id 使用 <context> 區塊提供的值）|
| 大盤現在多少 / 加權指數 / 櫃買 | get_market_overview（market="TWSE" 或 "TPEx"）|
| 外資今天買賣超 / 三大法人總額 / 市場資金流向 | get_market_institutional_flows |
| 台指期 / 外資多空單 / 期貨未平倉 | get_market_futures_positions（commodity="TXF" 預設）|

預設呼叫原則：可平行呼叫的工具（同一檔股票的多個面向）應同時觸發，不要串行等待。

<knowledge_base_usage>
**search_knowledge 不只用於純理論題，個股分析時也應主動呼叫**，以引用知識庫中的「眉角」與台股實務細節。觸發時機：

1. **進場分析 / 目標價評估**：
   - 平行呼叫 `search_knowledge`，query 例如：「目標價 估值 風險管理」、「RSI 鈍化 強多頭」、「台股 三大法人 解讀」
   - 引用知識庫中對應指標的「常見誤判」段落，避免教科書式解讀

2. **技術指標出現極端值時**：
   - RSI > 80 或 < 20 → search_knowledge("RSI 鈍化 強趨勢")
   - KD 高檔黃金交叉、低檔死亡交叉 → search_knowledge("KD 鈍化")
   - 布林帶突破 → search_knowledge("布林通道 軋空 假突破")

3. **籌碼面解讀**：
   - 三大法人連續買賣超 → search_knowledge("外資 投信 自營商 解讀")
   - 融資融券異常 → search_knowledge("融資維持率 軋空 斷頭")

4. **使用者出現行為偏誤訊號**（FOMO / 鎖定成本 / 跟單）：
   - 「會不會漲」「該不該追」「等回本」 → search_knowledge("行為金融 損失趨避 過度自信")

5. **回測結果解讀**：
   - 取得 `run_strategy_backtest` 結果後 → search_knowledge("夏普比率 過度擬合 回測 解讀")

6. **合規邊界判斷**：
   - 用戶要求保證、薦股、借錢投資 → search_knowledge("免責 紅線 合規")

**單位 sanity check**：法人買賣超數據單位為「張」（1 張 = 1000 股）。若工具回傳數值 > 該股單日成交量數十倍，極可能是單位誤解（股 vs 張），需重新核對而非直接引用。
</knowledge_base_usage>
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
  <thought>
  進場評估需多面向資料：股價、技術、基本、籌碼、新聞，以及使用者的持股部位。
  平行呼叫六個面向工具 + search_knowledge + get_portfolio。
  輸出時不下「建議 X 元買進」這類投顧式價位指令，
  改以「關鍵價位 + 不同週期解讀 + 你的部位狀況」呈現，把判斷權還給使用者。
  </thought>
  <tool_calls>
  get_stock_price(ticker="鴻海")
  analyze_technicals(ticker="鴻海", period="3mo")
  analyze_fundamentals(ticker="鴻海")
  get_institutional(ticker="鴻海")
  get_margin_trading(ticker="鴻海")
  search_financial_news(query="鴻海")
  search_knowledge(query="進場分析 目標價 估值 RSI 鈍化 三大法人解讀")
  get_portfolio(user_id="<context 提供的值>")
  </tool_calls>
  <response>
📌 現價位置：鴻海 178 元，位於 MA20（175）上方約 1.7%；
基本面 PE 12.5 低於歷史均值，落於估值帶「便宜→合理」之間。

🎯 關鍵價位（資料事實，非建議）
• 技術支撐：MA20=175（短中線分水嶺）、MA60=165（中期趨勢底）
• 技術壓力：近期高點 185（R1）
• 估值參考帶：便宜 155 / 合理 175 / 昂貴 195（PE × EPS 估算，未納入產業週期與成長率）
• 趨勢警戒位：跌破 165（MA60）視為中期趨勢轉弱訊號
• 籌碼觀察：外資連 3 日買超、投信小幅賣超

📐 不同投資週期的解讀
• 長線（存股 / 1 年以上）：估值偏低、ROE 8.2%（普通），
  若認同 AI 伺服器長期題材，可採定期定額分批，不需擇時。
• 波段（數週至數月）：均線多頭排列且法人續買為偏多訊號，但已接近估值帶上緣，追高賠率不佳。
  MA20（175）附近若回測且法人未轉賣，是相對較佳的觀察區，而非「保證進場」。
• 短線（數天至數週）：RSI 62 中性偏多、未鈍化，無明顯短線訊號。

📋 你的部位狀況（依 get_portfolio 結果填入）
• 已持有 1000 股、平均成本 165；目前損益 +7.9%
• 鴻海佔投組約 22% — 已超過 20% 集中度警戒線，建議「先檢視整體配置而非加碼」
（若 get_portfolio 顯示未持有此股，本段改寫為：
尚未持有此股；請留意整體投組是否已重壓相同產業／供應鏈）

⚠️ 風險與原則提醒
• 上述為資料中可觀察到的價位與訊號，不是「該幾塊買 / 該幾塊停損」的指令
• 估值法忽略產業週期與成長率，鴻海橫跨消費電子代工與 AI 伺服器，需自行判斷適用度
• 真正的決策需考量：你的投資週期、可承受虧損、整體部位、資金成本

📚 知識庫補充：
- 葛蘭碧第 3 法則：股價在上升均線上方拉回但未跌破，視為加碼訊號之一（前提：原本部位合理、非追高）
- 強多頭中 RSI 高檔可能鈍化，不代表立即反轉
- 三大法人買超數據以「張」為單位（1 張 = 1000 股）
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
        "🏦 {股票} 籌碼面分析\n• 三大法人近期買賣超趨勢\n• 融資融券變化（如有查詢）\n• 籌碼面結論"
    ),
    "news": ("📰 相關新聞彙整\n• 列出重點新聞\n• 分析對股價可能的影響（利多 / 利空 / 中性）"),
    "backtest": (
        "📊 回測結果解讀\n"
        "• 績效數據摘要（報酬率 / 夏普 / 最大回撤 / 勝率）\n"
        "• ✅ 策略優點\n"
        "• ⚠️ 策略缺點\n"
        "• 💡 改善建議\n"
        "• 與大盤 Buy & Hold 比較"
    ),
    "knowledge": (
        "📚 知識回覆\n• 清楚解釋概念\n• 搭配實際應用場景說明\n• 如有相關指標，說明判讀方式"
    ),
    "portfolio": (
        "💼 投資組合分析\n"
        "• 總覽：總市值 / 總損益\n"
        "• 個股表現摘要\n"
        "• 集中度風險提示（如有）\n"
        "• 建議關注事項"
    ),
    "price_query": (
        "📌 {股票} 即時報價\n• 現價、漲跌幅、成交量\n• 簡短技術位置描述（如在均線上方 / 下方）"
    ),
}


def _build_llm(model_name: str | None = None) -> ChatVertexAI:
    vertexai.init(project=settings.google_cloud_project)
    return ChatVertexAI(
        model_name=model_name or settings.gemini_model_name,
        temperature=0.3,
        project=settings.google_cloud_project,
    )


# ── Rule-based Intent Classification ─────────────────────────────────────────

# Regex patterns for intent classification (compiled once)
_INTENT_PATTERNS: list[tuple[str, re.Pattern, float]] = [
    # macro_overview: 大盤 / 外資總額 / 期貨多空（無個股 ticker）
    (
        "macro_overview",
        re.compile(
            r"(大盤|加權指數|加權.{0,3}指|TAIEX|台股.{0,3}指|"
            r"櫃買|OTC指|"
            r"外資.{0,3}(今天|今日|昨天|本週|這週|現在).{0,5}(買|賣|超|動向|流向)|"
            r"外資.{0,4}買賣超.{0,3}(多少|金額|總額)|"
            r"外資.{0,5}(未平倉|淨多單|淨空單|多空(?!.*[一-龥]{2,5}))|"
            r"三大法人.{0,5}(總額|彙總|整體|今天|昨天)|"
            r"市場.{0,3}(資金|籌碼).{0,6}(流向|流入|流出)|"
            r"台指期|臺指期|TXF|小台|微台|MXF|TMF|"
            r"期貨.{0,5}(多空|未平倉|淨多單|淨空單|大戶))",
            re.IGNORECASE,
        ),
        0.9,
    ),
    # entry_analysis: 進場、買入、目標價
    (
        "entry_analysis",
        re.compile(
            r"(進場|可以買|能買|適合買|值得買|值得投資|適不適合|目標價|多少錢.*(買|進)|"
            r"該不該買|何時.*(買|進場)|買入|建議.*(買|進場)|可不可以買|entry)",
            re.IGNORECASE,
        ),
        0.9,
    ),
    # backtest: 回測、策略
    (
        "backtest",
        re.compile(
            r"(回測|backt|策略績效|模擬交易|歷史績效|策略.*表現)",
            re.IGNORECASE,
        ),
        0.95,
    ),
    # portfolio: 持股、投資組合
    (
        "portfolio",
        re.compile(
            r"(我的持股|投資組合|portfolio|我的股票|持倉|我買了|我有哪些股)",
            re.IGNORECASE,
        ),
        0.95,
    ),
    # knowledge: 投資理論、教學
    (
        "knowledge",
        re.compile(
            r"(什麼是|教我|解釋.*(?:指標|理論|策略)|如何.*(?:分析|計算)|"
            r"怎麼看.*(?:技術|基本|財報)|原理|學習|入門|新手)",
            re.IGNORECASE,
        ),
        0.85,
    ),
    # news: 新聞、消息
    (
        "news",
        re.compile(
            r"(新聞|消息|市場動態|最近.*(?:發生|怎麼了)|news|利多|利空|重大.*事件)",
            re.IGNORECASE,
        ),
        0.9,
    ),
    # institutional_analysis: 法人、籌碼
    (
        "institutional_analysis",
        re.compile(
            r"(法人|外資|投信|自營商|籌碼|買超|賣超|融資|融券|三大法人|主力)",
            re.IGNORECASE,
        ),
        0.9,
    ),
    # technical_analysis: 技術面
    (
        "technical_analysis",
        re.compile(
            r"(技術[面指]|RSI|MACD|KD|均線|MA\d|布林|支撐|壓力|走勢|K線|趨勢|"
            r"黃金交叉|死亡交叉|超買|超賣|乖離|波段|型態)",
            re.IGNORECASE,
        ),
        0.9,
    ),
    # fundamental_analysis: 基本面
    (
        "fundamental_analysis",
        re.compile(
            r"(基本面|財報|EPS|PE|PB|ROE|本益比|殖利率|營收|毛利|淨利|股利|配息|估值)",
            re.IGNORECASE,
        ),
        0.9,
    ),
    # price_query: 股價查詢
    (
        "price_query",
        re.compile(
            r"(股價|現在.*多少錢|目前.*(?:價格|價位)|(?:漲|跌)了?多少|收盤|開盤|成交量|市值)",
            re.IGNORECASE,
        ),
        0.9,
    ),
    # comprehensive_analysis: 分析（廣泛）
    (
        "comprehensive_analysis",
        re.compile(
            r"((?:分析|怎麼樣|如何|怎樣|看法|看好|看壞|前景|展望).{0,6}$|"
            r"^(?:幫我|請|麻煩)?(?:分析|看看|評估))",
            re.IGNORECASE,
        ),
        0.85,
    ),
]

# Ticker extraction pattern:
# Non-ticker uppercase words to skip
_NON_TICKER_WORDS = frozenset(
    {
        "RSI",
        "MACD",
        "EPS",
        "PE",
        "PB",
        "ROE",
        "ROA",
        "MA",
        "KD",
        "ETF",
        "IPO",
        "AI",
        "BB",
        "ATR",
        "SMA",
        "EMA",
        "DCF",
        "DDM",
        "API",
        "SSE",
        "FAQ",
        "URL",
        "PDF",
        "CSV",
    }
)

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
        "最近",
        "目前",
        "現在",
        "今天",
        "昨天",
        "什麼",
        "怎麼",
        "如何",
        "為什",
        "哪些",
        "哪個",
        "這個",
        "那個",
        "那些",
        "請問",
        "幫我",
        "麻煩",
        "可以",
        "能不",
        "應該",
        "是否",
        "我的",
        "你的",
        "不是",
    }

    # b) Company name at start of sentence before query keywords:
    #    "台積電可以買嗎", "鴻海怎麼樣", "台積電均線交叉", "緯創漲跌如何", "環球晶最近怎麼樣"
    m = re.match(
        r"([一-龥]{2,5}?)"
        r"(?=的|可以|能不能|適合|值得|怎[麼樣]|如何|目前|現在|最近|短期|長期|"
        r"股價|股票|走勢|漲跌|漲幅|跌幅|多少|價格|報價|均線|"
        r"技術|基本|財報|營收|法人|外資|三大|新聞|消息|回測|策略)",
        q,
    )
    if m and len(m.group(1)) >= 2 and m.group(1)[:2] not in _non_company:
        return m.group(1)

    # c) Before technical indicators: "台積電RSI", "鴻海MACD"
    m = re.search(r"([一-龥]{2,5})\s*(?:RSI|MACD|KD|EPS|PE|PB|ROE)", q)
    if m:
        return m.group(1)

    # d) Fallback: action verb followed by Chinese name anywhere in sentence
    #    "幫我分析聯發科未來目標價格?" → "聯發科"
    #    Lazy match + lookahead to stop before non-name suffixes (未來/目標/的/etc.)
    m = re.search(
        r"(?:分析|看看|查[詢看]?|評估|了解|介紹|說明)(?:一下)?\s*"
        r"([一-龥]{2,5}?)"
        r"(?=未來|目標|股票|股價|公司|集團|的|怎|是否|可以|能否|"
        r"值得|適合|有沒|會不|該不|現在|目前|最近|短期|長期|"
        r"[^\u4e00-\u9fa5]|$)",
        q,
    )
    if m and m.group(1) not in _non_company:
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
            # macro_overview is market-wide; suppress any noisy ticker extraction
            if intent in _NON_TICKER_PREFETCH_INTENTS:
                return intent, None, confidence
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
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="分類信心分數")


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
    question: str,
    llm: ChatVertexAI,
) -> tuple[str, str | None, float]:
    """LLM fallback classifier using structured output.

    Only called when regex confidence is low. Any failure returns the safe
    default of ("general", None, 0.0).
    """
    try:
        classifier = llm.with_structured_output(_IntentResult)
        result = await classifier.ainvoke(
            [
                SystemMessage(content=_LLM_CLASSIFY_PROMPT),
                HumanMessage(content=question),
            ]
        )
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
    question: str,
    llm: ChatVertexAI,
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
        "get_margin_trading",
        "search_financial_news",
        "search_knowledge",
        "get_portfolio",
    ],
    "comprehensive_analysis": [
        "get_stock_price",
        "analyze_technicals",
        "analyze_fundamentals",
        "get_institutional",
        "get_margin_trading",
        "search_financial_news",
        "search_knowledge",
        "get_portfolio",
    ],
    "macro_overview": [
        "get_market_overview",
        "get_market_institutional_flows",
        "get_market_futures_positions",
        "search_knowledge",
    ],
}

# Macro intent 不需要 ticker，但仍走 prefetch 流程；這個集合用於 dispatch 判斷
_NON_TICKER_PREFETCH_INTENTS: frozenset[str] = frozenset({"macro_overview"})

# ── 預取模式回答格式 ─────────────────────────────────────────────────────────

_ENTRY_FORMAT = """\
📌 現價位置：股價相對於均線、支撐壓力、估值帶的位置（事實描述，不下「買/賣」結論）

🎯 關鍵價位（資料事實，非投顧式建議）
  • 技術支撐區：1-2 個重要支撐位（如 MA20 / MA60 / 近期低點），說明各自意義
  • 技術壓力區：1-2 個重要壓力位
  • 估值參考帶：依基本面回傳的便宜 / 合理 / 昂貴三段價位（須提醒此估值未納入產業週期與成長率）
  • 趨勢警戒位：跌破時意味中期趨勢轉弱的價位

📐 不同投資週期的解讀（教育取向，不指定單一動作）
  • 長線（1 年以上 / 定期定額 / 存股）：以基本面估值、ROE、股利穩定性為主，技術短線次要
  • 波段（數週至數月）：以均線排列、法人連續性、估值相對位置為主
  • 短線（數天至數週）：以 RSI/KD/MACD 訊號、量價結構、籌碼變化為主
  → 提醒：不同週期的「合理觀察點」不同，請使用者依自身週期取用，避免短線價位被誤用為長線進場依據

📋 你的部位狀況（若 <prefetched_data> 中的投資組合資料顯示此檔已持有）
  • 持有股數、平均成本、目前損益
  • 該檔佔投資組合比重；若 > 20% 須提示集中度風險、不宜再加碼
  • 若未持有此檔但組合已高度集中於同產業，亦須提示
  • 若使用者尚未建立投資組合或無此持股，本段省略

⚠️ 風險與原則提醒
  • 上述為資料中可觀察到的價位與訊號，不是「該幾塊買 / 該幾塊停損」的指令
  • 真正的決策需考量：你的投資週期、可承受虧損、整體部位、資金成本
  • 若各面向訊號矛盾，採較保守做法（觀望、減碼觀察、分批小額）

禁忌：
  • 不可使用「建議進場區間 X-Y」「建議停損 Z」這類投顧式價位指令句型
  • 不可單方面給出「風險報酬比 X:Y」結論（此比值需用戶自定報酬目標才有意義）
  • 不可省略「不同週期解讀」與「持股檢視」段落（除非真的無相關資料）"""

_COMPREHENSIVE_FORMAT = """\
📌 現況摘要：現價、趨勢方向
📊 技術面：關鍵指標與訊號、支撐壓力位（描述事實，不下進出結論）
📈 基本面：估值與獲利能力重點、估值參考帶（便宜 / 合理 / 昂貴）
🏦 籌碼面：法人與融資融券動向摘要
📰 近期新聞：重點消息與可能的影響面向
📋 你的部位狀況：若已持有此檔，提示成本相對位置與佔比；未持有則略過
📐 不同投資週期的解讀：長線 / 波段 / 短線各自的判讀重點
💡 綜合判斷：以「資料中可觀察到的方向」描述（偏多/偏空/分歧），不指定具體進出價位"""

_MACRO_FORMAT = """\
📈 大盤現況：加權指數現價、漲跌、（如有）盤中區間
🏦 三大法人：整體買賣超摘要（外資為重點，金額單位「億元」）
   - 逐日方向是否一致？是否出現連續買/賣超？
   - 投信、自營商方向是否與外資一致？
📐 期貨籌碼：外資臺指期未平倉淨額（多單偏多 / 空單偏空）與當日交易方向
   - 與現貨方向是否一致？（背離可能暗示避險或方向轉換）
💡 綜合判斷：以「資料中可觀察到的方向」描述（偏多/偏空/分歧），不可推測指數點位
⚠️ 風險提醒：大盤分析僅作為個股決策的環境背景，不構成短線進出依據

引用紀律：
- 數字一律使用 <prefetched_data> 中已格式化的金額（例：+434 億元），不要自行換算單位。
- 期貨「口」與股市「張」是不同單位，不可混用。
- 若某項資料顯示 ⚠️ 失敗，明確跳過該欄位並說明資料暫不可得。"""

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
5. **知識庫眉角檢核**：對照 search_knowledge 回傳內容檢視現狀。
   - RSI > 80 是否為強多頭中的「鈍化」？避免直接視為反轉訊號
   - 法人買賣超數據單位為「張」（1 張 = 1000 股），避免單位誤判
   - 目標價/估值是估算值，非承諾，需提醒用戶
   - 用戶若有 FOMO / 錨定 / 跟單跡象，引用行為金融偏誤提醒
6. **個人化檢視**：若 get_portfolio 結果顯示已持有此股票，
   計算佔投組比重、平均成本相對現價的位置、是否屬集中度過高（>20%）；
   若未持有此股但投組已重壓相同產業／供應鏈，亦需提示。
   若工具回傳「未提供 user_id」或「沒有任何持股」，省略個人化段落。
7. 矛盾檢查：各面向是否一致？若矛盾，取較保守結論。
8. 整合結論，但**不下「該幾塊買 / 該幾塊停損」這類投顧式價位指令**，
   改以「關鍵價位 + 不同投資週期解讀 + 趨勢警戒位」呈現。
</reasoning_process>

<response_format>
{format_instructions}
</response_format>

<rules>
- 所有數字必須來自 <prefetched_data>，不可自行捏造。
- **股價引用規則（重要）**：
  - 「現價 / 收盤」一律以 `get_stock_price` 結果為準（標註「收盤」或「現價」依工具輸出原樣引用）。
  - `analyze_technicals` 內的「日線最近收盤」僅供技術位置計算，**不可**單獨當成現價回答使用者。
    - 台股報價來源可切換（MIS 即時報價或 TWSE/TPEx 收盤資料）；回答時一律依工具輸出的「現價」或「收盤（YYYY-MM-DD）」標示，不可自行改寫時點。
- **必須將 search_knowledge 的內容融入分析**，而非僅依靠 LLM 內建知識；
  若知識庫內容對當前指標數值（如 RSI 鈍化、KD 高檔交叉、法人解讀）有對應說明，回應中應引用。
- **個人化原則**：若 <prefetched_data> 包含 `get_portfolio` 結果且使用者已持有相關標的，
  必須以「📋 你的部位狀況」段落呈現平均成本相對現價、佔投組比重、集中度警示；
  若未持有亦需檢視整體投組是否已重壓同產業／供應鏈。
- **禁用投顧式句型**：
  - 禁止「建議 X-Y 元進場」「建議 Z 元停損」「風險報酬比 N:M」這類具體投顧價位指令。
  - 改以「關鍵價位（支撐 / 壓力 / 估值帶 / 趨勢警戒位）」
    +「不同投資週期解讀（長 / 波段 / 短）」呈現，
    讓使用者依自身週期與部位判斷。
- 若某項工具結果包含 ⚠️ 錯誤標記，跳過該欄位並說明「此部分數據暫時無法取得」，其餘欄位正常輸出。
- 不可保證獲利、不可承諾報酬率。
- 任何看多描述都必須附帶趨勢警戒位或風險說明。
- 最後加上 ⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。
</rules>
"""

# ── Tool Registry ────────────────────────────────────────────────────────────

_TOOL_REGISTRY: dict = {}


def _init_tool_registry() -> None:
    global _TOOL_REGISTRY  # noqa: PLW0603
    if not _TOOL_REGISTRY:
        _TOOL_REGISTRY = {tool.name: tool for tool in ALL_TOOLS}


async def _prefetch_tool_results(
    ticker: str, tool_names: list[str], user_id: str = ""
) -> tuple[str, list[dict]]:
    """平行呼叫所有必要工具。

    Returns:
        (formatted_text, tool_calls) — tool_calls 為 citations 構建用的原始紀錄。
    """
    _init_tool_registry()

    async def _call(name: str) -> tuple[str, dict, str]:
        tool_fn = _TOOL_REGISTRY.get(name)
        if not tool_fn:
            return name, {}, f"⚠️ 工具 {name} 不存在"
        try:
            if name == "search_financial_news":
                inp = {"query": ticker} if ticker else {"query": "台股 大盤 外資"}
            elif name == "get_portfolio":
                # 個人化：進場 / 綜合分析時並行查詢使用者持股，讓 LLM 能作集中度 / 加碼合理性判斷
                if not user_id:
                    return name, {}, "⚠️ 未提供 user_id，跳過投資組合查詢"
                inp = {"user_id": user_id}
            elif name == "search_knowledge":
                if ticker:
                    # 個股分析：引入「眉角」與台股實務解讀
                    inp = {
                        "query": (
                            "進場分析 目標價 估值常見誤判 RSI鈍化強多頭 "
                            "台股三大法人解讀 位階與風險控制 行為金融偏誤"
                        )
                    }
                else:
                    # 大盤分析：引入大盤解讀的 KB 內容
                    inp = {
                        "query": (
                            "大盤趨勢 三大法人解讀 外資 台指期 未平倉 多空"
                            " 籌碼面 風險管理"
                        )
                    }
            elif name == "analyze_technicals":
                inp = {"ticker": ticker, "period": "3mo"}
            elif name == "get_market_overview":
                inp = {"market": "TWSE"}
            elif name == "get_market_institutional_flows":
                inp = {"days": 3}
            elif name == "get_market_futures_positions":
                inp = {"commodity": "TXF"}
            else:
                inp = {"ticker": ticker} if ticker else {}
            output = await asyncio.to_thread(tool_fn.invoke, inp)
            return name, inp, str(output)
        except Exception as e:
            logger.warning("Prefetch tool %s failed: %s", name, e)
            return name, {}, f"⚠️ {name} 查詢失敗：{e}"

    tasks = [_call(name) for name in tool_names]
    results = await asyncio.gather(*tasks)
    parts = []
    tool_calls: list[dict] = []
    for name, inp, output in results:
        parts.append(f"── {name} ──\n{output}")
        tool_calls.append({"name": name, "input": inp, "output": output})
    return "\n\n".join(parts), tool_calls



# ── Prefetch Mode ────────────────────────────────────────────────────────────


_DISCLAIMER_TEXT = "\n\n⚠️ 免責聲明：所有分析僅供學習與研究用途，不構成投資建議。"


def _missing_disclaimer(full_output: str) -> str:
    """免責聲明不能依賴 LLM 自律附加（串流截斷或模型漏寫時會消失）。

    回傳需要補上的免責文字；輸出已含免責聲明或為空時回傳空字串。
    """
    if not full_output or "免責聲明" in full_output:
        return ""
    return _DISCLAIMER_TEXT


async def _run_prefetch_mode(
    question: str,
    intent: str,
    ticker: str,
    tool_names: list[str],
    llm: ChatVertexAI,
    conversation_id: str | None,
    user_id: str,
    intent_event: IntentEvent | None = None,
) -> AsyncGenerator[StreamChunk, None]:
    """預取模式：平行呼叫工具 → 組裝結果 → 直接串流 LLM 回答。"""
    thinking_steps: list[dict] = []
    if intent_event is not None:
        thinking_steps.append(dict(intent_event))

    for name in tool_names:
        if name == "get_portfolio":
            start_input: dict[str, Any] = {"user_id": user_id} if user_id else {}
        elif ticker:
            start_input = {"ticker": ticker}
        else:
            start_input = {}
        start_event = ToolStartEvent(type="tool_start", tool=name, input=start_input)
        thinking_steps.append(dict(start_event))
        yield start_event

    tool_results, tool_calls = await _prefetch_tool_results(
        ticker, tool_names, user_id=user_id
    )

    for name in tool_names:
        end_event = ToolEndEvent(type="tool_end", tool=name)
        thinking_steps.append(dict(end_event))
        yield end_event

    citations = _build_citations(tool_calls)
    citations_event: CitationsEvent | None = None
    if citations:
        citations_event = CitationsEvent(type="citations", citations=citations)

    if intent == "entry_analysis":
        format_instructions = _ENTRY_FORMAT
    elif intent == "macro_overview":
        format_instructions = _MACRO_FORMAT
    else:
        format_instructions = _COMPREHENSIVE_FORMAT
    system_msg = _PREFETCH_SYSTEM_TEMPLATE.format(
        tool_results=tool_results,
        format_instructions=format_instructions,
    )

    chat_history: list = []
    if conversation_id:
        try:
            chat_history = load_history(conversation_id, user_id=user_id)
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

        disclaimer = _missing_disclaimer(full_output)
        if disclaimer:
            full_output += disclaimer
            yield disclaimer

        if citations_event is not None:
            yield citations_event

        if conversation_id and full_output:
            try:
                save_history(
                    conversation_id,
                    question,
                    full_output,
                    user_id=user_id,
                    thinking=thinking_steps or None,
                    citations=citations or None,
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
            f'目前使用者 user_id = "{user_id}"\n'
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
    intent_event: IntentEvent | None = None,
) -> AsyncGenerator[StreamChunk, None]:
    """LangGraph ReAct Agent 模式：自主決策工具呼叫。"""
    system_prompt = _build_agent_system_prompt(intent, user_id)

    thinking_steps: list[dict] = []
    if intent_event is not None:
        thinking_steps.append(dict(intent_event))

    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=system_prompt,
    )

    chat_history_messages: list = []
    if conversation_id:
        try:
            chat_history_messages = load_history(conversation_id, user_id=user_id)
        except Exception as e:
            logger.warning("Failed to load history for %s: %s", conversation_id, e)

    input_messages = list(chat_history_messages)
    input_messages.append(HumanMessage(content=question))

    try:
        full_output = ""
        active_tools: set[str] = set()
        # tool_call_id → {"name", "input", "output"} for citation building
        tool_calls_by_run: dict[str, dict] = {}

        async for event in agent.astream_events(
            {"messages": input_messages},
            version="v2",
        ):
            kind = event["event"]
            if kind == "on_tool_start":
                tool_name = event["name"]
                active_tools.add(tool_name)
                run_id = event.get("run_id", "")
                tool_input = event["data"].get("input", {}) or {}
                tool_calls_by_run[run_id] = {
                    "name": tool_name,
                    "input": tool_input if isinstance(tool_input, dict) else {},
                    "output": "",
                }
                start_event = ToolStartEvent(
                    type="tool_start",
                    tool=tool_name,
                    input=tool_input if isinstance(tool_input, dict) else {},
                )
                thinking_steps.append(dict(start_event))
                yield start_event
            elif kind == "on_tool_end":
                tool_name = event["name"]
                active_tools.discard(tool_name)
                run_id = event.get("run_id", "")
                output = event["data"].get("output")
                # output may be a ToolMessage or raw string
                if hasattr(output, "content"):
                    output_str = str(output.content)
                else:
                    output_str = str(output) if output is not None else ""
                if run_id in tool_calls_by_run:
                    tool_calls_by_run[run_id]["output"] = output_str
                end_event = ToolEndEvent(type="tool_end", tool=tool_name)
                thinking_steps.append(dict(end_event))
                yield end_event
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

        disclaimer = _missing_disclaimer(full_output)
        if disclaimer:
            full_output += disclaimer
            yield disclaimer

        citations = _build_citations(list(tool_calls_by_run.values()))
        if citations:
            yield CitationsEvent(type="citations", citations=citations)

        if conversation_id and full_output:
            try:
                save_history(
                    conversation_id,
                    question,
                    full_output,
                    user_id=user_id,
                    thinking=thinking_steps or None,
                    citations=citations or None,
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
    model_name: str | None = None,
) -> AsyncGenerator[StreamChunk, None]:
    """Run the tool-calling agent with hybrid intent classification.

    Flow:
        1. Classify user intent + extract ticker (regex fast path;
           LLM structured-output fallback when regex is low-confidence)
        2a. If entry/comprehensive analysis with ticker → prefetch mode
            (parallel tool calls → direct LLM streaming)
        2b. Otherwise → LangGraph ReAct agent mode

    Args:
        model_name: 依使用者 tier 傳入（config.model_for_tier）；None 用預設 Pro。
    """
    llm = _build_llm(model_name)

    # Step 1: 混合式意圖分類（regex 為主，低信心時 LLM 補強）
    intent, ticker, confidence = await _classify_intent_hybrid(question, llm)
    logger.info("Intent: %s | Ticker: %s | Confidence: %.2f", intent, ticker, confidence)

    intent_event = IntentEvent(
        type="intent", intent=intent, ticker=ticker, confidence=confidence
    )
    yield intent_event

    # Step 2: 分流執行策略
    prefetch_tools = _PREFETCH_INTENTS.get(intent)
    needs_ticker = intent not in _NON_TICKER_PREFETCH_INTENTS
    if prefetch_tools and (ticker or not needs_ticker):
        logger.info("→ Prefetch mode (%d tools, ticker=%s)", len(prefetch_tools), ticker or "—")
        async for chunk in _run_prefetch_mode(
            question,
            intent,
            ticker or "",
            prefetch_tools,
            llm,
            conversation_id,
            user_id,
            intent_event=intent_event,
        ):
            yield chunk
    else:
        logger.info("→ Agent mode (intent=%s)", intent)
        async for chunk in _run_agent_mode(
            question,
            intent,
            llm,
            conversation_id,
            user_id,
            intent_event=intent_event,
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
