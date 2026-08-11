"""Unified Settings loading and redacted Live configuration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from springfix_agent.benchmark.runner import (
    BenchmarkConfigurationError,
    read_live_configuration,
)
from springfix_agent.config import Settings

LLM_ENV_NAMES = (
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "LLM_TEMPERATURE",
    "LLM_MAX_OUTPUT_TOKENS",
)


def _clear_llm_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in LLM_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_settings_loads_provider_from_explicit_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_llm_environment(monkeypatch)
    env_file = tmp_path / "benchmark.env"
    env_file.write_text("LLM_PROVIDER=openai_compatible\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.llm_provider == "openai_compatible"


def test_os_environment_overrides_explicit_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_llm_environment(monkeypatch)
    env_file = tmp_path / "benchmark.env"
    env_file.write_text("LLM_MODEL=file-model\n", encoding="utf-8")
    monkeypatch.setenv("LLM_MODEL", "os-model")

    settings = Settings(_env_file=env_file)

    assert settings.llm_model == "os-model"


def test_live_config_safe_output_contains_no_secret_or_auth_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_llm_environment(monkeypatch)
    env_file = tmp_path / "benchmark.env"
    env_file.write_text(
        "\n".join(
            (
                "LLM_PROVIDER=openai_compatible",
                "LLM_BASE_URL=https://llm.example.test/v1?tenant=private",
                "LLM_API_KEY=sk-test-secret-value",
                "LLM_MODEL=live-model",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)
    configuration = read_live_configuration(settings)
    safe_output = json.dumps(configuration.safe_dict(), ensure_ascii=False)

    assert configuration.api_key_configured is True
    assert configuration.base_url_host == "llm.example.test"
    assert "sk-" not in safe_output
    assert "test-secret-value" not in safe_output
    assert "Bearer" not in safe_output
    assert ".env" not in safe_output
    assert "tenant=private" not in safe_output


def test_missing_live_config_returns_explicit_missing_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_llm_environment(monkeypatch)
    settings = Settings(_env_file=tmp_path / "does-not-exist.env")

    with pytest.raises(BenchmarkConfigurationError, match="LLM_PROVIDER") as exc_info:
        read_live_configuration(settings)

    message = str(exc_info.value)
    assert "LLM_BASE_URL" in message
    assert "LLM_API_KEY" in message
    assert "LLM_MODEL" in message
