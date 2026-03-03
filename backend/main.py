"""Navi — AI-Powered Stock Analyzer Backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import chat, knowledge, stock
from config import settings

# 正式環境關閉 Swagger /docs 與 /redoc，避免暴露 API 結構
_docs_url = "/docs" if settings.debug else None
_redoc_url = "/redoc" if settings.debug else None

app = FastAPI(
    title="Navi API",
    description="🧚 AI-Powered Stock Analyzer — Hey! Listen!",
    version="0.1.0",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
)

# CORS — 由 CORS_ORIGINS 環境變數控制，逗號分隔
# 正式環境：CORS_ORIGINS=https://navi-stock-analyzer.web.app
# 本機開發：CORS_ORIGINS=http://localhost:5173
_allowed_origins: list[str] = (
    [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if settings.cors_origins
    else (["*"] if settings.debug else [])  # 生產環境未設定 → 拒絕所有跨域
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 掛載路由
app.include_router(chat.router)
app.include_router(stock.router)
app.include_router(knowledge.router)


@app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "message": "🧚 Hey! Listen! Navi is ready."}


@app.get("/health", tags=["health"])
async def health():
    """公開 endpoint，供 Cloud Run health check 使用."""
    return {"status": "ok"}
