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

    # Gemini LLM
    gemini_model_name: str = "gemini-2.5-pro"

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
    # Screener email (optional)
    sendgrid_api_key: str = ""
    email_from_address: str = "notify@navi-stock.app"
    email_from_name: str = "Navi 智能選股"
    screener_unsubscribe_secret: str = ""
    screener_public_base_url: str = "https://navi-stock-analyzer.web.app"

    # TW 股價來源：'openapi'（TWSE/TPEx Open API，T-1 收盤）或 'mis'（MIS 即時報價，T-0）
    tw_quote_provider: str = "openapi"


settings = Settings()

# Sync credentials path to OS env so that google.auth.default() can find it.
if settings.google_application_credentials:
    os.environ.setdefault(
        "GOOGLE_APPLICATION_CREDENTIALS",
        settings.google_application_credentials,
    )
