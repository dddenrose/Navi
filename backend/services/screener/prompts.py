"""Stage 3 — LLM interpreter prompts, schema, and post-processing validators.

設計原則（v2）：
  - **Schema 只描述「這個欄位是什麼」**，不放行為規則 → 避免與 system prompt 雙重維護。
  - **System prompt 動態組裝**：依 profile 注入不同 horizon / value-trap playbook。
  - **數字 white-list**：user prompt 顯式列出允許引用的數字，搭配 `validate_narrative`
    後處理偵測幻覺。
  - **質性接地（grounding）**：具名業務事實（客戶、市占、產品線、事件）只能來自
    輸入資料，禁止模型以訓練記憶補充——記憶會過時、會編造，且無法被數字白名單攔截。
  - **narrative vs key_context 角色明確化**：
      narrative = WHY NOW（投資論述）；key_context = 輸入資料內的補充脈絡。

公開 API：
  - StockInterpretation                              — Pydantic schema
  - build_interpreter_system_prompt(profile)         — 動態 system prompt
  - build_interpreter_user_prompt(profile, xml, wl)  — user prompt（含 white-list）
  - format_allowed_numbers(allowed)                  — 把白名單 dict 渲染成文字
  - validate_narrative(text, allowed)                — 抓出 narrative 中未授權的數字
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

# ── Schema ──────────────────────────────────────────────────────────────────
# 注意：description 僅描述欄位「是什麼」，行為規範一律寫在 system prompt，
# 避免規則漂移（schema desc 與 prompt 不一致時模型行為會分裂）。


class StockInterpretation(BaseModel):
    """Stage 3 對單一資格化個股的質性解讀（schema-only 欄位描述）。"""

    narrative: str = Field(
        description=(
            "投資論述（thesis）。回答「為何此刻值得關注」，整合"
            "scoring_trace 中通過的條件成連貫論證。"
        ),
    )
    key_context: list[str] = Field(
        default_factory=list,
        description=(
            "補充脈絡（background）。條列輸入資料（snapshot / 規則明細 / 產業分類）"
            "中存在、但 narrative 沒展開的事實。"
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="投資前需注意的風險或量化規則未捕捉到的隱憂。",
    )
    value_trap_check: Literal["no_concern", "watch", "warning", "not_applicable"] = Field(
        default="not_applicable",
        description=(
            "Value Trap 判讀。no_concern = 已檢查無虞 / watch = 需觀察 / "
            "warning = 疑似價值陷阱 / not_applicable = 本策略不做此檢查。"
            "「沒有檢查」不得填 no_concern。"
        ),
    )
    value_trap_reason: str = Field(
        default="",
        description="value_trap_check != no_concern 時的具體依據；否則留空。",
    )


# ── System prompt（動態組裝）─────────────────────────────────────────────────

_BASE_ROLE = """\
<role>
你是 Navi 智能選股的投資解讀員。你看到的個股已通過量化規則的資格化篩選。
你的工作是把規則結果翻譯成投資邏輯，**不重新做篩選決策**。
</role>
"""

_BEHAVIOR_RULES = """\
<behavior_rules>
1. 不重新評估資格：規則已決定它通過。發現疑慮時寫進 warnings，禁止拒絕產出。
2. 不寫目標價、停損、買賣建議、信心分數：已由 valuation 規則計算。
3. 數字白名單：narrative / key_context / warnings / value_trap_reason 內
   所有 PE、PB、ROE、殖利率、營收成長、報酬率等量化數字 **只能引用**
   <allowed_numbers> 中列出的值（可換算單位但不可變動數量級）。
   未列出的數字一律不要寫。若需描述趨勢，用文字而非編造數字。
4. 質性事實接地：具名業務事實——特定客戶名稱、供應鏈關係、市占率、產品線、
   訂單、擴產、併購或其他公司事件——**只能來自輸入資料**（snapshot、規則明細、
   產業分類）。輸入資料沒有的一律不要寫：你的訓練知識可能已過時或有誤，
   寫出來會被使用者當成已查證的事實。允許產業層級的一般常識框架
   （如「半導體具循環性」），但不得指涉具體公司事實。
5. 不確定性語氣：用「在 X 假設下」「若 Y 不惡化」「目前訊號顯示」等條件式語氣，
   禁止「保證」「必漲」「零風險」「肯定」等絕對化用詞。
6. 語言：繁體中文。
</behavior_rules>
"""

_FIELD_GUIDE = """\
<field_guide>
- narrative（約 200-300 中文字）：**WHY NOW**。組織通過的必要條件 + 加分條件，
  論證「為何此刻是合理的進場觀察點」。一篇連貫論述，不條列規則；
  不得引入輸入資料以外的公司業務事實。
- key_context（0-5 條）：**輸入資料內的補充脈絡**。條列 snapshot、規則明細、
  產業分類中存在、但 narrative 沒展開的事實（如產業位階、估值相對位置、
  籌碼訊號）。輸入資料不足時寧可少列或留空，禁止以訓練知識補充客戶、
  市占、產品線或近期事件。**不得**與 narrative 重複論點。
- warnings（1-4 條）：規則沒抓到的潛在風險，僅限兩類：(a) 由輸入資料推得的
  隱憂（如配息率偏高、動能過熱）；(b) 產業層級的一般性風險（循環性、匯率、
  地緣），用條件式語氣。禁止具名的公司事件宣稱（特定訴訟、特定客戶流失等）。
  每條 ≤ 30 字。
- value_trap_check / value_trap_reason：見下方 value-trap 區段（若存在）。
</field_guide>
"""

_VALUE_HORIZON = """\
<horizon>
投資視野：1-3 年中長期持有。論述焦點應放在公司基本面韌性與估值修復空間，
而非短線價格動能。
</horizon>
"""

_MOMENTUM_HORIZON = """\
<horizon>
投資視野：1-3 個月波段。論述焦點應放在動能延續性與籌碼面訊號，
而非長期估值。
</horizon>
"""

_VALUE_TRAP_PLAYBOOK = """\
<value_trap_playbook>
Value Trap = 「數字漂亮但業務正在衰退」的標的。請逐一檢查以下訊號：

1. **Dividend trap**：高殖利率 + 6M 報酬大幅落後大盤
   → 市場已用股價反映悲觀預期。

2. **配息品質**：估算配息率 ≈ 殖利率 × PE。
   - 配息率 > 80% → watch（盈餘幾乎全配，再投資能量低）
   - 配息率 > 100% 或 FCF 正年數 < 2 → warning（靠資產 / 借款配息）

3. **低 PE 陷阱**：PE 顯著低於產業中位 **同時** 營收 CAGR 3Y 接近 0 或負
   → 衰退中的成熟產業，估值折價有結構原因。

4. **盈餘品質**：近 4 季毛利率標準差大、或最新一季營收 YoY 由正轉負
   → 獲利可能受一次性項目支撐，watch。

5. **基本面慢性惡化**：ROE 3Y 平均尚可但配息率高 + 營收成長失速
   → 溫水煮青蛙，watch。

判讀後填 value_trap_check（no_concern / watch / warning）。
非 no_concern 時，value_trap_reason 必須明確引用上述哪條訊號 + 對應數字
（數字仍受 <allowed_numbers> 白名單限制）。
</value_trap_playbook>
"""

_MOMENTUM_VALUE_TRAP_NOTE = """\
<value_trap_note>
本檔為 Momentum profile，不做價值陷阱檢查：value_trap_check 一律填
"not_applicable"，value_trap_reason 留空。
</value_trap_note>
"""


def build_interpreter_system_prompt(profile: str) -> str:
    """依 profile 動態組裝 system prompt。Momentum 不載入 value-trap playbook。"""
    parts = [_BASE_ROLE, _BEHAVIOR_RULES, _FIELD_GUIDE]
    if profile == "value":
        parts.extend([_VALUE_HORIZON, _VALUE_TRAP_PLAYBOOK])
    else:
        parts.extend([_MOMENTUM_HORIZON, _MOMENTUM_VALUE_TRAP_NOTE])
    return "\n".join(parts)


# 保留舊符號名稱以維持回溯相容（預設給 value playbook，內含完整規則描述）
INTERPRETER_SYSTEM_PROMPT = build_interpreter_system_prompt("value")


# ── User prompt + 數字白名單 ─────────────────────────────────────────────────


def format_allowed_numbers(allowed: dict[str, str]) -> str:
    """把 `{label: formatted_value}` 渲染成 XML 區塊。

    formatted_value 應已含單位（例：'15.2%' / '22.5' / '125 元'）。
    None 值請勿傳入；呼叫端負責過濾。
    """
    if not allowed:
        return "<allowed_numbers/>"
    lines = ["<allowed_numbers>"]
    for k, v in allowed.items():
        lines.append(f"  <item label=\"{k}\">{v}</item>")
    lines.append("</allowed_numbers>")
    return "\n".join(lines)


def build_interpreter_user_prompt(
    profile: str,
    snapshot_xml: str,
    allowed_numbers_xml: str,
) -> str:
    return f"""\
<task>
策略: {profile}
請對下面這檔資格化個股輸出 StockInterpretation。
</task>

{snapshot_xml}

{allowed_numbers_xml}

<reminder>
- 只能引用 <allowed_numbers> 列出的數字；其他數字一律改用文字描述趨勢。
- 業務事實（客戶、市占、產品線、事件）只能來自上方輸入資料；輸入沒有的不要寫。
- narrative 約 200-300 中文字，論證 WHY NOW；key_context 只條列輸入資料內的補充脈絡。
- 不寫目標價、停損、買賣建議；用條件式語氣表達不確定性。
</reminder>
"""


# ── 後處理：narrative 數字幻覺偵測 ──────────────────────────────────────────

# 抓出帶單位的數字 token：百分比 / 倍數 / 元 / 萬 / 億 / 點
_NUMBER_TOKEN_RE = re.compile(
    r"(?P<num>-?\d+(?:\.\d+)?)\s*(?P<unit>%|倍|x|X|元|塊|億|萬|點|個百分點|pp)"
)

# 允許的字面 token（如「3 年」「4 季」這類常識計數不檢查）— 已透過 unit 過濾，
# 沒有單位的純整數不會被抓進來。


def _normalize_number_to_pct(value: float, unit: str) -> float | None:
    """把帶單位的字面值轉換成「百分比」（與 ROE / 殖利率 / 報酬率比對基準）。"""
    if unit in {"%", "個百分點", "pp"}:
        return value
    return None


def validate_narrative(
    text: str,
    allowed: dict[str, float],
    *,
    tolerance_pct: float = 0.5,  # 絕對百分點容忍（例：寫 15.0%，允許 14.5~15.5）
    tolerance_rel: float = 0.05,  # 相對誤差容忍（適用倍數、價格）
) -> list[str]:
    """掃描 narrative / 任意自由文字，回傳「未授權」的數字 token 清單。

    Args:
        text: 待檢查文字。
        allowed: `{label: numeric_value}`，numeric_value 為原始數值
                 （比率用小數，例：ROE 0.152；倍數用倍數，例：PE 22.5）。
        tolerance_pct: 百分比比對的絕對容忍（單位：百分點）。
        tolerance_rel: 倍數 / 絕對值比對的相對容忍。

    Returns:
        違規 token 字串清單。為空代表無幻覺。
    """
    if not text:
        return []

    # 把白名單拆成兩個視角：百分比基準（× 100）與原始值
    allowed_pct: list[float] = []
    allowed_raw: list[float] = []
    for v in allowed.values():
        if v is None:
            continue
        allowed_raw.append(v)
        # 把小數比率（|v| < 1）轉成百分比基準供比對
        if abs(v) < 1.5:
            allowed_pct.append(v * 100)
        else:
            allowed_pct.append(v)  # 已是百分比量級

    violations: list[str] = []
    for m in _NUMBER_TOKEN_RE.finditer(text):
        try:
            num = float(m.group("num"))
        except ValueError:
            continue
        unit = m.group("unit")
        token = m.group(0).strip()

        if unit in {"%", "個百分點", "pp"}:
            if not any(abs(num - a) <= tolerance_pct for a in allowed_pct):
                violations.append(token)
        else:
            # 倍數 / 元 / 點 → 用相對誤差比對 raw 白名單
            ok = False
            for a in allowed_raw:
                if a == 0:
                    ok = ok or num == 0
                    continue
                if abs((num - a) / a) <= tolerance_rel:
                    ok = True
                    break
            if not ok:
                violations.append(token)

    return violations
