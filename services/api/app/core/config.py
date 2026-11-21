"""Application settings, read from environment variables (prefix NEXUS_)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEXUS_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    app_name: str = "NEXUS AI"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"
    redis_url: str = "redis://localhost:6379/0"

    # Secrets: never hard-coded. In production these must be set explicitly.
    jwt_secret: SecretStr = Field(default=SecretStr(""))
    encryption_key: SecretStr = Field(default=SecretStr(""))  # base64 of 32 bytes

    access_token_minutes: int = 15
    refresh_token_days: int = 30
    cookie_secure: bool = True
    cors_origins: list[str] = ["http://localhost:3000"]

    # Single-owner system: registration closes once the owner account exists.
    allow_registration_after_owner: bool = False

    login_rate_limit: int = 10  # attempts per window
    rate_limit_window_seconds: int = 300

    def require_secrets(self) -> None:
        missing = [
            name
            for name, value in (
                ("NEXUS_JWT_SECRET", self.jwt_secret),
                ("NEXUS_ENCRYPTION_KEY", self.encryption_key),
            )
            if not value.get_secret_value()
        ]
        if missing:
            raise RuntimeError(f"Missing required secrets: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
