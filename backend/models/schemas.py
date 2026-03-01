"""Pydantic request/response models for Navi API."""

from pydantic import BaseModel, Field


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="使用者問題")
    conversation_id: str | None = Field(None, description="對話 ID（多輪對話）")
    ticker: str | None = Field(None, description="相關股票代碼")


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


# ── Knowledge ────────────────────────────────────────────────────────────────

class KnowledgeStats(BaseModel):
    total_documents: int = 0
    categories: list[str] = []
    last_updated: str | None = None


class KnowledgeSearchResult(BaseModel):
    content: str
    metadata: dict = {}
    score: float | None = None
