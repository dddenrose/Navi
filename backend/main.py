"""Navi — AI-Powered Stock Analyzer Backend."""

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import backtest, chat, knowledge, portfolio, stock
from api.routes import admin as admin_route
from config import settings

# 結構化 logging：交由 root logger 輸出 stdout，便於 Cloud Run 收集
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s",
)


# 替預設 record 補上 request_id，避免無 context 時 KeyError
class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


logging.getLogger().addFilter(_RequestIdFilter())

# 降低第三方 logger 噪音
for noisy in ("urllib3", "yfinance", "google.auth", "google.api_core"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

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
_allowed_origins: list[str] = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if not _allowed_origins and settings.debug:
    # 本機開發預設允許 Vite dev server
    _allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

# 安全性：避免 wildcard + allow_credentials 同時開啟（CORS 規範禁止）
_allow_credentials = bool(_allowed_origins) and "*" not in _allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Observability：request-id + access log + 全域錯誤處理 ───────────────────


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """為每個請求注入 X-Request-ID 並記錄 access log + 處理時間."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "Unhandled error %s %s after %.1fms",
            request.method,
            request.url.path,
            elapsed_ms,
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    # Skip access log for health probes 避免噪音
    if request.url.path not in {"/", "/health"}:
        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={"request_id": request_id},
        )
    return response


# 掛載路由
app.include_router(chat.router)
app.include_router(stock.router)
app.include_router(knowledge.router)
app.include_router(portfolio.router)
app.include_router(backtest.router)
app.include_router(admin_route.router)


@app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "message": "🧚 Hey! Listen! Navi is ready."}


@app.get("/health", tags=["health"])
async def health():
    """公開 endpoint，供 Cloud Run health check 使用."""
    return {"status": "ok"}
