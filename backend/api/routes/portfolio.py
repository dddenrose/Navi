"""Portfolio API — 投資組合 CRUD."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import verify_firebase_token
from services.portfolio_service import (
    add_holding,
    delete_holding,
    get_portfolio_summary,
    list_holdings,
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
    holdings_count: int = 0
    holdings: list[HoldingWithPriceResponse] = []


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
