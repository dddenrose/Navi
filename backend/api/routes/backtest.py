"""Backtest API — 策略回測."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import verify_firebase_token
from services.backtest_service import run_backtest

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/backtest",
    tags=["backtest"],
    dependencies=[Depends(verify_firebase_token)],
)


# ── Request / Response models ────────────────────────────────────────────────


class CustomCondition(BaseModel):
    indicator: str = Field(..., description="指標名稱：rsi / macd_cross / ma_cross")
    op: str = Field(..., description="運算子：< / > / ==")
    value: float | str = Field(..., description="比較值")
    action: str = Field("buy", description="觸發動作：buy / sell")


class BacktestRequest(BaseModel):
    ticker: str = Field(..., min_length=1, description="股票代碼")
    strategy: str = Field("ma_cross", description="策略名稱：ma_cross / rsi / macd / custom")
    period: str = Field("1y", description="回測期間：3mo / 6mo / 1y / 2y")
    initial_capital: float = Field(1_000_000, gt=0, description="初始資金")
    strategy_params: dict | None = Field(None, description="策略參數（選填）")
    custom_conditions: list[CustomCondition] | None = Field(
        None, description="自訂條件（strategy=custom 時使用）"
    )


class TradeResponse(BaseModel):
    date: str
    action: str
    price: float
    shares: int
    value: float
    reason: str = ""


class EquityPointResponse(BaseModel):
    date: str
    equity: float
    drawdown: float = 0.0


class BacktestResponse(BaseModel):
    ticker: str
    strategy: str
    period: str
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 1_000_000
    final_equity: float = 0.0
    total_return: float = 0.0
    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    benchmark_return: float = 0.0
    trades: list[TradeResponse] = []
    equity_curve: list[EquityPointResponse] = []
    error: str = ""


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("", response_model=BacktestResponse)
async def execute_backtest(req: BacktestRequest):
    """執行策略回測，回傳績效報告、交易紀錄與權益曲線."""
    allowed_strategies = {"ma_cross", "rsi", "macd", "custom"}
    if req.strategy not in allowed_strategies:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的策略：{req.strategy}。可選：{', '.join(allowed_strategies)}",
        )

    allowed_periods = {"3mo", "6mo", "1y", "2y"}
    if req.period not in allowed_periods:
        raise HTTPException(
            status_code=400,
            detail=f"不支援的回測期間：{req.period}。可選：{', '.join(allowed_periods)}",
        )

    try:
        custom_conds = None
        if req.custom_conditions:
            custom_conds = [c.model_dump() for c in req.custom_conditions]

        result = run_backtest(
            ticker=req.ticker,
            strategy=req.strategy,
            period=req.period,
            initial_capital=req.initial_capital,
            strategy_params=req.strategy_params,
            custom_conditions=custom_conds,
        )

        # Convert dataclass → dict → response
        data = asdict(result)
        # Convert TradeAction enum values to strings
        for t in data["trades"]:
            t["action"] = t["action"].value if hasattr(t["action"], "value") else t["action"]

        return BacktestResponse(**data)

    except Exception as e:
        logger.exception("Backtest failed for %s", req.ticker)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies")
async def list_strategies():
    """列出可用的回測策略."""
    return {
        "strategies": [
            {
                "name": "ma_cross",
                "label": "均線交叉",
                "description": "短均線（MA5）上穿長均線（MA20）時買入，下穿時賣出",
                "params": {
                    "short_window": {"type": "int", "default": 5, "description": "短均線天數"},
                    "long_window": {"type": "int", "default": 20, "description": "長均線天數"},
                },
            },
            {
                "name": "rsi",
                "label": "RSI 指標",
                "description": "RSI 超賣區（< 30）回升時買入，超買區（> 70）回落時賣出",
                "params": {
                    "rsi_period": {"type": "int", "default": 14, "description": "RSI 週期"},
                    "oversold": {"type": "float", "default": 30, "description": "超賣門檻"},
                    "overbought": {"type": "float", "default": 70, "description": "超買門檻"},
                },
            },
            {
                "name": "macd",
                "label": "MACD 指標",
                "description": "MACD 金叉（柱狀由負轉正）買入，死叉（柱狀由正轉負）賣出",
                "params": {
                    "fast": {"type": "int", "default": 12, "description": "快速 EMA"},
                    "slow": {"type": "int", "default": 26, "description": "慢速 EMA"},
                    "signal_period": {"type": "int", "default": 9, "description": "信號線 EMA"},
                },
            },
            {
                "name": "custom",
                "label": "自訂條件",
                "description": "組合多個指標條件（RSI、MACD、均線）",
                "params": {},
            },
        ]
    }
