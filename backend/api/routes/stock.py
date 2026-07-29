"""Stock data API — 股票數據查詢."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_feature_access
from models.schemas import (
    FundamentalResponse,
    IndustryPeResponse,
    MonthlyRevenueResponse,
    NewsResponse,
    PopularResponse,
    StockOverview,
    TechnicalResponse,
)
from services.industry_valuation_service import get_industry_pe
from services.institutional_service import get_institutional_data
from services.margin_service import get_margin_data
from services.news_service import get_stock_news
from services.popular_service import get_popular_stocks
from services.screener.monthly_revenue import get_monthly_revenue
from services.stock_service import (
    get_fundamental_data,
    get_stock_overview,
    get_technical_indicators,
    normalize_ticker,
    search_tw_stocks,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/stock",
    tags=["stock"],
    dependencies=[Depends(require_feature_access("stock"))],
)


@router.get("/search")
async def search_stocks(q: str = ""):
    """搜尋台股代碼或名稱（回傳最多 10 筆）。"""
    if not q:
        return []
    return search_tw_stocks(q)


@router.get("/popular", response_model=PopularResponse)
async def get_popular(limit: int = 8):
    """熱門標的排行：成交值／漲幅／跌幅三榜（僅台股上市櫃普通股）。

    必須註冊在 `/{ticker}` 之前，否則會被那條 catch-all 當成股票代碼吃掉。
    """
    limit = max(1, min(limit, 20))
    try:
        data = get_popular_stocks(top_n=limit)
        return PopularResponse(**asdict(data))
    except Exception as e:
        logger.exception("Failed to get popular stocks")
        raise HTTPException(status_code=500, detail=str(e))


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


@router.get("/{ticker}/institutional")
async def get_institutional(ticker: str, days: int = 5):
    """三大法人買賣超（近 N 個交易日）。"""
    try:
        data = get_institutional_data(ticker, days=days)
        return asdict(data)
    except Exception as e:
        logger.exception("Failed to get institutional data for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/margin")
async def get_margin(ticker: str, days: int = 5):
    """融資融券資訊（近 N 個交易日）。"""
    try:
        data = get_margin_data(ticker, days=days)
        return asdict(data)
    except Exception as e:
        logger.exception("Failed to get margin data for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/news", response_model=NewsResponse)
async def get_news(ticker: str, limit: int = 10):
    """個股新聞（依公司名稱搜尋 Google News RSS，30 分鐘快取）。"""
    limit = max(1, min(limit, 20))
    try:
        overview = get_stock_overview(ticker)
        company_name = overview.name or ticker
        result = get_stock_news(overview.ticker, company_name, limit=limit)
        return NewsResponse(
            ticker=overview.ticker,
            query=result.query,
            articles=[
                {
                    "title": a.title,
                    "link": a.link,
                    "source": a.source,
                    "published": a.published,
                }
                for a in result.articles
            ],
            error=result.error,
        )
    except Exception as e:
        logger.exception("Failed to get news for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/monthly-revenue", response_model=MonthlyRevenueResponse)
async def get_monthly_revenue_route(ticker: str):
    """最新月營收快照（單月，僅上市 .TW；OTC 或查無資料回 404）。"""
    try:
        normalized = normalize_ticker(ticker)
        rev = get_monthly_revenue(normalized)
    except Exception as e:
        logger.exception("Failed to get monthly revenue for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e))
    if rev is None:
        raise HTTPException(status_code=404, detail="查無月營收資料（僅支援上市股票）")
    return MonthlyRevenueResponse(
        ticker=normalized,
        label=rev.label,
        revenue=rev.revenue,
        yoy=rev.yoy,
        mom=rev.mom,
        yoy_acc=rev.yoy_acc,
    )


@router.get("/{ticker}/industry-pe", response_model=IndustryPeResponse)
async def get_industry_pe_route(ticker: str):
    """個股 PE 在同產業中的分位數（僅陳述事實，非目標價；僅支援上市股票）。"""
    try:
        normalized = normalize_ticker(ticker)
        result = get_industry_pe(normalized)
    except Exception as e:
        logger.exception("Failed to get industry PE for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="查無足夠樣本可比較同業本益比")
    return IndustryPeResponse(**asdict(result))
