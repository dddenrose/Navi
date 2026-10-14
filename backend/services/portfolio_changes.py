"""持股變更：先整理成待確認清單，使用者確認後才寫入.

給 LINE 用：模型把使用者的話或截圖整理成交易／持股，這裡負責驗證、換算單位、
產生要給使用者核對的清單，以及確認後的實際寫入。數字一律在這裡算，不交給模型。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from services import portfolio_service
from services.portfolio_service import Holding
from services.stock_service import normalize_ticker, search_tw_stocks

logger = logging.getLogger(__name__)

TRADES = "trades"
HOLDINGS = "holdings"
SHARES_PER_LOT = 1000
MAX_ITEMS = 20
_TAIPEI = ZoneInfo("Asia/Taipei")
_CODE_RE = re.compile(r"\d{4,6}[A-Z]?")
_US_TICKER_RE = re.compile(r"[A-Z][A-Z.\-]{0,6}")


def today_taipei() -> date:
    return datetime.now(_TAIPEI).date()


# ── 股票與持股比對 ────────────────────────────────────────────────────────────


def _is_tw(ticker: str) -> bool:
    return ticker.endswith(".TW") or ticker.endswith(".TWO")


def code_of(ticker: str) -> str:
    """2330.TW → 2330；美股原樣回傳."""
    return ticker.split(".")[0] if _is_tw(ticker) else ticker


def resolve_stock(text: str) -> tuple[str, str] | None:
    """股票名稱或代號 → (yfinance ticker, 名稱)；認不得就回 None.

    「台積電 2330」這種名稱加代號的寫法，以代號為準。
    """
    raw = text.strip()
    if not raw:
        return None
    ticker = normalize_ticker(raw)
    if not _is_tw(ticker):
        code = _CODE_RE.search(raw.upper())
        if code:
            ticker = normalize_ticker(code.group(0))
    if _is_tw(ticker):
        code = code_of(ticker)
        name = next((r["name"] for r in search_tw_stocks(code, 20) if r["code"] == code), "")
        return ticker, name or raw
    if _US_TICKER_RE.fullmatch(ticker):
        return ticker, ticker
    return None


def _canonical(stored_ticker: str) -> str:
    try:
        return normalize_ticker(stored_ticker)
    except Exception:
        return stored_ticker.upper()


def find_holding(holdings: list[Holding], ticker: str) -> Holding | None:
    """依股票代號找既有持股.

    網頁存的 ticker 不一致（「0050」「南亞科」「2330.TW」都有），兩邊都轉成
    yfinance ticker 再比，否則同一檔會被當成新持股。
    """
    return next((h for h in holdings if _canonical(h.ticker) == ticker), None)


# ── 驗證與整理 ────────────────────────────────────────────────────────────────


def _to_shares(quantity: Any, unit: str, ticker: str) -> float:
    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        raise ValueError("數量不是數字") from None
    if quantity <= 0:
        raise ValueError("數量必須大於 0")
    if unit not in ("張", "股"):
        raise ValueError("單位要是張或股")
    shares = quantity * SHARES_PER_LOT if unit == "張" else quantity
    if _is_tw(ticker) and abs(shares - round(shares)) > 1e-9:
        raise ValueError("台股股數必須是整數")
    return round(shares) if _is_tw(ticker) else shares


def _positive_price(value: Any, label: str) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}不是數字") from None
    if value <= 0:
        raise ValueError(f"{label}必須大於 0")
    return value


def _trade_date(value: Any) -> str:
    today = today_taipei()
    if not value:
        return today.isoformat()
    try:
        day = date.fromisoformat(str(value))
    except ValueError:
        raise ValueError("日期格式要是 YYYY-MM-DD") from None
    if day > today:
        raise ValueError("日期不能是未來")
    return day.isoformat()


def _stock(text: Any) -> tuple[str, str]:
    resolved = resolve_stock(str(text or ""))
    if resolved is None:
        raise ValueError(f"找不到股票「{text}」")
    return resolved


def build_trades(holdings: list[Holding], trades: list[dict]) -> tuple[list[dict], list[str]]:
    """把模型給的交易轉成可寫入的項目；有任何一筆不合法就回傳錯誤、不產生項目."""
    if not trades:
        return [], ["沒有任何交易"]
    if len(trades) > MAX_ITEMS:
        return [], [f"一次最多 {MAX_ITEMS} 筆"]

    items: list[dict] = []
    errors: list[str] = []
    position: dict[str, float] = {}  # 依序套用同一批交易後的持股，用來檢查賣超
    for index, trade in enumerate(trades, start=1):
        try:
            ticker, name = _stock(trade.get("stock"))
            action = trade.get("action")
            if action not in ("buy", "sell"):
                raise ValueError("要說明是買進還是賣出")
            shares = _to_shares(trade.get("quantity"), trade.get("unit", ""), ticker)
            price = _positive_price(trade.get("price"), "價格")
            fee = trade.get("fee")
            fee = None if fee is None else float(fee)
            if fee is not None and fee < 0:
                raise ValueError("手續費不能是負數")
            if ticker not in position:
                held = find_holding(holdings, ticker)
                position[ticker] = float(held.shares) if held else 0.0
            if action == "sell" and shares > position[ticker] + 1e-9:
                raise ValueError(f"賣出 {shares:,.0f} 股超過目前持有的 {position[ticker]:,.0f} 股")
            position[ticker] += shares if action == "buy" else -shares
            items.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "action": action,
                    "shares": shares,
                    "price": price,
                    "fee": fee,
                    "trade_date": _trade_date(trade.get("trade_date")),
                }
            )
        except ValueError as e:
            errors.append(f"第 {index} 筆：{e}")
    return ([], errors) if errors else (items, [])


def build_holdings(holdings: list[Holding], rows: list[dict]) -> tuple[list[dict], list[str]]:
    """把「設成這個股數和均價」的清單轉成可寫入的項目；規則同 build_trades."""
    if not rows:
        return [], ["沒有任何持股"]
    if len(rows) > MAX_ITEMS:
        return [], [f"一次最多 {MAX_ITEMS} 檔"]

    items: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        try:
            ticker, name = _stock(row.get("stock"))
            if ticker in seen:
                raise ValueError(f"{name} 重複出現")
            seen.add(ticker)
            items.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "shares": _to_shares(row.get("quantity"), row.get("unit", ""), ticker),
                    "avg_cost": _positive_price(row.get("avg_cost"), "均價"),
                }
            )
        except ValueError as e:
            errors.append(f"第 {index} 檔：{e}")
    return ([], errors) if errors else (items, [])


# ── 給使用者看的文字 ──────────────────────────────────────────────────────────

SUMMARY_HEADER = "📝 待確認的持股變更"
CONFIRM_HINT = "回覆「確認」寫入，回覆「取消」放棄。"


def _join(*parts: str) -> str:
    """用空白接起來，但全形括號後面不加空白：「台積電（2330）2,000 股」."""
    text = ""
    for part in parts:
        text += part if not text or text.endswith("）") else f" {part}"
    return text


def _num(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _stock_label(item: dict) -> str:
    code = code_of(item["ticker"])
    return f"{item['name']}（{code}）" if item["name"] and item["name"] != code else code


def _shares_label(item: dict) -> str:
    shares = item["shares"]
    label = f"{_num(shares)} 股"
    if _is_tw(item["ticker"]) and shares >= SHARES_PER_LOT and shares % SHARES_PER_LOT == 0:
        label += f"（{_num(shares / SHARES_PER_LOT)} 張）"
    return label


def describe_trade(item: dict) -> str:
    verb = "買進" if item["action"] == "buy" else "賣出"
    return _join(verb, _stock_label(item), _shares_label(item), f"× {_num(item['price'])} 元")


def _trade_costs(item: dict) -> str:
    est_fee, tax = portfolio_service.estimate_costs(
        item["ticker"], item["action"], item["shares"], item["price"]
    )
    parts = []
    if item["fee"] is not None:
        parts.append(f"手續費 {_num(item['fee'])} 元")
    elif est_fee:
        parts.append(f"手續費約 {_num(est_fee)} 元")
    if tax:
        parts.append(f"證交稅約 {_num(tax)} 元")
    return "、".join(parts)


def describe_holding(item: dict) -> str:
    target = f"{_shares_label(item)}，均價 {_num(item['avg_cost'])} 元"
    return _join(_stock_label(item), "設為", target)


def _describe_holding_change(item: dict, current: Holding | None) -> str:
    if current is None:
        target = f"{_shares_label(item)}，均價 {_num(item['avg_cost'])} 元"
        return _join(_stock_label(item), "新增", target)
    before = f"原本 {_num(current.shares)} 股，均價 {_num(current.avg_cost)} 元"
    return f"{describe_holding(item)}（{before}）"


def summarize(kind: str, items: list[dict], holdings: list[Holding], minutes: int) -> str:
    lines = [f"{SUMMARY_HEADER}（{minutes} 分鐘內有效）"]
    for index, item in enumerate(items, start=1):
        if kind == TRADES:
            costs = _trade_costs(item)
            details = "｜".join(part for part in (costs, item["trade_date"]) if part)
            lines.append(f"{index}. {describe_trade(item)}｜{details}")
        else:
            current = find_holding(holdings, item["ticker"])
            lines.append(f"{index}. {_describe_holding_change(item, current)}")
    if kind == HOLDINGS:
        lines.append("沒列在這裡的持股不會變動。")
    lines.append(CONFIRM_HINT)
    return "\n".join(lines)


# ── 確認後寫入 ────────────────────────────────────────────────────────────────


def apply(user_id: str, kind: str, items: list[dict]) -> str:
    """依序寫入，回傳給使用者的結果；單筆失敗不影響其他筆.

    每筆都重新比對持股：確認前使用者可能在網頁改過，而且前一筆可能剛新增或清空同一檔。
    """
    done: list[str] = []
    failed: list[str] = []
    for item in items:
        holdings = portfolio_service.list_holdings(user_id)
        current = find_holding(holdings, item["ticker"])
        label = describe_trade(item) if kind == TRADES else describe_holding(item)
        try:
            if kind == TRADES:
                portfolio_service.add_transaction(
                    user_id,
                    ticker=item["ticker"],
                    action=item["action"],
                    shares=item["shares"],
                    price=item["price"],
                    trade_date=item["trade_date"],
                    name=item["name"],
                    fee=item["fee"],
                    holding_id=current.id if current else None,
                )
            elif current:
                portfolio_service.update_holding(
                    user_id, current.id, shares=item["shares"], avg_cost=item["avg_cost"]
                )
            else:
                portfolio_service.add_holding(
                    user_id, item["ticker"], item["shares"], item["avg_cost"], name=item["name"]
                )
            done.append(label)
        except ValueError as e:
            failed.append(f"{label}：{e}")
        except Exception:
            logger.exception("Portfolio change failed for %s", item.get("ticker"))
            failed.append(f"{label}：寫入失敗，請稍後再試")

    lines: list[str] = []
    if done:
        lines.append(f"✅ 已寫入 {len(done)} 筆")
        lines.extend(f"・{line}" for line in done)
    if failed:
        lines.append(f"⚠️ 有 {len(failed)} 筆沒有寫入")
        lines.extend(f"・{line}" for line in failed)
    lines.append("輸入「我的持股」可以看最新的持股。")
    return "\n".join(lines)
