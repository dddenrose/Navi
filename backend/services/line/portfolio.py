"""LINE 上記錄持股：給 agent 的額外工具與規則.

模型只能建立待確認清單（tools/line_portfolio_tool.py），使用者回「確認」後由
handler 呼叫 services.portfolio_changes.apply 寫入。
"""

from services import portfolio_changes
from services.agent_service import AgentExtras
from services.line import store
from tools.line_portfolio_tool import propose_set_holdings, propose_trades, required_blocks

_INSTRUCTIONS = """\
<line_portfolio>
今天是 {today}（台北時間）。
在 LINE 上，使用者可以請你記錄持股。你只能建立「待確認清單」，使用者回覆「確認」後系統才會寫入：
- 使用者說已經買進或賣出（例如「今天買 1 張台積電 600」）→ propose_trades。
  股票、數量、價格缺任何一項就先問，不要猜；數量要標明是張還是股。
- 使用者傳券商的庫存截圖，或要把某檔設成指定的股數和均價 → propose_set_holdings。
  看清楚截圖的數量欄位是張還是股；看不清楚的數字先問使用者。
- 使用者只是在問「可不可以買」「該不該賣」，是分析問題，不要呼叫這兩個工具。
- 工具成功後，把工具回傳的清單原樣貼給使用者，不要說已經寫入；工具回報錯誤時照實轉告。
- 刪除某一檔持股目前只能在網頁的投資組合頁面操作。
- 圖片不是券商庫存截圖時，照一般問題回答圖片內容。
- 清單 {minutes} 分鐘內有效；使用者回「確認」寫入、「取消」放棄，傳其他訊息也會作廢。
</line_portfolio>"""


def agent_extras(line_user_id: str) -> AgentExtras:
    return AgentExtras(
        tools=[propose_trades, propose_set_holdings],
        instructions=_INSTRUCTIONS.format(
            today=portfolio_changes.today_taipei().isoformat(),
            minutes=store.PENDING_PORTFOLIO_MINUTES,
        ),
        tool_context={"line_user_id": line_user_id},
        required_blocks=required_blocks,
    )
