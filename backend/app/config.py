"""
Application configuration loaded from environment variables.
Uses pydantic-settings for type-safe, validated config.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: Literal["development", "staging", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://asama:asama_pass@localhost:5432/asama_db"
    database_url_sync: str = "postgresql+psycopg2://asama:asama_pass@localhost:5432/asama_db"
    database_test_url: str = "postgresql+asyncpg://asama:asama_pass@localhost:5432/asama_test_db"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Auth & Security
    jwt_secret_key: str = "INSECURE-CHANGE-ME"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24h
    # Fernet symmetric encryption key for webhook secrets at rest (urlsafe base64 32 bytes)
    webhook_encryption_key: str = ""

    # Ollama / Embedding
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768

    # LLM
    llm_provider: Literal["ollama", "openai", "anthropic", "disabled"] = "ollama"
    llm_model: str = "llama3.2"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Routing
    routing_alpha: float = 0.65          # Weight for semantic vs metadata
    routing_threshold: float = 0.30      # Min score to notify
    max_notifications_per_post: int = 50
    max_routing_candidates: int = 500

    # Workers
    worker_concurrency: int = 4
    worker_retry_max: int = 3
    worker_retry_backoff_seconds: int = 5

    # CORS
    cors_origins: str = "http://localhost:3000"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str) -> str:
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
