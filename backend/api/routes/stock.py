"""Stock data API — 股票數據查詢."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import verify_firebase_token
from models.schemas import FundamentalResponse, StockOverview, TechnicalResponse
from services.stock_service import (
    get_fundamental_data,
    get_stock_overview,
    get_technical_indicators,
    normalize_ticker,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/stock",
    tags=["stock"],
    dependencies=[Depends(verify_firebase_token)],
)


@router.get("/{ticker}", response_model=StockOverview)
async def get_stock(ticker: str):
    """取得股票概覽（即時價格、漲跌幅、成交量）。"""
    try:
        data = get_stock_overview(ticker)
        return StockOverview(**asdict(data))
    except Exception as e:
        logger.exception("Failed to get stock overview for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/technical", response_model=TechnicalResponse)
async def get_technical(ticker: str, period: str = "3mo"):
    """技術面分析（MA, RSI, MACD, KD, 布林通道）。"""
    try:
        data = get_technical_indicators(ticker, period=period)
        return TechnicalResponse(**asdict(data))
    except Exception as e:
        logger.exception("Failed to get technical indicators for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/fundamental", response_model=FundamentalResponse)
async def get_fundamental(ticker: str):
    """基本面數據（PE, PB, ROE, EPS 等）。"""
    try:
        data = get_fundamental_data(ticker)
        return FundamentalResponse(**asdict(data))
    except Exception as e:
        logger.exception("Failed to get fundamental data for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e))
