"""Navi Backend — Configuration via pydantic-settings."""

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
    gemini_model_name: str = "gemini-2.0-flash"

    # Embedding
    embedding_model_name: str = "text-embedding-004"

    # Firestore
    firestore_collection_knowledge: str = "knowledge"

    # Auth
    auth_required: bool = True              # Set False in local dev to skip JWT
    cors_origins: str = ""                  # Comma-separated allowed origins; empty = deny all cross-origin

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


settings = Settings()
