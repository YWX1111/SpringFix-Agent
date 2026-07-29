"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for SpringFix Agent.

    M2 adds the LLM_* block. When LLM_PROVIDER="mock" (default) no API
    key is required and the agent runs entirely offline.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    allow_root: Path = Field(default=Path("./samples"))
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    # LLM configuration (M2)
    llm_provider: str = Field(default="mock")
    llm_base_url: str = Field(default="")
    llm_api_key: str = Field(default="")
    llm_model: str = Field(default="")
    llm_timeout_seconds: int = Field(default=60)
    llm_max_retries: int = Field(default=2)
    llm_temperature: float = Field(default=0.0)
    llm_max_output_tokens: int = Field(default=2000)

    def resolved_allow_root(self) -> Path:
        """Return allow_root as an absolute, canonicalized path."""
        return self.allow_root.resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton per process)."""
    return Settings()
