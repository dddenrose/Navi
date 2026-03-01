"""Stock data API — 股票數據查詢."""

from fastapi import APIRouter
from models.schemas import StockOverview

router = APIRouter(prefix="/api/stock", tags=["stock"])


@router.get("/{ticker}", response_model=StockOverview)
async def get_stock(ticker: str):
    """取得股票概覽。Phase 1 先回傳 placeholder。"""
    return StockOverview(ticker=ticker, name="Placeholder")
