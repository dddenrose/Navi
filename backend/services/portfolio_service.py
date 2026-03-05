"""Portfolio Service — 投資組合 CRUD + 即時市值計算 (Firestore)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from google.cloud.firestore_v1.base_query import FieldFilter

from services.firestore_client import get_db
from services.stock_service import get_stock_overview

logger = logging.getLogger(__name__)

# ── Firestore 集合名稱 ──────────────────────────────────────────────────────

PORTFOLIOS_COL = "portfolios"  # portfolios/{user_id}
HOLDINGS_SUB = "holdings"       # portfolios/{user_id}/holdings/{holding_id}


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
    total_pnl: float = 0.0
    total_pnl_percent: float = 0.0
    holdings_count: int = 0
    holdings: list[HoldingWithPrice] = field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _holdings_ref(user_id: str):
    """Return reference to a user's holdings sub-collection."""
    db = get_db()
    return db.collection(PORTFOLIOS_COL).document(user_id).collection(HOLDINGS_SUB)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── CRUD ─────────────────────────────────────────────────────────────────────

def add_holding(user_id: str, ticker: str, shares: float, avg_cost: float, name: str = "", notes: str = "") -> Holding:
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


def update_holding(user_id: str, holding_id: str, shares: float | None = None, avg_cost: float | None = None, notes: str | None = None) -> Holding:
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
    return Holding(id=holding_id, **{k: merged[k] for k in Holding.__dataclass_fields__ if k != "id" and k in merged})


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
        holdings.append(Holding(
            id=doc.id,
            ticker=d.get("ticker", ""),
            name=d.get("name", ""),
            shares=d.get("shares", 0),
            avg_cost=d.get("avg_cost", 0),
            notes=d.get("notes", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        ))
    return holdings


# ── 即時市值計算 ─────────────────────────────────────────────────────────────

def get_portfolio_summary(user_id: str) -> PortfolioSummary:
    """取得投資組合摘要（含即時市值損益）."""
    holdings = list_holdings(user_id)
    if not holdings:
        return PortfolioSummary()

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

        enriched.append(HoldingWithPrice(
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
        ))

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0.0

    return PortfolioSummary(
        total_value=round(total_value, 2),
        total_cost=round(total_cost, 2),
        total_pnl=round(total_pnl, 2),
        total_pnl_percent=round(total_pnl_pct, 2),
        holdings_count=len(enriched),
        holdings=enriched,
    )
