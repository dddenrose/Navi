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
    # 付費層用 Flash（US$0.30/$2.50 每 1M tokens），免費層用最便宜的 Flash-Lite
    # （US$0.10/$0.40）。意圖分類沿用同一 tier 模型。
    # 註：Gemini 3 家族目前本專案無存取權（preview 需 allowlist），待開放後再升級付費層。
    gemini_model_name: str = "gemini-2.5-flash"  # pro/unlimited/admin 層
    gemini_model_name_free: str = "gemini-2.5-flash-lite"  # free 層

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
    # Screener Stage 3 LLM — 解讀層是「翻譯」而非深度推理，用最便宜的 Flash-Lite 即可。
    # 實測 Pro 每檔約 US$0.03（76% 是 thinking tokens），Flash-Lite US$0.10/$0.40 每 1M tokens。
    screener_llm_model: str = "gemini-2.5-flash-lite"
    # Screener email (optional)
    sendgrid_api_key: str = ""
    email_from_address: str = "notify@navi-stock.app"
    email_from_name: str = "Navi 智能選股"
    screener_unsubscribe_secret: str = ""
    screener_public_base_url: str = "https://navi-stock-analyzer.web.app"

    # TW 股價來源：'mis'（MIS 即時報價，T-0）或 'openapi'（TWSE/TPEx Open API，T-1 收盤）
    tw_quote_provider: str = "mis"


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
