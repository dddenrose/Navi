"""Pydantic request/response models for Navi API."""

from pydantic import BaseModel, Field


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="使用者問題")
    conversation_id: str | None = Field(None, description="對話 ID（多輪對話）")


class SourceReference(BaseModel):
    title: str = ""
    source_file: str = ""
    category: str = ""
    score: float | None = None


class ChatResponse(BaseModel):
    response: str
    sources: list[SourceReference] = []


# ── Stock ────────────────────────────────────────────────────────────────────

class StockOverview(BaseModel):
    ticker: str
    name: str = ""
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    volume: int | None = None
    market_cap: int | None = None
    currency: str = ""
    exchange: str = ""
    high_52w: float | None = None
    low_52w: float | None = None


class TechnicalResponse(BaseModel):
    ticker: str
    period: str = "3mo"
    current_price: float | None = None
    # 均線
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    ma_trend: str = ""
    # RSI
    rsi_14: float | None = None
    rsi_signal: str = ""
    # MACD
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    macd_cross: str = ""
    # KD
    k_value: float | None = None
    d_value: float | None = None
    kd_signal: str = ""
    # 布林通道
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_position: str = ""
    # 支撐/阻力
    supports: list[tuple[str, float]] = []
    resistances: list[tuple[str, float]] = []
    fibonacci_levels: dict[str, float] = {}
    swing_high: float | None = None
    swing_low: float | None = None
    # 停損
    stop_loss: float | None = None
    stop_loss_note: str = ""
    risk_reward_note: str = ""
    # 綜合
    summary: str = ""


class FundamentalResponse(BaseModel):
    ticker: str
    name: str = ""
    # 估值
    pe_ratio: float | None = None
    forward_pe: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    # 獲利能力
    roe: float | None = None
    roa: float | None = None
    profit_margin: float | None = None
    operating_margin: float | None = None
    # 成長
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    # 每股
    eps: float | None = None
    forward_eps: float | None = None
    dividend_yield: float | None = None
    # 合理價位估算
    cheap_price: float | None = None
    fair_price: float | None = None
    expensive_price: float | None = None
    valuation_note: str = ""
    # 分類
    sector: str = ""
    industry: str = ""
    description: str = ""


# ── Knowledge ────────────────────────────────────────────────────────────────

class KnowledgeStats(BaseModel):
    total_documents: int = 0
    categories: list[str] = []
    last_updated: str | None = None


class KnowledgeSearchResult(BaseModel):
    content: str
    metadata: dict = {}
    score: float | None = None
