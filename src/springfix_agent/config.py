"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for SpringFix Agent.

    Loaded from environment variables or a local ``.env`` file.
    M0 uses only ``allow_root``; LLM-related fields will be added in M2.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    allow_root: Path = Field(default=Path("./samples"))
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    app_version: str = Field(default="0.1.0")

    def resolved_allow_root(self) -> Path:
        """Return allow_root as an absolute, canonicalized path."""
        return self.allow_root.resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton per process)."""
    return Settings()
