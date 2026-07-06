"""Portfolio Service — 投資組合 CRUD + 即時市值計算 (Firestore)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from services.firestore_client import get_db
from services.stock_service import get_stock_overview

logger = logging.getLogger(__name__)

# ── Firestore 集合名稱 ──────────────────────────────────────────────────────

PORTFOLIOS_COL = "portfolios"  # portfolios/{user_id}
HOLDINGS_SUB = "holdings"  # portfolios/{user_id}/holdings/{holding_id}
TRANSACTIONS_SUB = "transactions"  # portfolios/{user_id}/transactions/{tx_id}

# 台股交易成本（與回測引擎一致）
TW_COMMISSION_RATE = 0.001425
TW_MIN_COMMISSION = 20.0
TW_SELL_TAX_RATE = 0.003


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class Holding:
    """單一持股."""

    id: str = ""
    ticker: str = ""
    name: str = ""
    shares: float = 0.0
    avg_cost: float = 0.0
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class HoldingWithPrice(Holding):
    """含即時市值的持股."""

    current_price: float | None = None
    market_value: float = 0.0
    cost_basis: float = 0.0
    pnl: float = 0.0
    pnl_percent: float = 0.0
    currency: str = ""


@dataclass
class PortfolioSummary:
    """投資組合摘要."""

    total_value: float = 0.0
    total_cost: float = 0.0
    total_pnl: float = 0.0  # 未實現損益
    total_pnl_percent: float = 0.0
    realized_pnl: float = 0.0  # 已實現損益（來自賣出交易，含手續費與證交稅）
    holdings_count: int = 0
    holdings: list[HoldingWithPrice] = field(default_factory=list)


@dataclass
class Transaction:
    """單筆買賣交易（帳本；不可修改，只能沖銷後重記）."""

    id: str = ""
    ticker: str = ""
    name: str = ""
    action: str = ""  # buy / sell
    shares: float = 0.0
    price: float = 0.0
    fee: float = 0.0  # 手續費
    tax: float = 0.0  # 證交稅（賣出）
    amount: float = 0.0  # 成交金額（不含費稅）
    realized_pnl: float = 0.0  # 賣出時實現損益（含費稅；買入為 0）
    trade_date: str = ""  # YYYY-MM-DD
    notes: str = ""
    created_at: str = ""


# ── Helpers ──────────────────────────────────────────────────────────────────


def _holdings_ref(user_id: str):
    """Return reference to a user's holdings sub-collection."""
    db = get_db()
    return db.collection(PORTFOLIOS_COL).document(user_id).collection(HOLDINGS_SUB)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── CRUD ─────────────────────────────────────────────────────────────────────


def add_holding(
    user_id: str, ticker: str, shares: float, avg_cost: float, name: str = "", notes: str = ""
) -> Holding:
    """新增一筆持股."""
    ref = _holdings_ref(user_id)
    now = _now_iso()
    data = {
        "ticker": ticker.upper(),
        "name": name,
        "shares": shares,
        "avg_cost": avg_cost,
        "notes": notes,
        "created_at": now,
        "updated_at": now,
    }
    doc_ref = ref.add(data)[1]  # returns (timestamp, doc_ref)
    return Holding(id=doc_ref.id, **data)


def update_holding(
    user_id: str,
    holding_id: str,
    shares: float | None = None,
    avg_cost: float | None = None,
    notes: str | None = None,
) -> Holding:
    """修改持股（部分更新）."""
    ref = _holdings_ref(user_id).document(holding_id)
    doc = ref.get()
    if not doc.exists:
        raise ValueError(f"Holding {holding_id} not found")

    updates: dict = {"updated_at": _now_iso()}
    if shares is not None:
        updates["shares"] = shares
    if avg_cost is not None:
        updates["avg_cost"] = avg_cost
    if notes is not None:
        updates["notes"] = notes

    ref.update(updates)
    merged = {**doc.to_dict(), **updates}
    return Holding(
        id=holding_id,
        **{k: merged[k] for k in Holding.__dataclass_fields__ if k != "id" and k in merged},
    )


def delete_holding(user_id: str, holding_id: str) -> bool:
    """刪除持股."""
    ref = _holdings_ref(user_id).document(holding_id)
    doc = ref.get()
    if not doc.exists:
        raise ValueError(f"Holding {holding_id} not found")
    ref.delete()
    return True


def list_holdings(user_id: str) -> list[Holding]:
    """列出所有持股."""
    docs = _holdings_ref(user_id).stream()
    holdings = []
    for doc in docs:
        d = doc.to_dict()
        holdings.append(
            Holding(
                id=doc.id,
                ticker=d.get("ticker", ""),
                name=d.get("name", ""),
                shares=d.get("shares", 0),
                avg_cost=d.get("avg_cost", 0),
                notes=d.get("notes", ""),
                created_at=d.get("created_at", ""),
                updated_at=d.get("updated_at", ""),
            )
        )
    return holdings


# ── 交易紀錄（帳本制）────────────────────────────────────────────────────────


def _transactions_ref(user_id: str):
    db = get_db()
    return db.collection(PORTFOLIOS_COL).document(user_id).collection(TRANSACTIONS_SUB)


def _is_tw_ticker(ticker: str) -> bool:
    return ticker.upper().endswith(".TW") or ticker.upper().endswith(".TWO")


def estimate_costs(ticker: str, action: str, shares: float, price: float) -> tuple[float, float]:
    """估算台股手續費與證交稅（美股回 0）。回傳 (fee, tax)."""
    amount = shares * price
    if not _is_tw_ticker(ticker) or amount <= 0:
        return (0.0, 0.0)
    fee = round(max(TW_MIN_COMMISSION, amount * TW_COMMISSION_RATE), 2)
    tax = round(amount * TW_SELL_TAX_RATE, 2) if action == "sell" else 0.0
    return (fee, tax)


def add_transaction(
    user_id: str,
    ticker: str,
    action: str,
    shares: float,
    price: float,
    trade_date: str = "",
    name: str = "",
    notes: str = "",
    fee: float | None = None,
) -> Transaction:
    """記錄一筆買/賣交易，並同步維護持股（平均成本法）.

    - 買入：新平均成本 =（原成本基礎 + 成交金額 + 手續費）÷ 新總股數（成本內含費用）
    - 賣出：已實現損益 = 賣出淨額（扣費稅）－ 股數 × 平均成本；平均成本不變，
      股數歸零時刪除該持股
    - fee 可自行覆寫（券商折讓），不填則以台股牌告費率估算
    """
    if action not in ("buy", "sell"):
        raise ValueError("action 必須是 buy 或 sell")
    if shares <= 0 or price <= 0:
        raise ValueError("shares 與 price 必須為正數")

    ticker = ticker.upper()
    amount = round(shares * price, 2)
    est_fee, tax = estimate_costs(ticker, action, shares, price)
    if fee is None:
        fee = est_fee
    fee = round(fee, 2)

    # 找到既有持股（同 ticker 只取第一筆；帳本制下每檔應只有一筆 holding）
    holdings_ref = _holdings_ref(user_id)
    existing = None
    for doc in holdings_ref.stream():
        d = doc.to_dict() or {}
        if d.get("ticker", "").upper() == ticker:
            existing = (doc.id, d)
            break

    now = _now_iso()
    realized_pnl = 0.0

    if action == "buy":
        if existing:
            hid, d = existing
            old_shares = float(d.get("shares", 0))
            old_cost_basis = old_shares * float(d.get("avg_cost", 0))
            new_shares = old_shares + shares
            new_avg = (old_cost_basis + amount + fee) / new_shares
            holdings_ref.document(hid).update(
                {"shares": new_shares, "avg_cost": round(new_avg, 4), "updated_at": now}
            )
        else:
            holdings_ref.add(
                {
                    "ticker": ticker,
                    "name": name,
                    "shares": shares,
                    "avg_cost": round((amount + fee) / shares, 4),
                    "notes": "",
                    "created_at": now,
                    "updated_at": now,
                }
            )
    else:  # sell
        if not existing:
            raise ValueError(f"未持有 {ticker}，無法賣出")
        hid, d = existing
        held = float(d.get("shares", 0))
        if shares > held + 1e-9:
            raise ValueError(f"賣出股數 {shares} 超過持有股數 {held}")
        avg_cost = float(d.get("avg_cost", 0))
        net_proceeds = amount - fee - tax
        realized_pnl = round(net_proceeds - shares * avg_cost, 2)
        remaining = held - shares
        if remaining <= 1e-9:
            holdings_ref.document(hid).delete()
        else:
            holdings_ref.document(hid).update(
                {"shares": remaining, "updated_at": now}
            )

    tx_data = {
        "ticker": ticker,
        "name": name or (existing[1].get("name", "") if existing else ""),
        "action": action,
        "shares": shares,
        "price": price,
        "fee": fee,
        "tax": tax,
        "amount": amount,
        "realized_pnl": realized_pnl,
        "trade_date": trade_date or now[:10],
        "notes": notes,
        "created_at": now,
    }
    tx_ref = _transactions_ref(user_id).add(tx_data)[1]
    return Transaction(id=tx_ref.id, **tx_data)


def list_transactions(user_id: str, limit: int = 200) -> list[Transaction]:
    """列出交易紀錄（新→舊）."""
    docs = _transactions_ref(user_id).stream()
    txs = []
    for doc in docs:
        d = doc.to_dict() or {}
        txs.append(
            Transaction(
                id=doc.id,
                **{
                    k: d.get(k, Transaction.__dataclass_fields__[k].default)
                    for k in Transaction.__dataclass_fields__
                    if k != "id"
                },
            )
        )
    txs.sort(key=lambda t: (t.trade_date, t.created_at), reverse=True)
    return txs[:limit]


def get_realized_pnl(user_id: str) -> float:
    """賣出交易的已實現損益總和（含手續費與證交稅）."""
    return round(sum(t.realized_pnl for t in list_transactions(user_id, limit=10_000)), 2)


# ── 即時市值計算 ─────────────────────────────────────────────────────────────


def get_portfolio_summary(user_id: str) -> PortfolioSummary:
    """取得投資組合摘要（含即時市值損益與已實現損益）."""
    try:
        realized = get_realized_pnl(user_id)
    except Exception:
        logger.warning("Failed to compute realized pnl for %s", user_id, exc_info=True)
        realized = 0.0

    holdings = list_holdings(user_id)
    if not holdings:
        return PortfolioSummary(realized_pnl=realized)

    enriched: list[HoldingWithPrice] = []
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        cost_basis = h.shares * h.avg_cost
        total_cost += cost_basis

        try:
            overview = get_stock_overview(h.ticker)
            price = overview.price or 0.0
            currency = overview.currency
        except Exception:
            logger.warning("Failed to fetch price for %s, using avg_cost", h.ticker)
            price = h.avg_cost
            currency = ""

        market_value = h.shares * price
        total_value += market_value
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0.0

        enriched.append(
            HoldingWithPrice(
                id=h.id,
                ticker=h.ticker,
                name=h.name,
                shares=h.shares,
                avg_cost=h.avg_cost,
                notes=h.notes,
                created_at=h.created_at,
                updated_at=h.updated_at,
                current_price=price,
                market_value=round(market_value, 2),
                cost_basis=round(cost_basis, 2),
                pnl=round(pnl, 2),
                pnl_percent=round(pnl_pct, 2),
                currency=currency,
            )
        )

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0.0

    return PortfolioSummary(
        total_value=round(total_value, 2),
        total_cost=round(total_cost, 2),
        total_pnl=round(total_pnl, 2),
        total_pnl_percent=round(total_pnl_pct, 2),
        realized_pnl=realized,
        holdings_count=len(enriched),
        holdings=enriched,
    )
