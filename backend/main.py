"""Navi — AI-Powered Stock Analyzer Backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import chat, knowledge, stock

app = FastAPI(
    title="Navi API",
    description="🧚 AI-Powered Stock Analyzer — Hey! Listen!",
    version="0.1.0",
)

# CORS — 開發期允許所有來源，上線後限縮
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    return {"status": "ok"}
