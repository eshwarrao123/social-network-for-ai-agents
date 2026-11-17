"""
Application configuration loaded from environment variables.
Uses pydantic-settings for type-safe, validated config.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, field_validator, model_validator
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
    jwt_access_token_expire_minutes: int = 30  # Configurable default: 30 minutes
    jwt_expire_minutes: int | None = None  # Backward-compatible alias
    jwt_issuer: str = "social-network-for-ai-agents"
    jwt_audience: str = "agent-network"
    # Fernet symmetric encryption key for webhook secrets at rest (urlsafe base64 32 bytes)
    webhook_encryption_key: str = ""
    # Webhook Outbound Delivery & SSRF Security
    webhook_allowed_ports: list[int] = [443, 8443]
    webhook_connect_timeout: float = 3.0
    webhook_read_timeout: float = 5.0
    webhook_max_delivery_attempts: int = 3
    webhook_retry_backoff_seconds: float = 2.0
    webhook_allow_http: bool = False

    # Platform Operations & Metrics Observability Security
    operator_token: str = ""
    allow_internal_metrics_scraping: bool = False

    @property
    def token_expire_minutes(self) -> int:
        """Returns the effective access token lifetime in minutes, respecting legacy setting if set."""
        if self.jwt_expire_minutes is not None:
            return self.jwt_expire_minutes
        return self.jwt_access_token_expire_minutes

    # Ollama / Embedding
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_embed_endpoint: str = "/api/embed"
    embedding_dimensions: int = 768
    ollama_connect_timeout: float = 5.0
    ollama_read_timeout: float = 30.0

    # LLM
    llm_provider: Literal["ollama", "openai", "anthropic", "disabled"] = "ollama"
    llm_model: str = "llama3.2"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_timeout_seconds: float = 30.0
    llm_max_tokens: int = 512
    llm_temperature: float = 0.2
    llm_max_comment_length: int = 1000
    llm_min_confidence: float = 0.5
    llm_lease_duration_seconds: int = 60

    # Feedback Learning (P7)
    feedback_learning_enabled: bool = True
    feedback_learning_rate_pos: float = 0.08
    feedback_learning_rate_neg: float = 0.04
    feedback_min_confidence: float = 0.60
    feedback_min_samples: int = 3
    feedback_anchor_cosine_min: float = 0.70  # Maximum drift constraint (cos(v_t, v_0) >= 0.70)
    feedback_weight: float = 0.30             # Weight of learned preference in routing
    feedback_max_adjustment: float = 0.15     # Max clamp on feedback score delta
    feedback_lease_duration_seconds: int = 60

    # Routing
    routing_alpha: float = 0.65          # Weight for semantic vs metadata (alpha * semantic + (1-alpha) * metadata)
    routing_threshold: float = 0.60      # Provisional initial calibration to support cross-industry partnerships
    max_notifications_per_post: int = 5  # Top N candidates notified per post
    max_routing_candidates: int = 50     # Top K candidates retrieved from pgvector
    routing_algorithm_version: str = "v4.2-hybrid"
    routing_weight_industry: float = 0.30
    routing_weight_tag: float = 0.30
    routing_weight_capability: float = 0.25
    routing_weight_diversity: float = 0.10   # Cross-enterprise synergy policy factor (not a semantic similarity signal)
    routing_weight_recency: float = 0.05

    # Workers
    worker_concurrency: int = 4
    worker_retry_max: int = 3
    worker_retry_backoff_seconds: int = 5
    redis_claim_min_idle_ms: int = 120000  # 120s idle threshold before reclaiming abandoned messages

    @model_validator(mode="after")
    def validate_routing_and_worker_config(self) -> Settings:
        meta_sum = (
            self.routing_weight_industry
            + self.routing_weight_tag
            + self.routing_weight_capability
            + self.routing_weight_diversity
            + self.routing_weight_recency
        )
        if abs(meta_sum - 1.0) > 1e-4:
            raise ValueError(
                f"Metadata routing weights must sum to 1.0 (got {meta_sum:.4f}: "
                f"industry={self.routing_weight_industry}, tag={self.routing_weight_tag}, "
                f"capability={self.routing_weight_capability}, diversity={self.routing_weight_diversity}, "
                f"recency={self.routing_weight_recency})"
            )
        if not (0.0 <= self.routing_alpha <= 1.0):
            raise ValueError(f"routing_alpha must be between 0.0 and 1.0 (got {self.routing_alpha})")
        if not (0.0 <= self.routing_threshold <= 1.0):
            raise ValueError(f"routing_threshold must be between 0.0 and 1.0 (got {self.routing_threshold})")
        if self.redis_claim_min_idle_ms <= 0:
            raise ValueError(f"redis_claim_min_idle_ms must be positive (got {self.redis_claim_min_idle_ms})")
        return self

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
