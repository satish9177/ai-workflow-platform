import logging
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    environment: str = "development"
    database_url: str
    redis_url: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int = 7 * 24 * 60
    encryption_key: str
    openai_api_key: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from_email: str
    app_base_url: str
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 60
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"
    db_pool_size: int = 25
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_command_timeout: int = 30
    db_connect_timeout: int = 10
    db_statement_timeout_ms: int = 60000
    db_idle_in_transaction_session_timeout_ms: int = 30000
    db_connection_hold_warn_seconds: float = 5.0
    arq_max_jobs: int = 10

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_config(self) -> "Settings":
        if self.environment == "production":
            if self.secret_key == "change-me-in-production":
                raise ValueError("SECRET_KEY must be changed in production")
            if not self.encryption_key:
                raise ValueError("ENCRYPTION_KEY must be configured in production")

        if not self.openai_api_key:
            logging.getLogger(__name__).warning("OPENAI_API_KEY is not configured")

        if self.db_pool_size < self.arq_max_jobs:
            logging.getLogger(__name__).warning(
                "DB_POOL_SIZE is smaller than ARQ_MAX_JOBS; DB pool pressure may increase"
            )

        return self


settings = Settings()
