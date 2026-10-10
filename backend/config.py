"""Navi Backend — Configuration via pydantic-settings."""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google Cloud
    google_cloud_project: str = ""
    google_application_credentials: str = ""

    # Gemini LLM — 依 tier 分層控制成本：
    # 付費層用 3.8 Flash（US$0.75/$3.75 每 1M tokens，2027-01-01 起翻倍），免費層用
    # 3.5 Flash-Lite（US$0.30/$2.50，預設 minimal thinking）。意圖分類沿用同一 tier 模型。
    # Gemini 2.5 全系列 2026-10-20 在 Vertex AI 退場；Gemini 3 的 PayGo 只開在 global/us/eu
    # 端點，所以 ChatVertexAI 必須明確給 location（vertexai.init 預設的 us-central1 會 404）。
    gemini_model_name: str = "gemini-3.8-flash"  # pro/unlimited/admin 層
    gemini_model_name_free: str = "gemini-3.5-flash-lite"  # free 層
    gemini_location: str = "global"
    # 付費層每次呼叫的 thinking 上限。3.8 Flash 預設 MEDIUM，一句話問題實測就燒 ~380 tokens，
    # ReAct 多步工具呼叫會放大延遲；SDK 2.1.x 沒有 thinking_level，用 budget 封頂近似 LOW。
    gemini_thinking_budget: int = 1024

    # Embedding
    embedding_model_name: str = "text-embedding-004"

    # Firestore
    firestore_collection_knowledge: str = "knowledge"

    # Auth
    auth_required: bool = True  # Set False in local dev to skip JWT
    cors_origins: str = ""  # Comma-separated allowed origins; empty = deny all cross-origin

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Screener — shared-secret token for Cloud Scheduler /api/screener/run
    screener_runner_token: str = ""
    # Screener Stage 3 LLM — 解讀層是「翻譯」而非深度推理，用 Flash-Lite 即可。
    # 實測 Pro 每檔約 US$0.03（76% 是 thinking tokens）；3.5 Flash-Lite 預設不思考。
    screener_llm_model: str = "gemini-3.5-flash-lite"
    # Screener email (optional)
    sendgrid_api_key: str = ""
    email_from_address: str = "notify@navi-stock.app"
    email_from_name: str = "Navi 智能選股"
    screener_unsubscribe_secret: str = ""
    screener_public_base_url: str = "https://navi-stock-analyzer.web.app"

    # TW 股價來源：'mis'（MIS 即時報價，T-0）或 'openapi'（TWSE/TPEx Open API，T-1 收盤）
    tw_quote_provider: str = "mis"

    # LINE Messaging API — channel secret 為空時 webhook 回 503（視為未啟用）。
    # 只有 access token 為空時走 dry-run：只 log 要送的內容、不呼叫 LINE。
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    # Cloud Tasks queue：webhook 先回 200，再由 task 另起 request 跑 agent
    # （Cloud Run 回完 response 後 CPU 會被降速）。留空 = 本機開發，改在行程內處理。
    line_tasks_queue: str = ""
    line_tasks_location: str = "asia-east1"


settings = Settings()


def model_for_tier(tier: str) -> str:
    """依使用者 tier 選擇 LLM 模型（成本分層）."""
    if tier in ("pro", "unlimited", "admin"):
        return settings.gemini_model_name
    return settings.gemini_model_name_free

# Sync credentials path to OS env so that google.auth.default() can find it.
if settings.google_application_credentials:
    os.environ.setdefault(
        "GOOGLE_APPLICATION_CREDENTIALS",
        settings.google_application_credentials,
    )
