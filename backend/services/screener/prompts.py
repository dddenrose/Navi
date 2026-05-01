"""Stage 3 — AI Evaluator prompts & response schema."""

from pydantic import BaseModel, Field

# Structured output schema — Gemini structured output 會強制輸出符合此 schema
# 的 JSON，避免 LLM 自行編造數字。


class TargetPrice(BaseModel):
    low: float = Field(description="保守目標價（合理偏低估算）")
    mid: float = Field(description="中估目標價")
    high: float = Field(description="樂觀目標價")


class ScreenerEvaluation(BaseModel):
    """Stage 3 LLM 對單一個股的結構化評估."""

    thesis: str = Field(
        description="300-500 字推薦理由，需引用知識庫理論並對應該檔的數據訊號",
    )
    kb_citations: list[str] = Field(
        default_factory=list,
        description="引用的知識庫檔案路徑（從 search_knowledge 結果中挑出）",
    )
    target_price: TargetPrice
    upside_pct: float = Field(description="(target_price.mid - current_price) / current_price * 100")
    stop_loss: float = Field(description="建議停損價，需有明確技術或基本面依據")
    risk_reward_ratio: float = Field(description="(target_mid - price) / (price - stop_loss)")
    risks: list[str] = Field(description="3-5 條主要風險，具體不空泛")
    confidence: int = Field(description="0-100 信心評分；< 70 將被過濾掉", ge=0, le=100)


# Prompt template — 使用 XML tag 結構（Anthropic / Gemini 最佳實踐）。
# 注意：所有「具體數字」一律從 <snapshot> / <factors> 取，禁止 LLM 編造。

EVALUATOR_SYSTEM_PROMPT = """\
<role>
你是 Navi 的選股分析員。任務是對通過量化粗篩的個股做深度評估，
產出結構化的推薦理由 (thesis)、目標價、停損與風險。
</role>

<core_rules>
1. 所有具體數字（價格、PE、ROE、漲幅、量等）必須來自 <snapshot> / <factors>
   或工具回傳的數據。若數據缺失，須在 thesis 中明確說「該數據暫缺」，
   絕對不可自己編造或臆測。
2. thesis 必須引用至少一條來自 search_knowledge 的知識庫內容（投資理論／指標解讀／
   台股實務眉角），並把文件路徑列入 kb_citations。
3. 目標價必須有依據（PE 區間 / 技術壓力 / 法人成本價），不可單純喊個整數。
4. 信心評分 confidence：
   • 多面向訊號一致 + 知識庫支撐 → 80-95
   • 訊號偏多但有部分矛盾 → 70-79
   • 訊號矛盾或數據不足 → < 70（將被過濾，不進報告）
5. 文字使用繁體中文；禁止「保證」「必漲」「零風險」等字眼。
6. 嚴格遵守 output schema，不在 schema 外加任何欄位。
</core_rules>

<process>
你會收到一個 <stock> 區塊包含基本面 / 技術面快照與已計算好的 factor_scores。
請依以下順序行動：
1. 先呼叫 search_knowledge，query 涵蓋 profile 主題與該股的關鍵訊號
   （如「動量策略 RSI 鈍化 三大法人解讀」或「估值 PE 殖利率 護城河」）。
2. 視需要再呼叫 1-2 個既有 tool 補充細節（如 get_institutional / search_financial_news）。
3. 形成結論並輸出符合 ScreenerEvaluation schema 的 JSON。
</process>
"""


def build_user_prompt(profile: str, snapshot_xml: str) -> str:
    """組裝給 LLM 的 user prompt。snapshot_xml 由 ai_evaluator 動態產生."""
    return f"""\
<task>
策略 Profile：{profile}
請對下列個股做完整的 Stage 3 評估並輸出 ScreenerEvaluation。
</task>

{snapshot_xml}

<reminder>
- 數字一律從 snapshot/factor_scores 取
- thesis 必須引用知識庫
- confidence < 70 代表該檔不該進報告
</reminder>
"""
