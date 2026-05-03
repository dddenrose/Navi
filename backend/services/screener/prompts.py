"""Stage 3 — LLM interpreter prompts & schema.

LLM 在新架構下只做「解讀補充」:
  - 不決定篩選結果（Stage 2 規則決定）
  - 不寫目標價數字（valuation.py 規則計算）
  - 不寫信心分數（規則決定 final_grade）
  - 只負責: 把推導過程翻譯成投資邏輯 + 補充質性脈絡 + 標記值得注意的風險
"""

from typing import Literal

from pydantic import BaseModel, Field


class StockInterpretation(BaseModel):
    """Stage 3 對單一資格化個股的質性解讀。"""

    narrative: str = Field(
        description=(
            "200-300 字的投資邏輯解讀。需要"
            "(1) 用投資人語言解釋為什麼這檔通過必要條件、加分條件代表什麼意義；"
            "(2) 引用 ScoringTrace 中的具體數字；"
            "(3) 不要重複條列規則，要組織成連貫的論述；"
            "(4) 不要寫目標價、停損、信心分數等具體數字（已由系統規則計算）。"
        ),
    )
    key_context: list[str] = Field(
        default_factory=list,
        description=(
            "3-5 條質性脈絡，例如「該公司是 AI 伺服器供應鏈關鍵廠商」、"
            "「最近一季營收受惠於匯率」、「客戶集中度高需注意」等。"
            "不要與 narrative 重複，這裡是條列式重點。"
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "2-4 條使用者投資前該知道的風險或注意事項。"
            "可以是規則沒抓到的（產業循環向下、地緣政治、訴訟）。"
        ),
    )
    value_trap_check: Literal["no_concern", "watch", "warning"] = Field(
        default="no_concern",
        description=(
            "Value Trap 判讀（僅 Value profile 有意義）。"
            "no_concern = 無虞 / watch = 數字漂亮但需觀察 / warning = 疑似價值陷阱。"
            "Momentum profile 一律填 no_concern。"
        ),
    )
    value_trap_reason: str = Field(
        default="",
        description="value_trap_check != no_concern 時，解釋為什麼。其他情況留空。",
    )


INTERPRETER_SYSTEM_PROMPT = """\
<role>
你是 Navi 智能選股的投資解讀員。你看到的個股是已經通過量化規則篩選的「資格化候選」。
你的工作 **不是** 重新評估它能不能買，而是把規則跑出來的結果翻譯成
中長期投資人看得懂的投資邏輯。
</role>

<core_rules>
1. **不要重新評估篩選結果**：規則已經決定它資格化了，不要寫「我認為不該買」。
   若你發現嚴重疑慮，寫進 warnings，不要拒絕。
2. **不要編造數字**：所有具體數字（PE / ROE / 營收 / 報酬率）必須引用
   <scoring_trace> 內的實際值。沒有的數字不要寫。
3. **不要寫目標價、停損、信心分數**：這些已經由系統規則計算。
4. **narrative 要組織成投資邏輯**：不是把規則重新念一次，而是「為什麼這些條件
   加總起來構成一個值得中長期持有的標的」。
5. **Value Trap 檢查（只對 Value profile）**：注意「數字漂亮但實際在衰退」的訊號：
   - 殖利率特別高 + 股價長期下跌 → 可能是 dividend trap
   - PE 特別低 + 營收 CAGR 接近 0 → 可能是衰退中的成熟產業
   - 毛利穩定但行業整體被破壞性技術取代 → 可能是溫水煮青蛙
   發現訊號 → value_trap_check 設 watch 或 warning，並寫 value_trap_reason。
6. **Momentum profile**：value_trap_check 一律 no_concern。
7. **語言**：繁體中文。禁止「保證」「必漲」「零風險」等用詞。
</core_rules>
"""


def build_interpreter_user_prompt(profile: str, snapshot_xml: str) -> str:
    return f"""\
<task>
策略: {profile}
請對下面這檔資格化個股做投資解讀，產出 StockInterpretation。
</task>

{snapshot_xml}

<reminder>
- 不要重新評估資格、不要寫目標價 / 停損
- 數字一律引用 trace 內的實際值
- narrative 200-300 字、有投資邏輯而非條列規則
- Value profile 才檢查 value_trap；Momentum 一律 no_concern
</reminder>
"""
