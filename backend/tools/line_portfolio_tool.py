"""LINE 記錄持股的工具 — 只建立待確認清單，使用者回「確認」後才由 LINE handler 寫入.

只在 LINE 對話裡提供給 agent（services/line/portfolio.py），網頁聊天沒有這兩個工具。
"""

import logging
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from services import portfolio_changes, portfolio_service
from services.line import store
from tools.runtime import line_user_id_from, user_id_from

logger = logging.getLogger(__name__)

PROPOSAL_TOOL_NAMES = frozenset({"propose_trades", "propose_set_holdings"})
# 清單後面接給模型看的說明；agent 補貼清單時用它切開，不會把說明貼給使用者
_MODEL_NOTE = (
    "\n\n（給你的說明：清單已存成待確認，還沒寫入。請把上面的清單原樣貼給使用者，"
    "前面可以加一句話；不要說已經記錄完成。）"
)
_UNIT_HINT = "1 張 = 1000 股；使用者沒講單位就先問，不要猜"


class Trade(BaseModel):
    stock: str = Field(description="股票名稱或代號，例如 台積電、2330、0050")
    action: Literal["buy", "sell"] = Field(description="buy 買進、sell 賣出")
    quantity: float = Field(description="數量，單位看 unit")
    unit: Literal["張", "股"] = Field(description=_UNIT_HINT)
    price: float = Field(description="每股成交價（元）")
    fee: float | None = Field(
        default=None, description="使用者有講實際手續費才填；沒講就省略，系統會估算"
    )
    trade_date: str | None = Field(
        default=None, description="成交日期 YYYY-MM-DD；使用者沒講就省略，預設今天"
    )


class HoldingRow(BaseModel):
    stock: str = Field(description="股票名稱或代號，例如 台積電、2330、0050")
    quantity: float = Field(description="持有數量，單位看 unit")
    unit: Literal["張", "股"] = Field(description="看清楚截圖欄位或使用者說的是張還是股")
    avg_cost: float = Field(description="每股平均成本（成交均價），元")


def _rows(values: list) -> list[dict]:
    return [v.model_dump() if isinstance(v, BaseModel) else dict(v) for v in values]


def _propose(kind: str, rows: list[dict], config: RunnableConfig) -> str:
    user_id = user_id_from(config)
    line_user_id = line_user_id_from(config)
    if not user_id or not line_user_id:
        return "⚠️ 目前只能在 LINE 記錄持股；網頁請到投資組合頁面操作。"
    try:
        holdings = portfolio_service.list_holdings(user_id)
        build = (
            portfolio_changes.build_trades
            if kind == portfolio_changes.TRADES
            else portfolio_changes.build_holdings
        )
        items, errors = build(holdings, rows)
        if errors:
            problems = "\n".join(f"・{e}" for e in errors)
            return f"⚠️ 沒有建立待確認清單：\n{problems}\n請先跟使用者確認這些地方，再重新呼叫。"
        store.save_pending_portfolio(line_user_id, kind, items)
        summary = portfolio_changes.summarize(
            kind, items, holdings, store.PENDING_PORTFOLIO_MINUTES
        )
    except Exception:
        logger.exception("Failed to prepare a portfolio change")
        return "⚠️ 暫時無法建立待確認清單，請使用者稍後再試。不要說已經記錄。"
    return summary + _MODEL_NOTE


@tool
def propose_trades(trades: list[Trade], *, config: RunnableConfig) -> str:
    """記錄使用者已經成交的買進或賣出。只會建立「待確認清單」，使用者回覆「確認」後才寫入。

    使用時機：使用者說已經買了或賣了，例如「今天買 1 張台積電 600」「剛賣掉 500 股鴻海 205」。
    不要用在「可不可以買」「該不該賣」這類分析問題。
    股票、數量（含單位）、價格缺任何一項，先問使用者，不要猜。
    """
    return _propose(portfolio_changes.TRADES, _rows(trades), config)


@tool
def propose_set_holdings(holdings: list[HoldingRow], *, config: RunnableConfig) -> str:
    """把持股直接設成指定的股數與平均成本。只會建立「待確認清單」，使用者回覆「確認」後才寫入。

    使用時機：使用者傳券商 App 的庫存截圖，或說「把台積電改成 3000 股、均價 590」。
    截圖裡的每一檔都要列進來；看不清楚的數字先問使用者，並注意數量欄位是張還是股。
    沒列到的持股不會被動到。
    """
    return _propose(portfolio_changes.HOLDINGS, _rows(holdings), config)


def required_blocks(tool_calls: list[dict]) -> list[str]:
    """這一輪最後建立的待確認清單；agent 會確保它原樣出現在回覆裡."""
    summaries = [
        str(call.get("output") or "").split(_MODEL_NOTE)[0]
        for call in tool_calls
        if call.get("name") in PROPOSAL_TOOL_NAMES
        and str(call.get("output") or "").startswith(portfolio_changes.SUMMARY_HEADER)
    ]
    return summaries[-1:]
