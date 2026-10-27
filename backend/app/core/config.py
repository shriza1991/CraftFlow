"""Centralized Application Configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env files."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Application Information
    APP_NAME: str = "CraftFlow"
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # One business per deployment. These values are public application context.
    BUSINESS_NAME: str = "Your Business"
    BUSINESS_DESCRIPTION: str = "A business offering products and services."
    BUSINESS_INDUSTRY: str = "general"

    # Database Configuration
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ages_art_db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30

    # AI & LLM Provider Configuration
    AI_PROVIDER: str = "mock"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Logging
    LOG_LEVEL: str = "INFO"

    # Security & CORS
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://localhost:5173",
        ]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json

                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # Provider Implementations (swappable without code rewrites)
    CRM_PROVIDER: str = "mock"
    WHATSAPP_PROVIDER: str = "mock"
    VECTOR_DB_PROVIDER: str = "pgvector"

    # Automation Boundary (n8n)
    N8N_BASE_URL: str = "http://localhost:5678"
    N8N_WEBHOOK_SECRET: str = "dev_n8n_webhook_secret_placeholder"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.APP_ENV == "production"

    @property
    def is_testing(self) -> bool:
        """Check if running in test mode."""
        return self.APP_ENV == "test"


@lru_cache
def get_settings() -> Settings:
    """Provide cached settings instance across application calls."""
    return Settings()
