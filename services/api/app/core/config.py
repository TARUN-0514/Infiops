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

    # --- AI layer -------------------------------------------------------------
    # Local-first: every job runs on the owner's PC through an OpenAI-compatible server
    # (Ollama http://localhost:11434/v1 or LM Studio http://localhost:1234/v1).
    local_enabled: bool = True
    local_base_url: str = "http://localhost:11434/v1"
    local_model: str = "qwen3:14b"  # chat and tools
    local_model_plan: str = ""  # optional bigger model for planning; empty = local_model
    local_model_fast: str = ""  # optional smaller model for extraction; empty = local_model

    # Cloud is optional and off by default. When enabled, the owner can send one
    # request to the cloud ("Use cloud") for a hard task. Secret data never goes.
    cloud_enabled: bool = False
    anthropic_api_key: SecretStr = Field(default=SecretStr(""))  # or ANTHROPIC_API_KEY
    cloud_model_chat: str = "claude-sonnet-5-5"
    cloud_model_plan: str = "claude-opus-5-5"
    cloud_model_fast: str = "claude-haiku-5-5"
    anthropic_refusal_fallback: bool = True
    cloud_daily_token_budget: int = 300_000  # hard cap per day across cloud calls

    # Embeddings: "ollama" (bge-m3, 1024 dims), "none" (full-text only), "hash" (tests).
    embedding_provider: Literal["ollama", "none", "hash"] = "ollama"
    ollama_url: str = "http://localhost:11434"
    embedding_model: str = "bge-m3"
    # Optional price table, USD per million tokens: {"model": [input, output]}.
    # Empty by default so NEXUS never shows a cost it cannot back up.
    model_prices: dict[str, list[float]] = {}
    max_agent_iterations: int = 8
    approval_ttl_hours: int = 24
    # Background jobs run inline (tests, or when no worker is running).
    jobs_inline: bool = False
    storage_dir: str = "./data/uploads"
    max_upload_mb: int = 10
    # Optional local vision model (e.g. qwen2.5vl:7b) to read text from images in the
    # knowledge base. Empty = images are stored but not read.
    local_model_vision: str = ""
    kb_max_upload_mb: int = 25

    # --- Integrations -----------------------------------------------------------
    # The address you open NEXUS at on the PC. OAuth redirects come back here.
    public_web_url: str = "http://localhost:3000"
    google_client_id: str = ""
    google_client_secret: SecretStr = Field(default=SecretStr(""))
    sync_interval_minutes: int = 10
    email_sync_days: int = 14  # first Gmail sync looks back this far

    # --- Notifications ----------------------------------------------------------
    # Web Push (VAPID). Generate with: python -m app.cli vapid
    vapid_public_key: str = ""
    vapid_private_key: SecretStr = Field(default=SecretStr(""))
    vapid_subject: str = "mailto:nexus@localhost"
    briefing_default_time: str = "07:30"  # owner's local time

    # --- Voice (local) ----------------------------------------------------------
    # Speech-to-text: any server that takes a multipart `file` and returns {"text": ...}:
    # the NEXUS voice server, whisper.cpp's server (Vulkan on AMD), or an OpenAI-style one.
    stt_url: str = "http://localhost:8880/v1/audio/transcriptions"
    stt_language: str = "en"  # empty = detect
    # Text-to-speech: POST {"input": ...} returns WAV (NEXUS voice server with Piper).
    tts_url: str = "http://localhost:8880/v1/audio/speech"
    tts_voice: str = "en_US-lessac-medium"
    voice_enabled: bool = True
    voice_max_upload_mb: int = 10
    pair_code_minutes: int = 10

    @property
    def google_ready(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret.get_secret_value())

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.public_web_url.rstrip('/')}/api/v1/integrations/google/callback"

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
