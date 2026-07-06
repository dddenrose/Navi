"""Portfolio API — 投資組合 CRUD."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import verify_firebase_token
from services.portfolio_service import (
    add_holding,
    add_transaction,
    delete_holding,
    estimate_costs,
    get_portfolio_summary,
    list_holdings,
    list_transactions,
    update_holding,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/portfolio",
    tags=["portfolio"],
    dependencies=[Depends(verify_firebase_token)],
)


# ── Request / Response models ────────────────────────────────────────────────


class AddHoldingRequest(BaseModel):
    ticker: str = Field(..., min_length=1, description="股票代碼，例如 2330.TW")
    shares: float = Field(..., gt=0, description="持股張數/股數")
    avg_cost: float = Field(..., gt=0, description="平均成本")
    name: str = Field("", description="股票名稱（選填）")
    notes: str = Field("", description="備註（選填）")


class UpdateHoldingRequest(BaseModel):
    shares: float | None = Field(None, gt=0, description="持股張數/股數")
    avg_cost: float | None = Field(None, gt=0, description="平均成本")
    notes: str | None = Field(None, description="備註")


class HoldingResponse(BaseModel):
    id: str
    ticker: str
    name: str = ""
    shares: float
    avg_cost: float
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


class HoldingWithPriceResponse(HoldingResponse):
    current_price: float | None = None
    market_value: float = 0.0
    cost_basis: float = 0.0
    pnl: float = 0.0
    pnl_percent: float = 0.0
    currency: str = ""


class PortfolioSummaryResponse(BaseModel):
    total_value: float = 0.0
    total_cost: float = 0.0
    total_pnl: float = 0.0
    total_pnl_percent: float = 0.0
    realized_pnl: float = 0.0
    holdings_count: int = 0
    holdings: list[HoldingWithPriceResponse] = []


class AddTransactionRequest(BaseModel):
    ticker: str = Field(..., min_length=1, description="股票代碼，例如 2330.TW")
    action: str = Field(..., pattern="^(buy|sell)$", description="buy / sell")
    shares: float = Field(..., gt=0, description="股數")
    price: float = Field(..., gt=0, description="成交價")
    trade_date: str = Field("", description="交易日 YYYY-MM-DD（空 = 今天）")
    name: str = Field("", description="股票名稱（選填）")
    notes: str = Field("", description="備註（選填）")
    fee: float | None = Field(
        None, ge=0, description="手續費（不填以台股牌告費率估算，可含折讓）"
    )


class TransactionResponse(BaseModel):
    id: str
    ticker: str
    name: str = ""
    action: str
    shares: float
    price: float
    fee: float = 0.0
    tax: float = 0.0
    amount: float = 0.0
    realized_pnl: float = 0.0
    trade_date: str = ""
    notes: str = ""
    created_at: str = ""


# ── Routes ────────────────────────────────────────────────────────────────────


def _get_uid(user: dict) -> str:
    return user.get("uid", "")


@router.get("", response_model=PortfolioSummaryResponse)
async def get_portfolio(user: dict = Depends(verify_firebase_token)):
    """取得使用者投資組合（含即時市值損益）."""
    try:
        summary = get_portfolio_summary(_get_uid(user))
        return PortfolioSummaryResponse(**asdict(summary))
    except Exception as e:
        logger.exception("Failed to get portfolio for user %s", _get_uid(user))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/holdings", response_model=list[HoldingResponse])
async def get_holdings(user: dict = Depends(verify_firebase_token)):
    """列出所有持股（不含即時價格，較快）."""
    try:
        holdings = list_holdings(_get_uid(user))
        return [HoldingResponse(**asdict(h)) for h in holdings]
    except Exception as e:
        logger.exception("Failed to list holdings")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/holdings", response_model=HoldingResponse, status_code=201)
async def create_holding(
    req: AddHoldingRequest,
    user: dict = Depends(verify_firebase_token),
):
    """新增持股."""
    try:
        h = add_holding(
            user_id=_get_uid(user),
            ticker=req.ticker,
            shares=req.shares,
            avg_cost=req.avg_cost,
            name=req.name,
            notes=req.notes,
        )
        return HoldingResponse(**asdict(h))
    except Exception as e:
        logger.exception("Failed to add holding")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/holdings/{holding_id}", response_model=HoldingResponse)
async def modify_holding(
    holding_id: str,
    req: UpdateHoldingRequest,
    user: dict = Depends(verify_firebase_token),
):
    """修改持股."""
    try:
        h = update_holding(
            user_id=_get_uid(user),
            holding_id=holding_id,
            shares=req.shares,
            avg_cost=req.avg_cost,
            notes=req.notes,
        )
        return HoldingResponse(**asdict(h))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update holding %s", holding_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transactions", response_model=TransactionResponse, status_code=201)
async def create_transaction(
    req: AddTransactionRequest,
    user: dict = Depends(verify_firebase_token),
):
    """記錄一筆買/賣交易（自動計算台股手續費/證交稅並更新持股與已實現損益）."""
    try:
        tx = add_transaction(
            user_id=_get_uid(user),
            ticker=req.ticker,
            action=req.action,
            shares=req.shares,
            price=req.price,
            trade_date=req.trade_date,
            name=req.name,
            notes=req.notes,
            fee=req.fee,
        )
        return TransactionResponse(**asdict(tx))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Failed to add transaction")
        raise HTTPException(status_code=500, detail="交易記錄失敗，請稍後再試")


@router.get("/transactions", response_model=list[TransactionResponse])
async def get_transactions(
    limit: int = 100,
    user: dict = Depends(verify_firebase_token),
):
    """列出交易紀錄（新→舊）."""
    try:
        txs = list_transactions(_get_uid(user), limit=limit)
        return [TransactionResponse(**asdict(t)) for t in txs]
    except Exception:
        logger.exception("Failed to list transactions")
        raise HTTPException(status_code=500, detail="無法取得交易紀錄，請稍後再試")


@router.get("/transactions/estimate")
async def estimate_transaction_costs(
    ticker: str,
    action: str,
    shares: float,
    price: float,
    user: dict = Depends(verify_firebase_token),
):
    """估算一筆交易的手續費與證交稅（供前端輸入時即時顯示）."""
    fee, tax = estimate_costs(ticker, action, shares, price)
    return {"fee": fee, "tax": tax}


@router.delete("/holdings/{holding_id}")
async def remove_holding(
    holding_id: str,
    user: dict = Depends(verify_firebase_token),
):
    """刪除持股."""
    try:
        delete_holding(_get_uid(user), holding_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to delete holding %s", holding_id)
        raise HTTPException(status_code=500, detail=str(e))
